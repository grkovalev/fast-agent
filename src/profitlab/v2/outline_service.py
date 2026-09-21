"""Validated, cached navigation outlines derived from canonical visible lines."""
import hashlib
import json
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from .canonical import CanonicalDocument
from .contracts import OutlineSection, SourceRange


@dataclass(frozen=True)
class OutlineBatch:
    proposals: list[dict]
    actual_model: str
    cached: bool


class OutlineService:
    """Keep generated navigation metadata separate from canonical source text."""
    prompt_version = 'outline-v1'

    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository
        self.prompt_version = settings.outline_prompt_version

    @staticmethod
    def _range_hash(document: CanonicalDocument, start: int, end: int) -> str:
        material = '\n'.join(f'{line.line_number}:{line.text}' for line in document.lines[start - 1:end])
        return hashlib.sha256(material.encode()).hexdigest()

    def _configuration_hash(self) -> str:
        # Do not cache credentials; the endpoint/model and output contract affect output.
        material = json.dumps({'base_url': self.settings.llm_base_url,
                               'model': self.settings.llm_model,
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
    def _prompt(document: CanonicalDocument, start: int, end: int) -> str:
        lines = '\n'.join(f'{item.line_number}: {item.text}' for item in document.lines[start - 1:end])
        return '''Return JSON only: {"sections":[...]}. Each section may contain only:
generated_topic, exact_source_title, start_line, end_line, exact_representative_quote,
section_type, parent_topic_hint. Use the numbered visible lines below. Titles and quotes
must be exact copied substrings from those lines. Do not summarize source as a quote.
Propose navigational topics and ranges only within this window.\n\n''' + lines

    @staticmethod
    def _fixture_proposals(document: CanonicalDocument, start: int, end: int) -> list[dict]:
        headings = [line for line in document.lines[start - 1:end] if line.element_type == 'heading']
        return [{'generated_topic': f'Heading: {line.text}', 'exact_source_title': line.text,
                 'start_line': line.line_number, 'end_line': line.line_number,
                 'exact_representative_quote': line.text, 'section_type': 'heading',
                 'parent_topic_hint': None} for line in headings]

    async def _live_proposals(self, document: CanonicalDocument, start: int, end: int):
        if not self.settings.llm_api_key.get_secret_value():
            raise ValueError('LLM_API_KEY is missing; configure it for a live outline run.')
        async with httpx.AsyncClient(timeout=self.settings.provider_timeout) as client:
            sdk = AsyncOpenAI(base_url=self.settings.llm_base_url,
                              api_key=self.settings.llm_api_key.get_secret_value(),
                              max_retries=0, http_client=client)
            response = await sdk.chat.completions.create(model=self.settings.llm_model,
                messages=[{'role': 'system', 'content': 'You produce constrained filing navigation JSON.'},
                          {'role': 'user', 'content': self._prompt(document, start, end)}],
                response_format={'type': 'json_object'}, temperature=0)
        content = response.choices[0].message.content or '{}'
        parsed = json.loads(content)
        if not isinstance(parsed, dict) or not isinstance(parsed.get('sections'), list):
            raise TypeError('Outline model did not return a JSON sections list.')
        return parsed['sections'], (response.model or self.settings.llm_model)

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
        return {'generated_topic': topic.strip(), 'exact_source_title': title,
                'exact_representative_quote': quote, 'start_line': first, 'end_line': last,
                'section_type': proposal.get('section_type') if isinstance(proposal.get('section_type'), str) else None,
                'parent_topic_hint': proposal.get('parent_topic_hint') if isinstance(proposal.get('parent_topic_hint'), str) else None}, None

    async def _batch(self, document: CanonicalDocument, start: int, end: int, *, offline: bool):
        source_hash, config_hash = self._range_hash(document, start, end), self._configuration_hash()
        model = 'fixture-outline-v1' if offline else self.settings.llm_model
        cached = self.repo.outline_batch(source_hash, self.prompt_version, config_hash, model)
        if cached:
            return OutlineBatch(cached['proposals'], model, True)
        if offline:
            proposals, actual_model = self._fixture_proposals(document, start, end), model
        else:
            proposals, actual_model = await self._live_proposals(document, start, end)
        self.repo.save_outline_batch(source_hash, self.prompt_version, config_hash, actual_model,
                                     {'proposals': proposals})
        return OutlineBatch(proposals, actual_model, False)

    async def build(self, document: CanonicalDocument, *, offline: bool):
        accepted, warnings, models, cached_count = [], [], set(), 0
        for start, end in self.windows(document):
            batch = await self._batch(document, start, end, offline=offline)
            models.add(batch.actual_model)
            cached_count += batch.cached
            for proposal in batch.proposals:
                valid, warning = self._validate(document, start, end, proposal)
                if valid is None:
                    warnings.append(f'Lines {start}-{end}: rejected proposal: {warning}.')
                else:
                    accepted.append(valid)
        # Explicit visible headings take precedence. Duplicate overlap proposals collapse by range/title.
        unique = {}
        for item in accepted:
            key = (item['start_line'], item['end_line'], item['exact_source_title'] or '')
            current = unique.get(key)
            if current is None or (item['exact_source_title'] and not current['exact_source_title']):
                unique[key] = item
        starts = {item['start_line']: item for item in unique.values() if item['exact_source_title']}
        for line in document.lines:
            if line.element_type == 'heading':
                starts[line.line_number] = {'generated_topic': f'Heading: {line.text}',
                    'exact_source_title': line.text, 'exact_representative_quote': line.text,
                    'start_line': line.line_number, 'end_line': line.line_number,
                    'section_type': 'heading', 'parent_topic_hint': None}
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
        return sections, warnings, sorted(models), cached_count
