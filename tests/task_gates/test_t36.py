"""T36 cross-run strict-exact scorecard contracts."""
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.contracts import FactComparison, StageSnapshot, StructuredFact, V2Run
from profitlab.v2.evaluation_service import cross_run_scorecard
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def _run(repo, run_id, ticker, *, completed=True):
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id=run_id, ticker=ticker, created_at=now, updated_at=now))
    if completed:
        repo.update_stage(StageSnapshot(run_id=run_id, stage='evaluate', position=8,
                                        status='completed', completed_work=1, total_work=1),
                          event_kind='stage_finished', event_summary='done')


def _fact(fact_id, metric='net_income_consolidated'):
    return StructuredFact(fact_id=fact_id, concept='us-gaap:NetIncomeLoss', metric=metric,
                          value=Decimal(10), unit='USD', period_end=date(2025, 12, 31),
                          accession='0000000000-25-000001', form='10-K', filed_date=date(2026, 2, 1))


def test_multi_run_scorecard_counts_unsupported_assumed_mapping_as_false_positive(tmp_path):
    repo = V2Repository(tmp_path)
    _run(repo, 'run-one', 'ONE')
    _run(repo, 'run-two', 'TWO')
    repo.save_structured_facts('run-one', [_fact('fact-tp'), _fact('fact-fn', 'eps_diluted')])
    repo.save_comparisons('run-one', [
        FactComparison(comparison_id='tp', metric='net_income_consolidated', fact_id='fact-tp', state='exact_match'),
        FactComparison(comparison_id='fn', metric='eps_diluted', fact_id='fact-fn', state='structured_fact_missed'),
        FactComparison(comparison_id='incomparable', metric='eps_diluted', fact_id='fact-fn', state='period_match_unit_mismatch'),
    ])
    repo.save_comparisons('run-two', [
        FactComparison(comparison_id='fp', metric='net_income_consolidated', state='additional_visible_value'),
        FactComparison(comparison_id='unsupported-fp', state='unsupported'),
    ])

    scorecard = cross_run_scorecard(repo)

    matrix = scorecard['modes']['deterministic']
    assert {key: matrix[key] for key in ('true_positives', 'false_positives', 'false_negatives', 'incomparable')} == {
        'true_positives': 1, 'false_positives': 2, 'false_negatives': 1, 'incomparable': 1}
    assert matrix['precision'] == 1 / 3
    assert matrix['recall'] == .5
    assert matrix['f1'] == .4
    assert matrix['true_negatives'] is None
    assert len(scorecard['ledger']) == 2
    assert repo.evaluation_scorecard(scorecard['configuration_hash'])['input_hash'] == scorecard['input_hash']


def test_incomplete_run_is_accounted_and_zero_denominators_are_unavailable(tmp_path):
    repo = V2Repository(tmp_path)
    _run(repo, 'run-pending', 'PEND', completed=False)

    scorecard = cross_run_scorecard(repo)

    assert scorecard['ledger'] == [{'run_id': 'run-pending', 'ticker': 'PEND', 'included': False,
                                    'reason': 'evaluate stage is queued'}]
    assert scorecard['modes']['deterministic']['precision'] is None
    assert scorecard['modes']['deterministic']['recall'] is None
    assert scorecard['modes']['deterministic']['f1'] is None


def test_scorecard_route_displays_denominators_and_comparison_links(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    _run(repo, 'run-route', 'ROUTE')
    repo.save_comparisons('run-route', [
        FactComparison(comparison_id='additional-route', metric='diluted_eps', state='additional_visible_value'),
    ])

    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/benchmark')

    assert page.status_code == 200
    assert 'Positive denominator 0; predicted-positive denominator 1.' in page.text
    assert '/v2/runs/run-route/pipeline/evaluate#comparison-additional-route' in page.text
    assert 'accepted visible value with no supported configured target is a false positive' in page.text
