const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {test} = require('node:test');

test('station selection shares keyboard and pointer behavior and respects reduced motion', () => {
  const script = fs.readFileSync('src/profitlab/web/static/pipeline-inspector.js', 'utf8');
  const makeClassList = () => ({values: new Set(), add(value) {this.values.add(value);},
    remove(value) {this.values.delete(value);}, toggle(value, on) {
      if (on === undefined) on = !this.values.has(value);
      if (on) this.values.add(value); else this.values.delete(value);
    }});
  const station = (key) => ({dataset: {sourceStation: key}, attrs: {}, classList: makeClassList(),
    handlers: {}, setAttribute(name, value) {this.attrs[name] = value;},
    addEventListener(name, callback) {this.handlers[name] = callback;}});
  const request = station('request');
  const convert = station('convert');
  const connector = {dataset: {sourceConnector: 'request-convert'}, classList: makeClassList()};
  const loop = {classList: makeClassList(), querySelectorAll(selector) {
    if (selector === '[data-source-station]') return [request, convert];
    if (selector === '[data-source-connector]') return [connector];
    return [];
  }};
  const card = {replaceChildren(...children) {this.children = children;}};
  const template = {content: {cloneNode() {return {text: 'Converted source'};}}};
  const article = {querySelector(selector) {
    if (selector === '[data-source-loop]') return loop;
    if (selector === '[data-station-card]') return card;
    if (selector === 'template[data-station-template="convert"]') return template;
    return null;
  }};
  const document = {querySelector(selector) {
    return selector === '[data-stage-container="source"]' ? article : null;
  }};
  vm.runInNewContext(script, {document, window: {matchMedia: () => ({matches: true})}});
  assert.equal(request.attrs['aria-pressed'], 'true');
  let prevented = false;
  convert.handlers.keydown({key: 'Enter', preventDefault() {prevented = true;}});
  assert.equal(prevented, true);
  assert.equal(convert.attrs['aria-pressed'], 'true');
  assert.equal(request.attrs['aria-pressed'], 'false');
  assert.equal(card.children[0].text, 'Converted source');
  assert.equal(connector.classList.values.has('is-flowing'), false);
  request.handlers.pointerenter();
  assert.equal(request.classList.values.has('is-highlighted'), true);
  request.handlers.pointerleave();
  assert.equal(request.classList.values.has('is-highlighted'), false);
  convert.handlers.click();
  assert.equal(card.children[0].text, 'Converted source');
});
