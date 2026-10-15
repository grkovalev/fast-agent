"""Typed, indexed persistence for Findings phases."""
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
    PhaseAccounting,
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
CREATE TABLE findings_attempts (
 attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id TEXT NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE, payload TEXT NOT NULL);
CREATE INDEX findings_attempts_run ON findings_attempts(run_id, attempt_id);
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

    def _checkpoint_accounting(self, db, run_id, phase, completed, *, repair=False):
        row = db.execute('SELECT payload FROM findings_steps WHERE run_id=? AND phase=?', (run_id, phase)).fetchone()
        if not row:
            return  # Standalone component tests do not own an active orchestration attempt.
        step = FindingsStepResult.model_validate_json(row['payload'])
        if step.status != 'running':
            return
        summary_row = db.execute('SELECT payload FROM findings_run_results WHERE run_id=?', (run_id,)).fetchone()
        if not summary_row:
            return
        summary = FindingsRunSummary.model_validate_json(summary_row['payload'])
        if summary.status != 'running':
            return
        name = {FindingsPhase.ASSIGN:'jev_assign', FindingsPhase.ATTACH:'jev_attach',
                FindingsPhase.RANK:'jev_rank', FindingsPhase.CONVERT:'llm_repair' if repair else 'llm_conversion'}[phase]
        old = getattr(summary, name)
        usage = old.usage.model_dump() if old.usage else {'input_tokens':0, 'output_tokens':0}
        response = completed.response
        if not completed.cached and response.usage:
            for key in usage:
                usage[key] += getattr(response.usage, key)
        value = PhaseAccounting(planned=old.planned + 1,
            dispatched=old.dispatched + int(not completed.cached), completed=old.completed + int(not completed.cached),
            cached=old.cached + int(completed.cached), usage=usage,
            elapsed_seconds=old.elapsed_seconds + completed.elapsed_seconds,
            models=sorted({*old.models, response.model}))
        step = step.model_copy(update={'accounting': value,
            'reason':'Successful batches checkpointed; in-flight call accounting is unavailable after a hard interruption.'})
        db.execute('UPDATE findings_steps SET payload=? WHERE run_id=? AND phase=?', (step.model_dump_json(), run_id, phase))
        summary = summary.model_copy(update={name: value})
        db.execute('UPDATE findings_run_results SET payload=? WHERE run_id=?', (summary.model_dump_json(), run_id))

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
            self._checkpoint_accounting(db, run_id, identity.phase, completed)

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
            self._checkpoint_accounting(db, run_id, FindingsPhase.CONVERT, completed,
                repair=bool(completed.request.repair_bundle_ids))
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

    def start_findings_attempt(self, run_id, result):
        """Current phase projections start fresh; exact successful batch caches survive."""
        if result.status != 'running' or result.sealed or result.steps:
            raise ValueError('A new attempt starts with an empty running summary')
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM findings_steps WHERE run_id=?', (run_id,))
            db.execute('DELETE FROM findings_artifacts WHERE run_id=?', (run_id,))
            db.execute('INSERT OR REPLACE INTO findings_run_results VALUES (?, ?)', (run_id, result.model_dump_json()))

    def save_findings_progress(self, run_id, step):
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO findings_steps VALUES (?, ?, ?, ?, ?)',
                (run_id, step.phase, step.input_hash, step.policy_hash, step.model_dump_json()))

    def interrupt_findings(self, run_id):
        summary = self.findings_run_result(run_id)
        if summary is None or summary.status != 'running':
            return
        steps = [self.findings_step(run_id, phase) for phase in FindingsPhase]
        steps = [step for step in steps if step is not None]
        for index, step in enumerate(steps):
            if step.status == 'running':
                step = step.model_copy(update={'status':'interrupted',
                    'reason':'Worker stopped; successful batch usage retained. In-flight call accounting is unknown.'})
                self.save_findings_progress(run_id, step)
                steps[index] = step
        result = summary.model_copy(update={'status':'interrupted', 'steps':steps,
            'limitation':'Resume exact successful checkpoints. In-flight request/usage cannot be recovered after process loss.'})
        self.save_findings_terminal(run_id, result)

    def require_findings_seal(self, run_id):
        result = self.findings_run_result(run_id)
        if (self.stage(run_id, 'findings').status not in ('completed', 'partial') or
                result is None or not result.sealed or result.status not in ('completed', 'partial')):
            raise ValueError('Findings must have a completed or partial sealed result before independent data begins.')

    @staticmethod
    def _accumulate_attempt(db, run_id, result):
        """Keep paid work from failed/resumed attempts; caches never erase usage."""
        names = ('jev_assign', 'jev_attach', 'jev_rank', 'llm_conversion', 'llm_repair')
        previous = [FindingsRunSummary.model_validate_json(r['payload']) for r in db.execute(
            'SELECT payload FROM findings_attempts WHERE run_id=? ORDER BY attempt_id', (run_id,))]
        db.execute('INSERT INTO findings_attempts (run_id, payload) VALUES (?, ?)', (run_id, result.model_dump_json()))
        updates = {}
        for name in names:
            accounts = [getattr(r, name) for r in [*previous, result]]
            usage = [a.usage for a in accounts if a.usage is not None]
            updates[name] = PhaseAccounting(**{
                key: sum(getattr(a, key) for a in accounts)
                for key in ('planned', 'dispatched', 'completed', 'cached', 'failed', 'omitted', 'elapsed_seconds')},
                models=sorted({m for a in accounts for m in a.models}),
                usage=({'input_tokens': sum(u.input_tokens for u in usage),
                        'output_tokens': sum(u.output_tokens for u in usage)} if usage else None))
        return FindingsRunSummary.model_validate(result.model_copy(update=updates).model_dump(mode='json'))

    def save_findings_terminal(self, run_id, result):
        if result.sealed or result.status not in ('failed', 'cancelled', 'interrupted'):
            raise ValueError('Only unsealed failures finish outside atomic publication')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            total = self._accumulate_attempt(db, run_id, result)
            db.execute('INSERT OR REPLACE INTO findings_run_results VALUES (?, ?)', (run_id, total.model_dump_json()))
        return total

    def findings_saved_batches(self, run_id, phase, *, page=1):
        limit, offset = self._page_bounds(page, 20)
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM findings_checkpoints WHERE run_id=? AND phase=? '
                'ORDER BY identity_key, batch_id LIMIT ? OFFSET ?', (run_id, phase, limit, offset)).fetchall()
        model = CompletedConversionBatch if phase == FindingsPhase.CONVERT else CompletedJevBatch
        return [model.model_validate_json(r['payload']) for r in rows]

    def seal_findings(self, run_id, result, publications):
        """Publish rows, selected provenance, Validate, Seal and summary together."""
        result = FindingsRunSummary.model_validate_json(result.model_dump_json())
        publications = [FindingPublicationProvenance.model_validate_json(p.model_dump_json()) for p in publications]
        if not result.sealed or result.published_finding_ids != [p.finding.finding_id for p in publications]:
            raise ValueError('Publication must exactly match the sealed summary')
        self.get_run(run_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT cancellation_requested FROM runs WHERE run_id=?', (run_id,)).fetchone()[0]:
                raise ValueError('Cancelled Findings cannot seal')
            result = self._accumulate_attempt(db, run_id, result)
            db.execute('DELETE FROM findings WHERE run_id=?', (run_id,))
            db.executemany('INSERT INTO findings VALUES (?, ?, ?)',
                [(run_id, p.finding.finding_id, p.finding.model_dump_json()) for p in publications])
            db.execute('DELETE FROM findings_artifacts WHERE run_id=? AND phase=?', (run_id, FindingsPhase.VALIDATE))
            db.executemany('INSERT INTO findings_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)',
                [(run_id, FindingsPhase.VALIDATE, 'publication', p.concept.value, p.bundle_id, i, p.model_dump_json())
                 for i, p in enumerate(publications)])
            for step in result.steps:
                db.execute('INSERT OR REPLACE INTO findings_steps VALUES (?, ?, ?, ?, ?)',
                    (run_id, step.phase, step.input_hash, step.policy_hash, step.model_dump_json()))
            db.execute('INSERT OR REPLACE INTO findings_run_results VALUES (?, ?)', (run_id, result.model_dump_json()))
        return result

    def finding_summary(self, run_id):
        """Public accounting projection of the typed run summary; no legacy fallback."""
        result = self.findings_run_result(run_id)
        if result is None:
            return None
        names = ('jev_assign', 'jev_attach', 'jev_rank', 'llm_conversion', 'llm_repair')
        phases = {name: getattr(result, name).model_dump(mode='json') for name in names}
        return result.model_dump(mode='json') | {
            'provider_requests': sum(p['dispatched'] for p in phases.values()),
            'cached_batches': sum(p['cached'] for p in phases.values()),
            'phases': phases,
            'accounting_scope': ('current attempt while running' if result.status == 'running' else
                                 'accumulated terminal attempts, with cache reuse separate'),
        }

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
