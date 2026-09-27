"""Runnable bounded V3 graph exploration over one live, canonical SEC filing."""
import asyncio
import hashlib
import json
import time
from collections import deque
from collections.abc import Awaitable, Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from uuid import uuid4

import httpx

from profitlab.sec.client import SECClient, SECError
from profitlab.sec.service import DiscoveryService, normalize_ticker
from profitlab.v2.canonical import CanonicalDocument, canonicalize_html
from profitlab.v2.contracts import SourceRange

from .contracts import (
    AnswerCandidate,
    AnswerClaim,
    CampaignConfiguration,
    DevelopmentCampaign,
    EvidenceEdge,
    EvidenceNode,
    ExperimentManifest,
    ExplorationAction,
    GraphAnswer,
    GraphPath,
)
from .repository import V3Repository

ProposalCaller = Callable[[dict], Awaitable[dict]]


class _Trace:
    """SEC transport adapter; V3 persists its own source and action audit."""
    def __init__(self, redactor):
        self.redact = redactor

    @contextmanager
    def operation(self, _name, _request, **_metadata):
        yield {}


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _id(prefix: str, value: object) -> str:
    return f'{prefix}-{_digest(value)[:16]}'


class V3GraphService:
    """Generic graph mechanics only: models supply semantics, source validates them."""
    _NON_LEAK = ('V2 findings', 'Company Facts', 'reviewed expectations', 'comparisons',
                 'rubrics', 'evaluation output', 'XBRL payloads')
    _RELATIONS = ('supports', 'qualifies', 'contradicts', 'same_claim', 'narrows', 'related_to')
    _REQUEST_SCHEMA_VERSION = 'v3-graph-request-v2'
    _CONTINUATION_POLICY_VERSION = 'insufficiency-directed-v1'
    _STOPPING_POLICY_VERSION = 'sufficient-frontier-v1'
    _G6B_EXCLUDED_TICKERS = frozenset({'FGN', 'CRVL', 'SPRO', 'WOR', 'MSFT'})

    def __init__(self, settings, repository: V3Repository | None = None, *, caller: ProposalCaller | None = None):
        self.settings = settings
        self.repo = repository or V3Repository(settings.data_dir)
        self.caller = caller
        self.model = settings.v3_model or settings.llm_model

    def campaign_configuration(self) -> CampaignConfiguration:
        """The complete, server-owned G6b.1 graph identity."""
        return CampaignConfiguration(
            application_revision=self.settings.application_revision, model=self.model,
            exploration_prompt_version=self.settings.v3_prompt_version,
            answer_prompt_version=self.settings.v3_prompt_version,
            request_schema_version=self._REQUEST_SCHEMA_VERSION,
            relation_vocabulary=self._RELATIONS,
            source_window_lines=self.settings.v3_window_lines,
            source_window_overlap_lines=self.settings.v3_window_overlap_lines,
            max_actions=self.settings.v3_max_actions,
            max_total_source_characters=self.settings.v3_max_total_source_characters,
            max_wall_seconds=self.settings.v3_max_wall_seconds,
            continuation_policy_version=self._CONTINUATION_POLICY_VERSION,
            stopping_policy_version=self._STOPPING_POLICY_VERSION,
        )

    def validate_campaign_launch(self, campaign: DevelopmentCampaign, ticker: str) -> str:
        """Fail before source/provider work if a sealed campaign cannot run here."""
        normalized = normalize_ticker(ticker)
        if normalized in self._G6B_EXCLUDED_TICKERS:
            raise ValueError(f'{normalized} is excluded from G6b development campaigns.')
        if not self.settings.sec_contact_ready() or not self.settings.llm_api_key.get_secret_value():
            raise ValueError('V3 campaign launch requires ready SEC contact and LLM provider configuration.')
        if campaign.configuration != self.campaign_configuration():
            raise ValueError('The sealed campaign configuration does not match this V3 runtime.')
        return normalized

    def _acquire_live(self, ticker: str):
        if not self.settings.sec_contact_ready():
            raise ValueError('SEC_USER_AGENT with a real contact email is required for V3 live filing acquisition.')
        normalized = normalize_ticker(ticker)
        client = SECClient(self.settings, _Trace(self.settings.redactor()))
        try:
            result = DiscoveryService(self.settings).discover(client, normalized, 1, synthetic=False)
            if result.outcome != 'found' or not result.filings:
                raise ValueError(result.message)
            filing = next((item for item in result.filings if item.form == '10-K'), result.filings[0])
            raw_html, _ = client.get(filing.primary_document_url, bytes, stage='v3_source', document=True)
        except SECError as error:
            raise ValueError(str(error)) from None
        finally:
            client.close()
        document_id = 'v3-document-' + filing.accession.replace('-', '')
        document, visible_html = canonicalize_html(raw_html, document_id=document_id, filing_id=filing.filing_id)
        metadata = {'filing_id': filing.filing_id, 'accession': filing.accession, 'form': filing.form,
                    'report_date': filing.report_date.isoformat(), 'source_url': filing.primary_document_url}
        return normalized, document, raw_html, visible_html, metadata

    async def _live_call(self, payload: dict) -> dict:
        if self.caller:
            return await self.caller(payload)
        if not self.settings.llm_api_key.get_secret_value():
            raise ValueError('LLM_API_KEY is required for V3 graph exploration.')
        instructions = ('Return JSON only. You are proposing source-cited generic evidence graph data. '
                        'Generated labels are navigational metadata and never source text. Do not use knowledge outside supplied lines.')
        async with httpx.AsyncClient(timeout=self.settings.provider_timeout) as client:
            response = await client.post(self.settings.llm_base_url.rstrip('/') + '/chat/completions',
                headers={'Authorization': 'Bearer ' + self.settings.llm_api_key.get_secret_value()},
                json={'model': self.model, 'response_format': {'type': 'json_object'}, 'messages': [
                    {'role': 'system', 'content': instructions}, {'role': 'user', 'content': json.dumps(payload)}]})
            response.raise_for_status()
            body = response.json()
        content = body['choices'][0]['message']['content'] or '{}'
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise TypeError('V3 model returned non-object JSON.')
        return parsed

    def _window(self, document: CanonicalDocument):
        size, overlap = self.settings.v3_window_lines, self.settings.v3_window_overlap_lines
        step, start = max(1, size - overlap), 1
        while start <= document.ref.line_count:
            end = min(document.ref.line_count, start + size - 1)
            yield start, end
            if end == document.ref.line_count:
                return
            start += step

    def _initial_windows(self, document: CanonicalDocument):
        """Return a generic seed, rather than a filing-wide deterministic sweep.

        Subsequent windows are model proposals attached to graph evidence.  The
        first source window has no semantic claim: it merely gives the explorer a
        bounded place from which to construct the initial frontier.
        """
        end = min(document.ref.line_count, self.settings.v3_window_lines)
        return [(1, end)]

    def _budget_state(self, action_count, source_characters, started):
        return {
            'actions_used': action_count,
            'actions_remaining': max(0, self.settings.v3_max_actions - action_count),
            'source_characters_used': source_characters,
            'source_characters_remaining': max(0, self.settings.v3_max_total_source_characters - source_characters),
            'wall_seconds_used': round(time.monotonic() - started, 6),
            'wall_seconds_remaining': max(0.0, round(self.settings.v3_max_wall_seconds - (time.monotonic() - started), 6)),
        }

    @staticmethod
    def _frontier_ref(raw, local_nodes, local_edges):
        """Resolve only accepted/uncertain evidence from this action's graph."""
        if (isinstance(raw, int) and 0 <= raw < len(local_nodes) and local_nodes[raw] and
                local_nodes[raw].status != 'rejected'):
            return local_nodes[raw].node_id
        if isinstance(raw, str):
            for node in local_nodes:
                if node and raw in (node.node_id, node.label) and node.status != 'rejected':
                    return node.node_id
            for edge in local_edges:
                if raw == edge.edge_id and edge.status != 'rejected':
                    return edge.edge_id
        return None

    def _next_windows(self, proposal, document, local_nodes, local_edges):
        """Validate model-requested expansions without inventing candidates.

        A next window must be bounded and justified by accepted/uncertain graph
        evidence created in the action that requested it.  We intentionally do
        not rank headings, rows, tables, or financial-looking text here.
        """
        plans, errors = [], []
        if not isinstance(proposal, dict):
            return plans, errors
        requested = proposal.get('next_windows', [])
        if not isinstance(requested, list):
            return plans, ['next_windows is not a list']
        for index, raw in enumerate(requested):
            try:
                if not isinstance(raw, dict):
                    raise TypeError('next window is not an object')
                start, end = int(raw['start_line']), int(raw['end_line'])
                if start < 1 or end < start or end > document.ref.line_count:
                    raise ValueError('next window is outside the canonical document')
                if end - start + 1 > self.settings.v3_window_lines:
                    raise ValueError('next window exceeds the configured window bound')
                reason = raw.get('reason')
                if not isinstance(reason, str) or not reason.strip():
                    raise ValueError('next window lacks a model-supplied reason')
                raw_refs = raw.get('parent_refs', raw.get('parent_nodes', []))
                if not isinstance(raw_refs, list) or not raw_refs:
                    raise ValueError('next window lacks accepted or uncertain parent evidence')
                refs = [self._frontier_ref(item, local_nodes, local_edges) for item in raw_refs]
                if any(ref is None for ref in refs):
                    raise ValueError('next window references rejected or unknown graph evidence')
                # Preserve order while making the stored provenance unambiguous.
                refs = list(dict.fromkeys(refs))
                plans.append((start, end, reason.strip(), refs))
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f'next window {index} rejected: {error}')
        return plans, errors

    @staticmethod
    def _answerability(proposal) -> str:
        """Accept only the model's explicit frontier decision.

        The application deliberately does not infer sufficiency from labels,
        relations, document position, or source text. A malformed or omitted
        decision therefore cannot make a frontier answerable.
        """
        if not isinstance(proposal, dict):
            raise TypeError('response is not an object')
        value = proposal.get('answerability')
        if value not in ('sufficient', 'insufficient'):
            raise ValueError('answerability must be exactly sufficient or insufficient')
        return value

    def _range(self, document, value, start, end) -> SourceRange:
        if not isinstance(value, dict):
            raise TypeError('evidence span is not an object')
        first, last = int(value['start_line']), int(value.get('end_line', value['start_line']))
        if first < start or last > end or last < first:
            raise ValueError('evidence span is outside supplied source window')
        begin, finish = value.get('start_character'), value.get('end_character')
        source_range = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                                   start_line=first, end_line=last, start_character=begin, end_character=finish)
        exact = value.get('exact_text')
        if not isinstance(exact, str) or document.slice(source_range) != exact:
            raise ValueError('evidence span does not round-trip exactly from canonical source')
        return source_range

    @staticmethod
    def _status(value: object) -> str:
        """Map model-facing evidence language to the immutable three-state audit contract."""
        normalized = str(value or 'uncertain').strip().lower()
        if normalized in ('accepted', 'stated', 'supported', 'confirmed'):
            return 'accepted'
        if normalized in ('uncertain', 'qualified', 'qualifying', 'possible', 'ambiguous'):
            return 'uncertain'
        if normalized in ('rejected', 'unsupported', 'invalid'):
            return 'rejected'
        raise ValueError('invalid node or edge status')

    def _proposal_graph(self, document, proposal, start, end, experiment_id):
        if not isinstance(proposal, dict):
            return [], [], ['response is not an object'], [], []
        nodes, edges, errors, local = [], [], [], []
        for index, raw in enumerate(proposal.get('nodes', [])):
            try:
                status = self._status(raw.get('status'))
                ranges = [self._range(document, item, start, end) for item in raw['evidence']]
                label = raw['label']
                if not isinstance(label, str) or not label.strip():
                    raise ValueError('node label is missing')
                node = EvidenceNode(node_id=_id('node', [experiment_id, document.ref.source_hash, start, index, raw]),
                    document_id=document.ref.document_id, source_hash=document.ref.source_hash, label=label.strip(),
                    evidence_ranges=ranges, status=status, model=self.model, prompt_version=self.settings.v3_prompt_version,
                    uncertainty=raw.get('uncertainty') if isinstance(raw.get('uncertainty'), str) else None)
                nodes.append(node); local.append(node)
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f'node {index} rejected: {error}')
                local.append(None)
        for index, raw in enumerate(proposal.get('edges', [])):
            try:
                by_label = {node.label: index for index, node in enumerate(local) if node}
                left = by_label.get(raw['from_node'], raw['from_node'])
                right = by_label.get(raw['to_node'], raw['to_node'])
                left, right = int(left), int(right)
                if left < 0 or right < 0 or left >= len(local) or right >= len(local) or not local[left] or not local[right]:
                    raise ValueError('edge references invalid node')
                relation, status = raw['relation'], self._status(raw.get('status'))
                if relation not in ('supports', 'qualifies', 'contradicts', 'same_claim', 'narrows', 'related_to'):
                    raise ValueError('invalid relation')
                ranges = [self._range(document, item, start, end) for item in raw['evidence']]
                edges.append(EvidenceEdge(edge_id=_id('edge', [experiment_id, document.ref.source_hash, start, index, raw]),
                    document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                    from_node_id=local[left].node_id, to_node_id=local[right].node_id, relation=relation,
                    evidence_ranges=ranges, status=status, model=self.model, prompt_version=self.settings.v3_prompt_version,
                    uncertainty=raw.get('uncertainty') if isinstance(raw.get('uncertainty'), str) else None))
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f'edge {index} rejected: {error}')
        return nodes, edges, errors, local, edges

    def _paths(self, document, nodes, edges):
        paths = []
        for node in nodes:
            if node.status == 'rejected':
                continue
            paths.append(GraphPath(path_id=_id('path', [node.node_id]), document_id=document.ref.document_id,
                source_hash=document.ref.source_hash, node_ids=[node.node_id], source_ranges=node.evidence_ranges,
                status=node.status))
        for edge in edges:
            if edge.status == 'rejected':
                continue
            source_nodes = {item.node_id: item for item in nodes}
            if (edge.from_node_id in source_nodes and edge.to_node_id in source_nodes and
                    source_nodes[edge.from_node_id].status != 'rejected' and
                    source_nodes[edge.to_node_id].status != 'rejected'):
                ranges = source_nodes[edge.from_node_id].evidence_ranges + source_nodes[edge.to_node_id].evidence_ranges + edge.evidence_ranges
                paths.append(GraphPath(path_id=_id('path', [edge.edge_id]), document_id=document.ref.document_id,
                    source_hash=document.ref.source_hash, node_ids=[edge.from_node_id, edge.to_node_id], edge_ids=[edge.edge_id], source_ranges=ranges,
                    status='accepted' if edge.status == 'accepted' and
                    source_nodes[edge.from_node_id].status == source_nodes[edge.to_node_id].status == 'accepted'
                    else 'uncertain'))
        return paths

    def _answer_range(self, document, value, selected_paths):
        """Validate an answer quote and derive omitted character offsets from graph source.

        Models often quote a sentence from a supplied whole-line graph span without
        returning its character offsets.  The application may derive those offsets
        only when the quote has one exact occurrence inside a selected graph path.
        """
        allowed = [source for path in selected_paths for source in path.source_ranges]
        try:
            direct = self._range(document, value, 1, document.ref.line_count)
            if any(self._contained(direct, source) for source in allowed):
                return direct
        except (KeyError, TypeError, ValueError):
            pass
        if not isinstance(value, dict) or not isinstance(value.get('exact_text'), str):
            raise TypeError('answer citation lacks exact source text')
        quote = value['exact_text']
        if not quote:
            raise ValueError('answer citation cannot be empty')
        supplied_start = value.get('start_line')
        for source in allowed:
            if supplied_start is not None and not source.start_line <= int(supplied_start) <= source.end_line:
                continue
            # A character-range source already is its exact canonical slice; do
            # not broaden it while repairing an incomplete model citation.
            if source.start_character is not None:
                if document.slice(source) == quote:
                    return source
                continue
            for line_number in range(source.start_line, source.end_line + 1):
                text = document.lines[line_number - 1].text
                if text.count(quote) == 1:
                    begin = text.index(quote)
                    return SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                        start_line=line_number, end_line=line_number, start_character=begin,
                        end_character=begin + len(quote))
        raise ValueError('answer citation is not an exact unique substring of its selected graph path')

    @staticmethod
    def _contained(inner, outer):
        if inner.start_line < outer.start_line or inner.end_line > outer.end_line:
            return False
        if outer.start_character is None:
            return True
        return (inner.start_line == inner.end_line == outer.start_line == outer.end_line and
                inner.start_character is not None and outer.start_character <= inner.start_character and
                inner.end_character <= outer.end_character)

    def _paths_for_ranges(self, paths, ranges):
        """Return only graph paths that mechanically contain an answer citation."""
        return [path for path in paths if any(
            self._contained(source, graph_source)
            for source in ranges for graph_source in path.source_ranges
        )]

    async def _answer(self, manifest, document, nodes, edges, paths):
        accepted = [path for path in paths if path.status == 'accepted']
        uncertain = [path for path in paths if path.status == 'uncertain']
        usable = accepted or uncertain
        if not usable:
            raise ValueError('V3 frontier exhausted without accepted source-cited graph support; no answer was fabricated.')
        conflicted = any(edge.status == 'accepted' and edge.relation == 'contradicts' for edge in edges)
        limited_mode = bool(uncertain) or conflicted
        path_packet = [{**path.model_dump(mode='json'), 'evidence': [
            {'source_range': source.model_dump(mode='json'), 'exact_text': document.slice(source)}
            for source in path.source_ranges
        ]} for path in usable]
        packet = {'kind': 'answer', 'question': manifest.question, 'paths': path_packet,
                  'instruction': ('Answer only from the exact_text evidence in these paths. Labels are navigational metadata, not source. '
                                  'Return {"answer": string, "limitation": string|null, "path_ids": [...], '
                                  '"claims": [{"claim":string,"path_ids":[...],"citations":[{"start_line":int,"end_line":int,"start_character":int|null,"end_character":int|null,"exact_text":string}]}]}. '
                                  'Every material claim needs a non-empty exact-text citation and path. '
                                  + ('The selected graph is uncertain or conflicting: provide a limited answer and state that limitation; do not force a conclusion.'
                                     if limited_mode else 'State unresolved information as a limitation rather than guessing.'))}
        response = await self._live_call(packet)
        self.repo.save_answer_attempt(manifest.experiment_id, packet, response)
        supplied_path_ids = response.get('path_ids')
        valid_ids = {path.path_id for path in usable}
        selected_paths = ([path for path in usable if path.path_id in supplied_path_ids]
                          if isinstance(supplied_path_ids, list) and supplied_path_ids and
                          set(supplied_path_ids) <= valid_ids else [])
        # If opaque IDs are mangled, an answer remains useful only when its exact
        # source quotes mechanically identify accepted graph paths.
        raw_claims = response.get('claims')
        # Older saved callers used one answer-level citation list.  Preserve that
        # wire compatibility by treating it as one explicitly source-bound claim;
        # live prompts always request the stricter per-claim shape above.
        if not isinstance(raw_claims, list):
            raw_claims = [{'claim': response.get('answer'), 'path_ids': response.get('path_ids'),
                           'citations': response.get('citations', [])}]
        claims = []
        for item in raw_claims:
            if not isinstance(item, dict) or not isinstance(item.get('claim'), str) or not item['claim'].strip():
                raise ValueError('V3 answer claim is missing.')
            raw_ids = item.get('path_ids', response.get('path_ids'))
            claim_paths = ([path for path in usable if path.path_id in raw_ids]
                           if isinstance(raw_ids, list) and raw_ids and set(raw_ids) <= valid_ids else [])
            ranges = [self._answer_range(document, citation, claim_paths or usable)
                      for citation in item.get('citations', [])]
            if not ranges:
                raise ValueError('V3 answer claim has no source citation.')
            if not claim_paths:
                claim_paths = self._paths_for_ranges(usable, ranges)
            if not claim_paths:
                raise ValueError('V3 answer claim citation is absent from every selected graph path.')
            claims.append(AnswerClaim(claim=item['claim'].strip(), path_ids=[path.path_id for path in claim_paths],
                                      source_ranges=ranges))
        ranges = [source for claim in claims for source in claim.source_ranges]
        claim_path_ids = {path_id for claim in claims for path_id in claim.path_ids}
        if selected_paths:
            selected_paths = [path for path in usable if path.path_id in
                              ({path.path_id for path in selected_paths} | claim_path_ids)]
        derived_paths = False
        if not selected_paths:
            selected_paths = self._paths_for_ranges(usable, ranges)
            if not selected_paths:
                raise ValueError('V3 answer citation is absent from every accepted graph path.')
            derived_paths = True
        path_ids = [path.path_id for path in selected_paths]
        answer = response.get('answer')
        if not isinstance(answer, str) or not answer.strip():
            raise ValueError('V3 answer text is missing.')
        limitation = response.get('limitation') if isinstance(response.get('limitation'), str) else None
        if limited_mode and not limitation:
            limitation = ('The selected graph includes uncertain or conflicting source-cited evidence; '
                          'this answer is explicitly limited and does not resolve that ambiguity.')
        if derived_paths:
            note = 'Graph paths were derived mechanically from exact citations because the model returned missing or invalid path IDs.'
            limitation = f'{limitation} {note}' if limitation else note
        return AnswerCandidate(answer_id=_id('answer', [manifest.experiment_id, response]), experiment_id=manifest.experiment_id,
            answer=answer.strip(), limitation=limitation, path_ids=path_ids, source_ranges=ranges,
            claims=claims, status='limited' if limitation or limited_mode else 'accepted',
            model=self.model, prompt_version=self.settings.v3_prompt_version)

    async def answer_document(self, ticker: str, question: str, document: CanonicalDocument, *, raw_html=b'', visible_html=b'', filing=None):
        if not question.strip():
            raise ValueError('Question is required.')
        now = datetime.now(UTC)
        manifest = ExperimentManifest(experiment_id=_id('v3', [uuid4().hex]), question=question.strip(), document=document.ref,
            ticker=ticker, filing=filing or {}, application_revision=self.settings.application_revision, model=self.model,
            prompt_version=self.settings.v3_prompt_version, budgets={'max_actions': self.settings.v3_max_actions, 'max_source_characters': self.settings.v3_max_total_source_characters, 'max_wall_seconds': self.settings.v3_max_wall_seconds}, non_leak_inventory=self._NON_LEAK, created_at=now)
        self.repo.create(manifest, document, raw_html, visible_html)
        nodes, edges, seen, source_chars, started = [], [], set(), 0, time.monotonic()
        frontier = deque((start, end, 'initial generic source coverage', [])
                         for start, end in self._initial_windows(document))
        sequence, budget_exhausted, partial_terminal, answerable = 0, False, False, False
        while frontier:
            if (sequence >= self.settings.v3_max_actions or
                    source_chars >= self.settings.v3_max_total_source_characters or
                    time.monotonic() - started >= self.settings.v3_max_wall_seconds):
                budget_exhausted = True
                break
            start, end, reason, parent_path = frontier.popleft()
            # The normalized line interval is the identity of an exploration
            # window. A model cannot keep re-opening an equivalent interval.
            if (start, end) in seen:
                continue
            lines = [{'line_number': line.line_number, 'text': line.text}
                     for line in document.lines[start - 1:end]]
            characters = sum(len(line['text']) for line in lines)
            if source_chars + characters > self.settings.v3_max_total_source_characters:
                budget_exhausted = True
                break
            sequence += 1
            seen.add((start, end)); source_chars += characters
            window = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                                 start_line=start, end_line=end)
            request = {
                'kind': 'explore', 'question': question,
                'window': {'start_line': start, 'end_line': end}, 'lines': lines,
                'document_bounds': {'start_line': 1, 'end_line': document.ref.line_count},
                'next_window_max_lines': self.settings.v3_window_lines,
                'relation_vocabulary': ['supports', 'qualifies', 'contradicts', 'same_claim', 'narrows', 'related_to'],
                'output': {
                    'answerability': '"sufficient" | "insufficient"',
                    'nodes': '[{label,status,evidence:[{start_line,end_line?,start_character?,end_character?,exact_text}]}]',
                    'edges': '[{from_node,to_node,relation,status,evidence:[...]}]',
                    'next_windows': '[{start_line,end_line,reason,parent_refs:[node index or node id]}]',
                },
                'constraints': ('Use only supplied lines. Cite exact spans. Never emit an answer. '
                                'Node and edge status MUST be exactly accepted, uncertain, or rejected. '
                                'Edges must refer to nodes using their zero-based index, not their labels. '
                                'Set answerability to sufficient only when this frontier makes the supplied graph able to answer the question; '
                                'otherwise set it to insufficient. An insufficient frontier MUST request at least one bounded next_windows '
                                'entry within document_bounds, each justified by accepted or uncertain nodes from this response in parent_refs. '
                                f'Each next window may contain at most {self.settings.v3_window_lines} lines. '
                                'A sufficient frontier must return an empty next_windows list. Do not request a window already supplied.'),
            }
            request_hash = _digest({'request': request, 'model': self.model, 'prompt': self.settings.v3_prompt_version})
            cached = self.repo.cached(request_hash); tick = time.monotonic()
            answerability = None
            try:
                response = cached if cached is not None else await self._live_call(request)
                if cached is None:
                    self.repo.cache(request_hash, response)
                proposed_nodes, proposed_edges, errors, local_nodes, local_edges = self._proposal_graph(
                    document, response, start, end, manifest.experiment_id)
                nodes.extend(proposed_nodes); edges.extend(proposed_edges)
                next_plans, next_errors = self._next_windows(
                    response, document, local_nodes, local_edges)
                errors.extend(next_errors)
                answerability = self._answerability(response)
                unvisited_plans = [plan for plan in next_plans if plan[:2] not in seen]
                if answerability == 'insufficient':
                    if not unvisited_plans:
                        errors.append('insufficient frontier has no valid unvisited continuation')
                        partial_terminal = True
                    else:
                        frontier.extend(unvisited_plans)
                else:
                    # A sufficient declaration is the only model-provided
                    # permission to leave exploration for answer synthesis.
                    answerable = True
                state = 'cached' if cached else ('partial' if errors else 'completed')
            except Exception as error:  # noqa: BLE001 - audit a malformed/provider response and continue.
                response, errors, state = {'error': str(error)}, [str(error)], 'partial'
                partial_terminal = True
            action = ExplorationAction(
                action_id=_id('action', [manifest.experiment_id, sequence, request_hash]),
                experiment_id=manifest.experiment_id, sequence=sequence, window=window,
                reason=reason, parent_path=parent_path, status=state,
                budget_state=self._budget_state(sequence, source_chars, started), request_hash=request_hash,
                response_status='; '.join(errors)[:2000] or 'validated', answerability=answerability,
                elapsed_seconds=time.monotonic() - tick, created_at=datetime.now(UTC))
            self.repo.save_action(action, request, response)
            if partial_terminal or answerable:
                break
        manifest = manifest.model_copy(update={
            'frontier_state': ('partial' if partial_terminal else
                               'budget_exhausted' if budget_exhausted else 'exhausted'),
            'finished_at': datetime.now(UTC),
        })
        paths = self._paths(document, nodes, edges)
        self.repo.save_graph(manifest.experiment_id, nodes, edges, paths)
        # Record terminal frontier state before attempting synthesis.  In
        # particular, a graph with no accepted path must remain inspectable even
        # though _answer deliberately refuses to fabricate a claim.
        self.repo.update_manifest(manifest)
        if not answerable:
            raise ValueError('V3 frontier ended without a sufficient model-supplied answerability decision; no answer was synthesized.')
        answer = await self._answer(manifest, document, nodes, edges, paths)
        manifest = manifest.model_copy(update={'frontier_state': 'answered', 'finished_at': datetime.now(UTC)})
        self.repo.update_manifest(manifest); self.repo.save_answer(answer)
        cited = {f'L{line}': document.lines[line - 1].text for source in answer.source_ranges for line in range(source.start_line, source.end_line + 1)}
        return GraphAnswer(manifest=manifest, answer=answer, paths=[path for path in paths if path.path_id in answer.path_ids], cited_text=cited)

    async def answer_live(self, ticker: str, question: str):
        ticker, document, raw, visible, filing = await asyncio.to_thread(self._acquire_live, ticker)
        return await self.answer_document(ticker, question, document, raw_html=raw, visible_html=visible, filing=filing)

    async def answer_live_campaign(self, campaign: DevelopmentCampaign, ticker: str):
        """Launch using only the campaign's sealed question and configuration."""
        normalized = self.validate_campaign_launch(campaign, ticker)
        return await self.answer_live(normalized, campaign.question)
