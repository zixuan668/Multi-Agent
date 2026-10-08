"""SRS C.4 evaluation adapter proposal, using the published strategy boundary.

Creative output is not yet published in packages/contracts. These checks are
module-scoped and must be reviewed by A/B before being promoted to that folder.
No other agent's private storage, model client or validation helpers are used.
"""
from copy import deepcopy
from datetime import datetime
import math
import re

from src.agents.strategy.models import MarketingRequirements, StrategyResponse

DIMENSIONS = ("attraction", "audience_fit", "clarity", "channel_fit", "call_to_action")
RISK_CATEGORIES = ("fact", "constraint", "compliance", "brand", "audience")
SEVERITIES = ("low", "medium", "high")
ENVELOPE = {"schema_version", "task_id", "agent", "round_no", "attempt_count", "status", "result_id", "version", "data", "error", "created_at"}
REQUEST = {"schema_version", "task_id", "agent", "round_no", "attempt_count", "requirements", "strategy", "creative", "feedback", "previous_result", "config_version"}


class ContractError(ValueError):
    def __init__(self, field, message):
        self.field = field
        super().__init__(f"{field}: {message}")


def fields(value, names, path):
    if not isinstance(value, dict) or set(value) != set(names):
        raise ContractError(path, "字段缺失或含未声明字段")


