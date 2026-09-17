"""Controlled download/parse progression using immutable per-filing artifacts."""
import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from profitlab.contracts.sources import SourceBlock, SourceDownload, TableCell
from profitlab.documents.parser import VERSION, parse_source
from profitlab.sec.client import SECClient, SECError
from profitlab.sec.contracts import DiscoveryResult
from profitlab.sec.fixtures import FIXTURES, FixtureLimiter
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder


class SourceService:
    def __init__(self, settings, *, transport=None, limiter=None):
        self.settings, self.transport, self.limiter = settings, transport, limiter
        self.repo = Repository(settings.data_dir)

    def progress(self, run_id, stage, filing_id=None):
        from profitlab.sec.service import _live_lock

        run = self.repo.manifest(run_id)
        live = run.mode == 'live' and stage == 'download'
        if live and not _live_lock.acquire(blocking=False):
            raise ValueError('A live SEC operation is already active; wait before starting another.')
        try:
            return self._progress(run_id, stage, filing_id)
        finally:
            if live:
                _live_lock.release()

    def _progress(self, run_id, stage, filing_id=None):
        if stage not in ('download', 'parse'):
            raise ValueError('Implemented stages: download, parse.')
        run = self.repo.manifest(run_id)
        if run.mode == 'replay':
            raise ValueError('Replay sources are read-only.')
        if stage == 'download' and run.mode == 'live' and not self.settings.sec_contact_ready():
            raise ValueError('Configure SEC_USER_AGENT with a real contact email.')
        discovery = DiscoveryResult.model_validate_json(self.repo.read(run_id, 'discovery'))
        filings = [f for f in discovery.filings if filing_id is None or f.filing_id == filing_id]
        if not filings:
            raise ValueError('No discovered filings match this stage request.')
        trace = TraceRecorder(self.repo, run_id, self.settings.redactor())
        client = SECClient(self.settings, trace, transport=self.transport,
                           limiter=self.limiter or (FixtureLimiter() if run.mode == 'demo' else None),
                           fixture=run.mode == 'demo')
        errors = []
        try:
            for filing in filings:
                try:
                    with trace.operation(f'{stage.title()} source', {'filing_id': filing.filing_id},
                                         stage=stage) as out:
                        raw_id = 'raw-' + filing.filing_id
                        if stage == 'download':
                            try:
                                raw = self.repo.read(run_id, raw_id)
                                metadata = SourceDownload.model_validate_json(self.repo.read(
                                    run_id, 'source-' + filing.filing_id)).model_dump(mode='json')
                                if metadata['sha256'] != hashlib.sha256(raw).hexdigest():
                                    raise ValueError('Source metadata hash mismatch')
                                out.update(cache_status='hit', source=metadata)
                            except FileNotFoundError:
                                if run.mode == 'demo':
                                    raw = (FIXTURES / f'annual-{filing.report_date.year}.html').read_bytes()
                                    content_type = 'text/html'
                                else:
                                    raw, content_type = client.get(filing.primary_document_url, bytes,
                                        stage='download', document=True)
                                parse_source(raw, filing.filing_id)
                                metadata = {'filing_id': filing.filing_id, 'status': 'saved',
                                    'url': filing.primary_document_url, 'content_type': content_type,
                                    'retrieved_at': datetime.now(UTC).isoformat(),
                                    'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
                                metadata = SourceDownload.model_validate(metadata).model_dump(mode='json')
                                self.repo.put(run_id, raw_id, raw, 'text/html')
                                self.repo.put(run_id, 'source-' + filing.filing_id,
                                              json.dumps(metadata).encode())
                                out.update(source=metadata)
                        else:
                            raw = self.repo.read(run_id, raw_id)
                            blocks, cells, tables = parse_source(raw, filing.filing_id)
                            for block in blocks:
                                self.repo.save_contract(run_id, block.block_id, block)
                            # Headers may refer to later cells; publish all in one transaction.
                            with self.repo.connect() as db:
                                db.execute('BEGIN IMMEDIATE')
                                for cell in cells:
                                    self.repo._put(db, run_id, cell.cell_id,
                                        cell.model_dump_json(indent=2).encode(),
                                        'application/json', 'TableCell')
                                for cell in cells:
                                    self.repo._validate_references(db, run_id, cell)
                            index = {'parser_version': VERSION, 'filing_id': filing.filing_id,
                                'source_hash': hashlib.sha256(raw).hexdigest(),
                                'blocks': [b.block_id for b in blocks],
                                'cells': [c.cell_id for c in cells], 'tables': tables}
                            self.repo.put(run_id, 'parsed-' + VERSION + '-' + filing.filing_id,
                                          json.dumps(index).encode())
                            out.update(blocks=len(blocks), cells=len(cells), parser_version=VERSION)
                except (SECError, ValueError, FileNotFoundError) as error:
                    message = self.settings.redactor().text(str(error))
                    failure = {'filing_id': filing.filing_id, 'stage': stage, 'status': 'failed',
                               'error': message, 'recorded_at': datetime.now(UTC).isoformat()}
                    self.repo.put(run_id, 'source-error-' + filing.filing_id + '-' + uuid4().hex[:8],
                                  json.dumps(failure).encode())
                    errors.append(f'{filing.filing_id}: {message}')
        finally:
            client.close()
        if errors:
            raise ValueError('Stage incomplete: ' + '; '.join(errors))
        snapshot_id = 'manifest-' + stage
        try:
            self.repo.read(run_id, snapshot_id)
        except FileNotFoundError:
            snapshot = run.model_copy(update={'stage': stage,
                'updated_at': datetime.now(UTC),
                'limitation': 'Sources available for inspection. Financial extraction is not implemented yet.'})
            self.repo.save_contract(run_id, snapshot_id, snapshot)
        return self.repo.manifest(run_id)

    def sources(self, run_id):
        run = self.repo.manifest(run_id)
        discovery = DiscoveryResult.model_validate_json(self.repo.read(run_id, 'discovery'))
        failures = {}
        for artifact in self.repo.artifacts(run_id):
            if artifact['artifact_id'].startswith('source-error-'):
                failure = json.loads(self.repo.read(run_id, artifact['artifact_id']))
                previous = failures.get(failure['filing_id'])
                if not previous or previous['recorded_at'] < failure['recorded_at']:
                    failures[failure['filing_id']] = failure
        result = []
        for filing in discovery.filings:
            item = {'filing': filing, 'metadata': None, 'index': None, 'blocks': [],
                    'error': failures.get(filing.filing_id)}
            try:
                item['metadata'] = json.loads(self.repo.read(run_id, 'source-' + filing.filing_id))
                try:
                    item['index'] = json.loads(self.repo.read(
                        run_id, 'parsed-' + VERSION + '-' + filing.filing_id))
                except FileNotFoundError:
                    item['index'] = json.loads(self.repo.read(run_id, 'parsed-' + filing.filing_id))
                item['blocks'] = [SourceBlock.model_validate_json(self.repo.read(run_id, b))
                                  for b in item['index']['blocks']]
            except FileNotFoundError:
                pass
            result.append(item)
        return run, result

    def document(self, run_id, filing_id):
        run, items = self.sources(run_id)
        item = next((i for i in items if i['filing'].filing_id == filing_id), None)
        if item is None or item['index'] is None:
            raise FileNotFoundError(filing_id)
        item['cells'] = {c: TableCell.model_validate_json(self.repo.read(run_id, c))
                         for c in item['index']['cells']}
        return run, item
