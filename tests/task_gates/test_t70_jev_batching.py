"""T70: recorded mixed wire contract and bounded prepared batch execution.

The fixture is a genuine live response; default tests replay it with no network.
Synthetic edits below exercise controlled malformed/provider-failure boundaries.
"""
import asyncio
import copy
import json
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from profitlab.providers.jev import (
    JevRequest,
    JevResponse,
    LiveJevClient,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    validate_response,
)
from profitlab.providers.transport import ProviderFailure
from profitlab.settings import Settings
from profitlab.v2.findings_batching import (
    AtomicJevItem,
    JevBatchCancelled,
    JevBatchFailure,
    admits,
    execute_jev_batches,
    pack_jev_items,
    run_live_jev_batches,
    serialized,
)
from profitlab.v2.findings_policy import JevPhaseBudget

RECORD = json.loads((Path(__file__).parents[1] / 'fixtures/benchmarks/t70/live-mixed-azz.json').read_text())
SAVED = RECORD['execution']['completed'][0]


class Trace:
    def __init__(self):
        self.rows = []

    def emit(self, **value):
        self.rows.append(value)

    @contextmanager
    def operation(self, name, arguments=None, **metadata):
        output = {}
        yield output
        self.rows.append(dict(name=name, request=arguments, result=output, **metadata))


def item(key, text='Annual diluted shares 30,211'):
    return AtomicJevItem(item_id=key, request=JevRequest(model='jev-1.13.0', state={'source': text},
        questions={'member': NoulQuestion(instructions='Does `state.source` report diluted shares?')}))


async def checkpoint(_value):
    pass


@pytest.mark.asyncio
async def test_real_mixed_response_transport_and_schema():
    request = JevRequest.model_validate(SAVED['batch']['request'])
    response = JevResponse.model_validate(SAVED['response'])
    assert validate_response(request, response) == response
    assert isinstance(response.answers['item_0_q0'], NoulAnswer)
    score = response.answers['item_0_q1']
    assert isinstance(score, ScoreAnswer)
    assert abs(score.score - sum(int(k)*p for k,p in score.probabilities.items())) < .02
    # The preceding real HTTP 200 independently rounded score and probabilities.
    rounded = json.loads((Path(__file__).parents[1] /
        'fixtures/benchmarks/t70/live-rounded-response.json').read_text())
    prior = validate_response(request, JevResponse.model_validate(rounded['response']))
    assert prior.answers['item_0_q1'].score == 2.12
    assert sum(int(k)*p for k,p in prior.answers['item_0_q1'].probabilities.items()) == 2.13
    assert RECORD['provenance']['source_fixture_sha256'] == '7596a538bf783e5d52fea1616806b6ac51fc69a3c41888118d37a96f1d770a27'
    assert response.usage.input_tokens == 491
    trace = Trace()
    def handler(wire):
        assert json.loads(wire.content) == request.model_dump(exclude_none=True)
        assert wire.headers['authorization'] == 'Bearer test-secret'
        return httpx.Response(200, json=response.model_dump())
    client = LiveJevClient(Settings(_env_file=None, typesafe_api_key='test-secret'), trace,
                           transport=httpx.MockTransport(handler))
    assert await client.evaluate(request) == response
    assert any(row.get('name') == 'provider.http' for row in trace.rows)
    for model in (JevRequest, JevResponse):
        assert 'discriminator' in json.dumps(model.model_json_schema())


def test_malformed_ids_types_rubrics_and_distributions_are_rejected():
    request = JevRequest.model_validate(SAVED['batch']['request'])
    good = copy.deepcopy(SAVED['response'])
    variants = []
    bad = copy.deepcopy(good); bad['answers'].pop('item_0_q0'); variants.append(bad)
    bad = copy.deepcopy(good); bad['answers']['extra'] = bad['answers']['item_0_q0']; variants.append(bad)
    bad = copy.deepcopy(good); bad['answers']['item_0_q0'] = bad['answers']['item_0_q1']; variants.append(bad)
    bad = copy.deepcopy(good); bad['answers']['item_0_q1']['legend']['2'] = 'Different'; variants.append(bad)
    bad = copy.deepcopy(good); bad['answers']['item_0_q1']['probabilities']['2'] = .2; variants.append(bad)
    bad = copy.deepcopy(good); bad['answers']['item_0_q1']['score'] = .5; variants.append(bad)
    bad = copy.deepcopy(good); bad['answers']['item_0_q1']['probabilities']['4'] = 0; variants.append(bad)
    bad = copy.deepcopy(good); bad['answers']['item_0_q1']['score'] = float('nan'); variants.append(bad)
    for malformed in variants:
        with pytest.raises(ValueError):
            validate_response(request, JevResponse.model_validate(malformed))
    with pytest.raises(ValidationError):
        ScoreQuestion(instructions='Rate `state`', criteria=['One'])
    with pytest.raises(ValidationError):
        ScoreQuestion(instructions='Rate `state`', criteria=['Level'] * 11)
    # Structured rubric serialization is legal; its text legend is provider-rendered.
    question = ScoreQuestion(instructions={'question': 'Rate `state`'}, criteria=[{'level': 'Low'}, ['High']])
    assert ScoreQuestion.model_validate_json(question.model_dump_json()) == question


