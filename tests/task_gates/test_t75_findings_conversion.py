"""T75 selected conversion contracts; controlled outputs are not live measurements."""
import asyncio
import copy
import json
from decimal import Decimal

import pytest
from test_t71_findings_candidates import create_repo
from test_t74_findings_ranking import bundles, rank

from profitlab.providers.jev import TokenUsage
from profitlab.v2.findings_contracts import (
    ConversionResponse,
    FindingsConversionResult,
    FindingsPhase,
    visible_numeric_spans,
)
from profitlab.v2.findings_conversion import (
    FindingsConversionCancelled,
    FindingsConversionFailure,
    FindingsConversionService,
    build_conversion_request,
    validate_conversion,
)
from profitlab.v2.findings_examples import safe_findings_examples
from profitlab.v2.findings_policy import FindingsPolicy


def proposal(bundle, index=0):
    span = bundle.numeric_spans[index]
    return {'bundle_id':bundle.bundle_id, 'concept':bundle.concept.value,
        'source_range':bundle.source.source_range.model_dump(mode='json'),
        'numeric_span':span.model_dump(mode='json'), 'exact_quote':bundle.source.exact_text,
        'amount':str(span.displayed_amount)}


def options():
    return {'model':'controlled-llm', 'base_url':'https://example.invalid/v1'}


@pytest.mark.parametrize('mode', ['tool', 'native'])
def test_exact_wire_schema_budget_and_selected_metadata_validation(mode):
    examples = safe_findings_examples()
    state = examples['conversion_state']
    policy = FindingsPolicy()
    request = build_conversion_request(state, policy, output_mode=mode, **options())
    assert 'FindingConversionProposal' in json.dumps(request.body)
    assert request.body['messages'] == examples['conversion_messages']
    # Messages fit but the actual output schema/tool wrapper does not.
    message_size = len(json.dumps(request.body['messages'], ensure_ascii=False))
    bounded = FindingsPolicy(conversion_request_characters=message_size + 1)
    with pytest.raises(ValueError, match='envelope'):
        build_conversion_request(state, bounded, output_mode=mode, **options())
    with pytest.raises(ValueError, match='envelope'):
        build_conversion_request(state, FindingsPolicy(conversion_input_tokens=256), **options())
    raw = examples['contracts']['proposal'].model_dump(mode='json')
    publication, diagnostic = validate_conversion(raw, state, 'controlled-llm')
    assert diagnostic.state == 'accepted'
    assert publication.finding.scale == 'millions' and publication.finding.amount == 1200
    assert publication.finding.context_references == publication.context_references
    invalid = copy.deepcopy(raw)
    invalid['period']['source_references'][0]['start_line'] = 99
    invalid['period']['source_references'][0]['end_line'] = 99
    assert validate_conversion(invalid, state, 'controlled-llm')[0] is None
    invalid = copy.deepcopy(raw); invalid['concept'] = 'diluted_eps'
    assert validate_conversion(invalid, state, 'controlled-llm')[0] is None
    invalid = copy.deepcopy(raw); invalid['bundle_id'] = 'unselected'
    assert validate_conversion(invalid, state, 'controlled-llm')[0] is None


def test_multi_year_row_exact_span_sign_decimal_and_identity():
    state = safe_findings_examples()['conversion_state']
    bundle = state.selected_bundles[0]
    text = '2025 | (1,200.50) | 2024 | 1,100 | (1,200.50)'
    changed = bundle.model_copy(update={'source':bundle.source.model_copy(update={'exact_text':text}),
                                       'numeric_spans':visible_numeric_spans(text)})
    state = type(state)(filing=state.filing, selected_bundles=[changed])
    raw = proposal(changed, 1)
    accepted, _ = validate_conversion(raw, state, 'controlled-llm')
    assert accepted.finding.amount == Decimal('-1200.50')
    assert accepted.numeric_span.start_character == 7
    repeated, _ = validate_conversion(proposal(changed, 4), state, 'controlled-llm')
    assert repeated.finding.finding_id != accepted.finding.finding_id
    for field, value in [('amount','1200.50'), ('amount','NaN'), ('exact_quote','2025')]:
        invalid = {**raw, field:value}
        assert validate_conversion(invalid, state, 'controlled-llm')[0] is None
    invalid = copy.deepcopy(raw); invalid['numeric_span']['start_character'] += 1
    assert validate_conversion(invalid, state, 'controlled-llm')[0] is None
    assert validate_conversion(raw, state, 'another-model')[0].finding.finding_id == accepted.finding.finding_id


