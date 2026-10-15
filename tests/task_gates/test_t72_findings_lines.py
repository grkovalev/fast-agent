"""T72: real SEC/JEV replay plus controlled policy/failure boundary checks."""
import asyncio
import copy
import json
from datetime import date
from pathlib import Path

import pytest
from test_t71_findings_candidates import create_repo, saved_inputs

from profitlab.providers.jev import JevResponse, NoulAnswer, TokenUsage
from profitlab.v2.finding_concepts import FindingConcept
from profitlab.v2.findings_candidates import enumerate_candidates
from profitlab.v2.findings_contracts import (
    AssignmentState,
    ConceptLineAssignment,
    FindingsFilingMetadata,
    FindingsPhase,
    occurrence_id,
    visible_numeric_spans,
)
from profitlab.v2.findings_lines import (
    FindingsAssignmentCancelled,
    FindingsAssignmentFailure,
    FindingsAssignmentPlan,
    FindingsAssignmentsResult,
    FindingsLineAssignmentService,
    build_assignment_plan,
)
from profitlab.v2.findings_policy import FindingsPolicy, JevPhaseBudget
from profitlab.v2.storage import V2Repository

FIXTURE = Path(__file__).parents[1] / 'fixtures/benchmarks/t72/live-lines-azz.json'


def inputs(policy=None):
    policy = policy or FindingsPolicy()
    document, chunks, scores = saved_inputs()
    lines = enumerate_candidates(document, chunks, scores, relevance_threshold=.2, policy=policy).lines
    filing = FindingsFilingMetadata(ticker='AZZ', filing_id=document.ref.filing_id,
                                   report_date=date(2026, 2, 28))
    return document, filing, lines


class ControlledClient:
    """Only synthetic judgments: threshold, cancellation and failure controls."""
    def __init__(self, probability=.9, fail_at=None, cancel=False):
        self.calls = 0
        self.probability, self.fail_at, self.cancel = probability, fail_at, cancel

    async def evaluate(self, request):
        self.calls += 1
        if self.calls == self.fail_at:
            if self.cancel:
                raise asyncio.CancelledError()
            raise RuntimeError('controlled provider failure')
        return JevResponse(model=request.model, answers={
            q: NoulAnswer(type='noul', noul=self.probability) for q in request.questions},
            usage=TokenUsage(input_tokens=100, output_tokens=10))


@pytest.mark.asyncio
async def test_real_executed_requests_answers_storage_and_restart(tmp_path):
    record = json.loads(FIXTURE.read_text())
    plan = FindingsAssignmentPlan.model_validate(record['plan'])
    expected = FindingsAssignmentsResult.model_validate(record['result'])
    policy = FindingsPolicy()
    # Preserve the genuine fixture unchanged; rebuild its identical wire requests
    # under today's complete policy identity (T75 adds conversion-only bounds).
    recorded_plan = plan
    document, _, _ = inputs(policy)
    plan = build_assignment_plan(document, recorded_plan.filing, recorded_plan.candidates,
        model=recorded_plan.identity.model_identity, policy=policy,
        max_requests=recorded_plan.request_allowance)
    assert [x.request for x in plan.batches.batches] == [x.request for x in recorded_plan.batches.batches]
    responses = {x.batch.batch_id: x.response for x in expected.execution.completed}
    class Replay:
        async def evaluate(self, request):
            batch = next(b for b in plan.batches.batches if b.request == request)
            return responses[batch.batch_id]
    repo = create_repo(tmp_path)
    result = await FindingsLineAssignmentService(repo, policy).assign('test', plan, client=Replay())
    assert [x.answer for x in result.assignments] == [x.answer for x in expected.assignments]
    assert repo.findings_artifacts('test', ConceptLineAssignment) == result.assignments
    assert repo.findings_step('test', FindingsPhase.ASSIGN) == result.step
    assert FindingsAssignmentsResult.model_validate_json(result.model_dump_json()) == result
    for batch in plan.batches.batches:
        assert all(q.type == 'noul' for q in batch.request.questions.values())
        for value in batch.request.state['items'].values():
            state = AssignmentState.model_validate(value)
            assert not {'numeric_spans', 'owners', 'outline', 'structured_facts'} & value.keys()
            document, _, _ = inputs()
            assert document.slice(state.candidate.source_range) == state.candidate.exact_text
    client = ControlledClient(fail_at=1)
    resumed = await FindingsLineAssignmentService(V2Repository(tmp_path), policy).assign(
        'test', plan, client=client)
    assert client.calls == 0 and resumed.step.accounting.dispatched == 0
    assert resumed.step.accounting.cached == len(plan.batches.batches)
    assert resumed.step.accounting.usage is None
    assert all(x.provenance.cached for x in resumed.assignments)
    # Genuine smoke outputs distinguish basic-only from diluted EPS on saved rows.
    by_line = {(x.source_range.start_line, x.concept): x for x in result.assignments}
    assert by_line[288, FindingConcept.DILUTED_EPS].decision == 'rejected'
    assert by_line[289, FindingConcept.DILUTED_EPS].decision == 'supported'


