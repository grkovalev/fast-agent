(() => {
  const stations = {
    describe: { number: '01', title: 'Describe', heading: 'Keep provider inputs exact, visible, and inspectable', connectors: ['describe-score'], flow: 'describe-score' },
    score: { number: '02', title: 'Score', heading: 'Measure detailed retrieval signals without making a claim', connectors: ['describe-score', 'score-retain'], flow: 'score-retain' },
    retain: { number: '03', title: 'Retain', heading: 'Preserve diverse evidence within explicit bounds', connectors: ['score-retain'], flow: 'score-retain' }
  };

  document.querySelectorAll('[data-evidence-loop]').forEach((loop) => {
    const card = loop.parentElement.querySelector('#evidence-loop-card');
    let inspection = {};
    try {
      inspection = JSON.parse(
        loop.closest('.evidence-stage-slot')?.querySelector('[data-evidence-inspection]')?.textContent || '{}'
      );
    } catch { /* The server-rendered first station remains useful. */ }
    const stationNodes = [...loop.querySelectorAll('[data-evidence-station]')];
    const connectors = [...loop.querySelectorAll('[data-evidence-connector]')];
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const show = (key) => {
      const item = stations[key]; const panel = inspection[key] || {};
      card.replaceChildren();
      const add = (tag, value, className) => { const node = document.createElement(tag); if (className) node.className = className; node.textContent = value; card.append(node); };
      const dl = document.createElement('dl');
      [['Accepts', panel.accepts], ['Does', panel.does], ['Outputs', panel.outputs], ['Guarantee', panel.guarantee]].forEach(([term, value]) => {
        const row = document.createElement('div'); const dt = document.createElement('dt'); const dd = document.createElement('dd');
        dt.textContent = term;
        if (typeof value === 'string') dd.textContent = value;
        else { const pre = document.createElement('pre'); pre.textContent = JSON.stringify(value ?? {}, null, 2); dd.append(pre); row.className = 'is-json'; }
        row.append(dt, dd); dl.append(row);
      });
      add('p', `${item.number} · ${item.title}`, 'eyebrow'); add('h3', item.heading); card.append(dl);
      if (panel.request) { add('h4', 'Configured provider request'); add('pre', JSON.stringify(panel.request, null, 2)); }
      if (panel.policy) { add('h4', 'Deterministic retention policy'); add('pre', JSON.stringify(panel.policy, null, 2)); }
      const connector = loop.querySelector(`[data-evidence-connector="${item.flow}"]`);
      if (!reduceMotion && connector) { connector.classList.remove('is-flowing'); void connector.getBoundingClientRect(); connector.classList.add('is-flowing'); }
    };
    const inspect = (key) => { const item = stations[key]; loop.classList.add('is-inspecting'); stationNodes.forEach((node) => node.classList.toggle('is-highlighted', node.dataset.evidenceStation === key)); connectors.forEach((node) => node.classList.toggle('is-highlighted', item.connectors.includes(node.dataset.evidenceConnector))); };
    const clear = () => { loop.classList.remove('is-inspecting'); stationNodes.forEach((node) => node.classList.remove('is-highlighted')); connectors.forEach((node) => node.classList.remove('is-highlighted')); };
    stationNodes.forEach((node) => { const key = node.dataset.evidenceStation; node.addEventListener('pointerenter', () => inspect(key)); node.addEventListener('focus', () => inspect(key)); node.addEventListener('pointerleave', clear); node.addEventListener('blur', clear); node.addEventListener('click', () => show(key)); node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(key); } }); });
  });
})();
