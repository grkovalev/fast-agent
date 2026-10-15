"""Prepared bounded context attachment and bundles; activated with the UI in T76."""
import asyncio
import hashlib
import json

from pydantic import Field

from .canonical import CanonicalDocument
from .contracts import OutlineSection, ScoredItem, SourceRange, TextChunk, V2Contract
from .findings_batching import (
    AtomicJevItem,
    JevBatchCancelled,
    JevBatchExecution,
    JevBatchFailure,
    JevBatchPlan,
    execute_jev_batches,
    pack_jev_items,
    run_live_jev_batches,
    serialized,
)
from .findings_builders import build_context_request
from .findings_contracts import (
    ConceptChunkCandidates,
    ConceptLineAssignment,
    ContextPoolRange,
    ContextRole,
    ContextRoleAnswer,
    FindingContextCandidate,
    FindingContextLink,
    FindingContextPool,
    FindingEvidenceBundle,
    FindingLineCandidate,
    FindingsFilingMetadata,
    FindingsInputIdentity,
    FindingsPhase,
    FindingsStepResult,
    JudgmentProvenance,
    Omission,
    VisibleFindingLine,
    visible_numeric_spans,
)
from .findings_lines import _input_hash
from .findings_policy import FindingsPolicy, SupportDecision, support_decision
from .findings_storage import reusable_input


class FindingsContextPlan(V2Contract):
    request_allowance: int = Field(ge=1)
    filing: FindingsFilingMetadata
    pools: list[FindingContextPool] = Field(max_length=3)
    sources: list[FindingLineCandidate] = Field(max_length=10000)
    assignments: list[ConceptLineAssignment] = Field(max_length=10000)
    candidates: list[FindingContextCandidate]
    # Text is shared once, keyed by canonical line; never whole chunks/outline.
    context_lines: dict[int, VisibleFindingLine]
    omissions: list[Omission]
    identity: FindingsInputIdentity
    batches: JevBatchPlan


class FindingsContextResult(V2Contract):
    pools: list[FindingContextPool]
    links: list[FindingContextLink]
    bundles: list[FindingEvidenceBundle]
    step: FindingsStepResult
    execution: JevBatchExecution


class FindingsContextFailure(Exception):
    def __init__(self, result: FindingsContextResult):
        self.result = result
        super().__init__(result.step.reason)


class FindingsContextCancelled(asyncio.CancelledError):
    def __init__(self, result: FindingsContextResult):
        self.result = result
        super().__init__('Findings context cancelled')


def _items(filing, sources, candidates, lines, pools, model, policy):
    by_id = {x.candidate_id: x for x in sources}
    by_concept = {x.concept: x for x in pools}
    return [AtomicJevItem(item_id=x.link_id, request=build_context_request(
        filing, by_id[x.source_candidate_id], lines[x.context_range.start_line],
        context_section_id=x.section_id,
        allowed_pool=[r.source_range for r in by_concept[by_id[x.source_candidate_id].concept].ranges
                      if r.section_id == x.section_id], model=model, policy=policy, enforce_budget=False))
        for x in candidates]


def _identity_hash(items, pools, candidates, sources, assignments, omissions):
    # Bind enumeration/ownership/caps too. Chunk ownership uses exact coverage,
    # so a new run's local chunk IDs can reuse the same semantic work.
    ownership = {}
    for pool in pools:
        for r in pool.ranges:
            ownership.setdefault(r.chunk_id, []).append(reusable_input(r.model_dump(mode='json')))
    value = {
        'pools': [x.model_dump(mode='json') for x in pools],
        'candidates': [x.model_dump(mode='json', exclude={'owning_chunk_ids'}) |
                       {'owning_coverage': sorted((ownership[key] for key in x.owning_chunk_ids),
                                                 key=lambda v: json.dumps(v, sort_keys=True))}
                       for x in candidates],
        'sources': [{'candidate_id': x.candidate_id, 'concept': x.concept.value,
                     'source_range': x.source_range.model_dump(mode='json'),
                     'exact_text': x.exact_text} for x in sources],
        'assignments': [{'candidate_id': x.candidate_id, 'answer': x.answer.model_dump(),
                         'decision': x.decision.value} for x in assignments],
        'omissions': [x.model_dump(mode='json') for x in omissions],
    }
    return hashlib.sha256((json.dumps(reusable_input(value), sort_keys=True) + _input_hash(items)).encode()).hexdigest()