@pytest.mark.asyncio
async def test_independent_memberships_boundaries_and_empty(tmp_path):
    document, filing, lines = inputs()
    # Real row with both net income and diluted EPS; synthetic probabilities
    # deliberately prove that the application never forces one winning concept.
    selected = [x for x in lines if x.source_range.start_line == 147 and
                x.concept in (FindingConcept.ANNUAL_PROFIT, FindingConcept.DILUTED_EPS)]
    repo = create_repo(tmp_path)
    for probability, decision in ((.65, 'supported'), (.2, 'uncertain'), (.199, 'rejected')):
        policy = FindingsPolicy(version=f'controlled-{probability}')
        plan = build_assignment_plan(document, filing, selected, model='jev-1.13.0', policy=policy)
        result = await FindingsLineAssignmentService(repo, policy).assign(
            'test', plan, client=ControlledClient(probability))
        assert len(result.assignments) == 2
        assert {x.decision for x in result.assignments} == {decision}
        assert all(x.source_range.start_line == 147 for x in result.assignments)
        assert all(not hasattr(x, 'amount') for x in result.assignments)
    empty = build_assignment_plan(document, filing, [], model='jev-1.13.0', policy=policy)
    client = ControlledClient(fail_at=1)
    result = await FindingsLineAssignmentService(repo, policy).assign('test', empty, client=client)
    assert result.step.status == 'completed' and not result.assignments and client.calls == 0
    assert not repo.findings_artifacts('test', ConceptLineAssignment)


@pytest.mark.asyncio
async def test_whole_request_omissions_and_deterministic_plans(tmp_path):
    document, filing, lines = inputs()
    selected = lines[:4]
    policy = FindingsPolicy(assign_budget=JevPhaseBudget(questions=1), max_jev_requests=1)
    plan = build_assignment_plan(document, filing, selected, model='jev-1.13.0', policy=policy)
    assert plan == build_assignment_plan(document, filing, list(reversed(selected)),
                                         model='jev-1.13.0', policy=policy)
    result = await FindingsLineAssignmentService(create_repo(tmp_path), policy).assign(
        'test', plan, client=ControlledClient())
    assert result.step.status == 'partial' and len(result.assignments) == 1
    assert len(result.step.omissions) == 3
    assert all(x.kind == 'count_limit' and x.coverage_cut for x in result.step.omissions)
    policy = FindingsPolicy(assign_budget=JevPhaseBudget(serialized_characters=1000))
    plan = build_assignment_plan(document, filing, selected, model='jev-1.13.0', policy=policy)
    assert not plan.batches.batches
    result = await FindingsLineAssignmentService(V2Repository(tmp_path), policy).assign(
        'test', plan, client=ControlledClient(fail_at=1))
    assert result.step.status == 'partial' and not result.assignments
    assert all(x.kind == 'size_limit' for x in result.step.omissions)


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel', [False, True])
async def test_failure_checkpoints_resume_without_publishing_subset(tmp_path, cancel):
    policy = FindingsPolicy(assign_budget=JevPhaseBudget(questions=1))
    document, filing, lines = inputs(policy)
    plan = build_assignment_plan(document, filing, lines[:3], model='jev-1.13.0', policy=policy)
    repo = create_repo(tmp_path)
    service = FindingsLineAssignmentService(repo, policy)
    with pytest.raises(FindingsAssignmentCancelled if cancel else FindingsAssignmentFailure) as error:
        await service.assign('test', plan, client=ControlledClient(fail_at=2, cancel=cancel))
    result = error.value.result
    assert result.step.status == ('cancelled' if cancel else 'failed')
    assert result.step.availability == 'checkpointed' and len(result.assignments) == 1
    assert repo.findings_step('test', FindingsPhase.ASSIGN) is None
    assert not repo.findings_artifacts('test', ConceptLineAssignment)
    assert len(repo.findings_checkpoints('test', plan.identity)) == 1
    client = ControlledClient()
    resumed = await FindingsLineAssignmentService(V2Repository(tmp_path), policy).assign(
        'test', plan, client=client)
    assert client.calls == 2 and resumed.step.accounting.cached == 1
    assert len(resumed.assignments) == 3 and resumed.step.status == 'completed'


