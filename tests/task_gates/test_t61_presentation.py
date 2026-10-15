from findings_test_support import seal_empty

"""SEC presentation joins use saved real records; failures never damage comparators."""
import hashlib
import io
import json
import zipfile
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from profitlab.sec.client import SECClient, SECError
from profitlab.settings import Settings
from profitlab.v2.contracts import StatementDatasetRef, V2Run
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.v2.facts_service import CompanyFactsService
from profitlab.v2.presentation_service import PresentationService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app

FIXTURES = Path(__file__).parents[1] / 'fixtures' / 't61'
FILING = {'cik': '0000789019', 'accession': '0000950170-24-087843', 'form': '10-K',
          'report_date': '2024-06-30', 'filing_date': '2024-07-30', 'filing_id': 'filing-msft'}


def fixtures():
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in ('sub', 'num', 'pre'):
            archive.writestr(f'{name}.txt', (FIXTURES / f'{name}.tsv').read_bytes())
    meta = json.loads((FIXTURES / 'provenance.json').read_text())
    dataset = StatementDatasetRef(source_url=meta['url'], source_hash=meta['sha256'],
        retrieved_at=meta['retrieved_at'], accession=FILING['accession'], quarter='2024q3')
    company = json.loads((FIXTURES / 'company_facts.json').read_text())
    facts, _ = CompanyFactsService.normalize(company, FILING)
    index = json.loads((FIXTURES / 'index.json').read_text())
    return payload.getvalue(), dataset, company, facts, index


def test_real_presentation_join_preserves_periods_versions_contexts_and_occurrences():
    raw, dataset, _, facts, index = fixtures()
    for name, digest in json.loads((FIXTURES / 'provenance.json').read_text())['files'].items():
        assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == digest
    service = PresentationService(Settings(_env_file=None), None)
    projection = service.project(raw, FILING, facts)
    before = [fact.model_dump_json() for fact in facts]
    net, eps, shares = service.match(projection, FILING, facts, dataset, index)
    assert [item.status for item in (net, eps, shares)] == ['matched', 'missing', 'matched']
    assert [(item.report, item.presentation_row) for item in net.locations] == [(2, 17), (3, 1), (6, 2), (7, 10)]
    assert str(net.numeric_records[0].value) == '88136000000.0000'
    assert net.numeric_records[0].taxonomy_version == 'us-gaap/2023'
    assert len(net.numeric_records) == 1  # Comparative years and equity dimension excluded.
    assert shares.locations[0].presentation_row == 23
    assert all(item.report_url.endswith(f'/R{item.report}.htm') for item in net.locations)
    assert not eps.locations and 'USD/shares' in eps.diagnostics[-1]

    duplicated = deepcopy(projection)
    duplicated['num'] += deepcopy(duplicated['num'])
    assert service.match(duplicated, FILING, facts, dataset, index) == [net, eps, shares]
    # A different taxonomy family cannot match a same-name, same-amount fact.
    other = deepcopy(projection)
    for row in other['num']:
        row['version'] = 'ifrs-full/2023'
    assert all(item.status == 'missing' for item in service.match(other, FILING, facts, dataset, index))
    # Controlled second standard taxonomy year is ambiguous, not a guessed origin.
    other = deepcopy(projection)
    for table in ('num', 'pre'):
        extra = deepcopy(other[table])
        for row in extra:
            row['version'] = 'us-gaap/2024'
        other[table] += extra
    ambiguous = service.match(other, FILING, facts, dataset, index)[0]
    assert ambiguous.status == 'ambiguous' and len(ambiguous.locations) == 8
    assert [fact.model_dump_json() for fact in facts] == before
    assert all(item.report_url is None for item in service.match(projection, FILING, facts, dataset, {})[0].locations)


