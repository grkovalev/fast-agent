"""V3 remains source-cited and physically isolated from the V2 baseline."""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef
from profitlab.v2.storage import V2Repository
from profitlab.v3.service import V3GraphService, _Trace
from profitlab.web.app import create_app


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


@pytest.mark.asyncio
async def test_v3_plans_source_expansion_from_accepted_graph_evidence_and_records_frontier(tmp_path):
    ref = CanonicalDocumentRef(document_id='dynamic-document', filing_id='filing', source_hash='c' * 64,
                               line_count=20)
    texts = ['Opening context.', 'Need later support.'] + [f'Unrelated context {line}.' for line in range(3, 11)] + [
        'Later source support.'] + [f'Closing context {line}.' for line in range(12, 21)]
    document = CanonicalDocument(ref=ref, lines=[
        CanonicalLine(line_number=line, text=text, element_type='paragraph', html_anchor=f'line-{line}',
                      dom_reference=f'/p[{line}]')
        for line, text in enumerate(texts, 1)
    ])
    calls = []

    async def caller(payload):
        if payload['kind'] == 'explore':
            calls.append(payload['window'])
            if payload['window']['start_line'] == 1:
                return {'nodes': [{'label': 'need support', 'status': 'uncertain', 'evidence': [
                    {'start_line': 2, 'exact_text': 'Need later support.'}]}], 'edges': [],
                    'next_windows': [{'start_line': 11, 'end_line': 20, 'reason': 'seek support for the uncertain claim', 'parent_refs': [0]}]}
            return {'nodes': [{'label': 'support', 'status': 'accepted', 'evidence': [
                {'start_line': 11, 'exact_text': 'Later source support.'}]}], 'edges': [], 'next_windows': []}
        path = payload['paths'][0]
        return {'answer': 'Later source support.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 11, 'exact_text': 'Later source support.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10, v3_max_actions=3)
    service = V3GraphService(settings, caller=caller)
    result = await service.answer_document('TEST', 'Question?', document)
    assert calls == [{'start_line': 1, 'end_line': 10}, {'start_line': 11, 'end_line': 20}]
    with sqlite3.connect(service.repo.db_path) as db:
        actions = [__import__('json').loads(row[0]) for row in db.execute('SELECT payload FROM actions ORDER BY rowid')]
        assert actions[1]['parent_path']
        assert actions[1]['reason'] == 'seek support for the uncertain claim'
        assert actions[1]['budget_state']['actions_used'] == 2
    assert result.manifest.frontier_state == 'answered'


@pytest.mark.asyncio
async def test_v3_rejects_equivalent_frontier_revisit_and_keeps_audit_of_the_rejection(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [{'label': 'source', 'status': 'accepted', 'evidence': [
                {'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': [],
                'next_windows': [{'start_line': 1, 'end_line': 2, 'reason': 'repeat it', 'parent_refs': [0]}]}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_max_actions=4)
    service = V3GraphService(settings, caller=caller)
    await service.answer_document('TEST', 'Question?', _document())
    with sqlite3.connect(service.repo.db_path) as db:
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 1


def test_v3_sec_trace_supports_shared_client_cache_redaction(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    trace = _Trace(settings.redactor())
    assert trace.redact({'authorization': 'Bearer secret'}) == {'authorization': '[REDACTED]'}


@pytest.mark.asyncio
async def test_v3_explorer_shows_one_path_exact_source_and_frontier_audit(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'nodes': [
                {'label': 'revenue statement', 'status': 'accepted',
                 'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]},
                {'label': 'unresolved context', 'status': 'uncertain', 'uncertainty': 'not enough support',
                 'evidence': [{'start_line': 2, 'exact_text': 'The increase supports growth.'}]},
                {'label': 'discarded claim', 'status': 'rejected',
                 'evidence': [{'start_line': 2, 'exact_text': 'The increase supports growth.'}]},
            ], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    with TestClient(create_app(settings)) as client:
        listing = client.get('/v3/experiments')
        page = client.get(f'/v3/experiments/{result.manifest.experiment_id}')
        source = client.get(f'/v3/experiments/{result.manifest.experiment_id}/source?line=1')

    assert listing.status_code == page.status_code == source.status_code == 200
    assert result.manifest.experiment_id in listing.text
    assert 'Why each window was explored' in page.text
    assert 'Initial bounded source window' in page.text
    assert 'Revenue was 100.' in page.text
    assert 'Model label:' in page.text
    assert 'unresolved context' in page.text and 'discarded claim' in page.text
    assert 'Only canonical visible text is shown here.' in source.text
