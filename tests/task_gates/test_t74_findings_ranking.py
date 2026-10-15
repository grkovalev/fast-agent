"""T74 contracts on genuine saved SEC rows; judgments below are controlled, not live."""
import asyncio
import json

import pytest
from test_t71_findings_candidates import create_repo
from test_t72_findings_lines import ControlledClient, inputs
from test_t73_findings_context import prepared

from profitlab.providers.jev import JevResponse, NoulAnswer, ScoreAnswer, TokenUsage
from profitlab.v2.findings_builders import RANK_RUBRIC, build_conversion_messages
from profitlab.v2.findings_context import FindingsContextService
from profitlab.v2.findings_contracts import (
    ConceptLineAssignment,
    ContextRole,
    FindingConversionPack,
    FindingEvidenceBundle,
    FindingsPhase,
    JudgmentProvenance,
    RankedFindingBundle,
    RankState,
)
from profitlab.v2.findings_policy import FindingsPolicy, JevPhaseBudget
from profitlab.v2.findings_ranking import (
    FindingsRankingCancelled,
    FindingsRankingFailure,
    FindingsRankingPlan,
    FindingsRankingResult,
    FindingsRankingService,
    build_ranking_plan,
)
from profitlab.v2.storage import V2Repository


def bundles(policy=None, count=12):
    policy = policy or FindingsPolicy()
    document, filing, lines = inputs(policy)
    result = []
    # Interleave concepts so small controlled sets retain all lanes.
    lines = sorted(lines, key=lambda x:(x.source_range.start_line, x.concept.value))
    for candidate in lines[:count]:
        assignment = ConceptLineAssignment(candidate_id=candidate.candidate_id, concept=candidate.concept,
            source_range=candidate.source_range, answer=NoulAnswer(type='noul', noul=.9),
            decision='supported', reason='Controlled membership; not quality evidence',
            provenance=JudgmentProvenance(model='jev-1.13.0', call_id='controlled',
                question_id='source_support', question_version=policy.question_version,
                policy_hash=policy.identity(), request_hash='0'*64))
        result.append(FindingEvidenceBundle(bundle_id='bundle-'+candidate.candidate_id.removeprefix('line-'),
            concept=candidate.concept, source=candidate, assignment=assignment,
            unresolved_roles=list(ContextRole)))
    return document, filing, result


class RankClient:
    def __init__(self, *, conditions=None, scores=None, confidence=1, fail_at=None, cancel=False):
        self.conditions, self.scores = conditions or {}, scores or {}
        self.calls = 0
        self.confidence, self.fail_at, self.cancel = confidence, fail_at, cancel

    async def evaluate(self, request):
        self.calls += 1
        if self.calls == self.fail_at:
            if self.cancel:
                raise asyncio.CancelledError()
            raise RuntimeError('controlled ranking failure')
        answers = {}
        for wire, question in request.questions.items():
            slot, qindex = wire.split('_q')
            state = RankState.model_validate(request.state['items'][slot])
            key = state.bundle.bundle_id
            if question.type == 'score':
                score = self.scores.get(key, 3)
                probabilities = {str(i): float(i == score) for i in range(4)}
                answers[wire] = ScoreAnswer(type='score', score=score,
                    legend={str(i): value for i, value in enumerate(RANK_RUBRIC)},
                    probabilities=probabilities, confidence=self.confidence)
            else:
                condition = list(state.required_conditions)[int(qindex)-1]
                answers[wire] = NoulAnswer(type='noul',
                    noul=self.conditions.get((key, condition.value), .9))
        return JevResponse(model=request.model, answers=answers,
                           usage=TokenUsage(input_tokens=120, output_tokens=30))


async def rank(tmp_path, document, filing, values, policy=None, **client_kwargs):
    policy = policy or FindingsPolicy()
    plan = build_ranking_plan(document, filing, values, model='jev-1.13.0', policy=policy)
    repo = V2Repository(tmp_path)
    try:
        repo.get_run('test')
    except FileNotFoundError:
        repo = create_repo(tmp_path)
    result = await FindingsRankingService(repo, policy).rank('test', plan, document,
                                                          client=RankClient(**client_kwargs))
    return repo, plan, result


