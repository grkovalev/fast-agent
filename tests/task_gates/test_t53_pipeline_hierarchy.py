"""T53 route hierarchy and cross-stage relationship contract."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.contracts import V2Run
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_route_locator_and_distinct_data_and_completion_paths(tmp_path):
    V2Repository(tmp_path).create_run(
        V2Run(run_id='hierarchy-run', ticker='MAP', created_at=datetime.now(UTC),
              updated_at=datetime.now(UTC))
    )
    with TestClient(create_app(Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None))) as client:
        page = client.get('/v2/runs/hierarchy-run/pipeline')
        facts_page = client.get('/v2/runs/hierarchy-run/pipeline?stage=facts')

    assert page.status_code == 200
    assert facts_page.status_code == 200
    assert 'Back to pipeline' in facts_page.text
    html = page.text
    locator = html.split('<nav class="pipeline-route-locator"', 1)[1].split('</nav>', 1)[0]
    for stage in ('source', 'outline', 'section_score', 'chunk', 'chunk_score',
                  'findings', 'facts', 'evaluate'):
        assert locator.count(f'?stage={stage}"') == 1
    assert locator.count('<li ') == 8
    assert html.count('class="pipeline-relationship"') == 1
    assert html.count('class="pipeline-merge-note"') == 1
    assert 'Completion gate to Facts' in html
    assert 'Filing identity selects the SEC dataset' in html
    assert 'Independent input to Evaluate: normalized SEC facts' in html
    assert 'pipeline-semantic--output' in html
    assert 'pipeline-semantic--gate' in html
    assert 'pipeline-semantic--artifact' in html
    assert html.index('Completion gate to Facts') < html.index('data-evaluate-card')
    assert html.index('data-evaluate-card') < html.index('data-facts-card')
    assert 'pipeline-connector--facts-up' in html