@pytest.mark.asyncio
async def test_real_saved_rows_repair_preserves_accepted_and_checkpoint_restart(tmp_path):
    policy = FindingsPolicy()
    document, filing, values = bundles(policy, count=3)
    repo, _, ranked = await rank(tmp_path, document, filing, values, policy)
    calls = []
    async def client(request):
        calls.append(request)
        b = request.state.selected_bundles[0]
        valid = proposal(b)
        if not request.repair_bundle_ids:
            invalid = {**proposal(b, min(1,len(b.numeric_spans)-1)), 'exact_quote':'invented quote'}
            findings = [valid, valid, invalid]
        else:
            # Repair may omit the first accepted value; it must survive.
            findings = [proposal(b, min(1,len(b.numeric_spans)-1))]
        return ConversionResponse(model='controlled-llm', findings=findings,
            usage=TokenUsage(input_tokens=10, output_tokens=5), response_id='controlled-response')
    service = FindingsConversionService(repo, policy)
    result = await service.convert('test', ranked.conversion_packs, values, ranked.ranks, document,
                                   client=client, **options())
    assert len(calls) == 2 and calls[1].repair_bundle_ids
    first_id = next(d.proposal.numeric_span.start_character for d in result.diagnostics if d.state == 'accepted')
    assert any(p.numeric_span.start_character == first_id for p in result.publications)
    assert result.conversion.usage.input_tokens == 10 and result.repair.completed == 1
    assert any(p.finding.repair_attempted for p in result.publications) or len(result.publications) == 1
    assert len({p.finding.finding_id for p in result.publications}) == len(result.publications)
    assert FindingsConversionResult.model_validate_json(result.model_dump_json()) == result
    saved = repo.findings_artifacts('test', FindingsConversionResult)[0]
    assert saved == result
    restarted = await service.convert('test', ranked.conversion_packs, values, ranked.ranks, document,
                                      client=client, **options())
    assert len(calls) == 2 and restarted.conversion.cached == restarted.repair.cached == 1
    assert restarted.conversion.dispatched == restarted.repair.dispatched == 0
    assert restarted.publications == result.publications


@pytest.mark.asyncio
async def test_empty_failure_cancel_and_no_implicit_extra_work(tmp_path):
    policy = FindingsPolicy()
    repo = create_repo(tmp_path)
    document, filing, values = bundles(policy, count=1)
    service = FindingsConversionService(repo, policy)
    async def forbidden(request):
        raise AssertionError('Empty conversion must not call a model')
    empty = await service.convert('test', [], [], [], document, client=forbidden, **options())
    assert empty.publications == [] and empty.conversion.planned == 0
    _, _, ranked = await rank(tmp_path, document, filing, values, policy)
    for cancelled in (False, True):
        async def failing(request, cancelled=cancelled):
            if cancelled:
                raise asyncio.CancelledError()
            raise RuntimeError('controlled failure')
        with pytest.raises(FindingsConversionCancelled if cancelled else FindingsConversionFailure) as caught:
            await service.convert('test', ranked.conversion_packs, values, ranked.ranks, document,
                                  client=failing, **options())
        assert caught.value.result.publications == []
        assert caught.value.result.conversion.failed == 1
    assert repo.findings_step('test', FindingsPhase.CONVERT).status == 'cancelled'


def test_semantic_cache_remaps_current_references_and_invalidates_policy(tmp_path):
    from profitlab.v2.findings_contracts import CompletedConversionBatch, ConversionState
    examples = safe_findings_examples()
    state = examples['conversion_state']
    policy = FindingsPolicy()
    original = build_conversion_request(state, policy, **options())
    repo = create_repo(tmp_path)
    response = ConversionResponse(model='controlled-llm',
        findings=[examples['contracts']['proposal'].model_dump(mode='json')])
    repo.save_conversion_checkpoint('test', CompletedConversionBatch(request=original, response=response))
    value = state.model_dump_json().replace('illustrative-document', 'current-document').replace('illustrative-filing', 'current-filing')
    current = build_conversion_request(ConversionState.model_validate_json(value), policy, **options())
    assert original.cache_key() == current.cache_key()
    saved = repo.conversion_checkpoint(current)
    assert saved.cached and saved.request == current
    published, _ = validate_conversion(saved.response.findings[0], current.state, saved.response.model)
    assert published.finding.source_range.document_id == 'current-document'
    assert all(x.document_id == 'current-document' for x in published.context_references)
    changed = build_conversion_request(current.state, FindingsPolicy(conversion_output_tokens=777), **options())
    assert repo.conversion_checkpoint(changed) is None
    changed_model = build_conversion_request(current.state, policy, model='other-model', base_url=options()['base_url'])
    assert repo.conversion_checkpoint(changed_model) is None


