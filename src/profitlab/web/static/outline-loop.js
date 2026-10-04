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
    const runtimeText = (selector, fallback = 'Not available') => runtime?.querySelector(selector)?.textContent.trim() || fallback;
    const prettyJson = (value) => {
      try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; }
    };
    const inspection = (() => {
      try { return JSON.parse(runtimeText('[data-outline-inspection]', '{}')); } catch { return {}; }
    })();
    const showPrompt = () => {
      const add = (tag, text, className) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        card.append(node);
      };
      card.replaceChildren();
      add('p', 'LLM request', 'eyebrow');
      add('h3', 'Prompt, system instruction, and returned object');
      add('h4', 'System prompt');
      add('p', runtimeText('[data-outline-system-prompt]'));
      add('h4', 'User prompt');
      add('pre', runtimeText('[data-outline-user-prompt]'));
      add('h4', 'Illustrative response instance');
      add('pre', prettyJson(runtimeText('[data-outline-response-contract]')));
      card.hidden = false;
    };
    const showStationLogic = (key, item) => {
      const panel = inspection[key];
      if (!panel) return;
      const add = (tag, text, className) => {
        const node = document.createElement(tag);
        if (className) node.className = className;
        node.textContent = text;
        card.append(node);
      };
      card.replaceChildren();
      add('p', `${item.number} · ${item.title}`, 'eyebrow');
      add('h3', item.heading);
      add('h4', 'Accepts');
      add('pre', JSON.stringify(panel.accepts, null, 2));
      add('h4', 'Does');
      add('p', panel.does);
      add('h4', 'Outputs');
      add('pre', JSON.stringify(panel.outputs, null, 2));
      add('h4', 'Guarantee');
      add('p', panel.guarantee);
      card.hidden = false;
    };

    // On phones, crop the same vertical SVG to its station column instead of
    // scaling its type down. The return path moves to the visible outer edge.
    const mobileLayout = window.matchMedia('(max-width: 600px)');
    const setLayout = () => {
      const returning = loop.querySelector('[data-outline-connector="reconcile-window"]');
      const returnLabel = loop.querySelector('.outline-loop-payloads text:last-child');
      if (mobileLayout.matches) {
        svg.setAttribute('viewBox', '180 0 360 1290');
        returning.setAttribute('d', 'M520 1180C666 1180 666 91 520 91');
        returnLabel.setAttribute('x', '560');
      } else {
        svg.setAttribute('viewBox', '0 0 720 1290');
        returning.setAttribute('d', 'M200 1180C54 1180 54 91 200 91');
        returnLabel.setAttribute('x', '116');
      }
    };
    setLayout();
    mobileLayout.addEventListener('change', setLayout);

    const expandStation = (key, layout) => {
      const station = loop.querySelector(`[data-outline-station="${key}"]`);
      if (station.querySelector('[data-station-detail]')) return;
      const makeText = (text, x, y, className) => {
        const node = document.createElementNS('http://www.w3.org/2000/svg', 'text');
        node.setAttribute('data-station-detail', ''); node.setAttribute('x', x); node.setAttribute('y', y);
        node.setAttribute('class', className); node.textContent = text;
        station.append(node);
      };
      if (layout.translate) station.setAttribute('transform', `translate(0 ${layout.translate})`);
      station.querySelector('rect').setAttribute('height', layout.height);
      const purpose = station.querySelector('.outline-loop-purpose');
      purpose.textContent = layout.purpose[0];
      layout.purpose.slice(1).forEach((line) => {
        const continuation = document.createElementNS('http://www.w3.org/2000/svg', 'tspan');
        continuation.setAttribute('x', '224');
        continuation.setAttribute('dy', '16');
        continuation.textContent = line;
        purpose.append(continuation);
      });
      station.querySelector('.outline-loop-output').setAttribute('display', 'none');
      layout.detail.forEach(([text, y, className]) => makeText(text, 224, y, className));
    };
    expandStation('window', {
      height: '250', purpose: ['Select a bounded canonical-line', 'slice from the filing.'],
      detail: [
        ['Accepts', 155, 'outline-loop-detail-label'],
        ['Prior continuation context.', 173, 'outline-loop-detail-value'],
        ['Does', 197, 'outline-loop-detail-label'],
        ['Preserves a readable, overlapping set of', 215, 'outline-loop-detail-value'],
        ['visible canonical source lines.', 230, 'outline-loop-detail-value'],
        ['Outputs', 259, 'outline-loop-detail-label'],
        ['{lines: 841–1740, overlap: 60}', 277, 'outline-loop-detail-value']
      ]
    });
    expandStation('propose', {
      translate: 113, height: '280', purpose: ['Identify headings and', 'boundaries in source lines.'],
      detail: [
        ['Accepts', 313, 'outline-loop-detail-label'],
        ['Canonical lines 841–1740', 331, 'outline-loop-detail-value'],
        ['and prior section context.', 346, 'outline-loop-detail-value'],
        ['Does', 370, 'outline-loop-detail-label'],
        ['Sends each bounded line window and', 388, 'outline-loop-detail-value'],
        ['continuation context to the configured LLM', 403, 'outline-loop-detail-value'],
        ['with a navigation-only request.', 418, 'outline-loop-detail-value'],
        ['Outputs', 464, 'outline-loop-detail-label'],
        ['{title: “Revenue”, start: 912, end: 948}', 482, 'outline-loop-detail-value']
      ]
    });
    expandStation('validate', {
      translate: 268, height: '250', purpose: ['Check every proposed range, title,', 'and quote against the source.'],
      detail: [
        ['Accepts', 487, 'outline-loop-detail-label'],
        ['Navigation proposals.', 505, 'outline-loop-detail-value'],
        ['Does', 529, 'outline-loop-detail-label'],
        ['Requires an exact source match within', 547, 'outline-loop-detail-value'],
        ['the proposed canonical-line window.', 562, 'outline-loop-detail-value'],
        ['Outputs', 591, 'outline-loop-detail-label'],
        ['{accepted: [912–948], rejected: […]}', 609, 'outline-loop-detail-value']
      ]
    });
    expandStation('reconcile', {
      translate: 393, height: '250', purpose: ['Resolve overlap into one', 'ordered navigation map.'],
      detail: [
        ['Accepts', 648, 'outline-loop-detail-label'],
        ['Accepted ranges and rejected proposals.', 666, 'outline-loop-detail-value'],
        ['Does', 690, 'outline-loop-detail-label'],
        ['Deduplicates overlap and carries the', 708, 'outline-loop-detail-value'],
        ['last validated section into the next window.', 723, 'outline-loop-detail-value'],
        ['Outputs', 752, 'outline-loop-detail-label'],
        ['{prior: [{title: “Revenue”, endsAt: 948}]}', 770, 'outline-loop-detail-value']
      ]
    });
    loop.querySelector('[data-outline-connector="window-propose"]').setAttribute('d', 'M360 292V328');
    loop.querySelector('[data-outline-connector="propose-validate"]').setAttribute('d', 'M360 608V644');
    loop.querySelector('[data-outline-connector="validate-reconcile"]').setAttribute('d', 'M360 894V930');
    const payloads = loop.querySelectorAll('.outline-loop-payloads text');
    payloads[0].setAttribute('y', '315');
    payloads[1].setAttribute('y', '631');
    payloads[2].setAttribute('y', '917');
    loop.querySelector('.outline-loop-return').setAttribute('y', '1232');
    setLayout();
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
      if (key === 'propose') showPrompt(); else showStationLogic(key, item);
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
