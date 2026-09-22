"""T27 outline-aware, current-year findings requests."""
import asyncio

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.findings_service import FindingsService


def test_findings_request_sends_validated_outline_once_with_current_report_year(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        chunk_target_tokens=100, chunk_overlap_tokens=40,
                        chunk_question_overhead=500, chunk_request_budget=1000,
                        outline_window_lines=100, section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='outline-findings-t27')
    asyncio.run(pipeline.run('outline-findings-t27', implement_source=True))
    document_ref = pipeline.repo.canonical_refs('outline-findings-t27')[0]
    document = pipeline.repo.canonical_document('outline-findings-t27', document_ref.document_id)
    chunks = pipeline.repo.chunks('outline-findings-t27')
    sections = pipeline.repo.outline_sections('outline-findings-t27')
    state = FindingsService(settings, pipeline.repo)._request_data(
        'outline-findings-t27', document, chunks,
        pipeline.repo.scores('outline-findings-t27', 'chunk_score'))

    assert state['filing_metadata']['current_report_year'] == '2025'
    assert state['requested_value_period'] == 'current fiscal-reporting year'
    assert [item['section_id'] for item in state['validated_outline']] == [
        item.section_id for item in sections]
    assert len({item['section_id'] for item in state['validated_outline']}) == len(sections)
    assert {item['outline_section_id'] for item in state['retained_chunks']} <= {
        item['section_id'] for item in state['validated_outline']}
    assert 'contextRef' not in str(state) and 'structured_facts' not in state

    recorded = pipeline.repo.exploration_actions('outline-findings-t27', 'findings')[0]['request']
    assert recorded['validated_outline'] == state['validated_outline']
    assert recorded['filing_metadata']['current_report_year'] == '2025'
    summary = pipeline.repo.finding_summary('outline-findings-t27')
    assert summary['current_report_year'] == '2025'
    assert summary['outline_context_characters'] > 0
    assert summary['retained_evidence_characters'] > 0


def test_current_year_period_may_use_separate_retained_chunk_context(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        chunk_target_tokens=100, chunk_overlap_tokens=40,
                        chunk_question_overhead=500, chunk_request_budget=1000,
                        outline_window_lines=100, section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='period-proof-t27')
    asyncio.run(pipeline.run('period-proof-t27', implement_source=True))
    document_ref = pipeline.repo.canonical_refs('period-proof-t27')[0]
    document = pipeline.repo.canonical_document('period-proof-t27', document_ref.document_id)
    chunk = next(item for item in pipeline.repo.chunks('period-proof-t27') if any(
        '2025' not in line.text and line.text for line in document.lines[
            item.core_range.start_line - 1:item.core_range.end_line]))
    quote = next(line.text for line in document.lines[chunk.core_range.start_line - 1:
                                                      chunk.core_range.end_line]
                 if '2025' not in line.text and line.text)
    finding, reason = FindingsService(settings, pipeline.repo)._validate(document, [chunk], {
        'source_chunk_id': chunk.chunk_id, 'exact_quote': quote, 'period': '2025',
    }, 'controlled')

    assert reason is None
    assert finding is not None and finding.period == '2025'
