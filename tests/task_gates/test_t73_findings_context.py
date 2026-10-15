"""Saved AZZ canonical coverage plus controlled context judgments, never paid calls."""
import asyncio
import copy
import gzip
import json

import pytest
from test_t71_findings_candidates import BASE, create_repo, saved_inputs
from test_t72_findings_lines import ControlledClient, inputs

from profitlab.v2.contracts import OutlineSection
from profitlab.v2.finding_concepts import FindingConcept
from profitlab.v2.findings_builders import build_bundle_input
from profitlab.v2.findings_candidates import enumerate_candidates
from profitlab.v2.findings_context import (
    FindingsContextCancelled,
    FindingsContextFailure,
    FindingsContextPlan,
    FindingsContextService,
    build_context_plan,
)
from profitlab.v2.findings_contracts import (
    ConceptLineAssignment,
    ContextRole,
    ContextState,
    FindingContextLink,
    FindingContextPool,
    FindingEvidenceBundle,
    FindingsPhase,
    JudgmentProvenance,
)
from profitlab.v2.findings_policy import FindingsPolicy, JevPhaseBudget
from profitlab.v2.storage import V2Repository


def prepared(policy=None, *, source_numbers=(289, 291), model='jev-1.13.0'):
    policy = policy or FindingsPolicy()
    document, filing, lines = inputs(policy)
    _, chunks, scores = saved_inputs()
    record = json.loads(gzip.decompress((BASE/'t69/v2-6eca22455a84.json.gz').read_bytes()))
    sections = [OutlineSection.model_validate_json(x['payload']) for x in record['outline_sections']]
    concepts = enumerate_candidates(document, chunks, scores, relevance_threshold=.2, policy=policy).concepts
    lines = [x for x in lines if x.source_range.start_line in source_numbers and
             x.concept == FindingConcept.DILUTED_EPS]
    assignments = [ConceptLineAssignment(candidate_id=x.candidate_id, concept=x.concept,
        source_range=x.source_range, answer={'type':'noul', 'noul':.9}, decision='supported',
        reason='Controlled support for context invariants', provenance=JudgmentProvenance(
            model=model, call_id='controlled', question_id='source_support',
            question_version=policy.question_version, policy_hash=policy.identity(), request_hash='0'*64))
        for x in lines]
    args = [document, filing, concepts, lines, assignments, chunks, scores, sections]
    return args, build_context_plan(*args, model=model, policy=policy)


@pytest.mark.asyncio
async def test_saved_coverage_shared_context_exact_questions_storage_and_resume(tmp_path):
    policy = FindingsPolicy()
    args, plan = prepared(policy)
    assert plan.sources and plan.candidates
    assert FindingsContextPlan.model_validate_json(plan.model_dump_json()) == plan
    assert plan == build_context_plan(*args, model='jev-1.13.0', policy=policy)
    doc = args[0]
    for batch in plan.batches.batches:
        for state in batch.request.state['items'].values():
            parsed = ContextState.model_validate(state)
            assert doc.slice(parsed.context.source_range) == parsed.context.exact_text
            assert not {'outline', 'owners', 'chunks', 'numeric_spans'} & state.keys()
        assert len(batch.request.questions) % 5 == 0
        for q in batch.request.questions.values():
            assert 'source.exact_text' in q.instructions['question']
    repo = create_repo(tmp_path)
    result = await FindingsContextService(repo, policy).attach('test', plan, client=ControlledClient())
    assert len(result.bundles) == len(plan.sources)
    assert repo.findings_artifacts('test', FindingContextPool) == result.pools
    assert repo.findings_artifacts('test', FindingContextLink) == result.links
    assert repo.findings_artifacts('test', FindingEvidenceBundle) == result.bundles
    for bundle in result.bundles:
        request = build_bundle_input(bundle, doc)
        assert [x.source_range.start_line for x in request.context] == sorted(
            x.context_range.start_line for x in bundle.context_links)
        assert not bundle.unresolved_roles
    # Same canonical context can belong independently to more than one bundle.
    ranges = [{x.context_range.start_line for x in b.context_links} for b in result.bundles]
    assert set.intersection(*ranges)
    client = ControlledClient(fail_at=1)
    resumed = await FindingsContextService(V2Repository(tmp_path), policy).attach('test', plan, client=client)
    assert client.calls == 0 and resumed.step.accounting.dispatched == 0
    assert resumed.step.accounting.cached == len(plan.batches.batches)
    assert resumed.step.accounting.usage is None
    assert all(x.provenance.cached for x in resumed.links)


