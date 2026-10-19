/* v6 DOM controller. Every business state comes from the owner-scoped server. */
(() => {
 'use strict';
 const $=id=>document.getElementById(id), all=s=>[...document.querySelectorAll(s)];
 const {request,url,node}=window.CreativeAPI;
 const params=new URLSearchParams(location.search);
 const state={task:params.get('task_id'),record:null,selected:null,channel:params.get('channel'),tab:'copy',busy:false,drafts:{},instructionReady:false,revisionVisible:false};
 const fields={copy:'copy',slogan:'slogan',poster:'poster_concept',video:'video_script'};
 const labels={copy:'社群主文案',slogan:'核心短句',poster:'海报文字',video:'短视频脚本'};
 const sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const current=()=>state.record?.versions.find(v=>v.result_id===state.selected)||state.record?.versions.at(-1);
 const latest=()=>state.record?.versions.at(-1);
 const item=()=>current()?.data.items.find(x=>x.channel===state.channel);
 const key=field=>[state.selected,state.channel,field].join('|');
 const dirty=()=>Object.keys(state.drafts).length>0;
 const editable=()=>!state.busy&&current()===latest()&&!['pending','returned','needs_strategy','passed','not_passed'].includes(state.record?.state);
 function toast(message){$('toast').textContent=message;$('toast').classList.add('show');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.remove('show'),5000);}
 function errors(error){const modal=$('issueModal');$('issueMessages').replaceChildren(node('p',error.message));(error.issues||[]).forEach(e=>$('issueMessages').append(node('p',e.message)));modal.classList.remove('hidden');$('confirmIssues').focus();}
 function view(name){all('.view').forEach(n=>n.classList.toggle('hidden',n.id!=='view-'+name));all('[data-nav]').forEach(n=>n.classList.toggle('current',n.dataset.nav===name));all('[data-flow]').forEach(n=>n.classList.toggle('active',n.dataset.flow===(name==='transfer'?'creative':name)));$('pageTitle').textContent={strategy:'策略结果 → 创意交付',transfer:'策略交付处理中',creative:'广告创意智能体工作台',evaluation:'创意结果 → 效果评估'}[name];}
 function persistDrafts(){try{sessionStorage.setItem('b-drafts-'+state.task,JSON.stringify(state.drafts));}catch{}}
 function syncUrl(){const p=new URLSearchParams({task_id:state.task});if(state.channel)p.set('channel',state.channel);p.set('type',state.tab);history.replaceState(null,'','/creative?'+p);}
 function renderContext(){
  const r=state.record,h=r.handoff,c=r.context,s=h.strategy;
  $('pageNote').textContent=c.product_name;
  $('flowBText').textContent=current()?'创意已保存':'策略已接收 · 等待创作';
  $('flowCText').textContent={pending:'已交付 · 评估处理中',returned:'反馈已返回 B',needs_strategy:'反馈需返回 A',passed:'评估通过',not_passed:'评估已终止'}[r.state]||'尚未评估';
  $('channelTabs').replaceChildren();c.channels.forEach(ch=>{const b=node('button',ch.name);b.classList.toggle('active',ch.name===state.channel);b.onclick=()=>{state.channel=ch.name;render();};$('channelTabs').append(b);});
  const ch=c.channels.find(x=>x.name===state.channel);
  $('briefGrid').replaceChildren();[['传播重点',c.positioning],['目标人群',c.target_audience.segment],['渠道任务',ch?.content_direction],['传播主题',c.marketing_strategy.theme],['原文依据',c.selling_points.map(x=>x.source_quote).join('；')],['发布前约束',c.explicit_constraints||'遵守原始事实与资源边界']].forEach(([k,v])=>{const n=node('div',undefined,'brief-item');n.append(node('span',k),node('b',String(v??'').split('\n\n【智策需求补充 v1】')[0]));$('briefGrid').append(n);});
 }
 function render(){
  if(!state.record)return;
  const r=state.record,v=current(),i=item();renderContext();
  $('creativeRoundChip').textContent=v?'创意已保存':'尚未生成';
  $('humanEditChip').classList.toggle('hidden',!v?.edit_trace.some(t=>t.source==='human'));
  $('humanEditChip').textContent='人工修改已保存';
  $('exportControls').replaceChildren();
  for(const [text,fn] of [['复制当前渠道',()=>copyChannel()],['导出文字',()=>download(false)],['导出 JSON',()=>download(true)]]){const b=node('button',text,'btn');b.disabled=!v;b.onclick=fn;$('exportControls').append(b);}
  for(const [tab,field] of Object.entries(fields)){
    const output=$(tab+'Output'),editor=$(tab+'Editor'),draft=state.drafts[key(field)];
    output.textContent=i?.[field]||'本渠道尚未生成；生成后可以编辑、润色和单项重生成。';output.classList.toggle('placeholder',!i);output.classList.toggle('hidden',draft!==undefined);
    editor.classList.toggle('hidden',draft===undefined);$(tab+'EditActions').classList.toggle('hidden',draft===undefined);if(draft!==undefined)editor.value=draft;
    all(`[data-field="${tab}"]`).forEach(b=>b.disabled=!i||!editable());
    $(tab+'History').replaceChildren(node('span','创作记录','edit-history-label'));
    const trace=v?r.versions.filter(x=>x.version<=v.version).flatMap(x=>x.edit_trace.filter(t=>t.path===`items[${x.data.items.findIndex(a=>a.channel===state.channel)}].${field}`).map(t=>({...t,version:x.version}))):[];
    trace.forEach(t=>$(tab+'History').append(node('span',(({ai_draft:'AI 初稿',human:'人工修改',ai_polish:'AI 润色',ai_regenerate:'单项重生成',c_feedback:'按反馈修订'})[t.source]||t.source),'history-tag '+(t.source==='human'?'human':t.source==='c_feedback'?'feedback':'ai'))));
    if(i&&!trace.length)$(tab+'History').append(node('span','沿用上一版本','history-tag'));
  }
  $('generateBtn').disabled=state.busy||!editable();$('regenerateBtn').disabled=state.busy||!i||!editable();
  $('generateBtn').textContent='生成渠道创意 →';
  all('.creative-meta').forEach(n=>n.textContent='');const deliveryPossible=v&&!state.busy;
  $('packageBtn').disabled=!deliveryPossible;
  $('generatorStatus').classList.toggle('done',Boolean(v));$('generatorStatus').classList.toggle('loading',state.busy);
  $('generatorStatus').querySelector('span').textContent=state.busy?'AI 正在处理，请稍候…':r.last_error?'上次操作失败，旧版本仍保留':v?'创意已保存':'等待生成';
  const feedback=r.feedback.at(-1);$('feedbackArea').classList.toggle('hidden',!['returned','needs_strategy'].includes(r.state));
  $('feedbackTitle').textContent='来自效果评估智能体的退回任务'+(feedback?.mode==='development/demo only'?'（开发模拟）':'');
  $('feedbackIntro').textContent=feedback?.mode==='development/demo only'?'这是开发联调的模拟反馈，当前为离线模拟，只修改指定创意字段。':'只修改指定创意字段，策略保持锁定。';
  if(feedback){$('feedbackEvalId').textContent=feedback.evaluation_id;$('feedbackCreative').textContent=feedback.creative_result_id;$('feedbackIssue').textContent=feedback.items.map(f=>f.issue).join('；');$('feedbackRequirement').textContent=feedback.items.map(f=>f.suggestion).join('；');$('feedbackPath').textContent=feedback.items.map(f=>f.target_path).join(' / ');$('feedbackTargets').replaceChildren(...feedback.items.map(f=>node('span',`${f.target_path} · ${f.priority}`)));$('feedbackFootText').textContent=r.state==='needs_strategy'?'反馈涉及策略，请返回 A，B 不会修改 strategy':'旧版本保留，定向修订后创建下一版';}
  $('startRevisionBtn').disabled=state.busy||r.state!=='returned';
  if(!state.busy&&!state.revisionVisible)$('revisionShell').classList.add('hidden');
  syncUrl();renderEvaluation();
 }
 function renderEvaluation(){const r=state.record,v=latest(),d=r.deliveries.at(-1),f=r.feedback.at(-1);const status=r.state;
  const demo=f?.mode==='development/demo only';
  $('evaluationChip').textContent=(demo?'开发模拟 · ':'')+({pending:'已交付 · 评估处理中',returned:'创意需要修改',needs_strategy:'策略需要调整',passed:'评估通过',not_passed:'评估已终止'}[status]||'尚未评估');
  $('evaluationIcon').textContent=status==='passed'?'✓':status==='not_passed'?'■':status==='returned'?'↩':'⋯';
  $('evaluationTitle').textContent=status==='pending'?'正在交付并评估创意':f?$('evaluationChip').textContent:'尚未交付效果评估智能体';
  $('evaluationBody').textContent=d?(demo?'当前为开发模拟反馈。':f?'结论已保存，可以进入效果评估查看。':'进入效果评估查看进度和结论。'):'先完成创意，再确认交付。';
  $('evaluationSubtitle').textContent='创意已交付效果评估';
  $('evalCreativeVersion').textContent=v?`第 ${v.version} 版创意`:'尚未生成';
  $('evalRoundState').textContent=f?'评估已完成':'等待结论';
  $('openEvaluation').classList.toggle('hidden',!d||demo);
  ['simulateReject','simulatePass'].forEach(id=>{$(id).classList.toggle('hidden',!r.demo_enabled);$(id).disabled=status!=='pending'||state.busy;});
 }
 function openEvaluation(receive=false){location.href='/evaluation/?task_id='+encodeURIComponent(state.task)+(receive?'&receive=1':'');}
 async function load(){state.record=await request(url(state.task,'state'));state.selected=state.record.versions.at(-1)?.result_id;state.channel=state.channel||state.record.context.channels[0].name;if(!state.instructionReady){$('creativeInstruction').value=latest()?.creative_instruction||'';state.instructionReady=true;}render();}
 async function animate(prefix,steps,work,waiting='AI 正在生成创意，请稍候…'){
  $(prefix+'Shell')?.classList.remove('hidden');const nodes=all(`#${prefix}Workflow li`);nodes.forEach(n=>n.classList.remove('active','done'));
  const progress=(stage,attempt=1)=>{
   const index=({queued:0,reading:0,generating:prefix==='revision'?3:2,parsing:3,validating:3,saving:4,completed:4})[stage]??0;
   nodes.forEach((node,j)=>{node.classList.toggle('active',j===index);node.classList.toggle('done',j<index);});
   const label=stage==='generating'?(attempt>1?'正在修正返回格式…':waiting):steps[index];
   $(prefix+'State').querySelector('span').textContent=label;$(prefix+'Foot').textContent=label;
   $(prefix+'Meter').style.width=(index*100/nodes.length)+'%';$(prefix+'Percent').textContent=(stage==='generating'?'生成中':Math.round(index*100/nodes.length)+'%');
  };
  progress('queued');
  try{const result=await work(progress);nodes.forEach(n=>{n.classList.remove('active');n.classList.add('done');});$(prefix+'State').querySelector('span').textContent='创意已保存';$(prefix+'Meter').style.width='100%';$(prefix+'Percent').textContent='100%';return result;}
  catch(error){$(prefix+'State').querySelector('span').textContent='本次未完成，未交付下游';$(prefix+'Meter').style.width='0%';$(prefix+'Percent').textContent='未完成';throw error;}
 }
 async function operate(action,extra={},prefix='generation'){
  if(state.busy)return;if(action!=='edit'&&dirty()){toast('有未保存编辑，请先保存或取消。');return;}
  state.busy=true;render();
  const before=latest();
  try{
   const stages=action==='edit'?['读取人工修改','定位当前创意','整理修改内容','确认文字格式','保存修改']:prefix==='revision'?['接收评估反馈','定位指定字段','锁定策略与其他字段','按反馈生成修订','保存本次修订']:['读取锁定策略上下文','分析当前渠道和创意要求','调用模型生成候选创意','整理模型返回内容','保存创意内容'];
   await animate(prefix,stages,async(onProgress)=>{
    await request(url(state.task,'operations'),{action,base_result_id:before?.result_id||null,channel:state.channel,instruction:$('creativeInstruction').value,...extra});
    while(true){const r=await request(url(state.task,'state'));onProgress(r.job.stage,r.job.attempt_count);if(r.job.status==='failed'){const e=new Error(r.job.error.message);Object.assign(e,r.job.error);throw e;}if(r.job.status==='succeeded')return r;await sleep(700);}
   },action==='edit'?'正在保存人工修改，请稍候…':undefined);
   if(action==='edit')delete state.drafts[key(extra.path.split('.').at(-1))];
   const oldId=state.selected;
   state.selected=null;await load();
   if(action==='edit'){
    for(const k of Object.keys(state.drafts)){if(k.startsWith(oldId+'|')){state.drafts[state.selected+k.slice(oldId.length)]=state.drafts[k];delete state.drafts[k];}}
    persistDrafts();
   }
   if(action==='revision'){state.revisionVisible=true;showDiff(before,latest());}
   toast('创意已保存');
  }catch(e){errors(e);await load();}finally{state.busy=false;render();}
 }
 function showDiff(before,after){$('revisionTitle').textContent='本次创意修改';$('revisionState').querySelector('span').textContent='修订已完成并保存';$('revisionFoot').textContent='历史修订记录；当前不在重新调用模型';$('revisionMeter').style.width='100%';$('revisionPercent').textContent='100%';all('#revisionWorkflow li').forEach(n=>{n.classList.remove('active');n.classList.add('done');});const changes=after.edit_trace,feedback=state.record.feedback.find(f=>f.creative_result_id===before.result_id);$('revisionDiff').classList.remove('hidden');$('diffBeforeLabel').textContent='修改前';$('diffAfterLabel').textContent='修改后';$('diffBeforeText').textContent=changes.map(x=>`${x.before}`).join('\n\n');$('diffAfterText').textContent=changes.map(x=>`${x.after}`).join('\n\n');$('revisionNote').classList.remove('hidden');$('revisionNoteText').textContent=after.feedback_applied.map(f=>f.issue+'；'+f.suggestion).join(' / ');$('revisionNoteChip').textContent='新版本已保存';}
 async function transfer(){view('transfer');$('transferTitle').textContent='正在读取已确认策略';$('transferFoot').textContent='正在准备创意工作区';await load();all('#transferWorkflow li').forEach(n=>{n.classList.remove('active');n.classList.add('done');});$('transferMeter').style.width='100%';view('creative');}
 async function copy(text){try{await navigator.clipboard.writeText(text);toast('已复制');}catch{toast('复制未获浏览器允许，请选择文字复制或导出。');}}
 function copyChannel(){const i=item();if(i)copy(Object.keys(fields).map(t=>labels[t]+'\n'+i[fields[t]]).join('\n\n'));}
 function download(json){const v=current();if(!v)return;const text=json?JSON.stringify(v,null,2):['【创意草案，发布前须人工复核】',state.record.context.product_name,`strategy ${v.strategy_result_id} / v${v.strategy_version}`,`creative ${v.result_id} / v${v.version} · 尚未评估`,...v.data.items.flatMap(i=>[i.channel,...Object.keys(fields).map(t=>labels[t]+'\n'+i[fields[t]]),'发布前待确认事项：',...i.pending_confirmations])].join('\n\n');const a=node('a');a.href=URL.createObjectURL(new Blob(['\ufeff',text],{type:json?'application/json':'text/plain;charset=utf-8'}));a.download=`creative-v${v.version}.${json?'json':'txt'}`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
 function setTab(tab){state.tab=tab;all('[data-tab]').forEach(n=>n.setAttribute('aria-selected',String(n.dataset.tab===tab)));all('[data-pane]').forEach(n=>n.classList.toggle('hidden',n.dataset.pane!==tab));if(state.record)syncUrl();}
 all('[data-tab]').forEach((b,index,buttons)=>{b.onclick=()=>setTab(b.dataset.tab);b.onkeydown=e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){const next=buttons[(index+(e.key==='ArrowRight'?1:3))%4];next.focus();setTab(next.dataset.tab);}};});
 all('[data-action]').forEach(b=>b.onclick=()=>{const tab=b.dataset.field,f=fields[tab],i=item();if(!i||!editable())return;
  if(b.dataset.action==='edit'){state.drafts[key(f)]=state.drafts[key(f)]??i[f];persistDrafts();render();$(tab+'Editor').focus();}
  else{const idx=current().data.items.indexOf(i);operate(b.dataset.action==='polish'?'refine':'regenerate',{path:`items[${idx}].${f}`});}
 });
 Object.entries(fields).forEach(([tab,field])=>{$(tab+'Editor').oninput=e=>{state.drafts[key(field)]=e.target.value;persistDrafts();};});
 all('[data-cancel-edit]').forEach(b=>b.onclick=()=>{delete state.drafts[key(fields[b.dataset.cancelEdit])];persistDrafts();render();});
 all('[data-save-edit]').forEach(b=>b.onclick=()=>{const field=fields[b.dataset.saveEdit],idx=current().data.items.indexOf(item());operate('edit',{path:`items[${idx}].${field}`,value:state.drafts[key(field)]});});
 all('[data-copy]').forEach(b=>b.onclick=()=>{if(item())copy($(b.dataset.copy).textContent);});
 all('.quick-prompt').forEach(b=>b.onclick=()=>{$('creativeInstruction').value+=($('creativeInstruction').value?'\n':'')+b.dataset.prompt;$('creativeInstruction').oninput();});
 $('creativeInstruction').oninput=()=>{};$('clearInstruction').onclick=()=>{$('creativeInstruction').value='';$('creativeInstruction').oninput();};
 $('generateBtn').onclick=$('regenerateBtn').onclick=()=>operate('generate');$('startRevisionBtn').onclick=()=>operate('revision',{},'revision');
 $('packageBtn').onclick=async()=>{
  if(dirty()){errors({message:'你有尚未保存的修改，请先保存或取消编辑。'});return;}
  if(state.busy)return;
  if(state.record?.state==='pending'){if(state.record.demo_enabled)view('evaluation');else openEvaluation();return;}
  if(['passed','not_passed','needs_strategy'].includes(state.record?.state)){openEvaluation();return;}
  if(state.record?.state==='returned'){toast('请先按评估反馈修订创意。');return;}
  try{const v=current(),p=await request(url(state.task,'package')+'?result_id='+encodeURIComponent(v.result_id));
   const host=$('creativeDeliveryChecks');host.replaceChildren();
   const clean=x=>String(x||'').split('\n\n【智策需求补充 v1】')[0];
   const summary=[['产品与目标',`${p.requirements.product_name}：${clean(p.requirements.marketing_goal).split('\n').filter(Boolean).join(' · ')}`],
    ['渠道与创意',p.creative.data.items.map(i=>`${i.channel} · ${i.slogan}`).join('\n')],
    ['本次评估内容','广告文案、核心短句、海报文字和短视频脚本'],
    ['需要遵守的要求',clean(p.requirements.special_requirements)||'使用已确认的产品事实与资源']];
   summary.forEach(([title,description])=>{
    const row=node('div',undefined,'handoff-summary-row');const content=node('div');content.append(node('strong',title),node('p',description));row.append(content,node('span','√','summary-check'));host.append(row);
   });
   $('cBridgeCreative').textContent='创意方案已完成';$('cHandoffDesc').textContent='确认本次方案，查看评分与修改建议。';
   const modal=$('cHandoffModal');modal.classList.remove('hidden');modal.tabIndex=-1;modal.focus();$('deliverCBtn').disabled=false;
   modal.onkeydown=e=>{if(e.key==='Tab'){const buttons=[...modal.querySelectorAll('button')].filter(b=>!b.disabled),first=buttons[0],last=buttons.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}};
  }catch(e){errors(e);}
 };
 ['closeCHandoff','cancelCHandoff'].forEach(id=>$(id).onclick=()=>{$('cHandoffModal').classList.add('hidden');$('packageBtn').focus();});
 $('deliverCBtn').onclick=async()=>{
  if(state.busy)return;if(dirty()){errors({message:'请先保存人工编辑'});return;}
  state.busy=true;$('deliverCBtn').disabled=true;$('deliverCBtn').textContent='正在交付…';
  try{
   const delivery=await request(url(state.task,'delivery'),{base_result_id:latest().result_id});
   if(delivery.evaluation_error)throw delivery.evaluation_error;
   if(delivery.evaluation_job){
    // Display-only receipt avoids an empty first view; C rereads server state.
    if(delivery.package)try{sessionStorage.setItem('zhice.evaluation.receipt.'+state.task,JSON.stringify({task_id:state.task,received_at:Date.now(),product_name:delivery.package.requirements.product_name,creative:delivery.package.creative}));}catch{}
    openEvaluation(true);return;
   }
   $('cHandoffModal').classList.add('hidden');await load();view('evaluation');
  }catch(e){state.busy=false;render();errors(e);}
  finally{state.busy=false;$('deliverCBtn').disabled=false;$('deliverCBtn').textContent='确认交付，查看评估 →';}
 };
 async function demo(decision){if(state.busy)return;state.busy=true;render();try{await request(url(state.task,'demo-feedback'),{base_result_id:latest().result_id,decision});await sleep(800);await load();view(decision==='return'&&state.record.state==='returned'?'creative':'evaluation');}catch(e){errors(e);}finally{state.busy=false;render();}}
 $('simulateReject').onclick=()=>demo('return');$('simulatePass').onclick=()=>demo('pass');$('backFromEvaluation').onclick=()=>view('creative');
 $('openEvaluation').onclick=()=>openEvaluation();
 all('[data-nav]').forEach(b=>b.onclick=()=>{if(b.dataset.nav==='strategy'){location.href='/workspace';return;}if(b.dataset.nav==='evaluation'){if(!state.record?.deliveries.length){toast('请先确认交付本次创意。');return;}if(state.record.feedback.at(-1)?.mode==='real_c'||state.record.state==='pending'&&!state.record.demo_enabled){openEvaluation();return;}}view(b.dataset.nav);});
 async function entryView(){view('strategy');const h=$('strategySummary');h.replaceChildren(node('h2','从策略开始创作'),node('p','先在策略页面完成需求，再交付创意智能体。'));const b=node('button','前往策略页面','btn primary');b.onclick=()=>location.href='/workspace';h.append(b);}
 window.addEventListener('beforeunload',e=>{if(dirty()){e.preventDefault();e.returnValue='';}});
 $('confirmIssues').onclick=()=>{$('issueModal').classList.add('hidden');$('cHandoffModal').classList.add('hidden');view('creative');};document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('cHandoffModal').classList.add('hidden');$('issueModal').classList.add('hidden');}});
 async function init(){await request('/api/session');if(!state.task){await entryView();return;}try{state.drafts=JSON.parse(sessionStorage.getItem('b-drafts-'+state.task)||'{}');}catch{}state.selected=null;setTab(params.get('type') in fields?params.get('type'):'copy');try{await load();if(params.get('receive')==='1')await transfer();else{view('creative');if(state.record.state==='pending'&&!state.record.demo_enabled){openEvaluation();return;}if(state.record.job?.status==='running'){state.busy=true;while(state.record.job.status==='running'){await sleep(700);await load();}state.busy=false;render();}}}catch(e){if(e.code==='HANDOFF_REQUIRED'){view('strategy');$('strategySummary').replaceChildren(node('h2','接收真实策略'),node('p','先校验当前任务和来源，再确认进入 B。'));const b=node('button','校验并接收策略','btn primary');b.onclick=()=>window.CreativeHandoff.open(state.task,transfer);$('strategySummary').append(b);await window.CreativeHandoff.open(state.task,transfer);}else{await entryView();errors(e);}}}
 init().catch(errors);
})();
