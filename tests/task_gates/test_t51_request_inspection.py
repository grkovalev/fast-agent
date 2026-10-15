"""Provider inspectors must use the same bounded builders as runtime calls."""
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2.chunk_scoring import ChunkScoringService
from profitlab.v2.contracts import V2Run
from profitlab.v2.evaluation_service import EvaluationService
from profitlab.v2.findings_service import FindingsService
from profitlab.v2.outline_service import OutlineService
from profitlab.v2.section_scoring import SectionScoringService
from profitlab.v2.storage import V2Repository
from profitlab.web.app import create_app


def test_inspected_requests_use_runtime_builders_and_current_configuration(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None)
    outline = OutlineService.inspection_view(settings)['propose']['request']
    assert outline['messages'] == OutlineService._messages(
        OutlineService._inspection_document(), 1, 1, [])
    assert outline['model'] == settings.outline_model
    assert 'illustrative' in outline['kind']
    proposal = OutlineService._example_proposal().model_dump()
    assert OutlineService(settings, None)._validate(
        OutlineService._inspection_document(), 1, 1, proposal)[1] is None

    for service, station in ((SectionScoringService, 'score'),
                             (ChunkScoringService, 'score')):
        displayed = service.inspection_view(settings)[station]['request']
        payload = displayed['state']['sections' if station == 'score' and service is SectionScoringService
                                     else 'chunks']
        if service is SectionScoringService:
            from profitlab.v2.section_scoring import JevVisibleContext
            actual = service(settings, None)._request(
                [JevVisibleContext.model_validate(payload[0])])
        else:
            actual = service(settings, None)._request(payload)
        assert {key: displayed[key] for key in ('model', 'state', 'questions')} == actual.model_dump(mode='json')

    findings = FindingsService.inspection_view(settings)
    from profitlab.v2.findings_examples import safe_findings_examples
    example = safe_findings_examples(settings.findings_policy)
    assert findings['convert']['request']['example'] == example['conversion_request'].model_dump(mode='json')
    assert findings['assign_lines']['request']['example'] == example['assignment_request'].model_dump(mode='json')

    verify = EvaluationService.inspection_view(settings)['verify']['request']
    assert verify['questions']['same_visible_scaled_value']['instructions'] == (
        'Are these the same annual metric/value after an explicitly visible scale or unit?')
    assert verify['state']['finding']['amount'] == '100'
    assert verify['state']['structured_fact']['amount'] == '100000'


def test_pipeline_renders_configured_requests_without_credentials(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, LLM_API_KEY='inspection-secret',
                        _env_file=None)
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='request-inspection', ticker='TEST',
                          created_at=now, updated_at=now))
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/request-inspection/pipeline').text
    assert 'selected_bundles' in page
    assert 'same_visible_scaled_value' in page
    assert 'illustrative request built with current configuration' in page
    assert 'inspection-secret' not in page
