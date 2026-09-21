"""T15 canonical visible source contracts and integration path."""
import asyncio

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService, canonicalize_html
from profitlab.v2.contracts import SourceRange
from profitlab.web.app import create_app


def test_canonical_visible_html_unwraps_xbrl_and_resolves_exact_anchors():
    raw = b'''<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"><body>
    <h1>Annual Results</h1><p>Profit was <ix:nonFraction contextRef="c1" unitRef="USD"
    decimals="-6" name="us-gaap:NetIncomeLoss">$10 million</ix:nonFraction>.</p>
    <ix:hidden><ix:nonNumeric name="dei:EntityRegistrantName">SECRET</ix:nonNumeric></ix:hidden>
    <table><tr><th>Year</th><th>Income</th></tr><tr><td>2025</td><td>10</td></tr></table></body></html>'''
    document, visible = canonicalize_html(raw, document_id='document-fixture', filing_id='filing-fixture')
    assert [line.text for line in document.lines] == [
        'Annual Results', 'Profit was $10 million.', 'Year Income', '2025 10']
    assert [line.element_type for line in document.lines] == [
        'heading', 'paragraph', 'table_row', 'table_row']
    range_ = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                         start_line=2, end_line=2, start_character=11, end_character=22)
    assert document.slice(range_) == '$10 million'
    assert document.anchor_for(range_).startswith('v2-line-2-')
    assert b'contextRef' not in visible and b'us-gaap:' not in visible and b'SECRET' not in visible
    altered, _ = canonicalize_html(raw.replace(b'$10', b'$11'), document_id='document-fixture',
                                   filing_id='filing-fixture')
    assert altered.ref.source_hash != document.ref.source_hash


def test_offline_source_stage_and_paginated_viewer(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    service = V2PipelineService(settings)
    service.create(run_id='t15-source')
    run = asyncio.run(service.run('t15-source', implement_source=True))
    assert run.status == 'partial'
    source = service.repo.stage('t15-source', 'source')
    assert source.status == 'completed' and source.output_hash
    ref = service.repo.canonical_refs('t15-source')[0]
    canonical = service.repo.canonical_document('t15-source', ref.document_id)
    assert canonical.slice(SourceRange(document_id=ref.document_id, source_hash=ref.source_hash,
                                       start_line=1, end_line=min(2, ref.line_count)))
    payload = canonical.model_dump_json()
    assert all(value not in payload for value in ('us-gaap:', 'contextRef', 'unitRef', 'scale='))

    with TestClient(create_app(settings)) as client:
        created = client.post('/v2/runs', data={'ticker': 'DEMO', 'mode': 'offline'},
                              follow_redirects=False)
        assert created.status_code == 303 and created.headers['location'].startswith('/v2/runs/')
        page = client.get(f'/v2/runs/t15-source/source?document={ref.document_id}')
        assert page.status_code == 200
        assert 'Canonical visible source' in page.text and 'Open sanitized filing HTML' in page.text
        html_page = client.get(f'/v2/runs/t15-source/source/{ref.document_id}/html')
        assert html_page.status_code == 200
        assert canonical.lines[0].html_anchor in html_page.text
