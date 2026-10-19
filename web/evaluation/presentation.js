/** User-facing conclusions; system decisions and source versions stay intact. */
import {selectReportRecord,buildExport,unpackText} from './api.js';

export function describeConclusion(bundle,index=bundle.selected_index??bundle.records.length-1,job=bundle.execution??null){
  const record=bundle.records[index],data=record.outcome.evaluation.data;
  const historical=index!==(bundle.selected_index??bundle.records.length-1);
  const outcome=historical?record.outcome:bundle.final;
  const high=data.risks.filter(r=>r.severity==='high').length;
  const pending=outcome.pending_high_feedback_count||0;
  if(job?.status==='failed')return {title:'本次评估未完成',body:'已有结果已保留，请查看错误信息后处理。',tone:'red',label:'评估失败',historical,canDeliver:false};
  if(job?.status==='running')return {title:'正在评估新版本',body:'上一轮结果暂时保留，完成后将显示新的结论。',tone:'cyan',label:'评估中',historical,canDeliver:false};
  const action=outcome.decision;
  if(action==='accept'&&high===0)return {title:'当前方案通过评估',body:data.feedback.length?`综合评分 ${data.total_score.toFixed(1)} 分，无严重风险。另有 ${data.feedback.length} 项可完善建议。`:`综合评分 ${data.total_score.toFixed(1)} 分，本次未发现严重风险。`,tone:'green',label:'通过',historical,canDeliver:false};
  if(action==='regenerate_strategy')return {title:'策略需要调整',body:pending?`上轮仍有 ${pending} 项严重问题尚未确认解决，请先调整策略后重新评估。`:'先调整营销策略，再更新广告创意并重新评估。',tone:'amber',label:'交回策略',historical,canDeliver:!historical&&outcome.task_status==='optimizing'};
  if(action==='stop_needs_review')return {title:'方案需要人工复核',body:'已达到评估轮次上限，保留风险较少的版本供复核。',tone:'red',label:'待人工复核',historical,canDeliver:false};
  if(action==='stop_not_passed')return {title:'本次方案未达标',body:'已达到轮次上限，保留无严重风险的较优版本。',tone:'amber',label:'未达标',historical,canDeliver:false};
  return {title:'创意需要修改',body:pending?`上轮仍有 ${pending} 项严重问题尚未确认解决，请修改并再次交付评估。`:high?`发现 ${high} 项严重风险，修改后才能采用。`:'请按评估建议修改创意，再次交付评估。',tone:high||pending?'red':'amber',label:'待修改',historical,canDeliver:false};
}

export function buildADelivery(bundle){
  if(bundle.execution?.status==='failed'||bundle.execution?.status==='running')throw new Error('本次评估尚未成功，不能交付。');
  const final=bundle.final,record=selectReportRecord(bundle);
  if(final.task_status!=='optimizing'||final.decision!=='regenerate_strategy')throw new Error('只有待调整的策略问题需要交回策略智能体。');
  const ledger=bundle.feedback_status??[...(record.request.feedback??[]),...record.outcome.evaluation.data.feedback];
  const feedback=ledger.filter(f=>f.target_agent==='strategy'&&!f.resolved);
  if(!feedback.length)throw new Error('没有待处理的策略反馈。');
  const report=buildExport(bundle);
  return {schema_version:'c-to-a-delivery-candidate-v1',delivery_type:'strategy_feedback',
    task_id:record.request.task_id,source_evaluation_id:record.outcome.evaluation.result_id,requirements:record.request.requirements,
    strategy:record.request.strategy,creative:record.request.creative,evaluation:record.outcome.evaluation,
    feedback,pending_creative_feedback:ledger.filter(f=>f.target_agent==='creative'&&!f.resolved),
    assessment_status:final.assessment_status,selected_evaluation_id:final.selected_evaluation_id,
    next_action:'A只处理strategy反馈并保留原始需求，更新策略后由B生成依赖新策略的创意，再由C复评',
    report};
}

