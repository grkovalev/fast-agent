"""T76 atomic activation on saved SEC inputs with controlled provider judgments."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from test_t71_findings_candidates import create_repo, saved_inputs
from test_t74_findings_ranking import RankClient
from test_t75_findings_conversion import proposal

from profitlab.providers.jev import JevResponse, NoulAnswer, TokenUsage
from profitlab.settings import Settings
from profitlab.v2.contracts import OutlineSection
from profitlab.v2.findings_batching import execute_jev_batches
from profitlab.v2.findings_contracts import ConversionResponse, FindingEvidenceBundle, FindingsPhase
from profitlab.v2.findings_policy import FindingsPolicy
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.pipeline import V2PipelineService
from profitlab.web.app import create_app


def setup(tmp_path, policy=None):
    document, chunks, scores = saved_inputs()
    repo = create_repo(tmp_path)
    repo.save_canonical_document('test', document, b'<html/>', '<html/>')
    repo.save_filing('test', document.ref.filing_id, document.ref.source_hash,
                    {'report_date': '2026-02-28'})
    repo.save_chunks('test', chunks)
    sections = []
    for sid in dict.fromkeys(c.section_id for c in chunks):
        ranges = [r for c in chunks if c.section_id == sid for r in [c.core_range, *c.context_ranges]]
        sections.append(OutlineSection(section_id=sid, generated_topic='Saved source navigation',
            primary_range=ranges[0].model_copy(update={
                'start_line': min(r.start_line for r in ranges), 'end_line': max(r.end_line for r in ranges)})))
    repo.save_outline_sections('test', sections)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, findings_policy=policy or FindingsPolicy(max_candidate_lines=6),
        TYPESAFE_MODEL='jev-1.13.0', _env_file=None)
    return repo, document, chunks, scores, settings


def providers(monkeypatch, *, probability=.9, failure=False, waiting=False):
    calls = []
    class Client:
        async def evaluate(self, request):
            calls.append(request)
            if waiting:
                await asyncio.sleep(10)
            if failure:
                raise RuntimeError('controlled provider failure')
            if any(q.type == 'score' for q in request.questions.values()):
                return await RankClient().evaluate(request)
            return JevResponse(model=request.model,
                answers={q: NoulAnswer(type='noul', noul=probability) for q in request.questions},
                usage=TokenUsage(input_tokens=100, output_tokens=10))
    async def execute(plan, settings, recorder, **kwargs):
        return await execute_jev_batches(plan, Client(), concurrency=settings.v2_provider_concurrency, **kwargs)
    for name in ('lines', 'context', 'ranking'):
        monkeypatch.setattr(f'profitlab.v2.findings_{name}.run_live_jev_batches', execute)
    async def convert(request, _settings, _recorder):
        calls.append(request)
        return ConversionResponse(findings=[proposal(b) for b in request.state.selected_bundles],
            model=request.model, usage=TokenUsage(input_tokens=200, output_tokens=30))
    monkeypatch.setattr('profitlab.v2.findings_conversion.live_conversion', convert)
    return calls


@pytest.mark.asyncio
async def test_seven_phases_partial_seal_restart_cache_routes_and_accounting(tmp_path, monkeypatch):
    repo, document, chunks, scores, settings = setup(tmp_path)
    calls = providers(monkeypatch)
    result = await FindingsService(settings, repo).build('test', document, chunks, scores)
    assert result.sealed and result.status == 'partial'  # Explicit numeric enumeration cap.
    assert len(result.steps) == 7 and result.published_finding_ids
    assert result.jev_assign.dispatched and result.jev_attach.dispatched and result.jev_rank.dispatched
    assert result.llm_conversion.dispatched == 1 and result.llm_repair.dispatched == 0
    assert all(f.bundle_id and f.finding_type != 'unresolved' for f in repo.findings('test'))
    with pytest.raises(ValueError, match='sealed'):
        repo.require_findings_seal('test')  # Stage is still queued, atomic rows alone cannot start Facts.
    repo.update_stage(repo.stage('test', 'findings').model_copy(update={'status': result.status}),
                      event_kind='stage_finished', event_summary='sealed partial')
    repo.require_findings_seal('test')
    summary = repo.finding_summary('test')
    assert summary['provider_requests'] == len(calls)
    first_calls = len(calls)
    resumed = await FindingsService(settings, repo).build('test', document, chunks, scores)
    assert resumed.sealed and len(calls) == first_calls
    assert resumed.jev_assign.cached and resumed.llm_conversion.cached
    assert repo.finding_summary('test')['provider_requests'] == first_calls
    bundles = repo.findings_artifacts('test', FindingEvidenceBundle)
    assert bundles
    with TestClient(create_app(settings)) as client:
        overview = client.get('/v2/runs/test/pipeline').text
        selected = client.get('/v2/runs/test/pipeline?stage=findings').text
        for phase in FindingsPhase:
            assert f'data-findings-station="{phase.value}"' in overview
            assert phase.value in selected
            response = client.get(f'/v2/runs/test/findings/phases/{phase.value}')
            assert response.status_code == 200
        assert client.get('/v2/runs/test/findings/phases/wrong').status_code == 404
        assert client.get('/v2/runs/test/findings/phases/candidates?page=0').status_code == 422
    assert len(calls) == first_calls  # Render/read performs no provider I/O.
    for phrase in ('selected bundles only', 'accepted findings bypass repair', 'uncertain',
                   'zero LLM calls', 'partial sealed', 'not saved run data'):
        assert phrase in overview
    assert 'whole initial candidate set' not in selected
    assert 'JEV TYPE CLASSIFIER' not in overview
    assert 'source?document=' in overview and '#line-' in overview
    assert V2PipelineService(settings)._version_components()['findings_policy'] == settings.findings_policy.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize('probability', [.1, .4])
async def test_no_supported_lines_empty_seal_without_conversion(tmp_path, monkeypatch, probability):
    repo, document, chunks, scores, settings = setup(tmp_path)
    calls = providers(monkeypatch, probability=probability)
    result = await FindingsService(settings, repo).build('test', document, chunks, scores)
    assert result.sealed and not result.published_finding_ids and result.llm_conversion.dispatched == 0
    assert all(not hasattr(call, 'body') for call in calls)
    assert not repo.findings('test')


@pytest.mark.asyncio
async def test_failed_cancelled_deadline_and_resume_never_publish_subset(tmp_path, monkeypatch):
    repo, document, chunks, scores, settings = setup(tmp_path)
    providers(monkeypatch, failure=True)
    with pytest.raises(Exception, match='RuntimeError'):
        await FindingsService(settings, repo).build('test', document, chunks, scores)
    failed = repo.findings_run_result('test')
    assert failed.status == 'failed' and not failed.sealed and not repo.findings('test')
    providers(monkeypatch, waiting=True)
    task = asyncio.create_task(FindingsService(settings, repo).build('test', document, chunks, scores))
    await asyncio.sleep(.02)
    repo.request_cancellation('test')
    with pytest.raises(asyncio.CancelledError):
        await task
    assert repo.findings_run_result('test').status == 'cancelled'
    repo.resume('test')
    settings.findings_policy = settings.findings_policy.model_copy(update={'total_deadline_seconds': .01})
    with pytest.raises(TimeoutError, match='deadline'):
        await FindingsService(settings, repo).build('test', document, chunks, scores)
    assert repo.findings_run_result('test').status == 'failed'
    assert not repo.findings_run_result('test').sealed
    assert not repo.findings('test')


@pytest.mark.asyncio
async def test_scheduler_runs_partial_findings_then_independent_lanes(tmp_path, monkeypatch):
    from types import SimpleNamespace
    repo, _document, _chunks, scores, settings = setup(tmp_path)
    repo.save_scores('test', 'chunk_score', scores)
    for stage in ('source', 'outline', 'section_score', 'chunk', 'chunk_score'):
        repo.update_stage(repo.stage('test', stage).model_copy(update={'status': 'completed'}),
                          event_kind='stage_finished', event_summary='Retained upstream checkpoint')
    calls = providers(monkeypatch)
    observed = []
    def facts(self, run):
        self.repo.require_findings_seal(run.run_id)
        observed.append(self.repo.findings_run_result(run.run_id).status)
        return [], {}, '0'*64
    async def compare(self, run_id):
        self.repo.require_findings_seal(run_id)
        return SimpleNamespace(comparisons=[], summary={'expected_facts': 0, 'exact_matches': 0, 'misses': 0})
    monkeypatch.setattr('profitlab.v2.facts_service.CompanyFactsService.load', facts)
    monkeypatch.setattr('profitlab.v2.evaluation_service.EvaluationService.compare_with_scale_verdicts', compare)
    monkeypatch.setattr('profitlab.v2.benchmark.RetrievalBenchmarkService.evaluate_automatic', lambda *_: None)
    pipeline = V2PipelineService(settings)
    result = await pipeline.run('test', implement_source=True)
    assert result.status == 'partial' and observed == ['partial']
    assert repo.stage('test', 'findings').status == 'partial'
    assert repo.stage('test', 'facts').status == repo.stage('test', 'evaluate').status == 'completed'
    assert repo.performance_summary('test')['provider_requests']['findings_live'] == len(calls)
    await pipeline.run('test', implement_source=True)
    assert observed == ['partial']  # Explicit partial seal is resumable completion, no repeated calls.


@pytest.mark.asyncio
async def test_paid_phase_work_survives_failed_attempt_resume(tmp_path, monkeypatch):
    repo, document, chunks, scores, settings = setup(tmp_path)
    original = providers(monkeypatch)
    from profitlab.v2 import findings_context
    live = findings_context.run_live_jev_batches
    async def fail(*args, **kwargs):
        raise RuntimeError('Failure after successful assignment checkpoint')
    monkeypatch.setattr(findings_context, 'run_live_jev_batches', fail)
    with pytest.raises(RuntimeError):
        await FindingsService(settings, repo).build('test', document, chunks, scores)
    failed = repo.finding_summary('test')
    assert failed['jev_assign']['dispatched'] == len(original) > 0
    monkeypatch.setattr(findings_context, 'run_live_jev_batches', live)
    result = await FindingsService(settings, repo).build('test', document, chunks, scores)
    assert result.sealed and result.jev_assign.dispatched == failed['jev_assign']['dispatched']
    assert result.jev_assign.cached > 0
    assert repo.finding_summary('test')['provider_requests'] == len(original)


@pytest.mark.asyncio
async def test_process_recovery_retains_successful_batch_usage(tmp_path, monkeypatch):
    from datetime import date

    from profitlab.v2.findings_candidates import enumerate_candidates
    from profitlab.v2.findings_contracts import (
        FindingsFilingMetadata,
        FindingsRunSummary,
        FindingsStepResult,
    )
    from profitlab.v2.findings_lines import FindingsLineAssignmentService, build_assignment_plan

    repo, document, chunks, scores, settings = setup(tmp_path)
    providers(monkeypatch)
    policy = settings.findings_policy
    candidates = enumerate_candidates(document, chunks, scores, relevance_threshold=.2, policy=policy)
    repo.complete_findings_step('test', candidates.step, [*candidates.concepts, *candidates.lines])
    repo.save_findings_run_result('test', FindingsRunSummary(status='running', policy_hash=policy.identity(),
                                                           steps=[candidates.step]))
    repo.save_findings_progress('test', FindingsStepResult(phase=FindingsPhase.ASSIGN, status='running',
        availability='checkpointed', input_hash=document.ref.source_hash, policy_hash=policy.identity()))
    plan = build_assignment_plan(document, FindingsFilingMetadata(ticker='AZZ',
        filing_id=document.ref.filing_id, report_date=date(2026, 2, 28)), candidates.lines,
        model=settings.typesafe_model, policy=policy)
    with monkeypatch.context() as patch:
        # Simulate process loss after successful batch persistence, before phase finalization.
        patch.setattr(repo, 'complete_findings_step', lambda *_: None)
        from profitlab.v2.section_scoring import _V2Trace
        assigned = await FindingsLineAssignmentService(repo, policy).assign('test', plan,
            settings=settings, recorder=_V2Trace(repo, 'test', settings.redactor(), 'findings'))
    repo.update_run('test', status='running', summary='active', kind='stage_started')
    repo.update_stage(repo.stage('test', 'findings').model_copy(update={'status':'running'}),
                      event_kind='stage_started', event_summary='active')
    pipeline = V2PipelineService(settings)
    pipeline.recover()
    interrupted = repo.findings_run_result('test')
    assert interrupted.status == 'interrupted' and not interrupted.sealed
    assert interrupted.jev_assign.dispatched == assigned.step.accounting.dispatched
    assert interrupted.jev_assign.usage == assigned.step.accounting.usage
    assert 'In-flight' in interrupted.limitation
    assert repo.findings_step('test', FindingsPhase.ASSIGN).status == 'interrupted'
    pipeline.resume('test')
    resumed = await FindingsService(settings, repo).build('test', document, chunks, scores)
    assert resumed.sealed and resumed.jev_assign.dispatched == interrupted.jev_assign.dispatched
    assert resumed.jev_assign.cached == assigned.step.accounting.dispatched


@pytest.mark.asyncio
async def test_exhausted_global_budget_is_partial_and_atomic_seal_recovers(tmp_path, monkeypatch):
    repo, document, chunks, scores, settings = setup(tmp_path, FindingsPolicy(max_candidate_lines=6, max_jev_requests=1))
    calls = providers(monkeypatch)
    result = await FindingsService(settings, repo).build('test', document, chunks, scores)
    assert result.status == 'partial' and result.sealed
    assert len(calls) == 1 and result.llm_conversion.dispatched == 0
    assert any(s.omissions for s in result.steps if s.phase != FindingsPhase.CANDIDATES)
    # Crash after the atomic seal, before the scheduler's stage-status write.
    repo.update_run('test', status='running', summary='active', kind='stage_started')
    repo.update_stage(repo.stage('test', 'findings').model_copy(update={'status':'running'}),
                      event_kind='stage_started', event_summary='active')
    V2PipelineService(settings).recover()
    assert repo.stage('test', 'findings').status == 'partial'
    repo.require_findings_seal('test')
    assert repo.findings_run_result('test') == result
