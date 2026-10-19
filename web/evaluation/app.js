import {ParticleFlow} from './particles.js';
import {createClient,escapeHtml as e,resolveContent,buildExport,selectReportRecord,readReport,unpackText} from './api.js';
import {describeConclusion,buildADelivery,shouldReplaceLiveSelection,describeProcessing,buildReportText} from './presentation.js';
import {buildStrategyDocument} from './document.js';

const paths={grid:'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',layers:'m12 3 10 6-10 6L2 9z M2 14l10 6 10-6 M2 18l10 6 10-6',activity:'M2 12h4l3-8 6 16 3-8h4',file:'M14 2H5v20h14V7z M14 2v6h5 M8 12h8 M8 16h8',clock:'M12 8v5l3 2 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',sliders:'M4 4v16 M12 4v16 M20 4v16 M1 8h6 M9 16h6 M17 10h6',shield:'M12 3 3 7v6c0 5 9 9 9 9s9-4 9-9V7z m-4 9 3 3 5-6',sparkles:'m12 3 2 7 7 2-7 2-2 7-2-7-7-2 7-2z M20 2v4 M18 4h4',help:'M9 9a3 3 0 1 1 5 2l-2 2v1 M12 17h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',upload:'M12 16V3 m-5 5 5-5 5 5 M3 15v6h18v-6',download:'M12 3v13 m-5-5 5 5 5-5 M3 17v4h18v-4',play:'m7 3 14 9-14 9z',box:'m12 2 10 5v10l-10 5-10-5V7z M2 7l10 5 10-5 M12 12v10',compass:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 m-6-4-3 8-5 1 3-8z',pen:'m4 15 11-11 5 5L9 20l-6 1z M13 6l5 5',aperture:'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0 M7 3l7 12 M3 7h14 M3 17l7-12 M10 21l7-12 M21 17H7 M21 7l-7 12',info:'M12 11v6 M12 7h.01 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',cursor:'m4 3 15 10-7 1-4 6z', 'arrow-up-right':'M7 17 17 7 M7 7h10v10',x:'m6 6 12 12 M6 18 18 6',check:'m5 12 4 4 10-10',copy:'M9 9h12v12H9z M15 9V3H3v12h6',link:'m10 14 4-4 M8 16l-3 3a4 4 0 0 1-5-5l4-4 M16 8l3-3a4 4 0 0 1 5 5l-4 4'};
const icon=name=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${paths[name]||paths.file}"/></svg>`;
document.querySelectorAll('[data-icon]').forEach(node=>node.innerHTML=icon(node.dataset.icon));
const $=id=>document.getElementById(id), api=createClient(), flow=new ParticleFlow($('flow-canvas'));
const dimensions={attraction:'吸引力',audience_fit:'用户匹配度',clarity:'信息传达',channel_fit:'渠道适配',call_to_action:'行动引导'};
const actions={accept:'接受当前方案',regenerate_creative:'优化广告创意',regenerate_strategy:'优先优化营销策略',stop_not_passed:'停止优化 · 未达标',stop_needs_review:'停止优化 · 人工复核'};
const assessment={passed:['通过评估','green'],not_passed:['未达标','amber'],needs_review:['待人工复核','red'],not_evaluated:['待继续优化','cyan']};
const categories={fact:'事实依据',constraint:'硬性约束',compliance:'合规风险',brand:'品牌表达',audience:'用户接受'};
const level={high:'严重',medium:'中等',low:'轻微'};
const state={bundle:null,source:null,index:0,view:'workbench',context:'requirements',filter:'all',busy:false,loading:false,history:[]};
const liveTask=new URLSearchParams(location.search).get('task_id');
if(liveTask)$('nav-creative').href='/creative?task_id='+encodeURIComponent(liveTask);
let livePolling=false,liveJob=null,liveCreative=null,previewChannel=0,previewField='copy',processingPreviewKey=null;
try{state.history=JSON.parse(localStorage.getItem('zhice.evaluation.replays.v1')||'[]');if(!Array.isArray(state.history))state.history=[];}catch{state.history=[];}
let toastTimer;
function toast(message){$('toast').textContent=message;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3200);}
function error(error){$('error-banner').textContent=error.message||String(error);$('error-banner').hidden=false;}
function badge(status){const [label,color]=assessment[status]||assessment.not_evaluated;return `<span class="badge ${color}">${label}</span>`;}
function current(){return state.bundle?.records[state.index];}
function result(){return current()?.outcome.evaluation.data;}
function openDialog(title,html,eyebrow='EVALUATION DETAIL'){$('dialog-title').textContent=title;$('dialog-eyebrow').textContent=eyebrow;$('dialog-content').innerHTML=`<div class="dialog-copy">${html}</div>`;if(!$('detail-dialog').open)$('detail-dialog').showModal();}
$('dialog-close').onclick=()=>$('detail-dialog').close();$('detail-dialog').onclick=event=>{if(event.target===$('detail-dialog')){const r=$('detail-dialog').getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)$('detail-dialog').close();}};

