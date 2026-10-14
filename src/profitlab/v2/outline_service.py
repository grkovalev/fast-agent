"""Validated, cached navigation outlines derived from canonical visible lines."""
import hashlib
import json
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from .canonical import CanonicalDocument, CanonicalLine
from .contracts import (
    CanonicalDocumentRef,
    OutlineContinuation,
    OutlineProposal,
    OutlineSection,
    SourceRange,
)


@dataclass(frozen=True)
class OutlineBatch:
    proposals: list[dict]
    actual_model: str
    cached: bool


class OutlineService:
    """Keep generated navigation metadata separate from canonical source text."""
    prompt_version = 'outline-v1'
    system_prompt = 'You produce constrained filing navigation JSON.'
    continuation_limit = 8

    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository
        self.prompt_version = settings.outline_prompt_version

    @staticmethod
    def _range_hash(document: CanonicalDocument, start: int, end: int, continuation: list[dict]) -> str:
        material = '\n'.join(f'{line.line_number}:{line.text}' for line in document.lines[start - 1:end])
        material += '\nprevious=' + json.dumps(continuation, sort_keys=True)
        return hashlib.sha256(material.encode()).hexdigest()

    def _configuration_hash(self) -> str:
        # Do not cache credentials; the endpoint/model and output contract affect output.
        material = json.dumps({'base_url': self.settings.llm_base_url,
                               'model': self.settings.outline_model,
                               'prompt_version': self.prompt_version}, sort_keys=True)
        return hashlib.sha256(material.encode()).hexdigest()

    def windows(self, document: CanonicalDocument):
        size, overlap = self.settings.outline_window_lines, self.settings.outline_overlap_lines
        step = max(1, size - overlap)
        start = 1
        while start <= document.ref.line_count:
            end = min(document.ref.line_count, start + size - 1)
            yield start, end
            if end == document.ref.line_count:
                break
            start += step

    @staticmethod
    def _prompt_template() -> str:
        """The request instruction with only safe, named dynamic slots.

        Keeping this beside ``_prompt`` lets the overview expose the actual request
        instruction without copying filing text or prior navigation metadata into
        the page.
        """
        return '''Return JSON only: {"sections":[...]}. Each section may contain only:
generated_topic, exact_source_title, start_line, end_line, exact_representative_quote,
section_type, parent_topic_hint, continues_previous. Build exactly two navigation levels:
an overall parent topic (parent_topic_hint) and a concise child section. Prefer meaningful
visible headers/subheaders, merging boilerplate and adjacent chunks into the same child.
If this window begins inside the final preceding child, set continues_previous=true so it
extends rather than starts a duplicate section. Use the prior validated navigation context
below; it is metadata only, not filing source. Titles and quotes
must be exact copied substrings from those lines. Do not summarize source as a quote.
Propose navigational topics and ranges only within this window.\n\nPrior context:\n''' + \
            '{continuation}\n\nNumbered filing lines:\n{lines}'

    @classmethod
    def _prompt(cls, document: CanonicalDocument, start: int, end: int,
                continuation: list[dict]) -> str:
        lines = '\n'.join(f'{item.line_number}: {item.text}' for item in document.lines[start - 1:end])
        return cls._prompt_template().replace(
            '{continuation}', json.dumps(continuation, ensure_ascii=False)
        ).replace('{lines}', lines)

    @classmethod
    def prompt_view(cls) -> str:
        """The user message built for a validated illustrative source window."""
        return cls._messages(cls._inspection_document(), 1, 1, [])[1]['content']

    @staticmethod
    def _inspection_document() -> CanonicalDocument:
        return CanonicalDocument(ref=CanonicalDocumentRef(
            document_id='illustrative-document', filing_id='illustrative-filing',
            source_hash='0' * 64, line_count=1), lines=[CanonicalLine(
                line_number=1, text='Illustrative visible filing line.',
                element_type='paragraph', html_anchor='line-1',
                dom_reference='/html/body/p[1]')])

    @classmethod
    def _messages(cls, document, start, end, continuation):
        return [{'role': 'system', 'content': cls.system_prompt},
                {'role': 'user', 'content': cls._prompt(document, start, end, continuation)}]

    @staticmethod
    def _example_proposal() -> OutlineProposal:
        return OutlineProposal(
            generated_topic='Illustrative topic', exact_source_title=None, start_line=1,
            end_line=1, exact_representative_quote='Illustrative visible filing line.',
            section_type='child', parent_topic_hint='Illustrative parent',
            continues_previous=False,
        )

    @classmethod
    def response_contract_view(cls) -> str:
        """A representative response built from the typed LLM payload contract."""
        return json.dumps({'sections': [cls._example_proposal().model_dump()]}, ensure_ascii=False)

    @classmethod
    def inspection_view(cls, settings) -> dict:
        """Server-owned examples for the Outline station inspector.

        The browser receives these shapes rather than maintaining its own copies of
        the request, proposal, continuation, or persisted-section payloads.
        """
        proposal = cls._example_proposal()
        continuation = OutlineContinuation(
            generated_topic='Illustrative prior topic', exact_source_title=None,
            end_line=1, parent_topic_hint='Illustrative parent',
        )
        section = OutlineSection(
            section_id='outline-000001', generated_topic=proposal.generated_topic,
            exact_source_title=proposal.exact_source_title,
            exact_representative_quote=proposal.exact_representative_quote,
            primary_range=SourceRange(document_id='illustrative-document', source_hash='0' * 64,
                                      start_line=proposal.start_line, end_line=proposal.end_line),
            parent_topic_hint=proposal.parent_topic_hint, section_type=proposal.section_type,
        )
        window_end = settings.outline_window_lines
        return {
            'propose': {
                'request': {'kind': 'illustrative request built with current configuration',
                            'model': settings.outline_model,
                            'prompt_version': settings.outline_prompt_version,
                            'messages': cls._messages(cls._inspection_document(), 1, 1, [])},
                'outputs': {'sections': [proposal.model_dump(mode='json')]},
            },
            'window': {
                'accepts': {
                    'prior_context': [continuation.model_dump()],
                    'canonical_lines': [CanonicalLine(
                        line_number=1, text='Illustrative visible line',
                        element_type='paragraph', html_anchor='line-1',
                        dom_reference='/html/body/p[1]').model_dump()],
                },
                'does': ('Advances by window size minus overlap while retaining prior validated '
                         'navigation metadata. The next request re-reads overlapping source lines.'),
                'outputs': {
                    'window_start_line': 1, 'window_end_line': window_end,
                    'overlap_lines': settings.outline_overlap_lines,
                    'window_step_lines': max(1, window_end - settings.outline_overlap_lines),
                    'continuation_context_limit': cls.continuation_limit,
                    'continuation_context': [continuation.model_dump()],
                },
                'guarantee': ('Only sanitized, visible filing lines enter the loop. The window is '
                              'a source boundary, not generated text.'),
            },
            'validate': {
                'accepts': {'sections': [proposal.model_dump()]},
                'does': ('Re-reads every declared title, range, and representative quote from the '
                         'canonical window. It accepts only proposals whose bounds and text are exact.'),
                'outputs': {
                    'accepted': [proposal.model_dump()],
                    'rejected': [{'reason': 'quote mismatch'}],
                },
                'guarantee': ('A model suggestion never becomes source evidence by itself; failed '
                              'proposals remain inspectable as rejected.'),
            },
            'reconcile': {
                'accepts': {
                    'accepted_ranges': [proposal.model_dump()],
                    'rejected_proposals': [{'reason': 'quote mismatch'}],
                },
                'does': ('During each window, append validated proposals and carry the most recent '
                         'accepted proposals into the next request as navigation metadata. After the '
                         'last window, deduplicate matching range/title proposals, use non-continuing '
                         'starts as boundaries. Each final range ends before the next boundary; the last '
                         'extends to the document end, covering every canonical line exactly once. '
                         'Parent topics are navigation hints on flat stored ranges, not independently '
                         'selected parent objects or an enforced nested hierarchy.'),
                'outputs': {
                    'final_outline_section_example': section.model_dump(mode='json'),
                    'continuation_context': [continuation.model_dump()],
                },
                'guarantee': ('Continuation is not a persisted section. Missing first boundaries '
                              'produce warned unlabeled coverage; rejected proposals keep diagnostics '
                              'without creating a boundary.'),
            },
        }

    async def _live_proposals(self, document: CanonicalDocument, start: int, end: int,
                              continuation: list[dict], client=None):
        if not self.settings.llm_api_key.get_secret_value():
            raise ValueError('LLM_API_KEY is missing; configure it for a live outline run.')
        if client is None:
            async with httpx.AsyncClient(timeout=self.settings.provider_timeout) as temporary:
                return await self._live_proposals(document, start, end, continuation, temporary)
        sdk = AsyncOpenAI(base_url=self.settings.llm_base_url,
                          api_key=self.settings.llm_api_key.get_secret_value(),
                          max_retries=0, http_client=client)
        response = await sdk.chat.completions.create(model=self.settings.outline_model,
            messages=self._messages(document, start, end, continuation),
            response_format={'type': 'json_object'})
        content = response.choices[0].message.content or '{}'
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or not isinstance(parsed.get('sections'), list):
            raise TypeError('Outline model did not return a JSON sections list.')
        return parsed['sections'], (response.model or self.settings.outline_model)

    def _validate(self, document: CanonicalDocument, start: int, end: int, proposal: object):
        if not isinstance(proposal, dict):
            return None, 'proposal is not an object'
        try:
            first, last = int(proposal['start_line']), int(proposal['end_line'])
        except (KeyError, TypeError, ValueError):
            return None, 'range is missing or invalid'
        if first < start or last > end or last < first:
            return None, 'range falls outside its supplied window'
        topic = proposal.get('generated_topic')
        if not isinstance(topic, str) or not topic.strip():
            return None, 'generated topic is missing'
        source = '\n'.join(line.text for line in document.lines[first - 1:last])
        title, quote = proposal.get('exact_source_title'), proposal.get('exact_representative_quote')
        if title is not None and (not isinstance(title, str) or title not in source):
            return None, 'exact source title does not match the referenced lines'
        if quote is not None and (not isinstance(quote, str) or quote not in source):
            return None, 'representative quote does not match the referenced lines'
        return OutlineProposal(
            generated_topic=topic.strip(), exact_source_title=title,
            exact_representative_quote=quote, start_line=first, end_line=last,
            section_type=proposal.get('section_type') if isinstance(proposal.get('section_type'), str) else None,
            parent_topic_hint=proposal.get('parent_topic_hint') if isinstance(proposal.get('parent_topic_hint'), str) else None,
            continues_previous=proposal.get('continues_previous') is True,
        ).model_dump(), None

    async def _batch(self, document: CanonicalDocument, start: int, end: int, continuation: list[dict], *, client=None):
        source_hash, config_hash = self._range_hash(document, start, end, continuation), self._configuration_hash()
        model = self.settings.outline_model
        cached = self.repo.outline_batch(source_hash, self.prompt_version, config_hash, model)
        if cached:
            return OutlineBatch(cached['proposals'], model, True)
        proposals, actual_model = await self._live_proposals(document, start, end, continuation, client)
        self.repo.save_outline_batch(source_hash, self.prompt_version, config_hash, actual_model,
                                     {'proposals': proposals})
        return OutlineBatch(proposals, actual_model, False)

    async def build(self, document: CanonicalDocument):
        accepted, warnings, models, cached_count, continuation, window_count = [], [], set(), 0, [], 0
        client_context = httpx.AsyncClient(timeout=self.settings.provider_timeout)
        await client_context.__aenter__()
        try:
            for start, end in self.windows(document):
                window_count += 1
                batch = await self._batch(document, start, end, continuation, client=client_context)
                models.add(batch.actual_model)
                cached_count += batch.cached
                for proposal in batch.proposals:
                    valid, warning = self._validate(document, start, end, proposal)
                    if valid is None:
                        warnings.append(f'Lines {start}-{end}: rejected proposal: {warning}.')
                    else:
                        accepted.append(valid)
                continuation = [OutlineContinuation(
                    generated_topic=item['generated_topic'],
                    exact_source_title=item['exact_source_title'], end_line=item['end_line'],
                    parent_topic_hint=item['parent_topic_hint'],
                ).model_dump() for item in accepted[-self.continuation_limit:]]
        finally:
            await client_context.aclose()
        # Explicit visible headings take precedence. Duplicate overlap proposals collapse by range/title.
        unique = {}
        for item in accepted:
            key = (item['start_line'], item['end_line'], item['exact_source_title'] or '')
            current = unique.get(key)
            if current is None or (item['exact_source_title'] and not current['exact_source_title']):
                unique[key] = item
        starts = {item['start_line']: item for item in unique.values()
                  if not item['continues_previous']}
        # A deterministic partition covers every canonical line once; unproposed boundaries are warned,
        # never presented as an invented source title or quote.
        boundaries = sorted({1, *starts})
        sections = []
        for index, line in enumerate(boundaries):
            end = boundaries[index + 1] - 1 if index + 1 < len(boundaries) else document.ref.line_count
            proposal = starts.get(line)
            if proposal is None:
                proposal = {'generated_topic': 'Unlabeled source range', 'exact_source_title': None,
                            'exact_representative_quote': None, 'section_type': None,
                            'parent_topic_hint': None}
                warning = 'No validated outline boundary; retained as an unlabeled coverage range.'
            else:
                warning = None
            sections.append(OutlineSection(section_id=f'outline-{line:06d}',
                generated_topic=proposal['generated_topic'], exact_source_title=proposal['exact_source_title'],
                exact_representative_quote=proposal['exact_representative_quote'],
                primary_range=SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                    start_line=line, end_line=end), parent_topic_hint=proposal['parent_topic_hint'],
                section_type=proposal['section_type'], boundary_warnings=[warning] if warning else []))
        if warnings:
            # The proposal may not name a usable line, so retain its diagnostics on the
            # first partition item rather than manufacturing a source boundary for it.
            sections[0] = sections[0].model_copy(update={
                'boundary_warnings': sections[0].boundary_warnings + warnings,
            })
        return sections, warnings, sorted(models), cached_count, window_count