@pytest.mark.asyncio
async def test_assembled_context_exact_requests_results_storage_restart_and_rounding(tmp_path):
    policy = FindingsPolicy()
    args, context_plan = prepared(policy)
    repo = create_repo(tmp_path)
    context = await FindingsContextService(repo, policy).attach('test', context_plan, client=ControlledClient())
    document, filing = args[:2]
    plan = build_ranking_plan(document, filing, context.bundles, model='jev-1.13.0', policy=policy)
    assert FindingsRankingPlan.model_validate_json(plan.model_dump_json()) == plan
    assert plan == build_ranking_plan(document, filing, context.bundles[::-1], model='jev-1.13.0', policy=policy)
    for batch in plan.batches.batches:
        assert len(batch.request.questions) % 5 == 0
        for state in batch.request.state['items'].values():
            parsed = RankState.model_validate(state)
            assert parsed.bundle.context
            assert parsed.bundle.source.exact_text == document.slice(parsed.bundle.source.source_range)
        for q in batch.request.questions.values():
            assert 'assembled `bundle`' in q.instructions['question']
            if q.type == 'score':
                assert q.criteria == list(RANK_RUBRIC)
    class Rounded(RankClient):
        async def evaluate(self, request):
            response = await super().evaluate(request)
            for key, answer in list(response.answers.items()):
                if answer.type == 'score':
                    # Same independent rounding behavior observed by T70 real probe.
                    response.answers[key] = ScoreAnswer(type='score', score=2.12,
                        probabilities={'0':.07,'1':.14,'2':.38,'3':.41},
                        legend=answer.legend, confidence=.42)
            return response
    service = FindingsRankingService(repo, policy)
    result = await service.rank('test', plan, document, client=Rounded())
    assert all(x.score.score == 2.12 and x.score.probabilities['3'] == .41 for x in result.ranks)
    assert repo.findings_artifacts('test', RankedFindingBundle) == result.ranks
    assert repo.findings_artifacts('test', FindingConversionPack) == result.conversion_packs
    assert repo.findings_step('test', FindingsPhase.RANK) == result.step
    assert FindingsRankingResult.model_validate_json(result.model_dump_json()) == result
    client = RankClient(fail_at=1)
    restarted = await FindingsRankingService(V2Repository(tmp_path), policy).rank('test', plan, document, client=client)
    assert client.calls == 0 and restarted.step.accounting.cached == len(plan.batches.batches)
    assert all(x.score.provenance.cached for x in restarted.ranks)
    assert result.conversion_packs[0].messages == build_conversion_messages(result.conversion_packs[0].state, policy)
    assert result.conversion_packs[0].state.selected_bundles[0].context


@pytest.mark.asyncio
async def test_independent_required_conditions_boundaries_and_high_score_veto(tmp_path):
    document, filing, values = bundles(count=7)
    conditions = {}
    for bundle, condition in zip(values[:4], ('requested_year','annual_duration','reported_basis','concept_scope')):
        conditions[bundle.bundle_id, condition] = .199999
    conditions[values[4].bundle_id, 'requested_year'] = .2
    conditions[values[5].bundle_id, 'requested_year'] = .649999
    conditions[values[6].bundle_id, 'requested_year'] = .65
    _, _, result = await rank(tmp_path, document, filing, values, conditions=conditions,
                              scores={values[6].bundle_id:1}, confidence=0)
    assert [x.eligibility for x in result.ranks].count('ineligible') == 4
    assert [x.eligibility for x in result.ranks].count('uncertain') == 2
    winner = next(x for x in result.ranks if x.bundle_id == values[6].bundle_id)
    assert winner.decision == 'selected' and winner.score.score == 1
    # Missing optional unit/scale context and low confidence are no selection veto.
    assert result.conversion_packs and result.step.status == 'completed'
    assert len(result.conversion_packs[0].state.selected_bundles) == 1
    assert all(x.decision != 'selected' for x in result.ranks if x.score.score == 3)


@pytest.mark.asyncio
async def test_deterministic_ties_count_selection_and_batch_order_independence(tmp_path):
    policy = FindingsPolicy(max_bundles_per_concept=2, max_selected_bundles=3,
                            rank_budget=JevPhaseBudget(questions=5))
    document, filing, values = bundles(policy)
    _, plan, result = await rank(tmp_path, document, filing, values, policy)
    assert result.step.status == 'completed' and not result.step.omissions
    selected = [r for r in result.ranks if r.decision == 'selected']
    assert len(selected) == 3
    for concept in {r.concept for r in result.ranks}:
        lane = sorted([r for r in result.ranks if r.concept == concept], key=lambda r:r.rank_within_concept)
        assert [r.source_range.start_line for r in lane] == sorted(r.source_range.start_line for r in lane)
        assert sum(r.decision == 'selected' for r in lane) <= 2
    from profitlab.v2.findings_ranking import ranking_result
    reversed_execution = result.execution.model_copy(update={'completed':result.execution.completed[::-1]})
    reordered = ranking_result(plan, reversed_execution, policy)
    assert reordered.ranks == result.ranks and reordered.conversion_packs == result.conversion_packs
    assert any(r.decision == 'losing' for r in result.ranks)


