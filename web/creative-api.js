/* Shared B transport and handoff dialog. No credentials or provider settings in browser. */
(() => {
  async function request(url, body) {
    const response = await fetch(url, {cache:'no-store', ...(body === undefined ? {} : {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)})});
    const data = await response.json();
    if (!response.ok) { const e = new Error(data.error?.message || '服务暂不可用'); e.code=data.error?.code; e.issues=data.error?.issues || []; throw e; }
    return data;
  }
  function node(tag,text,cls) { const n=document.createElement(tag); if(text!==undefined)n.textContent=text; if(cls)n.className=cls; return n; }
  const url=(task,op)=>`/api/tasks/${encodeURIComponent(task)}/creative/${op}`;
  function showChecks(root,gate,error) {
    const host=root.querySelector('.checks');host.replaceChildren();
    const clean=x=>String(x||'').split('\n\n【智策需求补充 v1】')[0];
    let checks;
    if(error)checks=[['交付未完成',error.message],...(error.issues||[]).map(x=>['需要调整',x.message])];
    else {
      const r=gate.handoff.requirements,s=gate.handoff.strategy.data,p=r.campaign_period;
      const period=p?(p.duration_days?`${p.duration_days} 天`:`${p.start_date} 至 ${p.end_date}`):'周期尚未确定';
      const budget=r.budget?`${r.budget.amount.toLocaleString('zh-CN')} ${r.budget.currency==='CNY'?'元':r.budget.currency}`:'预算尚未确定';
      checks=[['产品事实与目标',`${r.product_name}：${clean(r.product_description).split('\n')[0]}\n${clean(r.marketing_goal).split('\n').filter(Boolean).join(' · ')}`],
              ['受众与定位',`${s.target_audience.segment} · ${clean(s.positioning).split(/[。！？]/)[0]}。`],
              ['预算与周期',`${budget} · ${period}`],
              ['特殊限制',clean(r.special_requirements)||'遵循已确认的产品事实与渠道要求']];
    }
    checks.forEach(([title,description])=>{const n=node('div',undefined,'handoff-summary-row');const content=node('div');content.append(node('strong',title),node('p',description));n.append(content,node('span',error?'!':'√',error?'summary-check failed':'summary-check'));host.append(n);});
    root.querySelector('.modal-actions > .chip').textContent=error?'交付未完成':'4 / 4 项检查通过';
    root.querySelector('#acceptHandoff').disabled=Boolean(error);
  }
  let dialog=null,activeTask=null,opener=null;
  async function open(task,onAccepted) {
    if(!dialog){const host=node('div');document.body.append(host);dialog=host.attachShadow({mode:'open'});
      const link=node('link');link.rel='stylesheet';link.href='/creative.css?v=6';dialog.append(link);
      const html=await (await fetch('/creative-handoff.html',{cache:'no-store'})).text();
      const template=document.createElement('template');template.innerHTML=html;dialog.append(template.content.cloneNode(true));
    }
    activeTask=task;opener=document.activeElement;
    const modal=dialog.querySelector('#handoffModal');modal.classList.remove('hidden');
    const close=()=>{modal.classList.add('hidden');opener?.focus();};
    ['closeHandoff','cancelHandoff'].forEach(id=>dialog.querySelector('#'+id).onclick=close);
    const button=dialog.querySelector('#acceptHandoff');button.disabled=true;button.textContent='正在校验真实任务…';
    dialog.querySelector('.checks').replaceChildren(node('p','正在读取当前任务和策略契约…'));
    modal.tabIndex=-1;modal.focus();
    modal.onkeydown=e=>{if(e.key==='Escape')close(); if(e.key==='Tab'){const els=[...modal.querySelectorAll('button:not(:disabled)')];const first=els[0],last=els.at(-1);if(e.shiftKey&&dialog.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&dialog.activeElement===last){e.preventDefault();first.focus();}}};
    try { const gate=await request(url(task,'handoff'));if(activeTask!==task)return;showChecks(dialog,gate);
      dialog.querySelector('.agent-node.from strong').textContent='策略方案已完成';
      dialog.querySelector('.agent-node.to strong').textContent='准备接收策略';
      button.textContent='确认交付，开始创作 →';
      button.onclick=async()=>{button.disabled=true;try{await request(url(task,'accept'),{});close();if(onAccepted)await onAccepted();else location.href='/creative?task_id='+encodeURIComponent(task)+'&receive=1';}catch(e){showChecks(dialog,null,e);button.textContent='交付未完成';}};
    } catch(e){showChecks(dialog,null,e);button.textContent='无法交付，请先解决问题';}
  }
  window.CreativeAPI={request,url,node};window.CreativeHandoff={open};
})();
