(() => {
  const stations = {
    checkpoint: { number: '01', title: 'Checkpoint', heading: 'Begin only after discovery is sealed', connectors: ['checkpoint-retrieve'], flow: 'checkpoint-retrieve' },
    retrieve: { number: '02', title: 'Retrieve', heading: 'Retain one bounded SEC source with provenance', connectors: ['checkpoint-retrieve', 'retrieve-normalize'], flow: 'retrieve-normalize' },
    normalize: { number: '03', title: 'Normalize', heading: 'Select configured annual facts without inference', connectors: ['retrieve-normalize', 'normalize-store'], flow: 'normalize-store' },
    store: { number: '04', title: 'Store', heading: 'Expose immutable inputs only to Evaluate', connectors: ['normalize-store'], flow: 'normalize-store' }
  };

  document.querySelectorAll('[data-facts-loop]').forEach((loop) => {
    const card = loop.parentElement.querySelector('#facts-loop-card');
    let inspection = {};
    try { inspection = JSON.parse(loop.closest('.facts-stage-slot')?.querySelector('[data-facts-inspection]')?.textContent || '{}'); } catch { /* The rendered first station remains useful. */ }
    const stationNodes = [...loop.querySelectorAll('[data-facts-station]')];
    const connectors = [...loop.querySelectorAll('[data-facts-connector]')];
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const show = (key) => {
      const item = stations[key]; const panel = inspection[key] || {}; card.replaceChildren();
      const add = (tag, value, className) => { const node = document.createElement(tag); if (className) node.className = className; node.textContent = value; card.append(node); };
      const dl = document.createElement('dl');
      [['Accepts', panel.accepts], ['Does', panel.does], ['Outputs', panel.outputs], ['Guarantee', panel.guarantee]].forEach(([term, value]) => {
        const row = document.createElement('div'); const dt = document.createElement('dt'); const dd = document.createElement('dd'); dt.textContent = term;
        if (typeof value === 'string') dd.textContent = value; else { const pre = document.createElement('pre'); pre.textContent = JSON.stringify(value ?? {}, null, 2); dd.append(pre); row.className = 'is-json'; }
        row.append(dt, dd); dl.append(row);
      });
      add('p', `${item.number} · ${item.title}`, 'eyebrow'); add('h3', item.heading); card.append(dl);
      if (panel.policy) { add('h4', 'Configured concept mapping'); add('pre', JSON.stringify(panel.policy, null, 2)); }
      const connector = loop.querySelector(`[data-facts-connector="${item.flow}"]`);
      if (!reduceMotion && connector) { connector.classList.remove('is-flowing'); void connector.getBoundingClientRect(); connector.classList.add('is-flowing'); }
    };
    const inspect = (key) => { const item = stations[key]; loop.classList.add('is-inspecting'); stationNodes.forEach((node) => node.classList.toggle('is-highlighted', node.dataset.factsStation === key)); connectors.forEach((node) => node.classList.toggle('is-highlighted', item.connectors.includes(node.dataset.factsConnector))); };
    const clear = () => { loop.classList.remove('is-inspecting'); stationNodes.forEach((node) => node.classList.remove('is-highlighted')); connectors.forEach((node) => node.classList.remove('is-highlighted')); };
    stationNodes.forEach((node) => { const key = node.dataset.factsStation; node.addEventListener('pointerenter', () => inspect(key)); node.addEventListener('focus', () => inspect(key)); node.addEventListener('pointerleave', clear); node.addEventListener('blur', clear); node.addEventListener('click', () => show(key)); node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(key); } }); });
  });
})();
