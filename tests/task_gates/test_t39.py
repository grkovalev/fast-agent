"""T39 source-context contracts: bounded visible ranges and no hidden inputs."""
from datetime import UTC, datetime

import pytest

from profitlab.providers.jev import JevResponse, NoulAnswer, TokenUsage
from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef, SourceRange, V2Run
from profitlab.v2.pipeline import V2PipelineService
from profitlab.v2.source_context import SourceContextService
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
    assert saved[0].core_range.start_line == saved[0].core_range.end_line == 3
    assert all(item.start_line != 3 and item.end_line != 3 for item in saved[0].context_ranges)


def test_source_context_configuration_is_versioned(tmp_path):
    common = {'PROFITLAB_DATA_DIR': tmp_path, 'SEC_USER_AGENT': 'ProfitLab test@example.org',
              'PROFITLAB_APPLICATION_REVISION': 'context-revision', '_env_file': None}
    baseline = V2PipelineService(Settings(**common)).create('BASE')
    changed = V2PipelineService(Settings(**{**common, 'source_context_rings': (3, 12, 30)})).create('CHANGE')

    assert baseline.version_id != changed.version_id
    assert baseline.version_components['source_context_rings'] == '(2, 8, 24)'
