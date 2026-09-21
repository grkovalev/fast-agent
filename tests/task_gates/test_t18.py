"""T18 source-range chunking invariants and workspace inspection."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService, canonicalize_html
from profitlab.v2.chunking import SourceRangeChunker
from profitlab.v2.contracts import OutlineSection, SourceRange
from profitlab.web.app import create_app


def test_selected_sections_chunk_by_atomic_lines_with_separate_bounded_overlap(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, chunk_target_tokens=100,
                        chunk_overlap_tokens=40, chunk_question_overhead=500,
                        chunk_request_budget=1000)
    document, _ = canonicalize_html(b'''<html><body><h1>Selected</h1>
        <p>Alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha alpha.</p><table><tr><td>Annual profit</td><td>100</td></tr>
        <tr><td>Diluted shares</td><td>25</td></tr></table><p>Omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega omega.</p>
        <h2>Skipped</h2><p>Must not be chunked.</p></body></html>''',
                                    document_id='document-chunk', filing_id='filing-chunk')
    selected = OutlineSection(section_id='outline-selected', generated_topic='Selected',
        exact_source_title='Selected', primary_range=SourceRange(
            document_id=document.ref.document_id, source_hash=document.ref.source_hash,
            start_line=1, end_line=5))
    chunks = SourceRangeChunker(settings).build(document, [selected])
    assert len(chunks) >= 2
    assert chunks[0].context_ranges == []
    assert any(item.context_ranges for item in chunks[1:])
    assert all(item.request_size_estimate <= settings.chunk_request_budget for item in chunks)
    assert [item.core_range.start_line for item in chunks] == sorted(
        item.core_range.start_line for item in chunks)
    assert {line for item in chunks for line in range(item.core_range.start_line,
                                                       item.core_range.end_line + 1)} == set(range(1, 6))
    assert sum(item.core_range.end_line - item.core_range.start_line + 1 for item in chunks) == 5
    assert all(document.slice(item.core_range) for item in chunks)
    assert all('Skipped' not in document.slice(item.core_range) for item in chunks)
    assert chunks[0].next_chunk_id == chunks[1].chunk_id
    assert chunks[1].previous_chunk_id == chunks[0].chunk_id

    oversized = document.lines[1].model_copy(update={'text': 'x' * 2000})
    huge = document.model_copy(update={'lines': [document.lines[0], oversized, *document.lines[2:]]})
    with pytest.raises(ValueError, match='Oversized unsupported canonical line 2'):
        SourceRangeChunker(settings).build(huge, [selected])


def test_offline_chunk_stage_persists_ranges_and_has_lazy_inspector(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, chunk_target_tokens=100,
                        chunk_overlap_tokens=40, chunk_question_overhead=500,
                        chunk_request_budget=1000, outline_window_lines=100,
                        section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='chunk-offline')
    asyncio.run(pipeline.run('chunk-offline', implement_source=True))
    stage = pipeline.repo.stage('chunk-offline', 'chunk')
    chunks = pipeline.repo.chunks('chunk-offline')
    assert stage.status == 'completed' and chunks
    document = pipeline.repo.canonical_document('chunk-offline', chunks[0].core_range.document_id)
    selected = {item.item_id for item in pipeline.repo.scores('chunk-offline', 'section_score')
                if item.policy_decision == 'selected'}
    assert {item.section_id for item in chunks} <= selected
    assert all(document.slice(item.core_range) for item in chunks)
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/chunk-offline?stage=chunk')
        inspector = client.get(f'/v2/runs/chunk-offline/chunks/{chunks[0].chunk_id}')
    assert page.status_code == 200 and 'Bounded source-range chunks' in page.text
    assert 'Table rows are atomic' in page.text
    assert inspector.status_code == 200 and 'Core preview' in inspector.text
