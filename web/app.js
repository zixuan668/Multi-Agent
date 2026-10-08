const $ = (id) => document.getElementById(id);
const textElement = (tag, text, className) => {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
};

let latestResponse = null;
let latestTask = null;
let currentTaskId = null;
let formMode = "wizard";
let wizardStep = 0;
let periodMode = "duration";
const draftKey = "strategyRequirementDraft.v2";
const archiveKey = "strategyResultArchive.v1";
const draftFields = ["productName", "productDescription", "marketingGoal", "targetAudience", "budgetRaw", "budgetAmount", "currency", "durationDays", "startDate", "endDate", "specialRequirements"];
const textLimits = {productName: 100, productDescription: 5000, marketingGoal: 500, targetAudience: 1000, specialRequirements: 2000};
const stageNames = {queued: "排队中", pending: "排队中", generating: "生成策略草案", validating: "结构与约束校验", reviewing: "策略编辑与事实复核", retrying: "自动修复 / 技术重试", completed: "策略完成（尚未评估）", failed: "未完成", interrupted: "服务中断"};

const templates = [
  {id:"ai", name:"AI 学习产品", note:"订阅制学习助手", values:{productName:"知问 AI 学习助手", productDescription:"提供错题整理、知识点问答与学习计划功能，支持网页端和移动端使用。", marketingGoal:"让准备职业考试的在职学习者了解产品并开始试用", targetAudience:"准备职业资格考试、每天可用学习时间有限的在职人群", durationDays:"30", budgetRaw:"预算 2 万元", specialRequirements:"不承诺通过考试；不虚构提分数据；突出辅助学习而非替代教师"}},
  {id:"tea", name:"奶茶门店", note:"到店认知场景", values:{productName:"原味奶茶", productDescription:"门店提供热饮和冷饮，可选择无糖或半糖，支持到店自取。", marketingGoal:"让附近大学生了解门店产品并产生到店兴趣", targetAudience:"门店附近的大学生", durationDays:"30", budgetRaw:"五千块", specialRequirements:"不虚构优惠；不承诺健康或减肥效果"}},
  {id:"watch", name:"智能手表", note:"新品功能沟通", values:{productName:"跃动智能手表 S2", productDescription:"支持心率趋势记录、睡眠时长记录、运动模式记录和手机消息提醒，续航最长 7 天。", marketingGoal:"建立新品认知，帮助用户理解核心功能与适用场景", targetAudience:"有日常运动和健康记录习惯的城市上班族", durationDays:"21", budgetRaw:"3 万元人民币", specialRequirements:"健康数据仅作日常参考，不作医疗诊断；不得使用医疗效果承诺"}},
  {id:"beauty", name:"护肤产品", note:"成分与场景表达", values:{productName:"清润保湿精华", productDescription:"含透明质酸钠与泛醇，质地清爽，适合日常保湿使用；规格为 30ml。", marketingGoal:"让关注基础保湿的人群理解产品成分与使用场景", targetAudience:"关注日常保湿、偏好清爽肤感的年轻消费者", durationDays:"28", budgetRaw:"预算一万二", specialRequirements:"不使用治疗、修复疾病、永久改善等表达；不虚构临床数据"}},
  {id:"travel", name:"旅游产品", note:"目的地内容种草", values:{productName:"周末古镇轻旅行", productDescription:"提供两天一夜小团行程，包含往返交通、住宿和古镇讲解服务；出发地为杭州。", marketingGoal:"获取对周末短途旅行有兴趣的咨询线索", targetAudience:"杭州及周边希望周末短途放松的上班族", durationDays:"14", budgetRaw:"8000 元", specialRequirements:"价格以实际出发日期为准；不承诺零购物或固定天气；必须说明包含项目"}}
];

function setList(id, values, emptyText = "无") {
  const list = $(id);
  list.replaceChildren();
  (values?.length ? values : [emptyText]).forEach(value => list.appendChild(textElement("li", value)));
}

function rememberTask(id) {
  currentTaskId = id;
  try { sessionStorage.setItem("strategyTaskId", id); } catch { /* optional */ }
}

function renderTask(task) {
  latestTask = task;
  const order = ["generating", "validating", "reviewing", "completed"];
  const index = order.indexOf(task.stage);
  $("workflow").querySelectorAll("li").forEach((node, i) => {
    node.classList.toggle("active", i === index);
    node.classList.toggle("done", task.status === "completed" || (index >= 0 && i < index));
  });
  $("loadingTitle").textContent = stageNames[task.stage] || "处理中";
  $("loadingDescription").textContent = task.stage === "retrying" ? "正在依据具体校验问题修复；技术重试不会增加业务轮次。" : "只有通过结构、事实与约束检查的策略才会交付。";
  const notes = task.review_notes || [];
  $("reviewNotes").classList.toggle("hidden", !notes.length);
  setList("reviewNotesList", notes.map(item => item.message));
  renderDiagnostics(task);
  $("exportResult").disabled = false;
}

