from copy import deepcopy
from datetime import datetime, timezone
import json
import re
from uuid import uuid4

from src.agents.strategy.errors import ContractValidationError
from src.agents.strategy.models import MarketingRequirements, StrategyResponse
from .poster import validate_poster_plan


DIMENSIONS = {
    "attraction": "吸引力",
    "audience_fit": "受众匹配",
    "clarity": "信息清晰度",
    "channel_fit": "渠道适配",
    "call_to_action": "行动引导",
}
LEVELS = {"low", "medium", "high"}
ASSET_FIELDS = {"asset_id", "creative_result_id", "uri", "mime_type", "width", "height", "sha256", "status"}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fields(value, expected, path):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ContractValidationError(f"{path} 字段不完整或包含未声明字段")


def text(value, path, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractValidationError(f"{path} 须为1至{limit}字文本")
    return value


def items(value, path, maximum=20, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ContractValidationError(f"{path} 数量须为{minimum}至{maximum}")
    return value


def compact(value):
    return re.sub(r"\s+", "", value if isinstance(value, str) else json.dumps(value, ensure_ascii=False))


def locate(request, path):
    text(path, "target_path", 200)
    if not re.fullmatch(r"(?:strategy|creative)\.[A-Za-z_]+(?:\[\d+\]|\.[A-Za-z_]+)*", path):
        raise ContractValidationError("target_path 须为策略或创意中的具体字段")
    current = {"strategy": request["strategy"]["data"], "creative": request["creative"]["data"]}
    try:
        for token in re.findall(r"[A-Za-z_]+|\d+", path):
            current = current[int(token)] if token.isdigit() else current[token]
    except (KeyError, TypeError, IndexError):
        raise ContractValidationError(f"target_path 无法定位 {path}") from None
    return current


def evidence(request, path, quote):
    value = locate(request, path)
    text(quote, "evidence", 500)
    if compact(quote) not in compact(value):
        raise ContractValidationError(f"evidence 不是 {path} 中的实际原文")


def envelope(agent, request, data, version, attempt=1):
    return {
        "schema_version": "1.1", "task_id": request["task_id"], "agent": agent,
        "round_no": request["round_no"], "attempt_count": attempt, "status": "succeeded",
        "result_id": f"{agent}-{uuid4().hex}", "version": version,
        "data": deepcopy(data), "error": None, "created_at": now(),
    }


def validate_creative(data, request):
    fields(data, {"strategy_result_id", "concept", "items", "assumptions"}, "creative")
    StrategyResponse.from_dict(request["strategy"], task_id=request["task_id"])
    if data["strategy_result_id"] != request["strategy"]["result_id"]:
        raise ContractValidationError("creative.strategy_result_id 必须引用当前策略")
    fields(data["concept"], {"idea", "rationale"}, "concept")
    for key in ("idea", "rationale"):
        text(data["concept"][key], "concept." + key, 800)
    channels = [channel["name"] for channel in request["strategy"]["data"]["channels"]]
    creative_items = items(data["items"], "creative.items", maximum=5, minimum=1)
    facts = compact(request["requirements"]["product_name"] + "\n" + request["requirements"]["product_description"])
    for index, item in enumerate(creative_items):
        path = f"creative.items[{index}]"
        fields(item, {"channel", "headline", "body", "call_to_action", "visual_brief", "fact_references", "assets"}, path)
        for key, limit in (("channel", 100), ("headline", 60), ("body", 1000), ("call_to_action", 120)):
            text(item[key], path + "." + key, limit)
        visual = item['visual_brief']
        fields(visual, {"subject", "composition", "style", "aspect_ratio"} | ({'poster'} if isinstance(visual, dict) and 'poster' in visual else set()), path + ".visual_brief")
        if 'poster' in visual:
            validate_poster_plan(visual['poster'])
        for key in ("subject", "composition", "style"):
            text(item["visual_brief"][key], path + ".visual_brief." + key, 500)
        if item["visual_brief"]["aspect_ratio"] not in ("1:1", "3:4", "4:5", "16:9", "9:16"):
            raise ContractValidationError("visual_brief.aspect_ratio 不在支持范围内")
        for reference in items(item["fact_references"], "fact_references", maximum=5, minimum=1):
            fields(reference, {"claim", "source_quote"}, "fact_reference")
            text(reference["claim"], "fact_reference.claim", 500)
            quote = text(reference["source_quote"], "fact_reference.source_quote", 500)
            if compact(quote) not in facts:
                raise ContractValidationError("fact_reference.source_quote 必须来自产品名称或产品介绍原文")
        items(item["assets"], "assets", maximum=0)
    if sorted(item["channel"] for item in creative_items) != sorted(channels):
        raise ContractValidationError("creative.items 必须分别对应当前策略的渠道，不能增删渠道")
    for assumption in items(data["assumptions"], "assumptions", maximum=10):
        text(assumption, "assumption", 500)
    return deepcopy(data)


def validate_review(data, request):
    expected = {"dimension_scores", "risks", "feedback", "feedback_checks"}
    fields(data, expected | ({"clarifications"} if isinstance(data, dict) and "clarifications" in data else set()), "evaluation")
    fields(data["dimension_scores"], DIMENSIONS, "dimension_scores")
    for key, score in data["dimension_scores"].items():
        fields(score, {"score", "reason", "target_path", "evidence"}, key)
        if type(score["score"]) is not int or not 0 <= score["score"] <= 100:
            raise ContractValidationError(f"{key}.score 须为0至100整数")
        text(score["reason"], key + ".reason", 800)
        evidence(request, score["target_path"], score["evidence"])
    for risk in items(data["risks"], "risks", maximum=30):
        fields(risk, {"category", "severity", "target_path", "evidence", "description"}, "risk")
        if risk["category"] not in ("fact", "constraint", "compliance", "brand", "audience") or risk["severity"] not in LEVELS:
            raise ContractValidationError("risk 类别或级别无效")
        text(risk["description"], "risk.description", 800)
        evidence(request, risk["target_path"], risk["evidence"])
    for feedback in items(data["feedback"], "feedback", maximum=30):
        fields(feedback, {"target_agent", "target_path", "issue", "suggestion", "priority"}, "feedback")
        if feedback["target_agent"] not in ("strategy", "creative") or feedback["priority"] not in LEVELS:
            raise ContractValidationError("feedback 目标或优先级无效")
        text(feedback["target_path"], "feedback.target_path", 200)
        if not feedback["target_path"].startswith(feedback["target_agent"] + "."):
            raise ContractValidationError("feedback 路径与目标智能体不符")
        locate(request, feedback["target_path"])
        for key in ("issue", "suggestion"):
            text(feedback[key], "feedback." + key, 800)
    previous = {feedback["feedback_id"]: feedback for feedback in request["feedback"]}
    checks = items(data["feedback_checks"], "feedback_checks", maximum=200)
    if len(checks) != len(previous) or {check.get("feedback_id") for check in checks if isinstance(check, dict)} != set(previous):
        raise ContractValidationError("feedback_checks 必须逐项复核每条未解决反馈")
    for check in checks:
        fields(check, {"feedback_id", "resolved", "reason", "target_path", "evidence"}, "feedback_check")
        if type(check["resolved"]) is not bool:
            raise ContractValidationError("feedback_check.resolved 须为布尔值")
        text(check["reason"], "feedback_check.reason", 800)
        text(check["target_path"], "feedback_check.target_path", 200)
        if not check["target_path"].startswith(previous[check["feedback_id"]]["target_agent"] + "."):
            raise ContractValidationError("feedback_check 必须复核原目标智能体")
        evidence(request, check["target_path"], check["evidence"])
    for clarification in items(data.get("clarifications", []), "clarifications", maximum=5):
        fields(clarification, {"question", "reason", "target_path", "evidence"}, "clarification")
        text(clarification["question"], "clarification.question", 500)
        text(clarification["reason"], "clarification.reason", 800)
        evidence(request, clarification["target_path"], clarification["evidence"])
    result = deepcopy(data)
    result.setdefault("clarifications", [])
    return result


def handoff(task, round_no, strategy, creative=None, previous=None, feedback=()):
    MarketingRequirements.from_dict(task["requirements"])
    StrategyResponse.from_dict(strategy, task_id=task["task_id"])
    if strategy["status"] != "succeeded" or strategy["round_no"] > round_no:
        raise ContractValidationError("交接只能引用当前任务已成功的策略")
    request = {
        "schema_version": "1.1", "task_id": task["task_id"], "round_no": round_no,
        "agent": "evaluation" if creative is not None else "creative", "attempt_count": 1,
        "requirements": deepcopy(task["requirements"]), "strategy": deepcopy(strategy),
        "creative": deepcopy(creative), "previous_result": deepcopy(previous),
        "feedback": deepcopy(list(feedback)), "config_version": task["config_version"],
    }
    if creative is not None:
        if creative.get("task_id") != task["task_id"] or creative.get("status") != "succeeded" or creative.get("round_no", 0) > round_no:
            raise ContractValidationError("创意归属、状态或轮次无效")
        validate_creative(creative["data"], request)
    return request
