"""Explicit Chat Completions configuration and an observable capability probe."""
import json
from dataclasses import asdict
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, NativeOutput, RunContext
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from profitlab.providers.transport import ProviderFailure, TracedTransport


class ProbeOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    value: str


def model_factory(settings, http_client):
    if not settings.llm_api_key.get_secret_value():
        raise ProviderFailure('configuration', 'LLM_API_KEY is missing.')
    sdk = AsyncOpenAI(base_url=settings.llm_base_url,
                      api_key=settings.llm_api_key.get_secret_value(),
                      max_retries=0, http_client=http_client)
    effort = settings.llm_reasoning_effort
    if (effort is None and settings.llm_model == 'gpt-5.6-luna'
            and urlsplit(settings.llm_base_url).hostname == 'api.openai.com'):
        # The live API rejects function tools with the model's default reasoning effort.
        effort = 'none'
    return OpenAIChatModel(settings.llm_model, provider=OpenAIProvider(openai_client=sdk),
                           settings={'openai_reasoning_effort': effort} if effort else None)


def fixture_model(recorder):
    def respond(messages, info):
        with recorder.operation('model.request.fixture', {
            'messages': json.loads(ModelMessagesTypeAdapter.dump_json(messages)),
            'tools': [asdict(tool) for tool in info.function_tools],
            'output_tools': [asdict(tool) for tool in info.output_tools],
        }, actor='model', provider='fake-llm', stage='probe') as output:
            tool_returns = [part for message in messages for part in message.parts
                            if part.part_kind == 'tool-return' and part.tool_name == 'read_probe']
            part = (ToolCallPart(info.output_tools[0].name, {'value': 'profitlab-probe-v1'},
                                 tool_call_id='fixture-output') if tool_returns else
                    ToolCallPart('read_probe', {}, tool_call_id='fixture-read'))
            response = ModelResponse(parts=[part], model_name='fixture-function-1')
            output.update(response=json.loads(ModelMessagesTypeAdapter.dump_json([response])), synthetic=True)
            return response
    return FunctionModel(respond, model_name='fixture-function-1')


async def probe_llm(settings, recorder, *, fake=False, transport=None, model=None):
    provider = 'fake-llm' if fake else 'llm'
    conversation = 'conversation-' + uuid4().hex
    async with httpx.AsyncClient(
        transport=TracedTransport(recorder, settings, provider, transport),
        timeout=settings.provider_timeout,
    ) as client:
        chosen = model or (fixture_model(recorder) if fake else model_factory(settings, client))
        output_type = ProbeOutput if fake or settings.llm_output_mode == 'tool' else NativeOutput(
            ProbeOutput, strict=True)
        agent = Agent(chosen, output_type=output_type, retries=settings.structured_output_repairs,
                      model_settings={'timeout': settings.provider_timeout},
                      instructions='Call read_probe once, then return its exact value as typed output.')
        calls = []

        @agent.tool
        def read_probe(ctx: RunContext) -> str:
            """Read a constant local compatibility marker. No external effects."""
            with recorder.operation('read_probe', {}, actor='agent_tool', stage='probe',
                                     provider=provider, call_id=ctx.tool_call_id) as output:
                calls.append(True)
                output['value'] = 'profitlab-probe-v1'
                return 'profitlab-probe-v1'

        observed_repairs = set()

        def save_history(run):
            for index, message in enumerate(run.all_messages()):
                for part_index, part in enumerate(message.parts):
                    if part.part_kind == 'retry-prompt' and (index, part_index) not in observed_repairs:
                        observed_repairs.add((index, part_index))
                        recorder.emit(kind='structured_repair', span_id=conversation,
                                      actor='model', stage='probe', provider=provider,
                                      summary='Output/tool validation feedback; not a transport retry.',
                                      result=json.loads(ModelMessagesTypeAdapter.dump_json([message])))
            recorder.emit(kind='conversation', span_id=conversation, actor='model', stage='probe',
                          provider=provider, summary='Fixture agent history' if fake else
                          'Observable agent history', result={
                              'native_messages': json.loads(run.all_messages_json()),
                              'synthetic': fake, 'conversation_id': conversation,
                              'usage': asdict(run.usage),
                              'usage_note': 'Framework estimates; no provider usage.' if fake
                              else 'Provider-reported usage when supplied.',
                          })

        with recorder.operation('llm.compatibility', {
            'requested_model': chosen.model_name, 'base_url': settings.llm_base_url if not fake
            else 'local fixture', 'output_mode': settings.llm_output_mode,
            'structured_output_repairs': settings.structured_output_repairs,
            'model_settings': chosen.settings,
        }, provider=provider, stage='probe', actor='model') as output:
            try:
                async with agent.iter('Read the compatibility marker and return {"value": marker}.',
                                      usage_limits=UsageLimits(request_limit=4,
                                                               tool_calls_limit=2)) as run:
                    try:
                        async for _node in run:
                            save_history(run)
                        if not calls:
                            raise ProviderFailure('compatibility_tool',
                                                  'No read_probe call was observed.')
                        if len(calls) != 1 or run.result.output.value != 'profitlab-probe-v1':
                            raise ProviderFailure('compatibility_output',
                                                  'Incorrect marker or tool count.')
                        output.update(value=run.result.output.value, synthetic=fake,
                                      structured_repairs=len(observed_repairs),
                                      actual_models=sorted({message.model_name for message in
                                          run.all_messages() if isinstance(message, ModelResponse)
                                          and message.model_name}))
                        return dict(output)
                    finally:
                        save_history(run)
            except ProviderFailure:
                raise
            except Exception as error:  # noqa: BLE001 — normalize SDK/framework capability failures
                raise ProviderFailure('compatibility', type(error).__name__ + ': ' + str(error)
                                      ) from None