@pytest.mark.asyncio
async def test_full_envelope_partial_omissions_and_repair_size_cap(tmp_path):
    policy = FindingsPolicy()
    document, filing, values = bundles(policy, count=3)
    repo, _, ranked = await rank(tmp_path, document, filing, values, policy)
    # Initial wire size fits; a large rejected quote makes repair oversized.
    state = ranked.conversion_packs[0].state
    request = build_conversion_request(state, policy, **options())
    cap = len(json.dumps(request.body, ensure_ascii=False)) + 10
    bounded = policy.model_copy(update={'conversion_request_characters':cap})
    calls = []
    async def invalid(request):
        calls.append(request)
        b = request.state.selected_bundles[0]
        return ConversionResponse(model='controlled-llm', findings=[proposal(b),
            {**proposal(b), 'exact_quote':'X'*cap}])
    result = await FindingsConversionService(repo, bounded).convert('test', ranked.conversion_packs,
        values, ranked.ranks, document, client=invalid, **options())
    assert result.publications and result.repair.omitted == 1 and len(calls) == 1
    # T74 messages remain valid; schema wrapper alone forces all bundles out.
    bounded = policy.model_copy(update={'conversion_input_tokens':256})
    async def forbidden(request):
        raise AssertionError('Oversized final envelope must never dispatch')
    result = await FindingsConversionService(repo, bounded).convert('test', ranked.conversion_packs,
        values, ranked.ranks, document, client=forbidden, **options())
    assert result.step.status == 'partial' and result.step.omissions
    assert result.conversion.dispatched == 0 and not result.publications


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['tool', 'native'])
async def test_actual_sdk_wire_matches_bounded_request_and_records_model_usage(mode):
    from contextlib import contextmanager

    import httpx

    from profitlab.settings import Settings
    from profitlab.v2.findings_conversion import live_conversion

    class Trace:
        def emit(self, **kwargs):
            pass

        @contextmanager
        def operation(self, *args, **kwargs):
            assert kwargs['stage'] == 'findings'
            yield {}
    state = safe_findings_examples()['conversion_state']
    request = build_conversion_request(state, FindingsPolicy(), output_mode=mode, **options())
    seen = []
    def handle(wire):
        seen.append(json.loads(wire.content))
        output = json.dumps({'schema_version':2, 'findings':[proposal(state.selected_bundles[0])]})
        message = {'role':'assistant', 'content':output} if mode == 'native' else {
            'role':'assistant', 'content':None, 'tool_calls':[{'id':'output-1', 'type':'function',
                'function':{'name':'convert_findings', 'arguments':output}}]}
        return httpx.Response(200, json={'id':'response-1', 'object':'chat.completion', 'created':1,
            'model':'controlled-llm', 'choices':[{'index':0, 'message':message,
                'finish_reason':'stop' if mode == 'native' else 'tool_calls'}],
            'usage':{'prompt_tokens':123, 'completion_tokens':45, 'total_tokens':168}})
    settings = Settings(_env_file=None, llm_api_key='test-key')
    result = await live_conversion(request, settings, Trace(), transport=httpx.MockTransport(handle))
    assert seen == [request.body]
    assert result.model == 'controlled-llm' and result.usage.input_tokens == 123
    assert result.response_id == 'response-1'
    assert validate_conversion(result.findings[0], state, result.model)[0]


@pytest.mark.asyncio
async def test_deadline_with_cached_work_and_terminal_rejections(tmp_path):
    policy = FindingsPolicy(max_repair_requests=0)
    document, filing, values = bundles(policy, count=1)
    repo, _, ranked = await rank(tmp_path, document, filing, values, policy)
    calls = []
    async def invalid(request):
        calls.append(request)
        b = request.state.selected_bundles[0]
        return ConversionResponse(model='controlled-llm', findings=[proposal(b),
            {**proposal(b), 'bundle_id':'unselected bundle with invalid ID'},
            {**proposal(b), 'amount':'NaN'}])
    service = FindingsConversionService(repo, policy)
    result = await service.convert('test', ranked.conversion_packs, values, ranked.ranks, document,
                                   client=invalid, **options())
    assert result.publications and result.repair.planned == 0 and len(calls) == 1
    assert sum(d.state == 'rejected' for d in result.diagnostics) == 2
    with pytest.raises(FindingsConversionFailure) as caught:
        await service.convert('test', ranked.conversion_packs, values, ranked.ranks, document,
                              client=invalid, deadline_seconds=0, **options())
    assert caught.value.result.publications == [] and len(calls) == 1
    assert repo.findings_step('test', FindingsPhase.CONVERT).status == 'failed'


def test_recorded_real_llm_response_retains_fixed_concept_offsets_and_uncertainty():
    from pathlib import Path

    from profitlab.v2.findings_contracts import CompletedConversionBatch
    path = Path(__file__).parents[1] / 'fixtures/benchmarks/t75/live-conversion-azz.json'
    recorded = json.loads(path.read_text())
    batch = CompletedConversionBatch.model_validate(recorded['result']['batches'][0])
    assert recorded['provenance']['selection'].startswith('Controlled')
    assert batch.response.model == 'gpt-5.6-luna'
    assert batch.response.usage.input_tokens == 2034
    publications = [validate_conversion(raw, batch.request.state, batch.response.model)[0]
                    for raw in batch.response.findings]
    assert all(publications) and len(publications) == 2
    assert {p.finding.finding_type for p in publications} == {'annual_profit'}
    assert {p.finding.amount for p in publications} == {Decimal(317260), Decimal(53635)}
    assert all(p.finding.period is None and p.finding.limitations for p in publications)
