"""Fresh SQLite namespace for V2 runs."""
import json
import sqlite3
import zlib
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic

from .canonical import CanonicalDocument
from .contracts import (
    STAGE_NAMES,
    CanonicalDocumentRef,
    OutlineSection,
    PipelineEvent,
    ReportBatch,
    ReportBatchItem,
    StageSnapshot,
    TextChunk,
    V2Run,
)


class V2Repository:
    _APPLICATION_ID = 0x50524F46  # "PROF" identifies a fresh ProfitLab V2 database.

    def __init__(self, data_dir: Path):
        self.root = data_dir / 'v2'
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'profitlab-v2.sqlite3'
        new_database = not self.db_path.exists()
        try:
            with self.connect() as db:
                if new_database:
                    db.executescript(self._schema())
                elif db.execute('PRAGMA application_id').fetchone()[0] != self._APPLICATION_ID:
                    raise ValueError(self._unsupported_database_message())
                else:
                    self._assert_current_schema(db)
        except sqlite3.DatabaseError as error:
            raise ValueError(self._unsupported_database_message()) from error

    def _unsupported_database_message(self) -> str:
        return (f'Unsupported existing V2 data at {self.root}. ProfitLab only opens newly '
                f'created V2 databases; remove {self.root} and restart to create fresh data.')

    def _assert_current_schema(self, db):
        required_tables = {
            'runs', 'stages', 'events', 'filings', 'canonical_documents', 'outline_sections',
            'outline_batches', 'scores', 'exploration_actions', 'chunks', 'chunk_ranges',
            'findings', 'structured_facts', 'comparisons', 'chunk_score_batches',
            'chunk_score_summaries', 'finding_batches', 'finding_summaries',
            'company_fact_datasets', 'fact_summaries', 'comparison_summaries',
            'section_score_batches', 'performance_summaries', 'evaluation_scale_verdicts',
            'ticker_selections', 'retrieval_benchmarks', 'evaluation_scorecards',
            'report_batches', 'report_batch_items',
        }
        actual_tables = {row['name'] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not required_tables <= actual_tables:
            raise ValueError(self._unsupported_database_message())
        run_columns = {row['name'] for row in db.execute('PRAGMA table_info(runs)')}
        expected_run_columns = {
            'run_id', 'ticker', 'status', 'selected_stage', 'cancellation_requested',
            'created_at', 'updated_at', 'summary', 'version_id', 'version_components',
            'version_state', 'total_elapsed_seconds', 'queued_seconds', 'active_seconds',
            'timing_origin_monotonic',
        }
        if run_columns != expected_run_columns:
            raise ValueError(self._unsupported_database_message())

    @staticmethod
    def _schema():
        return '''
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY, ticker TEXT NOT NULL,
                status TEXT NOT NULL, selected_stage TEXT NOT NULL,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, summary TEXT NOT NULL,
                version_id TEXT NOT NULL, version_components TEXT NOT NULL,
                version_state TEXT NOT NULL, total_elapsed_seconds REAL,
                queued_seconds REAL, active_seconds REAL, timing_origin_monotonic REAL);
            CREATE TABLE stages (
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                stage TEXT NOT NULL, position INTEGER NOT NULL, status TEXT NOT NULL,
                completed_work INTEGER NOT NULL, total_work INTEGER,
                started_at TEXT, finished_at TEXT, elapsed_seconds REAL NOT NULL,
                queued_seconds REAL NOT NULL, active_seconds REAL NOT NULL,
                retry_backoff_seconds REAL NOT NULL, active_started_monotonic REAL,
                summary TEXT NOT NULL, limitation TEXT, error TEXT,
                input_hash TEXT, output_hash TEXT, PRIMARY KEY(run_id, stage));
            CREATE TABLE events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                stage TEXT, kind TEXT NOT NULL, status TEXT NOT NULL,
                summary TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX events_run_sequence ON events(run_id, sequence);
            CREATE INDEX stages_run_position ON stages(run_id, position);

            CREATE TABLE filings (run_id TEXT NOT NULL, filing_id TEXT NOT NULL,
                source_hash TEXT, payload TEXT NOT NULL, PRIMARY KEY(run_id, filing_id));
            CREATE TABLE canonical_documents (
                run_id TEXT NOT NULL, document_id TEXT NOT NULL, filing_id TEXT NOT NULL,
                source_hash TEXT NOT NULL, line_count INTEGER NOT NULL, raw_html BLOB NOT NULL,
                visible_html BLOB NOT NULL, canonical_json TEXT NOT NULL,
                PRIMARY KEY(run_id, document_id), UNIQUE(run_id, filing_id));
            CREATE INDEX canonical_documents_run_filing ON canonical_documents(run_id, filing_id);
            CREATE TABLE outline_sections (run_id TEXT NOT NULL, section_id TEXT NOT NULL,
                filing_id TEXT, start_line INTEGER, end_line INTEGER, payload TEXT NOT NULL,
                PRIMARY KEY(run_id, section_id));
            CREATE TABLE outline_batches (
                source_range_hash TEXT NOT NULL, prompt_version TEXT NOT NULL,
                configuration_hash TEXT NOT NULL, actual_model TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(source_range_hash, prompt_version, configuration_hash, actual_model));
            CREATE TABLE scores (run_id TEXT NOT NULL, score_kind TEXT NOT NULL,
                item_id TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(run_id, score_kind, item_id));
            CREATE TABLE exploration_actions (run_id TEXT NOT NULL, action_id TEXT NOT NULL,
                stage TEXT NOT NULL, sequence INTEGER NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(run_id, action_id));
            CREATE TABLE chunks (run_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
                section_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id, chunk_id));
            CREATE TABLE chunk_ranges (run_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
                range_kind TEXT NOT NULL, ordinal INTEGER NOT NULL, start_line INTEGER NOT NULL,
                end_line INTEGER NOT NULL, PRIMARY KEY(run_id, chunk_id, range_kind, ordinal));
            CREATE TABLE findings (run_id TEXT NOT NULL, finding_id TEXT NOT NULL,
                payload TEXT NOT NULL, PRIMARY KEY(run_id, finding_id));
            CREATE TABLE structured_facts (run_id TEXT NOT NULL, fact_id TEXT NOT NULL,
                metric TEXT NOT NULL, value TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(run_id, fact_id));
            CREATE TABLE comparisons (run_id TEXT NOT NULL, comparison_id TEXT NOT NULL,
                state TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(run_id, comparison_id));
            CREATE TABLE chunk_score_batches (source_range_hash TEXT NOT NULL,
                prompt_version TEXT NOT NULL, configuration_hash TEXT NOT NULL,
                actual_model TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(source_range_hash, prompt_version, configuration_hash, actual_model));
            CREATE TABLE chunk_score_summaries (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE finding_batches (request_hash TEXT NOT NULL, prompt_version TEXT NOT NULL,
                configuration_hash TEXT NOT NULL, actual_model TEXT NOT NULL, payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(request_hash, prompt_version, configuration_hash, actual_model));
            CREATE TABLE finding_summaries (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE company_fact_datasets (run_id TEXT PRIMARY KEY,
                cik TEXT NOT NULL, source_url TEXT NOT NULL, source_hash TEXT NOT NULL,
                retrieved_at TEXT NOT NULL, payload BLOB NOT NULL);
            CREATE TABLE fact_summaries (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE comparison_summaries (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE section_score_batches (source_range_hash TEXT NOT NULL,
                prompt_version TEXT NOT NULL, configuration_hash TEXT NOT NULL,
                actual_model TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(source_range_hash, prompt_version, configuration_hash, actual_model));
            CREATE TABLE performance_summaries (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE evaluation_scale_verdicts (pair_hash TEXT NOT NULL,
                prompt_version TEXT NOT NULL, configuration_hash TEXT NOT NULL,
                actual_model TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(pair_hash, prompt_version, configuration_hash, actual_model));
            CREATE TABLE ticker_selections (
                selection_id INTEGER PRIMARY KEY AUTOINCREMENT, ticker TEXT,
                selected_at TEXT NOT NULL, directory_provenance TEXT NOT NULL,
                directory_version TEXT NOT NULL, cache_status TEXT NOT NULL,
                eligibility TEXT NOT NULL, message TEXT NOT NULL);
            CREATE TABLE retrieval_benchmarks (run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
                payload TEXT NOT NULL);
            CREATE TABLE evaluation_scorecards (
                configuration_hash TEXT PRIMARY KEY, input_hash TEXT NOT NULL,
                calculated_at TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE report_batches (
                batch_id TEXT PRIMARY KEY, requested_count INTEGER NOT NULL,
                status TEXT NOT NULL, cancellation_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, summary TEXT NOT NULL);
            CREATE TABLE report_batch_items (
                batch_id TEXT NOT NULL REFERENCES report_batches(batch_id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, ticker TEXT, run_id TEXT REFERENCES runs(run_id) ON DELETE SET NULL,
                started_at TEXT NOT NULL, finished_at TEXT, outcome TEXT, message TEXT NOT NULL,
                PRIMARY KEY(batch_id, ordinal));
            CREATE INDEX report_batch_items_batch_ordinal ON report_batch_items(batch_id, ordinal);
            CREATE INDEX scores_run_kind_item ON scores(run_id, score_kind, item_id);
            CREATE INDEX chunks_run_section ON chunks(run_id, section_id, chunk_id);
            CREATE INDEX exploration_actions_run_stage_sequence ON exploration_actions(run_id, stage, sequence);
            PRAGMA application_id=0x50524F46;
        '''

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                yield db
        finally:
            db.close()

    def create_run(self, run: V2Run):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM runs WHERE run_id=?', (run.run_id,)).fetchone():
                raise ValueError(f'V2 run {run.run_id} already exists; choose a fresh run ID.')
            db.execute('INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', (
                run.run_id, run.ticker, run.status, run.selected_stage,
                run.cancellation_requested, run.created_at.isoformat(), run.updated_at.isoformat(),
                run.summary, run.version_id, json.dumps(run.version_components, sort_keys=True),
                run.version_state, run.total_elapsed_seconds, run.queued_seconds, run.active_seconds,
                run.timing_origin_monotonic,
            ))
            for position, stage in enumerate(STAGE_NAMES, 1):
                snapshot = StageSnapshot(run_id=run.run_id, stage=stage, position=position)
                self._write_stage(db, snapshot)
            self._event(db, run.run_id, None, 'run_created', run.status,
                        'Fresh V2 run created.')

    @staticmethod
    def _write_stage(db, stage: StageSnapshot):
        if stage.elapsed_seconds and not stage.active_seconds:
            stage = stage.model_copy(update={'active_seconds': stage.elapsed_seconds})
        values = stage.model_dump(mode='json')
        db.execute('''INSERT OR REPLACE INTO stages VALUES (
            :run_id, :stage, :position, :status, :completed_work, :total_work,
            :started_at, :finished_at, :elapsed_seconds, :queued_seconds, :active_seconds,
            :retry_backoff_seconds, :active_started_monotonic, :summary, :limitation,
            :error, :input_hash, :output_hash)''', values)

    @staticmethod
    def _event(db, run_id, stage, kind, status, summary):
        now = datetime.now(UTC).isoformat()
        cursor = db.execute('INSERT INTO events '
            '(run_id, stage, kind, status, summary, created_at) VALUES (?, ?, ?, ?, ?, ?)',
            (run_id, stage, kind, status, summary, now))
        return cursor.lastrowid

    def get_run(self, run_id: str) -> V2Run:
        with self.connect() as db:
            row = db.execute('SELECT * FROM runs WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            raise FileNotFoundError(run_id)
        return self._run_from_row(row)

    @staticmethod
    def _run_from_row(row) -> V2Run:
        payload = dict(row)
        payload['version_components'] = json.loads(payload['version_components'])
        return V2Run.model_validate(payload)

    def recent(self, limit: int = 50):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM runs ORDER BY created_at DESC LIMIT ?',
                              (min(limit, 100),)).fetchall()
        return [self._run_from_row(row) for row in rows]

    def runs(self) -> list[V2Run]:
        """Return every persisted run for cross-run reporting."""
        with self.connect() as db:
            rows = db.execute('SELECT * FROM runs ORDER BY created_at DESC').fetchall()
        return [self._run_from_row(row) for row in rows]

    def processed_tickers(self):
        with self.connect() as db:
            rows = db.execute('SELECT DISTINCT ticker FROM runs').fetchall()
        return {row['ticker'] for row in rows}

    def create_report_batch(self, batch: ReportBatch):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO report_batches VALUES (?, ?, ?, ?, ?, ?, ?)', (
                batch.batch_id, batch.requested_count, batch.status, batch.cancellation_requested,
                batch.created_at.isoformat(), batch.updated_at.isoformat(), batch.summary))

    def report_batch(self, batch_id: str) -> ReportBatch:
        with self.connect() as db:
            row = db.execute('SELECT * FROM report_batches WHERE batch_id=?', (batch_id,)).fetchone()
        if not row:
            raise FileNotFoundError(batch_id)
        return ReportBatch.model_validate(dict(row))

    def report_batches(self, limit: int = 50) -> list[ReportBatch]:
        with self.connect() as db:
            rows = db.execute('SELECT * FROM report_batches ORDER BY created_at DESC LIMIT ?',
                              (min(limit, 100),)).fetchall()
        return [ReportBatch.model_validate(dict(row)) for row in rows]

    def update_report_batch(self, batch_id: str, *, status: str | None = None,
                            cancellation_requested: bool | None = None, summary: str | None = None):
        current = self.report_batch(batch_id)
        updated = current.model_copy(update={
            'status': status if status is not None else current.status,
            'cancellation_requested': (cancellation_requested if cancellation_requested is not None
                                       else current.cancellation_requested),
            'summary': summary if summary is not None else current.summary,
            'updated_at': datetime.now(UTC),
        })
        with self.connect() as db:
            db.execute('UPDATE report_batches SET status=?, cancellation_requested=?, updated_at=?, summary=? '
                       'WHERE batch_id=?', (updated.status, updated.cancellation_requested,
                                             updated.updated_at.isoformat(), updated.summary, batch_id))
        return updated

    def add_report_batch_item(self, item: ReportBatchItem):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT INTO report_batch_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (
                item.batch_id, item.ordinal, item.ticker, item.run_id, item.started_at.isoformat(),
                item.finished_at.isoformat() if item.finished_at else None, item.outcome, item.message))

    def finish_report_batch_item(self, batch_id: str, ordinal: int, *, outcome: str, message: str):
        now = datetime.now(UTC)
        with self.connect() as db:
            changed = db.execute('UPDATE report_batch_items SET finished_at=?, outcome=?, message=? '
                                 'WHERE batch_id=? AND ordinal=?',
                                 (now.isoformat(), outcome, message, batch_id, ordinal)).rowcount
        if not changed:
            raise FileNotFoundError(f'{batch_id}:{ordinal}')

    def report_batch_items(self, batch_id: str) -> list[ReportBatchItem]:
        self.report_batch(batch_id)
        with self.connect() as db:
            rows = db.execute('SELECT * FROM report_batch_items WHERE batch_id=? ORDER BY ordinal',
                              (batch_id,)).fetchall()
        return [ReportBatchItem.model_validate(dict(row)) for row in rows]

    def record_ticker_selection(self, selection):
        with self.connect() as db:
            db.execute('''INSERT INTO ticker_selections
                (ticker, selected_at, directory_provenance, directory_version, cache_status, eligibility, message)
                VALUES (?, ?, ?, ?, ?, ?, ?)''', (
                    selection.ticker, selection.selected_at.isoformat(), selection.directory_provenance,
                    selection.directory_version, selection.cache_status, selection.eligibility,
                    selection.message))

    def latest_ticker_selection(self):
        with self.connect() as db:
            row = db.execute('SELECT * FROM ticker_selections ORDER BY selection_id DESC LIMIT 1').fetchone()
        return dict(row) if row else None

    def remove_run(self, run_id: str):
        """Delete exactly one run and all of its run-owned persisted output."""
        run_owned_tables = (
            'chunk_ranges', 'chunks', 'comparisons', 'structured_facts', 'findings',
            'scores', 'outline_sections', 'canonical_documents', 'filings',
            'exploration_actions', 'chunk_score_summaries', 'finding_summaries',
            'company_fact_datasets', 'fact_summaries', 'comparison_summaries',
            'performance_summaries',
        )
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM runs WHERE run_id=?', (run_id,)).fetchone():
                raise FileNotFoundError(run_id)
            for table in run_owned_tables:
                db.execute(f'DELETE FROM {table} WHERE run_id=?', (run_id,))
            # Stages and events are foreign-key owned and cascade with the run.
            db.execute('DELETE FROM runs WHERE run_id=?', (run_id,))

    def clear_shared_caches(self):
        """Remove reusable provider results without touching any run-owned data."""
        cache_tables = (
            'outline_batches', 'section_score_batches', 'chunk_score_batches',
            'finding_batches', 'evaluation_scale_verdicts',
        )
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            return {table: db.execute(f'DELETE FROM {table}').rowcount for table in cache_tables}

    def stages(self, run_id: str):
        self.get_run(run_id)
        with self.connect() as db:
            rows = db.execute('SELECT * FROM stages WHERE run_id=? ORDER BY position',
                              (run_id,)).fetchall()
        return [StageSnapshot.model_validate(dict(row)) for row in rows]

    def stage(self, run_id: str, name: str):
        return next((stage for stage in self.stages(run_id) if stage.stage == name), None)

    def update_stage(self, stage: StageSnapshot, *, event_kind: str, event_summary: str):
        """Commit the stage snapshot before making its event visible to readers."""
        stage = StageSnapshot.model_validate(stage.model_dump(mode='json'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM runs WHERE run_id=?',
                              (stage.run_id,)).fetchone():
                raise FileNotFoundError(stage.run_id)
            self._write_stage(db, stage)
            db.execute('UPDATE runs SET selected_stage=?, updated_at=? WHERE run_id=?',
                       (stage.stage, datetime.now(UTC).isoformat(), stage.run_id))
            sequence = self._event(db, stage.run_id, stage.stage, event_kind,
                                   stage.status, event_summary)
        return sequence

    def update_run(self, run_id: str, *, status: str, summary: str, kind: str):
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT timing_origin_monotonic, total_elapsed_seconds FROM runs '
                             'WHERE run_id=?', (run_id,)).fetchone()
            if not row:
                raise FileNotFoundError(run_id)
            stage_active = db.execute('SELECT COALESCE(SUM(active_seconds), 0) AS value FROM stages '
                                      'WHERE run_id=?', (run_id,)).fetchone()['value']
            elapsed = row['total_elapsed_seconds']
            if row['timing_origin_monotonic'] is not None:
                elapsed = max(float(elapsed or 0), monotonic() - row['timing_origin_monotonic'])
            queued = max(0.0, elapsed - stage_active) if elapsed is not None else None
            changed = db.execute('UPDATE runs SET status=?, summary=?, updated_at=?, '
                                 'total_elapsed_seconds=?, queued_seconds=?, active_seconds=? WHERE run_id=?',
                                 (status, summary, now, elapsed, queued, stage_active, run_id)).rowcount
            if not changed:
                raise FileNotFoundError(run_id)
            return self._event(db, run_id, None, kind, status, summary)

    def request_cancellation(self, run_id: str):
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('UPDATE runs SET cancellation_requested=1, updated_at=? '
                                 'WHERE run_id=?', (now, run_id)).rowcount
            if not changed:
                raise FileNotFoundError(run_id)
            return self._event(db, run_id, None, 'cancellation_requested',
                               self.get_run_status(db, run_id), 'Cancellation requested.')

    def resume(self, run_id: str):
        """Clear only the durable stop flag; stage checkpoints remain authoritative."""
        now = datetime.now(UTC).isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            changed = db.execute('UPDATE runs SET cancellation_requested=0, status=?, updated_at=? '
                                 'WHERE run_id=?', ('queued', now, run_id)).rowcount
            if not changed:
                raise FileNotFoundError(run_id)
            return self._event(db, run_id, None, 'resume_requested', 'queued',
                               'Resume requested; completed checkpoints will be reused.')

    @staticmethod
    def get_run_status(db, run_id):
        return db.execute('SELECT status FROM runs WHERE run_id=?', (run_id,)).fetchone()['status']

    def cancellation_requested(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT cancellation_requested FROM runs WHERE run_id=?',
                             (run_id,)).fetchone()
        if not row:
            raise FileNotFoundError(run_id)
        return bool(row['cancellation_requested'])

    def events(self, run_id: str, after: int = 0, limit: int = 100):
        self.get_run(run_id)
        with self.connect() as db:
            rows = db.execute('SELECT * FROM events WHERE run_id=? AND sequence>? '
                              'ORDER BY sequence LIMIT ?',
                              (run_id, max(after, 0), min(max(limit, 1), 100))).fetchall()
        return [PipelineEvent.model_validate(dict(row)) for row in rows]

    def state(self, run_id: str):
        return {'run': self.get_run(run_id), 'stages': self.stages(run_id)}

    def save_canonical_document(self, run_id: str, document: CanonicalDocument,
                                raw_html: bytes, visible_html: bytes):
        self.get_run(run_id)
        ref = document.ref
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO canonical_documents
                (run_id, document_id, filing_id, source_hash, line_count, raw_html, visible_html,
                 canonical_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)''', (
                    run_id, ref.document_id, ref.filing_id, ref.source_hash, ref.line_count,
                    raw_html, visible_html, document.model_dump_json()))

    def save_filing(self, run_id: str, filing_id: str, source_hash: str, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO filings (run_id, filing_id, source_hash, payload) '
                       'VALUES (?, ?, ?, ?)', (run_id, filing_id, source_hash,
                                                json.dumps(payload, sort_keys=True)))

    def canonical_document(self, run_id: str, document_id: str) -> CanonicalDocument:
        with self.connect() as db:
            row = db.execute('SELECT canonical_json FROM canonical_documents WHERE run_id=? '
                             'AND document_id=?', (run_id, document_id)).fetchone()
        if not row:
            raise FileNotFoundError(document_id)
        return CanonicalDocument.model_validate_json(row['canonical_json'])

    def canonical_by_filing(self, run_id: str, filing_id: str) -> CanonicalDocument:
        with self.connect() as db:
            row = db.execute('SELECT canonical_json FROM canonical_documents WHERE run_id=? '
                             'AND filing_id=?', (run_id, filing_id)).fetchone()
        if not row:
            raise FileNotFoundError(filing_id)
        return CanonicalDocument.model_validate_json(row['canonical_json'])

    def canonical_refs(self, run_id: str) -> list[CanonicalDocumentRef]:
        with self.connect() as db:
            rows = db.execute('SELECT document_id, filing_id, source_hash, line_count FROM '
                              'canonical_documents WHERE run_id=? ORDER BY filing_id',
                              (run_id,)).fetchall()
        return [CanonicalDocumentRef.model_validate(dict(row)) for row in rows]

    def visible_html(self, run_id: str, document_id: str) -> bytes:
        with self.connect() as db:
            row = db.execute('SELECT visible_html FROM canonical_documents WHERE run_id=? '
                             'AND document_id=?', (run_id, document_id)).fetchone()
        if not row:
            raise FileNotFoundError(document_id)
        return bytes(row['visible_html'])

    def save_outline_sections(self, run_id: str, sections: list[OutlineSection]):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM outline_sections WHERE run_id=?', (run_id,))
            db.executemany('''INSERT INTO outline_sections
                (run_id, section_id, filing_id, start_line, end_line, payload)
                VALUES (?, ?, ?, ?, ?, ?)''', [
                    (run_id, item.section_id, item.primary_range.document_id,
                     item.primary_range.start_line, item.primary_range.end_line,
                     item.model_dump_json()) for item in sections])

    def outline_sections(self, run_id: str, *, page: int | None = None,
                         per_page: int = 100) -> list[OutlineSection]:
        limit, offset = self._page_bounds(page, per_page)
        with self.connect() as db:
            query = ('SELECT payload FROM outline_sections WHERE run_id=? '
                     'ORDER BY start_line, end_line, section_id')
            if limit:
                query += ' LIMIT ? OFFSET ?'
                rows = db.execute(query, (run_id, limit, offset)).fetchall()
            else:
                rows = db.execute(query, (run_id,)).fetchall()
        return [OutlineSection.model_validate_json(row['payload']) for row in rows]

    def save_scores(self, run_id: str, score_kind: str, scores):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM scores WHERE run_id=? AND score_kind=?', (run_id, score_kind))
            db.executemany('INSERT INTO scores (run_id, score_kind, item_id, payload) VALUES (?, ?, ?, ?)', [
                (run_id, score_kind, item.item_id, item.model_dump_json()) for item in scores])

    def scores(self, run_id: str, score_kind: str, *, page: int | None = None,
               per_page: int = 100):
        from .contracts import ScoredItem

        limit, offset = self._page_bounds(page, per_page)
        with self.connect() as db:
            query = 'SELECT payload FROM scores WHERE run_id=? AND score_kind=? ORDER BY item_id'
            if limit:
                query += ' LIMIT ? OFFSET ?'
                rows = db.execute(query, (run_id, score_kind, limit, offset)).fetchall()
            else:
                rows = db.execute(query, (run_id, score_kind)).fetchall()
        return [ScoredItem.model_validate_json(row['payload']) for row in rows]

    def scores_for_items(self, run_id: str, score_kind: str, item_ids: list[str]):
        """Fetch score metadata only for the bounded items rendered on a page."""
        from .contracts import ScoredItem

        item_ids = list(dict.fromkeys(item_ids))[:100]
        if not item_ids:
            return []
        placeholders = ', '.join('?' for _ in item_ids)
        with self.connect() as db:
            rows = db.execute(f'''SELECT payload FROM scores WHERE run_id=? AND score_kind=?
                AND item_id IN ({placeholders}) ORDER BY item_id''',
                              (run_id, score_kind, *item_ids)).fetchall()
        return [ScoredItem.model_validate_json(row['payload']) for row in rows]

    def chunk_score_batch(self, source_range_hash: str, prompt_version: str,
                          configuration_hash: str, actual_model: str):
        with self.connect() as db:
            row = db.execute('''SELECT payload FROM chunk_score_batches WHERE source_range_hash=?
                AND prompt_version=? AND configuration_hash=? AND actual_model=?''',
                             (source_range_hash, prompt_version, configuration_hash,
                              actual_model)).fetchone()
        return json.loads(row['payload']) if row else None

    def section_score_batch(self, source_range_hash: str, prompt_version: str,
                            configuration_hash: str, actual_model: str):
        with self.connect() as db:
            row = db.execute('''SELECT payload FROM section_score_batches WHERE source_range_hash=?
                AND prompt_version=? AND configuration_hash=? AND actual_model=?''',
                             (source_range_hash, prompt_version, configuration_hash,
                              actual_model)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_section_score_batch(self, source_range_hash: str, prompt_version: str,
                                 configuration_hash: str, actual_model: str, payload: dict):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO section_score_batches
                (source_range_hash, prompt_version, configuration_hash, actual_model, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)''',
                       (source_range_hash, prompt_version, configuration_hash, actual_model,
                        json.dumps(payload, sort_keys=True), datetime.now(UTC).isoformat()))

    def save_chunk_score_batch(self, source_range_hash: str, prompt_version: str,
                               configuration_hash: str, actual_model: str, payload: dict):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO chunk_score_batches
                (source_range_hash, prompt_version, configuration_hash, actual_model, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)''',
                       (source_range_hash, prompt_version, configuration_hash, actual_model,
                        json.dumps(payload, sort_keys=True), datetime.now(UTC).isoformat()))

    def save_chunk_score_summary(self, run_id: str, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO chunk_score_summaries (run_id, payload) VALUES (?, ?)',
                       (run_id, json.dumps(payload, sort_keys=True)))

    def chunk_score_summary(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM chunk_score_summaries WHERE run_id=?', (run_id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_findings(self, run_id: str, findings):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM findings WHERE run_id=?', (run_id,))
            db.executemany('INSERT INTO findings (run_id, finding_id, payload) VALUES (?, ?, ?)', [
                (run_id, item.finding_id, item.model_dump_json()) for item in findings])

    def findings(self, run_id: str, *, page: int | None = None, per_page: int = 100):
        from .contracts import Finding

        limit, offset = self._page_bounds(page, per_page)
        with self.connect() as db:
            query = 'SELECT payload FROM findings WHERE run_id=? ORDER BY finding_id'
            if limit:
                query += ' LIMIT ? OFFSET ?'
                rows = db.execute(query, (run_id, limit, offset)).fetchall()
            else:
                rows = db.execute(query, (run_id,)).fetchall()
        return [Finding.model_validate_json(row['payload']) for row in rows]

    def filing(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM filings WHERE run_id=? ORDER BY filing_id LIMIT 1',
                             (run_id,)).fetchone()
        if not row:
            raise FileNotFoundError('V2 filing')
        return json.loads(row['payload'])

    def save_company_fact_dataset(self, run_id: str, *, cik: str, source_url: str,
                                  source_hash: str, payload: bytes):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO company_fact_datasets
                (run_id, cik, source_url, source_hash, retrieved_at, payload) VALUES (?, ?, ?, ?, ?, ?)''',
                       (run_id, cik, source_url, source_hash, datetime.now(UTC).isoformat(), payload))

    def company_fact_dataset(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT cik, source_url, source_hash, retrieved_at, payload FROM '
                             'company_fact_datasets WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            return None
        return {**{key: row[key] for key in ('cik', 'source_url', 'source_hash', 'retrieved_at')},
                'payload': json.loads(bytes(row['payload']))}

    def save_structured_facts(self, run_id: str, facts):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM structured_facts WHERE run_id=?', (run_id,))
            db.executemany('INSERT INTO structured_facts (run_id, fact_id, metric, value, payload) VALUES (?, ?, ?, ?, ?)', [
                (run_id, item.fact_id, item.metric, str(item.value), item.model_dump_json()) for item in facts])

    def structured_facts(self, run_id: str, *, page: int | None = None,
                         per_page: int = 100):
        from .contracts import StructuredFact
        limit, offset = self._page_bounds(page, per_page)
        with self.connect() as db:
            query = 'SELECT payload FROM structured_facts WHERE run_id=? ORDER BY metric, payload'
            if limit:
                query += ' LIMIT ? OFFSET ?'
                rows = db.execute(query, (run_id, limit, offset)).fetchall()
            else:
                rows = db.execute(query, (run_id,)).fetchall()
        return [StructuredFact.model_validate_json(row['payload']) for row in rows]

    def save_fact_summary(self, run_id: str, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO fact_summaries (run_id, payload) VALUES (?, ?)',
                       (run_id, json.dumps(payload, sort_keys=True)))

    def fact_summary(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM fact_summaries WHERE run_id=?', (run_id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_comparisons(self, run_id: str, comparisons):
        run = self.get_run(run_id)
        comparisons = [item.model_copy(update={
            'evaluation_run_version': run.version_id,
            'evaluation_total_elapsed_seconds': run.total_elapsed_seconds,
        }) for item in comparisons]
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM comparisons WHERE run_id=?', (run_id,))
            db.executemany('INSERT INTO comparisons (run_id, comparison_id, state, payload) VALUES (?, ?, ?, ?)', [
                (run_id, item.comparison_id, item.state, item.model_dump_json()) for item in comparisons])

    def comparisons(self, run_id: str, *, page: int | None = None,
                    per_page: int = 100):
        from .contracts import FactComparison
        limit, offset = self._page_bounds(page, per_page)
        with self.connect() as db:
            query = 'SELECT payload FROM comparisons WHERE run_id=? ORDER BY state, comparison_id'
            if limit:
                query += ' LIMIT ? OFFSET ?'
                rows = db.execute(query, (run_id, limit, offset)).fetchall()
            else:
                rows = db.execute(query, (run_id,)).fetchall()
        return [FactComparison.model_validate_json(row['payload']) for row in rows]

    def save_comparison_summary(self, run_id: str, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO comparison_summaries (run_id, payload) VALUES (?, ?)',
                       (run_id, json.dumps(payload, sort_keys=True)))

    def comparison_summary(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM comparison_summaries WHERE run_id=?',
                             (run_id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def evaluation_scorecard(self, configuration_hash: str):
        """Return a persisted scorecard snapshot for an exact configuration."""
        with self.connect() as db:
            row = db.execute('SELECT input_hash, calculated_at, payload FROM evaluation_scorecards '
                             'WHERE configuration_hash=?', (configuration_hash,)).fetchone()
        return ({**json.loads(row['payload']), 'input_hash': row['input_hash'],
                 'calculated_at': row['calculated_at']} if row else None)

    def save_evaluation_scorecard(self, configuration_hash: str, input_hash: str, payload: dict):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO evaluation_scorecards
                (configuration_hash, input_hash, calculated_at, payload) VALUES (?, ?, ?, ?)''',
                       (configuration_hash, input_hash, datetime.now(UTC).isoformat(),
                        json.dumps(payload, sort_keys=True)))

    def evaluation_scale_verdict(self, pair_hash: str, prompt_version: str,
                                 configuration_hash: str, actual_model: str):
        with self.connect() as db:
            row = db.execute('''SELECT payload FROM evaluation_scale_verdicts WHERE pair_hash=?
                AND prompt_version=? AND configuration_hash=? AND actual_model=?''',
                             (pair_hash, prompt_version, configuration_hash, actual_model)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_evaluation_scale_verdict(self, pair_hash: str, prompt_version: str,
                                      configuration_hash: str, actual_model: str, payload: dict):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO evaluation_scale_verdicts
                (pair_hash, prompt_version, configuration_hash, actual_model, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)''',
                       (pair_hash, prompt_version, configuration_hash, actual_model,
                        json.dumps(payload, sort_keys=True), datetime.now(UTC).isoformat()))

    def finding_batch(self, request_hash: str, prompt_version: str,
                      configuration_hash: str, actual_model: str):
        with self.connect() as db:
            row = db.execute('''SELECT payload FROM finding_batches WHERE request_hash=?
                AND prompt_version=? AND configuration_hash=? AND actual_model=?''',
                             (request_hash, prompt_version, configuration_hash,
                              actual_model)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_finding_batch(self, request_hash: str, prompt_version: str,
                           configuration_hash: str, actual_model: str, payload: dict):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO finding_batches
                (request_hash, prompt_version, configuration_hash, actual_model, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)''',
                       (request_hash, prompt_version, configuration_hash, actual_model,
                        json.dumps(payload, sort_keys=True), datetime.now(UTC).isoformat()))

    def save_finding_summary(self, run_id: str, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO finding_summaries (run_id, payload) VALUES (?, ?)',
                       (run_id, json.dumps(payload, sort_keys=True)))

    def finding_summary(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM finding_summaries WHERE run_id=?', (run_id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_chunks(self, run_id: str, chunks: list[TextChunk]):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM chunk_ranges WHERE run_id=?', (run_id,))
            db.execute('DELETE FROM chunks WHERE run_id=?', (run_id,))
            db.executemany('INSERT INTO chunks (run_id, chunk_id, section_id, payload) VALUES (?, ?, ?, ?)', [
                (run_id, item.chunk_id, item.section_id, item.model_dump_json()) for item in chunks])
            ranges = []
            for item in chunks:
                ranges.append((run_id, item.chunk_id, 'core', 0,
                               item.core_range.start_line, item.core_range.end_line))
                ranges.extend((run_id, item.chunk_id, 'context', ordinal,
                               source_range.start_line, source_range.end_line)
                              for ordinal, source_range in enumerate(item.context_ranges))
            db.executemany('''INSERT INTO chunk_ranges
                (run_id, chunk_id, range_kind, ordinal, start_line, end_line) VALUES (?, ?, ?, ?, ?, ?)''',
                           ranges)

    def chunks(self, run_id: str, *, page: int | None = None,
               per_page: int = 100) -> list[TextChunk]:
        limit, offset = self._page_bounds(page, per_page)
        with self.connect() as db:
            query = ('SELECT payload FROM chunks WHERE run_id=? ORDER BY '
                     'json_extract(payload, "$.core_range.start_line"), chunk_id')
            if limit:
                query += ' LIMIT ? OFFSET ?'
                rows = db.execute(query, (run_id, limit, offset)).fetchall()
            else:
                rows = db.execute(query, (run_id,)).fetchall()
        return [TextChunk.model_validate_json(row['payload']) for row in rows]

    def chunk(self, run_id: str, chunk_id: str) -> TextChunk:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM chunks WHERE run_id=? AND chunk_id=?',
                             (run_id, chunk_id)).fetchone()
        if not row:
            raise FileNotFoundError(chunk_id)
        return TextChunk.model_validate_json(row['payload'])

    def save_exploration_action(self, run_id: str, action_id: str, stage: str,
                                sequence: int, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO exploration_actions '
                       '(run_id, action_id, stage, sequence, payload) VALUES (?, ?, ?, ?, ?)',
                       (run_id, action_id, stage, sequence, self._diagnostic_payload(payload)))

    def exploration_actions(self, run_id: str, stage: str, *, limit: int = 100):
        with self.connect() as db:
            rows = db.execute('SELECT action_id, payload FROM exploration_actions WHERE run_id=? '
                              'AND stage=? ORDER BY sequence, action_id LIMIT ?',
                              (run_id, stage, min(max(limit, 1), 100))).fetchall()
        return [{'action_id': row['action_id'], **self._read_diagnostic_payload(row['payload'])} for row in rows]

    @staticmethod
    def _diagnostic_payload(payload: dict):
        encoded = json.dumps(payload, sort_keys=True).encode()
        # Diagnostics can contain retained visible source. Keep small records easy
        # to inspect, but avoid multiplying database size for large provider bodies.
        return sqlite3.Binary(b'z:' + zlib.compress(encoded)) if len(encoded) > 2048 else encoded.decode()

    @staticmethod
    def _read_diagnostic_payload(payload):
        raw = bytes(payload) if isinstance(payload, bytes) else str(payload).encode()
        if raw.startswith(b'z:'):
            raw = zlib.decompress(raw[2:])
        return json.loads(raw)

    def save_performance_summary(self, run_id: str, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO performance_summaries (run_id, payload) VALUES (?, ?)',
                       (run_id, json.dumps(payload, sort_keys=True)))

    def performance_summary(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM performance_summaries WHERE run_id=?', (run_id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_retrieval_benchmark(self, run_id: str, payload: dict):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO retrieval_benchmarks (run_id, payload) VALUES (?, ?)',
                       (run_id, json.dumps(payload, sort_keys=True)))

    def retrieval_benchmark(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM retrieval_benchmarks WHERE run_id=?', (run_id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def record_route_measurement(self, run_id: str, *, route: str, latency_ms: float,
                                 payload_bytes: int):
        """Keep the latest bounded reader-page measurement alongside run metrics."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM runs WHERE run_id=?', (run_id,)).fetchone():
                raise FileNotFoundError(run_id)
            row = db.execute('SELECT payload FROM performance_summaries WHERE run_id=?', (run_id,)).fetchone()
            payload = json.loads(row['payload']) if row else {}
            payload['reader_route'] = {'route': route, 'latency_ms': round(latency_ms, 3),
                                       'payload_bytes': payload_bytes}
            db.execute('INSERT OR REPLACE INTO performance_summaries (run_id, payload) VALUES (?, ?)',
                       (run_id, json.dumps(payload, sort_keys=True)))

    @staticmethod
    def _page_bounds(page: int | None, per_page: int):
        if page is None:
            return None, 0
        limit = min(max(per_page, 1), 100)
        return limit, (max(page, 1) - 1) * limit

    def outline_batch(self, source_range_hash: str, prompt_version: str,
                      configuration_hash: str, actual_model: str):
        with self.connect() as db:
            row = db.execute('''SELECT payload FROM outline_batches WHERE source_range_hash=?
                AND prompt_version=? AND configuration_hash=? AND actual_model=?''',
                             (source_range_hash, prompt_version, configuration_hash,
                              actual_model)).fetchone()
        return json.loads(row['payload']) if row else None

    def save_outline_batch(self, source_range_hash: str, prompt_version: str,
                           configuration_hash: str, actual_model: str, payload: dict):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO outline_batches
                (source_range_hash, prompt_version, configuration_hash, actual_model, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)''', (source_range_hash, prompt_version,
                configuration_hash, actual_model, json.dumps(payload, sort_keys=True),
                datetime.now(UTC).isoformat()))
