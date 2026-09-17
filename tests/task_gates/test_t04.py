import json
import socket
from datetime import date

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from profitlab.cli import app
from profitlab.demo import DemoService
from profitlab.sec.client import RateLimiter, SECError, retry_after
from profitlab.sec.contracts import DiscoveryResult
from profitlab.sec.fixtures import FIXTURES, FixtureLimiter, fixture_transport
from profitlab.sec.service import DiscoveryService, normalize_ticker
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder
from profitlab.web.app import create_app


def settings_for(path, **overrides):
    return Settings(_env_file=None, PROFITLAB_DATA_DIR=path,
                    sec_user_agent='ProfitLab test contact@profitlab.test', **overrides)


def result_for(settings, run):
    return DiscoveryResult.model_validate_json(Repository(settings.data_dir).read(
        run.run_id, 'discovery'))


def test_offline_history_amendments_ui_and_restart(tmp_path, monkeypatch):
    monkeypatch.setenv('PROFITLAB_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))
    runner = CliRunner()
    assert runner.invoke(app, ['demo', '--through', 'T04', '--run-id', 'four']).exit_code == 0
    settings = settings_for(tmp_path)
    repo = Repository(tmp_path)
    run = repo.manifest('four')
    result = result_for(settings, run)
    assert run.covered_years == [2022, 2023, 2024, 2025]
    assert result.report_periods == [date(y, 12, 31) for y in [2025, 2024, 2023, 2022]]
    originals = [f for f in result.filings if f.form == '10-K']
    amendments = [f for f in result.filings if f.form == '10-K/A']
    assert len(originals) == 4 and len(amendments) == 1
    assert amendments[0].amendment_of == originals[0].filing_id
    assert all(f.accession_compact == f.accession.replace('-', '') for f in result.filings)
    events, _ = TraceRecorder(repo, 'four').history()
    payloads = [json.loads(repo.read('four', e.request_artifact_id)) for e in events
                if e.tool == 'SEC JSON request' and e.kind == 'start']
    assert len(payloads) == 3 and payloads[-1]['url'].endswith('submissions-001.json')
    client = TestClient(create_app(settings))
    page = client.get('/runs/four')
    for text in ['Synthetic Demo Corporation', '10-K/A', '4 distinct annual periods',
                 'Synthetic source', '2022-12-31']:
        assert text in page.text
    assert 'href="https://www.sec.gov/Archives' not in page.text
    assert runner.invoke(app, ['demo', '--through', 'T04', '--scenario', 'two-years',
                               '--run-id', 'two']).exit_code == 0
    assert repo.manifest('two').covered_years == [2024, 2025]
    assert repo.manifest('two').status == 'partial'
    assert '2 distinct annual periods' in client.get('/runs/two').text
    assert DemoService(tmp_path).get('four') == run
    assert TestClient(create_app(settings)).get('/runs/four').text == page.text
    assert runner.invoke(app, ['demo', '--run-id', 'four']).exit_code == 2
    unknown = client.post('/discover', data={'ticker': 'UNKNOWN', 'mode': 'demo'})
    assert 'not_found' in unknown.text and 'Ticker not found' in unknown.text
    timeout = client.post('/discover', data={'ticker': 'TIMEOUT', 'mode': 'demo'})
    assert 'service_error' in timeout.text and 'timeout' in timeout.text
    assert client.post('/discover', data={'ticker': '../escape'}).status_code == 400
    discovered = runner.invoke(app, ['discover', ' demo ', '--mode', 'demo', '--years', '1'])
    assert discovered.exit_code == 0 and '1 of 1' in discovered.output


@pytest.mark.parametrize('kind,code,attempts', [
    ('403', 'http_403', 1), ('429', 'retryable_http', 3), ('timeout', 'timeout', 3),
    ('malformed', 'invalid_response', 1), ('empty', 'invalid_response', 1),
])
def test_service_failure_never_not_found(tmp_path, monkeypatch, kind, code, attempts):
    monkeypatch.setattr('profitlab.sec.client.time.sleep', lambda _: None)
    settings = settings_for(tmp_path, llm_api_key='echo-secret-credential')
    calls = []

    def respond(request):
        calls.append(request)
        assert request.headers['User-Agent'] == settings.sec_user_agent
        if kind == 'timeout':
            raise httpx.ReadTimeout('echo-secret-credential', request=request)
        if kind in ('403', '429'):
            return httpx.Response(int(kind), headers={'Retry-After': '2'},
                                  text='echo-secret-credential')
        return httpx.Response(200, content=b'{bad' if kind == 'malformed' else b'{}')

    class CountingLimiter:
        count = 0

        def wait(self, deadline):
            self.count += 1

    limiter = CountingLimiter()
    run = DiscoveryService(settings, transport=httpx.MockTransport(respond),
                           limiter=limiter).create('AAPL', run_id='failed')
    result = result_for(settings, run)
    assert result.outcome == 'service_error' and result.error_code == code
    assert len(calls) == attempts == limiter.count
    events, _ = TraceRecorder(Repository(tmp_path), run.run_id).history()
    starts = [e for e in events if e.kind == 'start' and e.tool == 'SEC JSON request']
    assert [e.attempt for e in starts] == list(range(1, attempts + 1))
    assert len({e.call_id for e in starts}) == 1
    assert len([e for e in events if e.kind == 'end' and e.tool == 'SEC JSON request']) == attempts
    trace = TraceRecorder(Repository(tmp_path), run.run_id, settings.redactor())
    trace.export(tmp_path / 'export')
    for path in tmp_path.rglob('*'):
        if path.is_file():
            assert b'echo-secret-credential' not in path.read_bytes(), path


def test_cache_and_live_urls(tmp_path):
    settings = settings_for(tmp_path)
    calls = []
    fixture = fixture_transport()

    def respond(request):
        calls.append(str(request.url))
        return fixture.handle_request(request)

    service = DiscoveryService(settings, transport=httpx.MockTransport(respond),
                               limiter=FixtureLimiter())
    first = service.create('DEMO', run_id='first')
    assert len(calls) == 3
    service.create('DEMO', run_id='second')
    assert len(calls) == 3
    events, _ = TraceRecorder(Repository(tmp_path), 'second').history()
    assert len([e for e in events if e.tool == 'SEC cache hit' and e.kind == 'end']) == 3
    filing = result_for(settings, first).filings[0]
    assert filing.primary_document_url == (
        'https://www.sec.gov/Archives/edgar/data/1234567/000123456726000001/annual-2025.html')
    page = TestClient(create_app(settings)).get('/runs/first').text
    assert 'Live SEC' in page and 'SEC original' in page and 'Synthetic demo' not in page
    # A corrupted cache is refetched and is never accepted as a missing company.
    for path in (tmp_path / 'sec-cache').glob('*.json'):
        path.write_text('{truncated')
    service.create('DEMO', run_id='third')
    assert len(calls) == 6


@pytest.mark.parametrize('case,outcome', [('unknown', 'not_found'), ('ambiguous', 'ambiguous'),
                                         ('unsupported', 'unsupported')])
def test_lookup_outcomes(tmp_path, case, outcome):
    settings = settings_for(tmp_path)
    mapping = json.loads((FIXTURES / 'ticker.json').read_bytes())
    submissions = json.loads((FIXTURES / 'submissions.json').read_bytes())
    if case == 'ambiguous':
        mapping['1'] = dict(mapping['0'], cik_str=9876543)
    if case == 'unsupported':
        submissions['filings']['recent']['form'] = ['20-F'] * 4

    def respond(request):
        return httpx.Response(200, json=mapping if request.url.path.endswith(
            'company_tickers.json') else submissions)

    run = DiscoveryService(settings, transport=httpx.MockTransport(respond),
        limiter=FixtureLimiter()).create('UNKNOWN' if case == 'unknown' else 'DEMO', run_id=case)
    assert result_for(settings, run).outcome == outcome


def test_limits_contact_and_normalization(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    assert normalize_ticker(' brk.b ') == 'BRK-B'
    assert normalize_ticker('BRK-B') == 'BRK-B'
    for ticker in ['', 'A/B', '<script>', 'A B']:
        with pytest.raises(ValueError):
            normalize_ticker(ticker)
    missing = settings.model_copy(update={'sec_user_agent': ''})
    with pytest.raises(ValueError, match='SEC_USER_AGENT'):
        DiscoveryService(missing).create('AAPL')
    monkeypatch.setenv('PROFITLAB_DATA_DIR', str(tmp_path / 'doctor'))
    monkeypatch.setenv('SEC_USER_AGENT', 'ProfitLab your-email@example.com')
    assert CliRunner().invoke(app, ['doctor', '--live', 'sec']).exit_code == 2
    assert not (tmp_path / 'doctor').exists()
    assert retry_after('2') == 2 and retry_after('bad') == 0
    limiter = RateLimiter(tmp_path / 'rate.lock', 2)
    import time

    limiter.wait(time.monotonic() + 1)
    with pytest.raises(SECError, match='time limit'):
        limiter.wait(time.monotonic() + .01)


@pytest.mark.parametrize('case,code', [
    ('arrays', 'invalid_response'), ('cik', 'invalid_response'),
    ('history', 'invalid_response'), ('bytes', 'response_limit'),
    ('retry_wait', 'time_limit'), ('history_limit', 'history_limit'),
])
def test_invalid_history_and_bounded_limits(tmp_path, case, code):
    settings = settings_for(tmp_path, sec_max_response_bytes=1024 if case == 'bytes' else 20000000,
                            sec_max_history_files=1)
    submissions = json.loads((FIXTURES / 'submissions.json').read_bytes())
    arrays = submissions['filings']['recent']
    if case == 'arrays':
        arrays['form'].pop()
    elif case == 'cik':
        submissions['cik'] = '0000000001'
    elif case == 'history':
        submissions['filings']['files'] = [{'name': '../../private.json'}]
    elif case == 'history_limit':
        submissions['filings']['recent'] = {key: values[:1] for key, values in arrays.items()}
        submissions['filings']['files'] = [
            {'name': f'CIK0001234567-submissions-00{i}.json'} for i in [1, 2]]

    def respond(request):
        if case == 'retry_wait':
            return httpx.Response(429, headers={'Retry-After': '600'})
        if case == 'bytes':
            return httpx.Response(200, text='x' * 2048)
        if request.url.path.endswith('company_tickers.json'):
            return httpx.Response(200, content=(FIXTURES / 'ticker.json').read_bytes())
        if 'submissions-00' in request.url.path:
            return httpx.Response(200, json={key: [] for key in arrays})
        return httpx.Response(200, json=submissions)

    run = DiscoveryService(settings, transport=httpx.MockTransport(respond),
                           limiter=FixtureLimiter()).create('DEMO', run_id='bounded')
    result = result_for(settings, run)
    assert result.outcome == 'service_error' and result.error_code == code
    assert not result.history_complete


def test_successful_response_redaction_and_no_retry_multiplication(tmp_path, monkeypatch):
    monkeypatch.setattr('profitlab.sec.client.time.sleep', lambda _: None)
    settings = settings_for(tmp_path, typesafe_api_key='successful-echo-credential')
    fixture = fixture_transport()
    attempts = 0

    def respond(request):
        nonlocal attempts
        if request.url.path.endswith('company_tickers.json'):
            attempts += 1
            if attempts == 1:
                return httpx.Response(503, headers={'Retry-After': '0'})
            mapping = json.loads((FIXTURES / 'ticker.json').read_bytes())
            mapping['0']['title'] = 'Demo successful-echo-credential Corporation'
            return httpx.Response(200, json=mapping)
        return fixture.handle_request(request)

    run = DiscoveryService(settings, transport=httpx.MockTransport(respond),
                           limiter=FixtureLimiter()).create('DEMO', run_id='redacted')
    assert run.status == 'completed' and attempts == 2
    assert run.company.name == 'Demo [REDACTED] Corporation'
    for path in tmp_path.rglob('*'):
        if path.is_file():
            assert b'successful-echo-credential' not in path.read_bytes(), path
