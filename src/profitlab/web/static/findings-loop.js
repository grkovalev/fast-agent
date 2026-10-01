(() => {
  const stations = {
    assemble: { number: '01', title: 'Assemble', heading: 'Keep claim-generation inputs visible and bounded', connectors: ['assemble-propose'], flow: 'assemble-propose' },
    propose: { number: '02', title: 'Propose', heading: 'Request candidates, never published claims', connectors: ['assemble-propose', 'propose-validate'], flow: 'propose-validate' },
    validate: { number: '03', title: 'Validate', heading: 'Mechanically prove every published citation', connectors: ['propose-validate', 'validate-classify'], flow: 'validate-classify' },
    classify: { number: '04', title: 'Classify', heading: 'Add type metadata without changing evidence', connectors: ['validate-classify', 'classify-publish'], flow: 'classify-publish' },
    publish: { number: '05', title: 'Publish', heading: 'Seal one deduplicated, quote-backed finding set', connectors: ['classify-publish'], flow: 'classify-publish' }
  };

  document.querySelectorAll('[data-findings-loop]').forEach((loop) => {
    const card = loop.parentElement.querySelector('#findings-loop-card');
    let inspection = {};
    try {
      inspection = JSON.parse(
        loop.closest('.findings-stage-slot')?.querySelector('[data-findings-inspection]')?.textContent || '{}'
      );
    } catch { /* The server-rendered first station remains useful. */ }
    const stationNodes = [...loop.querySelectorAll('[data-findings-station]')];
    const connectors = [...loop.querySelectorAll('[data-findings-connector]')];
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
      if (panel.policy) { add('h4', 'Classification policy'); add('pre', JSON.stringify(panel.policy, null, 2)); }
      const connector = loop.querySelector(`[data-findings-connector="${item.flow}"]`);
      if (!reduceMotion && connector) { connector.classList.remove('is-flowing'); void connector.getBoundingClientRect(); connector.classList.add('is-flowing'); }
    };
    const inspect = (key) => { const item = stations[key]; loop.classList.add('is-inspecting'); stationNodes.forEach((node) => node.classList.toggle('is-highlighted', node.dataset.findingsStation === key)); connectors.forEach((node) => node.classList.toggle('is-highlighted', item.connectors.includes(node.dataset.findingsConnector))); };
    const clear = () => { loop.classList.remove('is-inspecting'); stationNodes.forEach((node) => node.classList.remove('is-highlighted')); connectors.forEach((node) => node.classList.remove('is-highlighted')); };
    stationNodes.forEach((node) => { const key = node.dataset.findingsStation; node.addEventListener('pointerenter', () => inspect(key)); node.addEventListener('focus', () => inspect(key)); node.addEventListener('pointerleave', clear); node.addEventListener('blur', clear); node.addEventListener('click', () => show(key)); node.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(key); } }); });
  });
})();