def text(value, path, limit=1000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ContractError(path, f"须为1至{limit}字非空文本")


def integer(value, path, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ContractError(path, f"须为{low}至{high}整数")


def texts(value, path, minimum=0):
    if not isinstance(value, list) or not minimum <= len(value) <= 10:
        raise ContractError(path, "数组数量不合法")
    for i, v in enumerate(value):
        text(v, f"{path}[{i}]")


def envelope(raw, agent, task):
    fields(raw, ENVELOPE, agent)
    if raw["schema_version"] != "1.0" or raw["agent"] != agent or raw["task_id"] != task:
        raise ContractError(agent, "接口版本、智能体或任务归属不一致")
    if raw["status"] != "succeeded" or raw["error"] is not None:
        raise ContractError(agent, "评估只接受成功的完整上游响应")
    text(raw["result_id"], f"{agent}.result_id")
    integer(raw["version"], f"{agent}.version", 1, 1000000)
    for field in ("round_no", "attempt_count"):
        integer(raw[field], f"{agent}.{field}", 1, 3)
    try:
        stamp = datetime.fromisoformat(raw["created_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise ContractError(f"{agent}.created_at", "须为带时区的ISO8601时间") from None


def resolve_path(request, path):
    if not isinstance(path, str):
        raise ContractError("target_path", "须为具体字段路径")
    path = path.replace("strategy.data.", "strategy.", 1).replace("creative.data.", "creative.", 1)
    current = {"strategy": request["strategy"]["data"], "creative": request["creative"]["data"], "requirements": request["requirements"]}
    position = 0
    try:
        for match in re.finditer(r"(?:^|\.)([^.\[\]]+)|\[(\d+)\]", path):
            if match.start() != position:
                raise ValueError()
            position = match.end()
            field, index = match.groups()
            current = current[field] if field is not None else current[int(index)]
        if not path or position != len(path):
            raise ValueError()
    except (KeyError, IndexError, TypeError, ValueError):
        raise ContractError("target_path", f"无法定位 {path}") from None
    return current


def validate_feedback(items, request, *, records=False):
    if not isinstance(items, list) or len(items) > 100:
        raise ContractError("feedback", "须为反馈数组，最多100项")
    names = {"target_agent", "target_path", "issue", "suggestion", "priority"}
    if records:
        names |= {"feedback_id", "evaluation_id", "resolved"}
    for i, item in enumerate(items):
        path = f"feedback[{i}]"
        fields(item, names, path)
        for key in names - {"resolved"}:
            text(item[key], f"{path}.{key}")
        if item["target_agent"] not in ("strategy", "creative") or item["priority"] not in SEVERITIES:
            raise ContractError(path, "目标智能体或优先级非法")
        canonical = item["target_path"].replace(".data.", ".", 1)
        if not canonical.startswith(item["target_agent"] + "."):
            raise ContractError(path + ".target_path", "反馈归属与字段路径不一致")
        resolve_path(request, canonical)
        if records and type(item["resolved"]) is not bool:
            raise ContractError(path + ".resolved", "须为布尔值")


def validate_handoff(raw):
    """Return a deep copy; never mutate A or B's result objects."""
    fields(raw, REQUEST, "request")
    for key in ("task_id", "config_version"):
        text(raw[key], key)
    if raw["schema_version"] != "1.0" or raw["agent"] != "evaluation":
        raise ContractError("request", "须为schema_version=1.0的evaluation请求")
    for key in ("round_no", "attempt_count"):
        integer(raw[key], key, 1, 3)
    try:
        MarketingRequirements.from_dict(raw["requirements"])
        StrategyResponse.from_dict(raw["strategy"], task_id=raw["task_id"])
    except ValueError as exc:
        raise ContractError("strategy/requirements", str(exc)) from None
    except Exception as exc:
        raise ContractError("strategy/requirements", str(exc)) from None
    for agent in ("strategy", "creative"):
        envelope(raw[agent], agent, raw["task_id"])
        if raw[agent]["round_no"] > raw["round_no"]:
            raise ContractError(agent + ".round_no", "上游版本来自未来轮次")
    data = raw["creative"]["data"]
    fields(data, {"strategy_result_id", "items", "assumptions", "constraint_conflicts"}, "creative.data")
    if data["strategy_result_id"] != raw["strategy"]["result_id"]:
        raise ContractError("creative.strategy_result_id", "创意必须引用本次评估的策略结果")
    items = data["items"]
    channels = [c["name"] for c in raw["strategy"]["data"]["channels"]]
    if not isinstance(items, list) or not 1 <= len(items) <= 5:
        raise ContractError("creative.items", "须包含1至5项渠道创意")
    if len(set(channels)) != len(channels) or sorted(i.get("channel", "") for i in items if isinstance(i, dict)) != sorted(channels):
        raise ContractError("creative.items", "每个策略渠道须恰好对应一项创意")
    for i, item in enumerate(items):
        path = f"creative.items[{i}]"
        fields(item, {"channel", "copy", "slogan", "poster_concept", "video_script"}, path)
        for key, limit in (("channel", 1000), ("copy", 500), ("slogan", 30)):
            text(item[key], path + "." + key, limit)
        fields(item["poster_concept"], {"headline", "visual_description"}, path + ".poster_concept")
        for key, limit in (("headline", 40), ("visual_description", 300)):
            text(item["poster_concept"][key], path + ".poster_concept." + key, limit)
        video = item["video_script"]
        fields(video, {"duration_seconds", "scenes"}, path + ".video_script")
        integer(video["duration_seconds"], path + ".video_script.duration_seconds", 15, 60)
        if not isinstance(video["scenes"], list) or not 1 <= len(video["scenes"]) <= 8:
            raise ContractError(path + ".video_script.scenes", "须包含1至8场")
        for scene in video["scenes"]:
            fields(scene, {"duration_seconds", "visual", "narration"}, path + ".video_script.scenes")
            integer(scene["duration_seconds"], path + ".scene.duration_seconds", 1, 60)
            for key in ("visual", "narration"):
                text(scene[key], path + ".scene." + key, 200)
        if sum(s["duration_seconds"] for s in video["scenes"]) != video["duration_seconds"]:
            raise ContractError(path + ".video_script", "分镜秒数合计须等于总时长")
    for key in ("assumptions", "constraint_conflicts"):
        texts(data[key], "creative." + key)
    validate_feedback(raw["feedback"], raw, records=True)
    if raw["previous_result"] is not None:
        previous = raw["previous_result"]
        envelope(previous, "evaluation", raw["task_id"])
        if previous["round_no"] >= raw["round_no"]:
            raise ContractError("previous_result.round_no", "上一评估轮次须早于当前轮次")
    if raw["round_no"] == 1 and (raw["previous_result"] is not None or raw["feedback"]):
        raise ContractError("request", "首轮previous_result=null，feedback=[]")
    return deepcopy(raw)


def validate_draft(raw, request):
    fields(raw, {"dimension_scores", "risks", "feedback", "recommended_action"}, "draft")
    fields(raw["dimension_scores"], DIMENSIONS, "dimension_scores")
    for key, item in raw["dimension_scores"].items():
        fields(item, {"score", "reason", "target_path"}, key)
        integer(item["score"], key + ".score", 0, 100)
        text(item["reason"], key + ".reason")
        resolve_path(request, item["target_path"])
    if not isinstance(raw["risks"], list) or len(raw["risks"]) > 100:
        raise ContractError("risks", "须为风险数组，最多100项")
    for item in raw["risks"]:
        fields(item, {"category", "severity", "target_path", "evidence", "description"}, "risk")
        if item["category"] not in RISK_CATEGORIES or item["severity"] not in SEVERITIES:
            raise ContractError("risks", "风险类别或等级非法")
        for key in ("evidence", "description"):
            text(item[key], "risk." + key)
        resolve_path(request, item["target_path"])
    validate_feedback(raw["feedback"], request)
    if raw["recommended_action"] not in ("accept", "regenerate_strategy", "regenerate_creative"):
        raise ContractError("recommended_action", "推荐动作非法")
    return deepcopy(raw)


def validate_config(config):
    fields(config, {"config_version", "pass_threshold", "max_rounds", "timeout_seconds", "max_attempts", "scoring_rule_version"}, "config_snapshot")
    text(config["config_version"], "config_version")
    if type(config["pass_threshold"]) not in (int, float) or not math.isfinite(config["pass_threshold"]) or not 0 <= config["pass_threshold"] <= 100:
        raise ContractError("pass_threshold", "须为0至100有限数值")
    integer(config["max_rounds"], "max_rounds", 1, 3)
    integer(config["max_attempts"], "max_attempts", 1, 3)
    integer(config["timeout_seconds"], "timeout_seconds", 10, 120)
    if config["scoring_rule_version"] != "equal-weight-v1":
        raise ContractError("scoring_rule_version", "仅支持固定五维等权规则equal-weight-v1")
    return deepcopy(config)
