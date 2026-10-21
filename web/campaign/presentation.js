export const statuses = {pending:'等待开始',running:'协作进行中',awaiting_direction:'等你选创意方向',awaiting_revision:'等你确认修改',awaiting_confirmation:'待你确认',awaiting_input:'需要补充信息',approved:'已确认方案',needs_revision:'需要继续修改',needs_review:'需要人工复核',failed:'当前阶段失败',interrupted:'可继续执行',cancelled:'已取消'};
export const agents = {strategy:'李智信 · 策略',creative:'李莉 · 创意',evaluation:'毛小纯 · 评审',coordinator:'协作交接',human:'你'};
export const dimensions = {attraction:'吸引力',audience_fit:'受众匹配',clarity:'信息清晰度',channel_fit:'渠道适配',call_to_action:'行动引导'};
export function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,character=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[character]));}
export function selectedRound(task,requested=null){if(!task?.rounds?.length)return null;return task.rounds.find(row=>row.round_no===(requested??task.selected_round??task.rounds.length))??task.rounds.at(-1);}
export function stageStates(task){const row=task?.rounds?.at(-1);return ['strategy','creative','evaluation'].map(agent=>({agent,done:Boolean(row?.[agent]),current:task?.status==='running'&&task.stage===agent}));}
export function openFeedback(task){return (task?.feedback??[]).filter(feedback=>feedback.status==='open');}
export function creativeText(creative,index){const item=creative.data.items[index];return [item.headline,item.body,item.call_to_action].join('\n\n');}
export function evidenceText(value){return typeof value==='string'?value:JSON.stringify(value,null,2);}
export function canResume(task,configVersion){return ['failed','interrupted'].includes(task.status)&&(!configVersion||task.config_version===configVersion)&&task.usage.model_calls<task.config_snapshot.max_model_calls&&task.usage.active_seconds<task.config_snapshot.max_seconds;}
export function roundLabel(task,row){if(task.status==='awaiting_direction')return `第 ${row.round_no} 轮 · 待选方向`;const active=['pending','running'].includes(task.status);return `第 ${row.round_no} 轮${task.selected_round===row.round_no?(task.status==='failed'||task.status==='interrupted'?' · 保留版本':' · 选中版本'):''}${!row.evaluation?(active?' · 生成中':' · 未完成'):''}`;}
