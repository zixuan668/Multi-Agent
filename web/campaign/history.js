import {escapeHtml as escape,statuses} from './presentation.js';

export function historyMarkup(tasks,currentId){
  return tasks.length?tasks.map(task=>`<article class="history-row ${currentId===task.task_id?'active':''}"><button class="history-item" data-task="${escape(task.task_id)}" ${currentId===task.task_id?'aria-current="page"':''}><strong>${escape(task.product_name)}</strong><span><i class="status-dot ${['pending','running'].includes(task.status)?'busy':['failed','needs_review','needs_revision','interrupted'].includes(task.status)?'warning':''}"></i>${escape(statuses[task.status]||task.status)}</span></button><button class="history-delete" data-history-delete="${escape(task.task_id)}" aria-label="删除任务：${escape(task.product_name)}" title="${task.deletable?'移入回收站':'生成中，请结束后再删除'}" ${task.deletable?'':'disabled'}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg></button></article>`).join(''):'<div class="history-empty">还没有任务。新建后会保存在这里。</div>';
}

export function trashMarkup(tasks){
  return tasks.length?tasks.map(task=>`<article class="trash-row"><div><strong>${escape(task.product_name)}</strong><p>${escape(statuses[task.status]||task.status)}</p></div><button class="button" data-history-restore="${escape(task.task_id)}">恢复任务</button></article>`).join(''):'<p class="history-empty">回收站为空。</p>';
}

export function setupHistory({document,request,post,getTasks,onRemoved,onRefresh,onError,notify}){
  const dialog=document.getElementById('history-dialog');
  const title=document.getElementById('history-dialog-title');
  const body=document.getElementById('history-dialog-body');
  const confirm=document.getElementById('history-confirm');
  const cancel=document.getElementById('history-cancel');
  let pending=null,busy=false;
  async function showTrash(){
    pending=null;title.textContent='回收站';confirm.hidden=true;cancel.textContent='关闭';
    body.innerHTML='<p>正在读取…</p>';
    if(!dialog.open)dialog.showModal();
    try{const response=await request('/api/campaigns?deleted=1');body.innerHTML='<p>恢复会保留所有版本与图片，不会重新调用模型。</p>'+trashMarkup(response.tasks);}catch(error){body.textContent=error.message;}
  }
  function ask(taskId){
    const task=taskId?getTasks().find(item=>item.task_id===taskId):null;
    if(taskId&&!task)return;
    if(task&&!task.deletable)return;
    pending=taskId?{path:'/api/campaigns/'+encodeURIComponent(taskId)+'/archive'}:{path:'/api/campaigns/history/clear'};
    title.textContent=task?'删除这条任务？':'清空任务历史？';
    body.textContent=task?`“${task.product_name}”将移入回收站，可以恢复。不会重新调用模型或影响其他任务。`:'将已结束的任务移入回收站，可以恢复。正在生成文字或图片的任务会保留。';
    confirm.hidden=false;confirm.disabled=false;confirm.textContent=task?'移入回收站':'清空已结束任务';cancel.textContent='取消';dialog.showModal();cancel.focus();
  }
  cancel.onclick=()=>{if(!busy)dialog.close();};
  dialog.addEventListener('cancel',event=>{if(busy)event.preventDefault();});
  confirm.onclick=async()=>{
    if(busy||!pending)return;
    busy=true;confirm.disabled=true;cancel.disabled=true;
    try{const result=await post(pending.path,{});onRemoved(result.task_ids);await onRefresh();dialog.close();notify(`已将 ${result.task_ids.length} 条任务移入回收站${result.skipped_ids?.length?'，生成中的任务已保留':''}，可恢复。`);}catch(error){dialog.close();onError(error);}finally{busy=false;confirm.disabled=false;cancel.disabled=false;pending=null;}
  };
  document.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||button.disabled||busy)return;
    if(button.dataset.historyDelete){ask(button.dataset.historyDelete);return;}
    if(button.id==='clear-history'){ask(null);return;}
    if(button.id==='open-trash'){await showTrash();return;}
    if(button.dataset.historyRestore){
      busy=true;button.disabled=true;cancel.disabled=true;
      try{await post('/api/campaigns/'+encodeURIComponent(button.dataset.historyRestore)+'/restore',{});await onRefresh();await showTrash();notify('任务已恢复，未重新生成。');}catch(error){onError(error);}finally{busy=false;button.disabled=false;cancel.disabled=false;}
    }
  });
}