@pytest.mark.asyncio
async def test_empty_no_eligible_and_request_budget_omissions(tmp_path):
    document, filing, values = bundles(count=3)
    policy = FindingsPolicy(rank_budget=JevPhaseBudget(questions=5), max_jev_requests=1)
    _, _, result = await rank(tmp_path, document, filing, values, policy)
    assert result.step.status == 'partial' and len(result.ranks) == 1 and len(result.step.omissions) == 2
    policy = FindingsPolicy(rank_budget=JevPhaseBudget(serialized_characters=1000))
    _, _, result = await rank(tmp_path, document, filing, values, policy)
    assert result.step.status == 'partial' and not result.ranks and not result.conversion_packs
    assert result.step.accounting.dispatched == 0
    _, _, empty = await rank(tmp_path, document, filing, [])
    assert empty.step.status == 'completed' and not empty.conversion_packs and empty.step.accounting.dispatched == 0
    conditions = {(b.bundle_id,'annual_duration'):.1 for b in values}
    _, _, rejected = await rank(tmp_path, document, filing, values, conditions=conditions)
    assert rejected.step.status == 'completed' and not rejected.conversion_packs
    assert all(r.decision == 'rejected' for r in rejected.ranks)


@pytest.mark.asyncio
async def test_whole_bundle_packing_limits_retain_context_and_record_cuts(tmp_path):
    args, context_plan = prepared()
    repo = create_repo(tmp_path)
    context = await FindingsContextService(repo, FindingsPolicy()).attach('test', context_plan, client=ControlledClient())
    document, filing = args[:2]
    # Exact envelope is measured with the shared builder, including context/roles/spans.
    policy = FindingsPolicy(conversion_request_characters=1000)
    _, _, result = await rank(tmp_path, document, filing, context.bundles, policy)
    assert result.step.status == 'partial' and not result.conversion_packs
    assert all(r.decision == 'omitted' for r in result.ranks)
    assert all('whole_bundle_conversion_size_limit' in x.reason for x in result.step.omissions)
    policy = FindingsPolicy(max_selected_text_characters=1000)
    # Keep genuine full selected context; ensure enough competing real rows to exceed text cap.
    document, filing, values = bundles(policy, count=30)
    policy = policy.model_copy(update={'max_bundles_per_concept':100, 'max_selected_bundles':100})
    _, _, result = await rank(tmp_path, document, filing, values, policy)
    assert result.step.status == 'partial' and any(x.reason == 'selected_text_limit' for x in result.step.omissions)
    # Force one bundle per request, then exhaust the initial conversion request allowance.
    default = FindingsPolicy()
    _, _, unlimited = await rank(tmp_path, document, filing, values[:3], default)
    pack = unlimited.conversion_packs[0]
    from profitlab.v2.findings_contracts import ConversionState
    sizes = [len(json.dumps(build_conversion_messages(ConversionState(filing=filing,
        selected_bundles=[b]), default), ensure_ascii=False)) for b in pack.state.selected_bundles]
    policy = FindingsPolicy(conversion_request_characters=max(sizes), max_conversion_requests=1)
    _, _, result = await rank(tmp_path, document, filing, values[:3], policy)
    assert len(result.conversion_packs) == 1 and len(result.conversion_packs[0].state.selected_bundles) == 1
    assert result.step.status == 'partial'
    assert any(x.reason == 'conversion_request_count_limit' for x in result.step.omissions)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_failure_resume_and_no_conversion_of_partial_provider_result(tmp_path, cancel):
    policy = FindingsPolicy(rank_budget=JevPhaseBudget(questions=5))
    document, filing, values = bundles(policy, count=3)
    plan = build_ranking_plan(document, filing, values, model='jev-1.13.0', policy=policy)
    repo = create_repo(tmp_path)
    with pytest.raises(FindingsRankingCancelled if cancel else FindingsRankingFailure) as error:
        await FindingsRankingService(repo, policy).rank('test', plan, document,
                                                      client=RankClient(fail_at=2, cancel=cancel))
    result = error.value.result
    assert len(result.ranks) == 1 and not result.conversion_packs
    assert result.step.availability == 'checkpointed'
    assert repo.findings_step('test', FindingsPhase.RANK) is None
    assert not repo.findings_artifacts('test', RankedFindingBundle)
    client = RankClient()
    resumed = await FindingsRankingService(V2Repository(tmp_path), policy).rank('test', plan, document, client=client)
    assert client.calls == 2 and resumed.step.accounting.cached == 1
    assert len(resumed.ranks) == 3


