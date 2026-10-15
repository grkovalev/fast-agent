"""Selected-bundle conversion in the active Findings pipeline.

Wire requests, validation and inspection share these builders. No type classifier,
source retrieval, chunk expansion or implicit structured-output retries occur here.
"""
import asyncio
import hashlib
import json
import time
from math import ceil
from urllib.parse import urlsplit

import httpx
from openai import AsyncOpenAI
from pydantic import ValidationError

from profitlab.providers.jev import TokenUsage
from profitlab.providers.transport import TracedTransport

from .contracts import Finding
from .findings_builders import build_conversion_messages, build_conversion_state
from .findings_contracts import (
    CompletedConversionBatch,
    ConversionDiagnostic,
    ConversionRequest,
    ConversionResponse,
    ConversionState,
    FindingConversionOutput,
    FindingConversionProposal,
    FindingPublicationProvenance,
    FindingsConversionResult,
    FindingsPhase,
    FindingsStepResult,
    Omission,
    PhaseAccounting,
    displayed_decimal,
)


def build_conversion_request(state, policy, *, model, base_url, output_mode='tool',
                             reasoning_effort=None, repair=None):
    """Bound the exact Chat Completions body, including output schema and settings.

    Token arithmetic is a conservative configured estimate, not a tokenizer or a
    verified model context capacity. No SDK/framework adds messages or tools later.
    """
    messages = build_conversion_messages(state, policy)
    if repair:
        messages.append({'role': 'user', 'content': json.dumps({
            'repair': 'Correct only rejected proposals for these supplied bundles. Accepted findings are preserved separately.',
            'diagnostics': [x.model_dump(mode='json') for x in repair]}, ensure_ascii=False)})
    schema = FindingConversionOutput.model_json_schema()
    body = {'model':model, 'messages':messages, 'max_completion_tokens':policy.conversion_output_tokens}
    if output_mode == 'tool':
        body.update(tools=[{'type': 'function', 'function': {
            'name': 'convert_findings', 'description': 'Return source-bound numeric proposals.',
            'parameters': schema}}],
            tool_choice={'type': 'function', 'function': {'name': 'convert_findings'}},
            parallel_tool_calls=False)
    elif output_mode == 'native':
        body['response_format'] = {'type': 'json_schema', 'json_schema': {
            'name': 'findings', 'schema': schema}}
    else:
        raise ValueError('Unknown conversion output mode')
    if reasoning_effort is None and model == 'gpt-5.6-luna' and urlsplit(base_url).hostname == 'api.openai.com':
        reasoning_effort = 'none'
    if reasoning_effort:
        body['reasoning_effort'] = reasoning_effort
    serialized = json.dumps(body, ensure_ascii=False)
    if (len(serialized) > policy.conversion_request_characters or
            ceil(len(serialized) / policy.conversion_characters_per_token) +
            policy.conversion_token_margin > policy.conversion_input_tokens):
        raise ValueError('Final model/tool/schema conversion envelope exceeds configured input budget')
    return ConversionRequest(base_url=base_url, model=model, state=state,
        body=body, policy_hash=policy.identity(),
        repair_bundle_ids=[x.bundle_id for x in state.selected_bundles] if repair else [])


