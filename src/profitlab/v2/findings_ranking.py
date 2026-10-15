"""Prepared bundle ranking/selection; no runtime registration until T76."""
import asyncio
import hashlib
import json

from pydantic import Field

from .canonical import CanonicalDocument
from .contracts import V2Contract
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
from .findings_builders import (
    build_conversion_messages,
    build_rank_request,
    build_rank_state,
)
from .findings_contracts import (
    BundleScore,
    FindingConversionPack,
    FindingEvidenceBundle,
    FindingsFilingMetadata,
    FindingsInputIdentity,
    FindingsPhase,
    FindingsStepResult,
    JudgmentProvenance,
    Omission,
    RankedFindingBundle,
    RankState,
    RequiredConditionAnswer,
)
from .findings_lines import _input_hash
from .findings_policy import FindingsPolicy, SupportDecision, support_decision


class FindingsRankingPlan(V2Contract):
    request_allowance: int = Field(ge=0)
    filing: FindingsFilingMetadata
    bundles: list[FindingEvidenceBundle] = Field(max_length=10000)
    states: list[RankState] = Field(max_length=10000)
    identity: FindingsInputIdentity
    batches: JevBatchPlan


class FindingsRankingResult(V2Contract):
    ranks: list[RankedFindingBundle]
    conversion_packs: list[FindingConversionPack]
    step: FindingsStepResult
    execution: JevBatchExecution


class FindingsRankingFailure(Exception):
    def __init__(self, result: FindingsRankingResult):
        self.result = result
        super().__init__(result.step.reason)


class FindingsRankingCancelled(asyncio.CancelledError):
    def __init__(self, result: FindingsRankingResult):
        self.result = result
        super().__init__('Findings ranking cancelled')


def _upstream(bundle):
    return next(x.concept_score for x in bundle.source.owners
                if x.chunk.chunk_id == bundle.source.owning_chunk_id)


def build_ranking_plan(document: CanonicalDocument, filing: FindingsFilingMetadata,
                       bundles: list[FindingEvidenceBundle], *, model: str,
                       policy: FindingsPolicy, max_requests: int | None = None) -> FindingsRankingPlan:
    if model not in ('jev-1.13.0', 'jev-1.14.0'):
        raise ValueError('Ranking requires a pinned verified actual JEV model')
    if filing.filing_id != document.ref.filing_id:
        raise ValueError('Filing metadata does not belong to canonical document')
    if len(bundles) > policy.max_candidate_lines or len({x.bundle_id for x in bundles}) != len(bundles):
        raise ValueError('Ranking bundles must be unique and within candidate budget')
    ordered = sorted(bundles, key=lambda x: (x.concept.value, x.source.source_range.start_line, x.bundle_id))
    for bundle in ordered:
        # Revalidate typed inputs even if a caller used Pydantic model_copy/update.
        FindingEvidenceBundle.model_validate_json(bundle.model_dump_json())
        if (policy.source_decision(bundle.assignment.answer.noul) != SupportDecision.SUPPORTED or
                len(bundle.context_links) > policy.max_selected_context_lines_per_bundle or
                any(link.support.noul < policy.context_support_threshold or any(
                    role.decision != support_decision(role.answer.noul,
                        policy.source_uncertain_threshold, policy.context_support_threshold)
                    for role in link.roles) for link in bundle.context_links)):
            raise ValueError('Bundle support/context differs from current Findings policy')
    states = [build_rank_state(filing, b, document, policy) for b in ordered]
    items = [AtomicJevItem(item_id=b.bundle_id,
        request=build_rank_request(s, model, policy, enforce_budget=False)) for b, s in zip(ordered, states)]
    # Tie-break inputs matter even when the provider request is unchanged.
    inputs = {'requests': _input_hash(items), 'ties': [
        (b.bundle_id, b.assignment.answer.noul, _upstream(b)) for b in ordered]}
    digest = hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    cap = policy.max_jev_requests if max_requests is None else max_requests
    if not 0 <= cap <= policy.max_jev_requests:
        raise ValueError('Ranking allowance must fit Findings policy')
    identity = FindingsInputIdentity(canonical_source_hashes=[document.ref.source_hash],
        exact_inputs_hash=digest, phase=FindingsPhase.RANK, policy_hash=policy.identity(),
        question_version=policy.question_version, model_identity=model)
    return FindingsRankingPlan(request_allowance=cap, filing=filing, bundles=ordered, states=states,
        identity=identity, batches=pack_jev_items(items, policy.rank_budget, cap))


