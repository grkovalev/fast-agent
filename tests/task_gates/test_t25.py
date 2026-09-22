"""T25 removes the superseded execution surface rather than adapting it."""
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from profitlab.cli import app
from profitlab.settings import Settings
from profitlab.web.app import create_app


def test_only_v2_commands_routes_and_modules_remain(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    help_output = CliRunner().invoke(app, ['--help']).output
    assert 'serve' in help_output
    for command in ('demo', 'discover', 'analyze', 'stage', 'inspect', 'export', 'verify'):
        assert command not in help_output

    with TestClient(create_app(settings)) as client:
        home = client.get('/')
        assert home.status_code == 200
        assert 'Historical V1 runs' not in home.text
        assert client.get('/runs/old-run').status_code == 404
        assert client.post('/analyze', data={'ticker': 'DEMO'}).status_code == 404

    root = Path(__file__).parents[2] / 'src' / 'profitlab'
    removed = ('demo.py', 'pipeline.py', 'analysis', 'documents', 'storage', 'contracts',
               'providers/extraction.py', 'providers/screening.py', 'providers/service.py')
    assert all(not (root / item).exists() for item in removed)
