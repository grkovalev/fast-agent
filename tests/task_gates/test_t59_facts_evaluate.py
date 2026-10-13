"""Facts acquisition and evaluation keep control, data, and optional calls distinct."""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.contracts import V2Run
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.v2.facts_service import FACT_TARGETS, CompanyFactsService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_facts_and_evaluate_overview_has_independent_inputs_and_bypass(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, evaluation_scale_max_pairs=0,
                        _env_file=None)
    V2Repository(tmp_path).create_run(V2Run(
        run_id='facts-evaluate-map', ticker='MAP',
        created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    with TestClient(create_app(settings)) as client:
        html = client.get('/v2/runs/facts-evaluate-map/pipeline').text
    facts = html.split('data-facts-card', 1)[1].split('data-stage-accounting="facts"', 1)[0]
    evaluate = html.split('data-evaluate-card', 1)[1].split('data-stage-accounting="evaluate"', 1)[0]

    assert 'SCHEDULING GATE FROM FINDINGS' in facts
    assert 'Finding amounts are never normalization inputs' in facts
    assert facts.index('Company CIK + selected filing') < facts.index('Retrieve Company Facts JSON')
    assert facts.index('Retrieve Company Facts JSON') < facts.index('Select same-filing annual rows')
    assert 'unselected alternatives' in facts
    assert 'FROM FINDINGS ABOVE ↓' in evaluate
    assert 'FROM FACTS BELOW ↑' in evaluate
    assert 'Direct path to record ↘' in evaluate
    assert 'Current configuration allows zero verification pairs' in evaluate
    assert 'Current maximum: 0 pair(s)' in evaluate
    assert 'FactComparison' in evaluate
    for station in ('checkpoint', 'retrieve', 'normalize', 'store'):
        assert f'data-facts-station="{station}"' in facts
    for station in ('pair', 'compare', 'verify', 'record'):
        assert f'data-evaluate-station="{station}"' in evaluate


def test_inspection_uses_runtime_mapping_and_request_builder(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, evaluation_scale_max_pairs=2,
                        _env_file=None)
    facts = CompanyFactsService.inspection_view()
    evaluate = EvaluationService.inspection_view(settings)
    mapping = facts['normalize']['policy']['concept_mapping']
    assert [row['concept'] for row in mapping] == [entry[1] for entry in FACT_TARGETS]
    assert 'Finding values are not read' in facts['checkpoint']['does']
    assert evaluate['verify']['request']['maximum_pairs'] == 2
    assert evaluate['verify']['request']['questions']['same_visible_scaled_value']['instructions'] == (
        'Are these the same annual metric/value after an explicitly visible scale or unit?')
    assert 'period_match_value_mismatch' in evaluate['verify']['accepts']['deterministic_state']
