import asyncio
import gzip
import json
from decimal import Decimal

import httpx
import pytest
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RequestUsage

from profitlab.demo import DemoService
from profitlab.providers.jev import JevRequest, LiveJevClient, NoulQuestion
from profitlab.providers.llm import probe_llm
from profitlab.providers.service import ProbeService
from profitlab.providers.transport import ProviderFailure
from profitlab.settings import Settings
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder
from profitlab.web.app import create_app


def setup(tmp_path):
    settings = Settings(_env_file=None, PROFITLAB_DATA_DIR=tmp_path,
                        typesafe_api_key='fixture-secret-jev', llm_api_key='fixture-secret-llm',
                        llm_base_url='https://custom.invalid/v1', llm_model='custom-model',
                        llm_reasoning_effort='none',
                        typesafe_base_url='https://decision.invalid', max_http_attempts=2)
    DemoService(tmp_path).create('probe-test', 'T01')
    repo = Repository(tmp_path)
    return settings, repo, TraceRecorder(repo, 'probe-test', settings.redactor())


def request():
    return JevRequest(model='jev-configured', state={'excerpt': 'annual'},
                      questions={'annual': NoulQuestion(instructions='Annual report?')})


def payloads(repo, recorder):
    return [json.loads(repo.read('probe-test', identifier)) for event in recorder.history()[0]
            for identifier in (event.request_artifact_id, event.result_artifact_id) if identifier]


@pytest.mark.asyncio
async def test_jev_retry_contract_and_errors(tmp_path, monkeypatch):
    settings, repo, recorder = setup(tmp_path)
    sleeps = []

    async def sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr('profitlab.providers.transport.asyncio.sleep', sleep)
    requests = []

    def handle(req):
        requests.append(req)
        if len(requests) < 2:
            return httpx.Response(529, json={'error': 'fixture-secret-jev'})
        return httpx.Response(200, json={
            'model': 'jev-actual', 'answers': {'annual': {'type': 'noul', 'noul': .9}},
            'usage': {'input_tokens': 10, 'output_tokens': 2}})

    result = await LiveJevClient(settings, recorder, httpx.MockTransport(handle)).evaluate(request())
    assert result.model == 'jev-actual'
    assert str(requests[0].url) == 'https://decision.invalid/v1/systemone'
    assert json.loads(requests[0].content)['model'] == 'jev-configured'
    assert sleeps == [.5]
    assert len([e for e in recorder.history()[0] if e.kind == 'retry']) == 1
    for status, code in ((401, 'authentication'), (422, 'request_validation'), (429, 'overloaded')):
        count = []

        def fail(req, count=count, status=status):
            count.append(req)
            return httpx.Response(status, json={'error': 'fixture-secret-jev'})

        with pytest.raises(ProviderFailure, match=code):
            await LiveJevClient(settings, recorder, httpx.MockTransport(fail)).evaluate(request())
        assert len(count) == (2 if status == 429 else 1)
    for answers in ({'annual': {'type': 'noul', 'noul': 2}},
                    {'wrong': {'type': 'noul', 'noul': .5}}):
        with pytest.raises(ProviderFailure, match='response_validation'):
            await LiveJevClient(settings, recorder, httpx.MockTransport(lambda req, answers=answers:
                httpx.Response(200, json={'model': 'actual', 'answers': answers,
                                         'usage': {'input_tokens': 1, 'output_tokens': 1}})
            )).evaluate(request())
    recorder.export(tmp_path / 'export')
    assert 'fixture-secret-jev' not in ''.join(p.read_text() for p in
        (tmp_path / 'export').rglob('*.json'))
    assert any('REDACTED' in json.dumps(p) for p in payloads(repo, recorder))