def _order(rank):
    # Confidence is retained for inspection, never used as a veto or tie-breaker.
    return (-rank.score.score, -rank.source_support, -rank.upstream_concept_score,
            rank.source_range.start_line, rank.bundle_id)


def pack_selected_bundles(filing, states, ranks, policy):
    """Greedy whole-bundle packing of the exact shared conversion message envelope.

    T75 must additionally enforce its actual model/tool/output-schema envelope;
    this bound covers all system/user messages including source/context metadata.
    Never strip context, split a bundle or silently downgrade to the source alone.
    """
    from .findings_contracts import ConversionState

    by_id = {s.bundle.bundle_id: s.bundle for s in states}
    selected = []
    packs = []
    omissions = []
    counts = {}
    text_count = 0
    for rank in sorted((x for x in ranks if x.eligibility == 'eligible'),
                       key=lambda x: (x.concept.value, *_order(x))):
        if (counts.get(rank.concept, 0) >= policy.max_bundles_per_concept or
                len(selected) >= policy.max_selected_bundles):
            continue
        bundle = by_id[rank.bundle_id]
        size = len(bundle.source.exact_text) + sum(len(x.exact_text) for x in bundle.context)
        reason = None
        if text_count + size > policy.max_selected_text_characters:
            reason = 'selected_text_limit'
        else:
            def messages(inputs):
                state = ConversionState(filing=filing, selected_bundles=inputs)
                return state, build_conversion_messages(state, policy)
            try:
                single_state, single_messages = messages([bundle])
            except ValueError:
                reason = 'whole_bundle_conversion_size_limit'
            if reason is None:
                # Keep source order within a bundle; pack order follows deterministic ranking.
                if packs:
                    try:
                        state, request = messages([*packs[-1].state.selected_bundles, bundle])
                    except ValueError:
                        state = None
                else:
                    state = None
                if state is not None:
                    packs[-1] = FindingConversionPack(pack_id=packs[-1].pack_id, state=state, messages=request)
                elif len(packs) < policy.max_conversion_requests:
                    packs.append(FindingConversionPack(pack_id=f'conversion-{len(packs)+1}',
                        state=single_state, messages=single_messages))
                else:
                    reason = 'conversion_request_count_limit'
        if reason:
            omissions.append(Omission(item_id=rank.bundle_id, reason=reason, coverage_cut=True,
                kind='count_limit' if reason == 'conversion_request_count_limit' else 'size_limit'))
            continue
        selected.append(rank.bundle_id)
        counts[rank.concept] = counts.get(rank.concept, 0) + 1
        text_count += size
    return selected, packs, omissions


