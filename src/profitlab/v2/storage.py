"""Fresh SQLite namespace for V2 runs; V1 storage is never opened here."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .canonical import CanonicalDocument
from .contracts import STAGE_NAMES, CanonicalDocumentRef, PipelineEvent, StageSnapshot, V2Run


class V2Repository:
    def __init__(self, data_dir: Path):
        self.root = data_dir / 'v2'
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'profitlab-v2.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 2, 3):
                raise ValueError(f'Unsupported V2 storage schema version: {version}')
            if version == 0:
                db.executescript(self._schema())
            elif version == 2:
                db.executescript(self._migrate_2_to_3())

    @staticmethod
    def _schema():
        return '''
            CREATE TABLE runs (
                run_id TEXT PRIMARY KEY, ticker TEXT NOT NULL, mode TEXT NOT NULL,
                status TEXT NOT NULL, selected_stage TEXT NOT NULL,
                cancellation_requested INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL, summary TEXT NOT NULL);
            CREATE TABLE stages (
                run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
                stage TEXT NOT NULL, position INTEGER NOT NULL, status TEXT NOT NULL,
                completed_work INTEGER NOT NULL, total_work INTEGER,
                started_at TEXT, finished_at TEXT, elapsed_seconds REAL NOT NULL,
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
            PRAGMA user_version=3;
        '''

    @staticmethod
    def _migrate_2_to_3():
        return '''
            CREATE TABLE canonical_documents (
                run_id TEXT NOT NULL, document_id TEXT NOT NULL, filing_id TEXT NOT NULL,
                source_hash TEXT NOT NULL, line_count INTEGER NOT NULL, raw_html BLOB NOT NULL,
                visible_html BLOB NOT NULL, canonical_json TEXT NOT NULL,
                PRIMARY KEY(run_id, document_id), UNIQUE(run_id, filing_id));
            CREATE INDEX canonical_documents_run_filing ON canonical_documents(run_id, filing_id);
            PRAGMA user_version=3;
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
            db.execute('INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', (
                run.run_id, run.ticker, run.mode, run.status, run.selected_stage,
                run.cancellation_requested, run.created_at.isoformat(), run.updated_at.isoformat(),
                run.summary,
            ))
            for position, stage in enumerate(STAGE_NAMES, 1):
                snapshot = StageSnapshot(run_id=run.run_id, stage=stage, position=position)
                self._write_stage(db, snapshot)
            self._event(db, run.run_id, None, 'run_created', run.status,
                        'Fresh V2 run created.')

    @staticmethod
    def _write_stage(db, stage: StageSnapshot):
        values = stage.model_dump(mode='json')
        db.execute('''INSERT OR REPLACE INTO stages VALUES (
            :run_id, :stage, :position, :status, :completed_work, :total_work,
            :started_at, :finished_at, :elapsed_seconds, :summary, :limitation,
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
        return V2Run.model_validate(dict(row))

    def recent(self, limit: int = 50):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM runs ORDER BY created_at DESC LIMIT ?',
                              (min(limit, 100),)).fetchall()
        return [V2Run.model_validate(dict(row)) for row in rows]

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
            changed = db.execute('UPDATE runs SET status=?, summary=?, updated_at=? '
                                 'WHERE run_id=?', (status, summary, now, run_id)).rowcount
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