@pytest.mark.asyncio
async def test_chat_completions_exact_config_history_and_tool(tmp_path):
    settings, repo, recorder = setup(tmp_path)
    requests = []

    def handle(req):
        body = json.loads(req.content)
        requests.append(body)
        assert str(req.url) == 'https://custom.invalid/v1/chat/completions'
        assert body['model'] == 'custom-model'
        assert body['reasoning_effort'] == 'none'
        assert req.headers['authorization'] == 'Bearer fixture-secret-llm'
        tool = ('read_probe' if len(requests) == 1 else
                next(t['function']['name'] for t in body['tools']
                     if t['function']['name'] != 'read_probe'))
        return httpx.Response(200, json={
            'id': f'chat-{len(requests)}', 'object': 'chat.completion', 'created': 1,
            'model': 'returned-model', 'choices': [{'index': 0, 'finish_reason': 'tool_calls',
                'message': {'role': 'assistant', 'content': None, 'tool_calls': [{
                    'id': f'call-{len(requests)}', 'type': 'function', 'function': {
                        'name': tool, 'arguments': '{}' if tool == 'read_probe' else
                        '{"value":"profitlab-probe-v1"}'}}]}}],
            'usage': {'prompt_tokens': 12, 'completion_tokens': 3, 'total_tokens': 15}})

    result = await probe_llm(settings, recorder, transport=httpx.MockTransport(handle))
    assert result['actual_models'] == ['returned-model']
    assert len(requests) == 2
    assert any(m['role'] == 'tool' for m in requests[1]['messages'])
    events = recorder.history()[0]
    tool = next(e for e in events if e.actor == 'agent_tool' and e.kind == 'start')
    assert tool.call_id == 'call-1'
    histories = [p['native_messages'] for p in payloads(repo, recorder) if 'native_messages' in p]
    restored = ModelMessagesTypeAdapter.validate_python(histories[-1])
    assert any(part.part_kind == 'tool-return' for m in restored for part in m.parts)
    assert any('usage' in p for p in payloads(repo, recorder))
    recorder.export(tmp_path / 'export')
    assert 'fixture-secret-llm' not in ''.join(p.read_text() for p in
        (tmp_path / 'export').rglob('*.json'))


@pytest.mark.asyncio
async def test_unsupported_and_interrupted_keep_native_history(tmp_path):
    settings, repo, recorder = setup(tmp_path)

    def unsupported(messages, info):
        return ModelResponse(parts=[TextPart('I cannot call tools.')])

    with pytest.raises(ProviderFailure, match='compatibility'):
        await probe_llm(settings, recorder, model=FunctionModel(unsupported))
    assert any('native_messages' in p for p in payloads(repo, recorder))

    def no_read(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name,
                                                {'value': 'profitlab-probe-v1'})])

    with pytest.raises(ProviderFailure, match='compatibility_tool'):
        await probe_llm(settings, recorder, model=FunctionModel(no_read))

    def interrupted(messages, info):
        if len(messages) > 1:
            raise asyncio.CancelledError()
        return ModelResponse(parts=[ToolCallPart('read_probe', {}, tool_call_id='interrupt-read')])

    with pytest.raises(asyncio.CancelledError):
        await probe_llm(settings, recorder, model=FunctionModel(interrupted))
    history = [p['native_messages'] for p in payloads(repo, recorder) if 'native_messages' in p][-1]
    assert any(part.part_kind == 'tool-return' for message in
               ModelMessagesTypeAdapter.validate_python(history) for part in message.parts)
    assert recorder.history()[0][-1].status == 'interrupted'


