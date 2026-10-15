"""Typed, indexed persistence for prepared Findings phases (not active runtime)."""
import hashlib
import json

from profitlab.providers.jev import validate_response

from .finding_concepts import FindingConcept
from .findings_batching import CompletedJevBatch, PackedJevBatch
from .findings_contracts import (
    CompletedConversionBatch,
    ConceptChunkCandidates,
    ConceptLineAssignment,
    ConversionDiagnostic,
    FindingContextLink,
    FindingContextPool,
    FindingConversionPack,
    FindingEvidenceBundle,
    FindingLineCandidate,
    FindingPublicationProvenance,
    FindingsConversionResult,
    FindingsInputIdentity,
    FindingsPhase,
    FindingsRunSummary,
    FindingsStepResult,
    RankedFindingBundle,
)

# Type owns its storage kind, phase, and occurrence key; arbitrary dicts cannot enter.
ARTIFACTS = {
    ConceptChunkCandidates: ('concept', FindingsPhase.CANDIDATES, 'concept'),
    FindingLineCandidate: ('line', FindingsPhase.CANDIDATES, 'candidate_id'),
    ConceptLineAssignment: ('assignment', FindingsPhase.ASSIGN, 'candidate_id'),
    FindingContextPool: ('context_pool', FindingsPhase.ATTACH, 'concept'),
    FindingContextLink: ('context', FindingsPhase.ATTACH, 'link_id'),
    FindingEvidenceBundle: ('bundle', FindingsPhase.ATTACH, 'bundle_id'),
    RankedFindingBundle: ('rank', FindingsPhase.RANK, 'bundle_id'),
    FindingConversionPack: ('conversion_pack', FindingsPhase.RANK, 'pack_id'),
    ConversionDiagnostic: ('conversion', FindingsPhase.CONVERT, 'bundle_id'),
    FindingsConversionResult: ('conversion_result', FindingsPhase.CONVERT, 'result_id'),
    FindingPublicationProvenance: ('publication', FindingsPhase.VALIDATE, 'bundle_id'),
}

FINDINGS_SCHEMA = '''
CREATE TABLE findings_steps (
 run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 phase TEXT NOT NULL, input_hash TEXT NOT NULL, policy_hash TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(run_id, phase));
CREATE TABLE findings_artifacts (
 run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 phase TEXT NOT NULL, kind TEXT NOT NULL, concept TEXT NOT NULL,
 occurrence_id TEXT NOT NULL, ordinal INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(run_id, phase, kind, ordinal));
CREATE INDEX findings_artifacts_lookup ON findings_artifacts
 (run_id, phase, kind, concept, occurrence_id, ordinal);
CREATE TABLE findings_checkpoints (
 run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
 phase TEXT NOT NULL, identity_key TEXT NOT NULL, batch_id TEXT NOT NULL,
 identity_json TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(run_id, phase, identity_key, batch_id));
CREATE TABLE findings_phase_cache (
 identity_key TEXT NOT NULL, batch_id TEXT NOT NULL, identity_json TEXT NOT NULL,
 payload TEXT NOT NULL, PRIMARY KEY(identity_key, batch_id));
CREATE TABLE findings_run_results (
 run_id TEXT PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE, payload TEXT NOT NULL);
'''