function showView(view){
  if(!state.bundle){if(liveTask&&liveCreative)renderProcessing(liveJob);return;}
  state.view=view;
  document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==`view-${view}`);
  const processing=Boolean(liveTask&&(liveJob?.status!=='succeeded'||state.busy));
  $('processing-panel').hidden=!processing||view!=='workbench';
  if(processing&&view==='workbench')$('view-workbench').hidden=true;
  document.querySelectorAll('.nav-item[data-view]').forEach(el=>el.classList.toggle('active',el.dataset.view===view));
  $('page-title').textContent={workbench:'效果评估智能体',versions:'历史轮次',report:'方案报告',events:'运行记录'}[view]||'效果评估智能体';
  if(view==='versions')renderVersions();if(view==='report')renderReport();
  if(view==='events')renderLiveEvents(state.liveEvents||state.bundle.events||[]);
  if(view==='workbench')flow.resize();
}

function disableInputs(disabled){for(const id of ['run-btn','import-btn','product-select','scenario-select'])$(id).disabled=disabled||Boolean(liveTask);}
async function loadPreset(){if(state.busy||state.loading)return;state.loading=true;disableInputs(true);$('run-btn').querySelector('span:last-child').textContent='载入样例…';try{const product=$('product-select').value;const scenario=$('scenario-select').value;state.source=await api.sample(product==='imported'?0:product||0,scenario==='imported'?'improve':scenario||'improve');await run(false);}catch(ex){error(ex);}finally{state.loading=false;disableInputs(state.busy);if(!state.busy)$('run-btn').querySelector('span:last-child').textContent='重放评估';}}
async function run(animate=true){if(!state.source||state.busy)return;state.busy=true;$('error-banner').hidden=true;$('run-btn').disabled=true;$('import-btn').disabled=true;$('product-select').disabled=true;$('scenario-select').disabled=true;$('run-btn').querySelector('span:last-child').textContent='重放中…';$('particle-stage').classList.add('running');$('engine-badge').innerHTML='<i></i>离线规则重放中';flow.running=true;
  try{const response=await api.replay(state.source);if(animate&&!matchMedia('(prefers-reduced-motion: reduce)').matches)await new Promise(resolve=>setTimeout(resolve,600));state.bundle=response.data;state.index=state.bundle.selected_index??state.bundle.records.length-1;state.filter='all';render();saveHistory();toast(animate?'重放完成 · 已重新计算分数、风险与系统动作':'已载入契约样例');notifyParent('zhice:evaluation:completed',{task_id:state.bundle.final.evaluation.task_id,assessment_status:state.bundle.final.assessment_status,selected_evaluation_id:state.bundle.final.selected_evaluation_id});}
  catch(ex){error(ex);$('engine-badge').textContent='重放未完成';toast('请检查错误位置后重试');}
  finally{state.busy=false;flow.running=false;$('particle-stage').classList.remove('running');disableInputs(state.loading);$('run-btn').querySelector('span:last-child').textContent='重放评估';if(state.bundle)render();}
}
$('run-btn').onclick=()=>run();$('product-select').onchange=loadPreset;$('scenario-select').onchange=loadPreset;
function render(){
  const b=state.bundle,r=current(),d=result(),c=b.config_snapshot;
  const summary=describeConclusion(b,state.index,liveTask?liveJob:b.execution);
  $('entry-panel').hidden=true;
  $('page-title').textContent='效果评估智能体';
  document.querySelector('.system-status').textContent=b.mode==='live'?'真实评估':b.mode==='imported'?'导入报告':'演示';
  document.querySelector('.page-footer').textContent='评分仅用于方案质量参考，不代表真实投放效果。';
  $('task-id').textContent=r.request.task_id;
  $('conclusion-product').textContent=r.request.requirements.product_name;
  $('conclusion-round').textContent=`第 ${r.request.round_no} 轮 / ${c.max_rounds??3} 轮`;
  $('conclusion-title').textContent=summary.title;$('conclusion-body').textContent=summary.body;
  $('conclusion-symbol').textContent=summary.tone==='green'?'✓':summary.tone==='red'?'!':'↗';
  $('conclusion-symbol').className='conclusion-symbol '+summary.tone;
  $('history-notice').hidden=!summary.historical;
  $('total-score').textContent=d.total_score.toFixed(1);$('ring-progress').style.strokeDashoffset=502.65*(1-d.total_score/100);
  $('assessment-badge').className='badge '+summary.tone;$('assessment-badge').textContent=summary.label;
  const delta=d.total_score-b.records[0].outcome.evaluation.data.total_score;
  $('score-delta').textContent=state.index?`${delta>=0?'+':''}${delta.toFixed(1)} 分，相比首轮`:'首次评估';
  $('pass-threshold').textContent='通过线 '+c.pass_threshold;
  $('dimensions').innerHTML=Object.entries(dimensions).map(([key,title])=>`<button class="dimension-row" data-dimension="${key}" aria-label="${title} ${d.dimension_scores[key].score}分，查看依据"><span>${title}</span><div class="bar-track"><div class="bar-fill" data-score="${d.dimension_scores[key].score}"></div></div><span class="bar-value">${d.dimension_scores[key].score}</span></button>`).join('');
  document.querySelectorAll('.bar-fill[data-score]').forEach(node=>node.style.width=node.dataset.score+'%');
  $('risk-count').textContent=d.risks.length;
  document.querySelectorAll('.nav-item[data-view]').forEach(n=>n.disabled=false);
  $('delivery-a-btn').hidden=b.mode==='offline'||b.original_mode==='offline'||!summary.canDeliver||state.busy||state.liveUnavailable;
  $('delivery-a-btn').disabled=state.busy;
  $('export-final-btn').hidden=b.final.task_status!=='completed'||liveJob?.status==='running'||liveJob?.status==='failed'||state.busy||state.liveUnavailable;
  $('revise-live').hidden=!liveTask||summary.historical||b.final.decision!=='regenerate_creative'||liveJob?.status!=='succeeded';
  $('revise-live').disabled=state.busy;
  $('feedback-heading').textContent=summary.label==='通过'?'可完善建议':'修改建议';
  renderRisks();renderFeedback();renderContext();showView(state.view);
}

