"""Fresh SQLite namespace for V3. It has no foreign keys into V2."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from profitlab.v2.canonical import CanonicalDocument

from .contracts import (
    AnswerCandidate,
    CampaignReview,
    CampaignRun,
    DevelopmentCampaign,
    DevelopmentLedgerReport,
    EvidenceEdge,
    EvidenceNode,
    ExperimentManifest,
    ExplorationAction,
    GraphPath,
    RubricReport,
)


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
            # G6 records only post-seal reviewer inputs and deterministic results.
            # It is intentionally not readable by graph construction services.
            db.execute('CREATE TABLE IF NOT EXISTS rubric_cohorts (cohort_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS rubric_reports (cohort_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            # G6b is separate from the held-out G6c rubric tables so neither
            # contract can be mistaken for the other in inspection or scoring.
            db.execute('CREATE TABLE IF NOT EXISTS development_cohorts (cohort_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS development_ledger_reports (cohort_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            # G6b.1 pre-run campaign state is intentionally separate from both
            # post-seal G6b ledgers and held-out G6c reports.
            db.execute('CREATE TABLE IF NOT EXISTS development_campaigns (campaign_id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS campaign_runs (run_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL, '
                       'ticker TEXT NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS campaign_reviews (review_id TEXT PRIMARY KEY, campaign_run_id TEXT NOT NULL UNIQUE, '
                       'payload TEXT NOT NULL)')

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

    def save_rubric_report(self, report: RubricReport):
        """Append-only cohort identity plus its deterministic post-seal score."""
        with self.connect() as db:
            db.execute('INSERT INTO rubric_cohorts VALUES (?, ?)',
                       (report.cohort.cohort_id, self._dump(report.cohort)))
            db.execute('INSERT INTO rubric_reports VALUES (?, ?)',
                       (report.cohort.cohort_id, self._dump(report)))

    def rubric_report(self, cohort_id: str) -> RubricReport:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM rubric_reports WHERE cohort_id=?', (cohort_id,)).fetchone()
        if not row:
            raise FileNotFoundError(cohort_id)
        return RubricReport.model_validate_json(row['payload'])

    def rubric_reports(self):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM rubric_reports').fetchall()
        return sorted((RubricReport.model_validate_json(row['payload']) for row in rows),
                      key=lambda report: report.cohort.created_at, reverse=True)

    def save_development_ledger_report(self, report: DevelopmentLedgerReport):
        with self.connect() as db:
            db.execute('INSERT INTO development_cohorts VALUES (?, ?)',
                       (report.cohort.cohort_id, self._dump(report.cohort)))
            db.execute('INSERT INTO development_ledger_reports VALUES (?, ?)',
                       (report.cohort.cohort_id, self._dump(report)))

    def development_ledger_report(self, cohort_id: str) -> DevelopmentLedgerReport:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM development_ledger_reports WHERE cohort_id=?', (cohort_id,)).fetchone()
        if not row:
            raise FileNotFoundError(cohort_id)
        return DevelopmentLedgerReport.model_validate_json(row['payload'])

    def development_ledger_reports(self):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM development_ledger_reports').fetchall()
        return sorted((DevelopmentLedgerReport.model_validate_json(row['payload']) for row in rows),
                      key=lambda report: report.cohort.created_at, reverse=True)

    def save_campaign(self, campaign: DevelopmentCampaign):
        with self.connect() as db:
            db.execute('INSERT INTO development_campaigns VALUES (?, ?)',
                       (campaign.campaign_id, self._dump(campaign)))

    def campaigns(self):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM development_campaigns').fetchall()
        return sorted((DevelopmentCampaign.model_validate_json(row['payload']) for row in rows),
                      key=lambda campaign: campaign.created_at, reverse=True)

    def campaign(self, campaign_id: str) -> DevelopmentCampaign:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM development_campaigns WHERE campaign_id=?', (campaign_id,)).fetchone()
        if not row:
            raise FileNotFoundError(campaign_id)
        return DevelopmentCampaign.model_validate_json(row['payload'])

    def create_campaign_run(self, run: CampaignRun):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM campaign_runs WHERE campaign_id=? AND ticker=?',
                              (run.campaign_id, run.ticker)).fetchall()
            if any(CampaignRun.model_validate_json(row['payload']).status in {'queued', 'running'} for row in rows):
                raise ValueError('A campaign run is already active for this ticker.')
            db.execute('INSERT INTO campaign_runs VALUES (?, ?, ?, ?)',
                       (run.run_id, run.campaign_id, run.ticker, self._dump(run)))

    def update_campaign_run(self, run: CampaignRun):
        with self.connect() as db:
            cursor = db.execute('UPDATE campaign_runs SET payload=? WHERE run_id=?',
                                (self._dump(run), run.run_id))
        if not cursor.rowcount:
            raise FileNotFoundError(run.run_id)

    def campaign_run(self, run_id: str) -> CampaignRun:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM campaign_runs WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            raise FileNotFoundError(run_id)
        return CampaignRun.model_validate_json(row['payload'])

    def campaign_runs(self, campaign_id: str | None = None):
        query, parameters = 'SELECT payload FROM campaign_runs', ()
        if campaign_id:
            query += ' WHERE campaign_id=?'
            parameters = (campaign_id,)
        with self.connect() as db:
            rows = db.execute(query, parameters).fetchall()
        return sorted((CampaignRun.model_validate_json(row['payload']) for row in rows),
                      key=lambda run: run.created_at, reverse=True)

    def interrupt_active_campaign_runs(self):
        """A process restart must never make unfinished work look sealed."""
        for run in self.campaign_runs():
            if run.status in {'queued', 'running'}:
                self.update_campaign_run(run.model_copy(update={
                    'status': 'interrupted', 'finished_at': datetime.now(UTC),
                    'error': 'Run interrupted by workspace restart; no sealed result was recorded.',
                }))

    def save_campaign_review(self, review: CampaignReview):
        """Append one immutable, terminal-only review per campaign run."""
        with self.connect() as db:
            if db.execute('SELECT 1 FROM campaign_reviews WHERE campaign_run_id=?',
                          (review.campaign_run_id,)).fetchone():
                raise ValueError('This sealed campaign run already has an immutable review.')
            db.execute('INSERT INTO campaign_reviews VALUES (?, ?, ?)',
                       (review.review_id, review.campaign_run_id, self._dump(review)))

    def campaign_review(self, campaign_run_id: str) -> CampaignReview:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM campaign_reviews WHERE campaign_run_id=?',
                             (campaign_run_id,)).fetchone()
        if not row:
            raise FileNotFoundError(campaign_run_id)
        return CampaignReview.model_validate_json(row['payload'])

    def experiments(self):
        """Return immutable experiment identities, newest first, for the explorer."""
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM experiments').fetchall()
        return sorted((ExperimentManifest.model_validate_json(row['payload']) for row in rows),
                      key=lambda item: item.created_at, reverse=True)

    def inspection(self, experiment_id):
        """Load the persisted graph audit without exposing provider request bodies."""
        with self.connect() as db:
            experiment = db.execute('SELECT payload FROM experiments WHERE experiment_id=?',
                                    (experiment_id,)).fetchone()
            if not experiment:
                raise FileNotFoundError(experiment_id)
            snapshot = db.execute(
                'SELECT payload FROM manifest_snapshots WHERE experiment_id=? '
                'ORDER BY sequence DESC LIMIT 1', (experiment_id,)).fetchone()
            document = db.execute('SELECT canonical_json FROM documents WHERE experiment_id=?',
                                  (experiment_id,)).fetchone()
            actions = db.execute('SELECT payload FROM actions WHERE experiment_id=? ORDER BY rowid',
                                 (experiment_id,)).fetchall()
            nodes = db.execute('SELECT payload FROM nodes WHERE experiment_id=? ORDER BY rowid',
                               (experiment_id,)).fetchall()
            edges = db.execute('SELECT payload FROM edges WHERE experiment_id=? ORDER BY rowid',
                               (experiment_id,)).fetchall()
            paths = db.execute('SELECT payload FROM paths WHERE experiment_id=? ORDER BY rowid',
                               (experiment_id,)).fetchall()
            answers = db.execute('SELECT payload FROM answers WHERE experiment_id=? ORDER BY rowid',
                                 (experiment_id,)).fetchall()
        return {
            'manifest': ExperimentManifest.model_validate_json(
                snapshot['payload'] if snapshot else experiment['payload']),
            'document': CanonicalDocument.model_validate_json(document['canonical_json']),
            'actions': [ExplorationAction.model_validate_json(row['payload']) for row in actions],
            'nodes': [EvidenceNode.model_validate_json(row['payload']) for row in nodes],
            'edges': [EvidenceEdge.model_validate_json(row['payload']) for row in edges],
            'paths': [GraphPath.model_validate_json(row['payload']) for row in paths],
            'answers': [AnswerCandidate.model_validate_json(row['payload']) for row in answers],
        }
