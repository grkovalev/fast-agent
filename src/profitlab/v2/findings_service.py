"""JEV-led evidence assembly followed by selected-bundle conversion and atomic seal."""
import asyncio
from datetime import date
from time import monotonic

from .finding_concepts import FindingConcept
from .findings_candidates import enumerate_candidates
from .findings_context import FindingsContextService, build_context_plan
from .findings_contracts import (
    FindingsFilingMetadata,
    FindingsPhase,
    FindingsRunSummary,
    FindingsStepResult,
)
from .findings_conversion import FindingsConversionService
from .findings_lines import FindingsLineAssignmentService, build_assignment_plan
from .findings_policy import build_findings_policy
from .findings_ranking import FindingsRankingService, build_ranking_plan
from .section_scoring import _V2Trace


class FindingsService:
    FINDING_TYPES = tuple(x.value for x in FindingConcept)

    def __init__(self, settings, repository):
        self.settings, self.repo = settings, repository
        self.policy = build_findings_policy(settings)

    @staticmethod
    def inspection_view(settings, *, summary=None, finding_count=0):
        from .findings_inspection import findings_inspection
        return findings_inspection(settings, summary, finding_count)

    async def build(self, run_id, document, chunks, scores):
        """Each phase checkpoints before publication; cancellation never seals a subset."""
        policy = self.policy
        start = monotonic()
        steps = []
        conversion = None
        phase = FindingsPhase.CANDIDATES
        recorder = _V2Trace(self.repo, run_id, self.settings.redactor(), 'findings')
        filing = FindingsFilingMetadata(ticker=self.repo.get_run(run_id).ticker,
            filing_id=document.ref.filing_id,
            report_date=date.fromisoformat(self.repo.filing(run_id)['report_date']))

        def summary(status='running', **updates):
            by_phase = {step.phase: step.accounting for step in steps}
            values = {'status': status, 'policy_hash': policy.identity(), 'steps': steps,
                'jev_assign': by_phase.get(FindingsPhase.ASSIGN, {}),
                'jev_attach': by_phase.get(FindingsPhase.ATTACH, {}),
                'jev_rank': by_phase.get(FindingsPhase.RANK, {})}
            if conversion:
                values.update(llm_conversion=conversion.conversion, llm_repair=conversion.repair,
                    rejection_count=sum(d.state == 'rejected' for d in conversion.diagnostics))
            return FindingsRunSummary(**(values | updates))

        def checkpoint(step):
            steps.append(step)
            self.repo.save_findings_run_result(run_id, summary())
            snapshot = self.repo.stage(run_id, 'findings').model_copy(update={
                'completed_work': len(steps), 'total_work': 7,
                'summary': f'{step.phase.value.replace("_", " ").title()}: {step.status}. {step.reason or ""}'})
            self.repo.update_stage(snapshot, event_kind='stage_started', event_summary=snapshot.summary)

        def remaining():
            seconds = policy.total_deadline_seconds - (monotonic() - start)
            if seconds <= 0:
                raise TimeoutError('Total Findings deadline exhausted')
            if self.repo.cancellation_requested(run_id):
                raise asyncio.CancelledError('Findings cancelled')
            return seconds

        async def execute(work):
            remaining()
            self.repo.save_findings_progress(run_id, FindingsStepResult(phase=phase, status='running',
                availability='checkpointed', input_hash=document.ref.source_hash, policy_hash=policy.identity(),
                reason='Current attempt running; successful batches are saved as they finish.'))
            task = asyncio.create_task(work())
            expired = False
            try:
                while not task.done():
                    await asyncio.wait({task}, timeout=.1)
                    if self.repo.cancellation_requested(run_id):
                        task.cancel()
                    if monotonic() - start >= policy.total_deadline_seconds:
                        expired = True
                        task.cancel()
                try:
                    return await task
                except asyncio.CancelledError as error:
                    if expired:
                        failure = TimeoutError('Total Findings deadline exhausted')
                        if hasattr(error, 'result'):
                            failure.result = error.result
                        raise failure from None
                    raise
            finally:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        try:
            self.repo.start_findings_attempt(run_id, summary())
            remaining()
            candidates = enumerate_candidates(document, chunks, scores,
                relevance_threshold=self.settings.chunk_score_uncertain_threshold, policy=policy)
            self.repo.complete_findings_step(run_id, candidates.step, [*candidates.concepts, *candidates.lines])
            checkpoint(candidates.step)
            phase = FindingsPhase.ASSIGN
            assignment_plan = build_assignment_plan(document, filing, candidates.lines,
                model=self.settings.typesafe_model, policy=policy)
            assignment = await execute(lambda: FindingsLineAssignmentService(self.repo, policy).assign(
                run_id, assignment_plan, settings=self.settings, recorder=recorder, deadline_seconds=remaining()))
            checkpoint(assignment.step)
            allowance = policy.max_jev_requests - assignment.step.accounting.dispatched
            phase = FindingsPhase.ATTACH
            context_plan = build_context_plan(document, filing, candidates.concepts, candidates.lines,
                assignment.assignments, chunks, scores, self.repo.outline_sections(run_id),
                model=self.settings.typesafe_model, policy=policy, max_requests=allowance)
            context = await execute(lambda: FindingsContextService(self.repo, policy).attach(run_id, context_plan,
                settings=self.settings, recorder=recorder, deadline_seconds=remaining()))
            checkpoint(context.step)
            allowance -= context.step.accounting.dispatched
            phase = FindingsPhase.RANK
            rank_plan = build_ranking_plan(document, filing, context.bundles,
                model=self.settings.typesafe_model, policy=policy, max_requests=allowance)
            ranking = await execute(lambda: FindingsRankingService(self.repo, policy).rank(run_id, rank_plan, document,
                settings=self.settings, recorder=recorder, deadline_seconds=remaining()))
            checkpoint(ranking.step)
            phase = FindingsPhase.CONVERT
            conversion = await execute(lambda: FindingsConversionService(self.repo, policy).convert(run_id,
                ranking.conversion_packs, context.bundles, ranking.ranks, document,
                model=self.settings.llm_model, base_url=self.settings.llm_base_url,
                output_mode=self.settings.llm_output_mode, settings=self.settings, recorder=recorder,
                deadline_seconds=remaining()))
            checkpoint(conversion.step)
            phase = FindingsPhase.VALIDATE
            validation = FindingsStepResult(phase=phase, status='completed', availability='final',
                input_hash=conversion.step.input_hash, policy_hash=policy.identity(),
                output_ids=[p.finding.finding_id for p in conversion.publications],
                reason='Exact selected source/span/sign/Decimal and metadata references checked; accepted findings bypass repair.')
            # Validate, Seal, published rows and summary commit in one transaction below.
            steps.append(validation)
            phase = FindingsPhase.SEAL
            remaining()
            status = 'partial' if any(s.status == 'partial' for s in steps) else 'completed'
            steps.append(FindingsStepResult(phase=phase, status=status, availability='final',
                input_hash=conversion.step.input_hash, policy_hash=policy.identity(),
                output_ids=validation.output_ids, reason='Atomic publication after all seven terminal phases.'))
            result = summary(status, sealed=True, published_finding_ids=validation.output_ids,
                limitation='Bounded search cut coverage; inspect phase omissions.' if status == 'partial' else None)
            return self.repo.seal_findings(run_id, result, conversion.publications)
        except BaseException as error:
            if not isinstance(error, (Exception, asyncio.CancelledError)):
                raise
            result = getattr(error, 'result', None)
            if result is not None:
                if phase == FindingsPhase.CONVERT:
                    conversion = result
                step = result.step
            else:
                status = ('cancelled' if isinstance(error, asyncio.CancelledError) else 'failed')
                step = FindingsStepResult(phase=phase, status=status, availability='checkpointed',
                    input_hash=document.ref.source_hash, policy_hash=policy.identity(),
                    reason=self.settings.redactor().text(str(error)) or status)
            if monotonic() - start >= policy.total_deadline_seconds:
                step = step.model_copy(update={'status': 'failed', 'reason': 'Total Findings deadline exhausted'})
            steps[:] = [s for s in steps if s.phase != phase]
            steps.append(step)
            self.repo.save_findings_progress(run_id, step)
            self.repo.save_findings_terminal(run_id, summary(step.status, limitation=step.reason))
            raise
