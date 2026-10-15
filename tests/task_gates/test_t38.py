"""T38 immutable run provenance, monotonic timing, and cohort isolation."""
from datetime import UTC, datetime
from time import monotonic

from profitlab.settings import Settings
from profitlab.v2.contracts import FactComparison, StageSnapshot, V2Run
from profitlab.v2.evaluation_service import cross_run_scorecard
from profitlab.v2.pipeline import V2PipelineService
from profitlab.v2.storage import V2Repository


def test_pipeline_captures_immutable_version_and_setting_change_creates_new_cohort(tmp_path):
    common = {'PROFITLAB_DATA_DIR': tmp_path, 'SEC_USER_AGENT': 'ProfitLab test@example.org',
              'PROFITLAB_APPLICATION_REVISION': 'revision-a', '_env_file': None}
    first = V2PipelineService(Settings(**common)).create('ACME')
    changed = V2PipelineService(Settings(**{**common, 'findings_policy': {'version': 'findings-next'}})).create('BETA')

    assert first.version_state == 'comparable'
    assert first.version_id != changed.version_id
    assert 'findings-jev-policy-v1' in first.version_components['findings_policy']
    assert 'findings-next' in changed.version_components['findings_policy']
    # Persisted run provenance does not change when a later service uses new settings.
    assert V2Repository(tmp_path).get_run(first.run_id).version_id == first.version_id


def test_terminal_timing_is_monotonic_and_stage_active_time_is_preserved(tmp_path):
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    repo.create_run(V2Run(run_id='timed', ticker='TIME', created_at=now, updated_at=now,
                          timing_origin_monotonic=monotonic() - .02))
    repo.update_stage(StageSnapshot(run_id='timed', stage='source', position=1,
                                    status='completed', elapsed_seconds=.01),
                      event_kind='stage_finished', event_summary='done')
    repo.update_run('timed', status='completed', summary='done', kind='run_finished')

    run = repo.get_run('timed')
    stage = repo.stage('timed', 'source')
    assert stage.active_seconds == .01
    assert run.total_elapsed_seconds is not None and run.total_elapsed_seconds >= .02
    assert run.active_seconds == .01
    assert run.queued_seconds is not None and run.queued_seconds >= 0


def test_cancelled_stage_keeps_its_monotonic_active_duration(tmp_path):
    settings = Settings(PROFITLAB_DATA_DIR=tmp_path, SEC_USER_AGENT='ProfitLab test@example.org',
                        PROFITLAB_APPLICATION_REVISION='revision-a', _env_file=None)
    pipeline = V2PipelineService(settings)
    run = pipeline.create('STOP')
    pipeline.repo.update_stage(StageSnapshot(
        run_id=run.run_id, stage='source', position=1, status='running',
        active_started_monotonic=monotonic() - .01),
        event_kind='stage_started', event_summary='started')

    pipeline._cancel(run.run_id, 'source')

    assert pipeline.repo.stage(run.run_id, 'source').active_seconds >= .01
    assert pipeline.repo.get_run(run.run_id).total_elapsed_seconds is not None


def test_scorecard_only_counts_the_selected_identical_version_cohort(tmp_path):
    repo = V2Repository(tmp_path)
    now = datetime.now(UTC)
    for run_id, version in (('same-one', 'version-a'), ('same-two', 'version-a'), ('other', 'version-b')):
        repo.create_run(V2Run(run_id=run_id, ticker=run_id.upper().replace('-', ''),
                              created_at=now, updated_at=now, version_id=version))
        repo.update_stage(StageSnapshot(run_id=run_id, stage='evaluate', position=8,
                                        status='completed', completed_work=1, total_work=1),
                          event_kind='stage_finished', event_summary='done')
        repo.save_comparisons(run_id, [FactComparison(comparison_id=f'{run_id}-tp',
                              metric='net_income_consolidated', state='exact_match')])

    scorecard = cross_run_scorecard(repo, version_id='version-a')

    assert scorecard['selected_version'] == 'version-a'
    assert scorecard['modes']['deterministic']['true_positives'] == 2
    assert any(item['run_id'] == 'other' and not item['included']
               and 'separate version cohort' in item['reason'] for item in scorecard['ledger'])
    assert repo.comparisons('same-one')[0].evaluation_run_version == 'version-a'
