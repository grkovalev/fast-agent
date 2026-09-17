import socket

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from profitlab.cli import app
from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.web.app import create_app


def test_offline_demo_and_navigation(tmp_path, monkeypatch):
    monkeypatch.setenv("PROFITLAB_DATA_DIR", str(tmp_path))
    for name in ["TYPESAFE_API_KEY", "LLM_API_KEY", "LLM_MODEL", "LLM_BASE_URL"]:
        monkeypatch.setenv(name, "")

    def forbidden(*args, **kwargs):
        pytest.fail("Demo must not use network")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    runner = CliRunner()
    result = runner.invoke(app, ["demo", "--through", "T01", "--run-id", "test-demo"])
    assert result.exit_code == 0, result.output
    assert "/runs/test-demo" in result.output
    client = TestClient(create_app(Settings(_env_file=None)))
    assert client.get("/health").status_code == 200
    home = client.get("/")
    assert 'href="/runs/test-demo"' in home.text
    page = client.get("/runs/test-demo")
    assert page.status_code == 200
    for text in ["DEMO", "Synthetic demo", "Setup complete", "Not implemented yet"]:
        assert text in page.text
    assert 'href="/"' in page.text
    assert client.get("/static/style.css").status_code == 200
    assert client.get("/runs/missing").status_code == 404
    original = (tmp_path / "runs/test-demo/summary.json").read_bytes()
    assert runner.invoke(app, ["demo", "--run-id", "test-demo"]).exit_code == 2
    assert (tmp_path / "runs/test-demo/summary.json").read_bytes() == original
    assert runner.invoke(app, ["doctor"]).exit_code == 0


@pytest.mark.parametrize("arguments", [
    ["demo", "--through", "T12", "--run-id", "future"],
    ["demo", "--run-id", "../escape"],
    ["demo"],
    ["doctor", "--live", "unknown"],
])
def test_invalid_cli_input(arguments, tmp_path, monkeypatch):
    monkeypatch.setenv("PROFITLAB_DATA_DIR", str(tmp_path))
    result = CliRunner().invoke(app, arguments)
    assert result.exit_code == 2
    assert "Error" in result.output or "error" in result.output
    assert not (tmp_path / "runs").exists()


def test_fresh_settings_and_help(tmp_path):
    settings = Settings(_env_file=None, PROFITLAB_DATA_DIR=tmp_path)
    assert TestClient(create_app(settings)).get("/").status_code == 200
    assert CliRunner().invoke(app, ["--help"]).exit_code == 0
    with pytest.raises(ValueError):
        DemoService(tmp_path).get("../invalid")
