"""模型结果的确定性业务规则校验。"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
import json
import re

from .constraints import extract_constraints, channel_matches

from .models import StrategyData, StrategyRequest
from .intake import unpack

VALIDATION_VERSION = "strategy-rules-v8-delivery-quality"


def _has_paid_action(text):
    """区分明确否定和实际付费建议；否定不免除同句其他付费动作。"""
    for clause in re.split(r"[，,；;。\n]|但是|不过|但|而", text):
        for match in re.finditer(r"付费(?:达人合作|广告投放|推广|投放|合作|广告)?|购买广告|广告投放|达人合作|竞价|信息流广告|赞助", clause):
            prefix=clause[:match.start()].rstrip()
            if re.search(r"(?:不得不|不能不|不可能不)$",prefix):
                return True
            if not re.search(r"(?:不|不能|不会|不需要|不得|禁止|无需|无须|避免|拒绝|不建议)(?:进行|开展|采用|安排|使用|投放|新增|购买|参与|依赖|产生|涉及|发生|导致|包含|引入|考虑|任何|所有|额外|再|做)*$",prefix):
                return True
    return False


def _product_evidence(requirements):
    description=requirements.product_description
    base,separator,detail=description.partition("\n\n【智策需求补充 v1】\n")
    facts=[requirements.product_name,base]
    if separator:
        try:
            value=json.loads(detail)
            # 兼容旧版已确认价格仅保存在补充JSON中的需求；不把其余元数据视为事实。
            if isinstance(value,dict) and value.get('formVersion')==1 and value.get('priceStatus')=='known' and isinstance(value.get('priceInfo'),str):
                facts.append(value['priceInfo'])
        except ValueError:
            pass
    return '\n'.join(facts)


def validate_business_rules(data: StrategyData, request: StrategyRequest) -> list[str]:
    issues: list[str] = []
    value = data.value
    requirements = request.requirements
    source_text = requirements.source_text()
    # 表单元数据、目标和执行资源不能作为产品卖点的事实依据。
    product_text = _product_evidence(requirements)

    for index, point in enumerate(value["selling_points"]):
        quote = point["source_quote"].strip()
        if quote not in product_text:
            issues.append(f"selling_points[{index}].source_quote 无法在原始产品介绍或名称中定位")

    if requirements.target_audience:
        audience_text = value["target_audience"]["segment"]
        if requirements.target_audience not in audience_text:
            issues.append("target_audience 未保留用户指定的目标人群")

    for field in ("age_range", "occupation"):
        item = value["target_audience"][field]
        if item is not None and item not in source_text:
            issues.append(f"target_audience.{field} 无输入事实依据，未知值应为 null")
    if requirements.target_audience is None and not value["assumptions"]:
        issues.append("assumptions 必须说明候选目标受众属于待验证推断")

    constraints = extract_constraints(unpack(requirements.special_requirements)[0])
    channel_names = [channel["name"] for channel in value["channels"]]
    for forbidden in constraints.forbidden_channels:
        if any(channel_matches(name, forbidden) for name in channel_names):
            issues.append(f"channels 推荐了禁用渠道：{forbidden}")
    for required in constraints.required_channels:
        if required not in constraints.conflicts and not any(channel_matches(name, required) for name in channel_names):
            issues.append(f"channels 缺少必选渠道：{required}")
    conflict_text = " ".join(value["constraint_conflicts"])
    for name in constraints.conflicts:
        if name not in conflict_text:
            issues.append(f"constraint_conflicts 未记录 {name} 同时必选与禁用")

    # 仅扫描建议内容，不把风险说明或约束引用误判为营销承诺。
    actionable = json.dumps({key: value[key] for key in ("positioning", "selling_points", "channels", "marketing_strategy")}, ensure_ascii=False)
    for token in constraints.forbidden_content:
        if token in actionable:
            issues.append(f"data 使用了用户禁用表达：{token}")
    for token in ("国家认证", "官方认证", "销量第一", "百分百", "保证减肥", "治愈", "买一送一", "满减", "优惠券"):
        if token in actionable and token not in product_text:
            issues.append(f"data 含无输入依据的事实或承诺：{token}")

    allocations: list[Decimal] = []
    for index, channel in enumerate(value["channels"]):
        raw_amount = channel["allocated_amount"]
        if raw_amount is not None:
            amount = Decimal(str(raw_amount))
            allocations.append(amount)
            if requirements.budget is None:
                issues.append(f"channels[{index}].allocated_amount 在未提供预算时必须为 null")
            elif requirements.budget.amount == 0 and amount > 0:
                issues.append(f"channels[{index}].allocated_amount 在预算为 0 时不得大于 0")
    if requirements.budget is not None and sum(allocations, Decimal("0")) > requirements.budget.amount:
        issues.append("渠道预算分配合计超过输入总预算")
    if requirements.budget is not None and requirements.budget.amount == 0:
        for index, channel in enumerate(value["channels"]):
            suggestion = " ".join(channel[field] for field in ("name", "content_direction"))
            if _has_paid_action(suggestion):
                issues.append(f"channels[{index}] 零预算不能建议付费渠道或付费合作")
        if _has_paid_action("；".join(value["marketing_strategy"]["promotion_methods"])):
            issues.append("marketing_strategy.promotion_methods 零预算不能包含付费推广")

    for raw in re.findall(r"\d{4}-\d{2}-\d{2}", actionable):
        period = requirements.campaign_period
        try:
            stamp = date.fromisoformat(raw)
        except ValueError:
            issues.append("data 存在非法排期日期")
            continue
        if period is None or period.start_date is None:
            issues.append("data 未提供日期对时不得编造排期日期")
        elif not date.fromisoformat(period.start_date) <= stamp <= date.fromisoformat(period.end_date):
            issues.append("data 排期日期超出输入推广周期")

    schedule = " ".join(value["marketing_strategy"]["promotion_methods"] + value["marketing_strategy"]["content_directions"])
    period = requirements.campaign_period
    limit = None
    if period:
        limit = period.duration_days or (date.fromisoformat(period.end_date) - date.fromisoformat(period.start_date)).days + 1
    for raw in re.findall(r"(?:推广周期|活动持续|连续推广)(?:为|共|[:：])?\s*(\d+)天", schedule):
        if limit is None:
            issues.append("marketing_strategy 未提供推广周期时不能编造总周期")
        elif int(raw) != limit:
            issues.append("marketing_strategy 总推广周期与输入不一致")
    for raw in re.findall(r"第\s*(\d+)\s*天", schedule):
        if limit is not None and not 1 <= int(raw) <= limit:
            issues.append("marketing_strategy 相对排期超出输入推广周期")

    missing = value["missing_information"]
    missing_text = " ".join(missing)
    if requirements.budget is None and "预算" not in missing_text:
        issues.append("missing_information 必须记录未提供预算")
    if requirements.campaign_period is None and not any(term in missing_text for term in ("周期", "时间", "日期")):
        issues.append("missing_information 必须记录未提供推广周期")
    if requirements.target_audience is None and "目标" not in missing_text and "受众" not in missing_text:
        issues.append("missing_information 必须记录未提供目标受众")

    return issues


def validate_strategy_quality(data: StrategyData, request: StrategyRequest) -> list[dict]:
    """关键词只能发现可疑质量缺口，不证明语义违规，不能触发模型重试。"""
    value = data.value
    requirements = request.requirements
    findings: list[dict] = []

    # 明确的占位输出/逐字重复不是关键词猜测语义，应阻断交付。
    placeholders = {"介绍产品", "宣传产品", "推广产品", "提高知名度", "发布内容", "制作内容", "了解产品", "待补充", "暂无", "无", "待定"}
    def normalized(text):
        return re.sub(r"[\s，。；：、,.!！?？:;\-]", "", re.sub(r"^(?:待验证假设|待验证|内容|方向|执行动作)[:：]", "", text))
    def concrete(field, text):
        if normalized(text) in placeholders:
            findings.append({"field": field, "message": "此项只有泛泛占位描述，需写出针对本产品的具体选择或动作", "category": "quality", "severity": "blocking"})
    concrete("positioning", value["positioning"])
    for index, channel in enumerate(value["channels"]):
        concrete(f"channels[{index}].content_direction", channel["content_direction"])
    for field in ("content_directions", "promotion_methods"):
        entries = value["marketing_strategy"][field]
        for index, entry in enumerate(entries):
            concrete(f"marketing_strategy.{field}[{index}]", entry)
        if len(entries) > 1 and len({normalized(v) for v in entries}) < len(entries):
            findings.append({"field": f"marketing_strategy.{field}", "message": "同组内容逐字重复，需合并或明确不同任务", "category": "quality", "severity": "blocking"})
    directions = [normalized(c["content_direction"]) for c in value["channels"]]
    if len(directions) > 1 and len(set(directions)) < len(directions):
        findings.append({"field": "channels", "message": "渠道执行内容完全重复，需明确各渠道的不同职责或合并", "category": "quality", "severity": "blocking"})

    for index, channel in enumerate(value["channels"]):
        direction = channel["content_direction"]
        has_publish_action = bool(re.search(r"制作|拍摄|撰写|整理|发布|投放|张贴|展示|讲解|推送|更新|复用", direction))
        has_verification = bool(re.search(r"核实|确认|检查|取得.{0,8}许可|获得.{0,8}权限|验证", direction))
        if (not has_publish_action or not has_verification) and not any(f["field"] == f"channels[{index}].content_direction" and f["severity"] == "blocking" for f in findings):
            findings.append({
                "field": f"channels[{index}].content_direction",
                "message": "建议人工检查渠道是否写清制作或发布动作及执行前提；关键词检查不能判断完整语义",
                "category": "quality",
                "severity": "advisory",
            })
    methods = " ".join(value["marketing_strategy"]["promotion_methods"])
    has_execution = bool(re.search(r"准备|制作|发布|测试|复用|调整|记录|收集|更新|安排|分发|整理", methods))
    has_verification = bool(re.search(r"核实|确认|检查|验证", methods))
    if not has_execution or not has_verification:
        findings.append({
            "field": "marketing_strategy.promotion_methods",
            "message": "建议人工检查推广方式的先后动作及实施前提，不要求特定关键词",
            "category": "quality",
            "severity": "advisory",
        })

    budget = requirements.budget
    if budget is not None and budget.amount > 0:
        allocations = [channel["allocated_amount"] for channel in value["channels"]]
        if any(amount is None for amount in allocations):
            findings.append({
                "field": "channels",
                "message": "部分渠道尚未估算金额，执行前需确认用途和预算；不得当作已完成预算分配",
                "category": "quality",
                "severity": "advisory",
            })
        for index, channel in enumerate(value["channels"]):
            if channel["allocated_amount"] in (None, 0):
                continue
            if not re.search(r"预算.{0,8}(?:用于|投入|安排|分配)|用于.{0,12}(?:制作|发布|测试|素材)", channel["content_direction"]):
                findings.append({
                    "field": f"channels[{index}].content_direction",
                    "message": "建议确认此渠道金额是否对应具体执行用途；不同表述不应因缺少关键词被拒绝",
                    "category": "quality",
                    "severity": "advisory",
                })

    return findings
