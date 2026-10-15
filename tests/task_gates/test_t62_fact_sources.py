from findings_test_support import seal_empty

"""Real retained SEC HTML proves exact cells; controlled failures cannot invent lines."""
import gzip
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import html

from profitlab.sec.client import SECClient
from profitlab.settings import Settings
from profitlab.v2.canonical import canonicalize_html
from profitlab.v2.contracts import Finding, StructuredFact, V2Run
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.v2.fact_source_service import FactSourceService
from profitlab.v2.facts_service import CompanyFactsService
from profitlab.v2.findings_candidates import enumerate_candidates
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app

FIXTURES = Path(__file__).parents[1] / 'fixtures'
FILING = {'cik': '0000789019', 'accession': '0000950170-24-087843', 'form': '10-K',
          'report_date': '2024-06-30', 'filing_date': '2024-07-30',
          'filing_id': 'filing-msft', 'document_id': 'document-msft'}


def real_source():
    raw = gzip.decompress((FIXTURES / 't62/msft-20240630.htm.gz').read_bytes())
    meta = json.loads((FIXTURES / 't62/provenance.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == meta['sha256']
    document, visible = canonicalize_html(raw, document_id=FILING['document_id'],
                                           filing_id=FILING['filing_id'])
    facts, _ = CompanyFactsService.normalize(json.loads(
        (FIXTURES / 't61/company_facts.json').read_text()), FILING)
    return raw, document, visible, facts


def test_real_cells_period_scale_repeated_rows_and_source_identity():
    raw, document, visible, facts = real_source()
    before = [fact.model_dump_json() for fact in facts]
    mappings = FactSourceService.map(raw, document, visible, FILING, facts)
    assert [item.status for item in mappings] == ['verified'] * 3
    assert [len(item.locations) for item in mappings] == [4, 2, 2]
    assert [l.source_range.start_line for l in mappings[0].locations] == [826, 840, 902, 1102]
    sanitized = html.document_fromstring(visible)
    for fact, mapping in zip(facts, mappings, strict=True):
        for location in mapping.locations:
            assert location.transformed_value == fact.value
            assert location.period_start == fact.period_start and location.period_end == fact.period_end
            assert location.unit == fact.unit and location.entity_identifier == FILING['cik']
            assert location.quote == document.slice(location.source_range)
            assert location.html_anchor == document.anchor_for(location.source_range)
            cell = sanitized.xpath(location.cell_dom_reference)[0]
            assert location.display_text in cell.text_content()
            assert sanitized.xpath('//*[@id=$id]', id=location.html_anchor)
            assert any('2024 2023 2022' in text for text in location.header_context)
    # Real comparative columns share a row, but retain distinct context and cell.
    comparative, _ = CompanyFactsService.normalize(json.loads(
        (FIXTURES / 't61/company_facts.json').read_text()), {**FILING, 'report_date': '2023-06-30'})
    previous = FactSourceService.map(raw, document, visible, FILING, comparative)
    assert [len(item.locations) for item in previous] == [4, 2, 2]
    assert previous[0].locations[0].display_text == '72,361'
    assert previous[0].locations[0].source_range == mappings[0].locations[0].source_range
    assert previous[0].locations[0].cell_dom_reference != mappings[0].locations[0].cell_dom_reference
    assert previous[0].locations[0].context_id != mappings[0].locations[0].context_id
    assert mappings[0].locations[0].scale == 6
    assert mappings[1].locations[0].display_text == '11.80' and mappings[1].locations[0].scale == 0
    assert mappings[2].locations[0].display_text == '7,469' and mappings[2].locations[0].scale == 6
    assert [fact.model_dump_json() for fact in facts] == before
    assert b'contextref' not in visible and b'us-gaap:' not in visible
    with pytest.raises(ValueError, match='hash mismatch'):
        FactSourceService.map(raw + b' ', document, visible, FILING, facts)
    with pytest.raises(ValueError, match='disagree'):
        FactSourceService.map(raw, document, visible + b' ', FILING, facts)
    changed = document.model_copy(deep=True)
    changed.lines[825] = changed.lines[825].model_copy(update={'text': 'Wrong retained text'})
    with pytest.raises(ValueError, match='disagree'):
        FactSourceService.map(raw, changed, visible, FILING, facts)


def controlled_source(*, attributes='', content='1.234,56', extra='', context_extra='', unit='iso4217:USD'):
    raw = f'''<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
      xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"
      xmlns:gaap="http://fasb.org/us-gaap/2023" xmlns:ixt="http://www.xbrl.org/inlineXBRL/transformation/2020-02-12">
      <body><ix:header><xbrli:context id="ctx"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000789019</xbrli:identifier>{context_extra}</xbrli:entity>
      <xbrli:period><xbrli:startDate>2023-07-01</xbrli:startDate><xbrli:endDate>2024-06-30</xbrli:endDate></xbrli:period></xbrli:context>
      <xbrli:unit id="usd"><xbrli:measure>{unit}</xbrli:measure></xbrli:unit></ix:header>
      <h1>Results</h1><table><tr><th>2024</th></tr><tr><td>Loss</td><td>(<ix:nonFraction id="loss" name="gaap:NetIncomeLoss" contextRef="ctx" unitRef="usd" scale="3" sign="-" format="ixt:num-comma-decimal" {attributes}>{content}</ix:nonFraction>)</td></tr></table>{extra}</body></html>'''.encode()
    fact = StructuredFact(fact_id='fact-loss', concept='us-gaap:NetIncomeLoss', metric='net_income_consolidated',
        value=Decimal(-1234560), unit='USD', period_start='2023-07-01', period_end='2024-06-30',
        accession=FILING['accession'], form='10-K', filed_date='2024-07-30')
    document, visible = canonicalize_html(raw, document_id=FILING['document_id'], filing_id=FILING['filing_id'])
    return raw, document, visible, [fact]


def test_controlled_hidden_ambiguous_formats_contexts_and_projection_bounds(monkeypatch):
    def mapped(**kwargs):
        raw, document, visible, facts = controlled_source(**kwargs)
        return FactSourceService.map(raw, document, visible, FILING, facts)[0]
    valid = mapped()
    assert valid.status == 'verified' and valid.locations[0].sign == '-'
    assert valid.locations[0].displayed_value == Decimal('1234.56')
    assert valid.locations[0].cell_text == '(1.234,56)'
    assert mapped(attributes='style="display:none"').status == 'hidden_only'
    assert mapped(attributes='continuedAt="continuation"', extra='<ix:continuation id="continuation">0</ix:continuation>').status == 'ambiguous'
    assert mapped(content='<span style="display:none">1</span>234,56').status == 'ambiguous'
    assert mapped(context_extra='<xbrli:segment>dimension</xbrli:segment>').status == 'unavailable'
    assert mapped(unit='iso4217:EUR').status == 'ambiguous'
    raw, _document, _visible, facts = controlled_source()
    for original, replacement in ((b'ixt:num-comma-decimal', b'ixt:unknown'),
                                  (b'http://fasb.org/us-gaap/2023', b'http://example.org/us-gaap/2023'),
                                  (b'2023-07-01', b'2023-07-02')):
        changed = raw.replace(original, replacement)
        d, v = canonicalize_html(changed, document_id=FILING['document_id'], filing_id=FILING['filing_id'])
        item = FactSourceService.map(changed, d, v, FILING, facts)[0]
        assert item.status in {'ambiguous', 'unavailable'} and not item.locations
    monkeypatch.setattr('profitlab.v2.fact_source_service.MAX_LOCATIONS', 0)
    capped = mapped()
    assert capped.status == 'ambiguous' and not capped.locations
    assert 'projection limit' in ' '.join(capped.diagnostics)


def test_post_findings_persistence_no_render_io_and_comparison_inputs_unchanged(tmp_path, monkeypatch):
    raw, document, visible, facts = real_source()
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    run = V2Run(run_id='fact-source-test', ticker='MSFT', created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
    repo.create_run(run)
    repo.save_canonical_document(run.run_id, document, raw, visible)
    repo.save_filing(run.run_id, FILING['filing_id'], document.ref.source_hash, FILING)
    repo.save_structured_facts(run.run_id, facts)
    repo.save_fact_summary(run.run_id, {'provenance': 'SEC Company Facts JSON', 'cik': FILING['cik'],
                                      'source_hash': document.ref.source_hash, 'alternatives': {}})
    service = FactSourceService(settings, repo)
    with pytest.raises(ValueError, match='sealed'):
        service.enrich(run, facts)
    seal_empty(repo, run.run_id)
    repo.update_stage(repo.stage(run.run_id, 'findings').model_copy(update={'status': 'completed'}),
                      event_kind='stage_finished', event_summary='Sealed')
    repo.update_stage(repo.stage(run.run_id, 'facts').model_copy(update={'status': 'completed'}),
                      event_kind='stage_finished', event_summary='Facts saved')
    baseline = EvaluationService(settings, repo).compare(run.run_id)
    discovery_before = enumerate_candidates(document, [], [], relevance_threshold=.2, policy=settings.findings_policy).model_dump(mode="json")
    source_line = document.lines[825]
    from profitlab.v2.contracts import SourceRange
    finding = Finding(finding_id='finding-net', exact_quote=source_line.text,
        source_range=SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                                 start_line=source_line.line_number, end_line=source_line.line_number),
        amount=Decimal(88136), finding_type='annual_profit', unit='USD', period='2024', validation_state='validated')
    evaluation_service = EvaluationService(settings, repo)
    visible_context = {'declared_core_evidence_line': {'line_number': 826, 'text': source_line.text}}
    verification_before = evaluation_service._request(finding, facts[0], visible_context)
    mappings = service.enrich(run, facts)
    assert enumerate_candidates(document, [], [], relevance_threshold=.2, policy=settings.findings_policy).model_dump(mode="json") == discovery_before
    assert evaluation_service._request(finding, facts[0], visible_context) == verification_before
    assert 'inline-visible' not in json.dumps(discovery_before)
    assert 'context_id' not in verification_before.model_dump_json()
    assert EvaluationService(settings, repo).compare(run.run_id) == baseline
    assert V2Repository(tmp_path).fact_sources_for_ids(run.run_id, [f.fact_id for f in facts]) == sorted(mappings, key=lambda m: m.fact_id)
    assert sorted(facts, key=lambda f: f.metric) == repo.structured_facts(run.run_id)

    def forbidden(*args, **kwargs):
        raise AssertionError('Rendering must only read saved provenance')
    monkeypatch.setattr(SECClient, 'get', forbidden)
    monkeypatch.setattr(FactSourceService, 'map', forbidden)
    with TestClient(create_app(settings)) as client:
        page = client.get(f'/v2/runs/{run.run_id}/pipeline?stage=facts')
        assert page.status_code == 200 and 'FactSourceMapping' in page.text
        assert '4 verified visible occurrence(s)' in page.text
        details = client.get(f'/v2/runs/{run.run_id}/pipeline/facts/source?fact_id={facts[0].fact_id}')
        assert details.status_code == 200 and 'Canonical line 826' in details.text
        assert 'Open fact source' in details.text and '88,136' in details.text and '88136000000' in details.text
        link = f'/v2/runs/{run.run_id}/source/{document.ref.document_id}/html#{mappings[0].locations[0].html_anchor}'
        assert link in details.text
        assert client.get(link).content == visible
        missing = client.get(f'/v2/runs/{run.run_id}/pipeline/facts/source?fact_id=fact-historical')
        assert 'No source mapping was saved' in missing.text
        assert client.get(f'/v2/runs/{run.run_id}/pipeline/facts/source?fact_id={facts[0].fact_id}&page=0').status_code == 400
