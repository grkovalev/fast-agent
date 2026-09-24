"""Durable, deliberately single-file batch orchestration for live V2 reports."""
import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from .contracts import ReportBatch, ReportBatchItem


class SequentialReportBatchService:
    """Select and execute child runs serially; child pipelines remain independent."""

    def __init__(self, settings, pipeline, picker_factory):
        self.settings = settings
        self.pipeline = pipeline
        self.repo = pipeline.repo
        self.picker_factory = picker_factory

    def create(self, requested_count: int) -> ReportBatch:
        if not 1 <= requested_count <= self.settings.random_batch_max_reports:
            raise ValueError(f'Choose between 1 and {self.settings.random_batch_max_reports} reports.')
        now = datetime.now(UTC)
        batch = ReportBatch(batch_id='batch-' + uuid4().hex[:12], requested_count=requested_count,
                            created_at=now, updated_at=now,
                            summary='Batch is queued; no report has started yet.')
        self.repo.create_report_batch(batch)
        return batch

    def cancel(self, batch_id: str):
        batch = self.repo.report_batch(batch_id)
        if batch.status in {'completed', 'cancelled'}:
            raise ValueError('This batch is already terminal.')
        return self.repo.update_report_batch(batch_id, status='cancelling', cancellation_requested=True,
                                             summary='Cancellation requested; the active report may finish safely.')

    def resume(self, batch_id: str):
        batch = self.repo.report_batch(batch_id)
        if batch.status not in {'cancelled', 'cancelling'}:
            raise ValueError('Only a cancelled batch can be resumed.')
        return self.repo.update_report_batch(batch_id, status='queued', cancellation_requested=False,
                                             summary='Batch resume requested; only remaining reports will be selected.')

    async def run(self, batch_id: str):
        batch = self.repo.report_batch(batch_id)
        if batch.status == 'running':
            raise ValueError('Batch is already active.')
        if batch.status == 'completed':
            return batch
        self.repo.update_report_batch(batch_id, status='running', cancellation_requested=False,
                                      summary='Selecting the next eligible report.')
        while True:
            batch = self.repo.report_batch(batch_id)
            if batch.status in {'completed', 'cancelled'}:
                return batch
            items = self.repo.report_batch_items(batch_id)
            active = next((item for item in items if item.outcome is None and item.run_id), None)
            if active:
                await self._finish_existing(active)
                continue
            if batch.cancellation_requested:
                return self.repo.update_report_batch(batch_id, status='cancelled',
                    summary='Batch cancelled; no future ticker will be selected.')
            if len(items) >= batch.requested_count:
                return self.repo.update_report_batch(batch_id, status='completed',
                    summary=f'Finished {len(items)}/{batch.requested_count} requested batch attempts.')
            if len(items) >= self.settings.random_batch_max_attempts:
                return self.repo.update_report_batch(batch_id, status='completed',
                    summary='Batch stopped after its bounded selection-attempt limit.')

            ordinal = len(items) + 1
            excluded = {item.ticker for item in items if item.ticker}
            selection = await asyncio.to_thread(self.picker_factory().pick, exclude_tickers=excluded)
            if not selection.ticker:
                now = datetime.now(UTC)
                self.repo.add_report_batch_item(ReportBatchItem(
                    batch_id=batch_id, ordinal=ordinal, started_at=now, outcome='skipped',
                    finished_at=now, message=selection.message))
                if not self.settings.random_batch_continue_after_failure:
                    return self.repo.update_report_batch(batch_id, status='completed',
                        summary='Batch stopped by the configured picker-failure policy.')
                continue
            if selection.ticker in excluded:
                now = datetime.now(UTC)
                self.repo.add_report_batch_item(ReportBatchItem(
                    batch_id=batch_id, ordinal=ordinal, ticker=selection.ticker, started_at=now,
                    outcome='skipped', finished_at=now,
                    message='Picker returned a ticker already attempted by this batch.'))
                continue
            try:
                run = self.pipeline.create(selection.ticker)
            except ValueError as error:
                now = datetime.now(UTC)
                self.repo.add_report_batch_item(ReportBatchItem(
                    batch_id=batch_id, ordinal=ordinal, ticker=selection.ticker, started_at=now,
                    outcome='failed', finished_at=now, message=str(error)))
                if not self.settings.random_batch_continue_after_failure:
                    return self.repo.update_report_batch(batch_id, status='completed', summary=str(error))
                continue
            self.repo.add_report_batch_item(ReportBatchItem(
                batch_id=batch_id, ordinal=ordinal, ticker=run.ticker, run_id=run.run_id,
                started_at=datetime.now(UTC), message='Child report is running.'))
            await self._finish_existing(self.repo.report_batch_items(batch_id)[-1])

    async def _finish_existing(self, item: ReportBatchItem):
        try:
            run = await self.pipeline.run(item.run_id, delay=.05, implement_source=True)
            evaluation = self.repo.stage(item.run_id, 'evaluate')
            successful = run.status == 'completed' or (evaluation and evaluation.status == 'completed')
            outcome = 'completed' if successful else ('cancelled' if run.status == 'cancelled' else 'failed')
            message = run.summary
        except Exception as error:  # noqa: BLE001 - the child remains independently inspectable.
            outcome, message = 'failed', str(error)
        self.repo.finish_report_batch_item(item.batch_id, item.ordinal, outcome=outcome, message=message)
        if outcome != 'completed' and not self.settings.random_batch_continue_after_failure:
            self.repo.update_report_batch(item.batch_id, status='completed',
                                          summary='Batch stopped by the configured child-failure policy.')
