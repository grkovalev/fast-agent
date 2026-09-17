"""Report agent uses actual framework tools/repairs with no paid test calls."""
import asyncio
import json
import socket

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from typer.testing import CliRunner

from profitlab.analysis.calculations import CalculationService
from profitlab.analysis.reporting import ReportingService, fixture_model
from profitlab.cli import app
from profitlab.contracts.reports import ReportSentence
from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.trace import TraceRecorder
from profitlab.web.app import create_app


@pytest.fixture(scope='module')
def setup(tmp_path_factory):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path_factory.mktemp('reports'), _env_file=None)
    original = socket.socket.connect
    def forbidden(*args, **kwargs):
        raise AssertionError('Offline report tests may not use network')
    socket.socket.connect = forbidden
    try:
        DemoService(settings.data_dir).create('report-demo', 'T12')
    finally:
        socket.socket.connect = original
    return settings, ReportingService(settings)


def test_actual_framework_tools_repair_persistence_and_ui(setup, monkeypatch):
    settings, service = setup
    monkeypatch.setenv('PROFITLAB_DATA_DIR', str(settings.data_dir))
    index, report, rendered = service.latest('report-demo')
    assert index['model_narrative'] and not index['failure']
    assert report.validation_status == 'valid'
    assert any('25.00%' in text for text in rendered.values())
    events, _ = TraceRecorder(service.repo, 'report-demo').history()
    assert any(e.kind == 'structured_repair' and e.stage == 'write' for e in events)
    calls = [e for e in events if e.actor == 'agent_tool' and e.stage == 'write']
    assert calls and any(e.call_id == 'writer-read' for e in calls)
    histories = [json.loads(service.repo.read('report-demo', e.result_artifact_id)) for e in events if e.kind == 'conversation' and e.stage == 'write']
    native = json.dumps(histories[-1])
    assert 'get_evidence' in native and 'retry-prompt' in native and 'tool-return' in native
    assert histories[-1]['synthetic'] is True
    checks = service.verify('report-demo')
    assert checks['mechanical_integrity'] == 'passed' and checks['rendered_matches']
    assert CliRunner().invoke(app, ['verify', 'report-demo']).exit_code == 0
    with TestClient(create_app(settings)) as client:
        page = client.get('/runs/report-demo/report')
        assert page.status_code == 200
        assert 'Validated model narrative' in page.text and 'Fake provider' in page.text
        assert 'Source drawer' in page.text and 'Management explanation' in page.text
        assert '25.00%' in page.text and '/calculations#calc-' in page.text
        assert '/candidates#candidate-' in page.text
        assert client.get('/runs/report-demo/checks').status_code == 200
        assert 'no model calls in this run' not in client.get('/runs/report-demo/trace').text


@pytest.mark.parametrize('defect', ['raw', 'fake-id', 'unselected', 'quote', 'coverage', 'summary', 'unavailable', 'coverage-bypass', 'misattribution'])
def test_validation_rejects_untrusted_output(setup, defect):
    _, service = setup
    deps = service.inputs('report-demo')
    base = deps.base_report()
    if defect == 'raw':
        extra = ReportSentence(sentence_id='bad', kind='comparison', text='EPS rose 99%.', fact_ids=[next(iter(deps.facts))], attribution='comparison')
        base = base.model_copy(update={'sentences': base.sentences + [extra]})
    elif defect == 'fake-id':
        extra = ReportSentence(sentence_id='bad', kind='interpretation', text='Invented source.', evidence_ids=['other-run-evidence'], attribution='Analyst interpretation')
        base = base.model_copy(update={'sentences': base.sentences + [extra], 'source_index': ['other-run-evidence']})
    elif defect == 'unselected':
        base = base.model_copy(update={'table_fact_ids': ['unknown-candidate']})
    elif defect == 'quote':
        eid = deps.passages[0]['evidence_ids'][0]
        extra = ReportSentence(sentence_id='bad', kind='management_explanation', text='Management said something else.', evidence_ids=[eid], attribution='Management explanation')
        base = base.model_copy(update={'sentences': base.sentences + [extra], 'source_index': [eid]})
    elif defect == 'misattribution':
        deps.passages = [{**p, 'attribution': 'Source passage; attribution not established'} for p in deps.passages]
        passage = deps.passages[0]
        extra = ReportSentence(sentence_id='bad', kind='management_explanation', text=passage['quote'], evidence_ids=passage['evidence_ids'], attribution='Management explanation')
        base = base.model_copy(update={'sentences': base.sentences + [extra], 'source_index': passage['evidence_ids']})
    elif defect == 'coverage':
        base = base.model_copy(update={'covered_years': [2025]})
    elif defect == 'summary':
        base = base.model_copy(update={'summary': 'EPS rose 999%.'})
    elif defect == 'coverage-bypass':
        extra = ReportSentence(sentence_id='bad', kind='coverage', text='EPS rose 999%.', attribution='coverage')
        base = base.model_copy(update={'sentences': base.sentences + [extra]})
    else:
        cid = next(iter(deps.calculations))
        extra = ReportSentence(sentence_id='bad', kind='comparison', text='Change {{calc:' + cid + ':invented_result}}.', calculation_ids=[cid], attribution='comparison')
        base = base.model_copy(update={'sentences': base.sentences + [extra]})
    with pytest.raises(ValueError):
        deps.validate(base)


