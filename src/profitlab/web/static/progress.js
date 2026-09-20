const workflow = document.getElementById('workflow');
if (workflow) {
  const poll = async () => {
    try {
      const response = await fetch(`/runs/${workflow.dataset.runId}/progress`);
      if (!response.ok) return;
      const state = await response.json();
      document.getElementById('workflow-company').textContent = state.run.company ? state.run.company.name : 'Resolving company…';
      document.getElementById('workflow-coverage').textContent = `${state.run.covered_years.length} / ${state.run.requested_years} annual periods discovered`;
      document.getElementById('workflow-status').textContent = `${state.run.status} · ${state.run.stage}`;
      const completed = state.stages.filter(s => s.status === 'completed').length;
      document.getElementById('workflow-count').textContent = `${completed} / ${state.stages.length} stages completed · ${state.elapsed_seconds.toFixed(1)} seconds`;
      document.getElementById('workflow-error').textContent = state.error || '';
      const list = document.getElementById('workflow-stages');
      list.replaceChildren(...state.stages.map(stage => {
        const item = document.createElement('li');
        item.textContent = `${stage.name}: ${stage.status} (${stage.output_count} saved outputs)`;
        return item;
      }));
      const active = ['queued', 'running'].includes(state.run.status);
      document.getElementById('cancel-run').hidden = !active;
      document.getElementById('resume-run').hidden = active;
      if (active) setTimeout(poll, 1000);
      else if (workflow.dataset.finished !== 'true') {
        workflow.dataset.finished = 'true';
        if (completed === state.stages.length) location.reload();
      }
    } catch (_) { setTimeout(poll, 1000); }
  };
  if (!['queued', 'running'].includes(document.getElementById('workflow-status').textContent.split(' ')[0])) workflow.dataset.finished = 'true';
  poll();
}