function renderRisks(){
  const all=result().risks,filtered=state.filter==='all'?all:all.filter(x=>x.severity===state.filter);
  for(const severity of ['all','high','medium','low'])$(severity+'-count').textContent=severity==='all'?all.length:all.filter(x=>x.severity===severity).length;
  document.querySelectorAll('[data-filter]').forEach(el=>el.classList.toggle('active',el.dataset.filter===state.filter));
  $('risks').innerHTML=filtered.length?filtered.map(r=>`<button class="risk-entry" data-risk="${all.indexOf(r)}"><div><span>${e(categories[r.category])}</span><span class="badge ${r.severity==='high'?'red':r.severity==='medium'?'amber':'cyan'}">${level[r.severity]}</span></div><p>${e(r.description)}</p></button>`).join(''):`<div class="risk-empty"><div class="shield-outline">${icon('shield')}</div><b>${all.length?'此等级暂无风险':'本次未发现风险项'}</b></div>`;
}

function feedbackRows(){return [...result().feedback,...(current().outcome.pending_feedback||[]).filter(f=>f.priority==='high').map(f=>({...f,pendingReview:true}))];}
function renderFeedback(){
  const rows=feedbackRows();
  $('feedback').innerHTML=rows.length?`<div class="feedback-scroll">${rows.map((f,i)=>`<div class="feedback-item"><span class="badge ${f.priority==='high'?'red':'amber'}">${f.pendingReview?'上轮待复核 · ':''}${f.target_agent==='strategy'?'策略':'创意'} · ${level[f.priority]}</span><button data-feedback="${i}">${e(f.issue)} ↗</button><p>${e(f.suggestion)}</p></div>`).join('')}</div>`:'<div class="feedback-empty">暂无修改建议</div>';
}

