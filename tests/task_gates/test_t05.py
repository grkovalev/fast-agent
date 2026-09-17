import json

import httpx
import pytest
from fastapi.testclient import TestClient

from profitlab.demo import DemoService
from profitlab.documents.parser import match_quote, parse_source
from profitlab.documents.service import SourceService
from profitlab.sec.fixtures import FixtureLimiter
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder
from profitlab.web.app import create_app


def test_source_pipeline_and_safe_viewer(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path)
    DemoService(tmp_path).create('source-test', 'T05')
    service = SourceService(settings)
    run, items = service.sources('source-test')
    assert len(items) == 5  # four originals plus separately stored amendment
    filing = items[0]['filing']
    repo = Repository(tmp_path)
    raw = repo.read(run.run_id, 'raw-' + filing.filing_id)
    assert b'<script>' in raw and b'onclick=' in raw
    blocks, cells, tables = parse_source(raw, filing.filing_id)
    assert parse_source(raw, filing.filing_id) == (blocks, cells, tables)
    assert all(b.page_label is None for b in blocks)
    assert any(b.original_anchor is None for b in blocks)
    assert any(c.column_span == 2 for c in cells)
    assert any(c.row_span == 2 for c in cells)
    edge = next(c for c in cells if c.xbrl_fact_ids == ['eps-edge'])
    assert edge.raw_text == '2.00' and len(edge.year_cell_ids) == 1
    assert next(c for c in cells if c.cell_id == edge.year_cell_ids[0]).raw_text == '2025'
    assert match_quote('Revenue\n  grew\u00a0 strongly.', 'Revenue grew strongly.') == (0, 22)
    assert match_quote('Revenue grew', 'fiction') is None
    with TestClient(create_app(settings)) as client:
        listing = client.get('/runs/source-test/sources')
        assert listing.status_code == 200 and 'Synthetic source' in listing.text
        url = f'/runs/source-test/sources/{filing.filing_id}'
        page = client.get(url, params={'cell': edge.cell_id})
        assert page.status_code == 200
        assert page.text.count('class="selected-cell') == 1
        assert 'onclick=' not in page.text and '<script>' not in page.text
        assert 'alert(' not in page.text and 'SEC original</a>' not in page.text
        assert f'id="block-{blocks[0].block_id}"' in page.text
        both = client.get(url, params={'row': edge.row_id, 'column': edge.column_id})
        assert both.status_code == 200
        assert both.text.count(' selected-row') == 3
        assert both.text.count(' selected-column') == 3
        assert client.get(url, params={'cell': 'unknown'}).status_code == 400
        assert client.get('/runs/source-test/sources/not-indexed').status_code == 404
        assert client.get('/runs/source-test/sources/%2e%2e%2f.env').status_code == 404
    service.progress(run.run_id, 'download')
    service.progress(run.run_id, 'parse')
    assert repo.read(run.run_id, 'raw-' + filing.filing_id) == raw
    assert json.loads(repo.read(run.run_id, 'source-' + filing.filing_id))['status'] == 'saved'


def live_source_run(tmp_path):
    from profitlab.sec.fixtures import fixture_transport
    from profitlab.sec.service import DiscoveryService

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='Test test@example.org')
    run = DiscoveryService(settings, transport=fixture_transport(), limiter=FixtureLimiter()).create(
        'DEMO', mode='live', run_id='download-test')
    repo = Repository(tmp_path)
    discovery = json.loads(repo.read(run.run_id, 'discovery'))
    filing = discovery['filings'][0]
    return repo, run, filing, filing['primary_document_url']



