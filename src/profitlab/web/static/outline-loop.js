(() => {
  const details = {
    window: {
      number: '01', title: 'Window', heading: 'Choose a source-bounded reading unit',
      purpose: 'Keep each request anchored to a readable, overlapping section of the canonical filing.',
      input: 'Continuation context from the prior reconciled window.',
      output: 'Canonical line window.',
      check: 'Visible canonical lines only; no hidden or XBRL-only content.',
      example: '{lines: 841–1740, overlap: 60}',
      tooltip: 'Receives continuation context; emits a canonical line window.',
      connectors: ['reconcile-window', 'window-propose'], flow: 'window-propose'
    },
    propose: {
      number: '02', title: 'Propose', heading: 'Suggest navigation, not source text',
      purpose: 'Generate section labels and boundaries that help a reader navigate this window.',
      input: 'Canonical line window.', output: 'Navigation proposals.',
      check: 'The request may describe source; it may never replace or invent it.',
      example: '{title: "Revenue", start: 912, end: 948}',
      tooltip: 'Receives a canonical line window; emits navigation proposals.',
      connectors: ['window-propose', 'propose-validate'], flow: 'propose-validate'
    },
    validate: {
      number: '03', title: 'Validate', heading: 'Trust only proposals that match the filing',
      purpose: 'Test each proposed range, title, and quote against the exact canonical lines.',
      input: 'Navigation proposals.', output: 'Accepted ranges plus rejected proposals.',
      check: 'A proposal must stay in its window and exactly match the cited source.',
      example: '{accepted: [912–948], rejected: ["quote mismatch"]}',
      tooltip: 'Receives navigation proposals; emits accepted ranges and rejected proposals.',
      connectors: ['propose-validate', 'validate-reconcile'], flow: 'validate-reconcile'
    },
    reconcile: {
      number: '04', title: 'Reconcile', heading: 'Carry a coherent map into the next window',
      purpose: 'Deduplicate overlap and resolve boundaries into one ordered navigation map.',
      input: 'Accepted ranges plus rejected proposals.', output: 'Continuation context for the next Window.',
      check: 'Every canonical line gets one primary owner; uncertain gaps remain visibly warned.',
      example: '{prior: [{title: "Revenue", endsAt: 948}]}',
      tooltip: 'Receives validated ranges; emits continuation context to the next Window.',
      connectors: ['validate-reconcile', 'reconcile-window'], flow: 'reconcile-window'
    }
  };

  document.querySelectorAll('[data-outline-loop]').forEach((loop) => {
    const tooltip = loop.querySelector('.outline-loop-tooltip');
    const card = loop.parentElement.querySelector('#outline-loop-card');
    const runtime = document.querySelector('[data-outline-runtime]')?.content;
    const svg = loop.querySelector('svg');
    const stations = [...loop.querySelectorAll('[data-outline-station]')];
    const connectors = [...loop.querySelectorAll('[data-outline-connector]')];
    const runtimeText = (selector) => runtime?.querySelector(selector)?.textContent.trim() || 'Not available';
    const showPrompt = () => {
      const add = (tag, text, className) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        card.append(node);
      };
      card.replaceChildren();
      add('p', 'LLM request', 'eyebrow');
      add('h3', 'Prompt, system instruction, and tools');
      add('h4', 'System prompt');
      add('p', runtimeText('[data-outline-system-prompt]'));
      add('h4', 'User prompt');
      add('pre', runtimeText('[data-outline-user-prompt]'));
      add('h4', 'Tools');
      add('p', runtimeText('[data-outline-tools]'));
      add('h4', 'Response format');
      add('p', runtimeText('[data-outline-response-format]'));
      card.hidden = false;
    };

    // On phones, crop the same vertical SVG to its station column instead of
    // scaling its type down. The return path moves to the visible outer edge.
    const mobileLayout = window.matchMedia('(max-width: 600px)');
    const setLayout = () => {
      const returning = loop.querySelector('[data-outline-connector="reconcile-window"]');
      const returnLabel = loop.querySelector('.outline-loop-payloads text:last-child');
      if (mobileLayout.matches) {
        svg.setAttribute('viewBox', '180 0 360 760');
        returning.setAttribute('d', 'M520 596C666 596 666 91 520 91');
        returnLabel.setAttribute('x', '560');
      } else {
        svg.setAttribute('viewBox', '0 0 720 760');
        returning.setAttribute('d', 'M200 596C54 596 54 91 200 91');
        returnLabel.setAttribute('x', '116');
      }
    };
    setLayout();
    mobileLayout.addEventListener('change', setLayout);

    const proposeStation = loop.querySelector('[data-outline-station="propose"]');
    const proposePurpose = proposeStation.querySelector('.outline-loop-purpose');
    proposePurpose.textContent = 'Identify headings and';
    const purposeContinuation = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
    purposeContinuation.setAttribute('x', '224');
    purposeContinuation.setAttribute('dy', '16');
    purposeContinuation.textContent = 'boundaries in source lines.';
    proposePurpose.append(purposeContinuation);
    proposeStation.querySelector('.outline-loop-output').setAttribute('display', 'none');
    const expandPropose = () => {
      if (proposeStation.querySelector('[data-propose-detail]')) return;
      const makeText = (text, x, y, className, tooltip) => {
        const node = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        node.setAttribute('data-propose-detail', ''); node.setAttribute('x', x); node.setAttribute('y', y);
        node.setAttribute('class', className); node.textContent = text;
        if (tooltip) node.addEventListener('click', (event) => { event.stopPropagation(); showPrompt(); });
        proposeStation.append(node);
      };
      proposeStation.querySelector('rect').setAttribute('height', '280');
      svg.setAttribute('viewBox', mobileLayout.matches ? '180 0 360 900' : '0 0 720 900');
      makeText('Accepts', 224, 313, 'outline-loop-detail-label');
      makeText('Canonical lines 841–1740', 224, 331, 'outline-loop-detail-value');
      makeText('and prior section context.', 224, 346, 'outline-loop-detail-value');
      makeText('Does', 224, 370, 'outline-loop-detail-label');
      makeText('Sends each bounded line window and', 224, 388, 'outline-loop-detail-value');
      makeText('continuation context to the configured LLM', 224, 403, 'outline-loop-detail-value');
      makeText('with a navigation-only request.', 224, 418, 'outline-loop-detail-value');
      makeText('Prompt ⓘ', 224, 442, 'outline-loop-detail-prompt', 'Return JSON only with navigation proposals. For each section: use an exact title or quote, a source-bounded line range, type, parent hint, and continuation flag. Never replace source text.');
      makeText('Outputs', 224, 464, 'outline-loop-detail-label');
      makeText('{title: “Revenue”, start: 912, end: 948}', 224, 482, 'outline-loop-detail-value');
      ['validate', 'reconcile'].forEach((key) => loop.querySelector(`[data-outline-station="${key}"]`).setAttribute('transform', 'translate(0 168)'));
      loop.querySelector('[data-outline-connector="propose-validate"]').setAttribute('d', 'M360 495V544');
      loop.querySelector('[data-outline-connector="validate-reconcile"]').setAttribute('d', 'M360 656V705');
      loop.querySelector('[data-outline-connector="reconcile-window"]').setAttribute('d', mobileLayout.matches ? 'M520 817C666 817 666 91 520 91' : 'M200 817C54 817 54 91 200 91');
    };
    expandPropose();
    card.hidden = true;

    const clear = () => {
      loop.classList.remove('is-inspecting');
      stations.forEach((station) => station.classList.remove('is-highlighted'));
      connectors.forEach((connector) => connector.classList.remove('is-highlighted'));
      tooltip.hidden = true;
    };

    const inspect = (key, anchor) => {
      const item = details[key];
      loop.classList.add('is-inspecting');
      stations.forEach((station) => station.classList.toggle('is-highlighted', station.dataset.outlineStation === key));
      connectors.forEach((connector) => connector.classList.toggle('is-highlighted', item.connectors.includes(connector.dataset.outlineConnector)));
      // Highlights provide the handoff context; station content remains visible.
    };

    const select = (key) => {
      const item = details[key];
      const connector = loop.querySelector(`[data-outline-connector="${item.flow}"]`);
      connector.classList.remove('is-flowing');
      void connector.getBoundingClientRect();
      connector.classList.add('is-flowing');
    };

    stations.forEach((station) => {
      const key = station.dataset.outlineStation;
      station.addEventListener('pointerenter', () => inspect(key, station));
      station.addEventListener('focus', () => inspect(key, station));
      station.addEventListener('pointerleave', clear);
      station.addEventListener('blur', clear);
      station.addEventListener('click', () => select(key));
      station.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          select(key);
        }
      });
    });
  });
})();
