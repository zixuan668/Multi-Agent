"""将旧版八字段里的表单补充转为模型可读简报，不改变公共契约。"""
from copy import deepcopy
import json

MARKER = "\n\n【智策需求补充 v1】\n"


def unpack(value):
    raw = value or ""
    base, separator, suffix = raw.rpartition(MARKER)
    if separator:
        try:
            detail = json.loads(suffix)
            if isinstance(detail, dict) and detail.get("formVersion") == 1:
                return base, detail
        except ValueError:
            pass
    return raw, {}


def normalized_brief(requirements):
    """只接受白名单字符串；unknown/none 不会带入旧草稿的资源值。"""
    original = deepcopy(requirements)
    product, product_detail = unpack(original.get("product_description"))
    goal, goal_detail = unpack(original.get("marketing_goal"))
    restrictions, context = unpack(original.get("special_requirements"))
    result = {
        "product_name": original.get("product_name"),
        "product_evidence_text": product,
        "goal_text": goal,
        "target_audience": original.get("target_audience"),
        "budget": original.get("budget"),
        "campaign_period": original.get("campaign_period"),
        "restrictions": restrictions,
    }
    def strings(source, keys):
        return {key: source[key].strip() for key in keys if isinstance(source.get(key), str) and source[key].strip()}
    result["product_context"] = strings(product_detail, ("productCategory", "salesScope", "salesRegion"))
    for state_key, value_key in (("priceStatus", "priceInfo"), ("purchaseStatus", "purchaseEntry")):
        state = product_detail.get(state_key, "unknown")
        result["product_context"][state_key] = state if state in ("known", "unknown") else "unknown"
        if state == "known" and isinstance(product_detail.get(value_key), str):
            result["product_context"][value_key] = product_detail[value_key].strip()
    # 旧版已确认价格可能只在补充 JSON 中；为逐字引用保留这一事实。
    price = result["product_context"].get("priceInfo")
    if price and price not in product:
        result["product_evidence_text"] += "\n已确认价格：" + price
    result["objective"] = strings(goal_detail, ("primaryGoal", "desiredAction", "actionDetail", "marketingGoal"))
    result["situation"] = strings(context, ("marketingProblem", "problemDetail", "audienceMode", "brandStyle"))
    resources = {}
    for state_key, value_key in (("channelsState", "existingChannels"), ("materialsState", "availableMaterials"), ("teamState", "teamResources")):
        state = context.get(state_key, "unknown")
        state = state if state in ("known", "none", "unknown") else "unknown"
        resources[value_key] = {"state": state, "detail": context.get(value_key, "").strip() if state == "known" and isinstance(context.get(value_key), str) else ""}
    result["resources"] = resources
    return result
