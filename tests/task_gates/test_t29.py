"""T29 renders compact, source-directed evaluation cards without changing verdicts."""
import asyncio
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.contracts import FactComparison, Finding, SourceRange, StructuredFact
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.web.app import create_app


def test_evaluation_cards_keep_outcomes_and_audit_details_separate(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='cards-t29')
    asyncio.run(pipeline.run('cards-t29', implement_source=True))
    document = pipeline.repo.canonical_document('cards-t29', pipeline.repo.canonical_refs('cards-t29')[0].document_id)
    source_range = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                               start_line=1, end_line=1, start_character=0, end_character=1)
    findings = [
        Finding(finding_id='scale-finding', exact_quote='237,789', source_range=source_range,
                amount=Decimal(237789), period='2025', unit='USD', validation_state='validated'),
        Finding(finding_id='mismatch-finding', exact_quote='3.00', source_range=source_range,
                amount=Decimal(3), period='2025', unit='USD/share', validation_state='validated'),
        Finding(finding_id='extra-finding', exact_quote='42', source_range=source_range,
                amount=Decimal(42), period='2025', unit='USD', validation_state='validated'),
    ]
    facts = [
        StructuredFact(fact_id='scale-fact', concept='NetIncomeLoss', metric='net_income_consolidated',
                       value=Decimal(237789000), unit='USD', period_end=date(2025, 12, 31),
                       accession='accession-scale', form='10-K', filed_date=date(2026, 2, 1)),
        StructuredFact(fact_id='mismatch-fact', concept='EarningsPerShareDiluted', metric='eps_diluted',
                       value=Decimal(2), unit='USD/share', period_end=date(2025, 12, 31),
                       accession='accession-mismatch', form='10-K', filed_date=date(2026, 2, 1)),
        StructuredFact(fact_id='missing-fact', concept='Shares', metric='weighted_average_shares_diluted',
                       value=Decimal(9), unit='shares', period_end=date(2025, 12, 31),
                       accession='accession-missing', form='10-K', filed_date=date(2026, 2, 1)),
    ]
    pipeline.repo.save_findings('cards-t29', findings)
    pipeline.repo.save_structured_facts('cards-t29', facts)
    pipeline.repo.save_comparisons('cards-t29', [
        FactComparison(comparison_id='scale-card', fact_id='scale-fact', metric='net_income_consolidated',
                       finding_ids=['scale-finding'], state='scale_aware_equivalent',
                       deterministic_state='period_match_value_mismatch', jev_verdict=True,
                       jev_model='fixture-evaluation-scale-v1', jev_prompt_version='evaluation-scale-v1'),
        FactComparison(comparison_id='mismatch-card', fact_id='mismatch-fact', metric='eps_diluted',
                       finding_ids=['mismatch-finding'], state='jev_rejected',
                       deterministic_state='period_match_value_mismatch', jev_verdict=False,
                       jev_model='fixture-evaluation-scale-v1', jev_prompt_version='evaluation-scale-v1'),
        FactComparison(comparison_id='missing-card', fact_id='missing-fact', metric='weighted_average_shares_diluted',
                       state='structured_fact_missed'),
        FactComparison(comparison_id='additional-card', metric='unclassified_visible_value',
                       finding_ids=['extra-finding'], state='additional_visible_value'),
    ])
    pipeline.repo.save_comparison_summary('cards-t29', {'expected_facts': 3, 'exact_matches': 0,
                                                        'misses': 1, 'additional_visible_numbers': 1})

    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/cards-t29/pipeline?stage=evaluate')

    assert page.status_code == 200
    assert 'comparison-card comparison-confirmed' in page.text
    assert 'Confirmed scale-aware equivalent' in page.text
    assert 'Rejected by Jev' in page.text
    assert 'Missing visible finding' in page.text
    assert 'Additional visible finding' in page.text
    assert '237789000' in page.text and '237789' in page.text
    assert 'Ground truth · match' in page.text
    assert 'Ground truth · mismatch' in page.text
    assert 'Heuristic evaluator' in page.text
    assert 'Jev verdict' in page.text
    assert 'Confirmed scale/unit support' in page.text
    assert '<strong>Rejected</strong>' in page.text
    assert 'Evidence, provenance, and diagnostics' in page.text
    assert 'Diagnostic JSON' in page.text
    assert 'accession-scale' in page.text
    assert 'data-comparison-filter' in page.text and 'v2-evaluation.js' in page.text
    assert '<table class="outline-table"><thead><tr><th>Expected fact' not in page.text


