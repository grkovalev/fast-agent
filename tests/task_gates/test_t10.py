"""Reconciliation acceptance: no forced winners, source-preserving coverage."""
import json
import socket
from decimal import Decimal
from html import unescape

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from profitlab.analysis.reconciliation import (
    ReconciliationService,
    comparison_key,
    precision_matches,
    select_group,
)
from profitlab.cli import app
from profitlab.contracts.facts import FactCandidate, Metric
from profitlab.demo import DemoService
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder
from profitlab.web.app import create_app


def fact(cid='a', raw='2.00', **changes):
    return FactCandidate.model_validate({
        'candidate_id': cid, 'metric': 'eps_diluted', 'raw_label': 'Diluted EPS',
        'raw_numeric_text': raw, 'value': raw, 'currency': 'USD', 'unit': 'currency_per_share',
        'period': {'start': '2025-01-01', 'end': '2025-12-31', 'fiscal_year': 2025},
        'annuality': 'annual', 'basis': 'gaap', 'scope': 'consolidated', 'attribution': 'common',
        'extraction_method': 'table', 'evidence_ids': ['evidence-' + cid],
        'validation_results': {k: True for k in ('source', 'numeric', 'period', 'unit', 'scope', 'basis')},
        **changes})


def contexts(candidates, **changes):
    return {c.candidate_id: {'filing_date': '2026-02-01', 'clarity': 2,
        'visible_labels': 1, 'adjustment': None, 'evidence_ids': c.evidence_ids,
        **changes.get(c.candidate_id, {})} for c in candidates}


def test_comparable_keys_and_invalid_context():
    a = fact()
    for changes in ({'annuality': 'quarterly'}, {'basis': 'adjusted'}, {'scope': 'segment'},
                    {'share_class': 'Class B'}, {'attribution': 'parent'}, {'currency': 'EUR'},
                    {'period': {'start': '2025-02-01', 'end': '2025-12-31', 'fiscal_year': 2025}},
                    {'metric': 'net_income_parent', 'unit': 'currency'}):
        assert comparison_key(a) != comparison_key(fact('b', **changes))
    for changes in ({'annuality': 'quarterly'}, {'basis': 'adjusted'}, {'scope': 'segment'},
                    {'validation_results': {}}, {'validation_results': {'source': False}}):
        c = fact(**changes)
        group, decisions = select_group([c], contexts([c]))
        assert group.selected_id is None
        assert decisions['a']['status'] == 'rejected'


def test_duplicates_precision_and_unexplained_conflicts():
    a, b, c = fact(), fact('b'), fact('c', '2.25')
    group, decisions = select_group([a, b], contexts([a, b], b={'filing_date': '2026-03-01'}))
    assert group.selected_id == 'b'
    assert group.duplicate_groups == [['a', 'b']]
    assert decisions['a']['reason_code'] == 'R6_DUPLICATE'
    with pytest.raises(ValueError):
        select_group([a, fact('quarter', annuality='quarterly')], contexts([a]))
    with pytest.raises(ValueError):
        type(group).model_validate({**group.model_dump(), 'duplicate_groups': [['a', 'unknown']]})
    with pytest.raises(ValueError):
        type(group).model_validate({**group.model_dump(), 'latest_comparative_id': 'unknown'})
    group, decisions = select_group([a, b, c], contexts([a, b, c], c={'filing_date': '2026-04-01'}))
    assert group.selected_id is None and group.unresolved_conflicts
    assert all(d['status'] == 'conflicting' for d in decisions.values())
    precise, coarse = fact('precise', '1.234'), fact('coarse', '1.23')
    assert precision_matches(precise, coarse)
    group, _ = select_group([precise, coarse], contexts([precise, coarse]))
    assert group.selected_id == 'precise'
    assert not precision_matches(fact('a', '1.23'), fact('b', '1.24'))
    # Do not chain two disagreeing fine values through a coarse bridge.
    chain = [fact('a', '1.231'), fact('b', '1.23'), fact('c', '1.234')]
    assert select_group(chain, contexts(chain))[0].selected_id is None
    assert precision_matches(fact('a', '-1.234'), fact('b', '-1.23'))
    assert precision_matches(fact('a', '1234', value='1234000', scale='1000'),
                             fact('b', '1.234', value='1234000', scale='1000000'))


