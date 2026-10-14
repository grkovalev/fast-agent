"""Two real statement layouts: independent cell identity and saved UI source links."""
import gzip
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from lxml import html

from profitlab.sec.client import SECClient
from profitlab.settings import Settings
from profitlab.v2.canonical import canonicalize_html
from profitlab.v2.contracts import Finding, V2Run
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.v2.fact_source_service import FactSourceService
from profitlab.v2.facts_service import CompanyFactsService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app

FIXTURES = Path(__file__).parents[1] / 'fixtures'
CASES = [
    ('MSFT', 't62/msft-20240630.htm.gz', 't61/company_facts.json',
     {'cik': '0000789019', 'accession': '0000950170-24-087843', 'form': '10-K',
      'report_date': '2024-06-30', 'filing_date': '2024-07-30',
      'filing_id': 'filing-msft', 'document_id': 'document-msft'},
     '2023-06-30', [[826, 840, 902, 1102], [829, 1108], [832, 1105]],
     ['88,136', '11.80', '7,469'], [6, 0, 6]),
    ('AAPL', 't64/aapl-20240928.htm.gz', 't64/company_facts.json',
     json.loads((FIXTURES / 't64/provenance.json').read_text())['filing'],
     '2023-09-30', [[123, 132, 207, 249], [126, 255], [129, 253]],
     ['93,736', '6.08', '15,408,095'], [6, 0, 3]),
]


@pytest.mark.parametrize('ticker,raw_path,facts_path,filing,previous_end,line_numbers,cells,scales',
                         CASES, ids=['MSFT', 'AAPL'])
