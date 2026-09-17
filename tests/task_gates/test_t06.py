import hashlib

import pytest
from fastapi.testclient import TestClient

from profitlab.demo import DemoService
from profitlab.documents.chunk_service import ChunkService
from profitlab.documents.chunking import chunk_document
from profitlab.documents.service import SourceService
from profitlab.settings import Settings
from profitlab.web.app import create_app


def test_offline_chunks_coverage_ui_and_restart(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    DemoService(tmp_path).create('chunks-test', 'T06')
    service = ChunkService(settings)
    run, chunks = service.list('chunks-test')
    assert run.stage == 'chunk'
    assert any(c.overlap_block_ids for c in chunks)
    assert any(c.table_id and c.token_estimate > 1500 and c.piece == 1 for c in chunks)
    pieces = [c for c in chunks if c.piece > 1]
    assert pieces
    assert all('2025' in c.text and '2024' in c.text and 'USD millions' in c.text for c in pieces)
    for item in SourceService(settings).sources('chunks-test')[1]:
        own = [c for c in chunks if c.filing_id == item['filing'].filing_id]
        assert {b.block_id for b in item['blocks']} == {b for c in own for b in c.primary_block_ids}
        _, doc = SourceService(settings).document('chunks-test', item['filing'].filing_id)
        assert set(doc['cells']) == {cid for c in own for cid in c.cell_ids}
        repeated = chunk_document(item['filing'], doc['blocks'], doc['cells'], doc['index']['tables'], settings)
        assert [c.model_dump() for c in own] == [c.model_dump() for c in repeated]
    assert all(c.request_token_estimate <= 24000 for c in chunks)
    assert all(c.content_hash == hashlib.sha256(c.text.encode()).hexdigest() for c in chunks)
    service.progress('chunks-test')
    assert len(service.list('chunks-test')[1]) == len(chunks)
    with TestClient(create_app(settings)) as client:
        page = client.get('/runs/chunks-test/chunks')
        assert page.status_code == 200
        assert 'Screening: Not implemented yet' in page.text
        assert 'Following chunk' in page.text and 'Table piece 2' in page.text
        assert 'Prose overlap:' in page.text
        assert 'No saved chunks' in client.get('/runs/chunks-test/chunks?min_tokens=999999').text
        assert 'No saved chunks' in client.get('/runs/chunks-test/chunks?heading=absent').text
        assert client.get('/runs/absent/chunks').status_code == 404


def test_guard_and_cross_filing(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    DemoService(tmp_path).create('guard-test', 'T05')
    item = SourceService(settings).sources('guard-test')[1][0]
    _, doc = SourceService(settings).document('guard-test', item['filing'].filing_id)
    block = doc['blocks'][0].model_copy(update={'text': 'x' * 100000})
    with pytest.raises(ValueError, match='Oversized unsupported'):
        chunk_document(item['filing'], [block], {}, {}, settings)
    with pytest.raises(ValueError, match='Cross-filing'):
        chunk_document(item['filing'], [block.model_copy(update={'filing_id': 'other'})], {}, {}, settings)
    table = next(b for b in doc['blocks'] if b.kind == 'table')
    row = next(r for r in doc['index']['tables'][table.table_id]['rows'] if not all(c['header'] for c in r))
    cells = dict(doc['cells'])
    cells[row[-1]['cell_id']] = cells[row[-1]['cell_id']].model_copy(update={'raw_text': 'z' * 100000})
    with pytest.raises(ValueError, match='Oversized unsupported row'):
        chunk_document(item['filing'], [table.model_copy(update={'text': 'z' * 100000})],
                       cells, doc['index']['tables'], settings)
