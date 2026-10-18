"""Immutable A handoff intake using the existing public schemas."""
import json
from copy import deepcopy
from .schema import validate
from .errors import CreativeError

MARKER = "\n\n【智策需求补充 v1】\n"

def split(value):
    if not isinstance(value, str): return "", {}
    if MARKER in value:
        base, raw = value.rsplit(MARKER,1)
        try:
            extra = json.loads(raw)
            if isinstance(extra,dict) and type(extra.get("formVersion")) is int and extra["formVersion"] == 1:
                return base.strip(), extra
        except ValueError: pass
    return value.strip(), {}

def receive(payload, task_id=None):
    validate(payload, "creative-request.schema.json")
    s, r = payload["strategy"], payload["requirements"]
    if s["task_id"] != payload["task_id"] or (task_id and task_id != payload["task_id"]):
        raise CreativeError("strategy.task_id 与当前任务不一致")
    if s["round_no"] != 1: raise CreativeError("首轮交付不能引用其他轮次策略")
    facts, extra = split(r["product_description"])
    price = extra.get("priceInfo", "") if extra.get("priceStatus") == "known" else ""
    for point in s["data"]["selling_points"]:
        if point["source_quote"] not in facts and (not price or point["source_quote"] not in price):
            raise CreativeError("selling_points.source_quote 无法定位到原始产品事实")
    budget = r["budget"]
    amounts = [c["allocated_amount"] for c in s["data"]["channels"] if c["allocated_amount"] is not None]
    if (budget is None and amounts) or (budget and sum(amounts) > budget["amount"]+0.001):
        raise CreativeError("渠道金额与原始预算不一致")
    names=[c["name"] for c in s["data"]["channels"]]
    if len(set(names)) != len(names): raise CreativeError("策略渠道名称重复，无法定位创意")
    return deepcopy(payload)

def brief(payload):
    r,s = payload["requirements"],payload["strategy"]["data"]
    facts, extra = split(r["product_description"])
    limits, resources = split(r.get("special_requirements"))
    goal, _ = split(r["marketing_goal"])
    return {"product_name":r["product_name"], "product_facts":facts,
            "price":extra.get("priceInfo", "") if extra.get("priceStatus")=="known" else "",
            "purchase_entry":extra.get("purchaseEntry", "") if extra.get("purchaseStatus")=="known" else "",
            "resources":{kind:{"status":resources.get(key,"unknown"),
                         "detail":resources.get(field,"") if resources.get(key)=="known" else ""}
                         for kind,key,field in [("channels","channelsState","existingChannels"),
                                              ("materials","materialsState","availableMaterials"),
                                              ("team","teamState","teamResources")]},
            "goal":goal,"budget":deepcopy(r["budget"]),"explicit_constraints":limits,
            **deepcopy(s)}