def make_run(tmp_path):
    repo = V2Repository(tmp_path)
    run = V2Run(run_id='presentation-test', ticker='MSFT', created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
    repo.create_run(run)
    repo.save_filing(run.run_id, FILING['filing_id'], 'a' * 64, FILING)
    seal_empty(repo, run.run_id)
    repo.update_stage(repo.stage(run.run_id, 'findings').model_copy(update={'status': 'completed'}), event_kind='stage_finished', event_summary='Sealed')
    repo.update_stage(repo.stage(run.run_id, 'facts').model_copy(update={'status': 'completed'}), event_kind='stage_finished', event_summary='Independent facts loaded')
    return repo, run


def transport_factory(monkeypatch, handler):
    def factory(config, trace):
        return SECClient(config, trace, transport=httpx.MockTransport(handler))
    monkeypatch.setattr('profitlab.v2.facts_service.SECClient', factory)
    monkeypatch.setattr('profitlab.v2.presentation_service.SECClient', factory)


def test_saved_facts_enrichment_and_reader_have_no_provider_or_render_io(tmp_path, monkeypatch):
    raw, _, company, expected, index = fixtures()
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_user_agent='ProfitLab test@profitlab.org',
                        sec_requests_per_second=10, _env_file=None)
    repo, run = make_run(tmp_path)
    calls = []

    def handler(request):
        assert repo.stage(run.run_id, 'findings').status == 'completed'
        calls.append(str(request.url))
        if str(request.url).endswith('.zip'):
            return httpx.Response(200, content=raw)
        return httpx.Response(200, json=index if str(request.url).endswith('index.json') else company)

    transport_factory(monkeypatch, handler)
    repo.save_structured_facts(run.run_id, expected)
    baseline = EvaluationService(settings, repo).compare(run.run_id)
    actual, _, _ = CompanyFactsService(settings, repo).load(run)
    assert actual == expected
    assert len(calls) == 3 and '2024q3.zip' in calls[1]
    persisted = repo.fact_presentations_for_ids(run.run_id, [fact.fact_id for fact in actual])
    assert {item.status for item in persisted} == {'matched', 'missing'}
    assert EvaluationService(settings, repo).compare(run.run_id) == baseline
    assert len(repo.exploration_actions(run.run_id, 'facts')) == 7
    assert all(item.status == 'unavailable' for item in repo.fact_sources_for_ids(
        run.run_id, [fact.fact_id for fact in actual]))  # This HTTP fixture has no retained primary HTML.
    # Cache avoids new archive/index calls; enrichment remains separate from facts.
    PresentationService(settings, repo).enrich(run, actual)
    assert len(calls) == 3
    (tmp_path / 'sec-cache' / 'statements-2024q3.zip').write_bytes(b'corrupted archive')
    PresentationService(settings, repo).enrich(run, actual)
    assert len(calls) == 4 and calls[-1].endswith('2024q3.zip')
    persisted = repo.fact_presentations_for_ids(run.run_id, [f.fact_id for f in actual])
    reopened = V2Repository(tmp_path)
    assert reopened.fact_presentations_for_ids(run.run_id, [f.fact_id for f in actual]) == persisted

    def forbidden(*args, **kwargs):
        raise AssertionError('SEC/network I/O during page rendering')
    monkeypatch.setattr(SECClient, 'get', forbidden)
    with TestClient(create_app(settings)) as client:
        page = client.get(f'/v2/runs/{run.run_id}/pipeline?stage=facts')
        details = client.get(f'/v2/runs/{run.run_id}/pipeline/facts/presentation')
        overview = client.get(f'/v2/runs/{run.run_id}/pipeline')
        assert page.status_code == details.status_code == overview.status_code == 200
        assert 'presentation row 17' in page.text and '/R2.htm' in page.text
        assert 'USD/shares' in page.text and 'not canonical filing lines' in page.text
        assert 'fact-presentation-dataset' in details.text
        assert 'data-facts-station="enrich"' in overview.text
        assert 'FactPresentation' in page.text
        repo.save_fact_presentations(run.run_id, [])
        assert 'No presentation provenance was saved for this fact' in client.get(
            f'/v2/runs/{run.run_id}/pipeline?stage=facts').text


def test_unavailable_archive_cannot_remove_facts_or_block_comparison(tmp_path, monkeypatch):
    _, _, company, expected, _ = fixtures()
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_user_agent='ProfitLab test@profitlab.org',
                        sec_requests_per_second=10, _env_file=None)
    repo, run = make_run(tmp_path)

    def handler(request):
        return httpx.Response(403) if str(request.url).endswith('.zip') else httpx.Response(200, json=company)
    transport_factory(monkeypatch, handler)
    repo.save_structured_facts(run.run_id, expected)
    baseline = EvaluationService(settings, repo).compare(run.run_id)
    actual, _, _ = CompanyFactsService(settings, repo).load(run)
    assert actual == expected
    assert sorted(actual, key=lambda x: x.metric) == repo.structured_facts(run.run_id)
    failed = repo.fact_presentations_for_ids(run.run_id, [fact.fact_id for fact in actual])
    assert all(item.status == 'retrieval_failed' and 'HTTP 403' in item.diagnostics[0] for item in failed)
    assert EvaluationService(settings, repo).compare(run.run_id) == baseline
    repo.update_stage(repo.stage(run.run_id, 'findings').model_copy(update={'status': 'queued'}), event_kind='resume_requested', event_summary='Unsealed')
    with pytest.raises(ValueError, match='sealed'):
        PresentationService(settings, repo).enrich(run, actual)


def test_archive_bounds_and_cache_integrity(tmp_path):
    raw, _, _, facts, _ = fixtures()
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_statement_max_rows=1, _env_file=None)
    with pytest.raises(ValueError, match='parsing row limit'):
        PresentationService(settings, None).project(raw, FILING, facts)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_statement_projection_rows=1, _env_file=None)
    with pytest.raises(ValueError, match='projection limit'):
        PresentationService(settings, None).project(raw, FILING, facts)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_statement_projection_bytes=1024, _env_file=None)
    with pytest.raises(ValueError, match='projection byte limit'):
        PresentationService(settings, None).project(raw, FILING, facts)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_statement_expanded_bytes=1024, _env_file=None)
    with pytest.raises(ValueError, match='expansion limit'):
        PresentationService(settings, None).project(raw, FILING, facts)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    with pytest.raises(ValueError, match='time limit'):
        PresentationService(settings, None).project(raw, FILING, facts, deadline=0)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, sec_statement_archive_bytes=1024,
                        sec_requests_per_second=10, _env_file=None)
    from profitlab.v2.source_service import _V2Trace
    client = SECClient(settings, _V2Trace(settings.redactor()),
                       transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'PK\x03\x04' + b'x' * 1024)))
    with pytest.raises(SECError, match='byte limit'):
        client.statement_archive('2024q3')
    client.close()