def ranking_result(plan: FindingsRankingPlan, execution: JevBatchExecution,
                   policy: FindingsPolicy) -> FindingsRankingResult:
    """Inspector and persistence consume exactly the dispatched answers and policy."""
    if plan.identity.policy_hash != policy.identity():
        raise ValueError('Ranking policy differs from plan')
    answered = {}
    for completed in execution.completed:
        for wire_id, (bundle_id, original_id) in completed.batch.routes.items():
            provenance = JudgmentProvenance(model=completed.response.model,
                call_id=completed.batch.batch_id, question_id=wire_id,
                question_version=policy.question_version, policy_hash=policy.identity(),
                request_hash=hashlib.sha256(serialized(completed.batch.request).encode()).hexdigest(),
                cached=completed.cached)
            answered.setdefault(bundle_id, {})[original_id] = (completed.response.answers[wire_id], provenance)
    ranks = []
    for bundle in plan.bundles:
        values = answered.get(bundle.bundle_id)
        if not values:
            continue
        score, provenance = values['bundle_score']
        conditions = [RequiredConditionAnswer(condition=c, answer=values[c.value][0],
            decision=policy.required_decision(values[c.value][0].noul), provenance=values[c.value][1])
            for c in policy.required_conditions(bundle.concept)]
        decisions = {x.decision for x in conditions}
        eligibility = ('ineligible' if SupportDecision.REJECTED in decisions else
                       'uncertain' if SupportDecision.UNCERTAIN in decisions else 'eligible')
        reason = '; '.join(f'{x.condition.value}={x.decision.value} ({x.answer.noul:g})' for x in conditions)
        ranks.append(RankedFindingBundle(bundle_id=bundle.bundle_id, concept=bundle.concept,
            score=BundleScore(score=score.score, probabilities=score.probabilities,
                confidence=score.confidence, rubric_version=policy.rubric_version, provenance=provenance),
            required_conditions=conditions, eligibility=eligibility,
            decision={'eligible':'losing', 'uncertain':'uncertain', 'ineligible':'rejected'}[eligibility],
            source_support=bundle.assignment.answer.noul, upstream_concept_score=_upstream(bundle),
            source_range=bundle.source.source_range, reason=reason))
    for concept in {r.concept for r in ranks}:
        for index, rank in enumerate(sorted((r for r in ranks if r.concept == concept and
                                            r.eligibility == 'eligible'), key=_order), 1):
            rank_index = ranks.index(rank)
            ranks[rank_index] = rank.model_copy(update={'rank_within_concept':index})
    successful = execution.status in ('completed', 'partial')
    # Incomplete ranking is inspectable/checkpointed, never a conversion-ready subset.
    selected, packs, packing_omissions = pack_selected_bundles(plan.filing, plan.states, ranks, policy) if successful else ([], [], [])
    omitted = {x.item_id: x.reason for x in packing_omissions}
    final = []
    for rank in ranks:
        decision, reason = rank.decision, rank.reason
        if rank.bundle_id in selected:
            decision, reason = 'selected', reason + '; selected by Score/support/upstream/source order'
        elif rank.bundle_id in omitted:
            decision, reason = 'omitted', reason + '; ' + omitted[rank.bundle_id]
        elif rank.eligibility == 'eligible':
            reason += '; per-concept/global rank selection limit' if successful else '; ranking incomplete; conversion withheld'
        final.append(rank.model_copy(update={'decision':decision, 'reason':reason}))
    omissions = [Omission(item_id=x.item_id, reason=x.reason, coverage_cut=True,
        kind='size_limit' if x.reason == 'atomic_request_limit' else 'count_limit')
        for x in execution.omissions] + packing_omissions
    status = 'partial' if successful and omissions else execution.status
    step = FindingsStepResult(phase=FindingsPhase.RANK, status=status,
        availability='final' if successful else 'checkpointed' if ranks else 'unavailable',
        input_hash=plan.identity.exact_inputs_hash, policy_hash=policy.identity(), accounting=execution.accounting,
        output_ids=[x.bundle_id for x in final], omissions=omissions,
        reason=execution.error or 'Score ranks eligible bundles only; count selection is intentional; size/packing cuts are explicit')
    return FindingsRankingResult(ranks=final, conversion_packs=packs, step=step, execution=execution)


class FindingsRankingService:
    def __init__(self, repository, policy: FindingsPolicy):
        self.repository, self.policy = repository, policy

    async def rank(self, run_id: str, plan: FindingsRankingPlan, document: CanonicalDocument, *,
                   client=None, settings=None, recorder=None, concurrency: int = 1,
                   deadline_seconds: float | None = None) -> FindingsRankingResult:
        expected = build_ranking_plan(document, plan.filing, plan.bundles,
            model=plan.identity.model_identity, policy=self.policy, max_requests=plan.request_allowance)
        if expected != plan:
            raise ValueError('Ranking plan differs from exact canonical inputs/policy')
        self.repository.get_run(run_id)
        cached = {}
        for batch in plan.batches.batches:
            saved = self.repository.findings_checkpoint(plan.identity, batch)
            if saved:
                cached[batch.batch_id] = saved.response
        async def checkpoint(completed):
            self.repository.save_findings_checkpoint(run_id, plan.identity, completed)
        deadline = min(deadline_seconds if deadline_seconds is not None else
                       self.policy.total_deadline_seconds, self.policy.total_deadline_seconds)
        try:
            if client is None:
                if settings is None or recorder is None:
                    raise ValueError('Live ranking needs configured settings and recorder')
                execution = await run_live_jev_batches(plan.batches, settings, recorder,
                    deadline_seconds=deadline, checkpoint=checkpoint, cached=cached)
            else:
                execution = await execute_jev_batches(plan.batches, client, concurrency=concurrency,
                    deadline_seconds=deadline, checkpoint=checkpoint, cached=cached)
        except (JevBatchFailure, JevBatchCancelled) as error:
            result = ranking_result(plan, error.result, self.policy)
            if isinstance(error, JevBatchCancelled):
                raise FindingsRankingCancelled(result) from None
            raise FindingsRankingFailure(result) from None
        result = ranking_result(plan, execution, self.policy)
        self.repository.complete_findings_step(run_id, result.step, [*result.ranks, *result.conversion_packs])
        return result
