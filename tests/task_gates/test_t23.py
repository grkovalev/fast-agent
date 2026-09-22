"""T23 keeps primary pages reader-facing and bounds repeated stage data."""
import asyncio

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.web.app import create_app


def settings_for(tmp_path):
    return Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                    chunk_target_tokens=100, chunk_overlap_tokens=40,
                    chunk_question_overhead=500, chunk_request_budget=1000,
                    outline_window_lines=100, section_score_batch_size=2)


def test_pipeline_is_the_single_run_view_with_on_demand_diagnostics(tmp_path):
    settings = settings_for(tmp_path)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='ui-t23')
    asyncio.run(pipeline.run('ui-t23', implement_source=True))
    with TestClient(create_app(settings)) as client:
        findings_page = client.get('/v2/runs/ui-t23/pipeline?stage=findings')
        evaluation_page = client.get('/v2/runs/ui-t23/pipeline?stage=evaluate')
        trace_page = client.get('/v2/runs/ui-t23/pipeline/findings/trace')
        report_page = client.get('/v2/runs/ui-t23/report')
        standalone_evaluation = client.get('/v2/runs/ui-t23/evaluation')
    assert findings_page.status_code == evaluation_page.status_code == 200
    assert 'Runs' in findings_page.text and 'Pipeline' in findings_page.text
    assert 'Quote-backed findings' in findings_page.text
    assert 'Independent fiscal-year comparison' in evaluation_page.text
    assert report_page.status_code == standalone_evaluation.status_code == 404
    assert trace_page.status_code == 200
    assert 'On-demand diagnostic' in trace_page.text


def test_storage_pages_cap_repeated_records_at_one_hundred(tmp_path):
    settings = settings_for(tmp_path)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='page-t23')
    asyncio.run(pipeline.run('page-t23', implement_source=True))
    sections = pipeline.repo.outline_sections('page-t23')
    first = sections[0]
    many = [first.model_copy(update={'section_id': f'page-section-{number}'})
            for number in range(101)]
    pipeline.repo.save_outline_sections('page-t23', many)
    assert len(pipeline.repo.outline_sections('page-t23', page=1)) == 100
    assert len(pipeline.repo.outline_sections('page-t23', page=2)) == 1