@pytest.mark.asyncio
async def test_input_policy_isolation_and_prepared_inspection_tampering(tmp_path):
    policy = FindingsPolicy()
    document, filing, lines = inputs()
    candidate = lines[0]
    with pytest.raises(ValueError, match='canonical line'):
        build_assignment_plan(document, filing,
            [candidate.model_copy(update={'exact_text': candidate.exact_text + ' changed'})],
            model='jev-1.13.0', policy=policy)
    with pytest.raises(ValueError, match='does not belong'):
        build_assignment_plan(document, filing.model_copy(update={'filing_id':'wrong'}),
                              [candidate], model='jev-1.13.0', policy=policy)
    with pytest.raises(ValueError, match='pinned'):
        build_assignment_plan(document, filing, [candidate], model='jev-latest', policy=policy)
    plan = build_assignment_plan(document, filing, [candidate], model='jev-1.13.0', policy=policy)
    service = FindingsLineAssignmentService(create_repo(tmp_path), policy)
    await service.assign('test', plan, client=ControlledClient())
    changed = FindingsPolicy(source_support_threshold=.8)
    other = build_assignment_plan(document, filing, [candidate], model='jev-1.13.0', policy=changed)
    client = ControlledClient()
    await FindingsLineAssignmentService(V2Repository(tmp_path), changed).assign('test', other, client=client)
    assert client.calls == 1
    altered = copy.deepcopy(plan)
    altered.batches.batches[0].request.state['extra'] = 'injected'
    with pytest.raises(ValueError, match='exact inputs'):
        await service.assign('test', altered, client=ControlledClient(fail_at=1))


@pytest.mark.asyncio
async def test_cross_run_local_id_remapping_and_deadline(tmp_path):
    policy = FindingsPolicy()
    document, filing, lines = inputs()
    candidate = next(x for x in lines if x.source_range.start_line == 291 and
                     x.concept == FindingConcept.DILUTED_SHARES)
    plan = build_assignment_plan(document, filing, [candidate], model='jev-1.13.0', policy=policy)
    repo = create_repo(tmp_path)
    await FindingsLineAssignmentService(repo, policy).assign('test', plan, client=ControlledClient())
    # A new run's local filing/document/chunk/section IDs must not invalidate exact semantic reuse.
    remapped_document = document.model_copy(update={'ref': document.ref.model_copy(update={
        'document_id':'fresh-document', 'filing_id':'fresh-filing'})})
    remapped = json.loads(candidate.model_dump_json())
    def local_ids(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key in ('document_id', 'filing_id', 'chunk_id', 'section_id'):
                    value[key] = 'fresh-' + key
                else:
                    local_ids(item)
        elif isinstance(value, list):
            for item in value:
                local_ids(item)
    local_ids(remapped)
    remapped['source_range']['document_id'] = 'fresh-document'
    for owner in remapped['owners']:
        owner['chunk']['core_range']['document_id'] = 'fresh-document'
    remapped['owning_chunk_id'] = 'fresh-chunk_id'
    new_candidate = type(candidate).model_validate(remapped)
    new_plan = build_assignment_plan(remapped_document, filing.model_copy(update={'filing_id':'fresh-filing'}),
                                    [new_candidate], model='jev-1.13.0', policy=policy)
    client = ControlledClient(fail_at=1)
    result = await FindingsLineAssignmentService(repo, policy).assign('test', new_plan, client=client)
    assert client.calls == 0 and result.assignments[0].source_range.document_id == 'fresh-document'
    assert result.assignments[0].provenance.cached
    # Changing reporting metadata invalidates reuse, and timeout never becomes an empty success.
    changed = build_assignment_plan(document, filing.model_copy(update={'report_date':date(2025,2,28)}),
                                    [candidate], model='jev-1.13.0', policy=policy)
    class Slow:
        async def evaluate(self, _request):
            await asyncio.Event().wait()
    with pytest.raises(FindingsAssignmentFailure) as error:
        await FindingsLineAssignmentService(repo, policy).assign(
            'test', changed, client=Slow(), deadline_seconds=.01)
    assert error.value.result.step.status == 'interrupted'
    assert error.value.result.step.availability == 'unavailable'
    assert repo.findings_step('test', FindingsPhase.ASSIGN) == result.step


def test_annual_quarterly_labels_and_numbers_remain_exact_without_semantic_filtering():
    document, filing, lines = inputs()
    candidate = lines[0]
    for text in ('Year ended 2026 | diluted EPS 10.50 | 1.79',
                 'Three months ended 2026 | diluted EPS 2.40 | 1.20'):
        # Controlled label variants exercise request construction, not provider accuracy.
        source = candidate.source_range
        controlled = candidate.model_copy(update={'exact_text':text,
            'candidate_id':occurrence_id(candidate.concept, source),
            'numeric_spans':visible_numeric_spans(text)})
        modified = document.model_copy(deep=True)
        modified.lines[source.start_line-1] = modified.lines[source.start_line-1].model_copy(
            update={'text':text})
        plan = build_assignment_plan(modified, filing, [controlled],
                                     model='jev-1.13.0', policy=FindingsPolicy())
        state = next(iter(plan.batches.batches[0].request.state['items'].values()))
        assert state['candidate']['exact_text'] == text
        instructions = next(iter(plan.batches.batches[0].request.questions.values())).instructions
        assert 'annual-duration' in instructions['question']
        assert 'Do not select a numeric span, amount or fiscal year' in instructions['question']
