"""T31 replays reviewed ranges only after retrieval; gold never reaches Jev."""
import asyncio
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.benchmark import (
    BenchmarkCase,
    BenchmarkDataset,
    RequiredFact,
    RetrievalBenchmarkService,
    ReviewedRange,
)
from profitlab.v2.contracts import Finding, SourceRange, StructuredFact
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.web.app import create_app


def test_benchmark_replays_pinned_strategies_and_renders_clickable_misses(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        chunk_target_tokens=100, chunk_overlap_tokens=40,
                        chunk_question_overhead=500, chunk_request_budget=1000,
                        outline_window_lines=100, section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='benchmark-t31')
    asyncio.run(pipeline.run('benchmark-t31', implement_source=True))
    automatic = pipeline.repo.retrieval_benchmark('benchmark-t31')
    assert automatic['case']['label_source'] == 'automatic_post_run'
    assert automatic['configuration']['provider_identity'] == 'automatic post-run replay'
    assert all(item['relevant_range_recall'] is None for item in automatic['results'])
    document = pipeline.repo.canonical_document('benchmark-t31', pipeline.repo.canonical_refs('benchmark-t31')[0].document_id)
    evidence = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                           start_line=1, end_line=1, start_character=0, end_character=1)
    fact = StructuredFact(fact_id='benchmark-income', concept='NetIncomeLoss',
                          metric='net_income_consolidated', value=Decimal(10), unit='USD',
                          period_end=date(2025, 12, 31), accession='fixture-accession', form='10-K',
                          filed_date=date(2026, 2, 1))
    finding = Finding(finding_id='benchmark-finding', exact_quote='10', source_range=evidence,
                      amount=Decimal(10), period='2025', unit='USD', finding_type='annual_profit',
                      validation_state='validated')
    pipeline.repo.save_structured_facts('benchmark-t31', [fact])
    pipeline.repo.save_findings('benchmark-t31', [finding])
    EvaluationService(pipeline.repo).compare('benchmark-t31')
    case = BenchmarkCase(case_id='heldout-demo', split='held_out', company_id='DEMO', accession='',
                         source_hash=document.ref.source_hash,
                         reviewed_ranges=[ReviewedRange(range=evidence, kind='relevant')],
                         required_facts=[RequiredFact(metric='net_income_consolidated', fiscal_year=2025,
                                                      evidence_range=evidence)])

    before_actions = pipeline.repo.exploration_actions('benchmark-t31', 'section_score')
    result = RetrievalBenchmarkService(pipeline.repo, settings).evaluate('benchmark-t31', case)

    assert len(result.payload['results']) == 7
    assert result.payload['gold_access'].startswith('post-run')
    assert pipeline.repo.exploration_actions('benchmark-t31', 'section_score') == before_actions
    keep_all = next(item for item in result.payload['results'] if item['strategy'] == 'keep_all')
    assert keep_all['relevant_range_recall'] == keep_all['structured_fact_coverage'] == 1
    assert keep_all['exact_value_accuracy'] == 1 and keep_all['wrong_metric_or_year_values'] == 0
    dataset = BenchmarkDataset(dataset_version='test-v1', cases=[case])
    with TestClient(create_app(settings, benchmark_dataset=dataset)) as client:
        rerun = client.post('/v2/runs/benchmark-t31/benchmark', follow_redirects=False)
        recalculate = client.post('/v2/benchmark/regenerate', follow_redirects=False)
        page = client.get('/v2/benchmark')
    assert rerun.status_code == 303
    assert recalculate.status_code == 303
    assert 'Cross-run evaluation' in page.text
    assert 'Jev Section Chunk' in page.text
    assert 'Automatic labels' in page.text
    assert 'Reviewed recall' not in page.text and 'Not reviewed' not in page.text
    assert 'Exact-value accuracy' in page.text and 'Provider calls' in page.text
    assert 'no labels are sent to Jev or the findings model' in page.text
