"""T39 range-bound adaptive context contracts."""
import asyncio
from datetime import UTC, datetime

from profitlab.providers.jev import JevResponse, NoulAnswer, TokenUsage
from profitlab.settings import Settings
from profitlab.v2.adaptive_context import AdaptiveContextService
from profitlab.v2.canonical import canonicalize_html
from profitlab.v2.contracts import AdaptiveSourceDecision, ScoredItem, SourceRange, TextChunk, V2Run
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.storage import V2Repository


class _DirectedClient:
    def __init__(self):
        self.requests = []

    async def evaluate(self, request):
        self.requests.append(request)
        answers = {key: NoulAnswer(type='noul', noul=0.01) for key in request.questions}
        for block in request.state['source_blocks']:
            prefix, expansion = block['block_id'], block['expansion_pass']
            if prefix == 'line-2':
                answers[f'{prefix}__evidence'] = NoulAnswer(type='noul', noul=.99)
                # Noul labels are independently scored; a related contextual
                # signal must not erase Jev's stronger evidence judgement.
                answers[f'{prefix}__contextual'] = NoulAnswer(type='noul', noul=.80)
                answers[f'{prefix}__relevant'] = NoulAnswer(type='noul', noul=.99)
                answers[f'{prefix}__annual_profit'] = NoulAnswer(type='noul', noul=.99)
                answers[f'{prefix}__sufficient'] = NoulAnswer(type='noul', noul=.99 if expansion else .01)
        return JevResponse(model='directed-jev', answers=answers,
                           usage=TokenUsage(input_tokens=1, output_tokens=1))


def test_adaptive_expansion_is_jev_directed_range_bound_and_visible_only(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='ProfitLab test@profitlab.test',
                        adaptive_context_initial_ring_lines=1, adaptive_context_max_expansion_passes=1,
                        _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='adaptive', ticker='ACME', created_at=now, updated_at=now))
    document, visible = canonicalize_html(
        b'<html><body><h1>Results</h1><p>Net income was 10.</p><p>Other text.</p></body></html>',
        document_id='doc-adaptive', filing_id='filing-adaptive')
    repo.save_canonical_document('adaptive', document, b'<html></html>', visible)
    repo.save_filing('adaptive', 'filing-adaptive', document.ref.source_hash, {'report_date': '2025-12-31'})
    client = _DirectedClient()
    monkeypatch.setattr(AdaptiveContextService, '_client', lambda self, run_id: client, raising=False)
    # Reuse the established accessor seam without constructing a configured live client.
    monkeypatch.setattr('profitlab.v2.section_scoring.SectionScoringService._client',
                        lambda self, run_id, stage='section_score': client)

    result = asyncio.run(AdaptiveContextService(settings, repo).classify(
        'adaptive', document, [], candidate_lines={2}))

    history = repo.adaptive_decisions('adaptive', line=2)
    assert [item.expansion_pass for item in history] == [0, 1]
    assert history[-1].role == 'evidence'
    assert history[-1].target_eligibility['annual_profit'] == 'eligible'
    assert history[-1].context_ranges[0].start_line == 1
    assert result.calls == 2
    assert all(set(item.state['source_blocks'][0]['source_lines'].values()) == {2}
               for item in client.requests)
    assert 'structured_facts' not in str(client.requests).lower()
    assert 'contextref' not in str(client.requests).lower()


def test_zero_adaptive_evidence_uses_labeled_flat_jev_baseline_for_findings(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='ProfitLab test@profitlab.test',
                        _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='fallback', ticker='ACME', created_at=now, updated_at=now))
    document, visible = canonicalize_html(b'<html><body><p>Net income was 10.</p></body></html>',
                                          document_id='doc-fallback', filing_id='filing-fallback')
    repo.save_canonical_document('fallback', document, b'<html></html>', visible)
    repo.save_filing('fallback', 'filing-fallback', document.ref.source_hash, {'report_date': '2025-12-31'})
    source_range = SourceRange(document_id=document.ref.document_id, source_hash=document.ref.source_hash,
                               start_line=1, end_line=1)
    chunk = TextChunk(chunk_id='chunk-fallback', section_id='section-fallback', core_range=source_range,
                      request_size_estimate=1)
    repo.save_adaptive_decisions('fallback', [AdaptiveSourceDecision(
        decision_id='decision-fallback', core_range=source_range, role='contextual', relevant=True,
        target_eligibility={'annual_profit': 'uncertain'}, context_sufficient=False,
        expansion_pass=0, confidence=.9, rationale='Needs context.', prompt_version='adaptive-context-v1')])
    repo.save_adaptive_summary('fallback', {'retention_mode': 'flat_baseline_no_direct_adaptive_evidence'})
    score = ScoredItem(item_id='chunk-fallback', target_scores={'annual_profit': .9}, model='jev',
                       call_id='baseline', policy_decision='selected', policy_reason='baseline')

    state = FindingsService(settings, repo)._request_data('fallback', document, [chunk], [score])

    assert state['retained_chunks'][0]['core_evidence_lines'][0]['line_number'] == 1
