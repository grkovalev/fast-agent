"""Prepared Findings JEV batches; no active pipeline registration or persistence.

Atomic requests retain their full state and question group. Packing scopes each
question explicitly to its item's state; question IDs are routing, not instructions.
Transport owns retries. Successful checkpoint callbacks finish before more work
is admitted on that worker. Failures carry honest partial accounting to the caller.
"""
import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from math import ceil
from time import monotonic
from typing import Literal

import httpx
from pydantic import Field, model_validator

from profitlab.providers.jev import (
    APIModel,
    JevRequest,
    JevResponse,
    LiveJevClient,
    validate_response,
)
from profitlab.providers.transport import TracedTransport

from .findings_contracts import PhaseAccounting
from .findings_policy import JevPhaseBudget

# Verified 2026-10-14: https://docs.typesafe.ai/models and /api.
# No long-context header is enabled. Unknown/custom models require new limits.
MODEL_LIMITS = {'jev-1.13.0': (64000, 32000), 'jev-1.14.0': (64000, 32000),
                'jev-latest': (64000, 32000), 'jev-preview': (64000, 32000)}


def serialized(request: JevRequest) -> str:
    return json.dumps(request.model_dump(mode='json', exclude_none=True), ensure_ascii=False,
                      sort_keys=True, separators=(',', ':'))


def admits(request: JevRequest, budget: JevPhaseBudget) -> bool:
    """Conservative application estimate, including all instructions and criteria.

    UTF-8 byte count is an upper estimate for byte-based tokenization, guarding
    multilingual inputs where a character ratio alone is optimistic. Native
    provider usage is still recorded; these are not tokenizer-exact counts.
    """
    text = serialized(request)
    if request.model not in MODEL_LIMITS:
        raise ValueError('Unverified JEV model limits; verify before dispatch')
    total, per_question = MODEL_LIMITS[request.model]
    if len(text.encode()) > 32 * 1024 * 1024 or not budget.admits(text, len(request.questions)):
        return False
    def estimate(value):
        encoded = json.dumps(value, ensure_ascii=False)
        return max(ceil(len(encoded) / budget.characters_per_token), len(encoded.encode()))
    if estimate(request.model_dump(mode='json', exclude_none=True)) + budget.token_margin > total:
        return False
    return all(estimate({'state': request.state, 'question': question.model_dump(exclude_none=True)})
               + budget.token_margin <= per_question for question in request.questions.values())


class AtomicJevItem(APIModel):
    item_id: str = Field(min_length=1)
    request: JevRequest


class BatchOmission(APIModel):
    item_id: str
    reason: Literal['atomic_request_limit', 'request_count_limit']


class PackedJevBatch(APIModel):
    batch_id: str
    request: JevRequest
    # Wire question ID -> original item and question ID. No ambiguous delimiters.
    routes: dict[str, tuple[str, str]]


class JevBatchPlan(APIModel):
    omitted_requests: int = Field(default=0, ge=0)
    batches: list[PackedJevBatch]
    omissions: list[BatchOmission]


def _batch(items: list[AtomicJevItem]) -> PackedJevBatch:
    states, questions, routes = {}, {}, {}
    for index, item in enumerate(items):
        slot = f'item_{index}'
        states[slot] = item.request.state
        for question_index, (key, question) in enumerate(item.request.questions.items()):
            wire_id = f'{slot}_q{question_index}'
            questions[wire_id] = question.model_copy(update={'instructions': {
                'scope': f'Use only `state.items.{slot}` as the state for `question` below. '
                         'All state references within that question refer to this item.',
                'question': question.instructions,
            }})
            routes[wire_id] = (item.item_id, key)
    request = JevRequest(model=items[0].request.model, state={'items': states}, questions=questions)
    identity = hashlib.sha256(serialized(request).encode()).hexdigest()
    return PackedJevBatch(batch_id=identity, request=request, routes=routes)


def pack_jev_items(items: list[AtomicJevItem], budget: JevPhaseBudget,
                   max_requests: int) -> JevBatchPlan:
    if max_requests < 1:
        raise ValueError('Request cap must be positive')
    if len({x.item_id for x in items}) != len(items):
        raise ValueError('Atomic item IDs must be unique')
    batches, omissions, pending = [], [], []
    for item in items:
        single = _batch([item])
        if not admits(single.request, budget):
            omissions.append(BatchOmission(item_id=item.item_id, reason='atomic_request_limit'))
            continue
        if pending and (item.request.model != pending[0].request.model or
                        not admits(_batch([*pending, item]).request, budget)):
            batches.append(_batch(pending))
            pending = []
        pending.append(item)
    if pending:
        batches.append(_batch(pending))
    for batch in batches[max_requests:]:
        for item_id in dict.fromkeys(route[0] for route in batch.routes.values()):
            omissions.append(BatchOmission(item_id=item_id, reason='request_count_limit'))
    return JevBatchPlan(batches=batches[:max_requests], omissions=omissions,
        omitted_requests=max(0, len(batches) - max_requests) +
        sum(x.reason == 'atomic_request_limit' for x in omissions))


