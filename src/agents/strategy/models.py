"""FR-001 至 FR-004 对应的数据契约与基础校验。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from copy import deepcopy
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .errors import ContractValidationError


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field} 必须是对象")
    return value


def _string(
    value: Any,
    field: str,
    *,
    required: bool = True,
    max_length: int | None = None,
) -> str | None:
    if value is None:
        if required:
            raise ContractValidationError(f"{field} 为必填字段")
        return None
    if not isinstance(value, str):
        raise ContractValidationError(f"{field} 必须是字符串")
    value = value.strip()
    if not value:
        if required:
            raise ContractValidationError(f"{field} 不能为空白")
        return None
    if max_length is not None and len(value) > max_length:
        raise ContractValidationError(f"{field} 最多 {max_length} 字")
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], field: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ContractValidationError(f"{field} 包含未声明字段: {', '.join(unknown)}")


def _decimal_number(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ContractValidationError(f"{field} 必须是数值")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ContractValidationError(f"{field} 必须是有限数值") from None
    if not result.is_finite():
        raise ContractValidationError(f"{field} 必须是有限数值")
    return result


def _number_for_json(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    return float(value)


@dataclass(frozen=True)
class Budget:
    amount: Decimal
    currency: str

    @classmethod
    def from_dict(cls, raw: Any) -> "Budget":
        data = _mapping(raw, "requirements.budget")
        _reject_unknown(data, {"amount", "currency"}, "requirements.budget")
        amount = _decimal_number(data.get("amount"), "requirements.budget.amount")
        if amount < 0 or amount > Decimal("100000000"):
            raise ContractValidationError("requirements.budget.amount 必须在 0 至 100000000 之间")
        if -amount.as_tuple().exponent > 2:
            raise ContractValidationError("requirements.budget.amount 最多保留 2 位小数")
        currency = _string(data.get("currency"), "requirements.budget.currency")
        assert currency is not None
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ContractValidationError("requirements.budget.currency 必须是 3 位大写英文字母")
        return cls(amount=amount, currency=currency)

    def to_dict(self) -> dict[str, Any]:
        return {"amount": _number_for_json(self.amount), "currency": self.currency}


@dataclass(frozen=True)
class CampaignPeriod:
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int | None = None

    @classmethod
    def from_dict(cls, raw: Any) -> "CampaignPeriod":
        data = _mapping(raw, "requirements.campaign_period")
        _reject_unknown(data, {"start_date", "end_date", "duration_days"}, "requirements.campaign_period")
        start = _string(data.get("start_date"), "requirements.campaign_period.start_date", required=False)
        end = _string(data.get("end_date"), "requirements.campaign_period.end_date", required=False)
        duration = data.get("duration_days")
        has_dates = start is not None or end is not None
        has_duration = duration is not None
        if has_dates and has_duration:
            raise ContractValidationError("campaign_period 的日期对与 duration_days 不能同时提供")
        if has_dates:
            if start is None or end is None:
                raise ContractValidationError("campaign_period 必须同时提供 start_date 和 end_date")
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
                    raise ValueError("invalid format")
                start_value = date.fromisoformat(start)
                end_value = date.fromisoformat(end)
            except ValueError:
                raise ContractValidationError("campaign_period 日期必须使用 YYYY-MM-DD") from None
            if end_value < start_value:
                raise ContractValidationError("campaign_period.end_date 不得早于 start_date")
            return cls(start_date=start, end_date=end)
        if has_duration:
            if isinstance(duration, bool) or not isinstance(duration, int) or not 1 <= duration <= 365:
                raise ContractValidationError("campaign_period.duration_days 必须是 1 至 365 的整数")
            return cls(duration_days=duration)
        raise ContractValidationError("campaign_period 必须提供日期对或 duration_days")

    def to_dict(self) -> dict[str, Any]:
        if self.duration_days is not None:
            return {"duration_days": self.duration_days}
        return {"start_date": self.start_date, "end_date": self.end_date}


@dataclass(frozen=True)
class MarketingRequirements:
    product_name: str
    product_description: str
    marketing_goal: str
    target_audience: str | None = None
    budget: Budget | None = None
    campaign_period: CampaignPeriod | None = None
    special_requirements: str | None = None
    budget_raw: str | None = None

    @classmethod
    def from_dict(cls, raw: Any) -> "MarketingRequirements":
        data = _mapping(raw, "requirements")
        allowed = {
            "product_name",
            "product_description",
            "marketing_goal",
            "target_audience",
            "budget",
            "campaign_period",
            "special_requirements",
            "budget_raw",
        }
        _reject_unknown(data, allowed, "requirements")
        product_name = _string(data.get("product_name"), "requirements.product_name", max_length=100)
        description = _string(
            data.get("product_description"),
            "requirements.product_description",
            max_length=5000,
        )
        goal = _string(data.get("marketing_goal"), "requirements.marketing_goal", max_length=500)
        audience = _string(
            data.get("target_audience"),
            "requirements.target_audience",
            required=False,
            max_length=1000,
        )
        special = _string(
            data.get("special_requirements"),
            "requirements.special_requirements",
            required=False,
            max_length=2000,
        )
        budget_raw = _string(
            data.get("budget_raw"),
            "requirements.budget_raw",
            required=False,
            max_length=200,
        )
        budget = None if data.get("budget") is None else Budget.from_dict(data["budget"])
        if budget_raw and budget is None:
            raise ContractValidationError("requirements.budget_raw 无对应可解析 budget，请填写金额和币种后提交")
        period = None if data.get("campaign_period") is None else CampaignPeriod.from_dict(data["campaign_period"])
        assert product_name and description and goal
        return cls(product_name, description, goal, audience, budget, period, special, budget_raw)

    def to_dict(self) -> dict[str, Any]:
        return {
            "product_name": self.product_name,
            "product_description": self.product_description,
            "marketing_goal": self.marketing_goal,
            "target_audience": self.target_audience,
            "budget": self.budget.to_dict() if self.budget else None,
            "campaign_period": self.campaign_period.to_dict() if self.campaign_period else None,
            "special_requirements": self.special_requirements,
            "budget_raw": self.budget_raw,
        }

    def source_text(self) -> str:
        values = [
            self.product_name,
            self.product_description,
            self.marketing_goal,
            self.target_audience,
            self.special_requirements,
            self.budget_raw,
        ]
        return "\n".join(value for value in values if value)


@dataclass(frozen=True)
class StrategyRequest:
    schema_version: str
    task_id: str
    agent: str
    round_no: int
    attempt_count: int
    requirements: MarketingRequirements
    strategy: None
    creative: None
    feedback: tuple[dict[str, Any], ...]
    previous_result: dict[str, Any] | None
    config_version: str

    @classmethod
    def from_dict(cls, raw: Any) -> "StrategyRequest":
        data = _mapping(raw, "request")
        allowed = {
            "schema_version",
            "task_id",
            "agent",
            "round_no",
            "attempt_count",
            "requirements",
            "strategy",
            "creative",
            "feedback",
            "previous_result",
            "config_version",
        }
        _reject_unknown(data, allowed, "request")
        if allowed - set(data):
            raise ContractValidationError(f"request 缺少字段: {', '.join(sorted(allowed - set(data)))}")
        normalized_fields = {"product_name", "product_description", "marketing_goal", "target_audience", "budget", "campaign_period", "special_requirements", "budget_raw"}
        if normalized_fields - set(_mapping(data.get("requirements"), "requirements")):
            raise ContractValidationError("智能体请求 requirements 必须包含全部规范化字段，可空字段使用 null")
        schema = _string(data.get("schema_version"), "schema_version")
        if schema != "1.0":
            raise ContractValidationError("schema_version 固定为 1.0")
        task_id = _string(data.get("task_id"), "task_id")
        agent = _string(data.get("agent"), "agent")
        if agent != "strategy":
            raise ContractValidationError("策略请求的 agent 必须为 strategy")
        round_no = data.get("round_no")
        if isinstance(round_no, bool) or not isinstance(round_no, int) or not 1 <= round_no <= 3:
            raise ContractValidationError("round_no 必须是 1 至 3 的整数")
        attempt_count = data.get("attempt_count")
        if isinstance(attempt_count, bool) or not isinstance(attempt_count, int) or not 1 <= attempt_count <= 3:
            raise ContractValidationError("attempt_count 必须是 1 至 3 的整数")
        if data.get("strategy") is not None or data.get("creative") is not None:
            raise ContractValidationError("策略请求的 strategy 和 creative 必须为 null")
        feedback_raw = data.get("feedback", [])
        if not isinstance(feedback_raw, list) or not all(isinstance(item, Mapping) for item in feedback_raw):
            raise ContractValidationError("feedback 必须是对象数组")
        previous = data.get("previous_result")
        if previous is not None and not isinstance(previous, Mapping):
            raise ContractValidationError("previous_result 必须是对象或 null")
        config_version = _string(data.get("config_version"), "config_version")
        validate_feedback(feedback_raw)
        if previous is not None:
            StrategyResponse.from_dict(previous, task_id=task_id)
            if previous["status"] != "succeeded" or previous["round_no"] > round_no:
                raise ContractValidationError("previous_result 必须是同任务的上一有效策略响应")
        if round_no == 1 and (feedback_raw or previous is not None):
            raise ContractValidationError("首轮 feedback 必须为空且 previous_result 必须为 null")
        if round_no > 1 and previous is None:
            raise ContractValidationError("策略优化必须提供 previous_result")
        assert task_id and agent and config_version
        return cls(
            schema,
            task_id,
            agent,
            round_no,
            attempt_count,
            MarketingRequirements.from_dict(data.get("requirements")),
            None,
            None,
            tuple(deepcopy(item) for item in feedback_raw),
            deepcopy(previous),
            config_version,
        )

    def to_dict(self, *, attempt_count: int | None = None) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "task_id": self.task_id,
            "agent": self.agent,
            "round_no": self.round_no,
            "attempt_count": attempt_count or self.attempt_count,
            "requirements": self.requirements.to_dict(),
            "strategy": None,
            "creative": None,
            "feedback": deepcopy(list(self.feedback)),
            "previous_result": deepcopy(self.previous_result),
            "config_version": self.config_version,
        }


@dataclass(frozen=True)
class StrategyData:
    value: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: Any) -> "StrategyData":
        def normalize(item):
            if isinstance(item, str):
                return item.strip()
            if isinstance(item, list):
                return [normalize(value) for value in item]
            if isinstance(item, Mapping):
                return {key: normalize(value) for key, value in item.items()}
            return item
        data = normalize(deepcopy(dict(_mapping(raw, "data"))))
        required = {
            "target_audience",
            "positioning",
            "selling_points",
            "channels",
            "marketing_strategy",
            "assumptions",
            "missing_information",
            "constraint_conflicts",
        }
        _reject_unknown(data, required, "data")
        missing = sorted(required - set(data))
        if missing:
            raise ContractValidationError(f"data 缺少字段: {', '.join(missing)}")

        audience = dict(_mapping(data["target_audience"], "data.target_audience"))
        audience_fields = {"segment", "needs", "pain_points", "age_range", "occupation", "basis"}
        _reject_unknown(audience, audience_fields, "data.target_audience")
        if audience_fields - set(audience):
            raise ContractValidationError("data.target_audience 字段不完整")
        for field in ("segment", "basis"):
            _string(audience[field], f"data.target_audience.{field}", max_length=1000)
        for field in ("age_range", "occupation"):
            if audience[field] is not None:
                _string(audience[field], f"data.target_audience.{field}", max_length=1000)
        for field in ("needs", "pain_points"):
            cls._string_list(audience[field], f"data.target_audience.{field}", minimum=1)

        _string(data["positioning"], "data.positioning", max_length=500)
        selling_points = data["selling_points"]
        if not isinstance(selling_points, list) or not 1 <= len(selling_points) <= 5:
            raise ContractValidationError("data.selling_points 必须包含 1 至 5 项")
        for index, item in enumerate(selling_points):
            point = _mapping(item, f"data.selling_points[{index}]")
            _reject_unknown(point, {"claim", "source_quote"}, f"data.selling_points[{index}]")
            _string(point.get("claim"), f"data.selling_points[{index}].claim", max_length=1000)
            _string(point.get("source_quote"), f"data.selling_points[{index}].source_quote", max_length=1000)

        channels = data["channels"]
        if not isinstance(channels, list) or not 1 <= len(channels) <= 5:
            raise ContractValidationError("data.channels 必须包含 1 至 5 项")
        for index, item in enumerate(channels):
            channel = _mapping(item, f"data.channels[{index}]")
            allowed = {"name", "reason", "content_direction", "allocated_amount"}
            _reject_unknown(channel, allowed, f"data.channels[{index}]")
            if allowed - set(channel):
                raise ContractValidationError(f"data.channels[{index}] 字段不完整")
            for field in ("name", "reason", "content_direction"):
                _string(channel[field], f"data.channels[{index}].{field}", max_length=1000)
            if channel["allocated_amount"] is not None:
                amount = _decimal_number(channel["allocated_amount"], f"data.channels[{index}].allocated_amount")
                if amount < 0:
                    raise ContractValidationError(f"data.channels[{index}].allocated_amount 不得为负数")

        marketing = _mapping(data["marketing_strategy"], "data.marketing_strategy")
        fields = {"theme", "content_directions", "promotion_methods"}
        _reject_unknown(marketing, fields, "data.marketing_strategy")
        if fields - set(marketing):
            raise ContractValidationError("data.marketing_strategy 字段不完整")
        _string(marketing["theme"], "data.marketing_strategy.theme", max_length=1000)
        cls._string_list(marketing["content_directions"], "data.marketing_strategy.content_directions", minimum=1)
        cls._string_list(marketing["promotion_methods"], "data.marketing_strategy.promotion_methods", minimum=1)
        for field in ("assumptions", "missing_information", "constraint_conflicts"):
            cls._string_list(data[field], f"data.{field}", minimum=0)
        return cls(data)

    @staticmethod
    def _string_list(raw: Any, field: str, *, minimum: int) -> None:
        if not isinstance(raw, list) or not minimum <= len(raw) <= 10:
            raise ContractValidationError(f"{field} 必须包含 {minimum} 至 10 项")
        for index, value in enumerate(raw):
            _string(value, f"{field}[{index}]", max_length=1000)

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.value)


@dataclass(frozen=True)
class StrategyResponse:
    value: dict[str, Any]

    @classmethod
    def from_dict(cls, raw: Any, *, task_id: str | None = None) -> "StrategyResponse":
        value = dict(_mapping(raw, "response"))
        fields = {"schema_version", "task_id", "agent", "round_no", "attempt_count", "status", "result_id", "version", "data", "error", "created_at"}
        if set(value) != fields:
            raise ContractValidationError("response 字段不完整或含未声明字段")
        if value["schema_version"] != "1.0" or value["agent"] != "strategy":
            raise ContractValidationError("response schema_version/agent 不合法")
        _string(value["task_id"], "response.task_id")
        if task_id is not None and value["task_id"] != task_id:
            raise ContractValidationError("response.task_id 与当前任务不一致")
        for field in ("round_no", "attempt_count"):
            if type(value[field]) is not int or not 1 <= value[field] <= 3:
                raise ContractValidationError(f"response.{field} 必须是 1 至 3 的整数")
        try:
            stamp = datetime.fromisoformat(value["created_at"].replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ContractValidationError("response.created_at 必须是带时区的 ISO 8601 时间") from None
        if value["status"] == "succeeded":
            _string(value["result_id"], "response.result_id")
            if type(value["version"]) is not int or value["version"] < 1 or value["error"] is not None:
                raise ContractValidationError("成功响应的 version/error 不合法")
            StrategyData.from_dict(value["data"])
        elif value["status"] == "failed":
            if any(value[field] is not None for field in ("result_id", "version", "data")):
                raise ContractValidationError("失败响应 result_id/version/data 必须为 null")
            error = _mapping(value["error"], "response.error")
            if set(error) != {"code", "message", "field", "retryable"} or type(error["retryable"]) is not bool:
                raise ContractValidationError("response.error 不合法")
            for field in ("code", "message"):
                _string(error[field], f"response.error.{field}")
            _string(error["field"], "response.error.field", required=False)
        else:
            raise ContractValidationError("response.status 不合法")
        return cls(deepcopy(value))

    def to_dict(self) -> dict[str, Any]:
        return deepcopy(self.value)


def validate_feedback(items: list) -> None:
    fields = {"feedback_id", "evaluation_id", "target_agent", "target_path", "issue", "suggestion", "priority", "resolved"}
    for index, item in enumerate(items):
        if not isinstance(item, Mapping) or set(item) != fields:
            raise ContractValidationError(f"feedback[{index}] 字段不符合附录 C.6")
        for field in ("feedback_id", "evaluation_id", "target_path", "issue", "suggestion"):
            _string(item[field], f"feedback[{index}].{field}", max_length=1000)
        if item["target_agent"] not in ("strategy", "creative") or item["priority"] not in ("low", "medium", "high") or type(item["resolved"]) is not bool:
            raise ContractValidationError(f"feedback[{index}] 类型或枚举不合法")
