"""Assembled pipeline inspection follows runtime contracts and request builders."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pydantic import Field, create_model

from profitlab.settings import Settings
from profitlab.v2.contracts import TextChunk, V2Run
from profitlab.v2.inspection import STAGE_CONTRACTS
from profitlab.v2.outline_service import OutlineService
from profitlab.v2.section_scoring import TARGETS
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_runtime_field_and_constraint_reach_selected_route(tmp_path, monkeypatch):
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='t60-contract', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    extended = create_model('ExtendedTextChunk',
                            audit_marker=(int | None, Field(default=None, ge=7)),
                            __base__=TextChunk)
    monkeypatch.setitem(STAGE_CONTRACTS, 'chunk', (*STAGE_CONTRACTS['chunk'], extended))

    with TestClient(create_app(Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None))) as client:
        page = client.get('/v2/runs/t60-contract/pipeline?stage=chunk')

    assert page.status_code == 200
    assert 'ExtendedTextChunk · runtime schema' in page.text
    assert '"audit_marker"' in page.text
    assert '"minimum": 7' in page.text
    assert 'Persisted instance unavailable on this page.' in page.text


def test_shared_prompt_and_question_changes_reach_overview(tmp_path, monkeypatch):
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='t60-builders', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    original = OutlineService._prompt_template()
    prompt_marker = 'T60 visible navigation instruction.'
    question_marker = 'T60 visible annual profit question?'
    monkeypatch.setattr(OutlineService, '_prompt_template',
                        staticmethod(lambda: original + '\n' + prompt_marker))
    monkeypatch.setitem(TARGETS, 'annual_profit', question_marker)

    with TestClient(create_app(Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None))) as client:
        page = client.get('/v2/runs/t60-builders/pipeline')

    assert page.status_code == 200
    assert prompt_marker in page.text
    assert question_marker in page.text
    assert 'illustrative request built with current configuration' in page.text