@pytest.mark.asyncio
async def test_live_adapter_rejects_wrong_primitive():
    response = copy.deepcopy(SAVED['response'])
    response['answers']['item_0_q0'] = response['answers']['item_0_q1']
    client = LiveJevClient(Settings(_env_file=None, typesafe_api_key='test-secret'), Trace(),
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)))
    with pytest.raises(ProviderFailure, match='Answer type'):
        await client.evaluate(JevRequest.model_validate(SAVED['batch']['request']))


def test_packing_preserves_whole_items_scope_overhead_caps_and_provider_limits():
    budget = JevPhaseBudget(questions=2)
    inputs = [item(str(i)) for i in range(5)]
    plan = pack_jev_items(inputs + [item('huge', 'x'*21000)], budget, max_requests=2)
    assert [len(x.request.questions) for x in plan.batches] == [2, 2]
    assert [(x.item_id, x.reason) for x in plan.omissions] == [
        ('huge', 'atomic_request_limit'), ('4', 'request_count_limit')]
    first = plan.batches[0]
    assert first.request.state['items']['item_0'] == inputs[0].request.state
    assert 'state.items.item_1' in first.request.questions['item_1_q0'].instructions['scope']
    assert first.routes['item_1_q0'] == ('1', 'member')
    assert all(admits(x.request, budget) for x in plan.batches)
    assert pack_jev_items(inputs, budget, 10) == pack_jev_items(inputs, budget, 10)
    with pytest.raises(ValueError, match='unique'):
        pack_jev_items([item('same'), item('same')], budget, 1)
    instruction_heavy = item('overhead').model_dump()
    instruction_heavy['request']['questions']['member']['instructions'] = 'state.source '*2000
    assert pack_jev_items([AtomicJevItem.model_validate(instruction_heavy)], budget, 1).omissions
    # Provider per-question guard still applies when local character/token caps are raised.
    wide = JevPhaseBudget(serialized_characters=100000, estimated_input_tokens=32000,
                          characters_per_token=4)
    assert not admits(pack_jev_items([item('x')], budget, 1).batches[0].request.model_copy(
        update={'state': '界'*12000}), wide)
    unknown = item('unknown').request.model_copy(update={'model':'unverified-custom'})
    with pytest.raises(ValueError, match='Unverified'):
        admits(unknown, budget)
    assert len(serialized(first.request)) > len(json.dumps(first.request.state))


@pytest.mark.asyncio
async def test_shared_bounded_execution_checkpoints_cache_and_accounting():
    plan = pack_jev_items([item(str(i)) for i in range(5)], JevPhaseBudget(questions=2), 10)
    active = peak = calls = 0
    release = asyncio.Event()
    ready = asyncio.Event()
    saved = []
    class Client:
        async def evaluate(self, request):
            nonlocal active, peak, calls
            calls += 1; active += 1; peak = max(peak, active)
            if active == 2:
                ready.set()
            try:
                await release.wait()
                return JevResponse(model='jev-1.13.0', answers={key: NoulAnswer(type='noul', noul=.8)
                    for key in request.questions}, usage={'input_tokens':10, 'output_tokens':2})
            finally:
                active -= 1
    async def save(value):
        saved.append(value)
    task = asyncio.create_task(execute_jev_batches(plan, Client(), concurrency=2,
        deadline_seconds=2, checkpoint=save))
    await asyncio.wait_for(ready.wait(), 1)
    assert calls == 2
    release.set()
    result = await task
    assert peak == 2 and calls == 3 and len(saved) == 3
    assert result.accounting.completed == 3 and result.accounting.usage.input_tokens == 30
    assert result.model_validate_json(result.model_dump_json()) == result
    cache = {x.batch.batch_id:x.response for x in saved}
    replay = await execute_jev_batches(plan, Client(), concurrency=2, deadline_seconds=2,
                                       checkpoint=save, cached=cache)
    assert replay.accounting.cached == 3 and replay.accounting.dispatched == 0
    assert replay.accounting.usage is None and calls == 3
    # Cache replay remaps routes using current caller IDs.
    remapped = pack_jev_items([item('new-'+str(i)) for i in range(5)], JevPhaseBudget(questions=2), 10)
    replay = await execute_jev_batches(remapped, Client(), concurrency=2, deadline_seconds=2,
                                      checkpoint=save, cached=cache)
    assert replay.completed[0].batch.routes['item_0_q0'][0] == 'new-0'
    assert replay.accounting.cached == 3


