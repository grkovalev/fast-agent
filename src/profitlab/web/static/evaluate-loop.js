(() => {
  const stations = {
    pair: { number: '01', title: 'Pair', heading: 'Meet two sealed inputs at one boundary', connectors: ['pair-compare'], flow: 'pair-compare' },
    compare: { number: '02', title: 'Compare', heading: 'Apply the deterministic comparison contract', connectors: ['pair-compare', 'compare-verify'], flow: 'compare-verify' },
    verify: { number: '03', title: 'Verify', heading: 'Accept only explicitly visible scale or unit support', connectors: ['compare-verify', 'verify-record'], flow: 'verify-record' },
    record: { number: '04', title: 'Record', heading: 'Keep an inspectable result without changing inputs', connectors: ['verify-record'], flow: 'verify-record' }
  };

  document.querySelectorAll('[data-evaluate-loop]').forEach((loop) => {
    const card = loop.parentElement.querySelector('#evaluate-loop-card');
    let inspection = {};
    try { inspection = JSON.parse(loop.closest('.evaluate-stage-slot')?.querySelector('[data-evaluate-inspection]')?.textContent || '{}'); } catch { /* The server-rendered first station remains useful. */ }
    const stationNodes = [...loop.querySelectorAll('[data-evaluate-station]')];
    const connectors = [...loop.querySelectorAll('[data-evaluate-connector]')];
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
      if (panel.request) { add('h4', 'Configured bounded verification'); add('pre', JSON.stringify(panel.request, null, 2)); }
      const connector = loop.querySelector(`[data-evaluate-connector="${item.flow}"]`);
      if (!reduceMotion && connector) { connector.classList.remove('is-flowing'); void connector.getBoundingClientRect(); connector.classList.add('is-flowing'); }
    };
    const inspect = (key) => { const item = stations[key]; loop.classList.add('is-inspecting'); stationNodes.forEach((node) => node.classList.toggle('is-highlighted', node.dataset.evaluateStation === key)); connectors.forEach((node) => node.classList.toggle('is-highlighted', item.connectors.includes(node.dataset.evaluateConnector))); };
    const clear = () => { loop.classList.remove('is-inspecting'); stationNodes.forEach((node) => node.classList.remove('is-highlighted')); connectors.forEach((node) => node.classList.remove('is-highlighted')); };
    stationNodes.forEach((node) => { const key = node.dataset.evaluateStation; node.addEventListener('pointerenter', () => inspect(key)); node.addEventListener('focus', () => inspect(key)); node.addEventListener('pointerleave', clear); node.addEventListener('blur', clear); node.addEventListener('click', () => show(key)); node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(key); } }); });
  });
})();
