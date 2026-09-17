"""TypeSafe /v1/systemone Noul contract, verified against docs.typesafe.ai/api.

Only the Noul primitive needed for screening is supported by this slice.
"""
from typing import Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from profitlab.contracts.base import Probability
from profitlab.providers.transport import ProviderFailure, TracedTransport


class APIModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class NoulQuestion(APIModel):
    type: Literal['noul'] = 'noul'
    instructions: str = Field(min_length=1)
    criteria: dict[Literal['true', 'false'], str] | None = None


class JevRequest(APIModel):
    state: str | dict[str, JsonValue] | list[JsonValue]
    model: str = Field(min_length=1)
    questions: dict[str, NoulQuestion] = Field(min_length=1)


class NoulAnswer(APIModel):
    type: Literal['noul']
    noul: Probability


class TokenUsage(APIModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class JevResponse(APIModel):
    model: str = Field(min_length=1)
    answers: dict[str, NoulAnswer]
    usage: TokenUsage


class JevClient(Protocol):
    async def evaluate(self, request: JevRequest) -> JevResponse: ...


class LiveJevClient:
    def __init__(self, settings, recorder, transport=None, stage='probe'):
        if not settings.typesafe_api_key.get_secret_value():
            raise ProviderFailure('configuration', 'TYPESAFE_API_KEY is missing.')
        self.settings, self.recorder, self.transport = settings, recorder, transport
        self.stage = stage

    async def evaluate(self, request):
        with self.recorder.operation('jev.evaluate', request.model_dump(exclude_none=True),
                                     provider='jev', stage=self.stage) as output:
            async with httpx.AsyncClient(
                transport=TracedTransport(self.recorder, self.settings, 'jev', self.transport, stage=self.stage),
                timeout=self.settings.provider_timeout,
            ) as client:
                response = await client.post(
                    self.settings.typesafe_base_url.rstrip('/') + '/v1/systemone',
                    headers={'Authorization': 'Bearer ' +
                             self.settings.typesafe_api_key.get_secret_value()},
                    json=request.model_dump(exclude_none=True))
            try:
                result = JevResponse.model_validate_json(response.content)
                if set(result.answers) != set(request.questions):
                    raise ValueError('Answer IDs must exactly match question IDs.')
            except ValueError as error:
                raise ProviderFailure('response_validation', str(error)) from None
            output.update(result.model_dump())
            return result


class FakeJevClient:
    """Fixture judgments, not an inference or benchmark."""
    def __init__(self, recorder):
        self.recorder = recorder

    async def evaluate(self, request):
        with self.recorder.operation('jev.evaluate.fixture', request.model_dump(exclude_none=True),
                                     provider='fake-jev', stage='probe') as output:
            result = JevResponse(model='fixture-jev-1', answers={
                key: NoulAnswer(type='noul', noul=0.99) for key in request.questions
            }, usage=TokenUsage(input_tokens=0, output_tokens=0))
            output.update(result.model_dump(), synthetic=True, usage_note='No provider tokens used.')
            return result
