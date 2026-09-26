"""T39 source-context contracts: bounded visible ranges and no hidden inputs."""
from datetime import UTC, datetime

import pytest

from profitlab.providers.jev import JevResponse, NoulAnswer, TokenUsage
from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef, SourceRange, V2Run
from profitlab.v2.pipeline import V2PipelineService
from profitlab.v2.source_context import SourceContextService
from profitlab.v2.source_replay import (
    ExpectedSourceRow,
    SourceReplayCase,
    SourceReplayDataset,
    SourceReplayService,
    load_source_replay_dataset,
)
from profitlab.v2.storage import V2Repository


def _setup(tmp_path):
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='context-run', ticker='CONTEXT', created_at=now, updated_at=now))
    repo.save_filing('context-run', 'filing', 'a' * 64,
                     {'filing_id': 'filing', 'report_date': '2025-12-31'})
    ref = CanonicalDocumentRef(document_id='document', filing_id='filing', source_hash='a' * 64, line_count=5)
    document = CanonicalDocument(ref=ref, lines=[
        CanonicalLine(line_number=number, text=text, element_type='table_row',
                      html_anchor=f'line-{number}', dom_reference=f'/tr[{number}]')
        for number, text in enumerate(('Consolidated statements', 'Year ended 2025',
                                       'Net income 123', 'Diluted EPS 1.20', 'Footer'), 1)])
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='ProfitLab test@example.org',
                        _env_file=None)
    return repo, document, SourceContextService(settings, repo)


def test_context_request_rejects_forbidden_material_and_keeps_core_separate(tmp_path):
    _, document, service = _setup(tmp_path)
    core = SourceRange(document_id='document', source_hash='a' * 64, start_line=3, end_line=3)
    request = service._request('context-run', document, core, service._ring(document, core, 1), 0)

    assert request.state['core_block']['line_number'] == 3
    assert [item['line_number'] for item in request.state['visible_context_before_after']] == [2, 4]
    assert 'structured_facts' not in str(request.state)
    with pytest.raises(ValueError, match='forbidden'):
        service._request('context-run', document, core, [], 0, 'us-gaap: poison')


def test_context_decision_is_range_bound_and_persists_expansion_history(tmp_path):
    repo, document, service = _setup(tmp_path)
    core = SourceRange(document_id='document', source_hash='a' * 64, start_line=3, end_line=3)
    request = service._request('context-run', document, core, service._ring(document, core, 2), 1)
    answers = {key: NoulAnswer(type='noul', noul=(.9 if key in ('evidence', 'sufficient',
               'eligible__annual_profit') else .05)) for key in request.questions}
    decision = service._decision(document, core, service._ring(document, core, 2), 1,
                                 JevResponse(model='jev-test', answers=answers,
                                             usage=TokenUsage(input_tokens=1, output_tokens=1)), 'call-1')
    repo.save_source_context_decisions('context-run', [decision])

    saved = repo.source_context_decisions('context-run')
    assert saved == [decision]
    assert saved[0].role == 'evidence'
    assert saved[0].target_eligibility == {'annual_profit': True, 'diluted_eps': False,
                                            'diluted_shares': False, 'earnings_change': False,
                                            'comparability': False}
    assert saved[0].response_scores['evidence'] == .9
    assert saved[0].response_scores['eligible__annual_profit'] == .9
    assert saved[0].core_range.start_line == saved[0].core_range.end_line == 3
    assert all(item.start_line != 3 and item.end_line != 3 for item in saved[0].context_ranges)


def test_source_context_configuration_is_versioned(tmp_path):
    common = {'PROFITLAB_DATA_DIR': tmp_path, 'SEC_USER_AGENT': 'ProfitLab test@example.org',
              'PROFITLAB_APPLICATION_REVISION': 'context-revision', '_env_file': None}
    baseline = V2PipelineService(Settings(**common)).create('BASE')
    changed = V2PipelineService(Settings(**{**common, 'source_context_rings': (3, 12, 30)})).create('CHANGE')

    assert baseline.version_id != changed.version_id
    assert baseline.version_components['source_context_rings'] == '(2, 8, 24)'


