"""Persisted, immutable chunk stage shared by demo and CLI."""
import json
from datetime import UTC, datetime

from profitlab.contracts.sources import Chunk
from profitlab.documents.chunking import VERSION, chunk_document
from profitlab.documents.service import SourceService
from profitlab.storage import Repository
from profitlab.trace import TraceRecorder


class ChunkService:
    def __init__(self, settings):
        self.settings = settings
        self.repo = Repository(settings.data_dir)

    def progress(self, run_id, filing_id=None):
        run, items = SourceService(self.settings).sources(run_id)
        if run.mode == 'replay':
            raise ValueError('Replay chunks are read-only.')
        items = [i for i in items if filing_id is None or i['filing'].filing_id == filing_id]
        if not items:
            raise ValueError('No discovered filings match this request.')
        trace = TraceRecorder(self.repo, run_id, self.settings.redactor())
        errors = []
        for item in items:
            try:
                with trace.operation('Chunk source', {'filing_id': item['filing'].filing_id,
                        'target': self.settings.chunk_target_tokens,
                        'overlap': self.settings.chunk_overlap_tokens,
                        'request_budget': self.settings.chunk_request_budget,
                        'question_overhead': self.settings.chunk_question_overhead}, stage='chunk') as out:
                    _, document = SourceService(self.settings).document(run_id, item['filing'].filing_id)
                    chunks = chunk_document(item['filing'], document['blocks'], document['cells'],
                                            document['index']['tables'], self.settings)
                    for chunk in chunks:
                        self.repo.save_contract(run_id, chunk.chunk_id, chunk)
                    index = {'version': VERSION, 'filing_id': item['filing'].filing_id,
                             'source_hash': document['index']['source_hash'],
                             'parser_version': document['index']['parser_version'],
                             'chunk_ids': [c.chunk_id for c in chunks]}
                    import hashlib

                    key = 'chunks-' + hashlib.sha256(json.dumps(index).encode()).hexdigest()[:24]
                    self.repo.put(run_id, key, json.dumps(index).encode())
                    out.update(index=key, count=len(chunks))
            except (FileNotFoundError, ValueError) as error:
                errors.append(self.settings.redactor().text(str(error)))
        if errors:
            raise ValueError('Chunk stage incomplete: ' + '; '.join(errors))
        try:
            self.repo.read(run_id, 'manifest-chunk')
        except FileNotFoundError:
            self.repo.save_contract(run_id, 'manifest-chunk', run.model_copy(update={
                'stage': 'chunk', 'updated_at': datetime.now(UTC),
                'limitation': 'Chunks available. Screening and financial extraction are not implemented yet.'}))
        return self.repo.manifest(run_id)

    def list(self, run_id):
        run = self.repo.manifest(run_id)
        chunks = [Chunk.model_validate_json(self.repo.read(run_id, a['artifact_id']))
                  for a in self.repo.artifacts(run_id) if a['contract'] == 'Chunk']
        ordinals = {}
        for c in chunks:
            if c.primary_block_ids[0] not in ordinals:
                from profitlab.contracts.sources import SourceBlock

                ordinals[c.primary_block_ids[0]] = SourceBlock.model_validate_json(
                    self.repo.read(run_id, c.primary_block_ids[0])).ordinal
        chunks.sort(key=lambda c: (c.filing_id, ordinals[c.primary_block_ids[0]], c.piece, c.chunk_id))
        return run, chunks
