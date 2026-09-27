"""T40 contracts for bounded citation repair preservation."""
from datetime import UTC, datetime

import pytest

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef, ScoredItem, SourceRange, TextChunk, V2Run
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.storage import V2Repository


def _setup(tmp_path):
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='repair-run', ticker='REPAIR', created_at=now, updated_at=now))
    repo.save_filing('repair-run', 'filing', 'a' * 64,
                     {'filing_id': 'filing', 'report_date': '2025-12-31'})
    ref = CanonicalDocumentRef(document_id='document', filing_id='filing', source_hash='a' * 64,
                               line_count=2)
    document = CanonicalDocument(ref=ref, lines=[
        CanonicalLine(line_number=1, text='Net income 100', element_type='table_row',
                      html_anchor='line-1', dom_reference='/tr[1]'),
        CanonicalLine(line_number=2, text='Diluted EPS 2.00', element_type='table_row',
                      html_anchor='line-2', dom_reference='/tr[2]'),
    ])
    chunk = TextChunk(chunk_id='chunk', section_id='section', core_range=SourceRange(
        document_id='document', source_hash='a' * 64, start_line=1, end_line=2),
        request_size_estimate=1)
    score = ScoredItem(item_id='chunk', target_scores={'annual_profit': .9}, model='jev',
                       call_id='call', policy_decision='selected', policy_reason='test')
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='ProfitLab test@example.org',
                        _env_file=None)
    return repo, document, chunk, score, FindingsService(settings, repo)


async def _no_classification(run_id, document, chunks, findings):
    return findings, 0, 0, []


@pytest.mark.asyncio
async def test_valid_first_pass_finding_survives_failed_citation_repair(tmp_path):
    repo, document, chunk, score, service = _setup(tmp_path)
    valid = {'source_chunk_id': 'chunk', 'source_line': 1, 'exact_quote': 'Net income 100',
             'amount': '100', 'limitations': []}
    invalid = {'source_chunk_id': 'chunk', 'source_line': 2, 'exact_quote': 'invented 3.00',
               'amount': '3.00', 'limitations': []}
    calls = []

    async def live(state, repair=None):
        calls.append(repair)
        return ([valid, invalid] if repair is None else [invalid]), 'llm-test'

    service._live = live  # type: ignore[method-assign]
    service._classify = _no_classification  # type: ignore[method-assign]

    result = await service.build('repair-run', document, [chunk], [score])

    assert [(item.exact_quote, item.repair_attempted) for item in result.findings] == [
        ('Net income 100', False)]
    assert result.rejected == 1
    assert len(calls) == 2
    assert calls[1] == [{'proposal': invalid,
                         'reason': 'quote is not an exact substring in the declared core evidence line'}]
    audit = repo.exploration_actions('repair-run', 'findings')[0]['proposal_audit']
    assert [item['outcome'] for item in audit] == [
        'first_pass_valid_finding', 'invalid_proposal', 'invalid_proposal']
    assert [item['repair_attempted'] for item in audit] == [False, False, True]


@pytest.mark.asyncio
async def test_repaired_findings_merge_with_first_pass_without_duplicate(tmp_path):
    repo, document, chunk, score, service = _setup(tmp_path)
    first_pass = {'source_chunk_id': 'chunk', 'source_line': 1, 'exact_quote': 'Net income 100',
                  'amount': '100', 'limitations': []}
    invalid = {'source_chunk_id': 'chunk', 'source_line': 2, 'exact_quote': 'wrong quote',
               'amount': '2.00', 'limitations': []}
    repaired = {'source_chunk_id': 'chunk', 'source_line': 2, 'exact_quote': 'Diluted EPS 2.00',
                'amount': '2.00', 'limitations': []}

    async def live(state, repair=None):
        return ([first_pass, invalid] if repair is None else [first_pass, repaired]), 'llm-test'

    service._live = live  # type: ignore[method-assign]
    service._classify = _no_classification  # type: ignore[method-assign]

    result = await service.build('repair-run', document, [chunk], [score])

    assert [(item.exact_quote, item.repair_attempted) for item in result.findings] == [
        ('Net income 100', False), ('Diluted EPS 2.00', True)]
    assert result.rejected == 0
    audit = repo.exploration_actions('repair-run', 'findings')[0]['proposal_audit']
    assert [item['outcome'] for item in audit] == [
        'first_pass_valid_finding', 'invalid_proposal',
        'repair_produced_finding', 'repair_produced_finding']