@pytest.mark.asyncio
async def test_context_request_cap_persists_an_explicit_partial_state(tmp_path):
    _, document, service = _setup(tmp_path)
    service.settings = service.settings.model_copy(update={'source_context_max_requests': 1})
    core = SourceRange(document_id='document', source_hash='a' * 64, start_line=3, end_line=3)

    class Client:
        async def evaluate(self, request):
            return JevResponse(model='jev-test', usage=TokenUsage(input_tokens=1, output_tokens=1),
                               answers={key: NoulAnswer(type='noul', noul=(.9 if key.endswith((
                                   '__evidence', '__eligible__annual_profit')) else .05))
                                        for key in request.questions})

    service._client = lambda *args, **kwargs: Client()  # type: ignore[method-assign]
    result = await service.classify('context-run', document, [(core, None)])

    assert result.calls == 1
    assert result.partial == 1
    assert [item.state for item in result.decisions] == ['completed', 'partial']
    assert result.decisions[-1].rationale == 'Configured live source-context request budget exhausted.'


@pytest.mark.asyncio
async def test_context_classification_batches_source_order_without_merging_ranges(tmp_path):
    _, document, service = _setup(tmp_path)
    service.settings = service.settings.model_copy(update={
        'source_context_batch_size': 2, 'source_context_max_requests': 1})
    cores = [SourceRange(document_id='document', source_hash='a' * 64, start_line=line, end_line=line)
             for line in (3, 4)]

    class Client:
        async def evaluate(self, request):
            assert [item['core_block']['line_number'] for item in request.state['source_blocks']] == [3, 4]
            return JevResponse(model='jev-test', usage=TokenUsage(input_tokens=1, output_tokens=1),
                               answers={key: NoulAnswer(type='noul', noul=(.9 if key.endswith((
                                   '__evidence', '__sufficient', '__eligible__annual_profit')) else .05))
                                        for key in request.questions})

    service._client = lambda *args, **kwargs: Client()  # type: ignore[method-assign]
    result = await service.classify('context-run', document, [(core, None) for core in cores])

    assert result.calls == 1
    assert [item.core_range.start_line for item in result.decisions] == [3, 4]
    assert [item.call_id for item in result.decisions] == ['context-1', 'context-1']
    assert result.decisions[0].context_ranges != result.decisions[1].context_ranges


@pytest.mark.asyncio
async def test_unusable_context_response_persists_an_explicit_partial_state(tmp_path):
    _, document, service = _setup(tmp_path)
    core = SourceRange(document_id='document', source_hash='a' * 64, start_line=3, end_line=3)

    class Client:
        async def evaluate(self, request):
            # Jev returned a response, but omitted a required finite answer.  This
            # diagnostic must not turn into a chunk-score baseline failure.
            return JevResponse(model='jev-test', usage=TokenUsage(input_tokens=1, output_tokens=1),
                               answers={'evidence': NoulAnswer(type='noul', noul=.9)})

    service._client = lambda *args, **kwargs: Client()  # type: ignore[method-assign]
    result = await service.classify('context-run', document, [(core, None)])

    assert result.calls == 1
    assert result.partial == 1
    assert result.decisions[0].state == 'partial'
    assert result.decisions[0].response_scores == {}
    assert result.decisions[0].rationale == 'Jev source-context response was unusable: KeyError.'


def test_chunk_inspector_renders_bounded_context_graph_without_changing_baseline(tmp_path):
    from fastapi.testclient import TestClient

    from profitlab.v2.contracts import OutlineSection, SourceContextDecision, TextChunk
    from profitlab.web.app import create_app

    repo, document, _ = _setup(tmp_path)
    repo.save_canonical_document('context-run', document, b'<html></html>', b'<html></html>')
    core = SourceRange(document_id='document', source_hash='a' * 64, start_line=3, end_line=3)
    context = SourceRange(document_id='document', source_hash='a' * 64, start_line=2, end_line=2)
    repo.save_outline_sections('context-run', [OutlineSection(
        section_id='section', generated_topic='Income statement', primary_range=core)])
    repo.save_chunks('context-run', [TextChunk(chunk_id='chunk', section_id='section', core_range=core,
                                                request_size_estimate=1)])
    repo.save_source_context_decisions('context-run', [SourceContextDecision(
        decision_id='decision', block_id='block', core_range=core, context_ranges=[context],
        expansion_pass=1, role='evidence', target_eligibility={'annual_profit': True},
        context_sufficient=True, rationale='Visible header establishes the period.', confidence=.9,
        model='jev-test', call_id='call-1')])

    with TestClient(create_app(Settings(PROFITLAB_DATA_DIR=tmp_path,
                                        SEC_USER_AGENT='ProfitLab test@example.org', _env_file=None))) as client:
        response = client.get('/v2/runs/context-run/chunks/chunk')

    assert response.status_code == 200
    assert 'Adaptive source-context decisions' in response.text
    assert 'Flat chunk retention is unchanged' in response.text
    assert 'context →' in response.text
    assert 'expansion →</strong> pass 1 wider visible ring' in response.text
    assert 'Jev response scores: unavailable' in response.text


