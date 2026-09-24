"""V2 contracts, isolated persistence, and eight-stage shell acceptance."""
import asyncio
import json
import socket
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import STAGE_NAMES, V2PipelineService
from profitlab.v2.contracts import Finding, SourceRange
from profitlab.web.app import create_app


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect',
                        lambda *a, **k: pytest.fail('T14 shell must not use network'))
    return Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)


def test_contracts_and_fresh_v2_storage(settings):
    source_range = SourceRange(document_id='doc', source_hash='a' * 64,
                               start_line=2, end_line=4)
    finding = Finding(finding_id='finding', exact_quote='Net income was $1.00.',
                      source_range=source_range, amount=Decimal('1.00'),
                      validation_state='validated')
    assert json.loads(finding.model_dump_json())['amount'] == '1.00'
    with pytest.raises(ValueError):
        SourceRange(document_id='doc', source_hash='a' * 64, start_line=4, end_line=2)

    service = V2PipelineService(settings)
    service.create(run_id='fresh')
    state = service.repo.state('fresh')
    assert tuple(stage.stage for stage in state['stages']) == STAGE_NAMES
    assert not (settings.data_dir / 'index.sqlite3').exists()
    with service.repo.connect() as db:
        tables = {row['name'] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'runs', 'stages', 'events', 'filings', 'outline_sections', 'scores', 'chunks',
            'chunk_ranges', 'findings', 'structured_facts', 'comparisons'} <= tables


def test_offline_shell_persists_before_events_and_ui(settings, monkeypatch):
    service = V2PipelineService(settings)
    service.create(run_id='shell')
    result = asyncio.run(service.run('shell'))
    assert result.status == 'partial'
    stages = service.repo.stages('shell')
    assert all(stage.status == 'partial' and stage.limitation for stage in stages)
    events = service.repo.events('shell')
    for event in events:
        if event.stage and event.kind == 'stage_finished':
            assert service.repo.stage('shell', event.stage).status == event.status

    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/shell?stage=chunk_score')
        assert page.status_code == 200
        assert 'aria-current="step"' in page.text
        assert 'Chunk Score' in page.text and 'Saved artifacts' not in page.text
        assert len(client.get('/v2/runs/shell/state').json()['stages']) == 8
        streamed = client.get('/v2/runs/shell/events?after=0')
        assert streamed.status_code == 200 and 'event: pipeline' in streamed.text

def test_durable_cancellation_and_restart_recovery(settings):
    service = V2PipelineService(settings)
    service.create(run_id='cancelled')
    service.cancel('cancelled')
    with pytest.raises(ValueError, match='cancelled'):
        asyncio.run(service.run('cancelled'))
    assert service.repo.get_run('cancelled').cancellation_requested

    service.create(run_id='restart')
    service.repo.update_run('restart', status='running', summary='active', kind='stage_started')
    source = service.repo.stage('restart', 'source').model_copy(update={'status': 'running'})
    service.repo.update_stage(source, event_kind='stage_started', event_summary='active')
    V2PipelineService(settings).recover()
    assert service.repo.get_run('restart').status == 'interrupted'
    assert service.repo.stage('restart', 'source').status == 'interrupted'


def test_resume_recovers_only_a_queued_run_with_a_stopped_stage(settings):
    service = V2PipelineService(settings)
    service.create(run_id='fresh-queued')
    with pytest.raises(ValueError, match='stopped'):
        service.resume('fresh-queued')

    service.create(run_id='queued-after-failure')
    failed = service.repo.stage('queued-after-failure', 'findings').model_copy(update={
        'status': 'failed', 'summary': 'bounded provider payload rejected',
    })
    service.repo.update_stage(failed, event_kind='stage_finished', event_summary=failed.summary)
    # This represents the persisted state from an interrupted dispatch request.
    service.resume('queued-after-failure')
    assert service.repo.get_run('queued-after-failure').status == 'queued'
