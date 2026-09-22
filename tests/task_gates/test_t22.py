"""T22 comparison remains an independent, exact-Decimal evaluation."""
import asyncio
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.contracts import Finding, SourceRange, StructuredFact
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.web.app import create_app


def settings_for(tmp_path):
    return Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                    chunk_target_tokens=100, chunk_overlap_tokens=40,
                    chunk_question_overhead=500, chunk_request_budget=1000,
                    outline_window_lines=100, section_score_batch_size=2)


def test_comparison_has_exact_decimal_states_and_never_mutates_discovery(tmp_path):
    settings = settings_for(tmp_path)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='evaluation-t22')
    asyncio.run(pipeline.run('evaluation-t22', implement_source=True))
    document = pipeline.repo.canonical_document(
        'evaluation-t22', pipeline.repo.canonical_refs('evaluation-t22')[0].document_id)
    source = document.lines[0]
    source_range = SourceRange(document_id=document.ref.document_id,
                               source_hash=document.ref.source_hash,
                               start_line=source.line_number, end_line=source.line_number,
                               start_character=0, end_character=1)
    facts = [
        StructuredFact(fact_id='fact-income', concept='us-gaap:NetIncomeLoss',
                       metric='net_income_consolidated', value=Decimal(10), unit='USD',
                       period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
                       accession='0001234567-25-000001', form='10-K', filed_date=date(2026, 2, 15)),
        StructuredFact(fact_id='fact-eps', concept='us-gaap:EarningsPerShareDiluted',
                       metric='eps_diluted', value=Decimal(2), unit='USD/shares',
                       period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
                       accession='0001234567-25-000001', form='10-K', filed_date=date(2026, 2, 15)),
        StructuredFact(fact_id='fact-shares', concept='us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding',
                       metric='weighted_average_shares_diluted', value=Decimal(9), unit='shares',
                       period_start=date(2025, 1, 1), period_end=date(2025, 12, 31),
                       accession='0001234567-25-000001', form='10-K', filed_date=date(2026, 2, 15)),
    ]
    def finding(identifier, target, value, period, unit):
        quote = f'{source.text[:1]} {identifier}'
        return Finding(finding_id=identifier, narrative='Visible number.', exact_quote=quote,
                       source_range=source_range, target=target, raw_number=quote,
                       normalized_value=Decimal(value), period=period, unit=unit,
                       validation_state='validated')
    findings = [finding('finding-exact', 'annual_profit', '10', 'FY 2025', 'USD'),
                finding('finding-mismatch', 'diluted_eps', '3', '2025', 'USD/shares'),
                finding('finding-unresolved', 'diluted_shares', '9', None, 'shares'),
                finding('finding-unsupported', 'comparability', '1', '2025', 'USD')]
    pipeline.repo.save_structured_facts('evaluation-t22', facts)
    pipeline.repo.save_findings('evaluation-t22', findings)
    before = [item.model_dump_json() for item in pipeline.repo.findings('evaluation-t22')]
    result = EvaluationService(pipeline.repo).compare('evaluation-t22')
    assert {item.state for item in result.comparisons} >= {
        'exact_match', 'period_match_value_mismatch', 'value_match_period_unresolved', 'unsupported'}
    assert result.summary['expected_facts'] == 3
    assert result.summary['exact_matches'] == 1
    assert result.summary['discovery_output_mutated'] is False
    assert [item.model_dump_json() for item in pipeline.repo.findings('evaluation-t22')] == before


def test_offline_evaluation_is_persisted_and_rendered(tmp_path):
    settings = settings_for(tmp_path)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='evaluation-ui-t22')
    asyncio.run(pipeline.run('evaluation-ui-t22', implement_source=True))
    assert pipeline.repo.stage('evaluation-ui-t22', 'evaluate').status == 'completed'
    assert pipeline.repo.comparisons('evaluation-ui-t22')
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/evaluation-ui-t22?stage=evaluate')
    assert page.status_code == 200
    assert 'Independent fiscal-year comparison' in page.text
    assert 'Evaluation did not modify discovery' in page.text