function diagnosticLocation(field = "") {
  const match = field.match(/channels\[(\d+)\](?:\.(\w+))?/);
  if (match) return `第 ${Number(match[1]) + 1} 个渠道${{content_direction:" · 内容与预算用途", reason:" · 推荐理由", allocated_amount:" · 分配金额", name:" · 渠道名称"}[match[2]] || ""}`;
  const point = field.match(/selling_points\[(\d+)\]/);
  if (point) return `第 ${Number(point[1]) + 1} 条卖点`;
  const labels = {target_audience:"用户画像", positioning:"产品定位", selling_points:"核心卖点", channels:"渠道方案", marketing_strategy:"推广策略", assumptions:"待验证假设", missing_information:"信息缺口", constraint_conflicts:"约束冲突"};
  const key = field.replace(/^(strategy_data|data)\./, "").split(/[.\[]/)[0];
  return labels[key] || "策略输出";
}

function diagnosticAdvice(issue) {
  if (/预算.*(?:用途|用于|具体执行)/.test(issue.message)) return "需要在对应渠道中写明这笔预算用于哪些执行动作，例如素材制作、发布准备或小范围测试。";
  if (issue.category === "fact") return "需要核对产品原始信息，修正缺少依据的表述，并保留可定位的原文引用。";
  if (issue.category === "structure") return "需要修正对应字段的格式或取值，再重新校验完整策略。";
  if (issue.category === "constraint") return "需要对照已填写的受众、预算、周期和特殊要求修正对应内容。";
  return "需要按上述原因完善对应内容，再重新校验。";
}

function groupDiagnosticIssues(issues) {
  const groups = new Map();
  (issues || []).forEach(issue => {
    const key = `${issue.category || "quality"}:${issue.message}:${issue.evidence || ""}`;
    if (!groups.has(key)) groups.set(key, {issue, locations:[], fields:[]});
    const group = groups.get(key);
    const location = diagnosticLocation(issue.field);
    if (!group.locations.includes(location)) group.locations.push(location);
    if (issue.field && !group.fields.includes(issue.field)) group.fields.push(issue.field);
  });
  return [...groups.values()];
}

function renderDiagnostics(task) {
  const records = task.attempt_diagnostics || [];
  const host = $("diagnostics");
  const previouslyHidden = host.classList.contains("hidden");
  host.classList.toggle("hidden", !records.length);
  $("diagnosticItems").replaceChildren();
  if (!records.length) return;
  const failed = task.status === "failed";
  if (previouslyHidden) host.open = failed;
  const last = records[records.length - 1];
  const remaining = groupDiagnosticIssues(last.issues).length;
  $("diagnosticSummary").textContent = task.status === "completed" ? `${records.length} 次处理 · 最终校验通过` : `${records.length} 次处理${remaining ? ` · 最后一次发现 ${remaining} 类问题` : ""}`;
  $("diagnosticConclusion").textContent = failed ? "自动修复后仍未通过校验，本次未生成可交付策略。下面按处理顺序展示每次发现的问题；你的需求已保留。" : task.status === "completed" ? "最终策略已通过校验。之前出现的问题和修复后的检查结果保留如下，供你回看。" : "以下是已完成的检查记录，后续结果会继续更新。";
  records.forEach((record, index) => {
    const groups = groupDiagnosticIssues(record.issues);
    const passed = !record.error_code;
    const section = textElement("section", "", `diagnostic-attempt ${passed ? "passed" : "needs-fix"}`);
    const header = textElement("div", "", "diagnostic-attempt-header");
    const title = textElement("div", "", "diagnostic-attempt-title");
    title.append(textElement("span", String(record.attempt_count), "diagnostic-number"), textElement("h3", index === 0 ? "首次生成 · 校验结果" : `第 ${index} 次自动修复 · 校验结果`));
    header.append(title, textElement("span", passed ? "校验通过" : ({OUTPUT_INVALID:"未通过校验", MODEL_TIMEOUT:"模型响应超时", MODEL_UNAVAILABLE:"模型服务不可用", MODEL_AUTH_FAILED:"模型鉴权失败"}[record.error_code] || "处理失败"), `diagnostic-outcome ${passed ? "success" : "warning"}`));
    section.appendChild(header);
    if (groups.length) groups.forEach(({issue, locations, fields}) => {
      const card = textElement("div", "", "diagnostic-issue");
      const label = {fact:"事实依据", constraint:"需求约束", structure:"输出格式", quality:"内容完整性"}[issue.category] || "内容检查";
      card.append(textElement("span", label, "diagnostic-category"), textElement("h4", issue.message));
      const places = textElement("div", "", "diagnostic-locations");
      locations.forEach(location => places.appendChild(textElement("span", location)));
      card.append(places, textElement("p", diagnosticAdvice(issue), "diagnostic-advice"));
      if (issue.evidence) card.appendChild(textElement("blockquote", issue.evidence, "diagnostic-evidence"));
      if (fields.length) {
        const technical = textElement("details", "", "diagnostic-technical");
        technical.append(textElement("summary", "字段位置"), textElement("code", fields.join("\n")));
        card.appendChild(technical);
      }
      section.appendChild(card);
    });
    else section.appendChild(textElement("p", passed ? "本次检查未发现阻断问题。" : "本次模型调用未完成，没有可展示的字段级校验结果。", "diagnostic-advice"));
    const footer = textElement("p", "", "diagnostic-attempt-footer");
    const milliseconds = Number(record.duration_ms);
    const duration = Number.isFinite(milliseconds) ? `本次耗时 ${(milliseconds / 1000).toFixed(1)} 秒` : "";
    footer.textContent = [index < records.length - 1 ? "随后已重新处理，结果见下一条" : passed ? "本次检查通过" : failed ? "本次处理已结束，问题仍未解决" : "等待后续处理", duration].filter(Boolean).join(" · ");
    section.appendChild(footer);
    $("diagnosticItems").appendChild(section);
  });
}

function showFailure(message, code, queryOnly = false) {
  $("emptyState").classList.add("hidden");
  $("loadingState").classList.add("hidden");
  $("failureState").classList.remove("hidden");
  $("failureTitle").textContent = message;
  $("failureAdvice").textContent = queryOnly ? "查询连接中断不等于生成失败。请恢复查询原任务，避免重复消耗模型额度。" : ({OUTPUT_INVALID:"输入已保留。请查看校验记录；不合格输出不会作为成功结果交付。", MODEL_AUTH_FAILED:"请检查服务端 .env 的密钥与模型权限，重启服务后再试。", MODEL_TIMEOUT:"模型生成与复核超时，可稍后重新提交。", ACCESS_DENIED:"服务重启或会话已失效；本地归档仍可查看，生成任务需重新提交。"}[code] || "输入已保留，请按提示检查后重试。");
  $("resumeTask").classList.toggle("hidden", !queryOnly || !currentTaskId);
}

async function pollTask(id, restoreInput = false) {
  while (true) {
    const query = await fetch(`/api/tasks/${encodeURIComponent(id)}`, {cache:"no-store"});
    const task = await query.json();
    if (!query.ok) { const error = new Error(task.error?.message || "任务查询失败"); error.code = task.error?.code; throw error; }
    if (restoreInput) { restoreRequirements(task.requirements); restoreInput = false; }
    renderTask(task);
    if (task.status === "failed") { showFailure(task.error?.message || "任务未完成", task.error?.code); break; }
    if (task.status === "completed") { renderResult(task.result); archiveTask(task); break; }
    await new Promise(resolve => setTimeout(resolve, 700));
  }
}

function setModeBadge(health) {
  const badge = $("modelBadge");
  if (health.real_model_configured) {
    badge.textContent = health.connection_verified ? "真实模型 · 已验证" : "真实模型已配置 · 待验证";
    badge.classList.remove("demo");
  } else { badge.textContent = "离线策略引擎"; badge.classList.add("demo"); }
}

async function loadHealth() {
  try { const response = await fetch("/api/health", {cache:"no-store"}); setModeBadge(await response.json()); }
  catch { $("modelBadge").textContent = "服务状态未知"; }
}

function renderTemplates() {
  const list = $("templateList");
  templates.forEach(template => {
    const button = textElement("button", "", "template-card");
    button.type = "button";
    button.dataset.template = template.id;
    button.append(textElement("strong", template.name), textElement("small", template.note));
    list.appendChild(button);
  });
}

function fillTemplate(id) {
  const template = templates.find(item => item.id === id);
  if (!template) return;
  draftFields.forEach(field => { if (field !== "currency") $(field).value = ""; });
  $("currency").value = "CNY";
  Object.entries(template.values).forEach(([key, value]) => { $(key).value = value; });
  parseBudgetInput();
  periodMode = "duration";
  updateFormUi();
  saveDraft();
  $("templatePanel").classList.add("hidden");
  $("toggleTemplates").setAttribute("aria-expanded", "false");
}

function draftValues() {
  return {...Object.fromEntries(draftFields.map(id => [id, $(id).value])), formMode, wizardStep, periodMode};
}

function saveDraft() {
  try {
    localStorage.setItem(draftKey, JSON.stringify(draftValues()));
    $("draftStatus").textContent = `草稿已保存 · ${new Date().toLocaleTimeString("zh-CN", {hour:"2-digit", minute:"2-digit"})}`;
  } catch { $("draftStatus").textContent = "浏览器未允许保存草稿"; }
}

function restoreDraft() {
  try {
    const draft = JSON.parse(localStorage.getItem(draftKey) || "null");
    if (!draft || typeof draft !== "object") return;
    draftFields.forEach(id => { if (typeof draft[id] === "string") $(id).value = draft[id]; });
    formMode = draft.formMode === "single" ? "single" : "wizard";
    wizardStep = Number.isInteger(draft.wizardStep) ? Math.min(3, Math.max(0, draft.wizardStep)) : 0;
    periodMode = draft.periodMode === "dates" ? "dates" : "duration";
    $("draftStatus").textContent = "已恢复上次需求草稿";
  } catch { /* corrupted storage does not block use */ }
}

function clearDraft() {
  draftFields.forEach(id => { $(id).value = id === "currency" ? "CNY" : ""; });
  try { localStorage.removeItem(draftKey); } catch { /* ignore */ }
  wizardStep = 0; periodMode = "duration";
  clearFieldErrors(); updateFormUi();
  $("draftStatus").textContent = "草稿已清空";
}

function restoreRequirements(r) {
  const values = {productName:r.product_name, productDescription:r.product_description, marketingGoal:r.marketing_goal, targetAudience:r.target_audience, budgetRaw:r.budget_raw, budgetAmount:r.budget?.amount, currency:r.budget?.currency || "CNY", durationDays:r.campaign_period?.duration_days, startDate:r.campaign_period?.start_date, endDate:r.campaign_period?.end_date, specialRequirements:r.special_requirements};
  Object.entries(values).forEach(([key, value]) => { $(key).value = value ?? ""; });
  periodMode = r.campaign_period?.start_date ? "dates" : "duration";
  updateFormUi();
}

function optionalText(id) { const value = $(id).value.trim(); return value || null; }

function chineseNumber(text) {
  const digits = {零:0,〇:0,一:1,二:2,两:2,三:3,四:4,五:5,六:6,七:7,八:8,九:9};
  if (/^[零〇一二两三四五六七八九]+$/.test(text)) return Number([...text].map(char => digits[char]).join(""));
  let total = 0, section = 0, number = 0;
  const units = {十:10,百:100,千:1000,万:10000,亿:100000000};
  for (const char of text) {
    if (char in digits) number = digits[char];
    else if (char in units) {
      const unit = units[char];
      if (unit >= 10000) { section = (section + (number || 0)) * unit; total += section; section = 0; }
      else section += (number || 1) * unit;
      number = 0;
    } else return null;
  }
  return total + section + number;
}

function parseBudget(raw) {
  const compact = raw.trim().replace(/[，,\s]/g, "").replace(/预算|大约|约|左右|以内|不超过/g, "");
  if (!compact) return null;
  const currency = /美元|USD/i.test(compact) ? "USD" : /欧元|EUR/i.test(compact) ? "EUR" : "CNY";
  let match = compact.match(/(\d+(?:\.\d+)?)\s*(亿|万|千|k|K)?/);
  let amount;
  if (match) amount = Number(match[1]) * ({亿:100000000, 万:10000, 千:1000, k:1000, K:1000}[match[2]] || 1);
  else { match = compact.match(/[零〇一二两三四五六七八九十百千万亿]+/); amount = match ? chineseNumber(match[0]) : null; }
  if (!Number.isFinite(amount) || amount < 0 || amount > 100000000 || Math.round(amount * 100) !== amount * 100) return {error:"预算无法可靠解析，请填写 0–1 亿且最多两位小数的金额。"};
  return {amount, currency};
}

function parseBudgetInput() {
  const raw = $("budgetRaw").value;
  const hint = $("budgetParseHint");
  if (!raw.trim()) { hint.textContent = "输入后会安全解析，无法确认时不会猜测。"; hint.className = "parse-hint"; return null; }
  const parsed = parseBudget(raw);
  if (!parsed || parsed.error) { hint.textContent = parsed?.error || "无法解析预算，请更正。"; hint.className = "parse-hint error"; return parsed; }
  $("budgetAmount").value = parsed.amount;
  $("currency").value = parsed.currency;
  hint.textContent = `已解析为 ${parsed.amount.toLocaleString("zh-CN")} ${parsed.currency}，请确认。`;
  hint.className = "parse-hint success";
  return parsed;
}

function buildPayload() {
  const budgetText = $("budgetAmount").value.trim();
  const durationText = $("durationDays").value.trim();
  const campaign = periodMode === "dates" ? (($("startDate").value || $("endDate").value) ? {start_date:$("startDate").value, end_date:$("endDate").value} : null) : (durationText ? {duration_days:Number(durationText)} : null);
  return {product_name:$("productName").value.trim(), product_description:$("productDescription").value.trim(), marketing_goal:$("marketingGoal").value.trim(), target_audience:optionalText("targetAudience"), budget:budgetText ? {amount:Number(budgetText), currency:$("currency").value} : null, campaign_period:campaign, special_requirements:optionalText("specialRequirements"), budget_raw:optionalText("budgetRaw") || (budgetText ? `${budgetText} ${$("currency").value}` : null)};
}

function clearFieldErrors() {
  ["productName", "productDescription", "marketingGoal"].forEach(id => { $(id).removeAttribute("aria-invalid"); $(`${id}Error`).textContent = ""; });
  $("budgetError").textContent = ""; $("periodError").textContent = "";
}

function validateForm(scopeStep = null) {
  clearFieldErrors();
  const errors = [];
  [{id:"productName",step:0,label:"产品名称"},{id:"productDescription",step:0,label:"产品介绍"},{id:"marketingGoal",step:1,label:"营销目标"}].forEach(field => {
    if (scopeStep !== null && field.step !== scopeStep) return;
    if (!$(field.id).value.trim()) { $(`${field.id}Error`).textContent = `${field.label}不能为空。`; $(field.id).setAttribute("aria-invalid", "true"); errors.push({step:field.step,node:$(field.id)}); }
  });
  if (scopeStep === null || scopeStep === 2) {
    const raw = $("budgetRaw").value.trim(), amount = $("budgetAmount").value.trim();
    const parsed = raw ? parseBudget(raw) : null;
    if (raw && (!parsed || parsed.error) && !amount) { $("budgetError").textContent = "预算原始表达无法解析，请填写明确金额。"; errors.push({step:2,node:$("budgetRaw")}); }
    if (amount && (!Number.isFinite(Number(amount)) || Number(amount) < 0 || Number(amount) > 100000000 || !/^\d+(?:\.\d{1,2})?$/.test(amount))) { $("budgetError").textContent = "金额须为 0–1 亿，最多两位小数。"; errors.push({step:2,node:$("budgetAmount")}); }
    if (periodMode === "duration" && $("durationDays").value && (!Number.isInteger(Number($("durationDays").value)) || Number($("durationDays").value) < 1 || Number($("durationDays").value) > 365)) { $("periodError").textContent = "持续天数须为 1–365 的整数。"; errors.push({step:2,node:$("durationDays")}); }
    if (periodMode === "dates") {
      const start = $("startDate").value, end = $("endDate").value;
      if ((start && !end) || (!start && end)) { $("periodError").textContent = "开始和结束日期必须同时填写。"; errors.push({step:2,node:$("startDate")}); }
      else if (start && end && end < start) { $("periodError").textContent = "结束日期不能早于开始日期。"; errors.push({step:2,node:$("endDate")}); }
    }
  }
  return errors;
}

function updateCounters() {
  Object.entries(textLimits).forEach(([id, limit]) => {
    const count = $(id).value.length;
    const node = document.querySelector(`[data-counter="${id}"]`);
    if (node) { node.textContent = `${count}/${limit}`; node.style.color = count / limit > .9 ? "var(--accent-dark)" : ""; }
  });
  const done = ["productName", "productDescription", "marketingGoal"].filter(id => $(id).value.trim()).length;
  $("completionText").textContent = `必填项 ${done}/3`;
  $("completionBar").style.width = `${done / 3 * 100}%`;
}

function updateBriefSummary() {
  const period = periodMode === "dates" ? ($("startDate").value && $("endDate").value ? `${$("startDate").value} 至 ${$("endDate").value}` : "周期待定") : ($("durationDays").value ? `${$("durationDays").value} 天` : "周期待定");
  const items = [["产品", $("productName").value.trim() || "未填写"], ["目标用户", $("targetAudience").value.trim() || "由智能体提出候选"], ["预算 / 周期", `${$("budgetAmount").value ? `${Number($("budgetAmount").value).toLocaleString("zh-CN")} ${$("currency").value}` : "预算待定"} · ${period}`]];
  $("briefSummary").replaceChildren(...items.map(([label,value]) => { const node = document.createElement("div"); node.append(textElement("span",label),textElement("strong",value)); return node; }));
}

function syncFormMode() {
  $("strategyForm").classList.toggle("wizard-mode", formMode === "wizard");
  document.querySelectorAll("[data-form-mode]").forEach(button => button.classList.toggle("active", button.dataset.formMode === formMode));
  $("wizardProgress").classList.toggle("hidden", formMode !== "wizard");
  $("wizardPrev").classList.toggle("hidden", formMode !== "wizard");
  $("wizardNext").classList.toggle("hidden", formMode !== "wizard" || wizardStep === 3);
  $("submitButton").classList.toggle("hidden", formMode === "wizard" && wizardStep !== 3);
  $("wizardPrev").disabled = wizardStep === 0;
  document.querySelectorAll(".form-section").forEach(section => section.classList.toggle("active", Number(section.dataset.step) === wizardStep));
  $("wizardProgress").replaceChildren(...[0,1,2,3].map(index => textElement("span", `0${index+1}`, `wizard-dot${index===wizardStep?" active":""}${index<wizardStep?" done":""}`)));
}

function syncPeriodMode() {
  document.querySelectorAll("[data-period-mode]").forEach(button => button.classList.toggle("active", button.dataset.periodMode === periodMode));
  document.querySelectorAll("[data-period-panel]").forEach(node => node.classList.toggle("hidden", node.dataset.periodPanel !== periodMode));
  if (periodMode === "dates") $("durationDays").value = "";
  else { $("startDate").value = ""; $("endDate").value = ""; }
}

function updateFormUi() { updateCounters(); updateBriefSummary(); syncPeriodMode(); syncFormMode(); }

function formattedStrategy(response = latestResponse) {
  if (!response?.data) return "";
  const d = response.data;
  return [`${$("productName").value.trim() || "产品"}｜营销策略`,"","一、策略定位",d.positioning,"","二、目标用户",d.target_audience.segment,`依据：${d.target_audience.basis}`,...d.target_audience.needs.map(v=>`- 需求：${v}`),...d.target_audience.pain_points.map(v=>`- 痛点：${v}`),"","三、核心卖点",...d.selling_points.flatMap((p,i)=>[`${i+1}. ${p.claim}`,`   依据原文：${p.source_quote}`]),"","四、渠道策略",...d.channels.flatMap((c,i)=>[`${i+1}. ${c.name}${c.allocated_amount==null?"":`｜${c.allocated_amount} ${latestTask?.requirements?.budget?.currency||""}`}`,`   为什么：${c.reason}`,`   发布什么：${c.content_direction}`]),"","五、推广策略",`主题：${d.marketing_strategy.theme}`,...d.marketing_strategy.content_directions.map(v=>`- 内容方向：${v}`),...d.marketing_strategy.promotion_methods.map(v=>`- 执行动作：${v}`),"","六、发布前需核实",...(d.assumptions.length?d.assumptions.map(v=>`- 假设：${v}`):["- 无待验证假设"]),...(d.missing_information.length?d.missing_information.map(v=>`- 信息缺口：${v}`):["- 无信息缺口"]),...d.constraint_conflicts.map(v=>`- 约束冲突：${v}`)].join("\n");
}

function renderResult(response) {
  latestResponse = response;
  const data = response.data;
  selectResultTab("strategyOverview");
  const amounts = data.channels.filter(channel => channel.allocated_amount != null);
  const currency = latestTask?.requirements?.budget?.currency || "";
  const allocated = amounts.reduce((sum, channel) => sum + channel.allocated_amount, 0);
  const total = latestTask?.requirements?.budget?.amount;
  $("summaryChannels").textContent = `${data.channels.length} 个`;
  $("summaryBudget").textContent = amounts.length ? `${allocated.toLocaleString("zh-CN")} ${currency}` : "尚未分配";
  $("summaryMissing").textContent = `${data.missing_information.length} 项`;
  if (latestTask?.config_snapshot?.provider === "compatible") setModeBadge({real_model_configured:true,connection_verified:true});
  $("positioning").textContent = data.positioning;
  $("audienceSegment").textContent = data.target_audience.segment;
  $("audienceAge").textContent = data.target_audience.age_range || "未提供 / 待验证";
  $("audienceOccupation").textContent = data.target_audience.occupation || "未提供 / 待验证";
  $("audienceBasis").textContent = data.target_audience.basis;
  setList("audienceNeeds",data.target_audience.needs); setList("audiencePainPoints",data.target_audience.pain_points);
  $("strategyTheme").textContent = data.marketing_strategy.theme;
  setList("contentDirections",data.marketing_strategy.content_directions); setList("promotionMethods",data.marketing_strategy.promotion_methods);
  setList("assumptions",data.assumptions); setList("missingInformation",data.missing_information); setList("constraintConflicts",data.constraint_conflicts);
  $("conflictCard").classList.toggle("hidden", !data.constraint_conflicts.length);

  $("sellingPoints").replaceChildren();
  data.selling_points.forEach((point,index) => {
    const card = textElement("div","","list-item"), title = textElement("strong",`${index+1}. ${point.claim}`);
    title.appendChild(textElement("span","事实","fact-badge"));
    const quote = textElement("p",`原文依据：“${point.source_quote}”`,"source-quote");
    quote.tabIndex=0; quote.setAttribute("role","button"); quote.addEventListener("click",()=>locateSource(point.source_quote)); quote.addEventListener("keydown",event=>{if(["Enter"," "].includes(event.key))locateSource(point.source_quote);});
    card.append(title,quote); $("sellingPoints").appendChild(card);
  });

  $("channels").replaceChildren();
  data.channels.forEach((channel,index) => {
    const card=textElement("div","","list-item"), title=textElement("strong",`${index+1}. ${channel.name}`);
    title.appendChild(textElement("span","策略判断","inference-badge"));
    const budget=channel.allocated_amount==null?"预算：待预算明确后分配":`预算：${channel.allocated_amount.toLocaleString("zh-CN")} ${currency}`;
    card.append(title,textElement("p",`为什么适合：${channel.reason}`),textElement("p",`发布什么：${channel.content_direction}`),textElement("p",budget));
    if(channel.allocated_amount!=null&&total>0){const track=textElement("div","","budget-track"),fill=textElement("span","","budget-fill");fill.style.width=`${Math.min(100,channel.allocated_amount/total*100)}%`;track.appendChild(fill);card.appendChild(track);}
    $("channels").appendChild(card);
  });
  const budgetSummary=$("budgetSummary"); budgetSummary.classList.toggle("hidden",total==null);
  if(total!=null){const cells=[["已分配",`${allocated.toLocaleString("zh-CN")} ${currency}`],["总预算",`${total.toLocaleString("zh-CN")} ${currency}`],["剩余",`${Math.max(0,total-allocated).toLocaleString("zh-CN")} ${currency}`]];budgetSummary.replaceChildren(...cells.map(([label,value])=>{const node=document.createElement("div");node.append(textElement("span",label),textElement("strong",value));return node;}));}
  $("rawJson").textContent=JSON.stringify(response,null,2);
  $("emptyState").classList.add("hidden"); $("loadingState").classList.add("hidden"); $("failureState").classList.add("hidden"); $("resultContent").classList.remove("hidden");
  ["copyResult","exportStrategy","exportResult","exportCreative"].forEach(id=>{$(id).disabled=false;});
}

function locateSource(quote) {
  const target=["productDescription","marketingGoal","productName","targetAudience","specialRequirements"].map(id=>$(id)).find(node=>node.value.includes(quote))||$("productDescription");
  formMode="single"; syncFormMode(); target.scrollIntoView({behavior:"smooth",block:"center"}); target.focus(); target.classList.remove("source-flash"); requestAnimationFrame(()=>target.classList.add("source-flash"));
  if(target.value.includes(quote)){const start=target.value.indexOf(quote);target.setSelectionRange(start,start+quote.length);}
}

function selectResultTab(id) {
  document.querySelectorAll("[data-result-tab]").forEach(button=>{const selected=button.dataset.resultTab===id;button.setAttribute("aria-selected",String(selected));button.tabIndex=selected?0:-1;$(button.dataset.resultTab).classList.toggle("hidden",!selected);});
}

function setLoading(loading) {
  $("submitButton").disabled=loading; $("submitButton").querySelector("span:first-child").textContent=loading?"智能体正在生成…":"生成营销策略";
  if(!loading)return;
  latestResponse=null;latestTask=null;["copyResult","exportStrategy","exportResult","exportCreative"].forEach(id=>{$(id).disabled=true;});
  $("emptyState").classList.add("hidden");$("resultContent").classList.add("hidden");$("loadingState").classList.remove("hidden");["failureState","reviewNotes","diagnostics"].forEach(id=>$(id).classList.add("hidden"));$("workflow").querySelectorAll("li").forEach(node=>node.classList.remove("active","done"));
}

async function submitForm(event) {
  event.preventDefault(); $("formMessage").textContent=""; parseBudgetInput();
  const errors=validateForm();
  if(errors.length){wizardStep=errors[0].step;syncFormMode();errors[0].node.focus();$("formMessage").textContent=`有 ${errors.length} 项需要修改，已定位到第一项。`;return;}
  saveDraft();setLoading(true);currentTaskId=null;
  try{
    const session=await fetch("/api/session",{cache:"no-store"});if(!session.ok)throw new Error("无法建立任务会话");
    const response=await fetch("/api/tasks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(buildPayload())});const result=await response.json();
    if(!response.ok||!result.task_id){const error=new Error(result.error?.message||"策略生成失败");error.code=result.error?.code;throw error;}
    rememberTask(result.task_id);$("resultPanel").scrollIntoView({behavior:"smooth",block:"start"});await pollTask(result.task_id);
  }catch(error){showFailure(error.message,error.code,Boolean(currentTaskId)&&!error.code);}finally{setLoading(false);}
}

function downloadTask(suffix="") {if(!latestTask)return;const anchor=document.createElement("a");anchor.href=`/api/tasks/${encodeURIComponent(latestTask.task_id)}${suffix}?download=1`;anchor.download=`${latestTask.task_id}${suffix.replaceAll("/","-")||"-strategy-task"}.json`;document.body.appendChild(anchor);anchor.click();anchor.remove();}
function exportStrategy(){if(!latestResponse)return;const bom=new Uint8Array([0xEF,0xBB,0xBF]),blob=new Blob([bom,JSON.stringify(latestResponse,null,2)],{type:"application/json;charset=utf-8"}),anchor=document.createElement("a");anchor.href=URL.createObjectURL(blob);const safeName=($("productName").value.trim()||"strategy").replace(/[\\/:*?"<>|]/g,"-");anchor.download=`${safeName}-${new Date().toISOString().slice(0,10)}.json`;document.body.appendChild(anchor);anchor.click();anchor.remove();URL.revokeObjectURL(anchor.href);}
async function exportCreative(){if(!latestTask)return;try{const response=await fetch(`/api/tasks/${encodeURIComponent(latestTask.task_id)}/creative-request`,{cache:"no-store"}),payload=await response.json();if(!response.ok)throw new Error(payload.error?.message||"下游请求校验失败");downloadTask("/creative-request");}catch(error){$("formMessage").textContent=error.message;}}
async function writeClipboard(text,button){try{await navigator.clipboard.writeText(text);}catch{$("formMessage").textContent="浏览器未允许复制，请使用导出功能。";return;}const original=button.textContent;button.textContent="已复制";setTimeout(()=>{button.textContent=original;},1200);}

function archiveTask(task){try{const archive=JSON.parse(localStorage.getItem(archiveKey)||"[]"),next=[task,...archive.filter(item=>item.task_id!==task.task_id)].slice(0,20);localStorage.setItem(archiveKey,JSON.stringify(next));renderRecentTasks();}catch{/* optional */}}
function renderRecentTasks(){const host=$("recentTasks");host.replaceChildren(textElement("h3","最近结果 · 本地归档"));try{const archive=JSON.parse(localStorage.getItem(archiveKey)||"[]").slice(0,4);if(!archive.length){host.appendChild(textElement("p","生成后的结果会保存在这里。","muted"));return;}archive.forEach(task=>{const button=textElement("button","","recent-task");button.type="button";button.dataset.archiveId=task.task_id;button.append(textElement("strong",task.requirements.product_name),textElement("time",new Date(task.created_at).toLocaleDateString("zh-CN")),textElement("span",`版本 ${task.result?.version||1} · ${task.result?.data?.channels?.length||0} 个渠道`));host.appendChild(button);});}catch{host.appendChild(textElement("p","本地归档暂不可用。","muted"));}}
function openArchived(id){try{const task=JSON.parse(localStorage.getItem(archiveKey)||"[]").find(item=>item.task_id===id);if(!task)return;restoreRequirements(task.requirements);renderTask(task);renderResult(task.result);$("resultPanel").scrollIntoView({behavior:"smooth",block:"start"});}catch{/* ignore */}}
async function resumeTask(){if(!currentTaskId)return;setLoading(true);try{await pollTask(currentTaskId,!$("productName").value);}catch(error){showFailure(error.message,error.code,!error.code);}finally{setLoading(false);}}

renderTemplates();restoreDraft();updateFormUi();renderRecentTasks();loadHealth();
$("strategyForm").addEventListener("submit",submitForm);
$("saveDraft").addEventListener("click",saveDraft);$("clearDraft").addEventListener("click",clearDraft);
$("toggleTemplates").addEventListener("click",()=>{const panel=$("templatePanel");panel.classList.toggle("hidden");$("toggleTemplates").setAttribute("aria-expanded",String(!panel.classList.contains("hidden")));});
$("templateList").addEventListener("click",event=>{const button=event.target.closest("[data-template]");if(button)fillTemplate(button.dataset.template);});
$("recentTasks").addEventListener("click",event=>{const button=event.target.closest("[data-archive-id]");if(button)openArchived(button.dataset.archiveId);});
$("budgetRaw").addEventListener("blur",()=>{parseBudgetInput();updateBriefSummary();});
document.querySelectorAll("[data-form-mode]").forEach(button=>button.addEventListener("click",()=>{formMode=button.dataset.formMode;syncFormMode();saveDraft();}));
document.querySelectorAll("[data-period-mode]").forEach(button=>button.addEventListener("click",()=>{periodMode=button.dataset.periodMode;syncPeriodMode();updateBriefSummary();}));
document.querySelectorAll("[data-days]").forEach(button=>button.addEventListener("click",()=>{$("durationDays").value=button.dataset.days;updateBriefSummary();saveDraft();}));
document.querySelectorAll("[data-goal]").forEach(button=>button.addEventListener("click",()=>{$("marketingGoal").value=button.dataset.goal;updateFormUi();}));
$("wizardPrev").addEventListener("click",()=>{wizardStep=Math.max(0,wizardStep-1);syncFormMode();});
$("wizardNext").addEventListener("click",()=>{const errors=validateForm(wizardStep);if(errors.length){errors[0].node.focus();$("formMessage").textContent="请先完成本步中的必要信息。";return;}$("formMessage").textContent="";wizardStep=Math.min(3,wizardStep+1);updateFormUi();});
$("copyResult").addEventListener("click",event=>writeClipboard(formattedStrategy(),event.currentTarget));
$("exportStrategy").addEventListener("click",exportStrategy);$("exportResult").addEventListener("click",()=>downloadTask());$("exportCreative").addEventListener("click",exportCreative);$("resumeTask").addEventListener("click",resumeTask);$("retryTask").addEventListener("click",()=>$("strategyForm").requestSubmit());
document.querySelectorAll("[data-copy-module]").forEach(button=>button.addEventListener("click",()=>{if(!latestResponse)return;const d=latestResponse.data,text=button.dataset.copyModule==="selling"?d.selling_points.map((p,i)=>`${i+1}. ${p.claim}\n依据：${p.source_quote}`).join("\n"):d.channels.map((c,i)=>`${i+1}. ${c.name}\n为什么：${c.reason}\n发布什么：${c.content_direction}`).join("\n\n");writeClipboard(text,button);}));
document.querySelectorAll("[data-result-tab]").forEach((button,index,buttons)=>{button.addEventListener("click",()=>selectResultTab(button.dataset.resultTab));button.addEventListener("keydown",event=>{const moves={ArrowRight:(index+1)%buttons.length,ArrowLeft:(index+buttons.length-1)%buttons.length,Home:0,End:buttons.length-1};if(!(event.key in moves))return;event.preventDefault();const next=buttons[moves[event.key]];selectResultTab(next.dataset.resultTab);next.focus();});});
let draftTimer;draftFields.forEach(id=>$(id).addEventListener("input",()=>{clearTimeout(draftTimer);updateCounters();updateBriefSummary();$("draftStatus").textContent="正在保存草稿…";draftTimer=setTimeout(saveDraft,350);}));
try{currentTaskId=sessionStorage.getItem("strategyTaskId");}catch{/* optional */}if(currentTaskId)resumeTask();
