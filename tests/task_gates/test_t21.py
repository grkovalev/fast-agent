"""T21 Company Facts must be strictly post-discovery and independently persisted."""
import asyncio
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.facts_service import CompanyFactsService
from profitlab.web.app import create_app


def settings_for(tmp_path):
    return Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                    chunk_target_tokens=100, chunk_overlap_tokens=40,
                    chunk_question_overhead=500, chunk_request_budget=1000,
                    outline_window_lines=100, section_score_batch_size=2)


def test_company_facts_are_sealed_after_findings_and_keep_exact_provenance(tmp_path):
    settings = settings_for(tmp_path)
    pipeline = V2PipelineService(settings)
    run = pipeline.create(run_id='facts-t21')
    with pytest.raises(ValueError, match='Findings must be sealed'):
        CompanyFactsService(settings, pipeline.repo).load(run)

    asyncio.run(pipeline.run(run.run_id, implement_source=True))
    facts = pipeline.repo.structured_facts(run.run_id)
    summary = pipeline.repo.fact_summary(run.run_id)
    dataset = pipeline.repo.company_fact_dataset(run.run_id)

    assert pipeline.repo.stage(run.run_id, 'facts').status == 'completed'
    assert {item.metric for item in facts} == {
        'net_income_consolidated', 'eps_diluted', 'weighted_average_shares_diluted'}
    assert next(item.value for item in facts if item.metric == 'net_income_consolidated') == Decimal(180000000)
    assert all(item.accession == '0001234567-25-000001' and item.form == '10-K' for item in facts)
    assert all(item.period_start and item.period_end.isoformat() == '2025-12-31' for item in facts)
    assert summary['alternatives'] and dataset['source_hash'] == pipeline.repo.stage(run.run_id, 'facts').output_hash
    # Discovery requests were recorded before the facts stage and cannot acquire the dataset.
    findings_request = pipeline.repo.exploration_actions(run.run_id, 'findings')[0]['request']
    assert 'company_facts' not in str(findings_request).lower()


def test_facts_workspace_shows_mapping_and_duplicate_alternatives(tmp_path):
    settings = settings_for(tmp_path)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='facts-ui-t21')
    asyncio.run(pipeline.run('facts-ui-t21', implement_source=True))
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/facts-ui-t21?stage=facts')
    assert page.status_code == 200
    assert 'Independent structured facts' in page.text
    assert 'NetIncomeLoss' in page.text
    assert 'alternative(s)' in page.text
