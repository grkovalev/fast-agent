import json
import socket
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from profitlab.cli import app
from profitlab.contracts.base import CompanyIdentity, FiscalPeriod
from profitlab.contracts.facts import AnnualObservation, FactCandidate, Metric, ScreeningDecision
from profitlab.contracts.sources import EvidenceRef, FilingRecord, SourceBlock
from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.web.app import create_app


def candidate(**changes):
    values = {'candidate_id': 'fact', 'metric': 'eps_diluted', 'raw_label': 'Diluted EPS',
                  'raw_numeric_text': '0.00', 'value': Decimal('0.00'), 'currency': 'USD',
                  'unit': 'currency_per_share', 'period': FiscalPeriod(
                      start='2025-01-01', end='2025-12-31', fiscal_year=2025),
                  'annuality': 'annual', 'basis': 'gaap', 'scope': 'consolidated',
                  'attribution': 'common', 'extraction_method': 'table', 'evidence_ids': ['evidence']}
    return FactCandidate(**(values | changes))


def test_contract_validation():
    fact = candidate(value=Decimal('12345678901234567890.00100'))
    assert '"12345678901234567890.00100"' in fact.model_dump_json()
    assert FactCandidate.model_validate_json(fact.model_dump_json()).value == fact.value
    assert candidate().value == Decimal(0)
    observation = AnnualObservation(
        observation_id='annual', period=candidate().period,
        selected_facts={Metric.EPS_DILUTED: 'zero-eps'},
        missingness={metric: 'missing' for metric in Metric if metric != Metric.EPS_DILUTED},
    )
    assert observation.selected_facts[Metric.EPS_DILUTED] == 'zero-eps'
    assert Metric.EPS_DILUTED not in observation.missingness
    with pytest.raises(ValidationError):
        candidate(value=None)
    with pytest.raises(ValidationError):
        candidate(unit='shares')
    with pytest.raises(ValidationError):
        FiscalPeriod(start='2025-01-01', end='2025-01-01', fiscal_year=2025)
    with pytest.raises(ValidationError):
        CompanyIdentity(ticker='demo', name='Demo', cik='123', lookup_source='test',
                        lookup_at=datetime.now(UTC))
    with pytest.raises(ValidationError):
        ScreeningDecision(decision_id='screen', chunk_id='chunk', prompt_version='1',
                          probabilities={'relevant': 1.01}, decision='keep', reasons=[],
                          provider_call_id='call', actual_model='fake')


def test_repository_reference_and_immutability(tmp_path):
    DemoService(tmp_path).create('demo', 'T02')
    repo = Repository(tmp_path)
    with pytest.raises(ValueError, match='source reference'):
        repo.save_contract('demo', 'fact', candidate())
    filing = FilingRecord(filing_id='filing', cik='0001234567',
                          accession='0001234567-26-000001', form='10-K',
                          report_date='2025-12-31', filing_date='2026-02-15',
                          primary_document_url='synthetic:annual-2025', source_hash='a'*64)
    repo.save_contract('demo', 'filing', filing)
    block = SourceBlock(block_id='block', filing_id='filing', kind='paragraph',
                        text='Diluted EPS 0.00', ordinal=0)
    repo.save_contract('demo', 'block', block)
    evidence = EvidenceRef(evidence_id='evidence', filing_id='filing', block_id='block',
                           original_url='synthetic:annual-2025', local_anchor='#block-block',
                           exact_segments=['0.00'], source_hash='a'*64)
    with pytest.raises(ValueError, match='anchor mismatch'):
        repo.save_contract('demo', 'evidence', evidence.model_copy(update={'local_anchor':'#invented'}))
    repo.save_contract('demo', 'evidence', evidence)
    repo.save_contract('demo', 'fact', candidate())
    repo.save_contract('demo', 'fact', candidate())
    with pytest.raises(ValueError, match='Immutable'):
        repo.save_contract('demo', 'fact', candidate(value=Decimal(1)))
    assert json.loads(Repository(tmp_path).read('demo', 'fact'))['value'] == '0.00'
    (tmp_path/'runs/demo/fact.json').write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'):
        repo.read('demo', 'fact')


def test_offline_restart_fixtures_and_inspector(tmp_path, monkeypatch):
    monkeypatch.setenv('PROFITLAB_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('network used'))
    runner = CliRunner()
    result = runner.invoke(app, ['demo', '--through', 'T02', '--run-id', 'demo'])
    assert result.exit_code == 0, result.output
    assert runner.invoke(app, ['inspect', 'demo']).exit_code == 0
    original = (tmp_path/'runs/demo/manifest.json').read_bytes()
    assert runner.invoke(app, ['demo', '--run-id', 'demo']).exit_code == 2
    assert (tmp_path/'runs/demo/manifest.json').read_bytes() == original
    DemoService(tmp_path).create('two', 'T02', 'two-years')
    assert len(json.loads(Repository(tmp_path).read('two', 'submissions'))[
        'filings']['recent']['reportDate']) == 2
    gold = json.loads((__import__('pathlib').Path('tests/fixtures/synthetic/gold.json')).read_text())
    for year, metrics in gold.items():
        source = Repository(tmp_path).read('demo', f'annual-{year}').decode()
        for metric in ('net_income_common', 'eps_diluted', 'weighted_average_shares_diluted'):
            assert metrics[metric]['value'] in source
    for _ in range(2):
        client = TestClient(create_app(Settings(_env_file=None)))
        page = client.get('/runs/demo')
        assert page.status_code == 200
        assert '/artifacts/manifest' in page.text
        assert '1.00' in client.get('/runs/demo/artifacts/fixture-metadata').text
        assert '&lt;html&gt;' in client.get('/runs/demo/artifacts/annual-2025').text
    assert not any('gold' in a['artifact_id'] for a in Repository(tmp_path).artifacts('demo'))
    assert DemoService(tmp_path).get('two').covered_years == []  # stored inputs, not extraction


def test_runtime_never_reads_gold(tmp_path, monkeypatch):
    from pathlib import Path

    original = Path.open

    def guarded(path, *args, **kwargs):
        if 'gold' in path.name or 'tests' in path.parts:
            pytest.fail('Runtime must not load gold answers')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'open', guarded)
    DemoService(tmp_path).create('no-gold', 'T02')