def test_source_row_replay_traces_persisted_loss_points_without_provider_inputs(tmp_path):
    from decimal import Decimal

    from profitlab.v2.contracts import FactComparison, Finding, ScoredItem, TextChunk

    repo, document, _ = _setup(tmp_path)
    repo.save_filing('context-run', 'filing', 'a' * 64, {
        'filing_id': 'filing', 'document_id': 'document', 'accession': 'accession',
        'report_date': '2025-12-31'})
    repo.save_canonical_document('context-run', document, b'<html></html>', b'<html></html>')
    core = SourceRange(document_id='document', source_hash='a' * 64, start_line=3, end_line=3)
    repo.save_chunks('context-run', [TextChunk(chunk_id='chunk', section_id='section', core_range=core,
                                                request_size_estimate=1)])
    repo.save_scores('context-run', 'chunk_score', [ScoredItem(
        item_id='chunk', target_scores={'annual_profit': .9}, model='jev', call_id='call',
        policy_decision='selected', policy_reason='test')])
    finding = Finding(finding_id='finding', exact_quote='Net income 123', source_range=core,
                      amount=Decimal(123), source_chunk_id='chunk', finding_type='annual_profit',
                      validation_state='validated')
    repo.save_findings('context-run', [finding])
    repo.save_comparisons('context-run', [FactComparison(
        comparison_id='comparison', metric='net_income_consolidated', finding_ids=['finding'],
        state='exact_match')])
    repo.save_exploration_action('context-run', 'findings-request', 'findings', 1, {
        'request': {'retained_chunks': [{'core_evidence_lines': [{'line_number': 3}]}]},
        'proposal_audit': [{'source_line': 3, 'quote_validated': True, 'validation_error': None,
                            'repair_attempted': False}],
    })
    dataset = SourceReplayDataset(dataset_version='test-v1', cases=[SourceReplayCase(
        case_id='case', ticker='CONTEXT', accession='accession', source_hash='a' * 64,
        rows=[ExpectedSourceRow(line_number=3, target='annual_profit', note='Reviewed row.')])])

    trace = SourceReplayService(repo, dataset).inspect('context-run')

    assert trace['proposal_audit_available'] is True
    assert trace['rows'] == [{
        'line_number': 3, 'target': 'annual_profit', 'note': 'Reviewed row.',
        'flat_retained': True, 'sent_to_findings': True, 'proposed': True,
        'quote_validated': True, 'classification': ['annual_profit'],
        'published': True, 'independent_match': True,
    }]


def test_checked_in_replay_set_pins_each_investigated_filing_and_source_row():
    dataset = load_source_replay_dataset()

    assert dataset.dataset_version == 't39-source-row-expectations-v2'
    cases = {item.ticker: item for item in dataset.cases}
    assert set(cases) == {'IWAL', 'CQP', 'VLOS', 'ATLC', 'NBHC', 'RANI'}
    assert all(len(item.rows) == 3 for item in cases.values())
    assert all({row.target for row in item.rows} == {
        'annual_profit', 'diluted_eps', 'diluted_shares'} for item in cases.values())
    # The source hash is an intentional membership boundary.  A refiled or otherwise
    # changed SEC HTML document must not silently inherit this reviewed row set.
    assert dataset.case_for(ticker='CQP', accession=cases['CQP'].accession,
                            source_hash='0' * 64) is None
