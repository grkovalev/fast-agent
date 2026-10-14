"""TypeSafe /v1/systemone typed contract, verified against docs.typesafe.ai/api."""
from math import isclose
from typing import Annotated, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from profitlab.providers.transport import ProviderFailure, TracedTransport

Probability = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class APIModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


StructuredText = str | dict[str, JsonValue] | list[JsonValue]


class NoulQuestion(APIModel):
    type: Literal['noul'] = 'noul'
    instructions: StructuredText = Field(min_length=1)
    criteria: dict[Literal['true', 'false'], StructuredText] | None = None


class ScoreQuestion(APIModel):
    type: Literal['score'] = 'score'
    instructions: StructuredText = Field(min_length=1)
    criteria: list[StructuredText] = Field(min_length=2, max_length=10)


Question = Annotated[NoulQuestion | ScoreQuestion, Field(discriminator='type')]


class JevRequest(APIModel):
    state: str | dict[str, JsonValue] | list[JsonValue]
    model: str = Field(min_length=1)
    questions: dict[str, Question] = Field(min_length=1)


class NoulAnswer(APIModel):
    type: Literal['noul']
    noul: Probability


class ScoreAnswer(APIModel):
    type: Literal['score']
    score: float = Field(ge=0, le=9)
    legend: dict[str, str] = Field(min_length=2, max_length=10)
    probabilities: dict[str, Probability]
    confidence: Probability

    @model_validator(mode='after')
    def distribution(self):
        levels = {str(i) for i in range(len(self.legend))}
        if set(self.legend) != levels or set(self.probabilities) != levels:
            raise ValueError('Score legend and probabilities must contain consecutive levels from zero.')
        # Live API rounds score and probabilities independently to two decimals.
        # Permit only the accumulated rounding envelope, not arbitrary mismatch.
        rounding = .005
        if not isclose(sum(self.probabilities.values()), 1,
                       abs_tol=rounding * len(levels) + 1e-9):
            raise ValueError('Score probabilities must sum to one.')
        expected = sum(int(k) * v for k, v in self.probabilities.items())
        if self.score > len(levels) - 1 or not isclose(
            self.score, expected,
            abs_tol=rounding * (1 + sum(range(len(levels)))) + 1e-9,
        ):
            raise ValueError('Score must equal its probability-weighted levels.')
        return self


Answer = Annotated[NoulAnswer | ScoreAnswer, Field(discriminator='type')]


class TokenUsage(APIModel):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)


class JevResponse(APIModel):
    model: str = Field(min_length=1)
    answers: dict[str, Answer]
    usage: TokenUsage


def validate_response(request: JevRequest, result: JevResponse) -> JevResponse:
    """Bind IDs, primitive and rubric to the exact dispatched request."""
    if set(result.answers) != set(request.questions):
        raise ValueError('Answer IDs must exactly match question IDs.')
    for key, question in request.questions.items():
        answer = result.answers[key]
        if answer.type != question.type:
            raise ValueError('Answer type must match question type.')
        if isinstance(question, ScoreQuestion):
            if len(answer.legend) != len(question.criteria):
                raise ValueError('Score levels must match requested rubric.')
            for i, criterion in enumerate(question.criteria):
                if isinstance(criterion, str) and answer.legend[str(i)] != criterion:
                    raise ValueError('Score legend must match requested rubric.')
    return result


class JevClient(Protocol):
    async def evaluate(self, request: JevRequest) -> JevResponse: ...


class LiveJevClient:
    def __init__(self, settings, recorder, transport=None, stage='probe', http_client=None):
        if not settings.typesafe_api_key.get_secret_value():
            raise ProviderFailure('configuration', 'TYPESAFE_API_KEY is missing.')
        self.settings, self.recorder, self.transport, self.http_client = settings, recorder, transport, http_client
        self.stage = stage

    async def evaluate(self, request):
        with self.recorder.operation('jev.evaluate', request.model_dump(exclude_none=True),
                                     provider='jev', stage=self.stage) as output:
            if self.http_client is not None:
                response = await self.http_client.post(
                    self.settings.typesafe_base_url.rstrip('/') + '/v1/systemone',
                    headers={'Authorization': 'Bearer ' + self.settings.typesafe_api_key.get_secret_value()},
                    json=request.model_dump(exclude_none=True))
            else:
                async with httpx.AsyncClient(
                    transport=TracedTransport(self.recorder, self.settings, 'jev', self.transport, stage=self.stage),
                    timeout=self.settings.provider_timeout,
                ) as client:
                    response = await client.post(
                        self.settings.typesafe_base_url.rstrip('/') + '/v1/systemone',
                        headers={'Authorization': 'Bearer ' + self.settings.typesafe_api_key.get_secret_value()},
                        json=request.model_dump(exclude_none=True))
            try:
                result = JevResponse.model_validate_json(response.content)
                validate_response(request, result)
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