def test_two_company_exact_cells_and_evaluation_links(
        tmp_path, monkeypatch, ticker, raw_path, facts_path, filing, previous_end,
        line_numbers, cells, scales):
    raw = gzip.decompress((FIXTURES / raw_path).read_bytes())
    metadata = json.loads((FIXTURES / raw_path.split('/')[0] / 'provenance.json').read_text())
    expected_hash = metadata['sha256'] if ticker == 'MSFT' else metadata['sources'][Path(raw_path).name]['sha256']
    assert hashlib.sha256(raw).hexdigest() == expected_hash
    facts_bytes = (FIXTURES / facts_path).read_bytes()
    facts_meta = json.loads((FIXTURES / facts_path.split('/')[0] / 'provenance.json').read_text())
    assert hashlib.sha256(facts_bytes).hexdigest() == facts_meta['sources']['company_facts.json']['fixture_sha256']
    dataset = json.loads(facts_bytes)
    document, visible = canonicalize_html(raw, document_id=filing['document_id'], filing_id=filing['filing_id'])
    original, sanitized = html.document_fromstring(raw), html.document_fromstring(visible)
    raw_nodes = {original.getroottree().getpath(node): node for node in original.iter()}
    facts, _ = CompanyFactsService.normalize(dataset, filing)
    mappings = FactSourceService.map(raw, document, visible, filing, facts)
    comparative, _ = CompanyFactsService.normalize(dataset, {**filing, 'report_date': previous_end})
    previous = FactSourceService.map(raw, document, visible, filing, comparative)
    assert len(facts) == len(comparative) == 3
    assert [m.status for m in [*mappings, *previous]] == ['verified'] * 6
    assert [[l.source_range.start_line for l in m.locations] for m in mappings] == line_numbers
    assert [[l.source_range.start_line for l in m.locations] for m in previous] == line_numbers
    assert b'contextref' not in visible and b'us-gaap:' not in visible

    # Audit every occurrence directly against retained DOM, independently of mapper helpers.
    for group, selected in ((mappings, facts), (previous, comparative)):
        for index, (mapping, fact) in enumerate(zip(group, selected, strict=True)):
            for location in mapping.locations:
                node = raw_nodes[location.raw_dom_reference]
                assert node.get('name').split(':')[1] == fact.concept.split(':')[1]
                prefix = node.get('name').split(':')[0].lower()
                namespace = next(parent.get('xmlns:' + prefix)
                    for parent in (node, *node.iterancestors()) if parent.get('xmlns:' + prefix))
                assert namespace == location.concept_namespace
                assert node.get('contextref') == location.context_id
                context = original.xpath('//*[@id=$id]', id=location.context_id)[0]
                values = {n.tag.split(':')[-1]: n.text for n in context.iterdescendants()}
                assert int(values['identifier']) == int(filing['cik'])
                assert values['startdate'] == fact.period_start.isoformat()
                assert values['enddate'] == fact.period_end.isoformat()
                assert not {'segment', 'scenario', 'explicitmember', 'typedmember'} & values.keys()
                unit = original.xpath('//*[@id=$id]', id=node.get('unitref'))[0]
                measures = [n.text.split(':')[-1] for n in unit.iterdescendants() if n.tag.endswith(':measure')]
                assert measures == {'USD': ['USD'], 'shares': ['shares'], 'USD/shares': ['USD', 'shares']}[fact.unit]
                assert location.unit == fact.unit and location.scale == scales[index]
                assert Decimal(node.text_content().replace(',', '')) * Decimal(10) ** int(node.get('scale', '0')) == fact.value
                assert location.transformed_value == fact.value
                table = next(parent for parent in node.iterancestors() if parent.tag == 'table')
                caption_nodes = [*table.xpath('.//tr[position()<=4]'),
                    *table.xpath('preceding-sibling::*[position()<=3]'),
                    *table.getparent().xpath('preceding-sibling::*[position()<=3]')]
                captions = ' '.join(n.text_content() for n in caption_nodes).lower()
                if scales[index]:
                    scale_word = 'thousands' if scales[index] == 3 else 'millions'
                    assert scale_word in captions
                    assert any(scale_word in n.text_content().lower() and
                               ' '.join(n.text_content().split()) in ' '.join(sanitized.text_content().split())
                               for n in caption_nodes)
                assert location.quote == document.slice(location.source_range)
                assert location.html_anchor == document.anchor_for(location.source_range)
                cell = sanitized.xpath(location.cell_dom_reference)[0]
                assert location.display_text in cell.text_content()
                anchor = sanitized.xpath('//*[@id=$id]', id=location.html_anchor)[0]
                assert cell is anchor or anchor in cell.iterancestors()
                assert any('2024' in h and '2023' in h for h in location.header_context)
                if group is mappings:
                    assert location.display_text == cells[index]
            if group is mappings:
                for current, prior in zip(mapping.locations, previous[index].locations, strict=True):
                    assert current.cell_dom_reference != prior.cell_dom_reference
                    assert current.context_id != prior.context_id

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    run_id = f't64-{ticker.lower()}'
    run = V2Run(run_id=run_id, ticker=ticker, created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
    repo.create_run(run)
    repo.save_canonical_document(run_id, document, raw, visible)
    repo.save_filing(run_id, filing['filing_id'], document.ref.source_hash, filing)
    repo.save_structured_facts(run_id, facts)
    repo.save_fact_summary(run_id, {'cik': filing['cik'], 'supported_facts': 3, 'alternatives': {}})
    # Controlled discovery outcomes using real quotes: an unscaled income amount,
    # exact EPS and absent shares. These are not recorded model responses.
    findings = [Finding(finding_id=f'finding-{i}', exact_quote=mappings[i].locations[0].quote,
        source_range=mappings[i].locations[0].source_range,
        amount=mappings[i].locations[0].displayed_value if i == 0 else facts[i].value,
        finding_type=('annual_profit', 'diluted_eps')[i], unit=facts[i].unit,
        period='2024', validation_state='validated') for i in range(2)]
    repo.save_findings(run_id, findings)
    for stage in ('findings', 'facts'):
        repo.update_stage(repo.stage(run_id, stage).model_copy(update={'status': 'completed'}),
                          event_kind='stage_finished', event_summary='Saved real-data acceptance checkpoint')
    evaluation = EvaluationService(settings, repo)
    baseline = evaluation.compare(run_id)
    assert {c.metric: c.state for c in baseline.comparisons} == {
        'net_income_consolidated': 'period_match_value_mismatch', 'eps_diluted': 'exact_match',
        'weighted_average_shares_diluted': 'structured_fact_missed'}
    repo.save_fact_source_mappings(run_id, mappings)
    assert evaluation.compare(run_id) == baseline
    repo.save_comparisons(run_id, baseline.comparisons)
    repo.save_comparison_summary(run_id, baseline.summary)
    saved_comparisons = repo.comparisons(run_id)

    # A deliberately incompatible unit must yield a reason, never a number-only link.
    unsupported = facts[0].model_copy(update={'unit': 'EUR'})
    unresolved = FactSourceService.map(raw, document, visible, filing, [unsupported])[0]
    assert unresolved.status == 'unavailable' and not unresolved.locations and unresolved.diagnostics

    def forbidden(*args, **kwargs):
        raise AssertionError('Acceptance UI must only read saved provenance')
    monkeypatch.setattr(SECClient, 'get', forbidden)
    monkeypatch.setattr(FactSourceService, 'map', forbidden)
    with TestClient(create_app(settings)) as client:
        for stage in ('evaluate', 'facts'):
            page = client.get(f'/v2/runs/{run_id}/pipeline?stage={stage}')
            assert page.status_code == 200
            parsed = html.fromstring(page.text)
            for mapping in mappings:
                assert mapping.locations[0].html_anchor in page.text
            # Every displayed canonical source anchor resolves to the retained row.
            links = parsed.xpath('//a[text()="Open fact source"]/@href')
            assert links
            for target in links:
                response = client.get(target)
                assert response.content == visible
                assert html.fromstring(response.content).xpath('//*[@id=$id]', id=urlsplit(target).fragment)
        repo.save_fact_source_mappings(run_id, [*mappings, *previous])
        for mapping in [*mappings, *previous]:
            # Comparative mappings use separate IDs and are inspected through the same saved route.
            details = client.get(f'/v2/runs/{run_id}/pipeline/facts/source?fact_id={mapping.fact_id}')
            assert details.status_code == 200
            for location in mapping.locations:
                assert f'Canonical line {location.source_range.start_line}' in details.text
                assert location.html_anchor in details.text
                assert location.display_text in details.text
            assert str(mapping.locations[0].transformed_value) in details.text
        repo.save_fact_source_mappings(run_id, [unresolved, *mappings[1:]])
        page = html.fromstring(client.get(f'/v2/runs/{run_id}/pipeline?stage=evaluate').text)
        card = page.xpath('//*[@data-comparison-card][@data-metric="net_income_consolidated"]')[0]
        assert 'unavailable' in card.text_content()
        assert all(diagnostic in card.text_content() for diagnostic in unresolved.diagnostics)
        assert not card.xpath('.//a[text()="Open fact source"]')
    assert repo.comparisons(run_id) == saved_comparisons
