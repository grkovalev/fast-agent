from datetime import UTC, datetime

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.contracts import StageSnapshot, V2Run
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_pending_zero_and_incomplete_accounting_have_distinct_rendering(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='accounting-state', ticker='ACCT',
                          created_at=now, updated_at=now))
    repo.update_stage(StageSnapshot(run_id='accounting-state', stage='chunk',
                                    position=4, status='completed',
                                    completed_work=0, total_work=0,
                                    active_seconds=.4, output_hash='a' * 64),
                      event_kind='stage_finished', event_summary='no chunks')
    repo.update_stage(StageSnapshot(run_id='accounting-state', stage='findings',
                                    position=6, status='partial',
                                    completed_work=2, total_work=3),
                      event_kind='stage_finished', event_summary='partial findings')
    repo.update_stage(StageSnapshot(run_id='accounting-state', stage='facts',
                                    position=7, status='failed',
                                    error='SEC unavailable'),
                      event_kind='stage_finished', event_summary='facts failed')
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/accounting-state/pipeline').text
        selected = client.get('/v2/runs/accounting-state/pipeline?stage=facts').text
    assert 'data-stage-progress="source"></small>' in page
    assert 'data-stage-progress="chunk">0 / 0</small>' in page
    assert 'data-stage-accounting="chunk"><p class="accounting-provenance">Persisted run accounting' in page
    assert '<dt>Stored chunks</dt><dd>0</dd>' in page
    assert 'data-stage-accounting="findings">' in page
    assert '<p>Partial persisted accounting</p>' in page
    assert 'data-stage-accounting="facts"><p>Complete accounting unavailable after failed.</p>' in page
    assert 'Current configuration and illustrative request; persisted decisions appear only after this stage saves output.' in page
    assert 'data-selected-work></span>' in selected
    assert 'Work total unavailable · failed · recorded active 0.00s' in selected
