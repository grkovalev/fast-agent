"""V3 remains source-cited and physically isolated from the V2 baseline."""
import sqlite3

import pytest

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef
from profitlab.v2.storage import V2Repository
from profitlab.v3.service import V3GraphService, _Trace


def _document():
    ref = CanonicalDocumentRef(document_id='v3-document', filing_id='filing', source_hash='b' * 64,
                               line_count=2)
    return CanonicalDocument(ref=ref, lines=[
        CanonicalLine(line_number=1, text='Revenue was 100.', element_type='paragraph',
                      html_anchor='one', dom_reference='/p[1]'),
        CanonicalLine(line_number=2, text='The increase supports growth.', element_type='paragraph',
                      html_anchor='two', dom_reference='/p[2]'),
    ])


@pytest.mark.asyncio
async def test_v3_answer_has_exact_cited_graph_path_and_never_touches_v2(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [
                {'label': 'reported revenue', 'status': 'accepted',
                 'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]},
                {'label': 'growth support', 'status': 'accepted',
                 'evidence': [{'start_line': 2, 'exact_text': 'The increase supports growth.'}]},
            ], 'edges': [{'from_node': 0, 'to_node': 1, 'relation': 'supports', 'status': 'accepted',
                          'evidence': [{'start_line': 2, 'exact_text': 'The increase supports growth.'}]}]}
        path = payload['paths'][0]
        return {'answer': 'The filing reports revenue of 100.', 'limitation': None,
                'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    # Establish a V2 database first: V3 must use another namespace and never migrate it.
    v2 = V2Repository(tmp_path)
    before = v2.db_path.read_bytes()
    result = await V3GraphService(settings, caller=caller).answer_document(
        'TEST', 'What revenue is reported?', _document(), filing={'form': '10-K'})

    assert result.answer.status == 'accepted'
    assert result.cited_text == {'L1': 'Revenue was 100.'}
    assert result.paths[0].source_ranges[0].start_line == 1
    assert (tmp_path / 'evidence-graph-experiment' / 'profitlab-v3.sqlite3').exists()
    assert v2.db_path.read_bytes() == before


@pytest.mark.asyncio
async def test_v3_answer_packet_includes_visible_path_text_not_only_generated_labels(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [{'label': 'navigation only', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        assert payload['paths'][0]['evidence'][0]['exact_text'] == 'Revenue was 100.'
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())


@pytest.mark.asyncio
async def test_v3_derives_missing_answer_character_offsets_only_from_selected_graph_path(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'was 100'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    assert result.answer.source_ranges[0].start_character == 8
    assert result.cited_text == {'L1': 'Revenue was 100.'}


@pytest.mark.asyncio
async def test_v3_limits_but_keeps_an_exact_answer_when_model_mangles_opaque_path_id(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        return {'answer': 'Revenue was 100.', 'path_ids': ['path-made-up'],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    assert result.answer.status == 'limited'
    assert result.answer.path_ids == [result.paths[0].path_id]
    assert 'derived mechanically' in result.answer.limitation


@pytest.mark.asyncio
async def test_v3_identical_source_runs_persist_distinct_immutable_graph_rows(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    service = V3GraphService(settings, caller=caller)
    await service.answer_document('TEST', 'Question?', _document())
    await service.answer_document('TEST', 'Question?', _document())
    with sqlite3.connect(service.repo.db_path) as db:
        assert db.execute('SELECT count(*) FROM nodes').fetchone()[0] == 2
        assert db.execute('SELECT count(*) FROM paths').fetchone()[0] == 2


@pytest.mark.asyncio
async def test_v3_rejects_non_round_tripping_model_provenance_and_does_not_fabricate(tmp_path):
    async def malformed(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [{'label': 'bad', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'invented'}]}], 'edges': []}
        raise AssertionError('answer model must not run without accepted source support')

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    with pytest.raises(ValueError, match='no answer was fabricated'):
        await V3GraphService(settings, caller=malformed).answer_document('TEST', 'Question?', _document())


@pytest.mark.asyncio
async def test_v3_accepts_model_facing_statuses_and_label_edge_references(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [
                {'label': 'revenue statement', 'status': 'stated',
                 'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]},
                {'label': 'growth statement', 'status': 'supported',
                 'evidence': [{'start_line': 2, 'exact_text': 'The increase supports growth.'}]},
            ], 'edges': [{'from_node': 'revenue statement', 'to_node': 'growth statement',
                          'relation': 'supports', 'status': 'supported',
                          'evidence': [{'start_line': 2, 'exact_text': 'The increase supports growth.'}]}]}
        path = next(path for path in payload['paths'] if path['edge_ids'])
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    assert result.answer.status == 'accepted'
    assert result.paths[0].edge_ids


def test_v3_sec_trace_supports_shared_client_cache_redaction(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    trace = _Trace(settings.redactor())
    assert trace.redact({'authorization': 'Bearer secret'}) == {'authorization': '[REDACTED]'}