@pytest.mark.asyncio
async def test_distant_structural_following_and_absent_roles(tmp_path):
    policy = FindingsPolicy(local_context_lines_each_direction=1)
    args, _ = prepared(policy, source_numbers=(289,))
    doc = args[0].model_copy(deep=True)
    source = args[3][0]
    # Controlled visible canonical labels exercise enumeration, not model accuracy.
    pool_chunk = next(x.chunk for x in args[2][1].chunks if x.chunk.chunk_id == source.owning_chunk_id)
    start = pool_chunk.core_range.start_line
    labels = {start: ('heading', 'AZZ Inc. consolidated shareholder results'),
              start+1: ('caption', 'In millions except per share amounts'),
              start+2: ('table_row', 'Years ended February 28 | 2026 | 2025 | 2024')}
    for n, (kind, text) in labels.items():
        if n != source.source_range.start_line:
            doc.lines[n-1] = doc.lines[n-1].model_copy(update={'element_type':kind, 'text':text})
    args[0] = doc
    plan = build_context_plan(*args, model='jev-1.13.0', policy=policy)
    numbers = {x.context_range.start_line for x in plan.candidates}
    assert set(labels) <= numbers
    assert source.source_range.start_line+1 in numbers
    assert all(x.section_id == source.section_id for x in plan.candidates)
    class Roles(ControlledClient):
        async def evaluate(self, request):
            response = await super().evaluate(request)
            for q, question in request.questions.items():
                if 'qualification' in question.instructions['question'].lower():
                    response.answers[q] = response.answers[q].model_copy(update={'noul':.1})
            return response
    result = await FindingsContextService(create_repo(tmp_path), policy).attach('test', plan, client=Roles())
    assert result.bundles[0].unresolved_roles == [ContextRole.QUALIFICATION]
    assert result.pools[0].limitation.startswith('Only retained canonical')
    assert 'external captions are unavailable' in result.pools[0].limitation
    # No raw HTML or external caption is imported to fill an absent canonical role.
    assert not any('invented external caption' in x.exact_text for x in plan.context_lines.values())


@pytest.mark.asyncio
async def test_candidates_selection_question_and_size_caps_are_explicit(tmp_path):
    policy = FindingsPolicy(max_context_candidates_per_bundle=4,
        reserved_structural_context_candidates=2, max_selected_context_lines_per_bundle=1,
        attach_budget=JevPhaseBudget(questions=5), max_jev_requests=2)
    _, plan = prepared(policy, source_numbers=(289,))
    assert len(plan.candidates) == 4 and len(plan.batches.batches) == 2
    assert plan.batches.omissions
    result = await FindingsContextService(create_repo(tmp_path), policy).attach('test', plan, client=ControlledClient())
    assert result.step.status == 'partial'
    assert len(result.bundles[0].context_links) == 1
    assert any(x.decision == 'omitted' for x in result.links)
    assert any(x.coverage_cut for x in result.step.omissions)
    tiny = FindingsPolicy(attach_budget=JevPhaseBudget(questions=4))
    _, plan = prepared(tiny, source_numbers=(289,))
    client = ControlledClient(fail_at=1)
    result = await FindingsContextService(V2Repository(tmp_path), tiny).attach('test', plan, client=client)
    assert client.calls == 0 and result.step.status == 'partial'
    assert set(result.bundles[0].unresolved_roles) == set(ContextRole)
    assert all(x.kind == 'size_limit' for x in result.step.omissions if x.coverage_cut)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_failure_checkpoint_resume_and_no_success_subset(tmp_path, cancel):
    policy = FindingsPolicy(attach_budget=JevPhaseBudget(questions=5), max_jev_requests=3)
    _, plan = prepared(policy, source_numbers=(289,))
    repo = create_repo(tmp_path)
    with pytest.raises(FindingsContextCancelled if cancel else FindingsContextFailure) as error:
        await FindingsContextService(repo, policy).attach('test', plan,
            client=ControlledClient(fail_at=2, cancel=cancel))
    assert error.value.result.step.availability == 'checkpointed'
    assert repo.findings_step('test', FindingsPhase.ATTACH) is None
    assert not repo.findings_artifacts('test', FindingEvidenceBundle)
    assert len(repo.findings_checkpoints('test', plan.identity)) == 1
    client = ControlledClient()
    result = await FindingsContextService(V2Repository(tmp_path), policy).attach('test', plan, client=client)
    assert client.calls == 2 and result.step.accounting.cached == 1


