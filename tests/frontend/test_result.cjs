// Run the actual result renderer; optional isolated preview never calls a model.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.resolve(__dirname,'../..');
const script = fs.readFileSync(path.join(root,'web/app.js'),'utf8');
const source = script.slice(0,script.indexOf('renderTemplates();restoreDraft();'));
const page = fs.readFileSync(path.join(root,'web/workspace.html'),'utf8');
const fixture = JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/creative/valid-milk-zero.json'),'utf8'));
const task = {requirements:fixture.requirements,result:fixture.strategy,status:'completed',stage:'completed',attempt_diagnostics:[],config_snapshot:{provider:'offline'}};
class Element {
  constructor() {
    this.children=[];this.textContent='';this.value='';this.style={};this.classes=new Set();
    this.classList={add:v=>this.classes.add(v),remove:v=>this.classes.delete(v),toggle:(v,enabled)=>enabled?this.classes.add(v):this.classes.delete(v),contains:v=>this.classes.has(v)};
  }
  append(...nodes){this.children.push(...nodes);}
  appendChild(node){this.children.push(node);}
  replaceChildren(...nodes){this.children=nodes;}
  addEventListener(){}
  setAttribute(){}
  querySelectorAll(){return [];}
  get text(){return [this.textContent,...this.children.map(c=>c.text)].join(' ');}
}
const elements = new Map([...page.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element()]));
const document={getElementById:id=>elements.get(id),createElement:()=>new Element(),querySelectorAll:()=>[]};
const context=vm.createContext({document,task});
for(const name of ['brief','examples','presentation']) vm.runInContext(fs.readFileSync(path.join(root,'web',name+'.js'),'utf8'),context);
vm.runInContext(source,context);
vm.runInContext('renderTask(task);renderResult(task.result)',context);
assert.equal(elements.get('firstAction').textContent,task.result.data.marketing_strategy.promotion_methods[0]);
assert.equal(elements.get('promotionMethods').children.length,Math.max(1,task.result.data.marketing_strategy.promotion_methods.length-1));
assert.match(elements.get('summaryBudget').textContent,/零预算/);
assert.match(elements.get('channels').text,/零预算/);
assert.doesNotMatch(elements.get('channels').text,/预算：待预算明确/);
assert.equal(elements.get('rawJson').textContent,JSON.stringify(task.result,null,2),'rendering never rewrites exported strategy');
const exported=vm.runInContext('formattedStrategy()',context);
assert.ok(exported.indexOf('二、执行顺序') < exported.indexOf('三、渠道分工'),'text export follows the decision reading order');
assert.ok(exported.includes('零预算'),'zero budget also exports correctly');
for(const id of ['firstAction','promotionMethods','contentDirections','channels','sellingPoints']) assert.ok(elements.get(id).text.length>0,id+' renders');
console.log('Result: real renderer, first action, remaining steps, zero-budget state, evidence and immutable JSON passed.');

if(process.argv.includes('--preview')) {
  let previewTask=task;
  const reportArg=process.argv.indexOf('--report');
  if(reportArg>=0) {
    const report=JSON.parse(fs.readFileSync(process.argv[reportArg+1],'utf8'));
    const record=report.records.find(v=>v.actual?.status==='succeeded' && v.case_id==='example-tea') || report.records.find(v=>v.actual?.status==='succeeded');
    if(!record) throw new Error('No successful preview record');
    previewTask={requirements:record.input.requirements,result:record.actual,status:'completed',stage:'completed',attempt_diagnostics:[],config_snapshot:{provider:report.model_mode||'compatible'}};
  }
  const previewScript=source+'\nrenderTask('+JSON.stringify(previewTask)+');renderResult(latestTask.result);showWorkspaceView("result");document.querySelectorAll("[data-result-tab]").forEach(button=>button.addEventListener("click",()=>selectResultTab(button.dataset.resultTab)));';
  const http=require('node:http');
  http.createServer((req,res)=>{
    const route=new URL(req.url,'http://localhost').pathname;
    if(route==='/app.js'){res.setHeader('Content-Type','application/javascript; charset=utf-8');res.end(previewScript);return;}
    const relative=route==='/workspace'||route==='/'?'workspace.html':route.slice(1);
    const filename=path.resolve(root,'web',relative);
    if(!filename.startsWith(path.resolve(root,'web')+path.sep)||!fs.existsSync(filename)||!fs.statSync(filename).isFile()){res.writeHead(404);res.end();return;}
    res.setHeader('Content-Type',filename.endsWith('.js')?'application/javascript; charset=utf-8':filename.endsWith('.css')?'text/css; charset=utf-8':filename.endsWith('.otf')?'font/otf':'text/html; charset=utf-8');
    res.setHeader('Cache-Control','no-store');
    res.end(fs.readFileSync(filename));
  }).listen(8002,'127.0.0.1',()=>console.log('Isolated result preview: http://127.0.0.1:8002/workspace'));
}
