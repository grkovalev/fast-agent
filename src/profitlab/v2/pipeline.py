"""Functional T14 shell around the eight ordered V2 stages."""
import asyncio
import hashlib
import json
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from profitlab.sec.service import normalize_ticker

from .benchmark import RetrievalBenchmarkService
from .chunk_scoring import ChunkScoringService
from .chunking import SourceRangeChunker
from .contracts import STAGE_NAMES, V2Run
from .evaluation_service import EvaluationService
from .facts_service import CompanyFactsService
from .findings_service import FindingsService
from .outline_service import OutlineService
from .section_scoring import SectionScoringService
from .source_context import SourceContextService
from .source_service import V2SourceService
from .storage import V2Repository


class V2PipelineService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = V2Repository(settings.data_dir)

    def create(self, ticker, run_id=None):
        ticker = normalize_ticker(ticker)
        if not self.settings.sec_contact_ready():
            raise ValueError('SEC_USER_AGENT is required and must include a real contact email before creating a run.')
        now = datetime.now(UTC)
        components = self._version_components()
        version_id = 'v2-' + hashlib.sha256(
            json.dumps(components, sort_keys=True, separators=(',', ':')).encode()).hexdigest()[:16]
        run = V2Run(run_id=run_id or 'v2-' + uuid4().hex[:12], ticker=ticker,
                    created_at=now, updated_at=now,
                    version_id=version_id, version_components=components,
                    version_state=('unknown' if components['application_revision'] == 'unknown'
                                   else 'comparable'),
                    timing_origin_monotonic=monotonic(),
                    summary='Eight-stage V2 pipeline is queued.')
        self.repo.create_run(run)
        return run

    def _version_components(self):
        """Only behavior-affecting, non-secret configuration belongs in a cohort ID."""
        names = (
            'application_revision', 'outline_model', 'outline_prompt_version',
            'section_score_prompt_version', 'chunk_score_prompt_version',
            'source_context_prompt_version', 'source_context_max_blocks',
            'source_context_max_requests', 'source_context_batch_size',
            'source_context_rings', 'source_context_request_char_budget',
            'source_context_role_threshold', 'source_context_role_margin',
            'source_context_eligibility_threshold',
            'findings_prompt_version', 'finding_type_prompt_version',
            'findings_packet_version', 'findings_packet_max_cores',
            'findings_packet_context_lines', 'findings_packet_uncertainty_reserve',
            'findings_request_char_budget',
            'evaluation_scale_prompt_version', 'typesafe_model', 'llm_model',
            'llm_output_mode', 'section_score_keep_threshold',
            'section_score_uncertain_threshold', 'section_score_max_selected',
            'section_score_max_uncertain', 'source_reserve_pattern_version', 'source_reserve_max_sections',
            'chunk_score_keep_threshold',
            'chunk_score_uncertain_threshold', 'chunk_score_max_retained',
            'chunk_score_uncertain_section_reserve', 'chunk_score_source_reserve',
            'findings_max_requests', 'evaluation_scale_max_pairs',
        )
        return {name: str(getattr(self.settings, name)) for name in names}

    async def run(self, run_id: str, delay: float = 0, *, implement_source: bool = False):
        run_started = monotonic()
        run = self.repo.get_run(run_id)
        if run.status == 'running':
            raise ValueError('V2 run is already active.')
        if run.cancellation_requested:
            raise ValueError('V2 run was cancelled; resume it before running.')
        self.repo.update_run(run_id, status='running', summary='V2 shell is advancing.',
                             kind='stage_started')
        for name in STAGE_NAMES:
            if self.repo.cancellation_requested(run_id):
                return self._cancel(run_id, name)
            old = self.repo.stage(run_id, name)
            if old.status == 'completed':
                continue
            started_at = datetime.now(UTC)
            tick = monotonic()
            running = old.model_copy(update={
                'status': 'running', 'started_at': started_at,
                'active_started_monotonic': tick,
                'summary': f'{name.replace("_", " ").title()} shell started.',
            })
            self.repo.update_stage(running, event_kind='stage_started',
                                   event_summary=running.summary)
            if delay:
                await asyncio.sleep(delay)
            if self.repo.cancellation_requested(run_id):
                return self._cancel(run_id, name, running)
            if name == 'source' and implement_source:
                try:
                    document, filing = await asyncio.to_thread(
                        V2SourceService(self.settings, self.repo).acquire, run)
                except ValueError as error:
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Visible filing source could not be prepared.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                self.repo.update_stage(running.model_copy(update={
                    'completed_work': 1, 'total_work': 1,
                    'summary': f"Canonicalized {document.ref.line_count} visible lines.",
                }), event_kind='stage_started', event_summary='Canonical visible source persisted.')
                finished = self.repo.stage(run_id, name).model_copy(update={
                    'status': 'completed', 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick,
                    'summary': (f"{filing['form']} {filing['report_date']}: "
                                f"{document.ref.line_count} visible lines."),
                    'limitation': None, 'output_hash': document.ref.source_hash,
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            if name == 'outline' and implement_source:
                try:
                    document = self.repo.canonical_refs(run_id)[0]
                    canonical = self.repo.canonical_document(run_id, document.document_id)
                    sections, warnings, models, cached_count = await OutlineService(
                        self.settings, self.repo).build(canonical)
                    self.repo.save_outline_sections(run_id, sections)
                except Exception as error:  # noqa: BLE001 - persist provider failures before ending the run
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Source-validated outline could not be prepared.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                summary = f'Validated {len(sections)} primary outline ranges using {", ".join(models)}.'
                if cached_count:
                    summary += f' {cached_count} cached window batch(es) reused.'
                if warnings:
                    summary += f' {len(warnings)} proposal(s) rejected.'
                finished = running.model_copy(update={
                    'status': 'completed', 'completed_work': len(sections),
                    'total_work': len(sections), 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick, 'summary': summary,
                    'limitation': None,
                    'input_hash': canonical.ref.source_hash,
                    'output_hash': hashlib.sha256(''.join(item.section_id for item in sections).encode()).hexdigest(),
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            if name == 'section_score' and implement_source:
                try:
                    document_ref = self.repo.canonical_refs(run_id)[0]
                    document = self.repo.canonical_document(run_id, document_ref.document_id)
                    sections = self.repo.outline_sections(run_id)
                    def score_progress(completed, total, calls, cached=0):
                        snapshot = self.repo.stage(run_id, 'section_score').model_copy(update={
                            'completed_work': completed, 'total_work': total,
                            'summary': (f'Jev checkpointed {completed}/{total} section descriptors; '
                                        f'{calls} live batch(es), {cached} cached batch(es).'),
                        })
                        self.repo.update_stage(snapshot, event_kind='stage_started',
                                               event_summary=snapshot.summary)
                    result = await SectionScoringService(self.settings, self.repo).score(
                        run_id, document, sections,
                        on_progress=score_progress)
                except Exception as error:  # noqa: BLE001 - preserve provider failures for inspection
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Visible-only Jev section scoring could not be completed.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                selected = sum(item.policy_decision == 'selected' for item in result.scores)
                uncertain = sum(item.policy_decision == 'uncertain' for item in result.scores)
                finished = running.model_copy(update={
                    'status': 'completed', 'completed_work': len(result.scores),
                    'total_work': len(result.scores), 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick,
                    'summary': (f'Jev scored {len(result.scores)} visible outline sections in '
                                f'{result.calls} batch(es): {selected} selected, '
                                f'{uncertain} uncertain; {result.cached_batches} cached batch(es) reused.'),
                    'limitation': None,
                    'input_hash': document.ref.source_hash,
                    'output_hash': hashlib.sha256(''.join(
                        f'{item.item_id}:{item.target_scores}' for item in result.scores).encode()).hexdigest(),
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            if name == 'chunk' and implement_source:
                try:
                    document_ref = self.repo.canonical_refs(run_id)[0]
                    document = self.repo.canonical_document(run_id, document_ref.document_id)
                    sections = self.repo.outline_sections(run_id)
                    candidate_ids = {item.item_id for item in self.repo.scores(run_id, 'section_score')
                                     if item.policy_decision in {'selected', 'uncertain'}}
                    candidate_sections = [item for item in sections if item.section_id in candidate_ids]
                    chunks = SourceRangeChunker(self.settings).build(document, candidate_sections)
                    self.repo.save_chunks(run_id, chunks)
                except Exception as error:  # noqa: BLE001 - persist invariant failures before ending the run
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Selected sections could not be split into safe source-range chunks.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                core_lines = sum(item.core_range.end_line - item.core_range.start_line + 1
                                 for item in chunks)
                finished = running.model_copy(update={
                    'status': 'completed', 'completed_work': len(chunks),
                    'total_work': len(chunks), 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick,
                    'summary': (f'Built {len(chunks)} bounded chunks from {len(candidate_sections)} '
                                f'selected or bounded-uncertain sections ({core_lines} primary canonical lines).'),
                    'limitation': None,
                    'input_hash': document.ref.source_hash,
                    'output_hash': hashlib.sha256(''.join(item.chunk_id for item in chunks).encode()).hexdigest(),
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            if name == 'chunk_score' and implement_source:
                try:
                    document_ref = self.repo.canonical_refs(run_id)[0]
                    document = self.repo.canonical_document(run_id, document_ref.document_id)
                    sections = self.repo.outline_sections(run_id)
                    chunks = self.repo.chunks(run_id)
                    def score_progress(completed, total, calls, cached, usage):
                        snapshot = self.repo.stage(run_id, 'chunk_score').model_copy(update={
                            'completed_work': completed, 'total_work': total,
                            'summary': (f'Jev checkpointed {completed}/{total} detailed chunks; '
                                        f'{calls} live batch(es), {cached} cached batch(es).'),
                        })
                        self.repo.update_stage(snapshot, event_kind='stage_started',
                                               event_summary=snapshot.summary)
                    uncertain_section_ids = {item.item_id for item in self.repo.scores(
                        run_id, 'section_score') if item.policy_decision == 'uncertain'}
                    source_reserve_section_ids = {item.item_id for item in self.repo.scores(
                        run_id, 'section_score') if item.policy_reason == 'bounded target-shaped source reserve'}
                    result = await ChunkScoringService(self.settings, self.repo).score(
                        run_id, document, sections, chunks,
                        uncertain_section_ids=uncertain_section_ids,
                        source_reserve_section_ids=source_reserve_section_ids,
                        on_progress=score_progress)
                except Exception as error:  # noqa: BLE001 - preserve bounded provider failure state
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Visible-only Jev chunk scoring could not be completed.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                selected = sum(item.policy_decision == 'selected' for item in result.scores)
                uncertain = sum(item.policy_decision == 'uncertain' for item in result.scores)
                # T39 is deliberately downstream of the flat policy.  Classify
                # individual canonical lines from retained cores in stable source
                # order, but never feed its semantic result back into retention or
                # the Findings inputs.
                retained_ids = {item.item_id for item in result.scores
                                if item.policy_decision == 'selected'}
                seen_lines, context_cores = set(), []
                for chunk in sorted((item for item in chunks if item.chunk_id in retained_ids),
                                    key=lambda item: (item.core_range.start_line, item.chunk_id)):
                    for line_number in range(chunk.core_range.start_line, chunk.core_range.end_line + 1):
                        if line_number not in seen_lines:
                            seen_lines.add(line_number)
                            context_cores.append((SourceContextService._range(
                                document, line_number, line_number), chunk.section_id))
                # This is an explicit diagnostic sampling boundary, not a semantic
                # eligibility decision.
                context_cores = context_cores[:self.settings.source_context_max_blocks]
                context_result = await SourceContextService(self.settings, self.repo).classify(
                    run_id, document, context_cores)
                finished = running.model_copy(update={
                    'status': 'completed', 'completed_work': len(result.scores),
                    'total_work': len(result.scores), 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick,
                    'summary': (f'Jev scored {len(result.scores)} detailed chunks: {selected} retained, '
                                f'{uncertain} uncertain; {result.calls} live batch(es), '
                                f'{result.cached_batches} cached batch(es). '
                                f'T39 recorded {len(context_result.decisions)} source-context decision(s) '
                                f'from {len(context_cores)} retained-core line(s); '
                                f'{context_result.calls} live diagnostic call(s), '
                                f'{context_result.partial} partial.'),
                    'limitation': None,
                    'input_hash': document.ref.source_hash,
                    'output_hash': hashlib.sha256(''.join(
                        f'{item.item_id}:{item.target_scores}' for item in result.scores).encode()).hexdigest(),
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            if name == 'findings' and implement_source:
                try:
                    document_ref = self.repo.canonical_refs(run_id)[0]
                    document = self.repo.canonical_document(run_id, document_ref.document_id)
                    result = await FindingsService(self.settings, self.repo).build(
                        run_id, document, self.repo.chunks(run_id),
                        self.repo.scores(run_id, 'chunk_score'))
                except Exception as error:  # noqa: BLE001 - citation failures must be durable and inspectable
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Quote-backed visible findings could not be prepared.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                finished = running.model_copy(update={
                    'status': 'completed', 'completed_work': len(result.findings),
                    'total_work': len(result.findings), 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick,
                    'summary': (f'Published {len(result.findings)} exact quote-validated findings; '
                                f'{result.rejected} invalid citation(s) rejected.' +
                                (' Request budget fallback retained only highest-scored evidence.'
                                 if result.context_fallback else '')),
                    'limitation': None,
                    'input_hash': document.ref.source_hash,
                    'output_hash': hashlib.sha256(''.join(item.finding_id for item in result.findings).encode()).hexdigest(),
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            if name == 'facts' and implement_source:
                try:
                    facts, alternatives, source_hash = await asyncio.to_thread(
                        CompanyFactsService(self.settings, self.repo).load, self.repo.get_run(run_id))
                except Exception as error:  # noqa: BLE001 - facts failure cannot rewrite discovery output
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Independent SEC Company Facts could not be loaded.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                finished = running.model_copy(update={
                    'status': 'completed', 'completed_work': len(facts),
                    'total_work': len(facts), 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick,
                    'summary': (f'Normalized {len(facts)} independent annual SEC Company Facts; '
                                f'{sum(map(len, alternatives.values()))} duplicate alternative(s) retained.'),
                    'limitation': None,
                    'output_hash': source_hash,
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            if name == 'evaluate' and implement_source:
                try:
                    result = await EvaluationService(self.settings, self.repo).compare_with_scale_verdicts(
                        run_id)
                    RetrievalBenchmarkService(self.repo, self.settings).evaluate_automatic(run_id)
                except Exception as error:  # noqa: BLE001 - evaluation must not alter sealed inputs
                    failed = running.model_copy(update={
                        'status': 'failed', 'finished_at': datetime.now(UTC),
                        'elapsed_seconds': monotonic() - tick,
                        'summary': 'Independent finding-to-fact comparison could not be completed.',
                        'error': self.settings.redactor().text(str(error)),
                    })
                    self.repo.update_stage(failed, event_kind='stage_finished',
                                           event_summary=failed.summary)
                    self.repo.update_run(run_id, status='failed', summary=failed.summary,
                                         kind='run_finished')
                    return self.repo.get_run(run_id)
                finished = running.model_copy(update={
                    'status': 'completed', 'completed_work': len(result.comparisons),
                    'total_work': len(result.comparisons), 'finished_at': datetime.now(UTC),
                    'elapsed_seconds': monotonic() - tick,
                    'summary': (f"Compared {result.summary['expected_facts']} independent expected fact(s): "
                                f"{result.summary['exact_matches']} exact match(es), "
                                f"{result.summary['misses']} miss(es), "
                                f"{result.summary.get('scale_aware_equivalences', 0)} scale-aware equivalent(s)."),
                    'limitation': None,
                    'output_hash': hashlib.sha256(''.join(item.comparison_id for item in result.comparisons).encode()).hexdigest(),
                })
                self.repo.update_stage(finished, event_kind='stage_finished',
                                       event_summary=finished.summary)
                continue
            limitation = 'Stage implementation begins in a later task; no domain output was fabricated.'
            finished = running.model_copy(update={
                'status': 'partial', 'completed_work': 0, 'total_work': 0,
                'finished_at': datetime.now(UTC), 'elapsed_seconds': monotonic() - tick,
                'summary': f'{name.replace("_", " ").title()} shell reached.',
                'limitation': limitation,
            })
            self.repo.update_stage(finished, event_kind='stage_finished',
                                   event_summary=finished.summary)
        summary = ('V2 source, outline, section scoring, source-range chunking, detailed chunk scoring, quote-backed findings, independent Company Facts, and independent evaluation are complete.'
                   if implement_source else
                   'V2 shell completed; all domain stages are explicitly unimplemented.')
        self.repo.update_run(run_id, status='partial', summary=summary, kind='run_finished')
        chunk = self.repo.chunk_score_summary(run_id) or {}
        findings = self.repo.finding_summary(run_id) or {}
        self.repo.save_performance_summary(run_id, {
            'wall_seconds': round(monotonic() - run_started, 6),
            'provider_requests': {'chunk_score_live': chunk.get('calls', 0),
                                  'findings_live': findings.get('calls', 0)},
            'cache': {'chunk_score_batches': chunk.get('cached_batches', 0),
                      'findings_reused': findings.get('cached', False)},
            'database_bytes': self.repo.db_path.stat().st_size if self.repo.db_path.exists() else 0,
            'measurement': 'live SEC and provider requests; cached and live requests are counted separately',
        })
        return self.repo.get_run(run_id)

    def _cancel(self, run_id, name, running=None):
        stage = running or self.repo.stage(run_id, name)
        active_elapsed = stage.elapsed_seconds
        if stage.active_started_monotonic is not None:
            active_elapsed = max(active_elapsed, monotonic() - stage.active_started_monotonic)
        cancelled = stage.model_copy(update={
            'status': 'cancelled', 'finished_at': datetime.now(UTC),
            'elapsed_seconds': active_elapsed, 'active_seconds': active_elapsed,
            'active_started_monotonic': None,
            'summary': 'Cancelled before domain work.',
            'limitation': 'Cancellation is durable; resume continues from completed checkpoints.',
        })
        self.repo.update_stage(cancelled, event_kind='stage_finished',
                               event_summary=cancelled.summary)
        self.repo.update_run(run_id, status='cancelled', summary=cancelled.limitation,
                             kind='run_cancelled')
        return self.repo.get_run(run_id)

    def cancel(self, run_id: str):
        self.repo.request_cancellation(run_id)

    def resume(self, run_id: str):
        run = self.repo.get_run(run_id)
        # A historical synchronous web-resume request could persist ``queued``
        # before failing to schedule its worker.  It is resumable only when a
        # stage proves that this is a stopped, partially executed run; a fresh
        # queued run remains ineligible.
        recoverable_queued = run.status == 'queued' and any(
            stage.status in ('failed', 'partial', 'cancelled', 'interrupted')
            for stage in self.repo.stages(run_id))
        if run.status not in ('cancelled', 'interrupted', 'failed', 'partial') and not recoverable_queued:
            raise ValueError('Only a stopped V2 run can be resumed.')
        self.repo.resume(run_id)

    def recover(self):
        for run in self.repo.recent(100):
            if run.status != 'running':
                continue
            for stage in self.repo.stages(run.run_id):
                if stage.status == 'running':
                    interrupted = stage.model_copy(update={
                        'status': 'interrupted', 'finished_at': datetime.now(UTC),
                        'summary': 'Worker stopped while this stage was active.',
                        'limitation': 'Create a fresh T14 shell run.',
                    })
                    self.repo.update_stage(interrupted, event_kind='stage_finished',
                                           event_summary=interrupted.summary)
            self.repo.update_run(run.run_id, status='interrupted',
                                 summary='Worker interrupted.', kind='run_interrupted')
