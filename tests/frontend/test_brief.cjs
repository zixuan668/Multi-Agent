const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname,'../..');
const brief = require('../../web/brief.js');
const fixture = {...brief.defaults,briefVersion:1,productName:'原味奶茶',productCategory:'食品饮料',productDescription:'提供冷热奶茶，支持到店自取。',productFeatures:'菜单确认：可以选择“无糖”或半糖。\n冷热均可。',priceStatus:'known',priceInfo:'12 元 / 杯',salesScope:'线下门店',salesRegion:'大学周边',purchaseStatus:'known',purchaseEntry:'门店自取',primaryGoal:'建立产品认知',marketingGoal:'让附近大学生了解点单选择',desiredAction:'到店了解或购买',audienceMode:'known',targetAudience:'门店附近大学生',marketingProblem:'产品差异讲不清楚',problemDetail:'顾客经常询问糖度',budgetMode:'amount',budgetRaw:'五千元',budgetAmount:'5000',currency:'CNY',periodMode:'duration',durationDays:'30',channelsState:'known',existingChannels:'门店微信群，发布权限待核实',materialsState:'known',availableMaterials:'自有菜单和实拍图',teamState:'known',teamResources:'店员每天可投入 30 分钟',constraintStatus:'known',specialRequirements:'禁止抖音渠道；不承诺减肥效果',brandStyle:'亲切直接'};
if(process.argv.includes('--payload')) { process.stdout.write(JSON.stringify(brief.payload(fixture))); process.exit(0); }

const payload = brief.payload(fixture);
assert.deepEqual(Object.keys(payload).sort(),['product_name','product_description','marketing_goal','target_audience','budget','campaign_period','special_requirements','budget_raw'].sort());
assert.ok(payload.product_description.includes(fixture.productFeatures),'literal feature evidence survives quotes and newlines');
assert.ok(payload.product_description.includes(fixture.productDescription));
assert.ok(payload.special_requirements.startsWith(fixture.specialRequirements));
assert.ok(payload.special_requirements.includes('店员每天可投入 30 分钟'));
assert.deepEqual(payload.budget,{amount:5000,currency:'CNY'});
assert.deepEqual(payload.campaign_period,{duration_days:30});
const restored = brief.fromRequirements(payload);
for(const id of brief.fields) assert.equal(restored[id],fixture[id],`restore ${id}`);
assert.equal(restored.periodMode,'duration');

const unknown = {...fixture,budgetMode:'unknown',periodMode:'unknown',audienceMode:'assist',priceStatus:'unknown',purchaseStatus:'unknown',channelsState:'none',materialsState:'unknown',teamState:'none',constraintStatus:'unknown'};
const uncertain = brief.payload(unknown);
assert.equal(uncertain.budget,null); assert.equal(uncertain.budget_raw,null); assert.equal(uncertain.campaign_period,null); assert.equal(uncertain.target_audience,null);
assert.ok(!uncertain.product_description.includes('12 元 / 杯'),'inactive price is not sent');
assert.ok(!uncertain.special_requirements.includes('自有菜单和实拍图'),'inactive resources are not sent');
assert.ok(!uncertain.special_requirements.includes('禁止抖音'),'inactive old restrictions are not sent');
assert.equal(brief.unpack(uncertain.special_requirements).detail.channelsState,'none');
assert.equal(brief.unpack(uncertain.special_requirements).detail.materialsState,'unknown');
assert.deepEqual(brief.payload({...fixture,budgetMode:'zero'}).budget,{amount:0,currency:'CNY'});
assert.deepEqual(brief.payload({...fixture,periodMode:'dates',startDate:'2026-10-08',endDate:'2026-10-28'}).campaign_period,{start_date:'2026-10-08',end_date:'2026-10-28'});

const legacy = {productName:'旧产品',productDescription:'原始介绍，不截断。',marketingGoal:'原始目标',targetAudience:'原始人群',budgetRaw:'5000 元',budgetAmount:'5000',durationDays:'21',specialRequirements:'原始限制'};
const migrated = brief.migrateDraft(legacy);
for(const [key,value] of Object.entries(legacy)) assert.equal(migrated[key],value);
assert.equal(migrated.primaryGoal,'其他');assert.equal(migrated.productFeatures,'','do not invent evidence for legacy drafts');
assert.equal(migrated.channelsState,'','new confirmations are not silently fabricated');
assert.equal(brief.fromRequirements({product_name:'旧产品',product_description:'旧介绍',marketing_goal:'旧目标',target_audience:null,budget:null,campaign_period:null,special_requirements:null,budget_raw:null}).productDescription,'旧介绍');
assert.equal(brief.unpack('普通介绍\n\n【智策需求补充 v1】\nnot-json').base,'普通介绍\n\n【智策需求补充 v1】\nnot-json','malformed historical text is preserved');
const markerText = {...fixture,productDescription:'原文含\n\n【智策需求补充 v1】\n这些字符'};
assert.equal(brief.fromRequirements(brief.payload(markerText)).productDescription,markerText.productDescription);

