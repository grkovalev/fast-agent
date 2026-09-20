"""Managed workflow acceptance with the real services and explicitly fake providers."""
import asyncio
import socket
import time

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from profitlab.analysis.reporting import ReportingService
from profitlab.cli import app
from profitlab.pipeline import PipelineService
from profitlab.settings import Settings
from profitlab.trace import TraceRecorder
from profitlab.web.app import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Demo must not use the network')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    return Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                    sec_user_agent='', typesafe_api_key='', llm_api_key='')


def complete(settings, run_id='workflow', scenario='normal'):
    service = PipelineService(settings)
    service.create('DEMO', mode='demo', run_id=run_id, scenario=scenario)
    result = asyncio.run(service.run(run_id))
    assert result.stage == 'complete', result.limitation
    return service


def test_pipeline_persistence_resume_and_real_report(settings):
    service = complete(settings)
    state = service.state('workflow')
    assert all(s.status == 'completed' and s.input_hash and s.output_hash for s in state.stages)
    assert all(s.source_run_id == 'workflow' for s in state.stages)
    index, report, rendered = ReportingService(settings).latest('workflow')
    assert index['synthetic'] and index['model_narrative']
    assert report.validation_status == 'valid'
    assert any('25.00%' in text for text in rendered.values())
    events, _ = TraceRecorder(service.repo, 'workflow').history()
    service = PipelineService(settings)
    assert asyncio.run(service.run('workflow')).stage == 'complete'
    after, _ = TraceRecorder(service.repo, 'workflow').history()
    assert len(events) == len(after)  # Reuse emits no fabricated tool calls.
    assert service.state('workflow').stages == state.stages
    with pytest.raises(ValueError, match='already exists'):
        service.create('DEMO', mode='demo', run_id='workflow')


def test_chunk_settings_invalidate_downstream(settings):
    service = complete(settings)
    before = service.state('workflow')
    changed = settings.model_copy(update={'chunk_target_tokens': 750, 'chunk_overlap_tokens': 90})
    service = PipelineService(changed)
    asyncio.run(service.run('workflow'))
    after = service.state('workflow')
    assert after.run.stage == 'complete', after.error
    assert after.stages[:3] == before.stages[:3]
    assert after.stages[3].input_hash != before.stages[3].input_hash
    assert after.stages[4].input_hash != before.stages[4].input_hash
    assert after.stages[8].input_hash != before.stages[8].input_hash
    from profitlab.documents.chunk_service import ChunkService
    _, chunks = ChunkService(changed).list('workflow')
    _, decisions = __import__('profitlab.providers.screening', fromlist=['ScreeningService']).ScreeningService(changed).latest('workflow')
    assert set(decisions) <= {c.chunk_id for c in chunks}


def test_writer_settings_only_invalidate_writer(settings):
    service = complete(settings)
    before = service.state('workflow')
    changed = PipelineService(settings.model_copy(update={'writer_max_tool_calls': 9}))
    asyncio.run(changed.run('workflow'))
    after = changed.state('workflow')
    assert after.stages[:8] == before.stages[:8]
    assert after.stages[8].input_hash != before.stages[8].input_hash
    assert after.stages[9].input_hash != before.stages[9].input_hash


def test_cancel_interrupted_resume_and_no_duplicate_facts(settings):
    service = PipelineService(settings.model_copy(update={'demo_stage_delay': .05}))
    service.create('DEMO', mode='demo', run_id='slow', scenario='slow')
    async def work():
        task = asyncio.create_task(service.run('slow'))
        while service.state('slow').stages[0].status != 'completed':
            await asyncio.sleep(.01)
        service.cancel('slow')
        await task
    asyncio.run(work())
    state = service.state('slow')
    assert state.run.status == 'cancelled'
    assert state.stages[0].status == 'completed'
    asyncio.run(service.run('slow'))
    state = service.state('slow')
    assert state.run.stage == 'complete' and state.run.status != 'cancelled'
    assert len({a['artifact_id'] for a in service.repo.artifacts('slow')}) == len(service.repo.artifacts('slow'))
    events, _ = TraceRecorder(service.repo, 'slow').history()
    assert any(e.kind == 'workflow_stop' and e.status == 'cancelled' for e in events)


def test_restart_recovery_and_duplicate_worker(settings):
    service = PipelineService(settings.model_copy(update={'demo_stage_delay': .05}))
    service.create('DEMO', mode='demo', run_id='restart', scenario='slow')
    state = service.state('restart')
    stages = list(state.stages)
    stages[0] = stages[0].model_copy(update={'status': 'running'})
    service.save(state.model_copy(update={'run': state.run.model_copy(update={'status': 'running'}), 'stages': stages}))
    with TestClient(create_app(service.settings)) as client:
        assert client.get('/runs/restart/progress').json()['run']['status'] == 'interrupted'
    async def work():
        task = asyncio.create_task(service.run('restart'))
        await asyncio.sleep(.01)
        with pytest.raises(ValueError, match='already active'):
            await service.run('restart')
        await task
    asyncio.run(work())
    assert service.state('restart').run.stage == 'complete'


