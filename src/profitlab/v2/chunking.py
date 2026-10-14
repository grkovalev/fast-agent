"""Range-only chunking for selected V2 outline sections."""
import hashlib
import json
import math

from .canonical import CanonicalDocument
from .contracts import OutlineSection, SourceRange, TextChunk

ESTIMATOR_VERSION = 'utf8-bytes-div3-ceil-1'


def estimate(text: str) -> int:
    """A stable request-size proxy; provider usage is recorded by scoring later."""
    return math.ceil(len(text.encode('utf-8')) / 3)


class SourceRangeChunker:
    """Split canonical atomic lines, keeping overlap as separate source ranges."""
    def __init__(self, settings):
        self.settings = settings

    @classmethod
    def inspection_view(cls, settings, *, selected_sections: int = 0,
                        chunks: list[TextChunk] | None = None, totals: dict | None = None):
        """Describe the deterministic range contract used by the chunk stage.

        This is deliberately owned by the chunker: the UI may format this data,
        but it must not recreate the boundary or sizing policy in JavaScript.
        """
        chunks = chunks or []
        core_lines = sum(item.core_range.end_line - item.core_range.start_line + 1
                         for item in chunks)
        totals = totals or {'count': len(chunks), 'core_lines': core_lines,
                            'max_request_size': max((item.request_size_estimate for item in chunks),
                                                    default=0)}
        sample = [item for item in chunks[:3]
                  if item.section_id == chunks[0].section_id] if chunks else []
        if not sample:
            def example_range(start: int, end: int) -> SourceRange:
                return SourceRange(document_id='example', source_hash='0' * 64,
                                   start_line=start, end_line=end)

            sample = [
                TextChunk(chunk_id='example-1', section_id='example-section',
                          core_range=example_range(101, 120), request_size_estimate=160,
                          next_chunk_id='example-2'),
                TextChunk(chunk_id='example-2', section_id='example-section',
                          core_range=example_range(121, 140),
                          context_ranges=[example_range(115, 120)],
                          request_size_estimate=175, previous_chunk_id='example-1',
                          next_chunk_id='example-3'),
                TextChunk(chunk_id='example-3', section_id='example-section',
                          core_range=example_range(141, 160),
                          context_ranges=[example_range(135, 140)],
                          request_size_estimate=180, previous_chunk_id='example-2'),
            ]
        return {
            'sample_kind': 'persisted' if chunks else 'illustrative',
            'sample_chunks': sample,
            'selected_sections': selected_sections,
            'chunk_count': totals['count'],
            'core_lines': totals['core_lines'],
            'max_request_size': totals['max_request_size'],
            'split': {
                'accepts': 'Selected outline sections and their canonical visible lines only.',
                'does': ('Walks canonical atomic lines in source order, stopping before a core '
                         'range exceeds the configured size or request budget.'),
                'outputs': {'section_id': 'ordered bounded core source ranges'},
                'guarantee': 'No model is called and no source text is generated or truncated.',
                'policy': {
                    'path': 'SourceRangeChunker — deterministic, no model request',
                    'core_target_tokens': settings.chunk_target_tokens,
                    'request_budget': settings.chunk_request_budget,
                    'question_overhead': settings.chunk_question_overhead,
                    'estimator': ESTIMATOR_VERSION,
                },
            },
            'context': {
                'accepts': 'A bounded core range and preceding canonical lines in the same selected section.',
                'does': 'Repeats bounded whole lines immediately before the core, within the same selected section; never following or cross-section lines.',
                'outputs': {'context_ranges': 'preceding source ranges for reading context'},
                'guarantee': 'Repeated context owns no additional coverage and cannot supply a finding citation for this chunk; only its core is citable.',
                'policy': {'overlap_tokens': settings.chunk_overlap_tokens},
            },
            'store': {
                'accepts': 'Core ranges plus optional preceding context ranges.',
                'does': 'Persists TextChunk range metadata and links adjacent chunks within a section.',
                'outputs': {'TextChunk': TextChunk.model_json_schema()},
                'guarantee': 'The stored source ranges remain the authoritative, inspectable record.',
            },
        }

    def _request_estimate(self, document: CanonicalDocument, core: SourceRange,
                          context: list[SourceRange]) -> int:
        return self.settings.chunk_question_overhead + estimate('\n'.join(
            [*(document.slice(item) for item in context), document.slice(core)]))

    def _range(self, document: CanonicalDocument, start: int, end: int) -> SourceRange:
        return SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                           start_line=start, end_line=end)

    def _context(self, document: CanonicalDocument, section: OutlineSection, core_start: int):
        """Keep a bounded trailing prefix of the preceding core within this section."""
        if not self.settings.chunk_overlap_tokens or core_start == section.primary_range.start_line:
            return []
        start, used = core_start, 0
        for line_number in range(core_start - 1, section.primary_range.start_line - 1, -1):
            size = estimate(document.lines[line_number - 1].text)
            if used + size > self.settings.chunk_overlap_tokens:
                break
            start, used = line_number, used + size
        return [self._range(document, start, core_start - 1)] if start < core_start else []

    def build(self, document: CanonicalDocument, sections: list[OutlineSection]) -> list[TextChunk]:
        if self.settings.chunk_overlap_tokens >= self.settings.chunk_target_tokens:
            raise ValueError('Chunk overlap must be smaller than target.')
        chunks: list[TextChunk] = []
        for section in sections:
            source = section.primary_range
            document._validate_range(source)
            start = source.start_line
            while start <= source.end_line:
                end = start - 1
                while end < source.end_line:
                    candidate = self._range(document, start, end + 1)
                    context = self._context(document, section, start)
                    request_size = self._request_estimate(document, candidate, context)
                    if request_size > self.settings.chunk_request_budget:
                        if end < start:
                            raise ValueError(
                                f'Oversized unsupported canonical line {start}; no truncation performed')
                        break
                    if end >= start and estimate(document.slice(candidate)) > self.settings.chunk_target_tokens:
                        break
                    end += 1
                if end < start:
                    raise ValueError(f'Could not form a chunk at canonical line {start}.')
                core = self._range(document, start, end)
                context = self._context(document, section, start)
                request_size = self._request_estimate(document, core, context)
                identity = json.dumps({
                    'source_hash': document.ref.source_hash, 'section_id': section.section_id,
                    'core': [start, end], 'context': [[item.start_line, item.end_line] for item in context],
                    'estimator': ESTIMATOR_VERSION, 'target': self.settings.chunk_target_tokens,
                    'overlap': self.settings.chunk_overlap_tokens,
                    'budget': self.settings.chunk_request_budget,
                    'overhead': self.settings.chunk_question_overhead,
                }, sort_keys=True)
                chunks.append(TextChunk(
                    chunk_id='chunk-' + hashlib.sha256(identity.encode()).hexdigest()[:24],
                    section_id=section.section_id, core_range=core, context_ranges=context,
                    request_size_estimate=request_size,
                ))
                if len(chunks) > self.settings.chunk_max_count:
                    raise ValueError('Chunk count limit exceeded; evidence is incomplete.')
                start = end + 1
        return [item.model_copy(update={
            'previous_chunk_id': (chunks[index - 1].chunk_id if index and
                                  chunks[index - 1].section_id == item.section_id else None),
            'next_chunk_id': (chunks[index + 1].chunk_id if index + 1 < len(chunks) and
                              chunks[index + 1].section_id == item.section_id else None),
        }) for index, item in enumerate(chunks)]