def validate_conversion(raw, state, model, *, repaired=False):
    """Source truth is only the supplied selected bundle, including exact offsets."""
    bundle_id = raw.get('bundle_id', 'unknown')
    bundle = next((x for x in state.selected_bundles if x.bundle_id == bundle_id), None)
    proposal = None
    try:
        proposal = FindingConversionProposal.model_validate(raw)
        if bundle is None:
            raise ValueError('Bundle is not in this selected conversion request')
        if proposal.concept != bundle.concept or proposal.source_range != bundle.source.source_range:
            raise ValueError('Concept/source line differs from selected bundle')
        if proposal.numeric_span not in bundle.numeric_spans:
            raise ValueError('Numeric span/sign/offset is not supplied by selected bundle')
        text, quote, span = bundle.source.exact_text, proposal.exact_quote, proposal.numeric_span
        # A repeated substring is valid only when a matching occurrence covers this span.
        positions = [i for i in range(len(text)) if text.startswith(quote, i)]
        positions = [i for i in positions if i <= span.start_character and
                     span.end_character <= i + len(quote)]
        if not positions:
            raise ValueError('Exact quote must cover the declared numeric span on the source line')
        available = [bundle.source.source_range, *[x.source_range for x in bundle.context]]
        claims = {k: getattr(proposal, k) for k in ('period', 'unit', 'scale', 'attribution')
                  if getattr(proposal, k) is not None}
        if any(r not in available for claim in claims.values() for r in claim.source_references):
            raise ValueError('Metadata references must be supplied selected source/context lines')
        offset = positions[0]
        location = proposal.source_range.model_copy(update={
            'start_character': offset, 'end_character': offset + len(quote)})
        identity = f'{bundle.concept}:{location.source_hash}:{location.start_line}:{span.start_character}:{span.end_character}:{displayed_decimal(span.raw_text)}'
        limitations = list(proposal.limitations)
        limitations.extend(f'{key} unresolved' for key in ('period', 'unit', 'scale', 'attribution') if key not in claims)
        limitations.extend(f'Context role unresolved: {x.value}' for x in bundle.unresolved_roles)
        limitations.append('Metadata references prove supplied provenance, not financial interpretation or requested-year semantics.')
        finding = Finding(finding_id='finding-' + hashlib.sha256(identity.encode()).hexdigest()[:32],
            exact_quote=quote, source_range=location, amount=proposal.amount,
            finding_type=bundle.concept.value, bundle_id=bundle.bundle_id,
            context_references=[x.source_range for x in bundle.context],
            **{k: v.value for k,v in claims.items()}, limitations=list(dict.fromkeys(limitations)),
            validation_state='validated', model=model, repair_attempted=repaired)
        publication = FindingPublicationProvenance(finding=finding, concept=bundle.concept,
            bundle_id=bundle.bundle_id, numeric_span=span,
            context_references=finding.context_references, metadata_claims=claims)
        return publication, ConversionDiagnostic(bundle_id=bundle_id, proposal=proposal,
            state='accepted', repaired=repaired)
    except (ValueError, TypeError, ValidationError) as error:
        # Keep malformed proposals inspectable; they do not replace valid siblings.
        return None, ConversionDiagnostic(bundle_id=bundle.bundle_id if bundle else 'unknown',
            proposal=proposal, raw_proposal=raw, state='rejected', reasons=[str(error)], repaired=repaired)


async def live_conversion(request, settings, recorder, *, transport=None):
    """One observable request, zero SDK retries; explicit repair is the sole retry."""
    async with httpx.AsyncClient(transport=TracedTransport(recorder, settings, 'llm', transport, stage='findings'),
                                timeout=settings.provider_timeout) as client:
        sdk = AsyncOpenAI(base_url=request.base_url, api_key=settings.llm_api_key.get_secret_value(),
                          max_retries=0, http_client=client)
        response = await sdk.chat.completions.create(**request.body)
    message = response.choices[0].message
    if 'tools' in request.body:
        calls = message.tool_calls or []
        if len(calls) != 1 or calls[0].function.name != 'convert_findings':
            raise ValueError('Expected exactly one convert_findings output call')
        raw = json.loads(calls[0].function.arguments)
    else:
        raw = json.loads(message.content or '')
    if (not isinstance(raw, dict) or 'findings' not in raw or
            set(raw) - {'findings', 'schema_version'} or raw.get('schema_version', 2) != 2):
        raise ValueError('Expected versioned findings output object')
    usage = response.usage
    return ConversionResponse(model=response.model, response_id=response.id, findings=raw['findings'],
        usage=TokenUsage(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens) if usage else None)


class FindingsConversionFailure(Exception):
    def __init__(self, result):
        self.result = result
        super().__init__(result.step.reason)


class FindingsConversionCancelled(asyncio.CancelledError):
    def __init__(self, result):
        self.result = result
        super().__init__('Conversion cancelled; publication withheld')


