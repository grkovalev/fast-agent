"""Fresh SQLite namespace for V3. It has no foreign keys into V2."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class V3Repository:
    _APPLICATION_ID = 0x56334752  # V3GR

    def __init__(self, data_dir: Path):
        self.root = data_dir / 'evidence-graph-experiment'
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'profitlab-v3.sqlite3'
        new = not self.db_path.exists()
        with self.connect() as db:
            if new:
                db.executescript(self._schema())
            elif db.execute('PRAGMA application_id').fetchone()[0] != self._APPLICATION_ID:
                raise ValueError(f'Unsupported V3 database at {self.db_path}; it was left unchanged.')
            # V3 is an isolated experiment. This additive audit table makes
            # malformed answer proposals inspectable without altering V2 data.
            db.execute('CREATE TABLE IF NOT EXISTS answer_attempts (experiment_id TEXT NOT NULL, '
                       'attempt_id INTEGER PRIMARY KEY AUTOINCREMENT, request TEXT NOT NULL, response TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        try:
            yield db
            db.commit()
        finally:
            db.close()

    @classmethod
    def _schema(cls):
        return f'''PRAGMA application_id={cls._APPLICATION_ID};
        CREATE TABLE experiments (experiment_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE manifest_snapshots (experiment_id TEXT NOT NULL REFERENCES experiments, sequence INTEGER NOT NULL,
          payload TEXT NOT NULL, PRIMARY KEY (experiment_id, sequence));
        CREATE TABLE documents (experiment_id TEXT PRIMARY KEY REFERENCES experiments, payload TEXT NOT NULL,
          raw_html BLOB NOT NULL, visible_html BLOB NOT NULL, canonical_json TEXT NOT NULL);
        CREATE TABLE actions (experiment_id TEXT NOT NULL REFERENCES experiments, action_id TEXT PRIMARY KEY,
          payload TEXT NOT NULL, request TEXT NOT NULL, response TEXT NOT NULL);
        CREATE TABLE nodes (experiment_id TEXT NOT NULL REFERENCES experiments, node_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE edges (experiment_id TEXT NOT NULL REFERENCES experiments, edge_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE paths (experiment_id TEXT NOT NULL REFERENCES experiments, path_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE answers (experiment_id TEXT NOT NULL REFERENCES experiments, answer_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE proposal_cache (request_hash TEXT PRIMARY KEY, payload TEXT NOT NULL);
        '''

    @staticmethod
    def _dump(model):
        return json.dumps(model.model_dump(mode='json'), sort_keys=True)

    def create(self, manifest, document, raw_html: bytes, visible_html: bytes):
        with self.connect() as db:
            db.execute('INSERT INTO experiments VALUES (?, ?)', (manifest.experiment_id, self._dump(manifest)))
            db.execute('INSERT INTO documents VALUES (?, ?, ?, ?, ?)', (manifest.experiment_id, self._dump(document.ref), raw_html, visible_html, self._dump(document)))

    def update_manifest(self, manifest):
        with self.connect() as db:
            # The creation manifest is immutable. Later frontier transitions are
            # append-only snapshots so replay can inspect the original identity.
            sequence = db.execute('SELECT count(*) FROM manifest_snapshots WHERE experiment_id=?',
                                  (manifest.experiment_id,)).fetchone()[0] + 1
            db.execute('INSERT INTO manifest_snapshots VALUES (?, ?, ?)',
                       (manifest.experiment_id, sequence, self._dump(manifest)))

    def save_action(self, action, request, response):
        with self.connect() as db:
            db.execute('INSERT INTO actions VALUES (?, ?, ?, ?, ?)', (action.experiment_id, action.action_id, self._dump(action), json.dumps(request, sort_keys=True), json.dumps(response, sort_keys=True)))

    def save_graph(self, experiment_id, nodes, edges, paths):
        with self.connect() as db:
            for table, values, key in [('nodes', nodes, 'node_id'), ('edges', edges, 'edge_id'), ('paths', paths, 'path_id')]:
                for value in values:
                    db.execute(f'INSERT INTO {table} VALUES (?, ?, ?)',
                               (experiment_id, getattr(value, key), self._dump(value)))

    def save_answer(self, answer):
        with self.connect() as db:
            db.execute('INSERT INTO answers VALUES (?, ?, ?)', (answer.experiment_id, answer.answer_id, self._dump(answer)))

    def save_answer_attempt(self, experiment_id, request, response):
        with self.connect() as db:
            db.execute('INSERT INTO answer_attempts (experiment_id, request, response) VALUES (?, ?, ?)',
                       (experiment_id, json.dumps(request, sort_keys=True), json.dumps(response, sort_keys=True)))

    def cached(self, request_hash):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM proposal_cache WHERE request_hash=?', (request_hash,)).fetchone()
            return json.loads(row['payload']) if row else None

    def cache(self, request_hash, payload):
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO proposal_cache VALUES (?, ?)', (request_hash, json.dumps(payload, sort_keys=True)))