class FindingsStorage:
    def complete_findings_step(self, run_id: str, result: FindingsStepResult, artifacts: list):
        """Replace one exact phase atomically; failed validation leaves prior work intact."""
        result = FindingsStepResult.model_validate_json(result.model_dump_json())
        self.get_run(run_id)
        rows = []
        for ordinal, value in enumerate(artifacts):
            kind, phase, key = ARTIFACTS[type(value)]
            value = type(value).model_validate_json(value.model_dump_json())
            if phase != result.phase:
                raise ValueError('Artifact belongs to a different phase')
            concept = (value.proposal.concept if value.proposal else '') if isinstance(value, ConversionDiagnostic) else getattr(value, 'concept', '')
            rows.append((run_id, phase.value, kind, str(concept), str(getattr(value, key)), ordinal,
                         value.model_dump_json()))
        if result.availability != 'final' or result.status not in ('completed', 'partial', 'skipped'):
            raise ValueError('Atomic phase completion requires a final result')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM findings_artifacts WHERE run_id=? AND phase=?', (run_id, result.phase))
            db.executemany('INSERT INTO findings_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)', rows)
            db.execute('INSERT OR REPLACE INTO findings_steps VALUES (?, ?, ?, ?, ?)',
                (run_id, result.phase, result.input_hash, result.policy_hash, result.model_dump_json()))

    def findings_artifacts(self, run_id: str, model, *, concept: FindingConcept | None = None,
                           occurrence_id: str | None = None, page: int = 1, per_page: int = 100):
        kind, phase, _ = ARTIFACTS[model]
        limit, offset = self._page_bounds(page, per_page)
        query = 'SELECT payload FROM findings_artifacts WHERE run_id=? AND phase=? AND kind=?'
        args = [run_id, phase.value, kind]
        for column, value in [('concept', concept), ('occurrence_id', occurrence_id)]:
            if value is not None:
                query += f' AND {column}=?'
                args.append(str(value))
        with self.connect() as db:
            rows = db.execute(query + ' ORDER BY ordinal LIMIT ? OFFSET ?', (*args, limit, offset)).fetchall()
        return [model.model_validate_json(row['payload']) for row in rows]

    def findings_step(self, run_id: str, phase: FindingsPhase):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM findings_steps WHERE run_id=? AND phase=?',
                             (run_id, phase)).fetchone()
        return FindingsStepResult.model_validate_json(row['payload']) if row else None

    def save_findings_checkpoint(self, run_id: str, identity: FindingsInputIdentity,
                                 completed: CompletedJevBatch):
        self.get_run(run_id)
        if identity.phase not in (FindingsPhase.ASSIGN, FindingsPhase.ATTACH, FindingsPhase.RANK):
            raise ValueError('JEV checkpoints require a JEV phase')
        validate_response(completed.batch.request, completed.response)
        if completed.response.model != identity.model_identity:
            raise ValueError('Checkpoint actual model disagrees with identity')
        key, batch_id = identity.cache_key(), reusable_request_key(completed.batch)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO findings_checkpoints VALUES (?, ?, ?, ?, ?, ?)',
                (run_id, identity.phase, key, batch_id, identity.model_dump_json(), completed.model_dump_json()))
            db.execute('INSERT OR REPLACE INTO findings_phase_cache VALUES (?, ?, ?, ?)',
                (key, batch_id, identity.model_dump_json(), completed.model_dump_json()))

    def findings_checkpoint(self, identity: FindingsInputIdentity, batch: PackedJevBatch, *,
                            run_id: str | None = None):
        # Exact request serialization excludes routes: those are current-run ownership.
        table = 'findings_checkpoints' if run_id else 'findings_phase_cache'
        query = f'SELECT identity_json, payload FROM {table} WHERE identity_key=? AND batch_id=?'
        args = [identity.cache_key(), reusable_request_key(batch)]
        if run_id:
            query += ' AND run_id=? AND phase=?'
            args.extend([run_id, identity.phase])
        with self.connect() as db:
            row = db.execute(query, args).fetchone()
        if not row or FindingsInputIdentity.model_validate_json(row['identity_json']) != identity:
            return None
        saved = CompletedJevBatch.model_validate_json(row['payload'])
        if reusable_request(saved.batch) != reusable_request(batch):
            return None
        validate_response(batch.request, saved.response)
        if saved.response.model != identity.model_identity:
            raise ValueError('Cached actual model disagrees with identity')
        return saved.model_copy(update={'batch': batch, 'cached': True})

    def findings_checkpoints(self, run_id: str, identity: FindingsInputIdentity, *,
                             page: int = 1, per_page: int = 100):
        limit, offset = self._page_bounds(page, per_page)
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM findings_checkpoints WHERE run_id=? '
                'AND phase=? AND identity_key=? ORDER BY batch_id LIMIT ? OFFSET ?',
                (run_id, identity.phase, identity.cache_key(), limit, offset)).fetchall()
        return [CompletedJevBatch.model_validate_json(row['payload']) for row in rows]

    def save_conversion_result(self, run_id, result: FindingsConversionResult):
        """Persist terminal diagnostics including failed/interrupted non-publication."""
        self.get_run(run_id)
        result = FindingsConversionResult.model_validate_json(result.model_dump_json())
        step = result.step
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM findings_artifacts WHERE run_id=? AND phase=?',
                       (run_id, FindingsPhase.CONVERT))
            for ordinal, value in enumerate([*result.diagnostics, result]):
                kind, phase, key = ARTIFACTS[type(value)]
                concept = value.proposal.concept if isinstance(value, ConversionDiagnostic) and value.proposal else ''
                db.execute('INSERT INTO findings_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)',
                    (run_id, phase, kind, str(concept), str(getattr(value, key)), ordinal, value.model_dump_json()))
            db.execute('INSERT OR REPLACE INTO findings_steps VALUES (?, ?, ?, ?, ?)',
                (run_id, step.phase, step.input_hash, step.policy_hash, step.model_dump_json()))

    def save_conversion_checkpoint(self, run_id, completed: CompletedConversionBatch):
        self.get_run(run_id)
        completed = CompletedConversionBatch.model_validate_json(completed.model_dump_json())
        # Requested identity must be pinned to the returned model before reusable caching.
        key = completed.request.cache_key()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('INSERT OR REPLACE INTO findings_checkpoints VALUES (?, ?, ?, ?, ?, ?)',
                (run_id, FindingsPhase.CONVERT, key, key, completed.request.model_dump_json(),
                 completed.model_dump_json()))
            if completed.response.model == completed.request.model:
                db.execute('INSERT OR REPLACE INTO findings_phase_cache VALUES (?, ?, ?, ?)',
                    (key, key, completed.request.model_dump_json(), completed.model_dump_json()))

    def conversion_checkpoint(self, request):
        import json
        key = request.cache_key()
        with self.connect() as db:
            row = db.execute('SELECT payload FROM findings_phase_cache WHERE identity_key=? AND batch_id=?',
                             (key, key)).fetchone()
        if not row:
            return None
        saved = CompletedConversionBatch.model_validate_json(row['payload'])
        if conversion_identity(saved.request) != conversion_identity(request) or saved.response.model != request.model:
            return None
        # Only remap canonical routing IDs from supplied current source/context references.
        refs = {line.source_range.source_hash: line.source_range.document_id
                for b in request.state.selected_bundles for line in [b.source, *b.context]}
        def remap(value):
            if isinstance(value, dict):
                return {k: refs.get(value.get('source_hash'), v) if k == 'document_id' else remap(v)
                        for k, v in value.items()}
            if isinstance(value, list):
                return [remap(x) for x in value]
            return value
        response = type(saved.response).model_validate(remap(json.loads(saved.response.model_dump_json())))
        return saved.model_copy(update={'request': request, 'response': response, 'cached': True})

    def save_findings_run_result(self, run_id: str, result: FindingsRunSummary):
        self.get_run(run_id)
        result = FindingsRunSummary.model_validate_json(result.model_dump_json())
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO findings_run_results VALUES (?, ?)',
                       (run_id, result.model_dump_json()))

    def findings_run_result(self, run_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM findings_run_results WHERE run_id=?', (run_id,)).fetchone()
        return FindingsRunSummary.model_validate_json(row['payload']) if row else None


def reusable_request(batch: PackedJevBatch):
    """Remove only routing IDs from safe request state; all visible content stays exact.

    Occurrence IDs already identify concept/hash/line. Source hashes, line offsets,
    instruction strings and model remain in the key. Responses remap via current routes.
    """
    return reusable_input(batch.request.model_dump(mode='json', exclude_none=True))


def reusable_input(value):
    """Normalize documented local routing fields, preserving exact safe content."""
    local_fields = {'document_id', 'filing_id', 'chunk_id', 'section_id'}
    if isinstance(value, dict):
        return {key: reusable_input(item) for key, item in value.items() if key not in local_fields}
    if isinstance(value, list):
        return [reusable_input(item) for item in value]
    return value


def reusable_request_key(batch: PackedJevBatch):
    return hashlib.sha256(json.dumps(reusable_request(batch), sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def conversion_identity(request):
    """Full safe wire identity; decode embedded state/repair JSON before local-ID removal."""
    value = request.model_dump(mode='json')
    for message in value['body']['messages']:
        if message['role'] == 'user':
            try:
                message['content'] = json.loads(message['content'])
            except ValueError:
                pass
    return reusable_input(value)