function block(title,body,ref=''){return `<div class="context-block"><h3>${e(title)}</h3>${body}${ref?`<div class="ref-row">${e(ref)}</div>`:''}</div>`;}
function contextHtml(r,kind){const req=r.request.requirements,s=r.request.strategy.data,c=r.request.creative.data;
  if(kind==='requirements'){const product=unpackText(req.product_description),goal=unpackText(req.marketing_goal),constraints=unpackText(req.special_requirements);return `<div class="context-grid">${block('产品与营销目标',`<strong>${e(req.product_name)}</strong><p>${e(product.base)}</p><p>目标：${e(goal.base)}</p>`)}${block('受众与资源',`<p>${e(req.target_audience||'未提供目标受众')}</p><span class="tag">${req.budget?`${e(req.budget.currency)} ${Number(req.budget.amount).toLocaleString('zh-CN')}`:'预算待补充'}</span><span class="tag">${req.campaign_period?(req.campaign_period.duration_days?req.campaign_period.duration_days+'天':e(req.campaign_period.start_date)+' — '+e(req.campaign_period.end_date)):'周期待补充'}</span>${[['已有渠道','channelsState','existingChannels'],['可用素材','materialsState','availableMaterials'],['执行人力','teamState','teamResources']].map(([label,key,field])=>`<p>${label}：${e(constraints.detail[key]==='known'?constraints.detail[field]:constraints.detail[key]==='none'?'确认暂无':'待确认')}</p>`).join('')}`)}${block('特殊要求',`<p>${e(constraints.base||'无额外要求')}</p><details><summary>查看原始提交记录</summary><pre>${e(JSON.stringify(req,null,2))}</pre></details>`,r.request.task_id+' · 原始需求不可变')}</div>`;}
  if(kind==='strategy')return `<div class="context-grid">${block('用户画像与定位',`<strong>${e(s.target_audience.segment)}</strong><p>${e(s.positioning)}</p><p>依据：${e(s.target_audience.basis)}</p>`,r.request.strategy.result_id)}${block('卖点与渠道',s.selling_points.map(p=>`<p>${e(p.claim)}<br><span class="small-label">原文：${e(p.source_quote)}</span></p>`).join('')+s.channels.map(c=>`<span class="tag">${e(c.name)}</span><p>${e(c.reason)}<br>内容方向：${e(c.content_direction)}<br>分配金额：${c.allocated_amount??'未指定'}</p>`).join(''))}${block('传播主题与执行方式',`<strong>${e(s.marketing_strategy?.theme)}</strong>${(s.marketing_strategy?.content_directions||[]).map(x=>`<p>${e(x)}</p>`).join('')}${(s.marketing_strategy?.promotion_methods||[]).map(x=>`<p>${e(x)}</p>`).join('')}`)}${block('假设、信息缺口与冲突',`<p>假设：${e(s.assumptions.join('；')||'无')}</p><p>信息缺口：${e(s.missing_information.join('；')||'无')}</p><p>约束冲突：${e(s.constraint_conflicts.join('；')||'无')}</p>`)}</div>`;
  if(r.request.creative.schema_version==='b-internal-candidate-v1')return `<div class="context-grid">${c.items.map(item=>block(item.channel,`<strong>${e(item.slogan)}</strong><p>${e(item.copy)}</p><h3>海报文字</h3><pre>${e(item.poster_concept)}</pre><details><summary>短视频文字脚本</summary><pre>${e(item.video_script)}</pre></details><details><summary>随附依据与待确认事项</summary>${item.evidence.map(v=>`<p>${e(v.claim)}<br>原文：${e(v.source_quote)}</p>`).join('')}<p>${e(item.pending_confirmations.join('；')||'无待确认事项')}</p></details>`,r.request.creative.result_id)).join('')}${block('策略引用',`<p>${e(r.request.creative.strategy_result_id)}</p><p>V${r.request.creative.strategy_version} · 所用策略版本</p>`)}</div>`;
  return `<div class="context-grid">${c.items.map(item=>block(item.channel,`<strong>${e(item.slogan)}</strong><p>${e(item.copy)}</p><p>海报标题：${e(item.poster_concept.headline)}</p><p>画面文字描述：${e(item.poster_concept.visual_description)}</p><details><summary>短视频文字脚本 · ${item.video_script.duration_seconds}秒</summary>${item.video_script.scenes.map(s=>`<p>${s.duration_seconds}秒 / ${e(s.visual)}<br>旁白：${e(s.narration)}</p>`).join('')}</details>`,r.request.creative.result_id)).join('')}${block('创意假设与冲突',`<p>假设：${e(c.assumptions.join('；')||'无')}</p><p>冲突：${e(c.constraint_conflicts.join('；')||'无')}</p>`, '引用策略：'+c.strategy_result_id)}</div>`;
}
function renderContext(){document.querySelectorAll('[data-context]').forEach(el=>el.classList.toggle('active',el.dataset.context===state.context));$('context-content').innerHTML=contextHtml(current(),state.context);}
function evidenceHtml(path,request=current().request){let value=resolveContent(request,path);return `<h3>对应方案内容</h3><div class="highlight-content">${e(typeof value==='object'?JSON.stringify(value,null,2):value??'内容位置不可用')}</div>`;}
function dimensionDetail(key){const d=result().dimension_scores[key];openDialog(dimensions[key],`<div class="detail-score">${d.score}<span>/ 100 · 权重 20%</span></div><h3>评分依据</h3><p>${e(d.reason)}</p>${evidenceHtml(d.target_path)}`,'DIMENSION EVIDENCE');}
function riskDetail(index){const r=result().risks[index];openDialog(categories[r.category],`<span class="badge ${r.severity==='high'?'red':'amber'}">${level[r.severity]}风险</span><h3>风险说明</h3><p>${e(r.description)}</p><h3>风险证据</h3><p>${e(r.evidence)}</p>${evidenceHtml(r.target_path)}`,'RISK EVIDENCE');}
function feedbackDetail(index){const original=feedbackRows()[index],f=state.bundle.feedback_status?.find(f=>f.feedback_id===original.feedback_id)||original;openDialog('优化反馈',`<span class="badge amber">${f.target_agent==='strategy'?'策略智能体':'创意智能体'} · ${level[f.priority]}优先级</span><h3>具体问题</h3><p>${e(f.issue)}</p><h3>可执行修改</h3><p>${e(f.suggestion)}</p>${evidenceHtml(f.target_path)}<h3>处理状态</h3><p>${f.resolved?'已解决':'待复核'}</p>`,'ACTIONABLE FEEDBACK');}
function renderVersions(){
  const b=state.bundle;
  $('view-versions').innerHTML=`<section class="panel"><div class="view-lead"><h2>评估记录</h2></div><div class="table-scroll"><table><thead><tr><th>轮次</th><th>评分</th><th>严重风险</th><th>评估结论</th><th></th></tr></thead><tbody>${b.records.map((r,i)=>{const d=r.outcome.evaluation.data,desc=describeConclusion(b,i);return `<tr class="${i===b.selected_index?'selected':''}"><td>第 ${r.request.round_no} 轮${i===b.selected_index?' · 最终方案':''}</td><td><strong>${d.total_score.toFixed(1)}</strong></td><td>${d.risks.filter(x=>x.severity==='high').length}</td><td>${e(desc.label)}</td><td><button class="table-action" data-round="${i}">查看</button></td></tr>`;}).join('')}</tbody></table></div></section>`;
}