@pytest.mark.asyncio
async def test_empty_rejected_source_and_plan_isolation(tmp_path):
    policy = FindingsPolicy()
    args, plan = prepared(policy)
    repo = create_repo(tmp_path)
    modified = copy.deepcopy(plan)
    modified.batches.batches[0].request.state['extra'] = 'tampered'
    with pytest.raises(ValueError, match='exact inputs'):
        await FindingsContextService(repo, policy).attach('test', modified, client=ControlledClient())
    invalid = list(args)
    invalid[4] = [x.model_copy(update={'answer':x.answer.model_copy(update={'noul':.1})}) for x in args[4]]
    with pytest.raises(ValueError, match='Assignment/source/policy'):
        build_context_plan(*invalid, model='jev-1.13.0', policy=policy)
    invalid = list(args)
    invalid[5] = [x.model_copy(update={'context_ranges':[x.core_range]}) for x in args[5]]
    with pytest.raises(ValueError):
        build_context_plan(*invalid, model='jev-1.13.0', policy=policy)
    args[3], args[4] = [], []
    empty = build_context_plan(*args, model='jev-1.13.0', policy=policy)
    client = ControlledClient(fail_at=1)
    result = await FindingsContextService(repo, policy).attach('test', empty, client=client)
    assert result.step.status == 'completed' and not result.bundles and client.calls == 0
    class Slow:
        async def evaluate(self, _):
            await asyncio.Event().wait()
    with pytest.raises(FindingsContextFailure) as error:
        await FindingsContextService(repo, policy).attach('test', plan, client=Slow(), deadline_seconds=.01)
    assert error.value.result.step.status == 'interrupted'


@pytest.mark.asyncio
async def test_nonsupported_assignments_and_context_answers_preserve_uncertainty(tmp_path):
    policy = FindingsPolicy()
    args, _ = prepared(policy, source_numbers=(289,))
    repo = create_repo(tmp_path)
    for probability in (.1, .3):
        args[4] = [args[4][0].model_copy(update={
            'answer':args[4][0].answer.model_copy(update={'noul':probability}),
            'decision':policy.source_decision(probability)})]
        plan = build_context_plan(*args, model='jev-1.13.0', policy=policy)
        client = ControlledClient(fail_at=1)
        result = await FindingsContextService(repo, policy).attach('test', plan, client=client)
        assert not result.bundles and not result.links and client.calls == 0
    args, plan = prepared(policy, source_numbers=(289,))
    for probability, decision in ((.1, 'rejected'), (.3, 'uncertain'), (.65, 'selected')):
        result = await FindingsContextService(repo, policy).attach('test', plan,
            client=ControlledClient(probability))
        # Isolate the next controlled judgment from successful-batch reuse.
        if probability != .65:
            assert all(x.decision == decision for x in result.links)
            assert set(result.bundles[0].unresolved_roles) == set(ContextRole)
        policy = policy.model_copy(update={'version':f'controlled-{probability}'})
        args, plan = prepared(policy, source_numbers=(289,))


@pytest.mark.asyncio
async def test_overlap_dedup_cross_section_guard_and_local_id_remapping(tmp_path):
    policy = FindingsPolicy()
    args, original = prepared(policy, source_numbers=(289,))
    source = args[3][0]
    owner = source.owners[0]
    duplicate = owner.chunk.model_copy(update={'chunk_id':'duplicate-owner'})
    args[5] = [*args[5], duplicate]
    args[2] = [x.model_copy(update={'chunks':[*x.chunks, owner.model_copy(update={'chunk':duplicate})]})
               if x.concept == source.concept else x for x in args[2]]
    plan = build_context_plan(*args, model='jev-1.13.0', policy=policy)
    assert len({x.link_id for x in plan.candidates}) == len(plan.candidates)
    assert len(plan.candidates) == len(original.candidates)
    assert any('duplicate-owner' in x.owning_chunk_ids for x in plan.candidates)
    invalid = copy.deepcopy(args)
    wrong = invalid[7][0].section_id
    invalid[5] = [x.model_copy(update={'section_id':wrong}) if x.chunk_id == source.owning_chunk_id else x
                  for x in invalid[5]]
    with pytest.raises(ValueError):
        build_context_plan(*invalid, model='jev-1.13.0', policy=policy)
    repo = create_repo(tmp_path)
    await FindingsContextService(repo, policy).attach('test', plan, client=ControlledClient())
    def remap(value):
        if isinstance(value, dict):
            return {k: ('fresh-'+v if k in ('document_id', 'filing_id', 'section_id', 'chunk_id', 'owning_chunk_id') or k == 'item_id' and v.startswith('chunk-')
                        else ['fresh-'+x for x in v] if k == 'owning_chunk_ids' else remap(v))
                    for k, v in value.items()}
        if isinstance(value, list):
            return [remap(x) for x in value]
        return value
    remapped = []
    for value in args:
        if isinstance(value, list):
            remapped.append([type(x).model_validate(remap(x.model_dump(mode='json'))) for x in value])
        else:
            remapped.append(type(value).model_validate(remap(value.model_dump(mode='json'))))
    new = build_context_plan(*remapped, model='jev-1.13.0', policy=policy)
    assert new.identity == plan.identity
    client = ControlledClient(fail_at=1)
    result = await FindingsContextService(repo, policy).attach('test', new, client=client)
    assert client.calls == 0 and all(x.provenance.cached for x in result.links)
    assert all(x.context_range.document_id.startswith('fresh-') for x in result.links)