@pytest.mark.asyncio
async def test_failure_deadline_cancellation_preserve_checkpoints_and_stop_workers():
    plan = pack_jev_items([item(str(i)) for i in range(3)], JevPhaseBudget(questions=1), 10)
    saved = []
    waiting = asyncio.Event()
    stopped = asyncio.Event()
    class Client:
        calls = 0
        mode = 'fail'
        async def evaluate(self, request):
            self.calls += 1
            if self.calls == 1:
                return JevResponse(model='jev-1.13.0', answers={'item_0_q0':NoulAnswer(type='noul', noul=.9)},
                                   usage={'input_tokens':1,'output_tokens':1})
            if self.mode == 'fail':
                raise ProviderFailure('transport', 'Controlled failure')
            waiting.set()
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()
    async def save(value):
        saved.append(value)
    client = Client()
    with pytest.raises(JevBatchFailure) as failed:
        await execute_jev_batches(plan, client, concurrency=1, deadline_seconds=1, checkpoint=save)
    assert failed.value.result.status == 'failed'
    assert failed.value.result.accounting.failed == 1
    assert len(saved) == 1 and client.calls == 2
    for mode in ('deadline', 'cancel'):
        client = Client(); client.mode = 'wait'
        waiting.clear(); stopped.clear()
        task = asyncio.create_task(execute_jev_batches(plan, client, concurrency=1,
            deadline_seconds=.02 if mode == 'deadline' else 2, checkpoint=save))
        await asyncio.wait_for(waiting.wait(), 1)
        if mode == 'cancel':
            task.cancel()
        with pytest.raises(JevBatchFailure if mode == 'deadline' else JevBatchCancelled) as stopped_error:
            await task
        result = stopped_error.value.result
        assert result.status == ('interrupted' if mode == 'deadline' else 'cancelled')
        assert result.accounting.completed == 1 and result.accounting.failed == 0
        assert len(result.completed) == 1 and client.calls == 2 and stopped.is_set()
    # A client that skips the HTTP adapter cannot bypass ID validation.
    class WrongClient:
        async def evaluate(self, request):
            return JevResponse(model='jev-1.13.0', answers={}, usage={'input_tokens':0,'output_tokens':0})
    with pytest.raises(JevBatchFailure) as malformed:
        await execute_jev_batches(plan, WrongClient(), concurrency=1, deadline_seconds=1, checkpoint=save)
    assert malformed.value.result.accounting.failed == 1


@pytest.mark.asyncio
async def test_empty_and_omitted_work_do_not_dispatch_and_live_uses_shared_transport(monkeypatch):
    async def no_network(*_args, **_kwargs):
        raise AssertionError('Must not call provider')
    monkeypatch.setattr(LiveJevClient, 'evaluate', no_network)
    empty = pack_jev_items([], JevPhaseBudget(), 1)
    result = await run_live_jev_batches(empty,
        Settings(_env_file=None, typesafe_api_key='test-secret'), Trace(),
        deadline_seconds=1, checkpoint=checkpoint)
    assert result.status == 'completed' and result.accounting.planned == 0
    omitted = pack_jev_items([item('large','x'*21000)], JevPhaseBudget(), 1)
    result = await execute_jev_batches(omitted, None, concurrency=1, deadline_seconds=1,
                                       checkpoint=checkpoint)
    assert result.status == 'partial' and result.accounting.dispatched == 0
    assert result.omitted_items == len(result.omissions) == 1
    assert result.accounting.omitted == result.accounting.planned == 1