const page = fs.readFileSync(path.join(root,'web/workspace.html'),'utf8');
const ids = [...page.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
assert.equal(ids.length,new Set(ids).size,'HTML IDs are unique');
for(const id of brief.fields) assert.ok(ids.includes(id),`control ${id} exists`);
assert.ok(page.indexOf('/brief.js?')<page.indexOf('/app.js?'),'mapping loads before application');
assert.ok(!page.includes('field-help') && !page.includes('workspaceDescription') && !page.includes('input-guide'),'explanatory small print is removed rather than hidden');
for(const match of page.matchAll(/aria-describedby="([^"]+)"/g)) for(const id of match[1].split(' ')) assert.ok(ids.includes(id),`description ${id} resolves after cleanup`);
const styles=fs.readFileSync(path.join(root,'web/styles.css'),'utf8');
assert.ok(styles.includes('--workspace-font: "TeX Gyre Heros", Arial, "Microsoft YaHei", "微软雅黑", sans-serif;'),'workspace uses local Helvetica-like Latin and YaHei Chinese faces');
for(const face of ['regular','bold']) {
  const asset=`/fonts/tex-gyre-heros/texgyreheros-${face}.otf`;
  assert.ok(styles.includes(`url("${asset}")`),'font CSS uses same-origin assets');
  assert.equal(fs.readFileSync(path.join(root,'web',asset.slice(1))).subarray(0,4).toString('ascii'),'OTTO','real OpenType font is bundled');
}
assert.ok(styles.includes('unicode-range: U+0000-024F, U+1E00-1EFF;'),'Latin face does not override Chinese glyphs');
for(const file of ['GUST-FONT-LICENSE.txt','LPPL.txt','MANIFEST-TeX-Gyre-Heros.txt','README.md']) assert.ok(fs.existsSync(path.join(root,'web/fonts/tex-gyre-heros',file)),`font distribution includes ${file}`);
assert.ok(styles.includes('font: 12px/1.8 var(--workspace-font)'),'JSON display uses the workspace fonts too');

class Element {
  constructor() { this.value='';this.textContent='';this.style={};this.attrs={};this.dataset={};this.children=[];this.listeners={};this.classes=new Set();this.classList={toggle:(name,force)=>force?this.classes.add(name):this.classes.delete(name),contains:name=>this.classes.has(name)}; }
  addEventListener(name,handler){this.listeners[name]=handler;}
  setAttribute(name,value){this.attrs[name]=value;} removeAttribute(name){delete this.attrs[name];}
  append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this.children=nodes;}
}
const elements=new Map(ids.map(id=>[id,new Element()]));
const document={getElementById:id=>elements.get(id)||null,querySelectorAll:()=>[],querySelector:()=>null,createElement:()=>new Element()};
const context=vm.createContext({document,Map,Number});
vm.runInContext(fs.readFileSync(path.join(root,'web/brief.js'),'utf8'),context);
const script=fs.readFileSync(path.join(root,'web/app.js'),'utf8');
vm.runInContext(script.slice(0,script.indexOf('renderTemplates();restoreDraft();')),context);
function setValues(values){for(const id of brief.fields)elements.get(id).value=String(values[id]??'');context.choice=values.periodMode||'';vm.runInContext('periodMode=choice',context);}
setValues(fixture);
assert.equal(vm.runInContext('validateForm().length',context),0,'complete intake passes real UI validation');
elements.get('productFeatures').value='';
assert.ok(vm.runInContext('validateForm(0)',context).some(error=>error.node===elements.get('productFeatures')));
setValues(unknown);assert.equal(vm.runInContext('validateForm().length',context),0,'explicit unknown/none choices do not force invention');
vm.runInContext('updateBriefSummary()',context);
assert.ok(elements.get('briefSummary').children.some(node=>node.children.some(child=>child.textContent.includes('周期待定'))),'unknown period summary ignores stale duration');
setValues({...fixture,budgetAmount:'0'});assert.ok(vm.runInContext('validateForm(2)',context).some(error=>error.node===elements.get('budgetAmount')));
setValues({...fixture,periodMode:'dates',startDate:'2026-10-28',endDate:'2026-10-08'});assert.ok(vm.runInContext('validateForm(2)',context).some(error=>error.node===elements.get('endDate')));
setValues({...fixture,productDescription:'长'.repeat(5000)});assert.ok(vm.runInContext('validateForm(0)',context).some(error=>error.node===elements.get('productDescription')),'combined public field limit checked before submission');
setValues(fixture);vm.runInContext('showWorkspaceView("result")',context);assert.ok(elements.get('requirementsPanel').classList.contains('hidden'));assert.ok(!elements.get('resultPanel').classList.contains('hidden'));
vm.runInContext('showWorkspaceView("input")',context);assert.ok(elements.get('resultPanel').classList.contains('hidden'));assert.equal(elements.get('productFeatures').value,fixture.productFeatures,'switching view keeps draft');
assert.equal(elements.get('workspaceTitle').textContent,'策略智能体','input title stays correct after switching views');
const saved=new Map();context.localStorage={setItem:(key,value)=>saved.set(key,value)};
const handlerStart=script.indexOf('draftFields.forEach(id=>{const handler=');
vm.runInContext(script.slice(handlerStart,script.indexOf('try{currentTaskId=',handlerStart)),context);
elements.get('constraintStatus').value='none';elements.get('constraintStatus').listeners.change();
assert.equal(JSON.parse(saved.get('strategyRequirementDraft.v3')).constraintStatus,'none','latest confirmation is saved synchronously before a reload');
console.log('Brief: mapping, round-trip, legacy drafts, explicit unknown/none, conditional validation, limits, unique controls and separated views passed.');
