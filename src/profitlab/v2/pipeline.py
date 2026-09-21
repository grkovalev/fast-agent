"""Functional T14 shell around the eight ordered V2 stages."""
import asyncio
from datetime import UTC, datetime
from time import monotonic
from uuid import uuid4

from profitlab.sec.service import normalize_ticker

from .contracts import STAGE_NAMES, V2Run
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

    async def run(self, run_id: str, delay: float = 0):
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
            limitation = 'Stage implementation begins in a later task; no domain output was fabricated.'
            finished = running.model_copy(update={
                'status': 'partial', 'completed_work': 0, 'total_work': 0,
                'finished_at': datetime.now(UTC), 'elapsed_seconds': monotonic() - tick,
                'summary': f'{name.replace("_", " ").title()} shell reached.',
                'limitation': limitation,
            })
            self.repo.update_stage(finished, event_kind='stage_finished',
                                   event_summary=finished.summary)
        summary = 'V2 shell completed; all domain stages are explicitly unimplemented.'
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