def test_failure_credentials_and_budget(settings):
    service = PipelineService(settings)
    service.create('MSFT', mode='live', run_id='missing')
    result = asyncio.run(service.run('missing'))
    assert result.status == 'failed' and 'SEC_USER_AGENT' in result.limitation
    assert not any(a['artifact_id'].startswith('screen-') for a in service.repo.artifacts('missing'))
    configured = settings.model_copy(update={'sec_user_agent': 'ProfitLab research@real-domain.org'})
    service = PipelineService(configured)
    service.create('MSFT', mode='live', run_id='paid')
    # Earlier operations are explicitly controlled for this credential preflight test.
    # Directly test real run starting at paid stage with controlled earlier execution.
    original = service.execute
    async def controlled(run_id, stage):
        if stage in ('discover', 'download', 'parse', 'chunk'):
            return
        await original(run_id, stage)
    service.execute = controlled
    result = asyncio.run(service.run('paid'))
    assert result.status == 'failed' and 'TYPESAFE_API_KEY' in result.limitation and 'LLM_API_KEY' in result.limitation
    assert not any(a['artifact_id'].startswith('screen-') for a in service.repo.artifacts('paid'))
    limited = PipelineService(settings.model_copy(update={'stage_timeout': .01, 'demo_stage_delay': .1}))
    limited.create('DEMO', mode='demo', run_id='budget', scenario='slow')
    result = asyncio.run(limited.run('budget'))
    assert result.status == 'failed' and 'TimeoutError' in result.limitation


def test_live_reservation(settings):
    service = PipelineService(settings)
    service.create('AAPL', mode='live', run_id='one')
    with pytest.raises(ValueError, match='live workflow'):
        PipelineService(settings).create('MSFT', mode='live', run_id='two')
    assert not (settings.data_dir / 'runs/two').exists()


def test_two_years_and_unknown_ticker(settings):
    service = complete(settings, scenario='two-years')
    assert service.state('workflow').run.status == 'partial'
    _, report, _ = ReportingService(settings).latest('workflow')
    assert len(report.covered_years) == 2
    assert any('Fewer fiscal years' in text for text in report.limitations)
    service.create('UNKNOWN', mode='demo', run_id='unknown')
    result = asyncio.run(service.run('unknown'))
    assert result.status == 'failed' and 'not found' in result.limitation
    assert not ReportingService(settings).latest('unknown')[1]


def test_home_background_progress_cancel_and_cli(settings, monkeypatch):
    with TestClient(create_app(settings.model_copy(update={'demo_stage_delay': .1}))) as client:
        assert 'action="/analyze"' in client.get('/').text
        response = client.post('/analyze', content='ticker=DEMO&mode=demo&scenario=slow', follow_redirects=False)
        assert response.status_code == 303
        url = response.headers['location']
        for _ in range(300):
            state = client.get(url + '/progress').json()
            if state['run']['status'] == 'running':
                break
            time.sleep(.01)
        assert client.get(url).status_code == 200
        client.post(url + '/cancel')
        for _ in range(300):
            state = client.get(url + '/progress').json()
            if state['run']['status'] == 'cancelled':
                break
            time.sleep(.01)
        assert state['run']['status'] == 'cancelled'
        assert client.get(url + '/trace').status_code == 200
        response = client.post(url + '/resume', follow_redirects=False)
        assert response.status_code == 303
        for _ in range(30000):
            state = client.get(url + '/progress').json()
            if state['run']['stage'] == 'complete':
                break
            time.sleep(.01)
        assert state['run']['stage'] == 'complete', state['error']
        assert client.get(url + '/report').status_code == 200
        assert all('output_count' in stage and 'output_ids' not in stage for stage in state['stages'])
        assert all('output_ids' in stage for stage in client.get(url + '/progress?detail=true').json()['stages'])
    monkeypatch.setenv('PROFITLAB_DATA_DIR', str(settings.data_dir))
    runner = CliRunner()
    result = runner.invoke(app, ['analyze', 'DEMO', '--mode', 'demo', '--run-id', 'cli'])
    assert result.exit_code == 0, result.output
    assert PipelineService(settings).state('cli').run.stage == 'complete'
    assert runner.invoke(app, ['resume', 'cli']).exit_code == 0


def test_async_cancel_and_sync_drain_preserve_ownership(settings):
    service = PipelineService(settings)
    service.create('DEMO', mode='demo', run_id='drain')
    completed = []
    def bounded_write():
        time.sleep(.1)
        service.repo.put('drain', 'thread-output', b'{"completed": true}')
        completed.append(True)
    async def work():
        task = asyncio.create_task(service.sync(bounded_write))
        await asyncio.sleep(.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert completed == [True]
        entered = asyncio.Event()
        closed = asyncio.Event()
        async def remote(run_id, stage):
            entered.set()
            try:
                await asyncio.sleep(30)
            finally:
                closed.set()
        service.execute = remote
        task = asyncio.create_task(service.run('drain'))
        await entered.wait()
        service.cancel('drain')
        result = await task
        assert result.status == 'cancelled' and closed.is_set()
    asyncio.run(work())
    assert service.repo.read('drain', 'thread-output') == b'{"completed": true}'