def test_evaluation_keeps_each_persisted_overlapping_finding_visible(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='duplicates-t29')
    asyncio.run(pipeline.run('duplicates-t29', implement_source=True))
    document = pipeline.repo.canonical_document('duplicates-t29', pipeline.repo.canonical_refs('duplicates-t29')[0].document_id)
    source_range = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                               start_line=1, end_line=1, start_character=0, end_character=1)
    finding = Finding(finding_id='first-citation', exact_quote='10', source_range=source_range,
                      amount=Decimal(10), period='2025', unit='USD', finding_type='annual_profit',
                      validation_state='validated')
    duplicate = finding.model_copy(update={'finding_id': 'second-citation'})
    fact = StructuredFact(fact_id='income-fact', concept='NetIncomeLoss', metric='net_income_consolidated',
                          value=Decimal(10), unit='USD', period_end=date(2025, 12, 31),
                          accession='accession', form='10-K', filed_date=date(2026, 2, 1))
    pipeline.repo.save_findings('duplicates-t29', [finding, duplicate])
    pipeline.repo.save_structured_facts('duplicates-t29', [fact])
    result = EvaluationService(pipeline.repo).compare('duplicates-t29')
    assert result.comparisons[0].finding_ids == ['first-citation', 'second-citation']

    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/duplicates-t29/pipeline?stage=evaluate')

    assert page.status_code == 200
    assert page.text.count('Open source quote') == 2


def test_remove_run_button_deletes_only_its_owned_data(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='remove-t29')
    pipeline.create(run_id='keep-t29')
    asyncio.run(pipeline.run('remove-t29', implement_source=True))

    with TestClient(create_app(settings)) as client:
        home = client.get('/')
        removed = client.post('/v2/runs/remove-t29/remove', follow_redirects=False)
        after = client.get('/')

    assert 'Remove run' in home.text
    assert removed.status_code == 303 and removed.headers['location'] == '/'
    assert 'remove-t29' not in after.text
    assert 'keep-t29' in after.text
    with pytest.raises(FileNotFoundError):
        pipeline.repo.get_run('remove-t29')
    assert pipeline.repo.get_run('keep-t29').run_id == 'keep-t29'


def test_clear_shared_cache_button_preserves_runs(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='cache-t29')
    asyncio.run(pipeline.run('cache-t29', implement_source=True))
    with pipeline.repo.connect() as db:
        before = db.execute('SELECT COUNT(*) FROM outline_batches').fetchone()[0]
    assert before > 0

    with TestClient(create_app(settings)) as client:
        home = client.get('/')
        cleared = client.post('/v2/cache/clear', follow_redirects=False)
        static = client.get('/static/v2.css')

    assert 'Clear shared provider cache' in home.text
    assert home.headers['cache-control'] == static.headers['cache-control'] == 'no-store'
    assert cleared.status_code == 303 and cleared.headers['location'] == '/'
    assert pipeline.repo.get_run('cache-t29').run_id == 'cache-t29'
    assert pipeline.repo.canonical_refs('cache-t29')
    with pipeline.repo.connect() as db:
        assert all(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0 for table in (
            'outline_batches', 'section_score_batches', 'chunk_score_batches',
            'finding_batches', 'evaluation_scale_verdicts',
        ))
