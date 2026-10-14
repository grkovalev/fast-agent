"""Findings publication and its overview use the same branch semantics."""
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.canonical import CanonicalDocument, CanonicalLine
from profitlab.v2.contracts import CanonicalDocumentRef, SourceRange, TextChunk, V2Run
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_findings_overview_explains_branches_and_uses_service_limits(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, findings_request_char_budget=12345,
                        findings_max_requests=3, _env_file=None)
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='findings-map', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/findings-map/pipeline').text
    region = page.split('data-findings-card', 1)[1].split('data-evaluate-card', 1)[0]
    assert 'within 12345 characters' in region
    assert 'maximum 3 requests' in region
    assert region.index('Retained chunk cores') < region.index('Bound the request')
    assert region.index('The initial candidates are discarded') < region.index('Deduplicate quote and amount')
    assert region.index('Deduplicate quote and amount') < region.index('JEV TYPE CLASSIFIER')
    assert region.index('JEV TYPE CLASSIFIER') < region.index('Seal Finding records')
    assert 'only core lines can be cited' in region
    assert 'SEC Company Facts and evaluation values do not enter this request' in region
    assert 'The set may be empty' in region
    from lxml import html
    card = html.fromstring(page).xpath('//*[@data-findings-card]')[0]
    example, = card.xpath('.//*[@data-findings-cardinality]')
    assert 'Not saved run data' in example.text_content()
    assert 'A: 2 · B: 0 · C: 1' in example.text_content()
    assert not example.xpath('.//details | .//template | .//*[@hidden]')
    visible = card.xpath('.//*[@data-findings-station="assemble"]')[0].text_content()
    assert visible.index('full outline') < visible.index('pack complete chunks') < visible.index('no preceding context')
    assert 'reduce context, then' not in visible
    for phrase in ('current fiscal-reporting year', 'finite Decimal',
                   'including initially accepted ones', 'Keep the first candidate',
                   'zero or multiple types', 'Per-request size overflow',
                   'Unresolved type alone does not reject'):
        assert phrase in card.text_content()
    classify = card.xpath('.//*[@data-findings-station="classify"]')[0].text_content()
    for name in ('shareholder', 'diluted EPS', 'weighted-average shares'):
        assert name in classify
    for station in ('assemble', 'propose', 'validate', 'classify', 'publish'):
        assert f'data-findings-station="{station}"' in region
    assert 'data-station-card' in region
    for station in ('propose', 'validate', 'classify', 'publish'):
        assert f'data-station-template="{station}"' in region
    view = FindingsService.inspection_view(settings)
    assert view['validate']['policy']['repair_result'].startswith('replacement')
    assert view['classify']['request']['model'] == settings.typesafe_model
    assert view['propose']['request']['model'] == settings.llm_model
    assert view['classify']['policy']['type_support_threshold'] == settings.chunk_score_keep_threshold
    assert tuple(view['classify']['policy']['allowed_types']) == FindingsService.FINDING_TYPES
    assert 'not strictly' in view['validate']['limitations']
    assert 'not independently source-verified' in view['validate']['limitations']
    assert 'total classification-call budget' in view['classify']['limitations']


