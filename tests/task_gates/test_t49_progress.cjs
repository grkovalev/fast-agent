const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

test('live state updates both counters and the expanded stage timer, then stops at terminal state', async () => {
  const script = fs.readFileSync('src/profitlab/web/static/v2-progress.js', 'utf8');
  const nodes = new Map();
  const node = (selector, extras = {}) => {
    const value = {
      dataset: {}, textContent: '', className: '',
      attrs: {},
      classList: {toggle() {}},
      setAttribute(key, data) { this.attrs[key] = data; },
      removeAttribute(key) { delete this.attrs[key]; },
      replaceChildren(...children) { this.children = children; },
      append(...children) { this.children = children; },
      ...extras,
    };
    nodes.set(selector, value);
    return value;
  };
  node('[data-v2-run]', {dataset: {v2Run: 'test-run'}});
  node('[data-stage="source"]', {dataset: {stage: 'source', stageStatus: 'queued'}});
  const container = node('[data-stage-container="source"]');
  node('[data-stage-card="source"]');
  const duration = node('[data-stage-duration="source"]');
  node('[data-stage-progress="source"]');
  node('[data-total-progress]');
  node('[data-map-progress]');
  node('[data-current-stage]');
  node('[data-map-run-status]');
  node('#v2-run-status');
  const accounting = node('[data-stage-accounting]', {dataset: {stageAccounting: 'source'}});
  const inspector = {selection: 'convert'};
  const document = {
    hidden: false,
    querySelector: (selector) => nodes.get(selector) || null,
    querySelectorAll: (selector) => {
      if (selector === '[data-stage]') return [nodes.get('[data-stage="source"]')];
      if (selector === '[data-stage-duration]') return [duration];
      if (selector === '[data-stage-accounting]') return [accounting];
      return [];
    },
    createElement: () => ({setAttribute() {}, textContent: ''}),
    importNode: (value) => value,
    addEventListener() {},
  };
  const timeouts = new Map();
  const intervals = new Map();
  let nextTimer = 0;
  let source;
  class EventSource {
    constructor() { source = this; this.closed = false; }
    addEventListener(kind, callback) { this[kind] = callback; }
    close() { this.closed = true; }
  }
  let state = {run: {status: 'running', selected_stage: 'source', summary: 'working'},
    stages: [{stage: 'source', position: 1, status: 'running', total_work: null,
      completed_work: 0, started_at: new Date(Date.now() - 5000).toISOString(),
      active_seconds: 1.2, queued_seconds: 2, retry_backoff_seconds: 0}]};
  const context = {
    document, Date, EventSource,
    DOMParser: class {parseFromString() {
      return {querySelectorAll: () => [{dataset: {stageAccounting: 'source'},
        childNodes: [{textContent: 'Persisted: zero'}]}]};
    }},
    window: {EventSource, addEventListener() {}},
    fetch: async (url) => url.endsWith('/pipeline')
      ? {ok: true, text: async () => '<html></html>'}
      : {ok: true, json: async () => state},
    setTimeout: (callback) => { const id = ++nextTimer; timeouts.set(id, callback); return id; },
    clearTimeout: (id) => timeouts.delete(id),
    setInterval: (callback) => { const id = ++nextTimer; intervals.set(id, callback); return id; },
    clearInterval: (id) => intervals.delete(id),
  };
  vm.runInNewContext(script, context);
  const flush = async () => {
    const callbacks = [...timeouts.values()];
    timeouts.clear();
    for (const callback of callbacks) await callback();
  };
  await flush();
  assert.equal(nodes.get('[data-current-stage]').textContent, 'Source');
  assert.equal(nodes.get('[data-map-progress]').textContent, '0 of 8 stages complete');
  assert.equal(nodes.get('[data-stage-progress="source"]').textContent, 'Work total pending');
  assert.match(duration.textContent, /Wall elapsed .*recorded active 1.2s · queued 2.0s/);
  assert.equal(container.attrs['aria-current'], 'step');
  state = {run: {status: 'completed', selected_stage: 'source', summary: 'done'},
    stages: [{...state.stages[0], status: 'completed', total_work: 0,
      started_at: null, active_seconds: 1.8}]};
  source.pipeline();
  await flush();
  assert.equal(nodes.get('[data-total-progress]').textContent, '1 of 8 complete');
  assert.equal(nodes.get('[data-map-progress]').textContent, '1 of 8 stages complete');
  assert.equal(nodes.get('[data-current-stage]').textContent, 'None');
  assert.equal(nodes.get('[data-stage-progress="source"]').textContent, '0 / 0');
  assert.equal(duration.textContent, 'Active 1.8s');
  assert.equal(accounting.children[0].textContent, 'Persisted: zero');
  assert.equal(inspector.selection, 'convert');
  assert.equal(source.closed, true);
  assert.equal(intervals.size, 0);
  source.onerror();
  assert.equal(intervals.size, 0);
});
