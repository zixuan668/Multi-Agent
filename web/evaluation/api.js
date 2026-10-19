/** Only this adapter knows HTTP paths; the UI never reads A/B private state. */
export function createClient(base='/api/evaluation') {
  const url=new URL(base,location.origin);
  if(url.origin!==location.origin)throw new Error('接口必须使用同源地址。');
  const endpoint=url.pathname.replace(/\/$/,'');
  async function requestURL(path,options={}){
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
    try{
      const response=await fetch(path,{...options,signal:controller.signal,credentials:'same-origin'});
      const value=await response.json();
      if(!response.ok||value.error){const details=value.error||{},failure=new Error(details.message||'请求未完成，请重试。');failure.code=details.code||'HTTP_ERROR';throw failure;}
      return value;
    }catch(failure){if(failure.name==='AbortError')throw new Error('读取状态超时，请刷新后继续查看。');throw failure;}
    finally{clearTimeout(timer);}
  }
  const post=body=>({method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  return {metadata:()=>requestURL(endpoint+'/scenarios'),sample:(product,scenario)=>requestURL(endpoint+`/sample?product=${encodeURIComponent(product)}&scenario=${encodeURIComponent(scenario)}`),
    replay:bundle=>requestURL(endpoint+'/replay',post(bundle)),session:()=>requestURL('/api/session'),
    creativeHistory:()=>requestURL('/api/creative/history'),
    task:(task,operation,body)=>requestURL(`/api/tasks/${encodeURIComponent(task)}/${operation}`,body===undefined?{}:post(body))};
}
export function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
export function resolveContent(request,path){const root={strategy:request.strategy.data,creative:request.creative.data,requirements:request.requirements};const keys=path.replaceAll('.data.','.').replace(/\[(\d+)\]/g,'.$1').split('.');return keys.reduce((item,key)=>item?.[key],root);}
export function unpackText(value){const text=String(value??''),marker='\n\n【智策需求补充 v1】\n',at=text.lastIndexOf(marker);if(at<0)return {base:text,detail:{}};try{const detail=JSON.parse(text.slice(at+marker.length));if(detail?.formVersion===1&&!Array.isArray(detail))return {base:text.slice(0,at),detail};}catch{}return {base:text,detail:{}};}
export function selectReportRecord(bundle){return bundle.records[bundle.selected_index??bundle.records.length-1];}
export function readReport(value){
  if(value?.schema_version==='c-to-a-delivery-candidate-v1')value=value.report;
  if(!value||typeof value!=='object')throw new Error('请导入完整评估报告。');
  const records=value.records||value.history;
  if(!Array.isArray(records)||!records.length||records.length>3)throw new Error('报告须包含1至3轮关联结果。');
  for(const row of records){
    const r=row.request,d=row.outcome?.evaluation?.data;
    if(!r||!d||row.outcome.evaluation.task_id!==r.task_id||d.strategy_result_id!==r.strategy?.result_id||d.creative_result_id!==r.creative?.result_id)throw new Error('报告的任务或结果引用不一致。');
    if(!r.requirements||!r.strategy.data||!Array.isArray(r.creative.data?.items)||!Array.isArray(d.risks)||!Array.isArray(d.feedback))throw new Error('报告缺少需求、方案、风险或反馈记录。');
    const strategy=r.strategy.data,creative=r.creative.data;
    if(!strategy.target_audience||!['selling_points','channels','assumptions','missing_information','constraint_conflicts'].every(k=>Array.isArray(strategy[k])))throw new Error('策略记录不完整，无法展示关联依据。');
    if(!creative.items.length||creative.items.some(item=>r.creative.schema_version!=='b-internal-candidate-v1'&&(!item.poster_concept||!Array.isArray(item.video_script?.scenes))))throw new Error('创意记录不完整，无法展示关联依据。');
    if(r.creative.schema_version==='b-internal-candidate-v1'?creative.items.some(item=>!Array.isArray(item.evidence)||!Array.isArray(item.pending_confirmations)):!Array.isArray(creative.assumptions)||!Array.isArray(creative.constraint_conflicts))throw new Error('创意记录缺少依据或待确认事项。');
    if(Object.keys(d.dimension_scores||{}).length!==5||!Number.isFinite(d.total_score)||d.total_score<0||d.total_score>100)throw new Error('报告评分不完整或非法。');
    if(r.task_id!==records[0].request.task_id)throw new Error('报告混入了其他任务。');
    for(const key of ['attraction','audience_fit','clarity','channel_fit','call_to_action'])if(!Number.isInteger(d.dimension_scores?.[key]?.score)||d.dimension_scores[key].score<0||d.dimension_scores[key].score>100)throw new Error('五维评分非法。');
    if(Math.abs(Object.values(d.dimension_scores).reduce((sum,s)=>sum+s.score,0)/5-d.total_score)>0.01)throw new Error('报告总分与五维分不一致。');
  }
  const final=value.final||{...records.at(-1).outcome,...value};
  if(final.task_status==='completed')final.decision=({passed:'accept',not_passed:'stop_not_passed',needs_review:'stop_needs_review'})[final.assessment_status]||final.decision;
  if(!['accept','regenerate_creative','regenerate_strategy','stop_not_passed','stop_needs_review'].includes(final.decision))throw new Error('报告缺少有效评估结论。');
  const index=final.selected_evaluation_id==null?null:records.findIndex(r=>r.outcome.evaluation.result_id===final.selected_evaluation_id);
  if(index===-1)throw new Error('找不到报告选中的关联版本。');
  if(final.task_status==='completed'&&index===null)throw new Error('已完成报告缺少最终方案引用。');
  if(value.selected_index!=null&&value.selected_index!==index)throw new Error('报告选中位置与结果引用不一致。');
  return {label:value.label||'导入结果快照',mode:'imported',original_mode:value.original_mode||value.mode,source:'导入结果快照 · 未重新调用模型',config_snapshot:value.config_snapshot||{pass_threshold:80},model_metadata:value.model_metadata,execution:value.execution,feedback_status:value.feedback_status,records,events:value.events||[],selected_index:index,final};
}
export function buildExport(bundle){const record=selectReportRecord(bundle);return {schema_version:'1.0',mode:bundle.mode,original_mode:bundle.original_mode||bundle.mode,feedback_status:bundle.feedback_status,source:bundle.source,task_id:record.request.task_id,config_snapshot:bundle.config_snapshot,model_metadata:bundle.model_metadata??null,execution:bundle.execution??null,final:bundle.final,assessment_status:bundle.final.assessment_status,task_status:bundle.final.task_status,termination_reason:bundle.final.termination_reason,selected_evaluation_id:bundle.final.selected_evaluation_id,selected_results:bundle.selected_index==null?null:{strategy:record.request.strategy,creative:record.request.creative,evaluation:record.outcome.evaluation},remaining_issues:bundle.final.remaining_issues,history:bundle.records};}