def test_documented_replacement_and_same_date_conflict():
    a, b = fact(), fact('b', '1.00')
    ctx = contexts([a, b], b={'filing_date': '2026-03-01', 'adjustment': 'split-adjusted'})
    group, decisions = select_group([a, b], ctx)
    assert group.selected_id == 'b'
    assert decisions['a']['reason_code'] == 'R4_DOCUMENTED_COMPARATIVE'
    # A label on an older presentation cannot authorize a newer discrepancy.
    ctx['a']['adjustment'], ctx['b']['adjustment'] = 'restated', None
    assert select_group([a, b], ctx)[0].selected_id is None
    ctx['a']['filing_date'] = ctx['b']['filing_date']
    ctx['b']['adjustment'] = 'restated'
    assert select_group([a, b], ctx)[0].selected_id is None
    ctx['a']['filing_date'] = '2026-02-01'
    ctx['b']['crosscheck_conflict'] = True
    assert select_group([a, b], ctx)[0].selected_id is None


@pytest.mark.parametrize('scenario', ['normal', 'conflict', 'restatement', 'split-adjusted', 'two-years'])
def test_real_offline_pipeline_selection_provenance_and_ui(tmp_path, monkeypatch, scenario):
    monkeypatch.setenv('PROFITLAB_DATA_DIR', str(tmp_path))
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))
    # Runtime may read source fixtures, but never gold answers.
    from pathlib import Path
    original = Path.open
    def guarded(path, *a, **kw):
        if 'gold' in path.name:
            pytest.fail('Gold answers read by runtime')
        return original(path, *a, **kw)
    monkeypatch.setattr(Path, 'open', guarded)
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    run = DemoService(tmp_path).create('reconcile-test', 'T10', scenario)
    assert run.stage == 'reconcile'
    service = ReconciliationService(settings)
    index, groups, observations = service.latest(run.run_id)
    assert len(index['coverage']) == (2 if scenario == 'two-years' else 4)
    eps2025 = next(g for g in groups if g.metric == Metric.EPS_DILUTED and g.period.fiscal_year == 2025)
    if scenario == 'conflict':
        assert eps2025.selected_id is None and eps2025.unresolved_conflicts
        row = next(r for r in index['coverage'] if r['fiscal_year'] == 2025)
        assert row['metrics']['eps_diluted']['status'] == 'conflicting'
        assert next(o for o in observations if o.period.fiscal_year == 2025).missingness[Metric.EPS_DILUTED] == 'conflicting'
    else:
        assert eps2025.selected_id
        fact2025 = json.loads(service.repo.read(run.run_id, eps2025.selected_id))
        assert Decimal(fact2025['value']) == (Decimal('1.00') if scenario == 'split-adjusted' else Decimal('2.00'))
        assert all(r['metrics']['net_income_common']['status'] == 'selected' for r in index['coverage'])
    if scenario == 'normal':
        assert len(eps2025.duplicate_groups[0]) >= 2
        assert len([p for p in index['passages'] if p['year'] == 2025]) == 1
        assert len(next(p for p in index['passages'] if p['year'] == 2025)['evidence_ids']) == 2
    if scenario in ('restatement', 'split-adjusted'):
        eps2024 = next(g for g in groups if g.metric == Metric.EPS_DILUTED and g.period.fiscal_year == 2024)
        chosen = json.loads(service.repo.read(run.run_id, eps2024.selected_id))
        assert Decimal(chosen['value']) == (Decimal('1.65') if scenario == 'restatement' else Decimal('0.80'))
        assert any(d['reason_code'] == 'R4_DOCUMENTED_COMPARATIVE' for d in index['decisions'].values())
        assert all(any('per_share_basis:' in f for f in o.comparability_flags) for o in observations)
        assert not any('Mixed original' in f for o in observations for f in o.comparability_flags)
    assert all(r['metrics']['net_income_parent']['status'] == 'missing' for r in index['coverage'])
    with TestClient(create_app(settings)) as client:
        page = client.get('/runs/reconcile-test/candidates')
        assert page.status_code == 200
        assert 'Annual metric coverage' in page.text
        assert 'Selections and competing sources' in page.text
        assert 'Unresolved conflict' in page.text if scenario == 'conflict' else 'Selected' in page.text
        import re
        links = re.findall(r'href="([^"]*sources/[^"]+)"', page.text)
        # Verify a representative cited cell from every saved filing; repeated
        # links to the same source are already covered by the candidate/evidence
        # reference checks, without repeatedly rendering the large source fixture.
        by_filing = {link.split('?')[0]: link for link in links}
        assert links and all(client.get(unescape(link)).status_code == 200 for link in by_filing.values())
        assert 'selected-row' in client.get(unescape(links[0])).text
        assert client.get('/runs/reconcile-test/trace?stage=reconcile').status_code == 200
    assert ReconciliationService(settings).latest(run.run_id)[0] == index
    events, warnings = TraceRecorder(Repository(tmp_path), run.run_id).history()
    assert not warnings and any(e.kind == 'selection' and e.stage == 'reconcile' for e in events)
    # Repeat creates an immutable new index but equivalent group/observation IDs.
    result = CliRunner().invoke(app, ['stage', run.run_id, 'reconcile'])
    assert result.exit_code == 0, result.output
    newindex, newgroups, newobs = service.latest(run.run_id)
    assert newindex['group_ids'] == index['group_ids']
    assert newindex['observation_ids'] == index['observation_ids']
    assert newgroups == groups and newobs == observations
    if scenario == 'normal':
        from profitlab.providers.extraction import ExtractionService

        ExtractionService(settings).progress(run.run_id)
        with TestClient(create_app(settings)) as client:
            page = client.get('/runs/reconcile-test/candidates')
            assert page.status_code == 200
            assert 'Extraction has changed since selection' in page.text
            assert 'Selections and competing sources' not in page.text


