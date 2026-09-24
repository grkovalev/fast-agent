"""T20 quote-backed findings and visible-number extraction."""
import asyncio

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.findings_service import FindingsService
from profitlab.web.app import create_app


def test_findings_reject_invalid_quote_and_resolve_valid_quote_to_exact_anchor(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        chunk_target_tokens=100, chunk_overlap_tokens=40,
                        chunk_question_overhead=500, chunk_request_budget=1000,
                        outline_window_lines=100, section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='quotes-t20')
    asyncio.run(pipeline.run('quotes-t20', implement_source=True))
    document = pipeline.repo.canonical_document(
        'quotes-t20', pipeline.repo.canonical_refs('quotes-t20')[0].document_id)
    chunks = pipeline.repo.chunks('quotes-t20')
    service = FindingsService(settings, pipeline.repo)
    rejected, reason = service._validate(document, chunks, {
        'source_chunk_id': chunks[0].chunk_id,
        'source_line': chunks[0].core_range.start_line,
        'exact_quote': 'invented oracle value',
        'amount': '1',
    }, 'controlled')
    assert rejected is None and 'exact substring' in reason

    findings = pipeline.repo.findings('quotes-t20')
    assert findings and all(item.validation_state == 'validated' for item in findings)
    for item in findings:
        assert item.exact_quote == document.slice(item.source_range)
        assert document.anchor_for(item.source_range).startswith('v2-line-')
        assert item.source_chunk_id in {chunk.chunk_id for chunk in chunks}
        source_chunk = next(chunk for chunk in chunks if chunk.chunk_id == item.source_chunk_id)
        assert source_chunk.core_range.start_line <= item.source_range.start_line <= source_chunk.core_range.end_line


def test_offline_findings_are_persisted_deduplicated_and_rendered(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        chunk_target_tokens=100, chunk_overlap_tokens=40,
                        chunk_question_overhead=500, chunk_request_budget=1000,
                        outline_window_lines=100, section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='workspace-t20')
    asyncio.run(pipeline.run('workspace-t20', implement_source=True))
    findings = pipeline.repo.findings('workspace-t20')
    summary = pipeline.repo.finding_summary('workspace-t20')
    assert pipeline.repo.stage('workspace-t20', 'findings').status == 'completed'
    assert findings and summary['rejected'] == 0
    assert len({(item.exact_quote, item.amount) for item in findings}) == len(findings)
    request = pipeline.repo.exploration_actions('workspace-t20', 'findings')[0]['request']
    assert 'contextRef' not in str(request) and 'us-gaap:' not in str(request)
    assert 'structured_facts' not in request
    type_requests = [item['request'] for item in pipeline.repo.exploration_actions('workspace-t20', 'findings')
                     if 'request' in item and 'allowed_finding_types' in item['request'].get('state', {})]
    assert type_requests
    assert all(item['state']['allowed_finding_types'] == [
        'annual_profit', 'diluted_eps', 'diluted_shares'] for item in type_requests)
    assert all(item['state']['validated_outline'] and
               item['state']['finding']['retained_chunk']['core_evidence_lines'] and
               item['state']['filing_metadata']['current_report_year'] == '2025'
               for item in type_requests)
    assert all('structured_fact' not in str(item) and 'us-gaap:' not in str(item).lower()
               for item in type_requests)
    # Fixture Jev intentionally cannot assign a real semantic type: ambiguity remains explicit.
    assert all(item.finding_type == 'unresolved' for item in findings)
    document = pipeline.repo.canonical_document(
        'workspace-t20', pipeline.repo.canonical_refs('workspace-t20')[0].document_id)
    asyncio.run(FindingsService(settings, pipeline.repo).build(
        'workspace-t20', document, pipeline.repo.chunks('workspace-t20'),
        pipeline.repo.scores('workspace-t20', 'chunk_score'), offline=True))
    replay = pipeline.repo.finding_summary('workspace-t20')
    assert replay['cached'] is True and replay['classification_calls'] == 0
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/workspace-t20?stage=findings')
    assert page.status_code == 200
    assert 'Quote-backed findings' in page.text
    assert 'Chunk retrieval signal:' in page.text
    assert 'Open exact source quote' in page.text


def test_findings_context_budget_falls_back_without_failing_the_run(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        findings_request_char_budget=1000, chunk_target_tokens=100,
                        chunk_overlap_tokens=40, chunk_question_overhead=500,
                        chunk_request_budget=1000, outline_window_lines=100,
                        section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='fallback-t20')

    asyncio.run(pipeline.run('fallback-t20', implement_source=True))

    stage = pipeline.repo.stage('fallback-t20', 'findings')
    summary = pipeline.repo.finding_summary('fallback-t20')
    assert stage.status == 'completed'
    assert summary['context_fallback'] is True
    assert 'Request budget fallback' in stage.summary


def test_finding_type_context_budget_leaves_valid_findings_unresolved(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        finding_type_request_char_budget=1000, chunk_target_tokens=100,
                        chunk_overlap_tokens=40, chunk_question_overhead=500,
                        chunk_request_budget=1000, outline_window_lines=100,
                        section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='type-budget-t20')

    asyncio.run(pipeline.run('type-budget-t20', implement_source=True))

    assert pipeline.repo.stage('type-budget-t20', 'findings').status == 'completed'
    findings = pipeline.repo.findings('type-budget-t20')
    summary = pipeline.repo.finding_summary('type-budget-t20')
    assert findings and all(item.finding_type == 'unresolved' for item in findings)
    assert summary['classification_calls'] == 0
    assert summary['classification_budget_limited'] == len(findings)
