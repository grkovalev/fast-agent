"""T37 sequential random-report batch contracts."""
import asyncio
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from profitlab.sec.ticker_picker import TickerSelection
from profitlab.settings import Settings
from profitlab.v2.batch import SequentialReportBatchService
from profitlab.v2.contracts import V2Run
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def _selection(ticker):
    return TickerSelection(ticker, datetime.now(UTC), 'directory', 'version', 'hit',
                           'eligible' if ticker else 'exhausted', 'picker result')


class Picker:
    def __init__(self, values, calls):
        self.values, self.calls = values, calls

    def pick(self, *, exclude_tickers=None):
        self.calls.append(set(exclude_tickers or set()))
        return _selection(self.values.pop(0) if self.values else None)


class Pipeline:
    def __init__(self, repo):
        self.repo, self.created, self.active, self.maximum = repo, [], 0, 0
        self.release = None
        self.failure_ids = set()

    def create(self, ticker):
        now = datetime.now(UTC)
        run = V2Run(run_id=f'run-{len(self.created) + 1}', ticker=ticker,
                    created_at=now, updated_at=now)
        self.repo.create_run(run)
        self.created.append(run)
        return run

    async def run(self, run_id, **_kwargs):
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        if self.release:
            await self.release.wait()
        self.active -= 1
        status = 'failed' if run_id in self.failure_ids else 'completed'
        return self.repo.get_run(run_id).model_copy(update={'status': status, 'summary': 'done'})


def _service(tmp_path, tickers, *, count=3):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, RANDOM_BATCH_MAX_REPORTS=count,
                        RANDOM_BATCH_MAX_ATTEMPTS=count, _env_file=None)
    repo, calls = V2Repository(tmp_path), []
    pipeline = Pipeline(repo)
    service = SequentialReportBatchService(settings, pipeline, lambda: Picker(tickers, calls))
    return service, pipeline, repo, calls


def test_batch_is_serial_unique_and_records_picker_exhaustion(tmp_path):
    service, pipeline, repo, calls = _service(tmp_path, ['AAA', 'AAA', None])
    batch = service.create(3)

    asyncio.run(service.run(batch.batch_id))

    items = repo.report_batch_items(batch.batch_id)
    assert pipeline.maximum == 1
    assert [item.ticker for item in items] == ['AAA', 'AAA', None]
    assert [item.outcome for item in items] == ['completed', 'skipped', 'skipped']
    assert [run.ticker for run in pipeline.created] == ['AAA']
    # The picker is given all prior attempted tickers and the coordinator also rejects a duplicate.
    assert calls[1] == {'AAA'}
    assert repo.report_batch(batch.batch_id).status == 'completed'


def test_batch_cancellation_waits_for_child_then_resume_only_selects_remaining(tmp_path):
    service, pipeline, repo, calls = _service(tmp_path, ['AAA', 'BBB'], count=2)
    batch = service.create(2)
    pipeline.release = asyncio.Event()

    async def exercise():
        task = asyncio.create_task(service.run(batch.batch_id))
        while not repo.report_batch_items(batch.batch_id):
            await asyncio.sleep(0)
        service.cancel(batch.batch_id)
        pipeline.release.set()
        await task
        assert repo.report_batch(batch.batch_id).status == 'cancelled'
        service.resume(batch.batch_id)
        pipeline.release = None
        await service.run(batch.batch_id)

    asyncio.run(exercise())
    items = repo.report_batch_items(batch.batch_id)
    assert [item.ticker for item in items] == ['AAA', 'BBB']
    assert [item.outcome for item in items] == ['completed', 'completed']
    assert calls[1] == {'AAA'}


def test_failed_child_is_accounted_then_next_report_runs_when_policy_allows(tmp_path):
    service, pipeline, repo, _calls = _service(tmp_path, ['AAA', 'BBB'], count=2)
    batch = service.create(2)
    pipeline.failure_ids.add('run-1')

    asyncio.run(service.run(batch.batch_id))

    assert [item.outcome for item in repo.report_batch_items(batch.batch_id)] == ['failed', 'completed']


def test_batch_route_validates_limit_and_shows_persisted_progress(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, RANDOM_BATCH_MAX_REPORTS=2, _env_file=None)
    with TestClient(create_app(settings)) as client:
        bad = client.post('/v2/batches', data={'count': '3'})
        started = client.post('/v2/batches', data={'count': '1'}, follow_redirects=False)
        detail = client.get(started.headers['location'])
        page = client.get('/')

    assert bad.status_code == 400
    assert started.status_code == 303
    assert detail.status_code == 200
    assert 'Attempt order' in detail.text
    assert 'Choose between 1 and 2 reports.' in bad.text
    assert 'Run random reports' in page.text
