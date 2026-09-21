"""Fresh SQLite namespace for V2 runs; V1 storage is never opened here."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .canonical import CanonicalDocument
from .contracts import (
    STAGE_NAMES,
    CanonicalDocumentRef,
    OutlineSection,
    PipelineEvent,
    StageSnapshot,
    TextChunk,
    V2Run,
)


class V2Repository:
    def __init__(self, data_dir: Path):
        self.root = data_dir / 'v2'
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'profitlab-v2.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 2, 3, 4, 5, 6):
                raise ValueError(f'Unsupported V2 storage schema version: {version}')
            if version == 0:
                db.executescript(self._schema())
            elif version == 2:
                db.executescript(self._migrate_2_to_3())
                db.executescript(self._migrate_3_to_4())
                db.executescript(self._migrate_4_to_5())
                db.executescript(self._migrate_5_to_6())
            elif version == 3:
                db.executescript(self._migrate_3_to_4())
                db.executescript(self._migrate_4_to_5())
                db.executescript(self._migrate_5_to_6())
            elif version == 4:
                db.executescript(self._migrate_4_to_5())
                db.executescript(self._migrate_5_to_6())
            elif version == 5:
                db.executescript(self._migrate_5_to_6())

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
            PRAGMA user_version=6;
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

    @staticmethod
    def _migrate_3_to_4():
        return '''
            CREATE TABLE outline_batches (
                source_range_hash TEXT NOT NULL, prompt_version TEXT NOT NULL,
                configuration_hash TEXT NOT NULL, actual_model TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(source_range_hash, prompt_version, configuration_hash, actual_model));
            PRAGMA user_version=4;
        '''

    @staticmethod
    def _migrate_4_to_5():
        return '''
            CREATE INDEX chunk_ranges_run_chunk ON chunk_ranges(run_id, chunk_id, range_kind, ordinal);
            PRAGMA user_version=5;
        '''

    @staticmethod
    def _migrate_5_to_6():
        return '''
            CREATE TABLE chunk_score_batches (source_range_hash TEXT NOT NULL,
                prompt_version TEXT NOT NULL, configuration_hash TEXT NOT NULL,
                actual_model TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(source_range_hash, prompt_version, configuration_hash, actual_model));
            CREATE TABLE chunk_score_summaries (run_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            PRAGMA user_version=6;
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

    def outline_sections(self, run_id: str) -> list[OutlineSection]:
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM outline_sections WHERE run_id=? '
                              'ORDER BY start_line, end_line, section_id', (run_id,)).fetchall()
        return [OutlineSection.model_validate_json(row['payload']) for row in rows]

    def save_scores(self, run_id: str, score_kind: str, scores):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM scores WHERE run_id=? AND score_kind=?', (run_id, score_kind))
            db.executemany('INSERT INTO scores (run_id, score_kind, item_id, payload) VALUES (?, ?, ?, ?)', [
                (run_id, score_kind, item.item_id, item.model_dump_json()) for item in scores])

    def scores(self, run_id: str, score_kind: str):
        from .contracts import ScoredItem

        with self.connect() as db:
            rows = db.execute('SELECT payload FROM scores WHERE run_id=? AND score_kind=? '
                              'ORDER BY item_id', (run_id, score_kind)).fetchall()
        return [ScoredItem.model_validate_json(row['payload']) for row in rows]

    def chunk_score_batch(self, source_range_hash: str, prompt_version: str,
                          configuration_hash: str, actual_model: str):
        with self.connect() as db:
            row = db.execute('''SELECT payload FROM chunk_score_batches WHERE source_range_hash=?
                AND prompt_version=? AND configuration_hash=? AND actual_model=?''',
                             (source_range_hash, prompt_version, configuration_hash,
                              actual_model)).fetchone()
        return json.loads(row['payload']) if row else None

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

    def chunks(self, run_id: str) -> list[TextChunk]:
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM chunks WHERE run_id=? ORDER BY '
                              'json_extract(payload, "$.core_range.start_line"), chunk_id',
                              (run_id,)).fetchall()
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
                       (run_id, action_id, stage, sequence, json.dumps(payload, sort_keys=True)))

    def exploration_actions(self, run_id: str, stage: str):
        with self.connect() as db:
            rows = db.execute('SELECT action_id, payload FROM exploration_actions WHERE run_id=? '
                              'AND stage=? ORDER BY sequence, action_id', (run_id, stage)).fetchall()
        return [{'action_id': row['action_id'], **json.loads(row['payload'])} for row in rows]

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
