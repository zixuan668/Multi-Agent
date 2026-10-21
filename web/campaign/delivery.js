import {escapeHtml as escape} from './presentation.js';

const pendingRequests=new Map();
const sending=new Set();

export function preferredPane(task){
  if(task.status==='awaiting_revision'||task.status==='needs_review')return 'review';
  if(['awaiting_confirmation','approved','needs_revision'].includes(task.status)&&task.rounds.some(row=>row.creative))return 'creative';
  return 'collaboration';
}

export function imageErrorMessage(message){
  if(message?.includes('SetLimitExceeded'))return '火山引擎的模型用量上限已触发。请在控制台调整可接受的额度后，再手动生成。';
  if(message?.includes('鉴权'))return '生图鉴权或模型权限被拒绝，请核对本机生图配置。';
  return message||'图片未生成成功；没有自动重试。';
}

export function imageMarkup(task,row,index,configured=false){
  const jobs=(task.image_jobs||[]).filter(job=>job.round_no===row.round_no&&job.item_index===index&&job.creative_result_id===row.creative.result_id);
  const latest=jobs.at(-1);
  const active=latest&&['pending','running'].includes(latest.status);
  const completed=[...jobs].reverse().find(job=>job.status==='succeeded');
  const display=latest?.status==='succeeded'?latest:completed;
  return `<aside class="poster-preview ai-image-panel"><h3>AI 宣传图</h3>${display?`<a href="${escape(display.uri)}" target="_blank" rel="noopener"><img src="${escape(display.uri)}" width="${display.width}" height="${display.height}" alt="${escape(task.requirements.product_name)}的AI宣传图"></a><a class="button" href="${escape(display.uri)}?download=1" download>下载原图</a>`:''}${active?'<div class="image-placeholder" role="status"><strong>李莉正在制作宣传图</strong><p>火山引擎正在生成，结果返回后会自动显示。刷新不会重新计费调用。</p></div>':latest&&latest.status!=='succeeded'?`<div class="image-error"><strong>本次未完成</strong><p>${escape(imageErrorMessage(latest.error))}</p><details><summary>错误详情</summary><p>${escape(latest.error)}</p></details></div>`:!display?'<div class="image-placeholder"><strong>把创意变成真正的画面</strong><p>先确认短文案与单一构图，再交给 Seedream 生成宣传图。</p></div>':''}${configured&&!active?`<button class="button primary" type="button" data-image-generate="${index}" data-image-round="${row.round_no}">${latest?'调整方案并重做':'制作宣传图'}</button>`:!configured?'<p>当前未启用生图服务，请检查本机生图配置。</p>':''}<p>AI 图片需核对文字与产品外观，尚未通过图像审核，不会自动发布。</p>${jobs.length?`<details><summary>生成记录 · ${jobs.length} 次</summary><ul class="image-history">${jobs.map(job=>`<li>${job.status==='succeeded'?`<a href="${escape(job.uri)}" target="_blank" rel="noopener">查看已生成图片</a>`:escape({pending:'等待开始',running:'生成中',failed:'生成失败',interrupted:'中断，未自动重试'}[job.status]||job.status)}</li>`).join('')}</ul></details>`:''}</aside>`;
}

export function setupImageGeneration({document,getTask,request,post,onTask,onError}){
  const dialog=document.getElementById('image-plan-dialog');
  const form=document.getElementById('image-plan-form');
  const submit=document.getElementById('image-plan-generate');
  const close=document.getElementById('image-plan-close');
  const errorBox=document.getElementById('image-plan-error');
  let context=null,loading=false;
  close.onclick=()=>{if(!sending.size)dialog.close();};
  dialog.addEventListener('cancel',event=>{if(sending.size)event.preventDefault();});
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-image-generate]');
    if(!button||button.disabled||loading)return;
    const task=getTask();
    if(!task)return;
    const index=Number(button.dataset.imageGenerate),roundNo=Number(button.dataset.imageRound);
    loading=true;button.disabled=true;
    try{
      const fresh=await request('/api/campaigns/'+encodeURIComponent(task.task_id));
      if(getTask()?.task_id!==task.task_id)return;
      onTask(fresh);
      if(fresh.image_jobs?.some(job=>job.round_no===roundNo&&job.item_index===index&&['pending','running'].includes(job.status)))return;
      const preview=await request('/api/campaigns/'+encodeURIComponent(task.task_id)+'/image-plan?round='+roundNo+'&item='+index);
      if(getTask()?.task_id!==task.task_id)return;
      context={taskId:task.task_id,index,roundNo,beforeCount:fresh.image_jobs?.length||0};
      for(const [key,value] of Object.entries(preview.plan))form.elements.namedItem(key).value=value??'';
      document.getElementById('image-plan-meta').textContent=`${preview.brand} · ${preview.aspect_ratio} · 打开方案不计费 · ${preview.visible_watermark?'保留供应商角标':'不添加供应商可选角标'}`;
      document.getElementById('image-plan-warnings').textContent=preview.warnings.join(' ');
      document.getElementById('image-plan-prompt').textContent=preview.prompt;
      errorBox.hidden=true;submit.disabled=false;dialog.showModal();
    }catch(error){onError(error);}finally{loading=false;button.disabled=false;}
  });
  form.onsubmit=async event=>{
    event.preventDefault();
    if(!context||!form.reportValidity()||getTask()?.task_id!==context.taskId)return;
    const {taskId,index,roundNo,beforeCount}=context;
    const plan=Object.fromEntries(new FormData(form));
    for(const key of ['supporting_text','action_text'])plan[key]=plan[key].trim()||null;
    const storageKey='zhice.image.request.v2.'+taskId+':'+roundNo+':'+index;
    if(sending.has(storageKey))return;
    let saved=pendingRequests.get(storageKey);
    if(!saved){try{saved=JSON.parse(localStorage.getItem(storageKey));}catch{}}
    if(!saved||beforeCount>saved.beforeCount)saved={key:crypto.randomUUID(),beforeCount};
    pendingRequests.set(storageKey,saved);
    try{localStorage.setItem(storageKey,JSON.stringify(saved));}catch{}
    sending.add(storageKey);submit.disabled=true;close.disabled=true;errorBox.hidden=true;submit.textContent='正在提交…';
    try{
      const updated=await post('/api/campaigns/'+encodeURIComponent(taskId)+'/images',{round_no:roundNo,item_index:index,submission_key:saved.key,poster_plan:plan});
      pendingRequests.delete(storageKey);
      try{localStorage.removeItem(storageKey);}catch{}
      dialog.close();
      if(getTask()?.task_id===taskId)onTask(updated);
    }catch(error){errorBox.textContent=error.message;errorBox.hidden=false;}finally{
      sending.delete(storageKey);
      submit.disabled=false;close.disabled=false;submit.textContent='确认并生成1张（计费）';
    }
  };
}
