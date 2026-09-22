"""T17 visible-only Jev section discovery contracts and workspace path."""
import asyncio

from fastapi.testclient import TestClient

from profitlab.providers.jev import JevResponse
from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService, canonicalize_html
from profitlab.v2.outline_service import OutlineService
from profitlab.v2.section_scoring import SectionScoringService
from profitlab.web.app import create_app


def test_section_scores_use_only_allowlisted_visible_context_and_stable_policy(tmp_path, monkeypatch):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, section_score_batch_size=2,
                        section_score_max_selected=2, section_score_max_uncertain=1)
    pipeline = V2PipelineService(settings)
    run = pipeline.create(run_id='section-policy')
    document, _ = canonicalize_html(b'''<html><body><h1>Results</h1><p>Net income was 10.</p>
        <h2>EPS</h2><p>Diluted EPS was 2.</p><h2>Restatement</h2><p>Comparable.</p>
        <h2>Other</h2><p>Background.</p></body></html>''', document_id='document-score',
                                    filing_id='filing-score')
    pipeline.repo.save_canonical_document(run.run_id, document, b'<html/>', b'<html/>')
    sections, *_ = asyncio.run(OutlineService(settings, pipeline.repo).build(document, offline=True))
    pipeline.repo.save_outline_sections(run.run_id, sections)
    service = SectionScoringService(settings, pipeline.repo)
    requests = []

    class Client:
        async def evaluate(self, request):
            requests.append(request)
            assert set(request.state) == {'sections', 'source_rule'}
            for context in request.state['sections']:
                assert set(context) == {'section_id', 'generated_topic', 'exact_visible_heading',
                                        'size', 'short_exact_preview', 'filing_metadata'}
                assert 'contextref' not in str(context).lower()
            answers = {}
            for key in request.questions:
                target = key.rsplit('__', 1)[1]
                score = (.9 if ('000001' in key and target == 'annual_profit') or
                         ('000003' in key and target == 'diluted_eps') else
                         .3 if '000007' in key else .01)
                answers[key] = {'type': 'noul', 'noul': score}
            return JevResponse.model_validate({'model': 'controlled-jev', 'answers': answers,
                                               'usage': {'input_tokens': 7, 'output_tokens': 3}})

    monkeypatch.setattr(service, '_client', lambda *_args: Client())
    result = asyncio.run(service.score(run.run_id, document, sections, offline=True))
    assert len(requests) == 2 and result.usage == {'input_tokens': 14, 'output_tokens': 6}
    assert [item.policy_decision for item in result.scores] == ['selected', 'selected', 'skipped', 'uncertain']
    assert 'covers annual_profit' in result.scores[0].policy_reason
    assert service.repo.scores(run.run_id, 'section_score') == result.scores
    assert service.repo.exploration_actions(run.run_id, 'section_score') == []
    with __import__('pytest').raises(ValueError, match='forbidden'):
        service._guard({'sections': [{'short_exact_preview': 'contextRef=forbidden'}]})
    service._guard({'sections': [{'short_exact_preview': 'Management evaluation is discussed.'}]})
    with __import__('pytest').raises(ValueError, match='forbidden field'):
        service._guard({'evaluation': {'expected_value': 'not allowed'}})


def test_section_batches_split_to_the_visible_request_budget(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                        section_score_batch_size=8, section_score_request_char_budget=2100)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='section-budget')
    document, _ = canonicalize_html((b'<html><body><h1>One</h1><p>' + b'A' * 580 +
                                    b'</p><h2>Two</h2><p>' + b'B' * 580 +
                                    b'</p></body></html>'), document_id='document-budget',
                                    filing_id='filing-budget')
    sections, *_ = asyncio.run(OutlineService(settings, pipeline.repo).build(document, offline=True))
    service = SectionScoringService(settings, pipeline.repo)
    contexts = [service._context(section, document, {'ticker': 'DEMO', 'filing_id': 'filing-budget'})
                for section in sections]
    batches = service._batches(contexts, offline=True)
    assert len(batches) == 2
    assert all(len(__import__('json').dumps(service._request(batch, True).model_dump(mode='json'))) <= 2100
               for batch in batches)


def test_offline_section_score_persists_and_is_inspectable_in_workspace(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, outline_window_lines=100,
                        section_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='section-offline')
    asyncio.run(pipeline.run('section-offline', implement_source=True))
    stage = pipeline.repo.stage('section-offline', 'section_score')
    scores = pipeline.repo.scores('section-offline', 'section_score')
    actions = pipeline.repo.exploration_actions('section-offline', 'section_score')
    assert stage.status == 'completed' and scores and actions
    assert all(item.policy_decision == 'selected' for item in scores)
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/section-offline?stage=section_score')
    assert page.status_code == 200
    assert 'Ranked visible sections' in page.text
    assert 'No XBRL, Company Facts, or evaluation values are supplied' in page.text
    assert 'Inspect sanitized provider trace' in page.text