class CompletedJevBatch(APIModel):
    plan_index: int = Field(default=0, ge=0)
    batch: PackedJevBatch
    response: JevResponse
    cached: bool = False
    elapsed_seconds: float = Field(ge=0)


class JevBatchExecution(APIModel):
    status: Literal['completed', 'partial', 'failed', 'cancelled', 'interrupted']
    accounting: PhaseAccounting
    completed: list[CompletedJevBatch] = Field(default_factory=list)
    omissions: list[BatchOmission] = Field(default_factory=list)
    error: str | None = None

    omitted_items: int = Field(default=0, ge=0)

    @model_validator(mode='after')
    def omission_count(self):
        if self.omitted_items != len(self.omissions):
            raise ValueError('Atomic omission count must match ledger')
        return self


class JevBatchFailure(Exception):
    def __init__(self, result: JevBatchExecution):
        self.result = result
        super().__init__(result.error)


class JevBatchCancelled(asyncio.CancelledError):
    def __init__(self, result: JevBatchExecution):
        self.result = result
        super().__init__('JEV batching cancelled')


async def execute_jev_batches(plan: JevBatchPlan, client, *, concurrency: int,
                              deadline_seconds: float,
                              checkpoint: Callable[[CompletedJevBatch], Awaitable[None]],
                              cached: dict[str, JevResponse] | None = None) -> JevBatchExecution:
    """Execute using one supplied shared client and no extra retry owner.

    Cache keys below bind exact wire request only. The persistence caller must
    first verify full source/policy/question/model identity (T69 BatchIdentity).
    Routes are always taken from the current plan, never from an old run.
    Request accounting counts packed requests plus omitted request groups
    (each oversized atomic item is one group). `omitted_items` and the ledger
    separately count atomic items, which may share a request-count omission. Unstarted/cancelled requests remain planned/dispatched
    without falsely counting them completed or failed.
    """
    if concurrency < 1 or deadline_seconds <= 0:
        raise ValueError('Concurrency and deadline must be positive')
    start = monotonic()
    counts = PhaseAccounting(planned=len(plan.batches) + plan.omitted_requests,
                             omitted=plan.omitted_requests).model_dump()
    result = JevBatchExecution(status='completed', accounting=PhaseAccounting(**counts), omissions=plan.omissions,
                               omitted_items=len(plan.omissions))
    iterator = iter(enumerate(plan.batches))
    async def worker():
        for index, batch in iterator:
            began = monotonic()
            response = (cached or {}).get(batch.batch_id)
            hit = response is not None
            if not hit:
                counts['dispatched'] += 1
                try:
                    response = await client.evaluate(batch.request)
                    validate_response(batch.request, response)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    counts['failed'] += 1
                    raise
                counts['completed'] += 1
            else:
                validate_response(batch.request, response)
                counts['cached'] += 1
            completed = CompletedJevBatch(plan_index=index, batch=batch, response=response, cached=hit,
                                          elapsed_seconds=monotonic() - began)
            result.completed.append(completed)
            if response.model not in counts['models']:
                counts['models'].append(response.model)
            if not hit:
                usage = counts['usage'] or {'input_tokens': 0, 'output_tokens': 0}
                counts['usage'] = {'input_tokens': usage['input_tokens'] + response.usage.input_tokens,
                                   'output_tokens': usage['output_tokens'] + response.usage.output_tokens}
            await checkpoint(completed)

    tasks = []
    try:
        async with asyncio.timeout(deadline_seconds):
            tasks = [asyncio.create_task(worker()) for _ in range(min(concurrency, len(plan.batches)))]
            await asyncio.gather(*tasks)
    except BaseException as error:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        result.accounting = PhaseAccounting(**{**counts, 'elapsed_seconds': monotonic() - start})
        result.completed.sort(key=lambda x: x.plan_index)
        result.status = ('cancelled' if isinstance(error, asyncio.CancelledError) else
                         'interrupted' if isinstance(error, TimeoutError) else 'failed')
        # Avoid retaining provider/error payloads that may contain sensitive text.
        result.error = type(error).__name__
        if isinstance(error, asyncio.CancelledError):
            raise JevBatchCancelled(result) from None
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        raise JevBatchFailure(result) from None
    result.accounting = PhaseAccounting(**{**counts, 'elapsed_seconds': monotonic() - start})
    result.status = 'partial' if plan.omissions else 'completed'
    result.completed.sort(key=lambda x: x.plan_index)
    return result


async def run_live_jev_batches(plan: JevBatchPlan, settings, recorder, *,
                                deadline_seconds: float, checkpoint, cached=None):
    """One pooled HTTP client, existing redaction/tracing and transport retries."""
    async with httpx.AsyncClient(
        transport=TracedTransport(recorder, settings, 'jev', stage='findings'),
        timeout=settings.provider_timeout,
    ) as http_client:
        client = LiveJevClient(settings, recorder, stage='findings', http_client=http_client)
        return await execute_jev_batches(plan, client, concurrency=settings.v2_provider_concurrency,
            deadline_seconds=deadline_seconds, checkpoint=checkpoint, cached=cached)