def test_offline_probe_and_missing_credentials(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    settings = Settings(_env_file=None, PROFITLAB_DATA_DIR=tmp_path)
    import socket

    monkeypatch.setenv('TYPESAFE_API_KEY', '')
    monkeypatch.setenv('LLM_API_KEY', '')
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Network forbidden'))
    run = DemoService(tmp_path).create('offline', 'T07')
    assert run.status == 'completed'
    assert Repository(tmp_path).manifest('offline').provider_models == {
        'jev': 'fixture-jev-1', 'llm': 'fixture-function-1'}
    with TestClient(create_app(settings)) as client:
        page = client.get('/runs/offline/trace')
        assert page.status_code == 200
        assert 'fake-jev' in page.text and 'Fixture agent history' in page.text
    failed = ProbeService(settings).create('llm')
    assert failed.status == 'failed'
    assert 'LLM_API_KEY is missing' in failed.limitation
    assert not failed.provider_models


@pytest.mark.asyncio
async def test_repairs_are_separate_and_quota_does_not_retry(tmp_path):
    settings, _repo, recorder = setup(tmp_path)
    calls = []

    def repair(messages, info):
        calls.append(True)
        if len(calls) == 1:
            part = ToolCallPart('read_probe', {}, tool_call_id='repair-read')
        else:
            part = ToolCallPart(info.output_tools[0].name,
                                {'value': 123} if len(calls) == 2 else
                                {'value': 'profitlab-probe-v1'}, tool_call_id='output-call')
        return ModelResponse(parts=[part], model_name='fixture-repair')

    result = await probe_llm(settings, recorder, model=FunctionModel(repair))
    assert result['structured_repairs'] == 1
    assert len(calls) == 3
    assert len([e for e in recorder.history()[0] if e.kind == 'structured_repair']) == 1
    assert not [e for e in recorder.history()[0] if e.kind == 'retry']
    attempts = []

    def quota(req):
        attempts.append(True)
        return httpx.Response(429, json={'error': {'type': 'insufficient_quota',
                                                 'code': 'credit_balance_exhausted'}})

    with pytest.raises(ProviderFailure, match='quota|compatibility'):
        await probe_llm(settings, recorder, transport=httpx.MockTransport(quota))
    assert len(attempts) == 1


def test_default_luna_chat_effort_is_explicit_and_overrideable(tmp_path):
    from profitlab.providers.llm import model_factory

    settings = Settings(_env_file=None, PROFITLAB_DATA_DIR=tmp_path,
                        llm_api_key='fixture-secret', llm_model='gpt-5.6-luna',
                        llm_base_url='https://api.openai.com/v1')
    # Construction only; no request or paid model call.
    client = httpx.AsyncClient()
    assert model_factory(settings, client).settings == {'openai_reasoning_effort': 'none'}
    settings.llm_reasoning_effort = 'low'
    assert model_factory(settings, client).settings == {'openai_reasoning_effort': 'low'}
    settings.llm_reasoning_effort = None
    settings.llm_model = 'custom-model'
    assert model_factory(settings, client).settings is None
    asyncio.run(client.aclose())


@pytest.mark.asyncio
async def test_compressed_wire_responses_are_not_decoded_twice(tmp_path):
    settings, _repo, recorder = setup(tmp_path)
    body = {'model': 'jev-actual', 'answers': {'annual': {'type': 'noul', 'noul': .9}},
            'usage': {'input_tokens': 10, 'output_tokens': 2}}
    compressed = gzip.compress(json.dumps(body).encode())
    transport = httpx.MockTransport(lambda req: httpx.Response(
        200, headers={'Content-Encoding': 'gzip', 'Content-Length': str(len(compressed))},
        content=compressed))
    result = await LiveJevClient(settings, recorder, transport).evaluate(request())
    assert result.model == 'jev-actual'
    assert result.answers['annual'].noul == .9


@pytest.mark.asyncio
async def test_decimal_usage_cost_survives_agent_trace_and_export(tmp_path):
    settings, repo, recorder = setup(tmp_path)
    count = 0

    def respond(messages, info):
        nonlocal count
        count += 1
        part = (ToolCallPart('read_probe', {}, tool_call_id='decimal-read') if count == 1 else
                ToolCallPart(info.output_tools[0].name, {'value': 'profitlab-probe-v1'},
                             tool_call_id='decimal-output'))
        return ModelResponse(parts=[part], model_name='decimal-provider',
                             usage=RequestUsage(input_tokens=1, output_tokens=1,
                                                cost=Decimal('0.0000000012300')))

    result = await probe_llm(settings, recorder, model=FunctionModel(respond))
    assert result['value'] == 'profitlab-probe-v1'
    snapshots = [p for p in payloads(repo, recorder) if 'native_messages' in p]
    assert snapshots[-1]['usage']['cost'] == '2.4600E-9'
    assert Decimal(snapshots[-1]['usage']['cost']) == Decimal('0.0000000024600')
    recorder.export(tmp_path / 'export')
    exported = [json.loads(p.read_text()) for p in (tmp_path / 'export/payloads').glob('*.json')]
    assert any(p.get('usage', {}).get('cost') == '2.4600E-9' for p in exported if isinstance(p, dict))
