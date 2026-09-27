(() => {
  const root = document.querySelector('[data-v2-run]');
  if (!root) return;
  const runId = root.dataset.v2Run;
  let fallback;
  let pending = false;
  const render = async () => {
    const response = await fetch(`/v2/runs/${runId}/state`, {cache: 'no-store'});
    if (!response.ok) {
      // The user may have removed this run in another tab or reset the fresh
      // workspace. It cannot recover by polling a non-existent run forever.
      if (response.status === 404) {
        if (fallback) clearInterval(fallback);
        events?.close();
      }
      return;
    }
    const state = await response.json();
    document.querySelector('#v2-run-status').textContent = `${state.run.status} · ${state.run.summary}`;
    for (const stage of state.stages) {
      const item = document.querySelector(`[data-stage="${stage.stage}"]`);
      if (item) item.textContent = stage.status;
    }
    if (!['queued', 'running'].includes(state.run.status) && fallback) clearInterval(fallback);
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
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) schedule();
  });
  if (!window.EventSource) {
    poll();
    return;
  }
  let events = new EventSource(`/v2/runs/${runId}/events`);
  events.addEventListener('pipeline', schedule);
  events.onerror = () => {
    events.close();
    if (!fallback) poll();
  };
})();
