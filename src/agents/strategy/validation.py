"""模型结果的确定性业务规则校验。"""

from __future__ import annotations

from decimal import Decimal
from datetime import date
import json
import re

from .constraints import extract_constraints, channel_matches

from .models import StrategyData, StrategyRequest


def validate_business_rules(data: StrategyData, request: StrategyRequest) -> list[str]:
    issues: list[str] = []
    value = data.value
    requirements = request.requirements
    source_text = requirements.source_text()

    for index, point in enumerate(value["selling_points"]):
        quote = point["source_quote"].strip()
        if quote not in source_text:
            issues.append(f"selling_points[{index}].source_quote 无法在原始输入中定位")

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

    constraints = extract_constraints(requirements.special_requirements)
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
        if token in actionable and token not in source_text:
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
            if re.search(r"付费|购买广告|广告投放|达人合作|竞价|信息流广告|赞助", suggestion):
                issues.append(f"channels[{index}] 零预算不能建议付费渠道或付费合作")
        if re.search(r"付费|购买广告|达人合作|竞价|信息流广告|赞助", " ".join(value["marketing_strategy"]["promotion_methods"])):
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
    """只拦截明确不可交付的内容缺口；主观优劣仍交给人工验收。"""
    value = data.value
    requirements = request.requirements
    findings: list[dict] = []

    for index, channel in enumerate(value["channels"]):
        direction = channel["content_direction"]
        has_publish_action = bool(re.search(r"制作|拍摄|撰写|整理|发布|投放|张贴|展示|讲解|推送|更新|复用", direction))
        has_verification = bool(re.search(r"核实|确认|检查|取得.{0,8}许可|获得.{0,8}权限|验证", direction))
        if not has_publish_action or not has_verification:
            findings.append({
                "field": f"channels[{index}].content_direction",
                "message": "渠道内容必须用自然语言写清具体制作或发布动作，以及执行前核实事项",
                "category": "quality",
                "severity": "blocking",
            })
    methods = " ".join(value["marketing_strategy"]["promotion_methods"])
    has_execution = bool(re.search(r"准备|制作|发布|测试|复用|调整|记录|收集|更新|安排|分发|整理", methods))
    has_verification = bool(re.search(r"核实|确认|检查|验证", methods))
    if not has_execution or not has_verification:
        findings.append({
            "field": "marketing_strategy.promotion_methods",
            "message": "整组推广方式必须同时体现实际执行动作和实施前核实事项",
            "category": "quality",
            "severity": "blocking",
        })

    budget = requirements.budget
    if budget is not None and budget.amount > 0:
        allocations = [channel["allocated_amount"] for channel in value["channels"]]
        if any(amount is None for amount in allocations):
            findings.append({
                "field": "channels",
                "message": "输入已提供预算时，每个推荐渠道都必须给出明确分配金额",
                "category": "quality",
                "severity": "blocking",
            })
        elif sum((Decimal(str(amount)) for amount in allocations), Decimal("0")) != budget.amount:
            findings.append({
                "field": "channels",
                "message": "渠道分配金额之和必须等于输入总预算，避免留下用途不明的余额",
                "category": "quality",
                "severity": "blocking",
            })
        for index, channel in enumerate(value["channels"]):
            if not re.search(r"预算.{0,8}(?:用于|投入|安排|分配)|用于.{0,12}(?:制作|发布|测试|素材)", channel["content_direction"]):
                findings.append({
                    "field": f"channels[{index}].content_direction",
                    "message": "已分配预算的渠道必须说明预算用于哪项具体执行动作",
                    "category": "quality",
                    "severity": "blocking",
                })

    return findings
