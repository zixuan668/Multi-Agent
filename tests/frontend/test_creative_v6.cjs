// Run the shipped B controller against its real DOM and a mock transport. No paid API.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'../..'),page=fs.readFileSync(path.join(root,'web/creative.html'),'utf8');
class El{
 constructor(tag='div',attrs={}){this.tagName=tag;this.attrs=attrs;this.children=[];this.value='';this.style={};this.disabled=false;this.dataset={};this.classes=new Set((attrs.class||'').split(/\s+/));this._text='';for(const [k,v]of Object.entries(attrs))if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=v;
 this.classList={add:(...v)=>v.forEach(x=>this.classes.add(x)),remove:(...v)=>v.forEach(x=>this.classes.delete(x)),contains:v=>this.classes.has(v),toggle:(v,on)=>{on=on===undefined?!this.classes.has(v):on;on?this.classes.add(v):this.classes.delete(v);return on;}};}
 get lastChild(){return this.children.at(-1);}get id(){return this.attrs.id;}get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}set textContent(v){this._text=String(v);this.children=[];}
 append(...nodes){this.children.push(...nodes);}replaceChildren(...nodes){this._text='';this.children=nodes;}
 setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k]??null;}focus(){}click(){if(this.onclick)return this.onclick();}remove(){}addEventListener(){}
 matches(s){if(s.startsWith('.'))return this.classes.has(s.slice(1));if(s.startsWith('#'))return this.id===s.slice(1);if(s.startsWith('[')){const m=s.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);return m&&m[1]in this.attrs&&(m[2]===undefined||this.attrs[m[1]]===m[2]);}return this.tagName===s;}
 querySelectorAll(s){const parts=s.split(' ');const out=[];for(const c of this.children){if(c.matches(parts[0])){if(parts.length===1)out.push(c);else out.push(...c.querySelectorAll(parts.slice(1).join(' ')));}out.push(...c.querySelectorAll(s));}return [...new Set(out)];}
 querySelector(s){return this.querySelectorAll(s)[0]||null;}
}
const document=new El('document'),stack=[document];
for(const match of page.matchAll(/<\/?([\w-]+)([^>]*)>|([^<]+)/g)){
 if(match[3]){stack.at(-1)._text+=match[3];continue;}
 const tag=match[1];if(match[0].startsWith('</')){for(let i=stack.length-1;i>0;i--)if(stack[i].tagName===tag){stack.length=i;break;}continue;}
 const attrs=Object.fromEntries([...match[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g)].map(m=>[m[1],m[2]??'']));const n=new El(tag,attrs);stack.at(-1).append(n);if(!['meta','link','input','br','hr','img'].includes(tag))stack.push(n);
}
document.getElementById=id=>document.querySelector('#'+id);document.createElement=tag=>new El(tag);document.body=document.querySelector('body');
const handoff=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/creative/valid-milk-owned.json'),'utf8'));
const context={...handoff.strategy.data,product_name:handoff.requirements.product_name,explicit_constraints:'不虚构优惠',budget:handoff.requirements.budget,resources:{channels:{status:'known',detail:'已有渠道'}}};
const data={items:[{channel:context.channels[0].name,copy:'初稿正文',slogan:'原始短句',poster_concept:'【标题】产品',video_script:'0–20s｜产品文字',evidence:[],pending_confirmations:[]}]};
const v1={result_id:'creative-test-1',version:1,round_no:1,strategy_result_id:handoff.strategy.result_id,strategy_version:1,created_at:new Date().toISOString(),creative_instruction:'自然直接',data,edit_trace:[{path:'items[0].slogan',source:'ai_draft'}],feedback_applied:[],previous_result_id:null};
const record={handoff,context,versions:[v1],deliveries:[],feedback:[],events:[],state:'ready',last_error:null,demo_enabled:true};
const calls=[],savedDrafts=new Map(),delays=[];let evaluationStatus='succeeded',evaluationReads=0;
async function request(url,body){calls.push({url,body});if(url==='/api/session')return{};if(url==='/api/creative/history')return {items:[]};if(url.includes('/evaluation/state')){evaluationReads++;assert.equal(ctx.location.href,'','stay on B until conclusion exists');return {job:{status:evaluationReads===1?'running':evaluationStatus,stage:'generating',creative_result_id:record.versions.at(-1).result_id,error:evaluationStatus==='failed'?{message:'测试评估失败'}:null}};}if(url.endsWith('/package')||url.includes('/package?'))return {...handoff,creative:record.versions.at(-1)};if(url.endsWith('/delivery')){record.state='pending';record.deliveries.push({delivery_id:'delivery-test'});return {evaluation_job:{status:'running'}};}if(url.endsWith('/state'))return structuredClone(record);if(url.endsWith('/operations')){assert.equal(body.action,'edit');const v2=structuredClone(v1);v2.result_id='creative-test-2';v2.version=2;v2.previous_result_id=v1.result_id;v2.data.items[0].slogan=body.value;v2.edit_trace=[{path:body.path,source:'human'}];record.versions.push(v2);record.job={status:'succeeded'};return record.job;}throw Error('Unexpected network operation '+url);}
const win={CreativeAPI:{request,url:(t,o)=>`/api/tasks/${t}/creative/${o}`,node:(tag,text,cls)=>{const n=new El(tag);if(text!==undefined)n.textContent=text;if(cls)n.classes=new Set(cls.split(' '));return n;}},addEventListener(){}};
const ctx=vm.createContext({window:win,document,URLSearchParams,location:{search:'?task_id='+handoff.task_id,href:''},history:{replaceState(){}},sessionStorage:{setItem:(k,v)=>savedDrafts.set(k,v),getItem:k=>savedDrafts.get(k)||null},navigator:{clipboard:{writeText:async()=>{}}},setTimeout:(fn,ms)=>{delays.push(ms);queueMicrotask(fn);return 1;},clearTimeout(){},Blob,URL,console});
vm.runInContext(fs.readFileSync(path.join(root,'web/creative.js'),'utf8'),ctx);
const flush=()=>new Promise(r=>setImmediate(r));
async function run(){
 await flush();await flush();const id=x=>document.getElementById(x),button=(attr,value)=>document.querySelector(`[${attr}="${value}"]`);
 assert.match(id('creativeRoundChip').textContent,/创意已保存/,'real controller must finish its first render');
 assert.equal(id('copyOutput').textContent,'初稿正文',id('toast').textContent);assert.equal(id('creativeInstruction').value,'自然直接');
 await button('data-tab','slogan').click();assert.equal(button('data-pane','copy').classList.contains('hidden'),true);assert.equal(button('data-pane','slogan').classList.contains('hidden'),false);
 await document.querySelectorAll('[data-action]').find(b=>b.dataset.field==='slogan'&&b.dataset.action==='edit').click();id('sloganEditor').value='人工短句';id('sloganEditor').oninput({target:id('sloganEditor')});
 await button('data-tab','poster').click();await button('data-tab','slogan').click();assert.equal(id('sloganEditor').value,'人工短句','tab switch keeps unsaved text');await id('packageBtn').click();assert.equal(id('issueModal').classList.contains('hidden'),false,'dirty draft opens a blocking dialog');await id('confirmIssues').click();
 assert.equal(calls.filter(c=>c.body!==undefined).length,0,'loading, rendering and tab/edit draft actions do not call model');
 await button('data-save-edit','slogan').click();await flush();await flush();
 assert.match(id('creativeRoundChip').textContent,/创意已保存/);assert.equal(record.versions[0].data.items[0].slogan,'原始短句');assert.equal(id('sloganOutput').textContent,'人工短句');assert.match(id('sloganHistory').textContent,/人工修改/);
 assert.equal(calls.filter(c=>c.url.endsWith('/operations')).length,1,'one save, one scoped operation');
 assert.ok(!delays.includes(650)&&!delays.includes(850)&&!delays.includes(400),'completed model/save operations do not wait for staged animation timers');
 assert.equal(document.getElementById('versionControls'),null,'history controls removed');assert.equal(document.getElementById('railCard0'),null,'source sidebar removed');assert.equal(document.getElementById('checkIssues'),null,'no inline issue area');assert.equal(document.getElementById('jsonPreview'),null,'no JSON handoff preview');assert.equal(document.getElementById('packageFields'),null,'no technical version chain');
 record.demo_enabled=false;
 await id('packageBtn').click();assert.equal(id('cHandoffModal').classList.contains('hidden'),false);
 await Promise.all([id('deliverCBtn').click(),id('deliverCBtn').click()]);assert.match(ctx.location.href,/evaluation\/\?task_id=.*receive=1/);assert.equal(evaluationReads,0,'enter C immediately; no model wait on B');
 assert.equal(calls.filter(c=>c.url.endsWith('/delivery')).length,1,'double click submits only once');
 ctx.location.href='';
 const posted=calls.filter(c=>c.body!==undefined).length;evaluationStatus='succeeded';evaluationReads=0;
 vm.runInContext(fs.readFileSync(path.join(root,'web/creative.js'),'utf8'),ctx);await flush();await flush();
 assert.match(ctx.location.href,/evaluation\/\?task_id=/);assert.equal(calls.filter(c=>c.body!==undefined).length,posted,'refresh returns to C without resubmitting');
 console.log('B v6: actual DOM/controller renders, tabs isolate content, drafts survive switches, dirty delivery blocks, save appends version, source trace, simplified dialogs and hidden history; reads never generate.');
}
run().catch(e=>{console.error(e);process.exitCode=1;});
