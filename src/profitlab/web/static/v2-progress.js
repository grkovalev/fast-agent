(() => {
  const root = document.querySelector('[data-v2-run]');
  if (!root) return;
  const runId = root.dataset.v2Run;
  const statusPresentation = {
    completed: ['✓', 'Complete'], running: ['●', 'Running'], queued: ['○', 'Queued'],
    partial: ['◐', 'Partial'], failed: ['!', 'Failed'], cancelled: ['×', 'Cancelled'],
    interrupted: ['!', 'Interrupted'],
  };
  let fallback;
  let clock;
  let pending = false;
  const terminal = new Set(['completed', 'partial', 'failed', 'cancelled', 'interrupted']);
  const formatSeconds = (seconds) => `${Math.max(0, seconds).toFixed(1)}s`;
  const timingDetail = (stage) => `${stage.status === 'running' ? 'Elapsed ' : ''}${formatSeconds(elapsed(stage))}${stage.queued_seconds ? ` · queued ${formatSeconds(stage.queued_seconds)}` : ''}${stage.retry_backoff_seconds ? ` · backoff ${formatSeconds(stage.retry_backoff_seconds)}` : ''}`;
  const elapsed = (stage) => {
    const started = stage.started_at ? Date.parse(stage.started_at) : NaN;
    return stage.status === 'running' && !Number.isNaN(started)
      ? Math.max(Number(stage.active_seconds || 0), (Date.now() - started) / 1000)
      : Number(stage.active_seconds || 0);
  };
  const updateTimer = (stage) => {
    const duration = document.querySelector(`[data-stage-duration="${stage.stage}"]`);
    if (!duration) return;
    duration.dataset.activeStartedAt = stage.started_at || '';
    duration.dataset.activeSeconds = stage.active_seconds || '0';
    duration.textContent = terminal.has(stage.status) ? formatSeconds(elapsed(stage))
      : stage.status === 'running' ? timingDetail(stage) : '';
  };
  const tick = () => {
    document.querySelectorAll('[data-stage-duration]').forEach((duration) => {
      const started = Date.parse(duration.dataset.activeStartedAt || '');
      const card = duration.closest('[data-stage-card]');
      if (!card?.classList.contains('is-active') || Number.isNaN(started)) return;
      const suffix = duration.textContent.split(' · ').slice(1).join(' · ');
      duration.textContent = `Elapsed ${formatSeconds(Math.max(Number(duration.dataset.activeSeconds || 0), (Date.now() - started) / 1000))}${suffix ? ` · ${suffix}` : ''}`;
    });
  };
  const stopLiveUpdates = () => {
    if (fallback) clearInterval(fallback);
    if (clock) clearInterval(clock);
  };
  const render = async () => {
    const response = await fetch(`/v2/runs/${runId}/state`, {cache: 'no-store'});
    if (!response.ok) return;
    const state = await response.json();
    document.querySelector('#v2-run-status').textContent = `${state.run.status} · ${state.run.summary}`;
    const completed = state.stages.filter((stage) => stage.status === 'completed').length;
    const active = state.stages.find((stage) => stage.status === 'running');
    const current = active || state.stages.find((stage) => stage.stage === state.run.selected_stage);
    const overall = document.querySelector('#pipeline-overall-progress');
    if (overall) overall.innerHTML = `<strong>${completed} of 8 stages complete</strong> · Current: <span data-current-stage>${current ? document.querySelector(`[data-stage-card="${current.stage}"] strong`)?.textContent || current.stage : 'Waiting to start'}</span> · Run: <span data-map-run-status>${state.run.status}</span>`;
    for (const stage of state.stages) {
      const item = document.querySelector(`[data-stage="${stage.stage}"]`);
      const card = document.querySelector(`[data-stage-card="${stage.stage}"]`);
      if (item) {
        const [symbol, label] = statusPresentation[stage.status] || ['!', stage.status];
        item.className = `stage-status status-${stage.status}`;
        item.dataset.stageStatus = stage.status;
        item.innerHTML = `<span aria-hidden="true">${symbol}</span><span>${label}</span>`;
        card?.setAttribute('aria-label', `${card.querySelector('strong').textContent} — ${label}`);
        card?.classList.toggle('is-active', stage.status === 'running');
        if (stage.status === 'running') card?.setAttribute('aria-current', 'step');
        else card?.removeAttribute('aria-current');
      }
      const progress = document.querySelector(`[data-stage-progress="${stage.stage}"]`);
      if (progress) progress.textContent = stage.status === 'running' && stage.total_work !== null
        ? `${stage.completed_work} / ${stage.total_work}` : '';
      updateTimer(stage);
    }
    if (!['queued', 'running'].includes(state.run.status)) stopLiveUpdates();
  };
  const schedule = () => {
    if (pending || document.hidden) return;
    pending = true;
    window.setTimeout(async () => { pending = false; await render(); }, 150);
  };
  const poll = () => {
    if (fallback) clearInterval(fallback);
    fallback = setInterval(() => { if (!document.hidden) schedule(); }, 2000);
  };
  clock = setInterval(tick, 250);
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) schedule();
  });
  if (!window.EventSource) {
    poll();
    return;
  }
  const events = new EventSource(`/v2/runs/${runId}/events`);
  events.addEventListener('pipeline', schedule);
  events.onerror = () => {
    events.close();
    if (!fallback) poll();
  };
})();
