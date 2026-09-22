"""T24 preserves decisions while reusing persisted provider work."""
import asyncio

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.web.app import create_app


def settings_for(tmp_path):
    return Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None,
                    chunk_target_tokens=100, chunk_overlap_tokens=40,
                    chunk_question_overhead=500, chunk_request_budget=1000,
                    outline_window_lines=100, section_score_batch_size=2,
                    v2_provider_concurrency=2)


def test_replay_reuses_scoring_cache_and_preserves_policy_with_measurements(tmp_path):
    settings = settings_for(tmp_path)
    first = V2PipelineService(settings)
    first.create(run_id='t24-first')
    asyncio.run(first.run('t24-first', implement_source=True))
    first_scores = [(item.item_id, item.target_scores, item.policy_decision)
                    for item in first.repo.scores('t24-first', 'section_score')]

    second = V2PipelineService(settings)
    second.create(run_id='t24-second')
    asyncio.run(second.run('t24-second', implement_source=True))
    second_scores = [(item.item_id, item.target_scores, item.policy_decision)
                     for item in second.repo.scores('t24-second', 'section_score')]

    stage = second.repo.stage('t24-second', 'section_score')
    measurements = second.repo.performance_summary('t24-second')
    assert first_scores == second_scores
    assert 'cached batch(es) reused' in stage.summary
    assert measurements['database_bytes'] > 0
    assert measurements['provider_requests']['chunk_score_live'] == 0
    assert measurements['cache']['chunk_score_batches'] > 0
    with TestClient(create_app(settings)) as client:
        assert client.get('/v2/runs/t24-second/pipeline?stage=findings').status_code == 200
    reader = second.repo.performance_summary('t24-second')['reader_route']
    assert reader['route'] == 'pipeline:findings'
    assert reader['latency_ms'] >= 0 and reader['payload_bytes'] > 0


def test_large_diagnostic_payload_is_transparently_compressed(tmp_path):
    service = V2PipelineService(settings_for(tmp_path))
    service.create(run_id='t24-diagnostic')
    service.repo.save_exploration_action('t24-diagnostic', 'large', 'findings', 1,
                                         {'visible_text': 'source ' * 1000})
    assert service.repo.exploration_actions('t24-diagnostic', 'findings')[0]['visible_text'].startswith('source')


def test_resume_keeps_completed_stage_checkpoints(tmp_path):
    service = V2PipelineService(settings_for(tmp_path))
    service.create(run_id='t24-resume')
    asyncio.run(service.run('t24-resume', implement_source=True))
    before = len([event for event in service.repo.events('t24-resume', limit=100)
                  if event.stage == 'source' and event.kind == 'stage_finished'])
    service.cancel('t24-resume')
    service.resume('t24-resume')
    asyncio.run(service.run('t24-resume', implement_source=True))
    after = len([event for event in service.repo.events('t24-resume', limit=100)
                 if event.stage == 'source' and event.kind == 'stage_finished'])
    assert before == after == 1
