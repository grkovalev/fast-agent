"""Functional T14 shell around the eight ordered V2 stages."""
import asyncio
import hashlib
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from profitlab.sec.service import normalize_ticker

from .chunking import SourceRangeChunker
from .contracts import STAGE_NAMES, V2Run
from .outline_service import OutlineService
from .section_scoring import SectionScoringService
from .source_service import V2SourceService
from .storage import V2Repository


class V2PipelineService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = V2Repository(settings.data_dir)

    def create(self, ticker='DEMO', mode='offline', run_id=None):
        ticker = normalize_ticker(ticker)
        if mode not in ('offline', 'live'):
            raise ValueError('Use V2 mode offline or live.')
        now = datetime.now(UTC)
        run = V2Run(run_id=run_id or 'v2-' + uuid4().hex[:12], ticker=ticker, mode=mode,
                    created_at=now, updated_at=now,
                    summary='Eight-stage V2 pipeline is queued.')
        self.repo.create_run(run)
        return run

    async def run(self, run_id: str, delay: float = 0, *, implement_source: bool = False):
        run = self.repo.get_run(run_id)
        if run.status == 'running':
            raise ValueError('V2 run is already active.')
        if run.cancellation_requested:
            raise ValueError('V2 run was cancelled; create a fresh run.')
        self.repo.update_run(run_id, status='running', summary='V2 shell is advancing.',
                             kind='stage_started')
        for name in STAGE_NAMES:
            if self.repo.cancellation_requested(run_id):
                return self._cancel(run_id, name)
            old = self.repo.stage(run_id, name)
            started_at = datetime.now(UTC)
            tick = monotonic()
            running = old.model_copy(update={
                'status': 'running', 'started_at': started_at,
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
                        self.settings, self.repo).build(canonical, offline=run.mode == 'offline')
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
                    'limitation': ('Offline fixture outline generator; configure LLM_API_KEY for live '
                                   'model inference.' if run.mode == 'offline' else None),
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
                    def score_progress(completed, total, calls):
                        snapshot = self.repo.stage(run_id, 'section_score').model_copy(update={
                            'completed_work': completed, 'total_work': total,
                            'summary': f'Jev completed {calls} section-score batch(es).',
                        })
                        self.repo.update_stage(snapshot, event_kind='stage_started',
                                               event_summary=snapshot.summary)
                    result = await SectionScoringService(self.settings, self.repo).score(
                        run_id, document, sections, offline=run.mode == 'offline',
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
                                f'{uncertain} uncertain.'),
                    'limitation': ('Fixture Jev scores only; configure TYPESAFE_API_KEY for live '
                                   'section discovery.' if run.mode == 'offline' else None),
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
                    selected_ids = {item.item_id for item in self.repo.scores(run_id, 'section_score')
                                    if item.policy_decision == 'selected'}
                    selected_sections = [item for item in sections if item.section_id in selected_ids]
                    chunks = SourceRangeChunker(self.settings).build(document, selected_sections)
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
                    'summary': (f'Built {len(chunks)} bounded chunks from {len(selected_sections)} '
                                f'selected sections ({core_lines} primary canonical lines).'),
                    'limitation': ('Offline fixture source and Jev section scores; live source-range '
                                   'chunking has not yet been inspected.' if run.mode == 'offline' else None),
                    'input_hash': document.ref.source_hash,
                    'output_hash': hashlib.sha256(''.join(item.chunk_id for item in chunks).encode()).hexdigest(),
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
        summary = ('V2 source, outline, section scoring, and source-range chunking are complete; later domain stages are explicitly unimplemented.'
                   if implement_source else
                   'V2 shell completed; all domain stages are explicitly unimplemented.')
        self.repo.update_run(run_id, status='partial', summary=summary, kind='run_finished')
        return self.repo.get_run(run_id)

    def _cancel(self, run_id, name, running=None):
        stage = running or self.repo.stage(run_id, name)
        cancelled = stage.model_copy(update={
            'status': 'cancelled', 'finished_at': datetime.now(UTC),
            'summary': 'Cancelled before domain work.',
            'limitation': 'Cancellation is durable; this shell run cannot be resumed.',
        })
        self.repo.update_stage(cancelled, event_kind='stage_finished',
                               event_summary=cancelled.summary)
        self.repo.update_run(run_id, status='cancelled', summary=cancelled.limitation,
                             kind='run_cancelled')
        return self.repo.get_run(run_id)

    def cancel(self, run_id: str):
        self.repo.request_cancellation(run_id)

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
