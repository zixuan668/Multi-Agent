/* Pure intake mapping. Public requirements schema stays at v1.0. */
const StrategyBrief = (() => {
  const fields = ["productName", "productCategory", "productDescription", "productFeatures", "priceStatus", "priceInfo", "salesScope", "salesRegion", "purchaseStatus", "purchaseEntry", "primaryGoal", "marketingGoal", "desiredAction", "actionDetail", "audienceMode", "targetAudience", "marketingProblem", "problemDetail", "budgetMode", "budgetRaw", "budgetAmount", "currency", "durationDays", "startDate", "endDate", "channelsState", "existingChannels", "materialsState", "availableMaterials", "teamState", "teamResources", "constraintStatus", "specialRequirements", "brandStyle"];
  const defaults = Object.fromEntries(fields.map(id => [id, id === "currency" ? "CNY" : ["priceStatus", "purchaseStatus"].includes(id) ? "unknown" : ""]));
  const steps = ["产品情况", "目标与人群", "执行条件", "限制与确认"];
  const marker = "\n\n【智策需求补充 v1】\n";
  const text = (values, id) => String(values[id] ?? "").trim();
  function pack(base, detail) { return `${base}${marker}${JSON.stringify(detail)}`; }
  function unpack(value) {
    const raw = typeof value === "string" ? value : "";
    const index = raw.lastIndexOf(marker);
    if (index < 0) return {base:raw, detail:null};
    try {
      const detail = JSON.parse(raw.slice(index + marker.length));
      if (!detail || typeof detail !== "object" || Array.isArray(detail) || detail.formVersion !== 1) return {base:raw, detail:null};
      return {base:raw.slice(0, index), detail};
    } catch { return {base:raw, detail:null}; }
  }
  function pick(values, ids) { return Object.fromEntries(ids.map(id => [id, text(values, id)])); }
  const productIds = fields.slice(1, 10);
  const goalIds = ["primaryGoal", "marketingGoal", "desiredAction", "actionDetail"];
  const contextIds = ["audienceMode", "marketingProblem", "problemDetail", "channelsState", "existingChannels", "materialsState", "availableMaterials", "teamState", "teamResources", "constraintStatus", "brandStyle"];
  function payload(values) {
    const v = {...defaults, ...values};
    const facts = `${text(v,"productDescription")}\n\n已确认的产品特点：\n${text(v,"productFeatures")}`;
    const product = {formVersion:1, ...pick(v, productIds), priceInfo:v.priceStatus === "known" ? text(v,"priceInfo") : "", purchaseEntry:v.purchaseStatus === "known" ? text(v,"purchaseEntry") : ""};
    const goal = v.primaryGoal === "其他" ? text(v,"marketingGoal") : v.primaryGoal;
    const action = v.desiredAction === "其他" ? text(v,"actionDetail") : v.desiredAction;
    const goalText = [`首要目标：${goal}`, `希望用户采取的行动：${action}`, v.marketingGoal && v.primaryGoal !== "其他" ? `目标补充：${text(v,"marketingGoal")}` : ""].filter(Boolean).join("\n");
    const context = {formVersion:1, ...pick(v, contextIds), existingChannels:v.channelsState === "known" ? text(v,"existingChannels") : "", availableMaterials:v.materialsState === "known" ? text(v,"availableMaterials") : "", teamResources:v.teamState === "known" ? text(v,"teamResources") : ""};
    const constraints = v.constraintStatus === "known" ? text(v,"specialRequirements") : v.constraintStatus === "none" ? "用户确认：暂无额外特殊限制。" : "特殊限制暂未确定，发布前需确认。";
    const amount = v.budgetMode === "zero" ? 0 : v.budgetMode === "amount" && text(v,"budgetAmount") ? Number(v.budgetAmount) : null;
    const campaign = v.periodMode === "duration" ? (text(v,"durationDays") ? {duration_days:Number(v.durationDays)} : null) : v.periodMode === "dates" ? {start_date:text(v,"startDate"),end_date:text(v,"endDate")} : null;
    return {
      product_name:text(v,"productName"), product_description:pack(facts,product),
      marketing_goal:pack(goalText,{formVersion:1,...pick(v,goalIds)}),
      target_audience:v.audienceMode === "known" ? text(v,"targetAudience") || null : null,
      budget:amount === null ? null : {amount,currency:v.currency}, campaign_period:campaign,
      special_requirements:pack(constraints,context),
      budget_raw:amount === null ? null : v.budgetMode === "zero" ? "零预算" : text(v,"budgetRaw") || `${amount} ${v.currency}`,
    };
  }
  function migrateDraft(raw = {}) {
    const result = {...defaults, ...Object.fromEntries(fields.filter(id => typeof raw[id] === "string").map(id => [id, raw[id]]))};
    const enhanced = raw.briefVersion === 1;
    result.briefVersion = 1;
    result.formMode = raw.formMode === "single" ? "single" : "wizard";
    result.wizardStep = Number.isInteger(raw.wizardStep) ? Math.max(0,Math.min(3,raw.wizardStep)) : 0;
    result.periodMode = enhanced ? (["duration","dates","unknown"].includes(raw.periodMode) ? raw.periodMode : "") : raw.startDate || raw.endDate ? "dates" : raw.durationDays ? "duration" : "unknown";
    if (!enhanced) {
      result.primaryGoal = raw.marketingGoal ? "其他" : "";
      result.desiredAction = "暂未确定";
      result.audienceMode = raw.targetAudience ? "known" : "assist";
      result.budgetMode = raw.budgetAmount === "0" ? "zero" : raw.budgetAmount || raw.budgetRaw ? "amount" : "unknown";
      result.constraintStatus = raw.specialRequirements ? "known" : "unknown";
      result.marketingProblem = "暂未确定";
    }
    return result;
  }
  function fromRequirements(r) {
    const product = unpack(r.product_description), goal = unpack(r.marketing_goal), context = unpack(r.special_requirements);
    const enhanced = product.detail !== null;
    const v = migrateDraft({productName:r.product_name,productDescription:product.base,marketingGoal:goal.base,targetAudience:r.target_audience || "",budgetRaw:r.budget_raw || "",budgetAmount:r.budget ? String(r.budget.amount) : "",currency:r.budget?.currency || "CNY",durationDays:r.campaign_period?.duration_days ? String(r.campaign_period.duration_days) : "",startDate:r.campaign_period?.start_date || "",endDate:r.campaign_period?.end_date || "",specialRequirements:context.base});
    if (enhanced) {
      for (const detail of [product.detail,goal.detail,context.detail]) {
        if (detail) for (const id of fields) if (typeof detail[id] === "string") v[id] = detail[id];
      }
      // Only typed constraints belong in the editable restriction field.
      v.specialRequirements = v.constraintStatus === "known" ? context.base : "";
    }
    return v;
  }
  function requirements(values, scope = null) {
    const v = {...defaults,...values};
    const required = [
      ["productName",0,"产品名称"],["productCategory",0,"产品品类"],["productDescription",0,"产品或服务内容"],["productFeatures",0,"已确认的产品特点"],["salesScope",0,"销售方式"],
      ["primaryGoal",1,"首要营销目标"],["desiredAction",1,"希望用户采取的行动"],["audienceMode",1,"目标人群填写方式"],["marketingProblem",1,"当前推广难题"],
      ["budgetMode",2,"预算情况"],["periodMode",2,"推广周期情况"],["channelsState",2,"已有渠道情况"],["materialsState",2,"素材情况"],["teamState",2,"执行人力情况"],["constraintStatus",3,"特殊限制情况"],
    ];
    const conditional = [
      [v.priceStatus === "known","priceInfo",0,"已确认价格"],[v.purchaseStatus === "known","purchaseEntry",0,"购买或咨询入口"],
      [v.primaryGoal === "其他","marketingGoal",1,"具体营销目标"],[v.desiredAction === "其他","actionDetail",1,"具体用户行动"],[v.audienceMode === "known","targetAudience",1,"已知目标人群"],[v.marketingProblem === "其他","problemDetail",1,"具体推广难题"],
      [v.budgetMode === "amount","budgetAmount",2,"预算金额"],[v.periodMode === "duration","durationDays",2,"持续天数"],[v.periodMode === "dates","startDate",2,"开始日期"],[v.periodMode === "dates","endDate",2,"结束日期"],
      [v.channelsState === "known","existingChannels",2,"已有渠道及可用情况"],[v.materialsState === "known","availableMaterials",2,"可用素材"],[v.teamState === "known","teamResources",2,"执行人力"],[v.constraintStatus === "known","specialRequirements",3,"具体特殊限制"],
    ];
    conditional.filter(([condition]) => condition).forEach(([,id,step,label]) => required.push([id,step,label]));
    return required.filter(([,step]) => scope === null || step === scope).map(([id,step,label]) => ({id,step,label,complete:Boolean(text(v,id))}));
  }
  return {fields,defaults,steps,payload,migrateDraft,fromRequirements,requirements,unpack};
})();
if (typeof module !== "undefined" && module.exports) module.exports = StrategyBrief;