export function describeProcessing(job){
  if(job?.status==='loading')return {title:'正在打开本次评估',body:'本次方案已准备好。',step:0,tone:'cyan'};
  if(job?.status==='failed')return {title:'本次评估未完成',body:job.error?.message||'请返回需求页面重新提交，已有方案可以继续查看。',step:-1,tone:'red'};
  if(!job)return {title:'方案尚未交付评估',body:'请在创意工作区确认本次方案。',step:0,tone:'neutral'};
  if(job.stage==='queued')return {title:'本次方案已接收',body:'下方是本次广告创意，结论会在这里更新。',step:0,tone:'cyan'};
  if(job.stage==='creative_revision')return {title:'正在完善广告创意',body:'正在按本轮建议修改创意，完成后重新评估。',step:0,tone:'cyan'};
  return {title:job.stage==='applying_feedback'?'正在整理评估结论':'正在评估这份方案',body:job.stage==='retrying'?'评估正在重新检查，你可以先查看下方方案。':'方案已接收，你可以先查看本次创意。',step:job.stage==='applying_feedback'?2:1,tone:'cyan'};
}

export function buildReportText(bundle){
  const row=selectReportRecord(bundle),r=row.request,d=row.outcome.evaluation.data,s=r.strategy.data;
  const desc=describeConclusion(bundle),levels={high:'严重',medium:'中等',low:'低'};
  const termination=({passed:'达到通过条件',round_limit:'达到评估轮次上限',technical_error:'评估执行失败'})[bundle.final.termination_reason]||'仍需调整';
  const dimensionNames={attraction:'吸引力',audience_fit:'用户匹配度',clarity:'信息传达',channel_fit:'渠道适配',call_to_action:'行动引导'};
  const clean=value=>unpackText(value).base;
  const lines=[r.requirements.product_name+' · 营销方案',`评估结论：${desc.label}`,`综合评分：${d.total_score.toFixed(1)} / 100`,`流程结果：${termination}`,
    '评分仅用于方案质量参考，不代表真实投放效果。','【原始需求】',clean(r.requirements.product_description),'目标：'+clean(r.requirements.marketing_goal),'限制：'+clean(r.requirements.special_requirements),
    '【营销策略】','目标人群：'+(s.target_audience?.segment||'待确认'),'定位：'+s.positioning,
    ...(s.selling_points||[]).map(p=>`卖点：${p.claim}\n依据：${p.source_quote}`),...(s.channels||[]).map(c=>`渠道：${c.name}\n理由：${c.reason}\n内容方向：${c.content_direction}\n预算分配：${c.allocated_amount??'待确认'}`),
    '传播主题：'+(s.marketing_strategy?.theme||''),...(s.marketing_strategy?.content_directions||[]),...(s.marketing_strategy?.promotion_methods||[]),
    '假设：'+(s.assumptions?.join('；')||'无'),'信息缺口：'+(s.missing_information?.join('；')||'无'),'约束冲突：'+(s.constraint_conflicts?.join('；')||'无'),'【广告创意】'];
  for(const item of r.creative.data.items){
    const poster=typeof item.poster_concept==='string'?item.poster_concept:[item.poster_concept?.headline,item.poster_concept?.visual_description].filter(Boolean).join('\n');
    const video=typeof item.video_script==='string'?item.video_script:(item.video_script?.scenes||[]).map(s=>`${s.duration_seconds}秒：${s.visual}\n旁白：${s.narration}`).join('\n');
    lines.push('渠道：'+item.channel,'广告文案：\n'+item.copy,'核心短句：'+item.slogan,'海报文字：\n'+poster,'短视频脚本：\n'+video,'待确认事项：'+(item.pending_confirmations?.join('；')||'无'));
  }
  lines.push('【五维评分】',...Object.entries(dimensionNames).map(([key,name])=>`${name}：${d.dimension_scores[key].score} 分\n${d.dimension_scores[key].reason||''}`),
    '【风险】',...(d.risks.length?d.risks.map(v=>`${levels[v.severity]}风险：${v.description}\n依据：${v.evidence}`):['本次未发现风险项']),
    '【修改建议】',...(d.feedback.length?d.feedback.map(f=>`${f.target_agent==='strategy'?'策略':'创意'}：${f.issue}\n建议：${f.suggestion}`):['无']),
    '【剩余问题】',...(bundle.final.remaining_issues?.length?bundle.final.remaining_issues:['无']),
    '策略版本：'+r.strategy.result_id,'创意版本：'+r.creative.result_id,'评估版本：'+row.outcome.evaluation.result_id);
  return lines.join('\n\n');
}

export function shouldReplaceLiveSelection(bundle,newBundle){
  return !bundle||bundle.records.at(-1)?.outcome.evaluation.result_id!==newBundle.records.at(-1)?.outcome.evaluation.result_id;
}
