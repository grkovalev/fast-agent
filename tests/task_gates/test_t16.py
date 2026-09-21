"""T16 source-validated outline contract and offline workspace path."""
import asyncio

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService, canonicalize_html
from profitlab.v2.outline_service import OutlineBatch, OutlineService
from profitlab.web.app import create_app


def test_outline_rejects_bad_model_boundaries_and_partitions_every_line(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, outline_window_lines=100)
    document, _ = canonicalize_html(b'''<html><body><h1>Results</h1><p>Net income was 10.</p>
        <h2>Notes</h2><p>Details.</p></body></html>''', document_id='document-outline',
                                    filing_id='filing-outline')
    service = OutlineService(settings, V2PipelineService(settings).repo)

    async def bad_batch(_document, _start, _end, _continuation, *, offline):
        return OutlineBatch([
            {'generated_topic': 'bad range', 'start_line': 0, 'end_line': 1},
            {'generated_topic': 'bad quote', 'start_line': 1, 'end_line': 2,
             'exact_representative_quote': 'invented quote'},
            {'generated_topic': 'valid but not source', 'start_line': 2, 'end_line': 2,
             'exact_representative_quote': 'Net income was 10.'},
        ], 'test-model', False)

    monkeypatch.setattr(service, '_batch', bad_batch)
    sections, warnings, models, cached = asyncio.run(service.build(document, offline=True))
    assert len(warnings) == 2 and models == ['test-model'] and cached == 0
    assert [(item.primary_range.start_line, item.primary_range.end_line) for item in sections] == [(1, 1), (2, 4)]
    assert sum(item.primary_range.end_line - item.primary_range.start_line + 1 for item in sections) == 4
    assert all('invented quote' not in item.model_dump_json() for item in sections)


def test_large_windows_pass_preceding_navigation_context(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, outline_window_lines=100,
                        outline_overlap_lines=10)
    raw = '<html><body><h1>Overview</h1>' + '<p>Detail.</p>' * 89 + \
        '<h2>Operations</h2>' + '<p>Detail.</p>' * 89 + '<h2>Financials</h2>' + \
        '<p>Detail.</p>' * 20 + '</body></html>'
    document, _ = canonicalize_html(raw.encode(), document_id='document-windows',
                                    filing_id='filing-windows')
    service = OutlineService(settings, V2PipelineService(settings).repo)
    contexts = []

    async def contextual_batch(_document, start, _end, continuation, *, offline):
        contexts.append(continuation)
        line = document.lines[start - 1]
        return OutlineBatch([{'generated_topic': f'Topic {line.text}',
                              'exact_source_title': line.text, 'start_line': start,
                              'end_line': start, 'parent_topic_hint': 'Annual report'}],
                            'test-model', False)

    monkeypatch.setattr(service, '_batch', contextual_batch)
    sections, _, _, _ = asyncio.run(service.build(document, offline=True))
    assert len(contexts) == 3 and not contexts[0]
    assert contexts[1][-1]['exact_source_title'] == 'Overview'
    assert contexts[2][-1]['exact_source_title'] == 'Operations'
    assert sections[-1].primary_range.end_line == document.ref.line_count


def test_offline_outline_is_persisted_cached_and_shown_in_workspace(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, outline_window_lines=100,
                        outline_overlap_lines=0)
    service = V2PipelineService(settings)
    service.create(run_id='outline-one')
    asyncio.run(service.run('outline-one', implement_source=True))
    sections = service.repo.outline_sections('outline-one')
    source = service.repo.canonical_refs('outline-one')[0]
    assert service.repo.stage('outline-one', 'outline').status == 'completed'
    assert sections and sections[0].primary_range.start_line == 1
    assert sections[-1].primary_range.end_line == source.line_count
    assert {line for section in sections for line in range(section.primary_range.start_line,
                                                            section.primary_range.end_line + 1)} == set(range(1, source.line_count + 1))

    service.create(run_id='outline-two')
    asyncio.run(service.run('outline-two', implement_source=True))
    assert 'cached window batch' in service.repo.stage('outline-two', 'outline').summary
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/outline-one?stage=outline')
    assert page.status_code == 200
    assert 'Validated two-level outline' in page.text and 'Generated child topic' in page.text
    assert 'Generated parent topic' in page.text
