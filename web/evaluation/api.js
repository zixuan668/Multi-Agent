/** Only this adapter knows HTTP paths; the UI never reads A/B private state. */
export function createClient(base='/api/evaluation') {
  const url=new URL(base,location.origin);
  if(url.origin!==location.origin)throw new Error('接口适配器只接受同源地址；跨服务请通过团队后端代理。');
  const endpoint=url.pathname.replace(/\/$/,'');
  async function request(path,options={}){
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),20000);
    try{const response=await fetch(endpoint+path,{...options,signal:controller.signal,credentials:'same-origin'});const value=await response.json();if(!response.ok||value.error){const err=value.error||{};throw new Error(`${err.code||'HTTP_ERROR'} · ${err.message||'本地服务请求失败'}${err.field?'\n字段：'+err.field:''}`);}return value;}catch(error){if(error.name==='AbortError')throw new Error('本地重放服务响应超时，请检查服务后重新运行。');throw error;}finally{clearTimeout(timer);}
  }
  return {metadata:()=>request('/scenarios'),sample:(product,scenario)=>request(`/sample?product=${encodeURIComponent(product)}&scenario=${encodeURIComponent(scenario)}`),replay:bundle=>request('/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(bundle)})};
}
export function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function resolveContent(request,path){const root={strategy:request.strategy.data,creative:request.creative.data,requirements:request.requirements};const keys=path.replaceAll('.data.','.').replace(/\[(\d+)\]/g,'.$1').split('.');return keys.reduce((item,key)=>item?.[key],root);}
export function selectReportRecord(bundle){return bundle.records[bundle.selected_index??bundle.records.length-1];}
export function buildExport(bundle){const record=selectReportRecord(bundle);return {schema_version:'1.0',mode:bundle.mode,source:bundle.source,task_id:record.request.task_id,config_snapshot:bundle.config_snapshot,assessment_status:bundle.final.assessment_status,task_status:bundle.final.task_status,termination_reason:bundle.final.termination_reason,selected_evaluation_id:bundle.final.selected_evaluation_id,selected_results:bundle.selected_index==null?null:{strategy:record.request.strategy,creative:record.request.creative,evaluation:record.outcome.evaluation},remaining_issues:bundle.final.remaining_issues,history:bundle.records};}
