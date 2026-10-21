from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import re
import json

from src.agents.generation import generate_validated, prompt_text
from src.agents.strategy.constraints import extract_constraints
from src.contracts.campaign import DIMENSIONS, compact, envelope, locate, validate_review
from .service import hard_risks


def content_risks(request):
    risks = hard_risks(request)
    facts = compact(request["requirements"]["product_name"] + request["requirements"]["product_description"])
    constraints = extract_constraints(request["requirements"].get("special_requirements"))
    patterns = (
        r"(?:保证|确保|承诺|一定|百分之百|100%)[^。！？\n]{0,25}(?:效果|通过|成功|提高|提升|治愈|减肥|收益)",
        r"(?:国际|权威|官方|国家级)[^。！？\n]{0,12}(?:认证|认定)",
        r"(?:已售|销量|好评率)[^。！？\n]{0,8}\d+[万千亿%]?",
    )
    for index, item in enumerate(request["creative"]["data"]["items"]):
        copy_fields = {field: item[field] for field in ('headline', 'body', 'call_to_action')}
        for field, value in item.get('visual_brief', {}).get('poster', {}).items():
            if field in ('headline', 'supporting_text', 'action_text') and value:
                copy_fields['visual_brief.poster.' + field] = value
        for field, value in copy_fields.items():
            path = f"creative.items[{index}].{field}"
            for expression in patterns:
                for match in re.finditer(expression, value):
                    prefix = value[max(0, match.start() - 3):match.start()]
                    if re.search(r"不|未|无|拒绝|禁止", prefix) or compact(match.group()) in facts:
                        continue
                    risks.append({"category": "fact", "severity": "high", "target_path": path, "evidence": match.group(), "description": "出现未获产品原文支持的认证、销量或效果承诺。"})
            for forbidden in constraints.forbidden_content:
                if forbidden in value:
                    risks.append({"category": "constraint", "severity": "high", "target_path": path, "evidence": forbidden, "description": "创意包含用户明确禁用的表达。"})
    unique = {}
    for risk in risks:
        unique[(risk["target_path"], risk["description"], risk["evidence"])] = risk
    return list(unique.values())


class EvaluationAgent:
    def __init__(self, client=None, *, offline=False, system_prompt=None):
        if client is None and not offline:
            raise ValueError("真实方案评审需要模型客户端")
        self.client = client
        self.offline = offline
        self.system_prompt = system_prompt or prompt_text("evaluation")

    def assess(self, request, *, version, check=lambda: None, progress=lambda attempt: None):
        check()
        if self.offline:
            progress(1)
            item = request["creative"]["data"]["items"][0]
            values = {
                "attraction": ("creative.items[0].headline", item["headline"]),
                "audience_fit": ("strategy.target_audience.segment", request["strategy"]["data"]["target_audience"]["segment"]),
                "clarity": ("creative.items[0].body", item["body"]),
                "channel_fit": ("creative.items[0].channel", item["channel"]),
                "call_to_action": ("creative.items[0].call_to_action", item["call_to_action"]),
            }
            data = {"dimension_scores": {}, "risks": [], "feedback": [], "feedback_checks": []}
            for key, (path, value) in values.items():
                actionable = key != "call_to_action" or bool(re.search(r"查看|了解|阅读|咨询|联系|到店|体验", value))
                data["dimension_scores"][key] = {"score": 80 if actionable else 60, "reason": "离线仅检查字段、引用和行动词，不代表模型判断的内容质量。", "target_path": path, "evidence": value[:500]}
            if data["dimension_scores"]["call_to_action"]["score"] < 80:
                data["feedback"].append({"target_agent": "creative", "target_path": "creative.items[0].call_to_action", "issue": "缺少明确的下一步动作。", "suggestion": "提供真实可执行的查看、咨询或了解产品的下一步。", "priority": "high"})
            for feedback in request["feedback"]:
                path = feedback["target_path"]
                try:
                    value = locate(request, path)
                    value = value if isinstance(value,str) else json.dumps(value,ensure_ascii=False)
                except Exception:
                    path = "strategy.positioning" if feedback["target_agent"] == "strategy" else "creative.items[0].body"
                    value = str(locate(request, path))
                data["feedback_checks"].append({"feedback_id": feedback["feedback_id"], "resolved": False, "reason": "离线规则无法确认语义问题已修复，保留人工复核。", "target_path": path, "evidence": value[:500]})
            data = validate_review(data, request)
            attempt = 1
        else:
            data, attempt = generate_validated(self.client, self.system_prompt, request, validate_review, check=check, progress=progress)
        check()
        data["risks"].extend(content_risks(request))
        unique = {(risk["severity"], risk["target_path"], risk["description"]): risk for risk in data["risks"]}
        data["risks"] = list(unique.values())
        for risk in data["risks"]:
            owner = risk["target_path"].split(".")[0]
            if risk["severity"] == "high" and not any(feedback["target_path"] == risk["target_path"] and feedback["priority"] == "high" for feedback in data["feedback"]):
                data["feedback"].append({"target_agent": owner, "target_path": risk["target_path"], "issue": risk["description"], "suggestion": "核对原始产品事实，删除或修正没有依据及违反约束的内容。", "priority": "high"})
        score = sum(Decimal(item["score"]) for item in data["dimension_scores"].values()) / len(DIMENSIONS)
        data.update(total_score=float(score.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)), strategy_result_id=request["strategy"]["result_id"], creative_result_id=request["creative"]["result_id"])
        return envelope("evaluation", request, data, version, attempt)
