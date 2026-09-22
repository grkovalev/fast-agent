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
    assert len({(item.exact_quote, item.raw_number) for item in findings}) == len(findings)
    request = pipeline.repo.exploration_actions('workspace-t20', 'findings')[0]['request']
    assert 'contextRef' not in str(request) and 'us-gaap:' not in str(request)
    assert 'structured_facts' not in request
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/workspace-t20?stage=findings')
    assert page.status_code == 200
    assert 'Quote-backed findings' in page.text
    assert 'Open exact source quote' in page.text