@pytest.mark.parametrize('response', [
    httpx.Response(200, headers={'content-type': 'text/html'}, content=b'<html><p>partial'),
    httpx.Response(200, headers={'content-type': 'application/pdf'}, content=b'%PDF'),
    httpx.Response(403, content=b'blocked'),
])
def test_invalid_download_not_published(tmp_path, response):
    from profitlab.sec.client import SECClient, SECError

    repo, run, _filing, url = live_source_run(tmp_path)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='Test test@example.org')
    client = SECClient(settings, TraceRecorder(repo, run.run_id),
        transport=httpx.MockTransport(lambda request: response), limiter=FixtureLimiter())
    cached_before = {p.name: p.read_bytes() for p in (tmp_path / 'sec-cache').glob('*')}
    try:
        with pytest.raises(SECError):
            client.get(url, bytes, stage='download', document=True)
        assert {p.name: p.read_bytes() for p in (tmp_path / 'sec-cache').glob('*')} == cached_before
    finally:
        client.close()


def test_download_retry_and_exact_bytes(tmp_path, monkeypatch):
    from profitlab.sec.client import SECClient, SECError

    repo, run, _filing, url = live_source_run(tmp_path)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='Test test@example.org')
    raw = b'<html><body><p>Exact annual source 2.00</p></body></html>'
    attempts = []
    def respond(request):
        attempts.append(request)
        if len(attempts) == 1:
            raise httpx.ReadError('partial stream disconnected', request=request)
        return httpx.Response(200, headers={'content-type': 'text/html'}, content=raw)
    monkeypatch.setattr('profitlab.sec.client.time.sleep', lambda seconds: None)
    client = SECClient(settings, TraceRecorder(repo, run.run_id),
        transport=httpx.MockTransport(respond), limiter=FixtureLimiter())
    try:
        assert client.get(url, bytes, stage='download', document=True)[0] == raw
        assert len(attempts) == 2
        with pytest.raises(SECError):
            client.get('https://evil.test/annual.html', bytes, stage='download', document=True)
    finally:
        client.close()


def test_live_service_persistence_and_byte_limit(tmp_path):
    repo, run, filing, url = live_source_run(tmp_path)
    raw = b'<html><body><h1>Annual</h1><p>Net income 180</p></body></html>'
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='Test test@example.org')
    requests = []
    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200, headers={'content-type': 'text/html'}, content=raw)
    service = SourceService(settings, transport=httpx.MockTransport(respond), limiter=FixtureLimiter())
    service.progress(run.run_id, 'download', filing['filing_id'])
    service.progress(run.run_id, 'parse', filing['filing_id'])
    assert repo.manifest(run.run_id).stage == 'parse'
    assert repo.read(run.run_id, 'raw-' + filing['filing_id']) == raw
    service.progress(run.run_id, 'download', filing['filing_id'])
    assert requests == [url]
    with TestClient(create_app(settings)) as client:
        assert 'SEC original' in client.get(
            f"/runs/{run.run_id}/sources/{filing['filing_id']}").text
    other = json.loads(repo.read(run.run_id, 'discovery'))['filings'][1]
    limited = SourceService(settings.model_copy(update={'sec_max_response_bytes': 10}),
        transport=httpx.MockTransport(respond), limiter=FixtureLimiter())
    with pytest.raises(ValueError, match='byte limit'):
        limited.progress(run.run_id, 'download', other['filing_id'])
    with pytest.raises(FileNotFoundError):
        repo.read(run.run_id, 'source-' + other['filing_id'])

    _, items = service.sources(run.run_id)
    failed = next(i for i in items if i['filing'].filing_id == other['filing_id'])
    assert failed['metadata'] is None and failed['error']['status'] == 'failed'


def test_parser_unreadable_and_extreme_spans():
    with pytest.raises(ValueError, match='readable HTML'):
        parse_source(b'', 'filing-test')
    with pytest.raises(ValueError, match='span expansion limit'):
        parse_source(b'<html><table><tr><td rowspan="1000" colspan="1000">1</td></tr></table></html>', 'filing-test')
    blocks, _, _ = parse_source(b'<html><div><span>Annual source prose</span></div></html>', 'filing-test')
    assert blocks[0].text == 'Annual source prose'