def build_context_plan(document: CanonicalDocument, filing: FindingsFilingMetadata,
                       concepts: list[ConceptChunkCandidates], sources: list[FindingLineCandidate],
                       assignments: list[ConceptLineAssignment], chunks: list[TextChunk],
                       scores: list[ScoredItem], sections: list[OutlineSection], *, model: str,
                       policy: FindingsPolicy, max_requests: int | None = None) -> FindingsContextPlan:
    if model not in ('jev-1.13.0', 'jev-1.14.0'):
        raise ValueError('Context requires a pinned verified actual JEV model')
    if filing.filing_id != document.ref.filing_id:
        raise ValueError('Filing metadata does not belong to canonical document')
    if len(sources) > policy.max_candidate_lines:
        raise ValueError('Source count exceeds Findings candidate policy')
    if len({x.concept for x in concepts}) != len(concepts):
        raise ValueError('Concept pools must be unique')
    section_map = {x.section_id: x.primary_range for x in sections}
    chunk_map = {x.chunk_id: x for x in chunks}
    if len(chunk_map) != len(chunks) or len(section_map) != len(sections):
        raise ValueError('Chunk and section IDs must be unique')
    for section in sections:
        document.slice(section.primary_range)
    def coverage(chunk):
        section = section_map[chunk.section_id]
        for kind, r in [('core', chunk.core_range),
                        *[('preceding_context', r) for r in chunk.context_ranges]]:
            document.slice(r)
            if (r.start_character is not None or r.start_line < section.start_line or
                    r.end_line > section.end_line or
                    (kind == 'preceding_context' and r.end_line >= chunk.core_range.start_line)):
                raise ValueError('Context coverage crosses section or preceding-overlap contract')
            yield ContextPoolRange(chunk_id=chunk.chunk_id, section_id=chunk.section_id,
                                   source_range=r, kind=kind)
    thresholds = {x.relevance_threshold for x in concepts}
    if len(thresholds) > 1:
        raise ValueError('Context pools require one upstream relevance threshold')
    relevance_threshold = next(iter(thresholds), 1.0)
    retained = []
    if len({x.item_id for x in scores}) != len(scores):
        raise ValueError('Score IDs must be unique')
    for score in scores:
        if score.item_id not in chunk_map:
            raise ValueError('Score references unavailable chunk')
        if score.policy_decision == 'selected' and any(
                t in score.target_scores and score.target_scores[t] >= relevance_threshold
                for t in ('earnings_change', 'comparability')):
            retained.append(chunk_map[score.item_id])
    admitted = {x.chunk_id: x for x in retained}
    for concept in concepts:
        for reference in concept.chunks:
            chunk = reference.chunk
            if chunk_map.get(chunk.chunk_id) != chunk:
                raise ValueError('Concept chunk differs from retained chunk')
            admitted[chunk.chunk_id] = chunk
    ranges = [r for chunk in sorted(admitted.values(), key=lambda x: (
        x.core_range.start_line, x.core_range.end_line, x.chunk_id)) for r in coverage(chunk)]
    pools = [FindingContextPool(concept=x.concept, ranges=ranges)
             for x in sorted(concepts, key=lambda x: x.concept.value)]
    if len({x.candidate_id for x in sources}) != len(sources) or len({x.candidate_id for x in assignments}) != len(assignments):
        raise ValueError('Source and assignment IDs must be unique')
    source_map = {x.candidate_id: x for x in sources}
    supported = []
    for assignment in assignments:
        source = source_map[assignment.candidate_id]
        if (assignment.source_range != source.source_range or assignment.concept != source.concept or
                document.slice(source.source_range) != source.exact_text or
                assignment.provenance.policy_hash != policy.identity() or
                assignment.decision != policy.source_decision(assignment.answer.noul)):
            raise ValueError('Assignment/source/policy mismatch')
        concept = next(x for x in concepts if x.concept == source.concept)
        owners = {x.chunk.chunk_id: x for x in concept.chunks}
        if any(owners.get(x.chunk.chunk_id) != x for x in source.owners):
            raise ValueError('Source owners must be concept-candidate cores')
        if chunk_map[source.owning_chunk_id].section_id != source.section_id:
            raise ValueError('Source section differs from owning chunk')
        if assignment.decision == SupportDecision.SUPPORTED:
            supported.append((source, assignment))
    supported.sort(key=lambda pair: (pair[0].concept.value, pair[0].source_range.start_line, pair[0].candidate_id))
    selected_sources = [x for x, _ in supported]
    selected_assignments = [x for _, x in supported]
    candidates, omissions, context_lines = [], [], {}
    for source in selected_sources:
        pool = next(x for x in pools if x.concept == source.concept)
        owned = {}
        for r in pool.ranges:
            if r.section_id == source.section_id:
                for n in range(r.source_range.start_line, r.source_range.end_line + 1):
                    owned.setdefault(n, set()).add(r.chunk_id)
        if source.owning_chunk_id not in owned.get(source.source_range.start_line, set()):
            raise ValueError('Supported source is outside owning concept pool')
        structural, local = [], []
        for n in sorted(owned):
            if n == source.source_range.start_line:
                continue
            line = document.lines[n-1]
            spans = visible_numeric_spans(line.text)
            # Table headers include numeric comparative years; ordinary value rows do not.
            is_structural = line.element_type in ('heading', 'caption') or (
                line.element_type == 'table_row' and (not spans or (
                    any(1900 <= x.displayed_amount <= 2100 for x in spans) and all(
                        (1 <= x.displayed_amount <= 31 or 1900 <= x.displayed_amount <= 2100)
                        and '.' not in x.raw_text for x in spans))))
            near = abs(n-source.source_range.start_line) <= policy.local_context_lines_each_direction
            if is_structural:
                structural.append(n)
            if near:
                local.append(n)
        distance = lambda n, origin=source.source_range.start_line: (abs(n-origin), n)
        structural.sort(key=distance)
        local.sort(key=distance)
        order = list(dict.fromkeys(structural[:policy.reserved_structural_context_candidates] + local + structural))
        admitted = set(order[:policy.max_context_candidates_per_bundle])
        # Range-grouped exclusions stay bounded even for a large allowed section.
        excluded = []
        other_sections = sorted({r.section_id for r in pool.ranges if r.section_id != source.section_id})
        if other_sections:
            omissions.append(Omission(item_id=source.candidate_id+'-ctx-other-sections', coverage_cut=False,
                kind='unavailable_context', reason=f'Cross-section coverage excluded: {len(other_sections)} sections'))
        for n in sorted(owned):
            if n == source.source_range.start_line:
                continue
            link_id = source.candidate_id + '-ctx-' + str(n)
            if n not in admitted:
                capped = n in order
                if excluded and excluded[-1][1] == n-1 and excluded[-1][2] == capped:
                    excluded[-1] = (excluded[-1][0], n, capped)
                else:
                    excluded.append((n, n, capped))
                continue
            r = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                            start_line=n, end_line=n)
            context_lines[n] = VisibleFindingLine(source_range=r, exact_text=document.slice(r))
            candidates.append(FindingContextCandidate(link_id=link_id, source_candidate_id=source.candidate_id,
                context_range=r, section_id=source.section_id, owning_chunk_ids=sorted(owned[n]), structural=n in structural))
        for start, end, capped in excluded:
            omissions.append(Omission(item_id=source.candidate_id+'-ctx-'+str(start), coverage_cut=capped,
                kind='count_limit' if capped else 'unavailable_context',
                reason=f'Lines {start}–{end}: '+('Context candidate cap' if capped else
                       'Outside local/structural search within allowed pool')))
    cap = policy.max_jev_requests if max_requests is None else max_requests
    if not 1 <= cap <= policy.max_jev_requests:
        raise ValueError('Context request allowance must fit Findings policy')
    items = _items(filing, selected_sources, candidates, context_lines, pools, model, policy)
    identity = FindingsInputIdentity(canonical_source_hashes=[document.ref.source_hash],
        exact_inputs_hash=_identity_hash(items, pools, candidates, selected_sources, selected_assignments, omissions),
        phase=FindingsPhase.ATTACH, policy_hash=policy.identity(), question_version=policy.question_version,
        model_identity=model)
    return FindingsContextPlan(request_allowance=cap, filing=filing, pools=pools, sources=selected_sources,
        assignments=selected_assignments, candidates=candidates, context_lines=context_lines, omissions=omissions,
        identity=identity, batches=pack_jev_items(items, policy.attach_budget, cap))


