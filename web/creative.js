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
  $('flowCText').textContent={pending:'已交付候选包 · 尚未评估',returned:'反馈已返回 B',needs_strategy:'反馈需返回 A',passed:'开发模拟通过',not_passed:'三轮上限 · 已终止'}[r.state]||'尚未评估';
  $('channelTabs').replaceChildren();c.channels.forEach(ch=>{const b=node('button',ch.name);b.classList.toggle('active',ch.name===state.channel);b.onclick=()=>{state.channel=ch.name;render();};$('channelTabs').append(b);});
  const ch=c.channels.find(x=>x.name===state.channel);
  $('briefGrid').replaceChildren();[['传播重点',c.positioning],['目标人群',c.target_audience.segment],['渠道任务',ch?.content_direction],['传播主题',c.marketing_strategy.theme],['原文依据',c.selling_points.map(x=>x.source_quote).join('；')],['发布前约束',c.explicit_constraints||'遵守原始事实与资源边界']].forEach(([k,v])=>{const n=node('div',undefined,'brief-item');n.append(node('span',k),node('b',v));$('briefGrid').append(n);});
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
  $('feedbackIntro').textContent=feedback?.mode==='development/demo only'?'这是开发联调的模拟反馈，真实 C 尚未接入。B 只修改指定创意字段。':'只修改指定创意字段，策略保持锁定。';
  if(feedback){$('feedbackEvalId').textContent=feedback.evaluation_id;$('feedbackCreative').textContent=feedback.creative_result_id;$('feedbackIssue').textContent=feedback.items.map(f=>f.issue).join('；');$('feedbackRequirement').textContent=feedback.items.map(f=>f.suggestion).join('；');$('feedbackPath').textContent=feedback.items.map(f=>f.target_path).join(' / ');$('feedbackTargets').replaceChildren(...feedback.items.map(f=>node('span',`${f.target_path} · ${f.priority}`)));$('feedbackFootText').textContent=r.state==='needs_strategy'?'反馈涉及策略，请返回 A，B 不会修改 strategy':'旧版本保留，定向修订后创建下一版';}
  $('startRevisionBtn').disabled=state.busy||r.state!=='returned';
  if(!state.busy&&!state.revisionVisible)$('revisionShell').classList.add('hidden');
  syncUrl();renderEvaluation();
 }
 function renderEvaluation(){const r=state.record,v=latest(),d=r.deliveries.at(-1),f=r.feedback.at(-1);const status=r.state;
  $('evaluationChip').textContent={pending:'已交付候选包 · 尚未评估',returned:'开发模拟：退回 B',needs_strategy:'需要返回策略智能体',passed:'开发模拟：通过',not_passed:'第3轮未通过 · 已终止'}[status]||'尚未评估';
  $('evaluationIcon').textContent=status==='passed'?'✓':status==='not_passed'?'■':status==='returned'?'↩':'⋯';
  $('evaluationTitle').textContent=status==='pending'?`creative v${v.version} 已锁定，等待 C` : status==='not_passed'?'已达到3轮上限，不再创建第4轮':f?$('evaluationChip').textContent:'尚未交付效果评估智能体';
  $('evaluationBody').textContent=d?(f?'当前为开发模式模拟反馈，真实检查智能体尚未接入。':'创意已交付，等待检查智能体接收。'):'先完成创意，再交付检查智能体。';
  $('evaluationSubtitle').textContent='真实 C 尚未接入；开发模拟仅用于验证反馈、版本与三轮上限。';
  ['simulateReject','simulatePass'].forEach(id=>{$(id).classList.toggle('hidden',!r.demo_enabled);$(id).disabled=status!=='pending'||state.busy;});
 }
 async function load(){state.record=await request(url(state.task,'state'));state.selected=state.record.versions.at(-1)?.result_id;state.channel=state.channel||state.record.context.channels[0].name;if(!state.instructionReady){$('creativeInstruction').value=latest()?.creative_instruction||'';state.instructionReady=true;}render();}
 async function animate(prefix,steps,work,waiting='AI 正在生成创意，请稍候…'){
  $(prefix+'Shell')?.classList.remove('hidden');const nodes=all(`#${prefix}Workflow li`);nodes.forEach(n=>n.classList.remove('active','done'));
  let settled=false,result,error;
  const promise=work().then(x=>{settled=true;result=x;},e=>{settled=true;error=e;});
  for(let n=0;n<nodes.length;n++){
   // Keep the actual model wait at CREATE/REVISE. Later phases never finish ahead of the server.
   if(n===nodes.length-2){while(!settled){$(prefix+'State').querySelector('span').textContent=waiting;await sleep(400);}}
   if(error)break;
   nodes.forEach((x,j)=>{x.classList.toggle('active',j===n);x.classList.toggle('done',j<n);});
   $(prefix+'State').querySelector('span').textContent=steps[n];$(prefix+'Foot').textContent=steps[n];$(prefix+'Meter').style.width=((n+1)*100/nodes.length)+'%';$(prefix+'Percent').textContent=Math.round((n+1)*100/nodes.length)+'%';await sleep(650);
  }
  await promise;
  if(error){$(prefix+'State').querySelector('span').textContent='本次未完成，未交付下游';$(prefix+'Meter').style.width='0%';$(prefix+'Percent').textContent='未完成';throw error;}
  nodes.forEach(n=>{n.classList.remove('active');n.classList.add('done');});$(prefix+'State').querySelector('span').textContent='创意已保存';return result;
 }
 async function operate(action,extra={},prefix='generation'){
  if(state.busy)return;if(action!=='edit'&&dirty()){toast('有未保存编辑，请先保存或取消。');return;}
  state.busy=true;render();
  const before=latest();
  try{
   const stages=action==='edit'?['读取人工修改','定位当前创意','整理修改内容','确认文字格式','保存修改']:prefix==='revision'?['接收评估反馈','定位指定字段','锁定策略与其他字段','按反馈生成修订','保存本次修订']:['读取锁定策略上下文','分析当前渠道和创意要求','调用模型生成候选创意','整理模型返回内容','保存创意内容'];
   await animate(prefix,stages,async()=>{
    await request(url(state.task,'operations'),{action,base_result_id:before?.result_id||null,channel:state.channel,instruction:$('creativeInstruction').value,...extra});
    while(true){const r=await request(url(state.task,'state'));if(r.job.status==='failed'){const e=new Error(r.job.error.message);Object.assign(e,r.job.error);throw e;}if(r.job.status==='succeeded')return r;await sleep(700);}
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
 async function transfer(){view('transfer');const names=['正在接收上游任务','正在确认并锁定策略来源','正在读取事实、约束并提炼创意简报','创意工作区准备完成'];const nodes=all('#transferWorkflow li');for(let i=0;i<nodes.length;i++){nodes.forEach((n,j)=>{n.classList.toggle('active',i===j);n.classList.toggle('done',j<i);});$('transferTitle').textContent=names[i];$('transferFoot').textContent=names[i];$('transferMeter').style.width=((i+1)*25)+'%';await sleep(850);}await load();view('creative');}
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
  try{const v=current(),p=await request(url(state.task,'package')+'?result_id='+encodeURIComponent(v.result_id));
   const host=$('creativeDeliveryChecks');host.replaceChildren();
   [['广告文案','copy'],['核心短句','slogan'],['海报文字','poster_concept'],['短视频脚本','video_script']].forEach(([title,field])=>{
    const count=p.creative.data.items.filter(i=>typeof i[field]==='string'&&i[field].trim()).length;
    const row=node('div',undefined,'handoff-summary-row');const content=node('div');content.append(node('strong',title),node('p',`${count} 个渠道已准备`));row.append(content,node('span','√','summary-check'));host.append(row);
   });
   $('cBridgeCreative').textContent='本次创意已准备';$('cHandoffDesc').textContent=p.requirements.product_name;
   $('cHandoffModal').classList.remove('hidden');$('deliverCBtn').disabled=false;
  }catch(e){errors(e);}
 };
 ['closeCHandoff','cancelCHandoff'].forEach(id=>$(id).onclick=()=>$('cHandoffModal').classList.add('hidden'));
 $('deliverCBtn').onclick=async()=>{if(dirty()){errors({message:'请先保存人工编辑'});return;}$('deliverCBtn').disabled=true;try{await request(url(state.task,'delivery'),{base_result_id:latest().result_id});await sleep(700);$('cHandoffModal').classList.add('hidden');await load();view('evaluation');}catch(e){errors(e);}finally{$('deliverCBtn').disabled=false;}};
 async function demo(decision){if(state.busy)return;state.busy=true;render();try{await request(url(state.task,'demo-feedback'),{base_result_id:latest().result_id,decision});await sleep(800);await load();view(decision==='return'&&state.record.state==='returned'?'creative':'evaluation');}catch(e){errors(e);}finally{state.busy=false;render();}}
 $('simulateReject').onclick=()=>demo('return');$('simulatePass').onclick=()=>demo('pass');$('backFromEvaluation').onclick=()=>view('creative');
 all('[data-nav]').forEach(b=>b.onclick=()=>{if(b.dataset.nav==='strategy'){location.href='/workspace';return;}if(b.dataset.nav==='evaluation'&&!state.record?.deliveries.length){toast('请先检查并交付当前创意版本。');return;}view(b.dataset.nav);});
 async function entryView(){view('strategy');const h=$('strategySummary');h.replaceChildren(node('h2','从策略开始创作'),node('p','先在策略页面完成需求，再交付创意智能体。'));const b=node('button','前往策略页面','btn primary');b.onclick=()=>location.href='/workspace';h.append(b);}
 window.addEventListener('beforeunload',e=>{if(dirty()){e.preventDefault();e.returnValue='';}});
 $('confirmIssues').onclick=()=>{$('issueModal').classList.add('hidden');$('cHandoffModal').classList.add('hidden');view('creative');};document.addEventListener('keydown',e=>{if(e.key==='Escape'){$('cHandoffModal').classList.add('hidden');$('issueModal').classList.add('hidden');}});
 async function init(){await request('/api/session');if(!state.task){await entryView();return;}try{state.drafts=JSON.parse(sessionStorage.getItem('b-drafts-'+state.task)||'{}');}catch{}state.selected=null;setTab(params.get('type') in fields?params.get('type'):'copy');try{await load();if(params.get('receive')==='1')await transfer();else{view('creative');if(state.record.job?.status==='running'){state.busy=true;while(state.record.job.status==='running'){await sleep(700);await load();}state.busy=false;render();}}}catch(e){if(e.code==='HANDOFF_REQUIRED'){view('strategy');$('strategySummary').replaceChildren(node('h2','接收真实策略'),node('p','先校验当前任务和来源，再确认进入 B。'));const b=node('button','校验并接收策略','btn primary');b.onclick=()=>window.CreativeHandoff.open(state.task,transfer);$('strategySummary').append(b);await window.CreativeHandoff.open(state.task,transfer);}else{await entryView();errors(e);}}}
 init().catch(errors);
})();
