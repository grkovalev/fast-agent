"""T19 detailed Jev scoring, bounded retention, and workspace inspection."""
import asyncio

from fastapi.testclient import TestClient

from profitlab.settings import Settings
from profitlab.v2 import V2PipelineService
from profitlab.v2.chunk_scoring import ChunkScoringService
from profitlab.v2.contracts import ScoredItem
from profitlab.web.app import create_app


def test_detailed_policy_preserves_target_section_and_year_diversity(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, chunk_target_tokens=100,
                        chunk_overlap_tokens=40, chunk_question_overhead=500,
                        chunk_request_budget=1000, outline_window_lines=100,
                        section_score_batch_size=2, chunk_score_max_retained=2,
                        chunk_score_max_uncertain=0)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='policy-t19')
    asyncio.run(pipeline.run('policy-t19', implement_source=True))
    document = pipeline.repo.canonical_document('policy-t19', pipeline.repo.canonical_refs('policy-t19')[0].document_id)
    chunks = pipeline.repo.chunks('policy-t19')
    raw = [ScoredItem(item_id=item.chunk_id, target_scores={
        'annual_profit': .99 if index == 0 else .1,
        'diluted_eps': .99 if index == 1 else .1,
        'diluted_shares': .1, 'earnings_change': .1, 'comparability': .1},
        model='controlled', call_id='controlled', policy_decision='skipped', policy_reason='pending')
        for index, item in enumerate(chunks)]
    scored = ChunkScoringService(settings, pipeline.repo)._policy(raw, chunks, document)
    selected = [item for item in scored if item.policy_decision == 'selected']
    assert {item.item_id for item in selected} >= {chunks[0].chunk_id, chunks[1].chunk_id}
    assert all('pending' not in item.policy_reason for item in scored)


def test_offline_chunk_scoring_checkpoints_caches_and_renders_workspace(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, _env_file=None, chunk_target_tokens=100,
                        chunk_overlap_tokens=40, chunk_question_overhead=500,
                        chunk_request_budget=1000, outline_window_lines=100,
                        section_score_batch_size=2, chunk_score_batch_size=2)
    pipeline = V2PipelineService(settings)
    pipeline.create(run_id='score-t19-a')
    asyncio.run(pipeline.run('score-t19-a', implement_source=True))
    stage = pipeline.repo.stage('score-t19-a', 'chunk_score')
    scores = pipeline.repo.scores('score-t19-a', 'chunk_score')
    summary = pipeline.repo.chunk_score_summary('score-t19-a')
    assert stage.status == 'completed' and scores and summary['calls'] > 0
    assert {item.item_id for item in scores} == {item.chunk_id for item in pipeline.repo.chunks('score-t19-a')}
    assert any(item.policy_decision == 'selected' for item in scores)
    assert pipeline.repo.exploration_actions('score-t19-a', 'chunk_score')

    pipeline.create(run_id='score-t19-b')
    asyncio.run(pipeline.run('score-t19-b', implement_source=True))
    assert pipeline.repo.chunk_score_summary('score-t19-b')['cached_batches'] > 0
    with TestClient(create_app(settings)) as client:
        page = client.get('/v2/runs/score-t19-a?stage=chunk_score')
    assert page.status_code == 200
    assert 'Ranked detailed evidence' in page.text
    assert 'Inspect sanitized provider trace' in page.text
