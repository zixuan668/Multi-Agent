import {dimensions,escapeHtml as escape,statuses} from './presentation.js';
import {roundFeedback} from './collaboration.js';

function verdict(row){
  const review=row.evaluation.data;
  if(review.risks.some(risk=>risk.severity==='high'))return '存在严重风险';
  if(row.decision==='request_input')return '需要补充事实';
  return row.decision==='accept'?'通过草稿评审':'需要修改或复核';
}

export function reviewSpotlight(task,row){
  const review=row?.evaluation?.data;
  const issue=roundFeedback(task,row).find(item=>item.status!=='resolved'&&item.priority==='high');
  return `<section class="review-spotlight" aria-label="毛小纯的效果评估"><div><strong>毛小纯 · 效果评估</strong><p>${review?`第 ${row.round_no} 轮 · ${escape(verdict(row))}${issue?' · '+escape(issue.issue):''}`:task.stage==='evaluation'?'正在核对这份策略与创意':'创意交付后，评分、风险与修改建议会在这里显示。'}</p></div>${review?`<span class="spotlight-score">${Number(review.total_score).toFixed(1)}<span>参考分</span></span>`:''}<button class="button" data-pane="review">${review?'查看完整评估':'查看评估进度'}</button></section>`;
}

export function evaluationOverview(task,row){
  const review=row.evaluation.data;
  const score=Math.min(100,Math.max(0,Number(review.total_score)||0));
  const high=review.risks.filter(risk=>risk.severity==='high').length;
  const feedback=roundFeedback(task,row).filter(item=>item.status!=='resolved');
  const first=task.rounds.find(item=>item.evaluation)?.evaluation.data.total_score;
  const delta=row.round_no>1?score-Number(first):null;
  return `<header class="evaluation-heading"><div><span class="section-label">第三位智能体 · 毛小纯</span><h2>效果评估与修改</h2><p>第 ${row.round_no} 轮 · ${task.config_snapshot.provider==='offline'?'离线规则结果':'基于本轮实际策略与创意'}</p></div><span class="team-badge">${escape(verdict(row))}</span></header><div class="evaluation-overview"><section class="evaluation-card"><h3>综合参考分</h3><div class="evaluation-score-body"><div class="evaluation-score-ring"><svg viewBox="0 0 160 160" aria-hidden="true"><circle class="evaluation-ring-track" cx="80" cy="80" r="70"/><circle class="evaluation-ring-value" cx="80" cy="80" r="70" pathLength="100" stroke-dasharray="${score} 100" transform="rotate(-90 80 80)"/></svg><strong>${score.toFixed(1)}<span>/ 100</span></strong></div><div><strong>${escape(verdict(row))}</strong><p>通过线 ${Number(task.config_snapshot.pass_threshold)}</p>${delta!==null?`<p>较首轮 ${delta>=0?'+':''}${delta.toFixed(1)} 分</p>`:''}</div></div><p>模型参考，不代表实际点击率或销量。</p></section><section class="evaluation-card"><h3>五维评分</h3><div class="evaluation-dimensions">${Object.entries(dimensions).map(([key,label])=>{const item=review.dimension_scores[key];const value=Math.min(100,Math.max(0,Number(item.score)||0));return `<details class="evaluation-dimension"><summary><span>${label}</span><meter class="evaluation-bar" min="0" max="100" value="${value}" aria-label="${label}">${value}</meter><strong>${value}</strong><span aria-hidden="true">⌄</span></summary><p>${escape(item.reason)}</p><p class="quote">${escape(item.evidence)}</p></details>`;}).join('')}</div></section></div><div class="evaluation-checks"><section><strong>${high}</strong><span>严重风险</span></section><section><strong>${feedback.filter(item=>item.priority==='high').length}</strong><span>必须修改</span></section><section><strong>${feedback.filter(item=>item.priority!=='high').length}</strong><span>完善建议</span></section></div>${task.image_jobs?.some(job=>job.status==='succeeded')?'<p class="image-review-boundary">本次评估针对文字方案，AI 宣传图仍需人工核对，未通过图像审核。</p>':''}`;
}

export function evaluationHub(tasks){
  const reviewed=tasks.filter(task=>task.review);
  return `<div class="page-heading"><div><span class="section-label">毛小纯 · 第三位智能体</span><h1>效果评估</h1><p>查看已保存任务的评估，不用再进入演示页。</p></div><button class="button" data-new-task>新建营销任务</button></div><section class="evaluation-hub-list" aria-label="已保存任务的效果评估">${reviewed.length?reviewed.map(task=>`<article class="panel evaluation-task"><div><h2>${escape(task.product_name)}</h2><p>第 ${task.review.round_no} 轮 · ${escape(statuses[task.status]||task.status)}${task.review.provider==='offline'?' · 离线规则结果':''}</p>${task.review.high_risks?`<p class="evaluation-risk-warning">${task.review.high_risks} 项严重风险，不能只看分数</p>`:''}</div><strong class="hub-score">${Number(task.review.total_score).toFixed(1)}<span>参考分</span></strong><button class="button primary" data-review-task="${escape(task.task_id)}" data-review-round="${task.review.round_no}">查看评估与修改</button></article>`).join(''):'<div class="panel history-empty"><h2>还没有已完成的评估</h2><p>策略与创意交付后，毛小纯会接手评估，结果保存在这里。</p></div>'}</section>`;
}
