"""T34 live-SEC-only V2 entrypoint and retained source contracts."""
import pytest
from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.canonical import canonicalize_html
from profitlab.v2.contracts import SourceRange
from profitlab.v2.pipeline import V2PipelineService
from profitlab.web.app import create_app


def test_live_run_requires_ticker_and_sec_contact_before_persistence(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    pipeline = V2PipelineService(settings)

    with pytest.raises(ValueError, match='SEC_USER_AGENT'):
        pipeline.create('MSFT')
    assert pipeline.repo.recent() == []

    ready = Settings(PROFITLAB_DATA_DIR=tmp_path / 'ready', SEC_USER_AGENT='ProfitLab test@profitlab.test',
                     _env_file=None)
    run = V2PipelineService(ready).create('msft', run_id='live-msft')
    assert run.ticker == 'MSFT'
    assert 'mode' not in run.model_dump()


def test_home_offers_only_live_sec_ticker_workflow_and_explains_missing_contact(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    with TestClient(create_app(settings)) as client:
        page = client.get('/')
        created = client.post('/v2/runs', data={'ticker': 'MSFT'})

    assert page.status_code == 200
    assert 'Live SEC source retrieval' in page.text
    assert 'name="mode"' not in page.text
    assert 'Offline' not in page.text
    assert created.status_code == 400
    assert 'SEC_USER_AGENT is required' in created.text


def test_canonical_source_contract_remains_independent_of_source_mode():
    document, visible = canonicalize_html(
        b'<html><body><div>Additional visible caption</div><h1>Results</h1>'
        b'<p>Net income was <ix:nonfraction contextRef="x">$10</ix:nonfraction>.</p>'
        b'<ul><li>List entry</li></ul><table><caption>Table caption</caption>'
        b'<tr><td>Row</td><td>12</td></tr></table><ix:hidden>Hidden value</ix:hidden></body></html>',
        document_id='document-real-contract', filing_id='filing-real-contract')
    assert document.ref.line_count == 5
    assert [line.element_type for line in document.lines] == [
        'heading', 'paragraph', 'list_item', 'caption', 'table_row']
    assert 'Additional visible caption' not in '\n'.join(line.text for line in document.lines)
    assert b'Additional visible caption' in visible
    assert b'Hidden value' not in visible
    assert b'contextRef' not in visible
    assert b'ix:nonfraction' not in visible
    assert document.slice(SourceRange(document_id=document.ref.document_id,
                                      source_hash=document.ref.source_hash,
                                      start_line=1, end_line=2)) == 'Results\nNet income was $10.'
    assert b'Net income was $10.' in visible
