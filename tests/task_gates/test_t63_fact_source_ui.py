"""Saved real filing sources remain inspectable across comparison states/pages."""
import csv
import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from lxml import html

from profitlab.sec.client import SECClient
from profitlab.settings import Settings
from profitlab.v2.canonical import canonicalize_html
from profitlab.v2.contracts import FactComparison, Finding, StatementDatasetRef, V2Run
from profitlab.v2.fact_source_service import FactSourceService
from profitlab.v2.facts_service import CompanyFactsService
from profitlab.v2.presentation_service import PresentationService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app
from profitlab.web.fact_provenance import source_preview

FIXTURES = Path(__file__).parents[1] / 'fixtures'
FILING = {'cik': '0000789019', 'accession': '0000950170-24-087843', 'form': '10-K',
          'report_date': '2024-06-30', 'filing_date': '2024-07-30',
          'filing_id': 'filing-msft', 'document_id': 'document-msft'}


def test_real_sources_across_comparison_states_pages_and_unavailable_history(tmp_path, monkeypatch):
    raw = gzip.decompress((FIXTURES / 't62/msft-20240630.htm.gz').read_bytes())
    document, visible = canonicalize_html(raw, document_id=FILING['document_id'],
                                           filing_id=FILING['filing_id'])
    facts, _ = CompanyFactsService.normalize(json.loads(
        (FIXTURES / 't61/company_facts.json').read_text()), FILING)
    mappings = FactSourceService.map(raw, document, visible, FILING, facts)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    run_id = 't63-real-sources'
    repo.create_run(V2Run(run_id=run_id, ticker='MSFT', created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    repo.save_canonical_document(run_id, document, raw, visible)
    repo.save_filing(run_id, FILING['filing_id'], document.ref.source_hash, FILING)
    # Controlled pagination stress: all real comparators sort after the first 100.
    padding = [facts[0].model_copy(update={'fact_id': f'padding-{i}', 'metric': 'aaa'}) for i in range(100)]
    repo.save_structured_facts(run_id, [*padding, *facts])
    repo.save_fact_summary(run_id, {'provenance': 'SEC Company Facts JSON', 'cik': FILING['cik'],
                                  'source_hash': document.ref.source_hash, 'alternatives': {}})
    repo.save_fact_source_mappings(run_id, mappings)
    meta = json.loads((FIXTURES / 't61/provenance.json').read_text())
    dataset = StatementDatasetRef(source_url=meta['url'], source_hash=meta['sha256'],
        retrieved_at=meta['retrieved_at'], accession=FILING['accession'], quarter='2024q3')
    projection = {name: list(csv.DictReader((FIXTURES / f't61/{name}.tsv').read_text().splitlines(),
                                          delimiter='\t')) for name in ('sub', 'num', 'pre')}
    presentations = PresentationService.match(projection, FILING, facts, dataset,
        json.loads((FIXTURES / 't61/index.json').read_text()))
    repo.save_fact_presentations(run_id, presentations)
    finding = Finding(finding_id='finding-net', exact_quote=mappings[0].locations[0].quote,
        source_range=mappings[0].locations[0].source_range, amount=facts[0].value,
        finding_type='annual_profit', unit=facts[0].unit, period='2024', validation_state='validated')
    repo.save_findings(run_id, [finding])
    comparisons = [FactComparison(comparison_id=f'comparison-{i}', fact_id=fact.fact_id,
        metric=fact.metric, finding_ids=[finding.finding_id] if i < 2 else [], state=state)
        for i, (fact, state) in enumerate(zip(facts, (
            'exact_match', 'period_match_value_mismatch', 'structured_fact_missed'), strict=True))]
    comparisons.append(FactComparison(comparison_id='comparison-additional',
        finding_ids=[finding.finding_id], state='additional_visible_value'))
    repo.save_comparisons(run_id, comparisons)
    repo.save_comparison_summary(run_id, {'expected_facts': 3, 'exact_matches': 1,
                                         'misses': 2, 'additional_visible_numbers': 1})
    before = repo.comparisons(run_id)
    assert not {f.fact_id for f in facts} & {f.fact_id for f in repo.structured_facts(run_id, page=1)}

    def forbidden(*args, **kwargs):
        raise AssertionError('Rendering must only read saved provenance')
    monkeypatch.setattr(SECClient, 'get', forbidden)
    monkeypatch.setattr(FactSourceService, 'map', forbidden)
    monkeypatch.setattr(PresentationService, 'enrich', forbidden)
    with TestClient(create_app(settings)) as client:
        url = f'/v2/runs/{run_id}/pipeline?stage=evaluate'
        response = client.get(url)
        assert response.status_code == 200
        assert len(response.content) < 250000
        all_cards = html.fromstring(response.text).xpath('//*[@data-comparison-card]')
        assert len(all_cards) == 4
        by_metric = {card.get('data-metric'): card for card in all_cards}
        cards = [by_metric[fact.metric] for fact in facts]
        additional = next(card for card in all_cards if card.get('data-kind') == 'additional')
        for card, mapping in zip(cards[:3], mappings, strict=True):
            assert 'Independent fact canonical source · verified' in card.text_content()
            assert '88,136' in response.text and 'Display scale 10^6' in response.text
            # The comparator has a one-action link outside collapsed diagnostics.
            links = card.xpath('.//*[@class="comparison-values"]//a[text()="Open fact source"]')
            assert len(links) == 1
            target = links[0].get('href')
            assert target.endswith('#' + mapping.locations[0].html_anchor)
            assert client.get(target).content == visible
            assert 'Nearby visible year and scale context' in card.text_content()
        assert 'Not found' in cards[2].text_content()
        assert not additional.xpath('.//*[@aria-label="Independent fact source"]')
        # Net income has four saved occurrences, only three appear in the card.
        assert 'Bounded preview: up to 3 occurrences' in cards[0].text_content()
        assert 'presentation row 17' in cards[0].text_content()
        assert 'not canonical filing lines' in cards[0].text_content()
        assert 'Canonical line 1102' not in cards[0].text_content()
        details = client.get(f'/v2/runs/{run_id}/pipeline/facts/source?fact_id={facts[0].fact_id}')
        assert 'Canonical line 1102' in details.text
        facts_page = client.get(f'/v2/runs/{run_id}/pipeline?stage=facts&page=2')
        assert 'id="fact-source-results"' in facts_page.text
        assert 'Canonical line 826' in facts_page.text and 'Open fact source' in facts_page.text
        overview = client.get(f'/v2/runs/{run_id}/pipeline')
        assert 'Inspect saved fact source lines, context, and provenance' in overview.text
        # Every retained occurrence remains reachable beyond the preview/page cap.
        repo.save_fact_source_mappings(run_id, [mappings[0].model_copy(update={
            'locations': [mappings[0].locations[0]] * 25})])
        details_url = f'/v2/runs/{run_id}/pipeline/facts/source?fact_id={facts[0].fact_id}'
        first_page = client.get(details_url).text
        next_page = client.get(details_url + '&page=2').text
        assert first_page.count('Open fact source') == 20 and 'Next locations' in first_page
        assert next_page.count('Open fact source') == 5 and 'Previous locations' in next_page

        # Controlled diagnostic variants; no visible line may be invented.
        for status in ('ambiguous', 'hidden_only', 'unavailable'):
            diagnostic = mappings[0].model_copy(update={
                'status': status, 'locations': [], 'diagnostics': ['Controlled unresolved occurrence']})
            repo.save_fact_source_mappings(run_id, [diagnostic])
            page = html.fromstring(client.get(url).text)
            first = page.xpath('//*[@data-comparison-card][@data-metric=$metric]', metric=facts[0].metric)[0]
            assert status.replace('_', ' ') in first.text_content()
            assert 'Controlled unresolved occurrence' in first.text_content()
            assert not first.xpath('.//a[text()="Open fact source"]')
            assert first.xpath('.//a[text()="Open SEC statement report"]')
        repo.save_fact_source_mappings(run_id, [])
        assert 'No source mapping was saved for this fact' in client.get(url).text
    assert repo.comparisons(run_id) == before


def test_preview_bounds_preserve_runtime_ranges_and_decimal():
    from profitlab.v2.contracts import FactSourceLocation, FactSourceMapping, SourceRange

    location = FactSourceLocation(fact_id='fact-bounds',
        source_range=SourceRange(document_id='document-bounds', source_hash='a' * 64, start_line=1, end_line=2),
        html_anchor='line-1', quote='q' * 20000, cell_text='c' * 20000,
        raw_dom_reference='/raw', concept_namespace='http://fasb.org/us-gaap/2023',
        context_id='ctx', entity_identifier='0000789019', period_start='2023-07-01',
        period_end='2024-06-30', unit='USD', display_text='1.01', scale=6,
        displayed_value='1.01', transformed_value='1010000', header_context=['h' * 10000] * 12)
    mapping = FactSourceMapping(fact_id=location.fact_id, status='verified',
        locations=[location] * 1000, diagnostics=['d' * 10000] * 20)
    preview = source_preview(mapping)
    assert preview['truncated'] and preview['location_count'] == 1000
    assert len(preview['locations']) == 3 and len(json.dumps(preview)) < 20000
    first = preview['locations'][0]
    assert first['source_range'] == location.source_range.model_dump(mode='json')
    assert first['transformed_value'] == '1010000' and len(first['quote']) == 1200
    assert len(first['header_context']) == 6
    assert len(mapping.locations[0].quote) == 20000
