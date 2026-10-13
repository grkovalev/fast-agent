(() => {
  const links = {
    source: ['request-convert', 'convert-store'],
    outline: ['window-propose', 'propose-validate', 'validate-reconcile', 'reconcile-window', 'reconcile-final'],
    sections: ['describe-score', 'score-select'],
    chunks: ['split-context', 'context-store'],
    evidence: ['describe-score', 'score-retain'],
    findings: ['assemble-propose', 'propose-validate', 'validate-classify', 'classify-publish'],
    facts: ['checkpoint-retrieve', 'retrieve-normalize', 'normalize-store'],
    evaluate: ['pair-compare', 'compare-verify', 'verify-record']
  };
  const stages = {
    source: 'source', outline: 'outline', section_score: 'sections', chunk: 'chunks',
    chunk_score: 'evidence', findings: 'findings', facts: 'facts', evaluate: 'evaluate'
  };
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

  Object.entries(stages).forEach(([stage, prefix]) => {
    const article = document.querySelector(`[data-stage-container="${stage}"]`);
    const loop = article?.querySelector(`[data-${prefix}-loop]`);
    const card = article?.querySelector('[data-station-card]');
    if (!loop || !card) return;
    const stations = [...loop.querySelectorAll(`[data-${prefix}-station]`)];
    const connectors = [...loop.querySelectorAll(`[data-${prefix}-connector]`)];
    const order = links[prefix];

    const highlight = (key) => {
      const index = stations.findIndex((node) => node.dataset[`${prefix}Station`] === key);
      loop.classList.add('is-inspecting');
      stations.forEach((node) => node.classList.toggle('is-highlighted', node.dataset[`${prefix}Station`] === key));
      connectors.forEach((node) => node.classList.toggle('is-highlighted',
        order.includes(node.dataset[`${prefix}Connector`]) &&
        (order[index - 1] === node.dataset[`${prefix}Connector`] ||
         order[index] === node.dataset[`${prefix}Connector`] ||
         (prefix === 'outline' && key === 'reconcile' && node.dataset.outlineConnector === 'reconcile-final'))));
    };
    const clear = () => {
      loop.classList.remove('is-inspecting');
      stations.forEach((node) => node.classList.remove('is-highlighted'));
      connectors.forEach((node) => node.classList.remove('is-highlighted'));
    };
    const select = (key) => {
      const template = article.querySelector(`template[data-station-template="${key}"]`);
      if (!template) return;
      card.replaceChildren(template.content.cloneNode(true));
      stations.forEach((node) => {
        const selected = node.dataset[`${prefix}Station`] === key;
        node.setAttribute('aria-pressed', String(selected));
        node.classList.toggle('is-selected', selected);
      });
      const index = stations.findIndex((node) => node.dataset[`${prefix}Station`] === key);
      const connector = connectors.find((node) => node.dataset[`${prefix}Connector`] === order[index]);
      if (!reducedMotion.matches && connector) {
        connector.classList.remove('is-flowing');
        void connector.getBoundingClientRect();
        connector.classList.add('is-flowing');
      }
    };
    stations.forEach((node, index) => {
      const key = node.dataset[`${prefix}Station`];
      node.setAttribute('aria-pressed', String(index === 0));
      node.addEventListener('pointerenter', () => highlight(key));
      node.addEventListener('focus', () => highlight(key));
      node.addEventListener('pointerleave', clear);
      node.addEventListener('blur', clear);
      node.addEventListener('click', () => select(key));
      node.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          select(key);
        }
      });
    });
  });
})();