function renderEvents(){const b=state.bundle;$('view-events').innerHTML=`<section class="panel"><div class="view-lead"><div><h2>协同交接与规则重放记录</h2><p>策略与创意均为载入记录，以下耗时为离线规则计算实测，不是模型生成耗时。</p></div><span class="badge cyan">${b.events.length} 条事件</span></div><div class="event-list">${b.events.map(v=>`<div class="event"><div class="event-time">${e(new Date(v.time).toLocaleTimeString('zh-CN',{hour12:false}))}<br>第 ${v.round_no} 轮</div><span class="event-marker">${icon(v.status==='succeeded'?'check':'activity')}</span><div class="event-content"><h3>${v.status==='succeeded'?'评估规则计算完成':'上游数据交接与校验'}</h3><p>${e(v.summary)}</p><div class="event-meta">EVALUATION · ATTEMPT ${v.attempt_count}${v.elapsed_ms!==undefined?' · '+v.elapsed_ms+' ms（离线计算）':''}</div></div></div>`).join('')}</div><div class="table-note">真实策略、创意生成和反馈调度需由公共后端接入；页面未执行上游模型生成。</div></section>`;}
function renderReport(){
  const b=state.bundle,r=selectReportRecord(b),d=r.outcome.evaluation.data,desc=describeConclusion(b);
  $('view-report').innerHTML=`<section class="panel"><div class="view-lead"><div><h2>${e(r.request.requirements.product_name)}</h2></div><div class="report-actions"><button class="button secondary" data-action="copy">复制报告</button><button class="button secondary" data-action="export">导出 JSON</button></div></div><div class="report-summary"><div class="report-status"><span class="big-number">${d.total_score.toFixed(1)}</span><span class="badge ${desc.tone}">${e(desc.label)}</span></div><p>${e(desc.body)}</p></div><div class="report-folds"><p>${e(({passed:'达到通过条件',round_limit:'达到轮次上限',technical_error:'本次评估未完成'})[b.final.termination_reason]||'仍需调整')} · 当前报告为第 ${r.request.round_no} 轮方案</p><details open><summary>评估意见</summary>${Object.entries(dimensions).map(([k,n])=>`<div class="report-dimension"><strong>${n} · ${d.dimension_scores[k].score} 分</strong><p>${e(d.dimension_scores[k].reason)}</p></div>`).join('')}</details><details><summary>风险与建议（${d.risks.length+d.feedback.length}）</summary>${d.risks.map(x=>`<p><strong>${e(level[x.severity])}风险</strong> · ${e(x.description)}</p>`).join('')}${d.feedback.map(x=>`<p><strong>${e(x.issue)}</strong><br>${e(x.suggestion)}</p>`).join('')||'<p>暂无修改建议。</p>'}</details><details><summary>原始需求</summary>${contextHtml(r,'requirements')}</details><details><summary>营销策略</summary>${contextHtml(r,'strategy')}</details><details><summary>广告创意</summary>${contextHtml(r,'creative')}</details></div></section>`;
}

