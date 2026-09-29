"""Session 1 architecture-map navigation contracts."""
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.contracts import StageSnapshot, V2Run
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_pipeline_default_is_map_only_and_each_stage_enters_its_existing_page(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='map-run', ticker='MAP', created_at=now, updated_at=now))

    with TestClient(create_app(settings)) as client:
        overview = client.get('/v2/runs/map-run/pipeline')
        selected = client.get('/v2/runs/map-run/pipeline?stage=findings')
        direct = client.get('/v2/runs/map-run/pipeline/findings')

    assert overview.status_code == 200
    assert 'Architecture overview' in overview.text
    assert 'Visible filing' in overview.text
    assert 'SEC data' in overview.text
    assert 'Findings + Facts' in overview.text
    assert 'Stage 1 of 8' not in overview.text
    assert 'Canonical documents' not in overview.text
    for stage in ('source', 'outline', 'section_score', 'chunk', 'chunk_score', 'findings', 'facts', 'evaluate'):
        assert f'?stage={stage}' in overview.text

    for page in (selected, direct):
        assert page.status_code == 200
        assert 'Stage 6 of 8' in page.text
        assert 'Back to pipeline' in page.text


def test_pipeline_map_has_textual_statuses_and_responsive_directional_paths(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='status-map-run', ticker='MAP', created_at=now, updated_at=now))

    with TestClient(create_app(settings)) as client:
        overview = client.get('/v2/runs/status-map-run/pipeline')

    assert 'aria-label="Source — Queued"' in overview.text
    assert 'class="stage-status status-queued"' in overview.text
    assert '>○</span><span>Queued</span>' in overview.text
    assert 'Findings + Facts meet only here' in overview.text
    stylesheet = (Path(__file__).parents[2] / 'src/profitlab/web/static/pipeline-map.css').read_text()
    assert '.pipeline-card:focus-visible' in stylesheet
    assert '.pipeline-connector--facts' in stylesheet
    assert '@media (max-width: 600px)' in stylesheet


def test_pipeline_map_exposes_persisted_progress_and_live_update_contract(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='live-map-run', ticker='LIVE', status='running',
                          created_at=now, updated_at=now, selected_stage='section_score'))
    with TestClient(create_app(settings)) as client:
        # Startup recovery deliberately interrupts stale work, so model the live
        # event after the app is accepting requests.
        repo.update_stage(StageSnapshot(run_id='live-map-run', stage='source', position=1,
                                        status='completed', active_seconds=1.2),
                          event_kind='stage_finished', event_summary='done')
        repo.update_stage(StageSnapshot(run_id='live-map-run', stage='section_score', position=3,
                                        status='running', completed_work=31, total_work=43,
                                        started_at=now, active_seconds=.5),
                          event_kind='stage_started', event_summary='scoring')
        overview = client.get('/v2/runs/live-map-run/pipeline')
        state = client.get('/v2/runs/live-map-run/state')

    assert '1 of 8 stages complete' in overview.text
    assert 'Current: <span data-current-stage>Sections</span>' in overview.text
    assert '31 / 43' in overview.text
    assert 'data-stage-card="section_score"' in overview.text
    assert 'aria-current="step"' in overview.text
    assert '1.2s' in overview.text
    assert state.json()['stages'][2]['total_work'] == 43
    script = (Path(__file__).parents[2] / 'src/profitlab/web/static/v2-progress.js').read_text()
    assert 'new EventSource' in script
    assert 'setInterval' in script
    assert 'data-stage-progress' in script
    assert 'stopLiveUpdates' in script
