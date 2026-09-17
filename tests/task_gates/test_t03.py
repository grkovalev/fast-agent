import asyncio
import json
import socket
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from profitlab.cli import app
from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.trace import Redactor, TraceRecorder
from profitlab.web.app import create_app


def test_demo_view_filters_payload_and_export(tmp_path, monkeypatch):
    monkeypatch.setenv('PROFITLAB_DATA_DIR', str(tmp_path / 'data'))
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))
    runner = CliRunner()
    result = runner.invoke(app, ['demo', '--through', 'T03', '--run-id', 'trace-demo'])
    assert result.exit_code == 0, result.output
    settings = Settings(_env_file=None)
    client = TestClient(create_app(settings))
    page = client.get('/runs/trace-demo/trace')
    assert page.status_code == 200
    assert 'Synthetic demo' in page.text
    assert 'no model calls' in page.text
    assert 'Full request JSON' in page.text
    events = client.get('/runs/trace-demo/trace/events').json()['events']
    assert {'failed', 'interrupted', 'completed', 'running'} <= {e['status'] for e in events}
    assert {'cache_hit', 'retry'} <= {e['kind'] for e in events}
    failed = next(e for e in events if e['status'] == 'failed')
    retry = next(e for e in events if e['kind'] == 'start' and e['attempt'] == 2)
    assert failed['call_id'] == retry['call_id']
    root = events[0]['span_id']
    assert retry['parent_id'] == root
    payload_id = next(e['result_artifact_id'] for e in events if e['tool'] == 'fixture read'
                      and e['kind'] == 'end')
    payload = client.get(f'/runs/trace-demo/trace/payloads/{payload_id}')
    assert len(payload.json()['text']) > 40000
    assert client.get('/runs/trace-demo/trace/payloads/manifest').status_code == 404
    filtered = client.get('/runs/trace-demo/trace/events?error_only=1').json()['events']
    assert len(filtered) == 2
    assert not client.get('/runs/trace-demo/trace/events?actor=agent_tool').json()['events']
    assert client.get('/runs/trace-demo/trace/events?q=retry%20example').json()['events']
    assert not client.get('/runs/trace-demo/trace/events?after_sequence=999').json()['events']
    restarted = TestClient(create_app(settings))
    assert restarted.get('/runs/trace-demo/trace/events').json()['events'] == events
    output = tmp_path / 'export'
    exported = runner.invoke(app, ['export', 'trace-demo', '--output', str(output)])
    assert exported.exit_code == 0, exported.output
    assert json.loads((output / 'trace.json').read_text())['events'] == events
    assert json.loads((output / 'payloads' / f'{payload_id}.json').read_text()) == payload.json()
    assert runner.invoke(app, ['export', 'trace-demo', '--output', str(output)]).exit_code == 2


def test_concurrent_journal_recovery_and_cancellation(tmp_path):
    DemoService(tmp_path).create('concurrent', 'T02')

    def write(index):
        trace = TraceRecorder(Repository(tmp_path), 'concurrent')
        with trace.operation('worker', {'index': index}) as result:
            with trace.operation('child'):
                pass
            result['index'] = index

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(20)))
    trace = TraceRecorder(Repository(tmp_path), 'concurrent')
    events, warnings = trace.history()
    assert not warnings
    assert [e.sequence for e in events] == list(range(1, 81))
    starts = {e.span_id: e for e in events if e.kind == 'start'}
    assert len(starts) == 40
    for event in events:
        if event.kind == 'end':
            assert starts[event.span_id].call_id == event.call_id
        if event.tool == 'child':
            assert starts[event.parent_id].tool == 'worker'
    trace.emit(kind='start', span_id='crashed', call_id='crashed-call', status='running')
    with trace.path.open('ab') as stream:
        stream.write(b'{"sequence":82')
    restarted = TraceRecorder(Repository(tmp_path), 'concurrent')
    assert len(restarted.history()[0]) == 81
    assert restarted.history()[1]
    with TestClient(create_app(Settings(_env_file=None, PROFITLAB_DATA_DIR=tmp_path))):
        pass  # Server startup reconciles spans left open by a stopped process.
    events, warnings = restarted.history()
    assert len(events) == 82 and warnings
    assert events[-1].status == 'interrupted'
    assert events[-1].span_id == 'crashed' and events[-1].call_id == 'crashed-call'
    restarted.recover_interrupted()
    assert len(restarted.history()[0]) == 82
    with pytest.raises(asyncio.CancelledError), restarted.operation('cancelled'):
        raise asyncio.CancelledError('cancelled')
    assert restarted.history()[0][-1].status == 'interrupted'


def test_redaction_all_persisted_exported_and_ui_data(tmp_path):
    DemoService(tmp_path).create('redaction', 'T02')
    secret = 'configured-test-credential-123'
    redactor = Redactor([secret])
    trace = TraceRecorder(Repository(tmp_path), 'redaction', redactor)
    with pytest.raises(RuntimeError), trace.operation('request ' + secret, {
        'Authorization': 'Bearer header-credential',
        'headers': {'Cookie': 'session=cookie-credential'},
        'api_key': 'other-api-credential',
        'url': 'https://url-user:url-password@example.com/?token=query-credential',
        'echo': secret, 'financial': '1.00 USD',
    }):
        raise RuntimeError('echoed ' + secret)
    with trace.operation('large result') as result:
        result['text'] = '<script>alert(1)</script>' + secret + 'x' * 50000
    trace.export(tmp_path / 'export')
    forbidden = [secret, 'header-credential', 'cookie-credential', 'other-api-credential',
                 'url-user', 'url-password', 'query-credential']
    for path in tmp_path.rglob('*'):
        if path.is_file():
            assert all(value.encode() not in path.read_bytes() for value in forbidden), path
    client = TestClient(create_app(Settings(_env_file=None, PROFITLAB_DATA_DIR=tmp_path)))
    page = client.get('/runs/redaction/trace').text
    assert all(value not in page for value in forbidden)
    assert '<script>alert(1)</script>' not in page
    event = trace.history()[0][-1]
    viewer = client.get(f'/runs/redaction/artifacts/{event.result_artifact_id}').text
    assert '&lt;script&gt;' in viewer
    assert '1.00 USD' in Repository(tmp_path).read(
        'redaction', trace.history()[0][0].request_artifact_id).decode()