class FindingsConversionService:
    def __init__(self, repository, policy):
        self.repository, self.policy = repository, policy

    async def convert(self, run_id, packs, bundles, ranks, document, *, model, base_url,
                      output_mode='tool', reasoning_effort=None, client=None, settings=None,
                      recorder=None, deadline_seconds=None):
        policy = self.policy
        self.repository.get_run(run_id)
        # Reconstruct every pack against current canonical lines and selected ranks.
        bundle_map, rank_map = {b.bundle_id:b for b in bundles}, {r.bundle_id:r for r in ranks}
        seen = set()
        states = []
        omissions = []
        if len(packs) > policy.max_conversion_requests:
            raise ValueError('Conversion pack count exceeds policy')
        for pack in packs:
            ids = [b.bundle_id for b in pack.state.selected_bundles]
            if seen.intersection(ids):
                raise ValueError('Conversion bundles must be unique across packs')
            seen.update(ids)
            state = build_conversion_state(pack.state.filing,
                [(bundle_map[i], rank_map[i]) for i in ids], document, policy)
            if state != pack.state or pack.messages != build_conversion_messages(state, policy):
                raise ValueError('Conversion pack differs from selected canonical inputs/policy')
            states.append(state)
        if seen != {r.bundle_id for r in ranks if r.decision == 'selected'}:
            raise ValueError('Conversion packs must cover exactly selected ranks')
        if states:
            if any(s.filing != states[0].filing for s in states) or states[0].filing.filing_id != document.ref.filing_id:
                raise ValueError('Conversion packs must share the canonical filing metadata')
            build_conversion_state(states[0].filing,
                [(bundle_map[b.bundle_id], rank_map[b.bundle_id]) for s in states for b in s.selected_bundles],
                document, policy)
        # Repack whole bundles under the final wire envelope, preserving T74 order.
        requests = []
        def request_for(state):
            return build_conversion_request(state, policy, model=model, base_url=base_url,
                output_mode=output_mode, reasoning_effort=reasoning_effort)
        for state in states:
            for bundle in state.selected_bundles:
                single = ConversionState(filing=state.filing, selected_bundles=[bundle])
                try:
                    single_request = request_for(single)
                except ValueError:
                    omissions.append(Omission(item_id=bundle.bundle_id, coverage_cut=True,
                        kind='size_limit', reason='Final provider/model/tool/schema envelope exceeds configured bounds'))
                    continue
                if requests:
                    combined = ConversionState(filing=state.filing,
                        selected_bundles=[*requests[-1].state.selected_bundles, bundle])
                    try:
                        combined_request = request_for(combined)
                    except ValueError:
                        pass
                    else:
                        requests[-1] = combined_request
                        continue
                if len(requests) < policy.max_conversion_requests:
                    requests.append(single_request)
                else:
                    omissions.append(Omission(item_id=bundle.bundle_id, coverage_cut=True,
                        kind='count_limit', reason='Final envelope packing exceeds conversion request allowance'))
        start = time.monotonic()
        deadline = min(deadline_seconds if deadline_seconds is not None else policy.total_deadline_seconds,
                       policy.total_deadline_seconds)
        conversion, repair = PhaseAccounting(planned=len(requests)+len(omissions), omitted=len(omissions)).model_dump(), PhaseAccounting().model_dump()
        batches, diagnostics, publications = [], [], {}
        from .findings_storage import reusable_input
        digest = hashlib.sha256(json.dumps(reusable_input({
            'states':[s.model_dump(mode='json') for s in states],
            'omissions':[o.model_dump(mode='json') for o in omissions],
            'requests':[r.cache_key() for r in requests], 'policy':policy.identity(),
            'model':model, 'base_url':base_url, 'output_mode':output_mode,
            'reasoning_effort':reasoning_effort}), sort_keys=True).encode()).hexdigest()

        async def execute(request, accounting):
            if time.monotonic() - start >= deadline:
                raise TimeoutError('Findings conversion deadline exhausted')
            saved = self.repository.conversion_checkpoint(request)
            if saved:
                accounting['cached'] += 1
                accounting['models'] = sorted({*accounting['models'], saved.response.model})
                batches.append(saved)
                return saved.response
            accounting['dispatched'] += 1
            began = time.monotonic()
            try:
                remaining = deadline - (began - start)
                if remaining <= 0:
                    raise TimeoutError('Findings conversion deadline exhausted')
                async with asyncio.timeout(remaining):
                    response = await (client(request) if client else live_conversion(request, settings, recorder))
                response = ConversionResponse.model_validate(response)
                batch = CompletedConversionBatch(request=request, response=response,
                    elapsed_seconds=time.monotonic()-began)
                self.repository.save_conversion_checkpoint(run_id, batch)
                batches.append(batch)
                accounting['completed'] += 1
                accounting['models'] = sorted({*accounting['models'], response.model})
                if response.usage:
                    prior = accounting['usage'] or TokenUsage(input_tokens=0, output_tokens=0)
                    accounting['usage'] = TokenUsage(input_tokens=prior.input_tokens+response.usage.input_tokens,
                        output_tokens=prior.output_tokens+response.usage.output_tokens)
                return response
            except BaseException:
                accounting['failed'] += 1
                raise
            finally:
                accounting['elapsed_seconds'] += time.monotonic()-began

        def accept(response, state, repaired=False):
            rejected = []
            for raw in response.findings:
                publication, diagnostic = validate_conversion(raw, state, response.model, repaired=repaired)
                diagnostics.append(diagnostic)
                if publication:
                    owner = bundle_map[publication.bundle_id].source
                    finding = publication.finding.model_copy(update={
                        'source_chunk_id':owner.owning_chunk_id,
                        'source_chunk_ids':sorted({x.chunk.chunk_id for x in owner.owners})})
                    publication = publication.model_copy(update={'finding':finding})
                    prior = publications.get(finding.finding_id)
                    if prior:
                        # Merge ownership of the same source occurrence; keep accepted claims.
                        merged = prior.finding.model_copy(update={'source_chunk_ids':sorted({
                            *prior.finding.source_chunk_ids, *finding.source_chunk_ids})})
                        publication = prior.model_copy(update={'finding':merged})
                    publications[finding.finding_id] = publication
                elif diagnostic.bundle_id in {b.bundle_id for b in state.selected_bundles}:
                    rejected.append(diagnostic)
            if not response.findings:
                diagnostics.extend(ConversionDiagnostic(bundle_id=b.bundle_id, state='empty', repaired=repaired)
                                   for b in state.selected_bundles)
            return rejected

        status, reason = 'completed', 'Selected bundles converted; invalid terminal proposals remain rejected.'
        try:
            rejected = []
            for request in requests:
                rejected.extend(accept(await execute(request, conversion), request.state))
            if rejected and policy.max_repair_requests:
                ids = {d.bundle_id for d in rejected}
                repair_state = ConversionState(filing=packs[0].state.filing,
                    selected_bundles=[b for p in packs for b in p.state.selected_bundles if b.bundle_id in ids])
                repair['planned'] = 1
                try:
                    request = build_conversion_request(repair_state, policy, model=model, base_url=base_url,
                        output_mode=output_mode, reasoning_effort=reasoning_effort, repair=rejected)
                except ValueError:
                    repair['omitted'] = 1
                    reason = 'Repair envelope exceeds configured bounds; accepted findings preserved; rejections terminal.'
                else:
                    accept(await execute(request, repair), request.state, repaired=True)
        except asyncio.CancelledError:
            status, reason = 'cancelled', 'Conversion cancelled; publication withheld.'
        except Exception as error:  # noqa: BLE001 — retain completed batches without publishing subset
            status, reason = 'failed', f'{type(error).__name__}: {error}'
        conversion, repair = PhaseAccounting.model_validate(conversion), PhaseAccounting.model_validate(repair)
        if status == 'completed' and omissions:
            status = 'partial'
            reason = f'{len(omissions)} selected bundles omitted by final envelope limits; converted retained whole bundles.'
        successful = status in ('completed', 'partial')
        step = FindingsStepResult(phase=FindingsPhase.CONVERT, status=status,
            availability='final' if successful else 'checkpointed' if batches else 'unavailable',
            input_hash=digest, policy_hash=policy.identity(), accounting=conversion,
            output_ids=list(publications) if successful else [], reason=reason, omissions=omissions)
        result = FindingsConversionResult(batches=batches, diagnostics=diagnostics,
            publications=list(publications.values()) if successful else [],
            conversion=conversion, repair=repair, step=step)
        self.repository.save_conversion_result(run_id, result)
        if not successful:
            raise (FindingsConversionCancelled(result) if status == 'cancelled' else FindingsConversionFailure(result))
        return result