def context_result(plan: FindingsContextPlan, execution: JevBatchExecution,
                   policy: FindingsPolicy) -> FindingsContextResult:
    if plan.identity.policy_hash != policy.identity():
        raise ValueError('Context policy differs from plan')
    answers, provenance = {}, {}
    for completed in execution.completed:
        for q, (item, original) in completed.batch.routes.items():
            answers.setdefault(item, {})[original] = completed.response.answers[q]
            provenance[item, original] = JudgmentProvenance(model=completed.response.model,
                call_id=completed.batch.batch_id, question_id=q, question_version=policy.question_version,
                policy_hash=policy.identity(), request_hash=hashlib.sha256(serialized(completed.batch.request).encode()).hexdigest(),
                cached=completed.cached)
    omissions = list(plan.omissions) + [Omission(item_id=x.item_id, reason=x.reason, coverage_cut=True,
        kind='size_limit' if x.reason == 'atomic_request_limit' else 'count_limit') for x in execution.omissions]
    links, bundles = [], []
    for source, assignment in zip(plan.sources, plan.assignments, strict=True):
        current = []
        for candidate in plan.candidates:
            if candidate.source_candidate_id != source.candidate_id or candidate.link_id not in answers:
                continue
            raw = answers[candidate.link_id]
            decision = support_decision(raw['context_support'].noul, policy.source_uncertain_threshold, policy.context_support_threshold)
            current.append(FindingContextLink(link_id=candidate.link_id, source_candidate_id=source.candidate_id,
                concept=source.concept, source_range=source.source_range, context_range=candidate.context_range,
                section_id=source.section_id, owning_chunk_ids=candidate.owning_chunk_ids,
                support=raw['context_support'], provenance=provenance[candidate.link_id, 'context_support'],
                roles=[ContextRoleAnswer(role=role, answer=raw[role.value],
                    decision=support_decision(raw[role.value].noul, policy.source_uncertain_threshold, policy.context_support_threshold),
                    provenance=provenance[candidate.link_id, role.value]) for role in ContextRole],
                decision='selected' if decision == SupportDecision.SUPPORTED else decision.value,
                reason=f'General context support {decision.value}; roles judged independently'))
        supported = sorted((x for x in current if x.decision == 'selected'), key=lambda x: (
            -sum(r.decision == SupportDecision.SUPPORTED for r in x.roles), -x.support.noul,
            abs(x.context_range.start_line-source.source_range.start_line), x.context_range.start_line))
        selected = {x.link_id for x in supported[:policy.max_selected_context_lines_per_bundle]}
        for index, link in enumerate(current):
            if link.decision == 'selected' and link.link_id not in selected:
                link = link.model_copy(update={'decision':'omitted',
                    'reason':'Selected context line cap; raw answers retained'})
                current[index] = link
                omissions.append(Omission(item_id=link.link_id, reason=link.reason, coverage_cut=True, kind='count_limit'))
        links.extend(current)
        context = sorted((x for x in current if x.decision == 'selected'), key=lambda x: x.context_range.start_line)
        resolved = {r.role for x in context for r in x.roles if r.decision == SupportDecision.SUPPORTED}
        bundles.append(FindingEvidenceBundle(bundle_id='bundle-'+source.candidate_id.removeprefix('line-'),
            concept=source.concept, source=source, assignment=assignment, context_links=context,
            unresolved_roles=[r for r in ContextRole if r not in resolved],
            omissions=[x for x in omissions if x.item_id.startswith(source.candidate_id+'-ctx-')]))
    successful = execution.status in ('completed', 'partial')
    status = 'partial' if successful and any(x.coverage_cut for x in omissions) else execution.status
    step = FindingsStepResult(phase=FindingsPhase.ATTACH, status=status,
        availability='final' if successful else 'checkpointed' if links else 'unavailable',
        input_hash=plan.identity.exact_inputs_hash, policy_hash=policy.identity(), accounting=execution.accounting,
        output_ids=[x.bundle_id for x in bundles], omissions=omissions,
        reason=execution.error or 'Bounded same-section canonical context only; unresolved roles remain explicit')
    return FindingsContextResult(pools=plan.pools, links=links, bundles=bundles, step=step, execution=execution)


