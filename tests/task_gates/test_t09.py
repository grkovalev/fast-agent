"""Independent numeric expectations and source-validation acceptance gate."""
import json
import socket
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from profitlab.demo import DemoService
from profitlab.documents.extraction import inline_figures, number, table_figures
from profitlab.documents.parser import parse_source
from profitlab.providers.extraction import ExtractionService
from profitlab.settings import Settings


def document(raw):
    blocks, cells, tables = parse_source(raw, 'test-filing')
    return {'blocks': blocks, 'cells': {c.cell_id: c for c in cells}, 'index': {'tables': tables}}


def test_offline_candidates_exact_values_rejections_and_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **kw: (_ for _ in ()).throw(AssertionError('Network forbidden')))
    run = DemoService(tmp_path).create('test-extract', 'T09')
    assert run.stage == 'extract'
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    service = ExtractionService(settings)
    index, attempts = service.latest(run.run_id)
    gold = json.loads((Path(__file__).parents[1] / 'fixtures/synthetic/gold.json').read_text())
    for year, values in gold.items():
        for metric in ('net_income_common', 'eps_diluted', 'weighted_average_shares_diluted'):
            expected = Decimal(values[metric]['value']) * (1 if metric == 'eps_diluted' else 1000000)
            assert any(a.candidate and a.candidate.metric.value == metric
                       and a.candidate.period.fiscal_year == int(year)
                       and a.candidate.value == expected for a in attempts)
    assert any(a.status == 'rejected' and a.proposal.get('cell_id') == 'invented-cell' for a in attempts)
    assert any(a.method == 'narrative' and a.evidence_id for a in attempts)
    assert index['synthetic']
    from profitlab.web.app import create_app
    with TestClient(create_app(settings)) as client:
        page = client.get('/runs/test-extract/candidates')
        assert page.status_code == 200
        assert 'fake extraction provider' in page.text
        assert 'View source' in page.text
        import re
        from html import unescape

        links = re.findall(r'href="([^"]*sources/[^"]+)"', page.text)
        assert links and all(client.get(unescape(link)).status_code == 200 for link in links)
    assert ExtractionService(settings).latest(run.run_id)[0] == index


def test_table_sign_scale_merged_headers_and_distractors():
    raw = b'''<html><body><p>Fiscal period: 2025-01-01 through 2025-12-31. USD.</p>
    <h2>Consolidated income statement annual GAAP</h2><table><caption>USD millions except per-share USD</caption>
    <tr><th rowspan="2">Metric</th><th colspan="2">Fiscal year ended</th></tr><tr><th>2025</th><th>2024</th></tr>
    <tr><th>Net income common shareholders</th><td>(12)</td><td>11</td></tr>
    <tr><th>Diluted EPS</th><td>(0.25)</td><td>0.20</td></tr>
    <tr><th>Adjusted diluted EPS</th><td>99</td><td>99</td></tr>
    <tr><th>Quarterly diluted EPS</th><td>88</td><td>88</td></tr>
    <tr><th>Segment net income common</th><td>77</td><td>77</td></tr></table></body></html>'''
    doc = document(raw)
    figures, issues = table_figures(doc, {b.block_id for b in doc['blocks']})
    assert {Decimal(f['value']) for f in figures.values()} == {Decimal(-12000000), Decimal('-0.25')}
    assert all(f['period']['fiscal_year'] == 2025 for f in figures.values())
    reasons = ' '.join(str(i['reasons']) for i in issues)
    for label in ('Adjusted', 'Quarterly', 'Segment', 'Exact fiscal interval'):
        assert label in reasons
    assert number('(1,200.50)') == Decimal('-1200.50')
    assert number('0') == 0
    import pytest

    with pytest.raises(ValueError, match='comma grouping'):
        number('1,25')