@pytest.mark.asyncio
async def test_repair_replaces_initial_candidates_before_dedup_and_classification(tmp_path,
                                                                                   monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    ref = CanonicalDocumentRef(document_id='doc', filing_id='filing',
                               source_hash='0' * 64, line_count=1)
    document = CanonicalDocument(ref=ref, lines=[CanonicalLine(
        line_number=1, text='Net income was $12.50 and EPS was $2.50.',
        element_type='paragraph', html_anchor='line-1', dom_reference='/html/body/p[1]')])
    chunk = TextChunk(chunk_id='chunk-1', section_id='section-1',
                      core_range=SourceRange(document_id='doc', source_hash='0' * 64,
                                             start_line=1, end_line=1), request_size_estimate=80)
    class Repo:
        def __init__(self):
            self.saved = None
            self.summary = None
            self.steps = {}

        def finding_batch(self, *_args):
            return None

        def save_finding_batch(self, *_args):
            pass

        def save_findings(self, _run_id, findings):
            self.saved = findings

        def save_finding_summary(self, _run_id, summary):
            self.summary = summary

        def save_exploration_action(self, _run_id, action_id, _stage, _sequence, payload):
            self.steps[action_id] = payload

    repo = Repo()
    service = FindingsService(settings, repo)
    state = {'retained_chunks': [{'chunk_id': 'chunk-1', 'core_evidence_lines':
        service._evidence_csv([{'line_number': 1, 'text': document.lines[0].text}])}],
        'validated_outline': [], 'context_fallback': False,
        'filing_metadata': {'current_report_year': '2025'}}
    monkeypatch.setattr(service, '_request_data', lambda *_args: state)
    valid = {'source_chunk_id': 'chunk-1', 'source_line': 1,
             'exact_quote': '$12.50', 'amount': '12.50'}
    invalid = {**valid, 'source_line': 2}
    repair = {**valid, 'exact_quote': '$2.50', 'amount': '2.50'}
    requests = []

    async def live(_state, rejected=None):
        requests.append(rejected)
        return ([valid, invalid] if rejected is None else [repair, repair]), 'model'

    async def classify(_run_id, _document, _chunks, findings):
        assert len(findings) == 1
        assert findings[0].exact_quote == '$2.50'
        return findings, 0, 0

    monkeypatch.setattr(service, '_live', live)
    monkeypatch.setattr(service, '_classify', classify)
    result = await service.build('run', document, [chunk], [])
    assert result.calls == 2
    assert len(requests[1]) == 1
    assert repo.summary['rejected'] == 0
    assert len(repo.saved) == 1
    assert repo.saved[0].repair_attempted is True
    assert repo.saved[0].exact_quote == '$2.50'
    assert repo.summary['retained_evidence_characters'] == len(document.lines[0].text)
    proposal_result = repo.steps['findings-step-propose']['result']
    assert proposal_result['initial_proposals'] == [valid, invalid]
    assert proposal_result['replacement_proposals'] == [repair, repair]
    validation = repo.steps['findings-step-validate']['result']
    assert len(validation['initial']['rejected']) == 1
    assert validation['repair_attempted'] is True
    assert validation['final_rejected'] == []
    assert validation['deduplicated_count'] == 1
    assert validation['final_accepted'][0]['exact_quote'] == '$2.50'
    assert repo.steps['findings-step-classify']['result']['count'] == 1
    assert repo.steps['findings-step-publish']['result']['findings'][0]['exact_quote'] == '$2.50'

    # Complete cached types bypass Jev without changing a validated unresolved result.
    monkeypatch.setattr(repo, 'finding_batch', lambda *_a: {
        'findings': [repair, repair], 'model': 'model',
        'finding_types': {repo.saved[0].finding_id: 'unresolved'}})

    async def no_provider(*_a):
        raise AssertionError('Complete extraction/type cache must avoid provider calls')

    monkeypatch.setattr(service, '_live', no_provider)
    monkeypatch.setattr(service, '_classify', no_provider)
    cached_result = await service.build('run', document, [chunk], [])
    assert cached_result.cached is True and cached_result.calls == 0
    assert len(repo.saved) == 1 and repo.saved[0].finding_type == 'unresolved'


def test_findings_step_results_render_saved_data_and_legacy_availability(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='step-results', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    repo.save_exploration_action('step-results', 'findings-request', 'findings', 1,
                                 {'request': {'retained_chunks': [{'chunk_id': 'saved-core'}]}})
    with TestClient(create_app(settings)) as client:
        legacy = client.get('/v2/runs/step-results/pipeline').text
        assert 'saved-core' in legacy
        assert 'No saved result for this step' in legacy
        for sequence, step in enumerate(('assemble', 'propose', 'validate', 'classify', 'publish')):
            repo.save_exploration_action('step-results', f'findings-step-{step}',
                                         'findings', sequence + 10,
                                         {'result': {'count': 25, 'findings': [
                                             {'exact_quote': f'{step}-result-{i}'} for i in range(25)]}})
        overview = client.get('/v2/runs/step-results/pipeline').text
        selected = client.get('/v2/runs/step-results/pipeline?stage=findings').text
    for page in (overview, selected):
        assert page.count('data-findings-run-result') == 5
        for step in ('assemble', 'propose', 'validate', 'classify', 'publish'):
            assert f'{step}-result-19' in page
            assert f'{step}-result-20' not in page
        assert 'Bounded preview' in page


@pytest.mark.asyncio
async def test_findings_empty_budget_records_skipped_steps(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    repo = V2Repository(tmp_path)
    repo.create_run(V2Run(run_id='empty-results', ticker='MAP',
                          created_at=datetime.now(UTC), updated_at=datetime.now(UTC)))
    service = FindingsService(settings, repo)
    monkeypatch.setattr(service, '_request_data', lambda *_args: {
        'retained_chunks': [], 'validated_outline': [], 'context_fallback': True,
        'filing_metadata': {'current_report_year': '2025'}})
    result = await service.build('empty-results', None, [], [])
    assert result.calls == 0
    actions = {item['action_id']: item for item in
               repo.exploration_actions('empty-results', 'findings')}
    for step in ('propose', 'validate', 'classify'):
        assert 'skipped' in actions[f'findings-step-{step}']['result']
    assert actions['findings-step-publish']['result'] == {'count': 0, 'findings': []}


def test_extraction_core_csv_preserves_source_text_and_measures_serialized_budget(tmp_path):
    import csv
    import io
    import json
    from types import SimpleNamespace

    from profitlab.v2.contracts import ScoredItem

    text = 'Net income, "current year": $1,234.50.\nSecond visible line.'
    ref = CanonicalDocumentRef(document_id='csv-doc', filing_id='filing',
                               source_hash='0' * 64, line_count=1)
    document = CanonicalDocument(ref=ref, lines=[CanonicalLine(
        line_number=1, text=text, element_type='paragraph',
        html_anchor='line-1', dom_reference='/html/body/p[1]')])
    chunk = TextChunk(chunk_id='csv-chunk', section_id='section',
                      core_range=SourceRange(document_id='csv-doc', source_hash='0' * 64,
                                             start_line=1, end_line=1), request_size_estimate=80)
    repo = SimpleNamespace(filing=lambda _: {'report_date': '2025-12-31'},
                           get_run=lambda _: SimpleNamespace(ticker='CSV'),
                           outline_sections=lambda _: [])
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    service = FindingsService(settings, repo)
    score = ScoredItem(item_id='csv-chunk', model='test', call_id='test',
                       target_scores={'annual_profit': 1.0}, policy_decision='selected',
                       policy_reason='Relevant core evidence')
    state = service._request_data('csv-run', document, [chunk], [score])
    evidence = state['retained_chunks'][0]['core_evidence_lines']
    assert isinstance(evidence, str)
    assert evidence.startswith('line_number,text\n')
    assert list(csv.DictReader(io.StringIO(evidence, newline=''))) == [
        {'line_number': '1', 'text': text}]
    assert json.loads(json.dumps(state))['retained_chunks'][0]['core_evidence_lines'] == evidence
    assert 'a CSV string with line_number,text columns' in service._prompt(state)
    settings.findings_request_char_budget = len(json.dumps(state, ensure_ascii=False))
    assert service._request_data('csv-run', document, [chunk], [score])['retained_chunks']
    settings.findings_request_char_budget -= 1
    fallback = service._request_data('csv-run', document, [chunk], [score])
    assert fallback['context_fallback'] is True
    assert len(json.dumps(fallback, ensure_ascii=False)) == settings.findings_request_char_budget
    settings.findings_request_char_budget -= 1
    assert service._request_data('csv-run', document, [chunk], [score])['retained_chunks'] == []

    # Dropping whole chunks precedes removal of preceding context/full navigation.
    settings.findings_request_char_budget = 100000
    chunk = chunk.model_copy(update={'context_ranges': [chunk.core_range]})
    second = chunk.model_copy(update={'chunk_id': 'lower-score'})
    scores = [score, score.model_copy(update={'item_id': second.chunk_id,
                                            'target_scores': {'annual_profit': .9}})]
    from profitlab.v2.contracts import OutlineSection
    outline = OutlineSection(section_id='section', generated_topic='Navigation ' * 100,
                             primary_range=chunk.core_range)
    repo.outline_sections = lambda _: [outline]
    full = service._request_data('csv-run', document, [second, chunk], scores)
    assert len(full['retained_chunks']) == 2 and full['context_fallback'] is False
    single = {**full, 'retained_chunks': [full['retained_chunks'][1]], 'context_fallback': True}
    settings.findings_request_char_budget = len(json.dumps(single, ensure_ascii=False))
    packed = service._request_data('csv-run', document, [second, chunk], scores)
    assert [item['chunk_id'] for item in packed['retained_chunks']] == [chunk.chunk_id]
    assert packed['validated_outline'] == full['validated_outline']
    assert packed['retained_chunks'][0]['context_lines']
    # Extra navigation crowds out even a single complete chunk, but compact core fits.
    extra = outline.model_copy(update={'section_id': 'unrelated', 'generated_topic': 'Other ' * 500})
    repo.outline_sections = lambda _: [outline, extra]
    compact = service._request_data('csv-run', document, [second, chunk], scores)
    assert [item['chunk_id'] for item in compact['retained_chunks']] == [chunk.chunk_id]
    assert compact['retained_chunks'][0]['context_lines'] == []
    assert compact['validated_outline'] == [service._outline_entry(outline)]
    settings.findings_request_char_budget = len(json.dumps(compact, ensure_ascii=False)) - 1
    assert service._request_data('csv-run', document, [second, chunk], scores)['retained_chunks'] == []


@pytest.mark.asyncio
async def test_type_classification_threshold_and_failure_limits(tmp_path, monkeypatch):
    from decimal import Decimal
    from types import SimpleNamespace

    from profitlab.v2.contracts import Finding
    from profitlab.v2.section_scoring import SectionScoringService

    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    service = FindingsService(settings, None)
    finding = Finding(finding_id='type-example', exact_quote='100', amount=Decimal(100),
                      source_range=SourceRange(document_id='doc', source_hash='0' * 64,
                                               start_line=1, end_line=1),
                      validation_state='validated')
    threshold = settings.chunk_score_keep_threshold
    vectors = iter([(threshold, 0, 0), (0, 0, 0), (threshold, threshold, 0)])

    async def evaluate(_request):
        return SimpleNamespace(answers={name: SimpleNamespace(noul=score)
                               for name, score in zip(service.FINDING_TYPES, next(vectors))})

    monkeypatch.setattr(SectionScoringService, '_client', lambda *_a, **_k:
                        SimpleNamespace(evaluate=evaluate))
    monkeypatch.setattr(service, '_classification_request', lambda *_a: object())
    typed, calls, limited = await service._classify('run', None, [], [finding] * 3)
    assert [item.finding_type for item in typed] == ['annual_profit', 'unresolved', 'unresolved']
    assert calls == 3 and limited == 0

    def overflow(*_a):
        raise ValueError('Finding-type request exceeds the configured visible-context budget.')

    monkeypatch.setattr(service, '_classification_request', overflow)
    typed, calls, limited = await service._classify('run', None, [], [finding])
    assert typed == [finding] and typed[0].finding_type == 'unresolved'
    assert calls == 0 and limited == 1
    settings.finding_type_max_requests = 1
    with pytest.raises(ValueError, match='provider-call budget'):
        await service._classify('run', None, [], [finding] * 2)

    async def failed(_request):
        raise RuntimeError('controlled provider failure')

    monkeypatch.setattr(service, '_classification_request', lambda *_a: object())
    monkeypatch.setattr(SectionScoringService, '_client', lambda *_a, **_k:
                        SimpleNamespace(evaluate=failed))
    with pytest.raises(RuntimeError, match='provider failure'):
        await service._classify('run', None, [], [finding])
