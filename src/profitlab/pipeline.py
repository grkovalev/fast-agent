"""One persisted workflow for CLI and application-managed asynchronous jobs."""
import asyncio
import fcntl
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from profitlab.contracts.base import RunManifest
from profitlab.contracts.pipeline import PipelineState, StageState
from profitlab.sec.service import DiscoveryService, normalize_ticker
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder

STAGES = ('discover', 'download', 'parse', 'chunk', 'screen', 'extract',
          'reconcile', 'calculate', 'write', 'validate')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class PipelineService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = Repository(settings.data_dir)
        with self.repo.connect() as db:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' "
                                "AND name='workflows'").fetchone()
            if not exists:
                db.execute('CREATE TABLE workflows '
                           '(run_id TEXT PRIMARY KEY REFERENCES runs(run_id), '
                           'state TEXT NOT NULL, cancel INTEGER NOT NULL DEFAULT 0)')

    def state(self, run_id):
        self.repo.manifest(run_id)
        with self.repo.connect() as db:
            row = db.execute('SELECT state FROM workflows WHERE run_id=?', (run_id,)).fetchone()
        return PipelineState.model_validate_json(row['state']) if row else None

    def save(self, state):
        with self.repo.connect() as db:
            db.execute('UPDATE workflows SET state=? WHERE run_id=?',
                       (state.model_dump_json(), state.run.run_id))

    def create(self, ticker, years=4, mode='live', run_id=None, scenario='normal'):
        ticker = normalize_ticker(ticker)
        if mode not in ('live', 'demo') or years not in range(1, 5):
            raise ValueError('Use mode demo|live and 1–4 years.')
        if scenario not in ('normal', 'two-years', 'conflict', 'restatement', 'split-adjusted', 'losses', 'slow'):
            raise ValueError('Unsupported workflow scenario.')
        now = datetime.now(UTC)
        run = RunManifest(run_id=run_id or 'analyze-' + uuid4().hex[:12], ticker=ticker,
            mode=mode, requested_years=years, created_at=now, updated_at=now,
            stage='lookup', status='queued', configuration={'scenario': scenario, 'through': 'T13', 'limits': {
                'stage_timeout': self.settings.stage_timeout, 'run_total_timeout': self.settings.run_total_timeout,
                'provider_concurrency': 1, 'screen_max_requests': self.settings.screen_max_requests,
                'screen_total_timeout': self.settings.screen_total_timeout,
                'writer_max_requests': self.settings.writer_max_requests}},
            limitation='Workflow queued.')
        # A transaction protects the live reservation across CLI/server processes.
        with (self.repo.root / 'workflow-create.lock').open('a') as reservation, self.repo.connect() as db:
            fcntl.flock(reservation, fcntl.LOCK_EX)
            if mode == 'live':
                for row in db.execute('SELECT state FROM workflows'):
                    other = PipelineState.model_validate_json(row['state']).run
                    if other.mode == 'live' and other.status in ('queued', 'running'):
                        raise ValueError('A live workflow is already active.')
            self.repo.create_run(run)
            self.repo.put(run.run_id, 'summary', run.model_dump_json().encode())
            state = PipelineState(run=run, stages=[StageState(name=s) for s in STAGES])
            db.execute('INSERT INTO workflows (run_id, state) VALUES (?, ?)',
                       (run.run_id, state.model_dump_json()))
        return run

    def cancel(self, run_id):
        state = self.state(run_id)
        if not state:
            raise ValueError('This earlier run has no managed workflow.')
        with self.repo.connect() as db:
            db.execute('UPDATE workflows SET cancel=1 WHERE run_id=?', (run_id,))
        return state

    def cancelled(self, run_id):
        with self.repo.connect() as db:
            return bool(db.execute('SELECT cancel FROM workflows WHERE run_id=?',
                                   (run_id,)).fetchone()['cancel'])

    def inputs(self, stage, state, upstream):
        # Include only settings relevant to this stage so wording changes reuse evidence.
        fields = {
            'chunk': ('chunk_target_tokens', 'chunk_overlap_tokens', 'chunk_request_budget', 'chunk_question_overhead', 'chunk_max_count'),
            'screen': ('screen_keep_threshold', 'screen_uncertain_threshold', 'screen_max_requests',
                       'screen_total_timeout', 'screen_recovery_max_chunks', 'typesafe_model',
                       'typesafe_base_url'),
            'extract': ('llm_model', 'llm_base_url', 'llm_output_mode', 'structured_output_repairs'),
            'write': ('llm_model', 'llm_base_url', 'llm_output_mode', 'llm_reasoning_effort', 'writer_max_requests', 'writer_max_tool_calls', 'structured_output_repairs'),
        }.get(stage, ())
        files = {
            'parse': ('documents/parser.py',), 'chunk': ('documents/chunking.py',),
            'screen': ('prompts/screen-v1.json', 'providers/screening.py'),
            'extract': ('documents/extraction.py', 'providers/extraction.py'),
            'reconcile': ('analysis/reconciliation.py',),
            'calculate': ('analysis/calculations.py',),
            'write': ('prompts/write-v1.txt', 'analysis/reporting.py'),
        }.get(stage, ())
        root = Path(__file__).parent
        return digest({'stage': stage, 'upstream': upstream, 'ticker': state.run.ticker,
            'years': state.run.requested_years, 'mode': state.run.mode,
            'scenario': state.run.configuration['scenario'],
            'settings': {key: getattr(self.settings, key) for key in fields},
            'versions': {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in files}})

    def outputs_valid(self, run_id, stage):
        try:
            values = [(aid, hashlib.sha256(self.repo.read(run_id, aid)).hexdigest())
                      for aid in stage.output_ids]
            return digest(values) == stage.output_hash
        except (ValueError, FileNotFoundError):
            return False

    async def sync(self, function, *args):
        # A Python thread cannot be killed. Drain it before releasing ownership,
        # so cancellation/resume cannot race an unfinished artifact write.
        task = asyncio.create_task(asyncio.to_thread(function, *args))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await task
            raise

    async def perform(self, run_id, stage):
        async def watch():
            while not self.cancelled(run_id):
                await asyncio.sleep(.1)
        work = asyncio.create_task(self.execute(run_id, stage))
        monitor = asyncio.create_task(watch())
        try:
            done, _ = await asyncio.wait((work, monitor), return_when=asyncio.FIRST_COMPLETED)
            if monitor in done:
                raise asyncio.CancelledError()
            return await work
        finally:
            monitor.cancel()
            if not work.done():
                work.cancel()
            await asyncio.gather(work, monitor, return_exceptions=True)

    async def execute(self, run_id, stage):
        from profitlab.analysis.calculations import CalculationService
        from profitlab.analysis.reconciliation import ReconciliationService
        from profitlab.analysis.reporting import ReportingService
        from profitlab.documents.chunk_service import ChunkService
        from profitlab.documents.service import SourceService
        from profitlab.providers.extraction import ExtractionService
        from profitlab.providers.screening import ScreeningService

        if stage == 'discover':
            run = self.repo.manifest(run_id)
            try:
                result = json.loads(self.repo.read(run_id, 'discovery'))
            except FileNotFoundError:
                scenario = run.configuration['scenario']
                await self.sync(DiscoveryService(self.settings)._create,
                    run.ticker, run.requested_years, run.mode, run_id,
                    'normal' if scenario == 'slow' else scenario, False)
                result = json.loads(self.repo.read(run_id, 'discovery'))
            if result['outcome'] != 'found':
                raise ValueError(result['message'] + ' Start a fresh run to retry discovery.')
        elif stage in ('download', 'parse'):
            await self.sync(SourceService(self.settings, chunk_fixture=True).progress, run_id, stage)
        elif stage == 'chunk':
            await self.sync(ChunkService(self.settings).progress, run_id)
        elif stage == 'screen':
            await ScreeningService(self.settings).screen(run_id)
        elif stage == 'extract':
            await ExtractionService(self.settings).extract(run_id)
        elif stage == 'reconcile':
            await self.sync(ReconciliationService(self.settings).progress, run_id)
        elif stage == 'calculate':
            await self.sync(CalculationService(self.settings).progress, run_id)
        elif stage == 'write':
            await ReportingService(self.settings).write(run_id)
        elif stage == 'validate':
            checks = await self.sync(ReportingService(self.settings).verify, run_id)
            self.repo.put(run_id, 'workflow-validation-' + uuid4().hex, json.dumps(checks).encode())

    async def run(self, run_id):
        state = self.state(run_id)
        if state is None:
            raise ValueError('This earlier run has no managed workflow; use stage commands.')
        lock = (self.repo.root / 'runs' / run_id / 'workflow.lock').open('a')
        live_lock = (self.repo.root / 'live-workflow.lock').open('a')
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if state.run.mode == 'live':
                    fcntl.flock(live_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError('Workflow is already active.') from None
            if state.run.status == 'running':
                raise ValueError('Workflow is already active; recover interrupted work on restart.')
            if state.run.status != 'queued':
                with self.repo.connect() as db:
                    db.execute('UPDATE workflows SET cancel=0 WHERE run_id=?', (run_id,))
            with (self.repo.root / 'workflow-create.lock').open('a') as reservation:
                fcntl.flock(reservation, fcntl.LOCK_EX)
                if state.run.mode == 'live':
                    with self.repo.connect() as db:
                        for row in db.execute('SELECT state FROM workflows WHERE run_id != ?', (run_id,)):
                            other = PipelineState.model_validate_json(row['state']).run
                            if other.mode == 'live' and other.status in ('queued', 'running'):
                                raise ValueError('A live workflow is already active.')
                state = state.model_copy(update={'run': state.run.model_copy(update={'status': 'running'}),
                    'started_at': datetime.now(UTC), 'error': None})
                self.save(state)
            trace = TraceRecorder(self.repo, run_id, self.settings.redactor())
            started = time.monotonic()
            partial = False
            upstream = None
            index = 0
            try:
                for index, old in enumerate(state.stages):
                    if self.cancelled(run_id):
                        raise asyncio.CancelledError()
                    if time.monotonic() - started > self.settings.run_total_timeout:
                        raise TimeoutError('Total run budget reached.')
                    name = old.name
                    key = self.inputs(name, state, upstream)
                    if old.status == 'completed' and old.input_hash == key and self.outputs_valid(run_id, old):
                        upstream = old.output_hash
                        for aid in old.output_ids:
                            if aid.startswith('manifest-'):
                                partial |= RunManifest.model_validate_json(self.repo.read(run_id, aid)).status == 'partial'
                        continue
                    # Invalidate all downstream stages before executing new inputs.
                    stages = list(state.stages)
                    stages[index:] = [StageState(name=s.name) for s in stages[index:]]
                    stages[index] = StageState(name=name, status='running', input_hash=key)
                    state = state.model_copy(update={'stages': stages,
                        'run': self.repo.manifest(run_id).model_copy(update={'stage': name, 'status': 'running'})})
                    self.save(state)
                    if state.run.mode == 'live':
                        if not self.settings.sec_contact_ready():
                            raise ValueError('Configure SEC_USER_AGENT with a real contact email.')
                        if name in ('screen', 'extract', 'write'):
                            missing = [key for key, ready in (
                                ('TYPESAFE_API_KEY', bool(self.settings.typesafe_api_key.get_secret_value())),
                                ('LLM_API_KEY', bool(self.settings.llm_api_key.get_secret_value()))) if not ready]
                            if missing:
                                raise ValueError('Missing live configuration: ' + ', '.join(missing))
                    before = {a['artifact_id'] for a in self.repo.artifacts(run_id)}
                    tick = time.monotonic()
                    with trace.operation('Workflow stage ' + name, {'input_hash': key}, stage=name) as out:
                        async with asyncio.timeout(min(self.settings.stage_timeout,
                                self.settings.run_total_timeout - (tick - started))):
                            if state.run.configuration['scenario'] == 'slow':
                                await asyncio.sleep(self.settings.demo_stage_delay)
                            await self.perform(run_id, name)
                        artifacts = self.repo.artifacts(run_id)
                        ids = sorted(a['artifact_id'] for a in artifacts
                            if a['artifact_id'] not in before and not a['artifact_id'].startswith('payload-'))
                        # Deterministic stages can produce no new artifacts on a retry.
                        if not ids:
                            prefixes = {
                                'discover': ('discovery', 'filing-'),
                                'download': ('raw-', 'source-filing-'),
                                'parse': ('parsed-', 'block-', 'cell-'),
                            }.get(name, ())
                            ids = sorted(a['artifact_id'] for a in artifacts
                                         if a['artifact_id'].startswith(prefixes))
                            ids = ids or old.output_ids or ['manifest']
                        hashes = [(aid, hashlib.sha256(self.repo.read(run_id, aid)).hexdigest()) for aid in ids]
                        upstream = digest(hashes)
                        out.update(output_hash=upstream, output_ids=ids, source_run_id=run_id)
                    current = self.repo.manifest(run_id)
                    partial |= current.status == 'partial'
                    if current.status == 'failed':
                        raise ValueError(current.limitation)
                    stages = list(state.stages)
                    stages[index] = StageState(name=name, status='completed', input_hash=key,
                        output_hash=upstream, output_ids=ids, source_run_id=run_id,
                        elapsed_seconds=time.monotonic() - tick)
                    state = state.model_copy(update={'stages': stages, 'run': current.model_copy(
                        update={'status': 'running', 'stage': name})})
                    self.save(state)
                if self.cancelled(run_id):
                    raise asyncio.CancelledError()
                from profitlab.analysis.reporting import ReportingService
                report_index, report, _ = ReportingService(self.settings).latest(run_id)
                partial |= (len(state.run.covered_years) < state.run.requested_years or
                            not report_index['model_narrative'] or len(report.limitations) > 1)
                status = 'partial' if partial else 'completed'
                state = state.model_copy(update={'run': state.run.model_copy(update={
                    'stage': 'complete', 'status': status, 'updated_at': datetime.now(UTC),
                    'limitation': 'Workflow finished. Inspect the report and its coverage limitations.'})})
            except BaseException as error:
                if not isinstance(error, (Exception, asyncio.CancelledError)):
                    raise
                cancelled = isinstance(error, asyncio.CancelledError) or self.cancelled(run_id)
                status = 'cancelled' if cancelled else 'failed'
                message = ('Cancelled; remote completion/billing may be unknown.' if cancelled else
                           self.settings.redactor().text(type(error).__name__ + ': ' + str(error)))
                stages = list(state.stages)
                if stages[index].status == 'running':
                    stages[index] = stages[index].model_copy(update={
                        'status': 'interrupted' if cancelled else 'failed', 'error': message})
                state = state.model_copy(update={'stages': stages, 'error': message,
                    'run': self.repo.manifest(run_id).model_copy(update={'status': status,
                        'stage': stages[index].name, 'limitation': message, 'updated_at': datetime.now(UTC)})})
                trace.emit(kind='workflow_stop', span_id='workflow-' + uuid4().hex,
                           stage=stages[index].name, status=status, summary=message)
            state = state.model_copy(update={'elapsed_seconds': state.elapsed_seconds + time.monotonic() - started})
            self.save(state)
            return state.run
        finally:
            lock.close()
            live_lock.close()

    def recover(self):
        for run in self.repo.recent():
            state = self.state(run.run_id)
            if state and state.run.status in ('queued', 'running'):
                lock = (self.repo.root / 'runs' / run.run_id / 'workflow.lock').open('a')
                try:
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        continue  # Another process owns this worker.
                    TraceRecorder(self.repo, run.run_id, self.settings.redactor()).recover_interrupted()
                    state = state.model_copy(update={'run': state.run.model_copy(update={
                        'status': 'interrupted', 'limitation': 'Worker interrupted; resume to reuse unchanged stages.'}),
                        'stages': [s.model_copy(update={'status': 'interrupted'}) if s.status == 'running' else s for s in state.stages]})
                    self.save(state)
                finally:
                    lock.close()


class JobManager:
    """Application-owned tasks; cancellation propagates to asynchronous provider work."""
    def __init__(self, pipeline):
        self.pipeline = pipeline
        self.tasks = {}

    def start(self, run_id):
        if run_id in self.tasks and not self.tasks[run_id].done():
            raise ValueError('Workflow is already active.')
        state = self.pipeline.state(run_id)
        if not state:
            raise ValueError('Managed workflow not found.')
        if state.run.status != 'queued':
            with self.pipeline.repo.connect() as db:
                db.execute('UPDATE workflows SET cancel=0 WHERE run_id=?', (run_id,))
            self.pipeline.save(state.model_copy(update={'run': state.run.model_copy(update={'status': 'queued'})}))
        self.tasks[run_id] = asyncio.create_task(self.pipeline.run(run_id))
        self.tasks[run_id].add_done_callback(lambda task: task.exception() if not task.cancelled() else None)

    def cancel(self, run_id):
        self.pipeline.cancel(run_id)
        task = self.tasks.get(run_id)
        if task and not task.done() and self.pipeline.state(run_id).run.status == 'running':
            task.cancel()

    async def close(self):
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
