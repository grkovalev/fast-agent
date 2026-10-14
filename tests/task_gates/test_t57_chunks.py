"""Chunk ranges give each source line one core owner and repeat context separately."""
from datetime import UTC, datetime
from itertools import pairwise

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.chunking import SourceRangeChunker
from profitlab.v2.contracts import (
    CanonicalDocumentRef,
    OutlineSection,
    SourceRange,
    StageSnapshot,
    V2Run,
)
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_core_partition_context_and_bounded_persisted_render(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        chunk_target_tokens=100, chunk_overlap_tokens=80,
                        chunk_question_overhead=500, chunk_request_budget=1000)
    ref = CanonicalDocumentRef(document_id='doc', filing_id='filing',
                               source_hash='a' * 64, line_count=5)
    document = CanonicalDocument(ref=ref, lines=[
        CanonicalLine(line_number=n, text=f'{n} ' + 'Visible source ' * 12,
                      element_type='table_row' if n == 3 else 'paragraph',
                      html_anchor=f'line-{n}', dom_reference=f'/p[{n}]')
        for n in range(1, 6)])
    section = OutlineSection(section_id='s1', generated_topic='Selected topic',
                             primary_range=SourceRange(document_id='doc',
                                                       source_hash=ref.source_hash,
                                                       start_line=1, end_line=5))
    chunks = SourceRangeChunker(settings).build(document, [section])
    owned = [line for chunk in chunks
             for line in range(chunk.core_range.start_line, chunk.core_range.end_line + 1)]
    assert owned == list(range(1, 6))
    assert len(chunks) >= 3
    assert not chunks[0].context_ranges
    assert any(chunk.context_ranges for chunk in chunks[1:])
    for previous, current in pairwise(chunks):
        assert current.core_range.start_line == previous.core_range.end_line + 1
        assert current.previous_chunk_id == previous.chunk_id
        assert previous.next_chunk_id == current.chunk_id
        assert all(context.end_line < current.core_range.start_line
                   for context in current.context_ranges)
        assert current.request_size_estimate <= settings.chunk_request_budget

    # Context and neighbor links reset at selected-section boundaries.
    split_sections = [section.model_copy(update={
        'section_id': f's{n}', 'primary_range': section.primary_range.model_copy(
            update={'start_line': start, 'end_line': end})})
        for n, (start, end) in enumerate(((1, 3), (4, 5)), 1)]
    split_chunks = SourceRangeChunker(settings).build(document, split_sections)
    first_second_section = next(item for item in split_chunks if item.section_id == 's2')
    assert not first_second_section.context_ranges
    assert first_second_section.previous_chunk_id is None
    assert all(context.start_line >= (1 if item.section_id == 's1' else 4)
               for item in split_chunks for context in item.context_ranges)

    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='chunk-map', ticker='MAP', created_at=now, updated_at=now))
    repo.save_canonical_document('chunk-map', document, b'<p>source</p>',
                                 b''.join(f'<p id="line-{n}">Visible source {n}</p>'.encode()
                                          for n in range(1, 6)))
    repo.save_outline_sections('chunk-map', [section])
    repo.save_chunks('chunk-map', chunks)
    repo.update_stage(StageSnapshot(run_id='chunk-map', stage='chunk', position=4,
                                    status='completed', output_hash='b' * 64),
                      event_kind='stage_finished', event_summary='chunks saved')
    with TestClient(create_app(settings)) as client:
        html = client.get('/v2/runs/chunk-map/pipeline').text
        source_page = client.get('/v2/runs/chunk-map/source?document=doc&page=1')
        chunk_page = client.get(f'/v2/runs/chunk-map/chunks/{chunks[1].chunk_id}')
        selected = client.get('/v2/runs/chunk-map/pipeline?stage=chunk')
    fragment = html.split('data-chunks-card', 1)[1].split('</article>', 1)[0]
    assert 'Bounded persisted example from this run' in fragment
    assert fragment.count('class="chunks-core-item"') == 3
    assert fragment.count('class="chunks-transfer"') == 2
    assert 'Advance to next uncovered line' in fragment
    assert 'Copy a bounded tail into its context' in fragment
    assert '+ Copied context · already owned' in fragment
    assert 'New core · owns these lines' in fragment
    assert 'For example, lines' in fragment
    assert 'Their core owner stays in the earlier chunk.' in fragment
    assert f'/v2/runs/chunk-map/chunks/{chunks[0].chunk_id}">{chunks[0].chunk_id}</a>' in fragment
    assert f'≈ {chunks[1].request_size_estimate} tokens' in fragment
    assert 'Core + context + question overhead' in fragment
    assert f'/v2/runs/chunk-map/chunks/{chunks[0].chunk_id}' in fragment
    assert '/v2/runs/chunk-map/source?document=doc' in fragment
    assert '#line-1' in fragment
    assert chunk_page.status_code == selected.status_code == 200
    assert 'cannot supply a finding citation for this chunk' in chunk_page.text
    assert 'same selected section' in chunk_page.text
    assert f'/chunks/{chunks[0].chunk_id}' in chunk_page.text
    assert f'#line-{chunks[1].context_ranges[0].start_line}' in chunk_page.text
    assert 'cannot supply a finding citation for this chunk' in selected.text
    assert 'cannot cite those context lines in a finding' in fragment
    assert 'following or different section' in fragment
    assert source_page.status_code == 200
    assert 'line-1' in source_page.text
    assert 'This stage makes no model request.' in fragment
    assert 'Current configuration' in fragment
    assert 'Whole canonical lines' in fragment
    assert 'rather than being cut' in fragment


def test_pending_chunk_stage_labels_illustration_and_unavailable_accounting(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='pending-chunk-map', ticker='MAP',
                          created_at=now, updated_at=now))
    with TestClient(create_app(settings)) as client:
        html = client.get('/v2/runs/pending-chunk-map/pipeline').text
    fragment = html.split('data-chunks-card', 1)[1].split('</article>', 1)[0]
    assert 'Illustrative ranges and estimates' in fragment
    assert 'Persisted accounting pending.' in fragment
    assert 'Open source' not in fragment
    assert '/v2/runs/pending-chunk-map/chunks/' not in fragment
    repo.update_stage(StageSnapshot(run_id='pending-chunk-map', stage='chunk', position=4,
                                    status='failed', error='test failure'),
                      event_kind='stage_failed', event_summary='test failure')
    with TestClient(create_app(settings)) as client:
        failed = client.get('/v2/runs/pending-chunk-map/pipeline').text
    failed_fragment = failed.split('data-chunks-card', 1)[1].split('</article>', 1)[0]
    assert 'Complete accounting unavailable after failed.' in failed_fragment
    assert 'Illustrative ranges and estimates' in failed_fragment
