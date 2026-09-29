"""Session 1 architecture-map navigation contracts."""
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.canonical import canonicalize_html
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
    assert 'Pipeline overview' in overview.text
    assert 'Process summary placeholder' in overview.text
    assert 'Plain-language description placeholder.' in overview.text
    assert 'Prompt control placeholder' in overview.text
    assert 'Inspect sanitized provider trace' not in overview.text
    assert 'Canonical documents' not in overview.text
    ordered_labels = ('Source', 'Outline', 'Sections', 'Chunks', 'Evidence',
                      'Findings', 'Evaluate', 'Facts')
    positions = [overview.text.index(f'<strong>{label}</strong>') for label in ordered_labels]
    assert positions == sorted(positions)
    assert 'Evaluate is the only merge point' in overview.text
    assert 'Independent input to Evaluate' in overview.text
    assert 'pipeline-connector--facts-up' in overview.text
    assert 'Stage 1 of 8' not in overview.text
    for stage in ('source', 'outline', 'section_score', 'chunk', 'chunk_score', 'findings', 'facts', 'evaluate'):
        assert f'?stage={stage}' in overview.text

    for page in (selected, direct):
        assert page.status_code == 200
        assert 'Stage 6 of 8' in page.text
        assert 'Back to pipeline' in page.text
        assert 'stage-entry-header' in page.text
        assert '❝' in page.text
        assert '>○</span><span>Queued</span>' in page.text

    with TestClient(create_app(settings)) as client:
        for position, stage in enumerate(
                ('source', 'outline', 'section_score', 'chunk', 'chunk_score', 'findings', 'facts', 'evaluate'), 1):
            page = client.get(f'/v2/runs/map-run/pipeline?stage={stage}')
            assert page.status_code == 200
            assert f'Stage {position} of 8' in page.text
            assert 'stage-entry-header' in page.text


def test_pipeline_map_has_textual_statuses_and_accessible_vertical_paths(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='status-map-run', ticker='MAP', created_at=now, updated_at=now))

    with TestClient(create_app(settings)) as client:
        overview = client.get('/v2/runs/status-map-run/pipeline')

    assert 'aria-label="Source — Queued"' in overview.text
    assert 'class="stage-status status-queued"' in overview.text
    assert '>○</span><span>Queued</span>' in overview.text
    assert 'Evaluate is the only merge point' in overview.text
    assert 'aria-label="Facts flows upward into Evaluate"' in overview.text
    assert 'class="pipeline-card-list pipeline-card-list--vertical"' in overview.text
    stylesheet = (Path(__file__).parents[2] / 'src/profitlab/web/static/pipeline-map.css').read_text()
    assert '.pipeline-card:focus-visible' in stylesheet
    assert '.pipeline-connector--facts-up' in stylesheet
    assert '.pipeline-card-list--vertical' in stylesheet
    assert '@media (max-width: 600px)' in stylesheet


def test_source_card_uses_persisted_sec_filing_and_canonical_line_result(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='source-map-run', ticker='MAP', created_at=now, updated_at=now))
    document, visible_html = canonicalize_html(
        b'<html><body><h1>Annual report</h1><p>Visible result</p></body></html>',
        document_id='document-map-2025', filing_id='filing-map-2025')
    repo.save_canonical_document('source-map-run', document,
                                b'<html><body>source</body></html>', visible_html)
    repo.save_filing('source-map-run', 'filing-map-2025', document.ref.source_hash, {
        'filing_id': 'filing-map-2025', 'form': '10-K', 'report_date': '2025-12-31',
        'document_id': document.ref.document_id, 'source_hash': document.ref.source_hash,
    })

    with TestClient(create_app(settings)) as client:
        overview = client.get('/v2/runs/source-map-run/pipeline')

    assert 'data-source-card' in overview.text
    assert 'aria-label="SEC filing source transformation"' in overview.text
    assert '>1 · Request</small><b>SEC primary filing</b>' in overview.text
    assert '>Primary filing HTML · 10-K · report date 2025-12-31</em>' in overview.text
    assert '>2 · Convert</small><b>Visible HTML only</b>' in overview.text
    assert 'Remove hidden and Inline XBRL-only content, plus taxonomy, context, unit, scale, and format metadata.' in overview.text
    assert f'>3 · Store</small><b>{document.ref.line_count:,} canonical visible lines</b>' in overview.text
    assert 'Numbered lines retain links to their sanitized HTML anchors.' in overview.text
    source_start = overview.text.index('data-source-card')
    outline_start = overview.text.index('data-stage-card="outline"')
    source_card = overview.text[source_start:outline_start]
    assert 'Process summary placeholder' not in source_card
    assert 'Prompt control placeholder' not in source_card
    stylesheet = (Path(__file__).parents[2] / 'src/profitlab/web/static/pipeline-map.css').read_text()
    assert '.source-card-flow' in stylesheet
    assert '.pipeline-map--vertical .pipeline-card { box-sizing: border-box; block-size: 12rem; }' in stylesheet
    assert '.pipeline-map--vertical .pipeline-card { block-size: auto; }' in stylesheet


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


def test_selected_stage_header_uses_persisted_partial_or_failed_status(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='stage-state-run', ticker='STATE', created_at=now, updated_at=now))
    repo.update_stage(StageSnapshot(run_id='stage-state-run', stage='facts', position=7,
                                    status='partial', completed_work=2, total_work=3),
                      event_kind='stage_finished', event_summary='partial facts')
    repo.update_stage(StageSnapshot(run_id='stage-state-run', stage='evaluate', position=8,
                                    status='failed', error='comparison unavailable'),
                      event_kind='stage_finished', event_summary='failed evaluation')

    with TestClient(create_app(settings)) as client:
        facts = client.get('/v2/runs/stage-state-run/pipeline?stage=facts')
        evaluate = client.get('/v2/runs/stage-state-run/pipeline?stage=evaluate')

    assert '▦' in facts.text
    assert '>◐</span><span>Partial</span>' in facts.text
    assert '· 2 / 3' in facts.text
    assert '⇄' in evaluate.text
    assert '>!</span><span>Failed</span>' in evaluate.text