def test_inline_context_units_scale_hidden_and_unsupported():
    raw = b'''<html><body><ix:header><ix:hidden><ix:nonFraction id="hidden" name="us-gaap:EarningsPerShareDiluted">999</ix:nonFraction></ix:hidden></ix:header>
    <xbrli:context id="annual"><xbrli:period><xbrli:startDate>2024-10-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:context id="quarter"><xbrli:period><xbrli:startDate>2025-07-01</xbrli:startDate><xbrli:endDate>2025-09-30</xbrli:endDate></xbrli:period></xbrli:context>
    <xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>
    <table><tr><td>Income</td><td><ix:nonFraction id="income" contextRef="annual" unitRef="usd" name="us-gaap:NetIncomeLoss" scale="6" sign="-">12</ix:nonFraction></td></tr>
    <tr><td>Quarter</td><td><ix:nonFraction id="quarterly" contextRef="quarter" unitRef="usd" name="us-gaap:NetIncomeLoss">99</ix:nonFraction></td></tr>
    <tr><td>Missing</td><td><ix:nonFraction id="missing" name="us-gaap:EarningsPerShareDiluted">42</ix:nonFraction></td></tr>
    <tr><td>Unsupported</td><td><ix:nonFraction id="transform" contextRef="annual" unitRef="usd" name="us-gaap:NetIncomeLoss" format="ixt:num-comma-decimal">1,25</ix:nonFraction></td></tr>
    </table></body></html>'''
    doc = document(raw)
    figures, issues = inline_figures(raw, doc, {b.block_id for b in doc['blocks']})
    assert len(figures) == 1
    fact = next(iter(figures.values()))
    assert Decimal(fact['value']) == -12000000
    assert fact['period']['start'] == '2024-10-01'
    reasons = ' '.join(str(i['reasons']) for i in issues)
    assert 'Hidden-only' in reasons and 'Nonannual' in reasons and 'Missing XBRL context' in reasons
    assert 'Unsupported XBRL transformation' in reasons


def test_proposals_wrong_year_value_table_and_scale():
    from profitlab.contracts.extraction import FigureProposal
    from profitlab.contracts.sources import Chunk
    from profitlab.documents.extraction import validate_figure

    raw = b'''<html><body><p>2025-01-01 through 2025-12-31. USD.</p>
    <h2>Annual GAAP consolidated income statement</h2><table><caption>USD per share</caption>
    <tr><th>Metric</th><th>2025</th><th>2024</th></tr><tr><th>Diluted EPS</th><td>2.00</td><td>1.50</td></tr></table>
    <table><tr><td>Other</td><td>2.00</td></tr></table></body></html>'''
    doc = document(raw)
    retained = {b.block_id for b in doc['blocks']}
    entries, _ = table_figures(doc, retained)
    entry = next(iter(entries.values()))
    proposal = FigureProposal(**{k: entry[k] for k in ('block_id', 'cell_id', 'metric', 'raw_numeric_text', 'value', 'scale', 'period')})
    chunk = Chunk(chunk_id='test-chunk', filing_id='test-filing', block_ids=list(retained),
                  primary_block_ids=list(retained), text='', token_estimate=0,
                  estimator_version='test', source_anchors=[], cell_ids=list(doc['cells']))
    assert validate_figure(proposal, chunk, doc, entries)[0] == 'accepted'
    for changes in ({'value': Decimal('9.99')}, {'scale': Decimal(1000000)},
                    {'cell_id': 'hallucinated'}, {'raw_numeric_text': '1.00'},
                    {'period': proposal.period.model_copy(update={'fiscal_year': 2024})},
                    {'block_id': doc['blocks'][-1].block_id}):
        status, reasons, _ = validate_figure(proposal.model_copy(update=changes), chunk, doc, entries)
        assert status == 'rejected', reasons


def test_company_facts_conflict_never_replaces_filing_value():
    from profitlab.contracts.facts import FactCandidate
    from profitlab.documents.company_facts import crosscheck

    candidate = FactCandidate(candidate_id='check-candidate', metric='eps_diluted', raw_label='Diluted EPS',
        raw_numeric_text='2.00', value='2.00', currency='USD', unit='currency_per_share',
        period={'start': '2025-01-01', 'end': '2025-12-31', 'fiscal_year': 2025},
        annuality='annual', basis='gaap', scope='consolidated', attribution='common',
        extraction_method='table', evidence_ids=['check-evidence'])
    payload = {'facts': {'us-gaap': {'EarningsPerShareDiluted': {
        'label': 'EPS', 'description': 'Diluted EPS', 'units': {'USD/shares': [
            {'start': '2025-01-01', 'end': '2025-12-31', 'val': '3.00', 'accn': 'original', 'form': '10-K'}]}}}}}
    result = crosscheck(candidate, payload, 'original')
    assert result['status'] == 'conflict' and candidate.value == Decimal('2.00')
    assert crosscheck(candidate, payload, 'other')['status'] == 'unavailable'
