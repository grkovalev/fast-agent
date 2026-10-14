"""Outline window carry and whole-document partition remain distinct."""
import asyncio

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef
from profitlab.v2.outline_service import OutlineBatch, OutlineService


def test_overlapping_windows_carry_validated_context_then_partition_once(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        outline_window_lines=100, outline_overlap_lines=20)
    document = CanonicalDocument(
        ref=CanonicalDocumentRef(document_id='doc', filing_id='filing',
                                 source_hash='0' * 64, line_count=170),
        lines=[CanonicalLine(line_number=n, text=f'Visible line {n}',
                             element_type='paragraph', html_anchor=f'line-{n}',
                             dom_reference=f'/p[{n}]') for n in range(1, 171)],
    )
    service = OutlineService(settings, None)
    assert list(service.windows(document)) == [(1, 100), (81, 170)]
    calls = []

    async def batch(_document, start, end, continuation, *, client):
        calls.append((start, end, continuation))
        proposal = {'generated_topic': 'Illustrative navigation', 'exact_source_title': None,
                    'start_line': 90, 'end_line': 95, 'continues_previous': False}
        if start == 1:
            # The first proposal ends before the next window; a bad quote cannot
            # become a partition boundary or continuation metadata.
            return OutlineBatch([proposal, {**proposal, 'start_line': 40,
                                           'exact_representative_quote': 'Absent'}], 'model', False)
        return OutlineBatch([proposal], 'model', False)

    service._batch = batch
    sections, warnings, models, cached, windows = asyncio.run(service.build(document))

    assert calls[1][2][0]['end_line'] == 95
    assert len(calls[1][2]) == 1
    assert [(s.primary_range.start_line, s.primary_range.end_line) for s in sections] == [
        (1, 89), (90, 170)]
    assert sections[0].generated_topic == 'Unlabeled source range'
    assert sections[0].boundary_warnings
    assert len(warnings) == 1 and 'quote' in warnings[0]
    assert windows == 2 and models == ['model'] and cached == 0

    inspection = OutlineService.inspection_view(settings)
    assert inspection['window']['outputs']['window_step_lines'] == 80
    assert inspection['window']['outputs']['continuation_context_limit'] == service.continuation_limit
    assert 'final_outline_section_example' in inspection['reconcile']['outputs']
    assert 'outline_sections' not in inspection['reconcile']['outputs']

    assert 'Each final range ends before the next boundary' in inspection['reconcile']['does']
    assert 'Parent topics are navigation hints on flat stored ranges' in inspection['reconcile']['does']