def test_real_apple_external_caption_is_unavailable_to_context_pool():
    from datetime import date

    from lxml import html

    from profitlab.v2.canonical import canonicalize_html
    from profitlab.v2.contracts import ScoredItem, SourceRange, TextChunk
    from profitlab.v2.findings_contracts import FindingsFilingMetadata

    raw = gzip.decompress((BASE.parent/'t64/aapl-20240928.htm.gz').read_bytes())
    document, visible = canonicalize_html(raw, document_id='aapl', filing_id='aapl-filing')
    captions = [x for x in html.fromstring(visible).xpath('//div|//span')
                if 'In millions, except number of shares' in x.text_content() and len(x.text_content()) < 200]
    exact_caption = ' '.join(captions[0].text_content().split())
    assert all(exact_caption not in x.text for x in document.lines)
    r = SourceRange(document_id='aapl', source_hash=document.ref.source_hash, start_line=120, end_line=130)
    chunk = TextChunk(chunk_id='apple-statement', section_id='apple-section', core_range=r, request_size_estimate=1000)
    score = ScoredItem(item_id=chunk.chunk_id, target_scores={'diluted_eps':.9}, model='controlled',
                       call_id='controlled', policy_decision='selected', policy_reason='Context isolation')
    policy = FindingsPolicy()
    candidates = enumerate_candidates(document, [chunk], [score], relevance_threshold=.2, policy=policy)
    source = next(x for x in candidates.lines if x.source_range.start_line == 126)
    _, template = prepared(policy, source_numbers=(289,))
    assignment = template.assignments[0].model_copy(update={
        'candidate_id':source.candidate_id, 'source_range':source.source_range, 'concept':source.concept})
    plan = build_context_plan(document, FindingsFilingMetadata(ticker='AAPL', filing_id='aapl-filing',
        report_date=date(2024,9,28)), candidates.concepts, [source], [assignment], [chunk], [score],
        [OutlineSection(section_id=chunk.section_id, primary_range=r, generated_topic='Statement')],
        model='jev-1.13.0', policy=policy)
    assert plan.candidates
    assert all(document.slice(x.source_range) == x.exact_text for x in plan.context_lines.values())
    assert exact_caption not in json.dumps([x.request.state for x in plan.batches.batches])
    assert all('external captions are unavailable' in x.limitation for x in plan.pools)


def test_retained_context_target_threshold_and_candidate_core_ownership():
    policy = FindingsPolicy()
    args, _ = prepared(policy, source_numbers=(289,))
    source = args[3][0]
    context_only = source.owners[0].chunk.model_copy(update={'chunk_id':'context-only'})
    args[5] = [*args[5], context_only]
    score = args[6][0].model_copy(update={'item_id':context_only.chunk_id,
        'target_scores':{'earnings_change':.2}, 'policy_decision':'selected'})
    args[6] = [*args[6], score]
    plan = build_context_plan(*args, model='jev-1.13.0', policy=policy)
    assert all(any(r.chunk_id == 'context-only' for r in pool.ranges) for pool in plan.pools)
    args[6][-1] = score.model_copy(update={'target_scores':{'earnings_change':.199}})
    plan = build_context_plan(*args, model='jev-1.13.0', policy=policy)
    assert all(not any(r.chunk_id == 'context-only' for r in pool.ranges) for pool in plan.pools)
    args[6][-1] = score
    wrong_owner = source.owners[0].model_copy(update={'chunk':context_only})
    args[3] = [source.model_copy(update={'owners':[wrong_owner], 'owning_chunk_id':'context-only'})]
    with pytest.raises(ValueError, match='concept-candidate cores'):
        build_context_plan(*args, model='jev-1.13.0', policy=policy)