function configDialog(){if(!state.bundle)return;const c=state.bundle.config_snapshot;openDialog('任务配置快照',`<p>任务创建时冻结配置。此处只读，管理员通过受控配置维护。</p><div class="config-list">${Object.entries(c).map(([k,v])=>`<div><span>${e(k)}</span><strong>${e(v)}</strong></div>`).join('')}</div><p>密钥不进入页面或导出。${liveTask?'当前任务使用冻结的服务端模型配置。':'当前为离线规则预览。'}</p>`,'FROZEN CONFIGURATION');}
$('config-btn').onclick=configDialog;
function scoreHelp(){openDialog('五维等权评分规则',`<p>综合分 =（吸引力 + 用户匹配度 + 信息传达 + 渠道适配 + 行动引导）÷ 5，四舍五入保留1位小数。</p><p>通过必须同时满足：达到任务冻结的通过线，且没有严重风险。</p><h3>分档解释</h3><p>0–39 明显不满足<br>40–59 关键内容缺失<br>60–79 基本满足但有明显缺陷<br>80–89 满足且理由充分<br>90–100 充分满足且无明显缺陷</p>`,'SCORING RULES');}
$('score-help').onclick=scoreHelp;
function downloadBlob(filename,blob){const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=filename;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function download(filename,value){downloadBlob(filename,new Blob([JSON.stringify(value,null,2)],{type:'application/json;charset=utf-8'}));}
function exportReport(){if(!state.bundle)return;download(`${selectReportRecord(state.bundle).request.task_id}-evaluation.json`,buildExport(state.bundle));toast('完整方案与评估报告已导出');}
async function copyReport(){
  const content=buildReportText(state.bundle);
  try{await navigator.clipboard.writeText(content);toast('报告已复制');}catch{openDialog('复制报告',`<pre>${e(content)}</pre>`);}
}
$('export-final-btn').onclick=()=>exportReport();

function saveHistory(){const b=state.bundle;const item={id:b.final.evaluation.result_id,product:selectReportRecord(b).request.requirements.product_name,label:b.label,time:new Date().toISOString(),source:state.source};state.history=[item,...state.history].slice(0,20);try{localStorage.setItem('zhice.evaluation.replays.v1',JSON.stringify(state.history));}catch{toast('浏览器存储已满，当前结果仍可导出');}$('history-count').textContent=state.history.length;}
function historyDialog(){openDialog('本地重放记录',`<div class="history-toolbar"><span>仅此浏览器 · 最多20条</span><button class="text-link" data-action="clear-history">清空记录</button></div><p>这不是全站历史查询或云端持久化。重新打开记录会通过本地规则引擎再次计算。</p>${state.history.length?state.history.map((h,i)=>`<div class="history-item"><div><b>${e(h.product)}</b><small>${e(h.label)} · ${e(new Date(h.time).toLocaleString('zh-CN'))}</small></div><button data-history="${i}">重新载入 ↗</button></div>`).join(''):'<div class="empty-state">暂无本地记录</div>'}`,'LOCAL REPLAY HISTORY');}
$('history-count').textContent=state.history.length;$('history-btn').onclick=historyDialog;
$('import-btn').onclick=()=>$('file-input').click();
$('file-input').onchange=async event=>{
  const file=event.target.files?.[0];if(!file)return;
  try{
    if(file.size>2000000)throw new Error('报告不能超过2MB。');
    const source=JSON.parse(await file.text());
    if(source.records||source.history||source.schema_version==='c-to-a-delivery-candidate-v1'){
      const next=readReport(source);state.bundle=next;state.source=null;state.index=next.selected_index??next.records.length-1;state.view='workbench';state.filter='all';
      $('error-banner').hidden=true;$('entry-panel').hidden=true;$('processing-panel').hidden=true;
      document.querySelector('.task-bar').hidden=true;$('run-btn').hidden=true;render();toast('报告已载入');
    }else{
      if(!source.rounds||!source.config_snapshot)throw new Error('请导入完整评估报告或重放记录。');
      state.source=source;$('entry-panel').hidden=true;await run();
    }
  }catch(ex){error(ex);}finally{event.target.value='';}
};

$('help-btn').onclick=()=>liveTask?openDialog('真实评估使用说明','<p>B交付当前已保存版本后，效果评估智能体通过服务端模型评估五维质量与风险。分数、风险否决和最终版本由代码计算。</p><p>仅创意问题可按反馈修订；策略问题导出给A，由A更新策略后交B重新生成。最多三轮，技术重试不会增加业务轮次。</p><p>报告保留同一组策略、创意和评估引用。当前任务在服务进程内保存，请在停机前导出JSON。</p>'):openDialog('工作台使用说明',`<p>选择产品和评估场景，点击“重放评估”。综合分、严重风险否决、反馈路由和最终版本由 Python 规则计算。</p><h3>团队交接</h3><p>A 提供完整策略响应，B 提供引用该策略的完整创意响应；效果评估智能体通过公开契约校验它们属于同一任务。当前仓库中的创意响应与评估契约仍是待团队复核的提案。</p><h3>导入记录</h3><p>使用含 rounds、config_snapshot 的 JSON 包，每轮包含 request 与预设 draft。原始需求和配置不可变，最多3轮。模板是联调用样例，不是真实模型报告。</p><button class="button secondary" data-action="template">${icon('download')}下载当前重放模板</button><h3>数据保存</h3><p>离线重放只保存在当前浏览器，不调用付费模型。</p>`,'WORKBENCH GUIDE');
document.addEventListener('click',async event=>{const target=event.target.closest('button');if(!target)return;if(target.dataset.view){showView(target.dataset.view);return;}if(target.dataset.preview){previewField=target.dataset.preview;renderProcessing(liveJob);return;}if(target.dataset.previewChannel!==undefined){previewChannel=Number(target.dataset.previewChannel);renderProcessing(liveJob);return;}if(!state.bundle)return;if(target.dataset.dimension)dimensionDetail(target.dataset.dimension);if(target.dataset.risk!==undefined)riskDetail(Number(target.dataset.risk));if(target.dataset.feedback!==undefined)feedbackDetail(Number(target.dataset.feedback));if(target.dataset.filter){state.filter=target.dataset.filter;renderRisks();}if(target.dataset.context){state.context=target.dataset.context;renderContext();}if(target.dataset.round!==undefined){state.index=Number(target.dataset.round);render();showView('workbench');toast('正在查看第 '+current().request.round_no+' 轮的关联版本');}if(target.dataset.action==='export')exportReport();if(target.dataset.action==='copy')await copyReport();if(target.dataset.action==='template'){download('zhice-evaluation-replay-template.json',state.source);toast('已下载当前场景的完整重放模板');}if(target.dataset.action==='clear-history'){state.history=[];localStorage.removeItem('zhice.evaluation.replays.v1');$('history-count').textContent='0';historyDialog();}if(target.dataset.history!==undefined){state.source=state.history[Number(target.dataset.history)].source;$('detail-dialog').close();await run();}});
// Optional iframe bridge; only messages from the actual same-origin parent are accepted.
function notifyParent(type,data={}){if(parent!==window)parent.postMessage({type,...data},location.origin);}
window.addEventListener('message',async event=>{if(parent===window||event.source!==parent||event.origin!==location.origin)return;if(event.data?.type==='zhice:evaluation:load'&&!state.busy&&!state.loading){state.source=event.data.bundle;await run();}});
function renderProcessing(job){
  if(!liveCreative)return;
  const desc=describeProcessing(job),versions=liveCreative.versions||[],items=versions.at(-1)?.data.items||[];
  $('processing-product').textContent=liveCreative.context.product_name;
  $('live-title').textContent=desc.title;$('live-status').textContent=desc.body;
  $('processing-panel').dataset.tone=desc.tone;
  document.querySelector('.processing-preview').hidden=false;document.querySelector('.review-stages').hidden=false;
  $('processing-back').href='/creative?task_id='+encodeURIComponent(liveTask);
  if(previewChannel>=items.length)previewChannel=0;
  const previewKey=[versions.at(-1)?.result_id,previewChannel,previewField].join('|');
  if(processingPreviewKey!==previewKey){
  processingPreviewKey=previewKey;
  $('preview-channels').innerHTML=items.map((item,i)=>`<button data-preview-channel="${i}" class="${previewChannel===i?'active':''}">${e(item.channel)}</button>`).join('');
  document.querySelectorAll('[data-preview]').forEach(n=>{n.classList.toggle('active',n.dataset.preview===previewField);n.setAttribute('aria-pressed',String(n.dataset.preview===previewField));});
  const text=items[previewChannel]?.[previewField];
  $('preview-content').textContent=typeof text==='string'?text:'暂无该项内容。';
  }
  for(let i=0;i<3;i++){const n=$('review-stage-'+i);n.classList.toggle('done',desc.step>i);n.classList.toggle('active',desc.step===i);if(desc.step===i)n.setAttribute('aria-current','step');else n.removeAttribute('aria-current');}
  $('processing-panel').hidden=state.view!=='workbench';
  if(!state.bundle){document.querySelectorAll('.view').forEach(n=>n.hidden=true);document.querySelectorAll('.nav-item[data-view]').forEach(n=>n.disabled=n.dataset.view!=='workbench');}
  document.querySelector('.system-status').textContent=job?.status==='failed'?'评估未完成':job?.status==='running'?'评估中':'方案已接收';
  $('delivery-a-btn').hidden=true;$('export-final-btn').hidden=true;
}
async function pollLive(){
  if(livePolling)return;livePolling=true;
  const deadline=Date.now()+600000;
  try{do{
    const record=await api.task(liveTask,'evaluation/state'),previousJob=liveJob;liveJob=record.job;state.liveEvents=record.events;state.liveUnavailable=false;
    $('error-banner').hidden=true;
    if(record.bundle){
      const replace=shouldReplaceLiveSelection(state.bundle,record.bundle);
      state.bundle=record.bundle;state.bundle.execution=record.job;state.source=null;
      if(replace)state.index=record.bundle.selected_index??record.bundle.records.length-1;
      if(replace||previousJob?.status!==liveJob?.status||previousJob?.stage!==liveJob?.stage)render();
    }
    if(record.job?.status!=='succeeded')renderProcessing(record.job);
    else if(record.bundle){$('processing-panel').hidden=true;showView(state.view);}
    flow.running=record.job?.status==='running';$('particle-stage').classList.toggle('running',flow.running);
    if(!record.job||record.job.status!=='running')break;
    if(Date.now()>deadline)throw new Error('评估仍在处理，请刷新状态继续查看。');
    await new Promise(resolve=>setTimeout(resolve,700));
  }while(true);}catch(ex){state.liveUnavailable=true;error(ex);$('delivery-a-btn').hidden=true;$('export-final-btn').hidden=true;
    if(liveCreative){renderProcessing(liveJob);$('live-title').textContent='暂时无法读取评估';$('live-status').textContent='点击刷新状态继续查看，本次方案已保留在下方。';}
  }finally{livePolling=false;}
}

function renderLiveEvents(events){$('view-events').innerHTML=`<section class="panel"><div class="view-lead"><div><h2>真实评估执行记录</h2><p>技术尝试与业务轮次分别记录，反馈绑定已交付版本。</p></div></div><div class="event-list">${events.map(v=>`<div class="event"><div class="event-time">${e(new Date(v.time).toLocaleTimeString('zh-CN'))}<br>第 ${v.round_no} 轮</div><span class="event-marker">${icon('activity')}</span><div class="event-content"><h3>${e(v.status)} · 尝试 ${v.attempt_count}</h3><p>${e(v.summary)}</p></div></div>`).join('')}</div></section>`;}
$('refresh-live').onclick=pollLive;
$('revise-live').onclick=async()=>{
  if(state.busy||!liveTask)return;
  state.busy=true;$('revise-live').disabled=true;$('delivery-a-btn').hidden=true;$('processing-panel').hidden=false;
  renderProcessing({status:'running',stage:'creative_revision'});$('view-workbench').hidden=true;
  try{
    let b=await api.task(liveTask,'creative/state');
    // A refresh can land between B save and C delivery. Resume the saved version.
    if(b.state==='returned'){
      if(b.job?.status!=='running')await api.task(liveTask,'creative/operations',{action:'revision',base_result_id:b.versions.at(-1).result_id});
      const deadline=Date.now()+600000;
      do{await new Promise(resolve=>setTimeout(resolve,700));b=await api.task(liveTask,'creative/state');if(Date.now()>deadline)throw new Error('修订仍在执行，请返回创意工作区查看。');}while(b.job?.status==='running');
      if(b.job?.status==='failed')throw new Error(b.job.error?.message||'创意修订失败');
    }else if(b.state!=='ready'&&b.state!=='pending')throw new Error('当前任务不需要创意修订，请刷新评估状态。');
    liveCreative=b;renderProcessing({status:'running',stage:'queued'});
    if(b.state==='ready')await api.task(liveTask,'evaluation/operations',{base_result_id:b.versions.at(-1).result_id});
    await pollLive();
  }catch(ex){error(ex);$('live-title').textContent='创意修订尚未完成';$('live-status').textContent=ex.message;}
  finally{state.busy=false;if(state.bundle)render();}
};

$('strategy-feedback').onclick=async()=>{try{download(liveTask+'-feedback-for-A.json',await api.task(liveTask,'evaluation/strategy-handoff'));}catch(ex){error(ex);}};
let deliveryPayload=null;
$('return-final').onclick=()=>{if(!state.bundle)return;state.index=state.bundle.selected_index??state.bundle.records.length-1;render();};
$('delivery-a-btn').onclick=async()=>{
  if(!state.bundle||state.busy)return;
  try{
    deliveryPayload=buildADelivery(state.bundle);
    $('delivery-heading').textContent='导出策略修改文档';
    $('delivery-from').textContent='发现策略问题';
    $('delivery-description').textContent=deliveryPayload.requirements.product_name+'：请先调整以下策略问题，再更新广告创意。';
    $('delivery-summary').innerHTML=deliveryPayload.feedback.map(f=>`<div class="strategy-change"><strong>${e(f.issue)}</strong><p>${e(f.suggestion)}</p></div>`).join('');
    $('delivery-note').hidden=true;$('confirm-delivery').disabled=false;$('delivery-dialog').showModal();
  }catch(ex){error(ex);}
};
$('close-delivery').onclick=$('cancel-delivery').onclick=()=>$('delivery-dialog').close();
$('confirm-delivery').onclick=async()=>{
  if(!deliveryPayload||$('confirm-delivery').disabled)return;
  $('confirm-delivery').disabled=true;
  try{
    if(liveTask){
      const latest=await api.task(liveTask,'evaluation/state');
      if(latest.job?.status!=='succeeded'||latest.bundle.final.evaluation.result_id!==deliveryPayload.evaluation.result_id||latest.bundle.final.decision!=='regenerate_strategy')throw new Error('评估结论已更新，请刷新后查看。');
      const handoff=await api.task(liveTask,'evaluation/strategy-handoff');
      if(handoff.evaluation.result_id!==deliveryPayload.evaluation.result_id)throw new Error('策略反馈已更新，请重新打开修改单。');
      deliveryPayload.strategy_handoff=handoff;
    }
    downloadBlob(deliveryPayload.task_id+'-策略修改单.docx',new Blob([buildStrategyDocument(deliveryPayload)],{type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}));$('delivery-dialog').close();toast('Word 策略修改单已下载');
  }catch(ex){$('delivery-note').textContent=ex.message;$('delivery-note').hidden=false;}finally{$('confirm-delivery').disabled=false;}
};

async function openDemo(){
  $('entry-panel').hidden=true;document.querySelector('.task-bar').hidden=false;$('run-btn').hidden=false;
  state.loading=false;await loadPreset();
}
$('show-demo').onclick=openDemo;
async function init(){
  state.loading=true;disableInputs(true);
  try{
    if(liveTask){
      try{const cached=JSON.parse(sessionStorage.getItem('zhice.evaluation.receipt.'+liveTask)||'null');
        if(cached?.task_id===liveTask&&Date.now()>=cached.received_at&&Date.now()-cached.received_at<120000&&cached.creative?.task_id===liveTask&&Array.isArray(cached.creative.data?.items)&&cached.creative.data.items.every(i=>i&&typeof i.channel==='string')){
          liveCreative={context:{product_name:cached.product_name},versions:[cached.creative]};renderProcessing({status:'loading'});
        }}catch{}
      await api.session();$('processing-panel').hidden=false;$('back-creative').href='/creative?task_id='+encodeURIComponent(liveTask);
      $('run-btn').hidden=true;$('import-btn').hidden=true;
      const upstream=await api.task(liveTask,'creative/state');
      liveCreative=upstream;renderProcessing({status:'loading'});
      sessionStorage.removeItem('zhice.evaluation.receipt.'+liveTask);
      await pollLive();return;
    }
    const meta=await api.metadata();
    $('product-select').innerHTML=meta.products.map(p=>`<option value="${p.id}">${e(p.name)}</option>`).join('');
    $('scenario-select').innerHTML=meta.scenarios.map(item=>`<option value="${e(item.id)}">${e(item.name)}</option>`).join('');
    if(meta.mode==='live_available'){
      await api.session();$('entry-panel').hidden=false;
      const history=await api.creativeHistory();
      $('entry-tasks').innerHTML=history.items.map(t=>`<a class="entry-task" href="${t.state==='ready'?'/creative?task_id=':'/evaluation/?task_id='}${encodeURIComponent(t.task_id)}"><strong>${e(t.product_name)}</strong><span>${({pending:'正在评估',passed:'查看结论',returned:'待修改',needs_strategy:'策略需调整',not_passed:'查看结论',ready:'继续创意'})[t.state]||'查看任务'} →</span></a>`).join('');
    }else await openDemo();
  }catch(ex){error(ex);if(liveTask){$('processing-panel').hidden=false;$('live-title').textContent='无法读取任务';$('live-status').textContent='请在原浏览器会话中打开，或从创意工作区重新进入。';}else $('entry-panel').hidden=false;}
  finally{state.loading=false;disableInputs(state.busy);}
}

init();
