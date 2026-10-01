(() => {
  const stations = {
    describe: {
      number: '01', title: 'Describe', heading: 'Keep retrieval inputs visible and bounded',
      accepts: 'Validated section topic, exact visible heading, source range, and filing identity.',
      does: (runtime) => `Builds an allowlisted descriptor with up to ${runtime.previewLimit} characters of exact source preview.`,
      outputs: 'Visible section descriptor.',
      guarantee: 'Inline XBRL, Company Facts, and evaluation values never enter scoring.',
      connectors: ['describe-score'], flow: 'describe-score'
    },
    score: {
      number: '02', title: 'Score', heading: 'Measure retrieval signals without judging facts',
      accepts: 'Visible section descriptors only.',
      does: (runtime) => `${runtime.model} evaluates five target-specific retrieval questions in batches of up to ${runtime.batchSize} sections.`,
      outputs: 'Target score vector for each section.',
      guarantee: 'Scores are retrieval signals, not probabilities of financial correctness.',
      connectors: ['describe-score', 'score-select'], flow: 'score-select'
    },
    select: {
      number: '03', title: 'Select', heading: 'Keep coverage while preserving uncertainty',
      accepts: 'Target score vectors in source order.',
      does: (runtime) => `Applies the deterministic keep threshold of ${runtime.keepThreshold} and retains a bounded uncertain band from ${runtime.uncertainThreshold}.`,
      outputs: (runtime) => `At most ${runtime.maxSelected} selected sections and ${runtime.maxUncertain} uncertain candidates.`,
      guarantee: 'The policy preserves high-score target coverage; it does not change source text or scores.',
      connectors: ['score-select'], flow: 'score-select'
    }
  };

  document.querySelectorAll('[data-sections-loop]').forEach((loop) => {
    const card = loop.parentElement.querySelector('#sections-loop-card');
    const runtimeNode = loop.closest('.sections-stage-slot')?.querySelector('[data-sections-runtime]')?.content;
    const runtime = {
      model: runtimeNode?.querySelector('[data-sections-model]')?.textContent.trim() || 'Configured retrieval model',
      previewLimit: runtimeNode?.querySelector('[data-sections-preview-limit]')?.textContent.trim() || '600',
      batchSize: runtimeNode?.querySelector('[data-sections-batch-size]')?.textContent.trim() || '1',
      keepThreshold: runtimeNode?.querySelector('[data-sections-keep-threshold]')?.textContent.trim() || 'configured',
      uncertainThreshold: runtimeNode?.querySelector('[data-sections-uncertain-threshold]')?.textContent.trim() || 'configured',
      maxSelected: runtimeNode?.querySelector('[data-sections-max-selected]')?.textContent.trim() || 'configured',
      maxUncertain: runtimeNode?.querySelector('[data-sections-max-uncertain]')?.textContent.trim() || 'configured'
    };
    const inspection = (() => {
      try {
        return JSON.parse(document.querySelector('[data-sections-inspection]')?.textContent || '{}');
      } catch { return {}; }
    })();
    const stationNodes = [...loop.querySelectorAll('[data-sections-station]')];
    const connectors = [...loop.querySelectorAll('[data-sections-connector]')];
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const value = (item, key) => typeof item[key] === 'function' ? item[key](runtime) : item[key];
    const show = (key) => {
      const item = stations[key];
      const panel = inspection[key] || {};
      card.replaceChildren();
      const add = (tag, text, className) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        card.append(node);
      };
      const stringify = (content) => typeof content === 'string' ? content : JSON.stringify(content, null, 2);
      const dl = document.createElement('dl');
      [['Accepts', panel.accepts ?? value(item, 'accepts')], ['Does', panel.does ?? value(item, 'does')],
       ['Outputs', panel.outputs ?? value(item, 'outputs')], ['Guarantee', panel.guarantee ?? value(item, 'guarantee')]].forEach(([term, description]) => {
        const row = document.createElement('div');
        const dt = document.createElement('dt'); const dd = document.createElement('dd');
        dt.textContent = term;
        if (typeof description === 'string') {
          dd.textContent = description;
        } else {
          const pre = document.createElement('pre');
          pre.textContent = stringify(description);
          row.className = 'is-json';
          dd.append(pre);
        }
        row.append(dt, dd); dl.append(row);
      });
      add('p', `${item.number} · ${item.title}`, 'eyebrow');
      add('h3', item.heading);
      card.append(dl);
      if (panel.request) {
        add('h4', 'Jev request');
        add('pre', JSON.stringify(panel.request, null, 2));
      }
      if (panel.questions) {
        add('h4', 'Scores requested');
        add('pre', JSON.stringify(panel.questions, null, 2));
      }
      if (panel.policy) {
        add('h4', 'Selection policy');
        add('pre', JSON.stringify(panel.policy, null, 2));
      }
      const connector = loop.querySelector(`[data-sections-connector="${item.flow}"]`);
      if (!reduceMotion && connector) {
        connector.classList.remove('is-flowing');
        void connector.getBoundingClientRect();
        connector.classList.add('is-flowing');
      }
    };
    const inspect = (key) => {
      const item = stations[key];
      loop.classList.add('is-inspecting');
      stationNodes.forEach((node) => node.classList.toggle('is-highlighted', node.dataset.sectionsStation === key));
      connectors.forEach((node) => node.classList.toggle('is-highlighted', item.connectors.includes(node.dataset.sectionsConnector)));
    };
    const clear = () => {
      loop.classList.remove('is-inspecting');
      stationNodes.forEach((node) => node.classList.remove('is-highlighted'));
      connectors.forEach((node) => node.classList.remove('is-highlighted'));
    };
    stationNodes.forEach((node) => {
      const key = node.dataset.sectionsStation;
      node.addEventListener('pointerenter', () => inspect(key));
      node.addEventListener('focus', () => inspect(key));
      node.addEventListener('pointerleave', clear);
      node.addEventListener('blur', clear);
      node.addEventListener('click', () => show(key));
      node.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); show(key); }
      });
    });
  });
})();
