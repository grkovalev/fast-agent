"""Session 1 architecture-map navigation contracts."""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.contracts import V2Run
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
