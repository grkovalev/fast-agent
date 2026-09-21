(() => {
  const root = document.querySelector('[data-v2-run]');
  if (!root) return;
  const runId = root.dataset.v2Run;
  let fallback;
  const render = async () => {
    const response = await fetch(`/v2/runs/${runId}/state`, {cache: 'no-store'});
    if (!response.ok) return;
    const state = await response.json();
    document.querySelector('#v2-run-status').textContent = `${state.run.status} · ${state.run.summary}`;
    for (const stage of state.stages) {
      const item = document.querySelector(`[data-stage="${stage.stage}"]`);
      if (item) item.textContent = stage.status;
    }
    if (!['queued', 'running'].includes(state.run.status) && fallback) clearInterval(fallback);
  };
  if (!window.EventSource) {
    fallback = setInterval(render, 1000);
    return;
  }
  const events = new EventSource(`/v2/runs/${runId}/events`);
  events.addEventListener('pipeline', render);
  events.onerror = () => {
    events.close();
    if (!fallback) fallback = setInterval(render, 1000);
  };
})();