def test_missing_class_period_and_contextual_income_coverage(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    from datetime import UTC, datetime

    from profitlab.contracts.base import RunManifest
    run = RunManifest(run_id='unit', mode='demo', ticker='DEMO', covered_years=[2024, 2025],
                      created_at=datetime.now(UTC), updated_at=datetime.now(UTC))
    a, b = fact('a', share_class='A'), fact('b', share_class='B')
    parent = fact('parent', metric='net_income_parent', unit='currency', attribution='parent')
    facts = {c.candidate_id: c for c in [a, b, parent]}
    ctx = contexts(list(facts.values()))
    groups = [select_group([c], ctx)[0] for c in facts.values()]
    obs, rows = ReconciliationService(settings).coverage(run, facts, groups, ctx)
    row = rows[0]
    assert row['metrics']['eps_diluted']['status'] == 'conflicting'
    assert row['metrics']['net_income_common']['status'] == 'missing'
    assert row['metrics']['net_income_parent']['status'] == 'selected'
    assert rows[1]['fiscal_year'] == 2024 and rows[1]['periods'] == []
    assert len(obs) == 1  # no invented fiscal dates for missing 2024
    # A single split-adjusted year cannot quietly establish a comparable series.
    adjusted = fact('adjusted', period={'start': '2024-01-01', 'end': '2024-12-31', 'fiscal_year': 2024})
    pair = [a, adjusted]
    ctx = contexts(pair, adjusted={'adjustment': 'split-adjusted'})
    obs, rows = ReconciliationService(settings).coverage(run, {c.candidate_id: c for c in pair},
        [select_group([c], ctx)[0] for c in pair], ctx)
    assert all(any('Mixed original' in f for f in row['comparability_flags']) for row in rows)
