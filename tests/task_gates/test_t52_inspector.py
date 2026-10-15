from datetime import UTC, datetime
from html.parser import HTMLParser

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.contracts import V2Run
from profitlab.v2.source_service import V2SourceService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.stations = []
        self.templates = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if 'id' in values:
            self.ids.append(values['id'])
        if (values.get('role') == 'button' or tag == 'button') and any(
                key.endswith('-station') for key in values):
            self.stations.append(values)
        if tag == 'template' and 'data-station-template' in values:
            self.templates.append(values['data-station-template'])


def test_overview_renders_shared_inspection_from_service_without_javascript(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='inspector-run', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    original = V2SourceService.inspection_view

    def changed(**kwargs):
        view = original(**kwargs)
        view['request']['new_runtime_field'] = {'nested': ['from source service']}
        return view

    monkeypatch.setattr(V2SourceService, 'inspection_view', changed)
    with TestClient(create_app(settings)) as client:
        response = client.get('/v2/runs/inspector-run/pipeline')
    assert response.status_code == 200
    markup = Markup()
    markup.feed(response.text)
    assert len(markup.ids) == len(set(markup.ids))
    assert len(markup.stations) == 32
    assert all((station.get('tabindex') == '0' or station.get('type') == 'button')
               and station.get('aria-controls')
               and station.get('aria-label') for station in markup.stations)
    assert len(markup.templates) == 24
    assert 'New Runtime Field' in response.text
    assert 'from source service' in response.text
    assert 'data-station-card' in response.text
    assert '/static/pipeline-inspector.js' in response.text
    assert '/static/source-loop.js' not in response.text
