"""Prepared source-line assignments. Unregistered until the T76 runtime switch."""
import asyncio
import hashlib
import json

from pydantic import Field

from .canonical import CanonicalDocument
from .contracts import V2Contract
from .findings_batching import (
    AtomicJevItem,
    JevBatchCancelled,
    JevBatchExecution,
    JevBatchFailure,
    JevBatchPlan,
    PackedJevBatch,
    execute_jev_batches,
    pack_jev_items,
    run_live_jev_batches,
    serialized,
)
from .findings_builders import build_assignment_request
from .findings_contracts import (
    ConceptLineAssignment,
    FindingLineCandidate,
    FindingsFilingMetadata,
    FindingsInputIdentity,
    FindingsPhase,
    FindingsStepResult,
    JudgmentProvenance,
    Omission,
)
from .findings_policy import FindingsPolicy
from .findings_storage import reusable_request


class FindingsAssignmentPlan(V2Contract):
    request_allowance: int = Field(ge=1)
    filing: FindingsFilingMetadata
    candidates: list[FindingLineCandidate] = Field(max_length=10000)
    identity: FindingsInputIdentity
    batches: JevBatchPlan


class FindingsAssignmentsResult(V2Contract):
    assignments: list[ConceptLineAssignment] = Field(max_length=10000)
    step: FindingsStepResult
    execution: JevBatchExecution


class FindingsAssignmentFailure(Exception):
    def __init__(self, result: FindingsAssignmentsResult):
        self.result = result
        super().__init__(result.step.reason)


class FindingsAssignmentCancelled(asyncio.CancelledError):
    def __init__(self, result: FindingsAssignmentsResult):
        self.result = result
        super().__init__('Findings line assignment cancelled')


def _input_hash(items: list[AtomicJevItem]) -> str:
    # Include omitted atomic inputs; strip only documented run-local routing fields.
    inputs = [reusable_request(PackedJevBatch(batch_id='identity', request=x.request, routes={}))
              for x in items]
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def build_assignment_plan(document: CanonicalDocument, filing: FindingsFilingMetadata,
                          candidates: list[FindingLineCandidate], *, model: str,
                          policy: FindingsPolicy,
                          max_requests: int | None = None) -> FindingsAssignmentPlan:
    """Validate exact source before dispatch; minimal state contains no chunk/outline."""
    if model not in ('jev-1.13.0', 'jev-1.14.0'):
        raise ValueError('Assignment requires a pinned verified actual JEV model')
    if filing.filing_id != document.ref.filing_id:
        raise ValueError('Filing metadata does not belong to canonical document')
    if len(candidates) > policy.max_candidate_lines:
        raise ValueError('Enumerate candidates under the configured policy before assignment')
    if len({x.candidate_id for x in candidates}) != len(candidates):
        raise ValueError('Assignment candidate IDs must be unique')
    ordered = sorted(candidates, key=lambda x: (
        x.concept.value, -next(o.concept_score for o in x.owners
                              if o.chunk.chunk_id == x.owning_chunk_id),
        x.source_range.start_line, x.candidate_id))
    items = []
    for candidate in ordered:
        if document.slice(candidate.source_range) != candidate.exact_text:
            raise ValueError('Assignment source text must equal canonical line')
        items.append(AtomicJevItem(item_id=candidate.candidate_id,
            request=build_assignment_request(filing, candidate, model, policy, enforce_budget=False)))
    cap = policy.max_jev_requests if max_requests is None else max_requests
    if not 1 <= cap <= policy.max_jev_requests:
        raise ValueError('Assignment request allowance must fit Findings policy')
    batches = pack_jev_items(items, policy.assign_budget, cap)
    identity = FindingsInputIdentity(canonical_source_hashes=[document.ref.source_hash],
        exact_inputs_hash=_input_hash(items), phase=FindingsPhase.ASSIGN, policy_hash=policy.identity(),
        question_version=policy.question_version, model_identity=model)
    return FindingsAssignmentPlan(request_allowance=cap, filing=filing, candidates=ordered,
                                  identity=identity, batches=batches)


