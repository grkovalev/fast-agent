(() => {
  const stations = {
    request: {
      number: '01', title: 'Request', heading: 'Retrieve the authoritative primary filing',
      accepts: 'Selected ticker and annual-filing identity.',
      does: 'Locates and requests the SEC primary annual filing for the report.',
      outputs: (runtime) => runtime.received,
      guarantee: 'The document identity is retained before any downstream transformation.',
      connectors: ['request-convert'], flow: 'request-convert'
    },
    convert: {
      number: '02', title: 'Convert', heading: 'Preserve what a reader can actually see',
      accepts: (runtime) => runtime.received,
      does: 'Converts the filing to canonical visible text and removes hidden and Inline XBRL-only content plus taxonomy, context, unit, scale, and format metadata.',
      outputs: 'Sanitized visible lines.',
      guarantee: 'No source text is invented; removed metadata never reaches navigation or extraction.',
      connectors: ['request-convert', 'convert-store'], flow: 'convert-store'
    },
    store: {
      number: '03', title: 'Store', heading: 'Make each visible line inspectable',
      accepts: 'Sanitized visible lines and their source HTML anchors.',
      does: 'Persists a canonical document with stable line numbers and sanitized HTML anchors.',
      outputs: (runtime) => runtime.stored,
      guarantee: 'Every later source link resolves to this retained, line-addressable record.',
      connectors: ['convert-store'], flow: 'convert-store'
    }
  };

  document.querySelectorAll('[data-source-loop]').forEach((loop) => {
    const card = loop.parentElement.querySelector('#source-loop-card');
    const runtimeNode = loop.closest('.source-stage-slot')?.querySelector('[data-source-runtime]')?.content;
    const runtime = {
      request: runtimeNode?.querySelector('[data-source-request]')?.textContent.trim() || 'SEC primary filing',
      received: runtimeNode?.querySelector('[data-source-received]')?.textContent.trim() || 'Primary filing HTML',
      stored: runtimeNode?.querySelector('[data-source-stored]')?.textContent.trim() || 'Canonical visible lines pending'
    };
    const stationNodes = [...loop.querySelectorAll('[data-source-station]')];
    const connectors = [...loop.querySelectorAll('[data-source-connector]')];
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const value = (item, key) => typeof item[key] === 'function' ? item[key](runtime) : item[key];
    const show = (key) => {
      const item = stations[key];
      card.replaceChildren();
      const add = (tag, text, className) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        card.append(node);
      };
      const dl = document.createElement('dl');
      [['Accepts', value(item, 'accepts')], ['Does', value(item, 'does')],
       ['Outputs', value(item, 'outputs')], ['Guarantee', value(item, 'guarantee')]].forEach(([term, description]) => {
        const row = document.createElement('div');
        const dt = document.createElement('dt'); const dd = document.createElement('dd');
        dt.textContent = term; dd.textContent = description; row.append(dt, dd); dl.append(row);
      });
      add('p', `${item.number} · ${item.title}`, 'eyebrow');
      add('h3', item.heading);
      card.append(dl);
      const connector = loop.querySelector(`[data-source-connector="${item.flow}"]`);
      if (!reduceMotion && connector) {
        connector.classList.remove('is-flowing');
        void connector.getBoundingClientRect();
        connector.classList.add('is-flowing');
      }
    };
    const inspect = (key) => {
      const item = stations[key];
      loop.classList.add('is-inspecting');
      stationNodes.forEach((node) => node.classList.toggle('is-highlighted', node.dataset.sourceStation === key));
      connectors.forEach((node) => node.classList.toggle('is-highlighted', item.connectors.includes(node.dataset.sourceConnector)));
    };
    const clear = () => {
      loop.classList.remove('is-inspecting');
      stationNodes.forEach((node) => node.classList.remove('is-highlighted'));
      connectors.forEach((node) => node.classList.remove('is-highlighted'));
    };
    stationNodes.forEach((node) => {
      const key = node.dataset.sourceStation;
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
