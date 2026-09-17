import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

from profitlab.contracts.base import RunManifest, StableID

ID = TypeAdapter(StableID)


class Repository:
    """Transactional index of immutable, atomically published run artifacts."""

    def __init__(self, data_dir: Path):
        self.root = data_dir
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / 'index.sqlite3'
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise ValueError(f'Unsupported storage schema version: {version}')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    artifact_id TEXT NOT NULL, path TEXT NOT NULL, hash TEXT NOT NULL,
                    media_type TEXT NOT NULL, contract TEXT,
                    PRIMARY KEY(run_id, artifact_id));
                PRAGMA user_version=1;
            ''')

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def create_run(self, manifest: RunManifest):
        run_dir = self.root / 'runs' / manifest.run_id
        run_dir.parent.mkdir(exist_ok=True)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                run_dir.mkdir()
            except FileExistsError:
                raise ValueError(f'Run {manifest.run_id} already exists; choose a fresh run ID.')
            db.execute('INSERT INTO runs VALUES (?, ?)',
                       (manifest.run_id, manifest.created_at.isoformat()))
            self._put(db, manifest.run_id, 'manifest', manifest.model_dump_json(indent=2).encode(),
                      'application/json', 'RunManifest')

    def _put(self, db, run_id, artifact_id, content, media_type, contract=None):
        ID.validate_python(run_id)
        ID.validate_python(artifact_id)
        if not db.execute('SELECT 1 FROM runs WHERE run_id=?', (run_id,)).fetchone():
            raise FileNotFoundError(run_id)
        digest = hashlib.sha256(content).hexdigest()
        old = db.execute('SELECT * FROM artifacts WHERE run_id=? AND artifact_id=?',
                         (run_id, artifact_id)).fetchone()
        if old:
            if old['hash'] != digest or old['media_type'] != media_type or old['contract'] != contract:
                raise ValueError('Immutable artifact cannot be overwritten with different content')
            self._read(old)
            return
        suffix = '.json' if media_type == 'application/json' else '.html'
        relative = Path('runs') / run_id / (artifact_id + suffix)
        target = self.root / relative
        if target.exists():
            if target.read_bytes() != content:
                raise ValueError('Existing unindexed artifact has different content')
        else:
            fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.artifact-')
            try:
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, target)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        db.execute('INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?)',
                   (run_id, artifact_id, str(relative), digest, media_type, contract))

    def put(self, run_id: str, artifact_id: str, content: bytes,
            media_type: str = 'application/json'):
        if media_type not in ('application/json', 'text/html'):
            raise ValueError('Unsupported artifact media type')
        if media_type == 'application/json':
            json.loads(content)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._put(db, run_id, artifact_id, content, media_type)

    def save_contract(self, run_id: str, artifact_id: str, model: BaseModel):
        # Revalidate even objects constructed with model_construct or model_copy.
        model = type(model).model_validate(model.model_dump(mode='json'))
        primary_fields = {'RunManifest': 'run_id', 'FilingRecord': 'filing_id',
                          'SourceBlock': 'block_id', 'TableCell': 'cell_id', 'Chunk': 'chunk_id',
                          'EvidenceRef': 'evidence_id', 'FactCandidate': 'candidate_id',
                          'CandidateGroup': 'group_id', 'AnnualObservation': 'observation_id',
                          'Calculation': 'calculation_id', 'Report': 'report_id',
                          'TraceEvent': 'event_id', 'ScreeningDecision': 'decision_id'}
        field = primary_fields.get(type(model).__name__)
        if field and field != 'run_id' and getattr(model, field) != artifact_id:
            raise ValueError('Artifact ID must match the contract stable ID')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._validate_references(db, run_id, model)
            self._put(db, run_id, artifact_id, model.model_dump_json(indent=2).encode(),
                      'application/json', type(model).__name__)

    def _validate_references(self, db, run_id, model):
        from profitlab.contracts.facts import CandidateGroup
        from profitlab.contracts.reports import Report
        from profitlab.contracts.sources import EvidenceRef

        reference_fields = {
            'filing_id': 'FilingRecord', 'block_id': 'SourceBlock',
            'block_ids': 'SourceBlock', 'primary_block_ids': 'SourceBlock',
            'overlap_block_ids': 'SourceBlock', 'cell_ids': 'TableCell',
            'header_cell_ids': 'TableCell', 'year_cell_ids': 'TableCell',
            'unit_cell_ids': 'TableCell', 'chunk_id': 'Chunk',
            'evidence_ids': 'EvidenceRef', 'candidate_ids': 'FactCandidate',
            'selected_id': 'FactCandidate', 'fact_ids': 'FactCandidate',
            'table_fact_ids': 'FactCandidate', 'calculation_ids': 'Calculation',
            'table_calculation_ids': 'Calculation', 'source_index': 'EvidenceRef',
            'amendment_of': 'FilingRecord', 'latest_comparative_id': 'FactCandidate',
        }

        def fetch(identifier, expected=None):
            row = db.execute('SELECT * FROM artifacts WHERE run_id=? AND artifact_id=?',
                             (run_id, identifier)).fetchone()
            if row is None or (expected and row['contract'] != expected):
                raise ValueError(f'Unknown or incompatible source reference: {identifier}')
            return json.loads(self._read(row))

        def visit(value):
            if isinstance(value, BaseModel):
                for field in type(value).model_fields:
                    item = getattr(value, field)
                    if field in reference_fields and item is not None:
                        for identifier in item if isinstance(item, list) else [item]:
                            if reference_fields[field] != type(value).__name__:
                                fetch(identifier, reference_fields[field])
                    if field in ('input_ids', 'artifact_ids', 'request_artifact_id',
                                 'result_artifact_id') and item is not None:
                        for identifier in item if isinstance(item, list) else [item]:
                            fetch(identifier)
                    if field == 'selected_facts':
                        for identifier in item.values():
                            fetch(identifier, 'FactCandidate')
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)
        visit(model)
        if isinstance(model, EvidenceRef):
            block = fetch(model.block_id, 'SourceBlock')
            filing = fetch(model.filing_id, 'FilingRecord')
            if (block['filing_id'] != model.filing_id or
                    model.local_anchor != f'#block-{model.block_id}' or
                    filing['source_hash'] != model.source_hash or
                    block['table_id'] != model.table_id):
                raise ValueError('Evidence source identity, hash or anchor mismatch')
            if any(segment not in block['text'] for segment in model.exact_segments):
                raise ValueError('Evidence quote does not match source')
            for cell_id in model.cell_ids:
                if fetch(cell_id, 'TableCell')['table_id'] != model.table_id:
                    raise ValueError('Cell belongs to a different source table')
        if isinstance(model, CandidateGroup):
            for identifier in model.candidate_ids:
                candidate = fetch(identifier, 'FactCandidate')
                for field in ('metric', 'period', 'unit', 'currency', 'scope', 'attribution',
                              'share_class', 'basis'):
                    if candidate[field] != model.model_dump(mode='json')[field]:
                        raise ValueError('Candidate does not match group comparison key')
        if isinstance(model, Report) and model.validation_status == 'valid':
            selected = set()
            for row in db.execute("SELECT * FROM artifacts WHERE run_id=? AND contract=?",
                                  (run_id, 'CandidateGroup')):
                selected.add(json.loads(self._read(row))['selected_id'])
            if not set(model.table_fact_ids) <= selected:
                raise ValueError('Final report references unselected candidates')

    def _read(self, row):
        content = (self.root / row['path']).read_bytes()
        if hashlib.sha256(content).hexdigest() != row['hash']:
            raise ValueError('Artifact hash mismatch')
        return content

    def read(self, run_id, artifact_id):
        ID.validate_python(run_id)
        ID.validate_python(artifact_id)
        with self.connect() as db:
            row = db.execute('SELECT * FROM artifacts WHERE run_id=? AND artifact_id=?',
                             (run_id, artifact_id)).fetchone()
            if row is None:
                raise FileNotFoundError(artifact_id)
            return self._read(row)

    def artifacts(self, run_id):
        ID.validate_python(run_id)
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM artifacts WHERE run_id=? ORDER BY artifact_id', (run_id,))]

    def manifest(self, run_id):
        snapshots = [a for a in self.artifacts(run_id)
                     if a['artifact_id'].startswith('manifest-screen-')]
        if snapshots:
            return max((RunManifest.model_validate_json(self.read(run_id, a['artifact_id']))
                        for a in snapshots), key=lambda m: m.updated_at)
        # Stage snapshots preserve the original immutable manifest.
        for stage in ('probe', 'chunk', 'parse', 'download', 'discovery'):
            try:
                return RunManifest.model_validate_json(self.read(run_id, 'manifest-' + stage))
            except FileNotFoundError:
                pass
        return RunManifest.model_validate_json(self.read(run_id, 'manifest'))

    def recent(self):
        with self.connect() as db:
            ids = [row['run_id'] for row in db.execute(
                'SELECT run_id FROM runs ORDER BY created_at DESC')]
        return [self.manifest(identifier) for identifier in ids]
