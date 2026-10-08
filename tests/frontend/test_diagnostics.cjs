// Exercise the real diagnostic renderer without making any model calls.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'web/app.js'), 'utf8');
const page = fs.readFileSync(path.join(root, 'web/workspace.html'), 'utf8');

class Element {
  constructor(tag = 'div') {
    this.tag = tag;
    this.textContent = '';
    this.children = [];
    this.classes = new Set();
    this.classList = {
      contains: name => this.classes.has(name),
      toggle: (name, force) => {
        const enabled = force === undefined ? !this.classes.has(name) : force;
        if (enabled) this.classes.add(name); else this.classes.delete(name);
      },
    };
  }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.children.push(node); }
  replaceChildren(...nodes) { this.children = nodes; }
  get text() { return [this.textContent, ...this.children.map(node => node.text)].join(' '); }
}

const elements = new Map();
const document = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  },
  createElement: tag => new Element(tag),
};
const context = vm.createContext({document, Map, Number});
vm.runInContext(fs.readFileSync(path.join(root,'web/brief.js'),'utf8'), context);
// Only omit page initialization/event wiring; renderer functions are unchanged.
vm.runInContext(source.slice(0, source.indexOf('renderTemplates();restoreDraft();')), context);
const issue = index => ({category:'quality', field:`channels[${index}].content_direction`, message:'已分配预算的渠道必须说明预算用于哪项具体执行动作'});
const fixture = {
  status:'failed', stage:'failed', attempt_count:3,
  attempt_diagnostics:[
    {attempt_count:1, duration_ms:82800, error_code:'OUTPUT_INVALID', issues:[issue(0),issue(1)]},
    {attempt_count:2, duration_ms:49400, error_code:'OUTPUT_INVALID', issues:[issue(0),issue(1)]},
    {attempt_count:3, duration_ms:48700, error_code:'OUTPUT_INVALID', issues:[issue(1)]},
  ],
};
context.task = fixture;
document.getElementById('diagnostics').classList.toggle('hidden', true);
vm.runInContext('renderDiagnostics(task)', context);
const timeline = document.getElementById('diagnosticItems');
assert.equal(timeline.children.length, 3);
assert.equal(timeline.children[0].children.filter(node => node.className === 'diagnostic-issue').length, 1, 'duplicate reasons merge');
assert.match(timeline.children[0].text, /第 1 个渠道 · 内容与预算用途/);
assert.match(timeline.children[0].text, /第 2 个渠道 · 内容与预算用途/);
assert.match(timeline.children[2].text, /本次处理已结束，问题仍未解决/);
assert.equal(document.getElementById('diagnostics').open, true, 'failed records expand initially');
document.getElementById('diagnostics').open = false;
vm.runInContext('renderDiagnostics(task)', context);
assert.equal(document.getElementById('diagnostics').open, false, 'refresh preserves user collapse');
context.task = {status:'completed', attempt_diagnostics:[{attempt_count:1, duration_ms:100, error_code:null, issues:[]}]};
vm.runInContext('renderDiagnostics(task)', context);
assert.match(timeline.text, /校验通过/);
assert.match(timeline.text, /未发现阻断问题/);
context.task = {status:'failed', attempt_diagnostics:[{attempt_count:1, error_code:'MODEL_TIMEOUT', issues:[]}]};
vm.runInContext('renderDiagnostics(task)', context);
assert.match(timeline.text, /模型响应超时/);
assert.doesNotMatch(timeline.text, /NaN/);
context.task = {status:'running', attempt_diagnostics:[]};
vm.runInContext('renderDiagnostics(task)', context);
assert.equal(document.getElementById('diagnostics').classList.contains('hidden'), true);
assert.equal(timeline.children.length, 0);
assert.doesNotMatch(page, /id="task(Status|Meta)"/);
assert.doesNotMatch(source, /\$\("task(Status|Meta)"\)/);
console.log('Diagnostics: grouping, positions, failure/success/timeout, disclosure state and removed UI passed.');

if (process.argv.includes('--preview')) {
  const http = require('node:http');
  const previewScript = source.slice(0, source.indexOf('renderTemplates();restoreDraft();')) + `\nrenderTask(${JSON.stringify(fixture)});document.getElementById('emptyState').classList.add('hidden');`;
  http.createServer((req, res) => {
    const isCss = req.url.startsWith('/styles.css');
    const isJs = req.url.startsWith('/app.js');
    const isBrief = req.url.startsWith('/brief.js');
    res.setHeader('Content-Type', isCss ? 'text/css' : isJs || isBrief ? 'application/javascript' : 'text/html; charset=utf-8');
    res.end(isCss ? fs.readFileSync(path.join(root,'web/styles.css')) : isBrief ? fs.readFileSync(path.join(root,'web/brief.js')) : isJs ? previewScript : page.replace('panel result-panel hidden','panel result-panel'));
  }).listen(8001, '127.0.0.1', () => console.log('Visual fixture: http://127.0.0.1:8001/workspace'));
}
