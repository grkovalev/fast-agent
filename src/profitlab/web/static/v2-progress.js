(() => {
  const root = document.querySelector('[data-v2-run]');
  if (!root) return;
  const runId = root.dataset.v2Run;
  const names = ['Source', 'Outline', 'Sections', 'Chunks', 'Evidence', 'Findings', 'Facts', 'Evaluate'];
  const statuses = {
    completed: ['✓', 'Complete'], running: ['●', 'Running'], queued: ['○', 'Queued'],
    partial: ['◐', 'Partial'], failed: ['!', 'Failed'], cancelled: ['×', 'Cancelled'],
    interrupted: ['!', 'Interrupted'],
  };
  const terminal = new Set(['completed', 'partial', 'failed', 'cancelled', 'interrupted']);
  let fallback, clock, delayed, events;
  let priorStatuses = Object.fromEntries([...document.querySelectorAll('[data-stage]')]
    .map((item) => [item.dataset.stage, item.dataset.stageStatus]));
  let pending = false;
  let stopped = false;
  const seconds = (value) => `${Math.max(0, value).toFixed(1)}s`;
  const tick = () => {
    document.querySelectorAll('[data-stage-duration]').forEach((node) => {
      if (node.dataset.status !== 'running') return;
      const started = Date.parse(node.dataset.activeStartedAt || '');
      const active = Number(node.dataset.activeSeconds || 0);
      node.textContent = Number.isNaN(started)
        ? `Recorded active ${seconds(active)}`
        : `Wall elapsed ${seconds((Date.now() - started) / 1000)} · recorded active ${seconds(active)}`;
      if (Number(node.dataset.queuedSeconds)) node.textContent += ` · queued ${seconds(Number(node.dataset.queuedSeconds))}`;
      if (Number(node.dataset.backoffSeconds)) node.textContent += ` · backoff ${seconds(Number(node.dataset.backoffSeconds))}`;
    });
  };
  const stopLiveUpdates = () => {
    stopped = true;
    if (events) events.close();
    if (fallback) clearInterval(fallback);
    if (clock) clearInterval(clock);
    if (delayed) clearTimeout(delayed);
    fallback = clock = delayed = undefined;
  };
  const refreshAccounting = async () => {
    const regions = [...document.querySelectorAll('[data-stage-accounting]')];
    if (!regions.length) return;
    const response = await fetch(`/v2/runs/${runId}/pipeline`, {cache: 'no-store'});
    if (!response.ok) return;
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    for (const region of regions) {
      const replacement = [...page.querySelectorAll('[data-stage-accounting]')]
        .find((item) => item.dataset.stageAccounting === region.dataset.stageAccounting);
      if (replacement) region.replaceChildren(...[...replacement.childNodes].map((node) => document.importNode(node, true)));
    }
  };
  const render = async () => {
    const response = await fetch(`/v2/runs/${runId}/state`, {cache: 'no-store'});
    if (!response.ok || stopped) return;
    const state = await response.json();
    if (stopped) return;
    const [runSymbol, runLabel] = statuses[state.run.status] || ['!', state.run.status];
    const runStatus = document.querySelector('#v2-run-status');
    if (runStatus) runStatus.textContent = `${runLabel} · ${state.run.summary}`;
    const mapStatus = document.querySelector('[data-map-run-status]');
    if (mapStatus) mapStatus.textContent = `${runSymbol} ${runLabel}`;
    const completed = state.stages.filter((item) => item.status === 'completed').length;
    const totalProgress = document.querySelector('[data-total-progress]');
    if (totalProgress) totalProgress.textContent = `${completed} of 8 complete`;
    const mapProgress = document.querySelector('[data-map-progress]');
    if (mapProgress) mapProgress.textContent = `${completed} of 8 stages complete`;
    const active = state.stages.find((item) => item.status === 'running');
    const selected = active || state.stages.find((item) => item.stage === state.run.selected_stage);
    const current = document.querySelector('[data-current-stage]');
    if (current) current.textContent = terminal.has(state.run.status)
      ? 'None' : selected ? names[selected.position - 1] : 'Waiting to start';
    const changed = state.stages.some((item) =>
      priorStatuses[item.stage] !== item.status && terminal.has(item.status));
    priorStatuses = Object.fromEntries(state.stages.map((item) => [item.stage, item.status]));
    for (const stage of state.stages) {
      const container = document.querySelector(`[data-stage-container="${stage.stage}"]`);
      const item = document.querySelector(`[data-stage="${stage.stage}"]`);
      const card = document.querySelector(`[data-stage-card="${stage.stage}"]`);
      const [symbol, label] = statuses[stage.status] || ['!', stage.status];
      const selectedDetail = document.querySelector(`[data-selected-stage="${stage.stage}"]`);
      if (selectedDetail) {
        const status = selectedDetail.querySelector('[data-selected-status]');
        if (status) {
          const icon = document.createElement('span');
          icon.setAttribute('aria-hidden', 'true');
          icon.textContent = symbol;
          const text = document.createElement('span');
          text.textContent = label;
          status.replaceChildren(icon, text);
        }
        const work = selectedDetail.querySelector('[data-selected-work]');
        if (work) work.textContent = stage.total_work === null
          ? (stage.status === 'running' ? '· Work total pending' : '')
          : `· ${stage.completed_work} / ${stage.total_work}`;
        const progressDetail = selectedDetail.querySelector('[data-selected-progress]');
        if (progressDetail) progressDetail.textContent = `${stage.total_work === null
          ? (stage.status === 'running' ? 'Work total pending' : 'Work total unavailable')
          : `${stage.completed_work} / ${stage.total_work}`} · ${stage.status} · recorded active ${stage.active_seconds.toFixed(2)}s`;
        const headerStatus = selectedDetail.querySelector('.stage-entry-status');
        if (headerStatus) headerStatus.className = `stage-entry-status stage-status status-${stage.status}`;
      }
      if (item) {
        item.className = `stage-status status-${stage.status}`;
        item.dataset.stageStatus = stage.status;
        const icon = document.createElement('span');
        icon.setAttribute('aria-hidden', 'true');
        icon.textContent = symbol;
        const text = document.createElement('span');
        text.textContent = label;
        item.replaceChildren(icon, text);
      }
      if (card) {
        card.setAttribute('aria-label', `${names[stage.position - 1]} — ${label}`);
        if (stage.status === 'running') card.setAttribute('aria-current', 'step');
        else card.removeAttribute('aria-current');
      }
      if (container) {
        container.classList.toggle('is-active', stage.status === 'running');
        if (stage.status === 'running') container.setAttribute('aria-current', 'step');
        else container.removeAttribute('aria-current');
      }
      const progress = document.querySelector(`[data-stage-progress="${stage.stage}"]`);
      if (progress) progress.textContent = stage.total_work === null
        ? (stage.status === 'running' ? 'Work total pending' : '')
        : `${stage.completed_work} / ${stage.total_work}`;
      const duration = document.querySelector(`[data-stage-duration="${stage.stage}"]`);
      if (duration) {
        duration.dataset.status = stage.status;
        duration.dataset.activeStartedAt = stage.started_at || '';
        duration.dataset.activeSeconds = stage.active_seconds;
        duration.dataset.queuedSeconds = stage.queued_seconds;
        duration.dataset.backoffSeconds = stage.retry_backoff_seconds;
        duration.textContent = terminal.has(stage.status) ? `Active ${seconds(stage.active_seconds)}` : '';
      }
    }
    tick();
    try {
      if (changed) await refreshAccounting();
    } finally {
      if (terminal.has(state.run.status)) stopLiveUpdates();
    }
  };
  const schedule = () => {
    if (pending || stopped || document.hidden) return;
    pending = true;
    delayed = setTimeout(async () => {
      delayed = undefined;
      try { await render(); } catch { poll(); } finally { pending = false; }
    }, 150);
  };
  const poll = () => {
    if (stopped || fallback) return;
    fallback = setInterval(schedule, 2000);
    schedule();
  };
  clock = setInterval(tick, 250);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) schedule(); });
  window.addEventListener('pagehide', stopLiveUpdates, {once: true});
  schedule();
  if (!window.EventSource) { poll(); return; }
  events = new EventSource(`/v2/runs/${runId}/events`);
  events.addEventListener('pipeline', schedule);
  events.onerror = () => { events.close(); poll(); };
})();
