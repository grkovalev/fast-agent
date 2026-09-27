"""T41 contracts: bounded visible core packets and auditable request exclusions."""
from datetime import UTC, datetime

import pytest

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef, ScoredItem, SourceRange, TextChunk, V2Run
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.pipeline import V2PipelineService
from profitlab.v2.storage import V2Repository


def _setup(tmp_path, **setting_overrides):
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='packets-run', ticker='PACKETS', created_at=now, updated_at=now))
    repo.save_filing('packets-run', 'filing', 'a' * 64,
                     {'filing_id': 'filing', 'report_date': '2025-12-31'})
    ref = CanonicalDocumentRef(document_id='document', filing_id='filing', source_hash='a' * 64,
                               line_count=5)
    document = CanonicalDocument(ref=ref, lines=[
        CanonicalLine(line_number=1, text='Consolidated statements of operations', element_type='heading',
                      html_anchor='line-1', dom_reference='/h[1]'),
        CanonicalLine(line_number=2, text='Year ended December 31, 2025', element_type='table_row',
                      html_anchor='line-2', dom_reference='/tr[2]'),
        CanonicalLine(line_number=3, text='Net income 100', element_type='table_row',
                      html_anchor='line-3', dom_reference='/tr[3]'),
        CanonicalLine(line_number=4, text='Diluted EPS 2.00', element_type='table_row',
                      html_anchor='line-4', dom_reference='/tr[4]'),
        CanonicalLine(line_number=5, text='Notes follow', element_type='paragraph',
                      html_anchor='line-5', dom_reference='/p[5]'),
    ])
    chunk = TextChunk(chunk_id='chunk', section_id='section', core_range=SourceRange(
        document_id='document', source_hash='a' * 64, start_line=1, end_line=5), request_size_estimate=1)
    score = ScoredItem(item_id='chunk', target_scores={'annual_profit': .9}, model='jev',
                       call_id='call', policy_decision='selected', policy_reason='test')
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='ProfitLab test@example.org',
                        findings_packet_max_cores=2, findings_packet_uncertainty_reserve=1,
                        _env_file=None, **setting_overrides)
    return repo, document, chunk, score, FindingsService(settings, repo), settings


def test_packets_are_target_shaped_with_a_measured_non_target_reserve(tmp_path):
    _, document, chunk, score, service, _ = _setup(tmp_path)
    packets, candidates = service._packet_plan(document, [chunk], [score])

    assert [core['source_line'] for packet in packets for core in packet['cores']] == [1, 3, 4]
    assert [core['selection_kind'] for packet in packets for core in packet['cores']] == [
        'uncertainty_reserve', 'target_shaped', 'target_shaped']
    assert candidates[-1]['source_line'] == 5
    assert candidates[-1]['selection_kind'] == 'uncertainty_reserve'
    # Context is visible orientation, separately represented from the citable core.
    core = packets[0]['cores'][1]
    assert core['core_line']['line_number'] == 3
    assert all(item['line_number'] != 3 for item in core['context_lines'])


@pytest.mark.asyncio
async def test_packet_audit_records_size_exclusion_and_context_cannot_be_cited(tmp_path):
    repo, document, chunk, score, service, _ = _setup(tmp_path, findings_request_char_budget=1800)
    # Make the compact request fit only its initial packet; source line 4 remains a
    # target-shaped candidate but is explicitly excluded by the request-size budget.
    state, candidates, packets = service._request_data('packets-run', document, [chunk], [score])
    assert state['context_fallback'] is True
    selection = service._selection_audit([chunk], [score], state, candidates, packets)
    assert any(item['size_budget_exclusion'] == 'packet excluded by findings request size budget'
               for item in selection)
    assert next(item for item in selection if item['line_number'] == 2) == {
        'line_number': 2, 'packet_id': None,
        'core_inclusion': 'not_in_bounded_uncertainty_reserve',
        'request_state': 'not_selected_for_packet_reserve',
        'size_budget_exclusion': None, 'proposal_count': 0,
        'quote_validated_count': 0, 'classification': [],
    }

    async def live(state, repair=None):
        return ([{'source_chunk_id': 'chunk', 'source_line': 5, 'exact_quote': 'Notes follow',
                  'amount': '5', 'limitations': []}], 'llm-test')

    async def no_classification(run_id, document, chunks, findings):
        return findings, 0, 0, []

    service._live = live  # type: ignore[method-assign]
    service._classify = no_classification  # type: ignore[method-assign]
    result = await service.build('packets-run', document, [chunk], [score])
    assert result.findings == []
    action = repo.exploration_actions('packets-run', 'findings')[0]
    assert action['packet_audit']['packet_version'] == 'findings-core-packets-v1'
    assert action['proposal_audit'][0]['validation_error'] == (
        'source line was not included as an independently citable request core')


def test_packet_configuration_is_in_the_run_version(tmp_path):
    common = {'PROFITLAB_DATA_DIR': tmp_path, 'SEC_USER_AGENT': 'ProfitLab test@example.org',
              'PROFITLAB_APPLICATION_REVISION': 't41-contract', '_env_file': None}
    first = V2PipelineService(Settings(**common)).create('FIRST')
    changed = V2PipelineService(Settings(**{**common, 'findings_packet_max_cores': 3})).create('SECOND')

    assert first.version_id != changed.version_id
    assert first.version_components['findings_packet_version'] == 'findings-core-packets-v1'
    assert first.version_components['findings_request_char_budget'] == '60000'
