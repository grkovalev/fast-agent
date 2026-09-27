"""V3 remains source-cited and physically isolated from the V2 baseline."""
import json
import sqlite3
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from profitlab.sec.ticker_picker import TickerSelection
from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef, SourceRange
from profitlab.v2.storage import V2Repository
from profitlab.v3.campaign_review import CampaignReviewService
from profitlab.v3.contracts import (
    CampaignReview,
    CampaignRun,
    DevelopmentCampaign,
    DevelopmentCase,
    DevelopmentCohort,
    DevelopmentConfiguration,
    FrozenArtifact,
    PostSealCase,
    RubricCohort,
)
from profitlab.v3.development_ledger import DevelopmentLedgerService
from profitlab.v3.repository import V3Repository
from profitlab.v3.rubric import PostSealRubricService
from profitlab.v3.service import V3ExplorationIncomplete, V3GraphService, _Trace
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
            return {'answerability': 'sufficient', 'nodes': [
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
            return {'answerability': 'sufficient', 'nodes': [{'label': 'navigation only', 'status': 'accepted',
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
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
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
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        return {'answer': 'Revenue was 100.', 'path_ids': ['path-made-up'],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    assert result.answer.status == 'limited'
    assert result.answer.path_ids == [result.paths[0].path_id]
    assert 'derived mechanically' in result.answer.limitation


@pytest.mark.asyncio
async def test_v3_persists_each_material_answer_claim_with_its_exact_graph_path(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'limitation': None, 'path_ids': [path['path_id']],
                'claims': [{'claim': 'Revenue was 100.', 'path_ids': [path['path_id']],
                            'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    assert result.answer.claims[0].path_ids == result.answer.path_ids
    assert result.answer.claims[0].source_ranges[0].start_line == 1


@pytest.mark.asyncio
async def test_v3_refuses_a_claim_citation_outside_its_graph_path(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Unsupported claim.', 'path_ids': [path['path_id']],
                'claims': [{'claim': 'Unsupported claim.', 'path_ids': [path['path_id']],
                            'citations': [{'start_line': 2, 'exact_text': 'The increase supports growth.'}]}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    with pytest.raises(ValueError, match='selected graph path'):
        await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())


@pytest.mark.asyncio
async def test_v3_returns_explicitly_limited_answer_from_uncertain_graph(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'possible revenue', 'status': 'uncertain',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'The source may report revenue of 100.', 'path_ids': [path['path_id']],
                'claims': [{'claim': 'The source may report revenue of 100.', 'path_ids': [path['path_id']],
                            'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    assert result.answer.status == 'limited'
    assert 'uncertain or conflicting' in result.answer.limitation


@pytest.mark.asyncio
async def test_v3_identical_source_runs_persist_distinct_immutable_graph_rows(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
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
            return {'answerability': 'sufficient', 'nodes': [{'label': 'bad', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'invented'}]}], 'edges': []}
        raise AssertionError('answer model must not run without accepted source support')

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    with pytest.raises(V3ExplorationIncomplete, match='no answer was synthesized') as error:
        await V3GraphService(settings, caller=malformed).answer_document('TEST', 'Question?', _document())
    assert error.value.frontier_state in {'partial', 'exhausted'}
    assert V3Repository(tmp_path).inspection(error.value.experiment_id)['manifest'].frontier_state == error.value.frontier_state


@pytest.mark.asyncio
async def test_v3_accepts_model_facing_statuses_and_label_edge_references(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [
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
                return {'answerability': 'insufficient', 'nodes': [{'label': 'need support', 'status': 'uncertain', 'evidence': [
                    {'start_line': 2, 'exact_text': 'Need later support.'}]}], 'edges': [],
                    'next_windows': [{'start_line': 11, 'end_line': 20, 'reason': 'seek support for the uncertain claim', 'parent_refs': [0]}]}
            return {'answerability': 'sufficient', 'nodes': [{'label': 'support', 'status': 'accepted', 'evidence': [
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
        assert actions[0]['answerability'] == 'insufficient'
        assert actions[1]['answerability'] == 'sufficient'
        assert actions[1]['parent_path']
        assert actions[1]['reason'] == 'seek support for the uncertain claim'
        assert actions[1]['budget_state']['actions_used'] == 2
    assert result.manifest.frontier_state == 'answered'


@pytest.mark.asyncio
async def test_v3_rejects_equivalent_frontier_revisit_and_keeps_audit_of_the_rejection(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'insufficient', 'nodes': [{'label': 'source', 'status': 'accepted', 'evidence': [
                {'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': [],
                'next_windows': [{'start_line': 1, 'end_line': 2, 'reason': 'repeat it', 'parent_refs': [0]}]}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_max_actions=4)
    service = V3GraphService(settings, caller=caller)
    with pytest.raises(ValueError, match='no answer was synthesized'):
        await service.answer_document('TEST', 'Question?', _document())
    with sqlite3.connect(service.repo.db_path) as db:
        assert db.execute('SELECT count(*) FROM actions').fetchone()[0] == 1
        action = json.loads(db.execute('SELECT payload FROM actions').fetchone()[0])
        manifest = json.loads(db.execute('SELECT payload FROM manifest_snapshots').fetchone()[0])
    assert action['answerability'] == 'insufficient'
    assert action['status'] == 'partial'
    assert manifest['frontier_state'] == 'partial'


@pytest.mark.asyncio
async def test_v3_insufficient_without_continuation_persists_partial_and_never_calls_answer(tmp_path):
    calls = []

    async def caller(payload):
        calls.append(payload['kind'])
        if payload['kind'] == 'explore':
            return {'answerability': 'insufficient', 'nodes': [{'label': 'unresolved', 'status': 'uncertain',
                'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': [], 'next_windows': []}
        raise AssertionError('an insufficient frontier must not enter answer synthesis')

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    service = V3GraphService(settings, caller=caller)
    with pytest.raises(ValueError, match='no answer was synthesized'):
        await service.answer_document('TEST', 'Question?', _document())
    inspection = service.repo.inspection(service.repo.experiments()[0].experiment_id)
    assert calls == ['explore']
    assert inspection['manifest'].frontier_state == 'partial'
    assert inspection['actions'][0].answerability == 'insufficient'


@pytest.mark.asyncio
async def test_v3_sufficient_frontier_is_the_only_answer_synthesis_eligibility(tmp_path):
    calls = []

    async def caller(payload):
        calls.append(payload['kind'])
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'reported revenue', 'status': 'accepted',
                'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': [], 'next_windows': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    result = await V3GraphService(settings, caller=caller).answer_document('TEST', 'Question?', _document())
    assert calls == ['explore', 'answer']
    assert result.manifest.frontier_state == 'answered'


def test_v3_sec_trace_supports_shared_client_cache_redaction(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    trace = _Trace(settings.redactor())
    assert trace.redact({'authorization': 'Bearer secret'}) == {'authorization': '[REDACTED]'}


@pytest.mark.asyncio
async def test_v3_explorer_shows_one_path_exact_source_and_frontier_audit(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [
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


def test_v3_explorer_reads_pre_g5_answer_rows(tmp_path):
    """Existing isolated experiments remain inspectable after claim persistence."""
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    service = V3GraphService(settings)
    document = _document()
    manifest = __import__('profitlab.v3.contracts', fromlist=['ExperimentManifest']).ExperimentManifest(
        experiment_id='v3-' + 'a' * 16, question='Question?', document=document.ref, ticker='TEST',
        filing={}, application_revision='legacy', model='model', prompt_version='old', budgets={},
        non_leak_inventory=service._NON_LEAK, created_at=__import__('datetime').datetime.now(__import__('datetime').UTC))
    service.repo.create(manifest, document, b'', b'')
    with service.repo.connect() as db:
        db.execute('INSERT INTO answers VALUES (?, ?, ?)', (manifest.experiment_id, 'answer-' + 'b' * 16,
            json.dumps({'schema_version': 3, 'answer_id': 'answer-' + 'b' * 16,
                        'experiment_id': manifest.experiment_id, 'answer': 'Revenue was 100.',
                        'limitation': None, 'path_ids': ['path-' + 'c' * 16],
                        'source_ranges': [SourceRange(document_id=document.ref.document_id,
                                                      source_hash=document.ref.source_hash,
                                                      start_line=1, end_line=1).model_dump(mode='json')],
                        'status': 'limited',
                        'model': 'model', 'prompt_version': 'old'})))
    with TestClient(create_app(settings)) as client:
        response = client.get('/v3/experiments/' + manifest.experiment_id)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_v3_post_seal_rubric_compares_frozen_methods_without_provider_input(tmp_path):
    calls = []

    async def caller(payload):
        calls.append(payload)
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    service = V3GraphService(settings, caller=caller)
    result = await service.answer_document('TEST', 'Question?', _document())
    source = SourceRange(document_id='v3-document', source_hash='b' * 64, start_line=1, end_line=1)
    cohort = RubricCohort(
        cohort_id='cohort-' + 'd' * 16, rubric_version='g6-post-seal-v1', configuration_id='frozen-v1',
        held_out=True, created_at=datetime.now(UTC), cases=[PostSealCase(
            case_id='held-out-1', experiment_id=result.manifest.experiment_id, question='Question?',
            required_ranges=[source], artifacts=[
                FrozenArtifact(artifact_id='graph-result', method='graph', source_ranges=[source],
                               citation_ranges=[source], graph_path_ids=result.answer.path_ids,
                               answer_support='supported', ambiguity_handling='handled', provider_calls=2,
                               provider_input_tokens=10, provider_output_tokens=4, latency_seconds=.4),
                FrozenArtifact(artifact_id='frozen-v2', method='v2_packet', source_ranges=[source],
                               citation_ranges=[source], answer_support='partial',
                               ambiguity_handling='disclosed', provider_calls=3, latency_seconds=.7),
                FrozenArtifact(artifact_id='window', method='bounded_window', source_ranges=[source],
                               citation_ranges=[], answer_support='unresolved',
                               ambiguity_handling='disclosed', provider_calls=1),
            ])])

    report = PostSealRubricService.score(cohort, service.repo)
    assert len(calls) == 2
    assert report.method_summary['graph']['citation_valid_artifacts'] == 1
    assert report.method_summary['v2_packet']['path_fidelity_valid_artifacts'] == 0
    assert report.method_summary['bounded_window']['citation_valid_artifacts'] == 0
    service.repo.save_rubric_report(report)
    assert service.repo.rubric_report(cohort.cohort_id).artifacts[0].source_coverage == 1
    with TestClient(create_app(settings)) as client:
        page = client.get('/v3/comparisons/' + cohort.cohort_id)
    assert page.status_code == 200
    assert 'These reviewer inputs are attached after graph construction.' in page.text


@pytest.mark.asyncio
async def test_v3_post_seal_rubric_rejects_non_heldout_and_out_of_path_graph_citation(tmp_path):
    async def caller(payload):
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
                               'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    service = V3GraphService(Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10), caller=caller)
    result = await service.answer_document('TEST', 'Question?', _document())
    first = SourceRange(document_id='v3-document', source_hash='b' * 64, start_line=1, end_line=1)
    second = SourceRange(document_id='v3-document', source_hash='b' * 64, start_line=2, end_line=2)
    base = {'cohort_id': 'cohort-' + 'e' * 16, 'rubric_version': 'g6-post-seal-v1',
            'configuration_id': 'frozen-v1', 'created_at': datetime.now(UTC), 'cases': [PostSealCase(
                case_id='held-out-2', experiment_id=result.manifest.experiment_id, question='Question?',
                required_ranges=[first], artifacts=[FrozenArtifact(
                    artifact_id='bad-graph', method='graph', source_ranges=[first, second], citation_ranges=[second],
                    graph_path_ids=result.answer.path_ids, answer_support='unsupported',
                    ambiguity_handling='forced', provider_calls=2)])]}
    with pytest.raises(ValueError, match='explicitly held out'):
        PostSealRubricService.score(RubricCohort(held_out=False, **base), service.repo)
    report = PostSealRubricService.score(RubricCohort(held_out=True, **base), service.repo)
    assert report.artifacts[0].citation_valid is False
    assert report.artifacts[0].path_fidelity == 'invalid'


@pytest.mark.asyncio
async def test_g6b_development_ledger_is_post_run_exact_and_inspectable_without_provider_calls(tmp_path):
    calls = []

    async def caller(payload):
        calls.append(payload)
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
                     'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    service = V3GraphService(settings, caller=caller)
    result = await service.answer_document('TEST', 'Question?', _document())
    ground_truth = SourceRange(document_id='v3-document', source_hash='b' * 64, start_line=1, end_line=1)
    cohort = DevelopmentCohort(
        cohort_id='development-cohort-' + 'a' * 16, configuration_id='fixed-v5', created_at=datetime.now(UTC),
        configuration=DevelopmentConfiguration(application_revision=result.manifest.application_revision,
            model=result.manifest.model, prompt_version=result.manifest.prompt_version,
            budgets=result.manifest.budgets),
        cases=[DevelopmentCase(case_id='development-1', experiment_id=result.manifest.experiment_id,
            question='Question?', ground_truth_ranges=[ground_truth], answer_support='supported',
            ambiguity_handling='handled')])
    before = len(calls)
    report = DevelopmentLedgerService.score(cohort, service.repo)
    assert len(calls) == before
    assert all('ground_truth_ranges' not in json.dumps(payload) for payload in calls)
    assert report.cases[0].ground_truth_coverage == 1
    assert report.cases[0].exact_citations_valid is True
    service.repo.save_development_ledger_report(report)
    assert service.repo.development_ledger_report(cohort.cohort_id).summary['cases'] == 1
    with TestClient(create_app(settings)) as client:
        page = client.get('/v3/development-ledgers/' + cohort.cohort_id)
    assert page.status_code == 200
    assert 'not graph or provider inputs' in page.text
    invalid = cohort.model_copy(update={'cohort_id': 'development-cohort-' + 'b' * 16,
        'cases': [cohort.cases[0].model_copy(update={'ground_truth_ranges': [ground_truth.model_copy(update={'end_line': 3})]})]})
    with pytest.raises(ValueError, match='exact canonical range'):
        DevelopmentLedgerService.score(invalid, service.repo)


def test_g6b_campaign_seals_server_configuration_and_workspace_rejects_excluded_before_work(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, sec_user_agent='Tester test@example.org',
                        llm_api_key='test-key', v3_window_lines=10)
    service = V3GraphService(settings)
    campaign = DevelopmentCampaign(campaign_id='campaign-' + 'a' * 16, question='Question?',
                                   configuration=service.campaign_configuration(), created_at=datetime.now(UTC))
    assert service.validate_campaign_launch(campaign, 'new') == 'NEW'
    with pytest.raises(ValueError, match='excluded'):
        service.validate_campaign_launch(campaign, 'MSFT')
    with pytest.raises(ValueError, match='does not match'):
        service.validate_campaign_launch(campaign.model_copy(update={
            'configuration': campaign.configuration.model_copy(update={'max_actions': 11})}), 'NEW')

    with TestClient(create_app(settings)) as client:
        created = client.post('/v3/campaigns', data={'question': 'What does this filing say?'}, follow_redirects=False)
        assert created.status_code == 303
        workspace = client.get(created.headers['location'])
        assert workspace.status_code == 200
        assert 'Immutable V3 configuration' in workspace.text
        assert 'What does this filing say?' in workspace.text
        rejected = client.post(created.headers['location'] + '/runs', data={'ticker': 'MSFT'})
    assert rejected.status_code == 400
    assert 'excluded' in rejected.text
    assert V3Repository(tmp_path).campaign_runs() == []


@pytest.mark.asyncio
async def test_g6b_campaign_review_is_terminal_only_exact_immutable_and_uses_the_existing_scorer(tmp_path):
    calls = []

    async def caller(payload):
        calls.append(payload)
        if payload['kind'] == 'explore':
            return {'answerability': 'sufficient', 'nodes': [{'label': 'revenue', 'status': 'accepted',
                'evidence': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}], 'edges': []}
        path = payload['paths'][0]
        return {'answer': 'Revenue was 100.', 'path_ids': [path['path_id']],
                'citations': [{'start_line': 1, 'exact_text': 'Revenue was 100.'}]}

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, v3_window_lines=10)
    service = V3GraphService(settings, caller=caller)
    result = await service.answer_document('NEW', 'Question?', _document())
    campaign = DevelopmentCampaign(campaign_id='campaign-' + 'b' * 16, question='Question?',
                                   configuration=service.campaign_configuration(), created_at=datetime.now(UTC))
    repo = service.repo
    repo.save_campaign(campaign)
    run = CampaignRun(run_id='campaign-run-' + 'b' * 16, campaign_id=campaign.campaign_id, ticker='NEW',
                      status='sealed', experiment_id=result.manifest.experiment_id, created_at=datetime.now(UTC),
                      finished_at=datetime.now(UTC))
    repo.create_campaign_run(run)
    source = SourceRange(document_id='v3-document', source_hash='b' * 64, start_line=1, end_line=1)
    review = CampaignReview(review_id='campaign-review-' + 'b' * 16, campaign_id=campaign.campaign_id,
        campaign_run_id=run.run_id, experiment_id=result.manifest.experiment_id, question='Question?',
        ground_truth_ranges=[source], answer_support='supported', ambiguity_handling='handled', created_at=datetime.now(UTC))
    before = len(calls)
    report = CampaignReviewService.submit(review, repo)
    assert len(calls) == before
    assert report.cohort.cases[0].ground_truth_ranges == [source]
    assert repo.campaign_review(run.run_id) == review
    assert repo.development_ledger_report(report.cohort.cohort_id) == report
    with pytest.raises(ValueError, match='already has an immutable review'):
        CampaignReviewService.submit(review.model_copy(update={'review_id': 'campaign-review-' + 'c' * 16}), repo)
    unsealed = run.model_copy(update={'run_id': 'campaign-run-' + 'c' * 16, 'status': 'failed'})
    repo.create_campaign_run(unsealed)
    with pytest.raises(ValueError, match='sealed'):
        CampaignReviewService.submit(review.model_copy(update={
            'review_id': 'campaign-review-' + 'd' * 16, 'campaign_run_id': unsealed.run_id}), repo)
    invalid_run = run.model_copy(update={'run_id': 'campaign-run-' + 'd' * 16})
    repo.create_campaign_run(invalid_run)
    with pytest.raises(ValueError, match='exact canonical range'):
        CampaignReviewService.submit(review.model_copy(update={
            'review_id': 'campaign-review-' + 'e' * 16, 'campaign_run_id': invalid_run.run_id,
            'ground_truth_ranges': [source.model_copy(update={'end_line': 3})]}), repo)
    cross_document_run = run.model_copy(update={'run_id': 'campaign-run-' + 'f' * 16})
    repo.create_campaign_run(cross_document_run)
    with pytest.raises(ValueError, match='exact canonical range'):
        CampaignReviewService.submit(review.model_copy(update={
            'review_id': 'campaign-review-' + 'f' * 16, 'campaign_run_id': cross_document_run.run_id,
            'ground_truth_ranges': [source.model_copy(update={'document_id': 'other-document'})]}), repo)
    web_run = run.model_copy(update={'run_id': 'campaign-run-' + 'e' * 16})
    repo.create_campaign_run(web_run)
    with TestClient(create_app(settings)) as client:
        page = client.get('/v3/campaign-runs/' + web_run.run_id)
        assert page.status_code == 200
        assert 'optional' in page.text
        review_page = client.get('/v3/campaign-runs/' + web_run.run_id + '/review')
        assert 'Attach reviewed canonical evidence' in review_page.text
        submitted = client.post('/v3/campaign-runs/' + web_run.run_id + '/review', data={
            'start_line': '1', 'end_line': '1', 'answer_support': 'supported',
            'ambiguity_handling': 'handled', 'notes': 'Post-seal review.'}, follow_redirects=False)
    assert submitted.status_code == 303
    assert submitted.headers['location'].startswith('/v3/development-ledgers/')


def test_v3_primary_workspace_launches_the_fixed_v2_metric_experiment_without_question_or_campaign_input(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, sec_user_agent='Tester test@example.org',
                        llm_api_key='test-key', v3_window_lines=10)
    with TestClient(create_app(settings)) as client:
        page = client.get('/v3/experiments')
        assert page.status_code == 200
        assert 'Run experimental report' in page.text
        assert 'Start random eligible report' in page.text
        assert 'Start sequential V3 batch' in page.text
        assert 'V3 experiment' in page.text
        assert 'name="question"' not in page.text
        assert 'name="ticker"' in page.text
        rejected = client.post('/v3/reports', data={'ticker': 'MSFT'})
    assert rejected.status_code == 400
    assert 'excluded' in rejected.text
    assert V3Repository(tmp_path).campaigns()  # Server owns the fixed, sealed campaign.
    assert V3Repository(tmp_path).campaign_runs() == []


def test_v3_random_and_batch_controls_persist_only_v3_local_selection_and_batch_history(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, sec_user_agent='Tester test@example.org',
                        llm_api_key='test-key', v3_window_lines=10)
    v2 = V2Repository(tmp_path)
    before = v2.db_path.read_bytes()

    class UnavailablePicker:
        def __init__(self, repo):
            self.repo = repo

        def pick(self, **_kwargs):
            selection = TickerSelection(None, datetime.now(UTC), 'test directory', 'test', 'hit', 'exhausted',
                                        'No test ticker is available.')
            self.repo.record_ticker_selection(selection)
            return selection

    with TestClient(create_app(settings, v3_ticker_picker_factory=UnavailablePicker)) as client:
        unavailable = client.post('/v3/ticker-picker')
        invalid_batch = client.post('/v3/batches', data={'count': '0'})
        started = client.post('/v3/batches', data={'count': '2'}, follow_redirects=False)
        assert unavailable.status_code == 503
        assert invalid_batch.status_code == 400
        assert started.status_code == 303
        page = client.get(started.headers['location'])
    repo = V3Repository(tmp_path)
    batch = repo.v3_report_batch(started.headers['location'].rsplit('/', 1)[-1])
    assert batch.requested_count == 2
    assert batch.status in {'running', 'completed', 'interrupted'}
    assert repo.processed_tickers() == set()
    with sqlite3.connect(repo.db_path) as db:
        assert db.execute('SELECT count(*) FROM v3_ticker_selections').fetchone()[0] >= 1
        assert db.execute('SELECT count(*) FROM v3_report_batches').fetchone()[0] == 1
    assert 'V3-only batch' in page.text
    assert v2.db_path.read_bytes() == before