@pytest.mark.asyncio
async def test_policy_input_tampering_deadline_and_cache_identity(tmp_path):
    document, filing, values = bundles(count=2)
    repo, plan, _ = await rank(tmp_path, document, filing, values)
    altered = plan.model_copy(deep=True)
    altered.batches.batches[0].request.state['items']['item_0']['rubric'][0] = 'injected'
    with pytest.raises(ValueError, match='exact canonical'):
        await FindingsRankingService(repo, FindingsPolicy()).rank('test', altered, document, client=RankClient(fail_at=1))
    changed_policy = FindingsPolicy(required_support_threshold=.8)
    changed = build_ranking_plan(document, filing, values, model='jev-1.13.0', policy=changed_policy)
    assert changed.identity != plan.identity
    client = RankClient()
    await FindingsRankingService(repo, changed_policy).rank('test', changed, document, client=client)
    assert client.calls > 0
    class Slow:
        async def evaluate(self, request):
            await asyncio.Event().wait()
    changed = build_ranking_plan(document, filing.model_copy(update={'ticker':'CHANGED'}), values,
                                model='jev-1.13.0', policy=FindingsPolicy())
    with pytest.raises(FindingsRankingFailure) as error:
        await FindingsRankingService(repo, FindingsPolicy()).rank('test', changed, document,
                                                               client=Slow(), deadline_seconds=.01)
    assert error.value.result.step.status == 'interrupted' and not error.value.result.conversion_packs


@pytest.mark.asyncio
async def test_support_upstream_source_ties_and_policy_revalidation(tmp_path):
    from profitlab.v2.finding_concepts import FindingConcept
    document, filing, values = bundles(count=60)
    lane = [b for b in values if b.concept == FindingConcept.ANNUAL_PROFIT][:4]
    assert len(lane) == 4
    # All scores tie; source support wins before upstream relevance, then source order.
    modified = []
    for index, bundle in enumerate(lane):
        source = bundle.source.model_copy(update={'owners':[
            owner.model_copy(update={'concept_score':.7 if index == 2 else .9})
            for owner in bundle.source.owners]})
        assignment = bundle.assignment.model_copy(update={'answer':NoulAnswer(type='noul', noul=.7 if index == 0 else .9)})
        modified.append(bundle.model_copy(update={'source':source, 'assignment':assignment}))
    policy = FindingsPolicy(max_bundles_per_concept=4)
    _, _, result = await rank(tmp_path, document, filing, modified, policy)
    order = [r.bundle_id for r in sorted(result.ranks, key=lambda r:r.rank_within_concept)]
    assert order == [lane[1].bundle_id, lane[3].bundle_id, lane[2].bundle_id, lane[0].bundle_id]
    with pytest.raises(ValueError, match='current Findings policy'):
        build_ranking_plan(document, filing, modified, model='jev-1.13.0',
                           policy=FindingsPolicy(source_support_threshold=.8))
    # A changed tie input invalidates semantic reuse even though provider states stay exact.
    changed = modified[0].model_copy(update={'assignment':modified[0].assignment.model_copy(update={
        'answer':NoulAnswer(type='noul', noul=.8)})})
    original = build_ranking_plan(document, filing, modified, model='jev-1.13.0', policy=policy)
    altered = build_ranking_plan(document, filing, [changed,*modified[1:]], model='jev-1.13.0', policy=policy)
    assert original.identity != altered.identity


@pytest.mark.asyncio
async def test_cross_run_identity_reuse_remaps_occurrences_without_source_changes(tmp_path):
    document, filing, values = bundles(count=3)
    policy = FindingsPolicy()
    repo, original, _ = await rank(tmp_path, document, filing, values, policy)
    def remap(value):
        if isinstance(value, dict):
            return {key: ('fresh-document' if key == 'document_id' else
                          'fresh-filing' if key == 'filing_id' else
                          'fresh-'+item if key in ('chunk_id','owning_chunk_id','section_id') else remap(item))
                    for key, item in value.items()}
        if isinstance(value, list):
            return [remap(x) for x in value]
        return value
    changed = [FindingEvidenceBundle.model_validate(remap(b.model_dump(mode='json'))) for b in values]
    fresh_doc = document.model_copy(update={'ref':document.ref.model_copy(update={
        'document_id':'fresh-document','filing_id':'fresh-filing'})})
    fresh_filing = filing.model_copy(update={'filing_id':'fresh-filing'})
    plan = build_ranking_plan(fresh_doc, fresh_filing, changed, model='jev-1.13.0', policy=policy)
    assert plan.identity == original.identity
    client = RankClient(fail_at=1)
    result = await FindingsRankingService(repo, policy).rank('test', plan, fresh_doc, client=client)
    assert client.calls == 0 and result.step.accounting.cached > 0
    assert all(r.source_range.document_id == 'fresh-document' for r in result.ranks)
    assert result.conversion_packs[0].state.filing.filing_id == 'fresh-filing'
    assert all(x.source.source_range.document_id == 'fresh-document'
               for p in result.conversion_packs for x in p.state.selected_bundles)