def assignment_result(plan: FindingsAssignmentPlan, execution: JevBatchExecution,
                      policy: FindingsPolicy) -> FindingsAssignmentsResult:
    """Prepared inspector projection uses the exact dispatched requests and answers."""
    if plan.identity.policy_hash != policy.identity():
        raise ValueError('Assignment policy differs from executed plan')
    by_id = {x.candidate_id: x for x in plan.candidates}
    answers = {}
    for completed in execution.completed:
        for question_id, (candidate_id, original_id) in completed.batch.routes.items():
            candidate = by_id[candidate_id]
            answer = completed.response.answers[question_id]
            decision = policy.source_decision(answer.noul)
            answers[candidate_id] = ConceptLineAssignment(candidate_id=candidate_id,
                concept=candidate.concept, source_range=candidate.source_range, answer=answer,
                decision=decision,
                reason=f'{decision.value}: Noul {answer.noul:g}; support >= '
                       f'{policy.source_support_threshold:g}, uncertain >= '
                       f'{policy.source_uncertain_threshold:g}; independent concept membership',
                provenance=JudgmentProvenance(model=completed.response.model,
                    call_id=completed.batch.batch_id, question_id=question_id,
                    question_version=policy.question_version, policy_hash=policy.identity(),
                    request_hash=hashlib.sha256(serialized(completed.batch.request).encode()).hexdigest(),
                    cached=completed.cached))
            if original_id != 'source_support':
                raise ValueError('Unexpected assignment question route')
    assignments = [answers[x.candidate_id] for x in plan.candidates if x.candidate_id in answers]
    omissions = [Omission(item_id=x.item_id, reason=x.reason, coverage_cut=True,
        kind='size_limit' if x.reason == 'atomic_request_limit' else 'count_limit')
        for x in execution.omissions]
    successful = execution.status in ('completed', 'partial')
    step = FindingsStepResult(phase=FindingsPhase.ASSIGN, status=execution.status,
        availability='final' if successful else 'checkpointed' if assignments else 'unavailable',
        input_hash=plan.identity.exact_inputs_hash, policy_hash=policy.identity(),
        accounting=execution.accounting, output_ids=[x.candidate_id for x in assignments],
        omissions=omissions, reason=execution.error or
        'Independent source membership only; no numeric span, year or amount selected')
    return FindingsAssignmentsResult(assignments=assignments, step=step, execution=execution)


class FindingsLineAssignmentService:
    def __init__(self, repository, policy: FindingsPolicy):
        self.repository = repository
        self.policy = policy

    async def assign(self, run_id: str, plan: FindingsAssignmentPlan, *, client=None,
                     settings=None, recorder=None, concurrency: int = 1,
                     deadline_seconds: float | None = None) -> FindingsAssignmentsResult:
        if plan.identity.policy_hash != self.policy.identity():
            raise ValueError('Assignment policy differs from plan')
        items = [AtomicJevItem(item_id=x.candidate_id, request=build_assignment_request(
            plan.filing, x, plan.identity.model_identity, self.policy, enforce_budget=False))
            for x in plan.candidates]
        source_hashes = sorted({x.source_range.source_hash for x in plan.candidates})
        if (plan.identity.model_identity not in ('jev-1.13.0', 'jev-1.14.0') or
                plan.identity.concept is not None or
                len(plan.candidates) > self.policy.max_candidate_lines or
                plan.identity.phase != FindingsPhase.ASSIGN or
                plan.identity.question_version != self.policy.question_version or
                plan.identity.exact_inputs_hash != _input_hash(items) or
                (bool(plan.candidates) and plan.identity.canonical_source_hashes != source_hashes) or
                plan.request_allowance > self.policy.max_jev_requests or
                plan.batches != pack_jev_items(items, self.policy.assign_budget, plan.request_allowance)):
            raise ValueError('Assignment plan differs from exact inputs/policy')
        self.repository.get_run(run_id)
        cached = {}
        for batch in plan.batches.batches:
            saved = self.repository.findings_checkpoint(plan.identity, batch)
            if saved:
                cached[batch.batch_id] = saved.response
        async def checkpoint(completed):
            self.repository.save_findings_checkpoint(run_id, plan.identity, completed)
        deadline = min(deadline_seconds if deadline_seconds is not None else
                       self.policy.total_deadline_seconds, self.policy.total_deadline_seconds)
        try:
            if client is None:
                if settings is None or recorder is None:
                    raise ValueError('Live assignment needs configured settings and recorder')
                execution = await run_live_jev_batches(plan.batches, settings, recorder,
                    deadline_seconds=deadline, checkpoint=checkpoint, cached=cached)
            else:
                execution = await execute_jev_batches(plan.batches, client, concurrency=concurrency,
                    deadline_seconds=deadline, checkpoint=checkpoint, cached=cached)
        except (JevBatchFailure, JevBatchCancelled) as error:
            result = assignment_result(plan, error.result, self.policy)
            if isinstance(error, JevBatchCancelled):
                raise FindingsAssignmentCancelled(result) from None
            raise FindingsAssignmentFailure(result) from None
        result = assignment_result(plan, execution, self.policy)
        self.repository.complete_findings_step(run_id, result.step, result.assignments)
        return result