class FindingsContextService:
    def __init__(self, repository, policy: FindingsPolicy):
        self.repository, self.policy = repository, policy

    async def attach(self, run_id: str, plan: FindingsContextPlan, *, client=None, settings=None,
                     recorder=None, concurrency: int = 1, deadline_seconds: float | None = None):
        policy = self.policy
        items = _items(plan.filing, plan.sources, plan.candidates, plan.context_lines, plan.pools,
                       plan.identity.model_identity, policy)
        if (plan.identity.policy_hash != policy.identity() or plan.identity.phase != FindingsPhase.ATTACH or
                plan.identity.question_version != policy.question_version or
                plan.identity.model_identity not in ('jev-1.13.0', 'jev-1.14.0') or
                plan.identity.concept is not None or
                len(plan.sources) > policy.max_candidate_lines or
                (bool(plan.sources) and plan.identity.canonical_source_hashes !=
                 sorted({x.source_range.source_hash for x in plan.sources})) or
                plan.identity.exact_inputs_hash != _identity_hash(items, plan.pools, plan.candidates, plan.sources,
                                                                 plan.assignments, plan.omissions) or
                plan.request_allowance > policy.max_jev_requests or
                plan.batches != pack_jev_items(items, policy.attach_budget, plan.request_allowance)):
            raise ValueError('Context plan differs from exact inputs/policy')
        self.repository.get_run(run_id)
        cached = {}
        for batch in plan.batches.batches:
            saved = self.repository.findings_checkpoint(plan.identity, batch)
            if saved:
                cached[batch.batch_id] = saved.response
        async def checkpoint(completed):
            self.repository.save_findings_checkpoint(run_id, plan.identity, completed)
        deadline = min(deadline_seconds if deadline_seconds is not None else policy.total_deadline_seconds,
                       policy.total_deadline_seconds)
        try:
            if client is None:
                if settings is None or recorder is None:
                    raise ValueError('Live context needs configured settings and recorder')
                execution = await run_live_jev_batches(plan.batches, settings, recorder,
                    deadline_seconds=deadline, checkpoint=checkpoint, cached=cached)
            else:
                execution = await execute_jev_batches(plan.batches, client, concurrency=concurrency,
                    deadline_seconds=deadline, checkpoint=checkpoint, cached=cached)
        except (JevBatchFailure, JevBatchCancelled) as error:
            result = context_result(plan, error.result, policy)
            if isinstance(error, JevBatchCancelled):
                raise FindingsContextCancelled(result) from None
            raise FindingsContextFailure(result) from None
        result = context_result(plan, execution, policy)
        self.repository.complete_findings_step(run_id, result.step, [*result.pools, *result.links, *result.bundles])
        return result
