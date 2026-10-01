(() => {
  const stations = {
    split: { number: '01', title: 'Split', heading: 'Bound source coverage without a model call', connectors: ['split-context'], flow: 'split-context' },
    context: { number: '02', title: 'Context', heading: 'Carry reading context without double-counting evidence', connectors: ['split-context', 'context-store'], flow: 'context-store' },
    store: { number: '03', title: 'Store', heading: 'Keep the authoritative chunk record inspectable', connectors: ['context-store'], flow: 'context-store' }
  };

  document.querySelectorAll('[data-chunks-loop]').forEach((loop) => {
    const card = loop.parentElement.querySelector('#chunks-loop-card');
    let inspection = {};
    try {
      inspection = JSON.parse(
        loop.closest('.chunks-stage-slot')?.querySelector('[data-chunks-inspection]')?.textContent || '{}'
      );
    } catch { /* rendered fallback remains useful */ }
    const stationNodes = [...loop.querySelectorAll('[data-chunks-station]')];
    const connectors = [...loop.querySelectorAll('[data-chunks-connector]')];
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const show = (key) => {
      const item = stations[key]; const panel = inspection[key] || {};
      card.replaceChildren();
      const add = (tag, text, className) => { const node = document.createElement(tag); if (className) node.className = className; node.textContent = text; card.append(node); };
      const dl = document.createElement('dl');
      [['Accepts', panel.accepts], ['Does', panel.does], ['Outputs', panel.outputs], ['Guarantee', panel.guarantee]].forEach(([term, description]) => {
        const row = document.createElement('div'); const dt = document.createElement('dt'); const dd = document.createElement('dd'); dt.textContent = term;
        if (typeof description === 'string') dd.textContent = description;
        else { const pre = document.createElement('pre'); pre.textContent = JSON.stringify(description ?? {}, null, 2); dd.append(pre); row.className = 'is-json'; }
        row.append(dt, dd); dl.append(row);
      });
      add('p', `${item.number} · ${item.title}`, 'eyebrow'); add('h3', item.heading); card.append(dl);
      if (panel.policy) { add('h4', key === 'split' ? 'Deterministic path and bounds' : 'Context bound'); add('pre', JSON.stringify(panel.policy, null, 2)); }
      const connector = loop.querySelector(`[data-chunks-connector="${item.flow}"]`);
      if (!reduceMotion && connector) { connector.classList.remove('is-flowing'); void connector.getBoundingClientRect(); connector.classList.add('is-flowing'); }
    };
    const inspect = (key) => { const item = stations[key]; loop.classList.add('is-inspecting'); stationNodes.forEach((node) => node.classList.toggle('is-highlighted', node.dataset.chunksStation === key)); connectors.forEach((node) => node.classList.toggle('is-highlighted', item.connectors.includes(node.dataset.chunksConnector))); };
    const clear = () => { loop.classList.remove('is-inspecting'); stationNodes.forEach((node) => node.classList.remove('is-highlighted')); connectors.forEach((node) => node.classList.remove('is-highlighted')); };
    stationNodes.forEach((node) => { const key = node.dataset.chunksStation; node.addEventListener('pointerenter', () => inspect(key)); node.addEventListener('focus', () => inspect(key)); node.addEventListener('pointerleave', clear); node.addEventListener('blur', clear); node.addEventListener('click', () => show(key)); node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(key); } }); });
  });
})();