def test_tool_ownership_budgets_and_fallback(setup):
    _, service = setup
    deps = service.inputs('report-demo')
    assert deps.read('evidence', ['another-run-id'])[0]['status'] == 'missing'
    from pydantic_ai import ModelRetry
    with pytest.raises(ModelRetry):
        deps.read('evidence', ['unknown'] * 9)
    old_index, old_report, _ = service.latest('report-demo')
    result = asyncio.run(service.write('report-demo', fixture_model(deps, fail=True)))
    index, report, _ = service.latest('report-demo')
    assert result.status == 'partial' and report.validation_status == 'partial'
    assert not index['model_narrative'] and index['failure']
    assert all(s.kind == 'coverage' for s in report.sentences)
    assert service.repo.read('report-demo', old_report.report_id)
    assert service.verify('report-demo')['model_narrative'] is False
    assert old_index['report_id'] != index['report_id']


def test_interrupted_writer_keeps_partial_history(setup):
    _, service = setup
    counter = 0
    def interrupted(messages, info):
        nonlocal counter
        counter += 1
        if counter > 1:
            raise asyncio.CancelledError()
        return ModelResponse(parts=[ToolCallPart('get_coverage', {}, tool_call_id='interrupt-read')])
    before = service.latest('report-demo')[0]['report_id']
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service.write('report-demo', FunctionModel(interrupted)))
    assert service.latest('report-demo')[0]['report_id'] == before
    events, _ = TraceRecorder(service.repo, 'report-demo').history()
    histories = [e for e in events if e.kind == 'conversation' and e.stage == 'write']
    payload = json.loads(service.repo.read('report-demo', histories[-1].result_artifact_id))
    assert 'interrupt-read' in json.dumps(payload) and 'tool-return' in json.dumps(payload)


def test_stale_report_hidden_after_calculation(setup):
    settings, service = setup
    CalculationService(settings).progress('report-demo')
    assert service.latest('report-demo') == (None, None, {})
    with pytest.raises(ValueError, match='No current report'):
        service.verify('report-demo')


def test_storage_connections_close_after_transactions(tmp_path):
    import sqlite3

    from profitlab.storage import Repository

    repo = Repository(tmp_path)
    with repo.connect() as db:
        assert db.execute('SELECT 1').fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        db.execute('SELECT 1')
    with pytest.raises(RuntimeError), repo.connect() as failed:
        raise RuntimeError('rollback')
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        failed.execute('SELECT 1')


def test_incomplete_coverage_and_real_cross_run_id(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('No network'))
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    DemoService(tmp_path).create('two-years-report', 'T12', 'two-years')
    service = ReportingService(settings)
    index, report, rendered = service.latest('two-years-report')
    assert index['model_narrative']
    assert report.covered_years == [2024, 2025]
    assert 'Requested years: 4' in rendered['coverage']
    assert 'Fewer fiscal years are available than requested.' in report.limitations
    DemoService(tmp_path).create('another-report', 'T11', 'two-years')
    first = service.inputs('two-years-report')
    second = service.inputs('another-report')
    other_eid = next(iter(second.evidence))
    assert other_eid not in first.evidence
    assert first.read('evidence', [other_eid])[0]['status'] == 'missing'
    with TestClient(create_app(settings)) as client:
        page = client.get('/runs/two-years-report/report')
        assert page.status_code == 200 and 'Fewer fiscal years' in page.text
