"""AC-008：创意首轮输入校验，不实现创意生成。"""
from copy import deepcopy

from .errors import ContractValidationError
from .models import MarketingRequirements, StrategyResponse
from .validation import validate_business_rules, validate_strategy_quality
from .models import StrategyRequest
from .models import StrategyData


def validate_creative_request(payload: dict) -> dict:
    fields = {"schema_version", "task_id", "agent", "round_no", "attempt_count", "requirements", "strategy", "creative", "feedback", "previous_result", "config_version"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ContractValidationError("creative request 字段不完整或包含未声明字段")
    if payload["schema_version"] != "1.0" or payload["agent"] != "creative":
        raise ContractValidationError("creative request schema_version/agent 不合法")
    if payload["round_no"] != 1 or type(payload["round_no"]) is not int or payload["attempt_count"] != 1 or type(payload["attempt_count"]) is not int:
        raise ContractValidationError("此校验器仅支持创意首轮首次请求")
    if payload["creative"] is not None or payload["previous_result"] is not None or payload["feedback"] != []:
        raise ContractValidationError("首轮 creative/previous_result 必须为 null，feedback 为 []")
    response = StrategyResponse.from_dict(payload["strategy"], task_id=payload["task_id"])
    if response.value["status"] != "succeeded":
        raise ContractValidationError("创意输入不能使用失败策略")
    MarketingRequirements.from_dict(payload["requirements"])
    check = deepcopy(payload)
    check.update(agent="strategy", strategy=None)
    strategy_request = StrategyRequest.from_dict(check)
    issues = validate_business_rules(StrategyData.from_dict(response.value["data"]), strategy_request)
    issues.extend(item["message"] for item in validate_strategy_quality(StrategyData.from_dict(response.value["data"]), strategy_request))
    if issues:
        raise ContractValidationError(issues)
    return deepcopy(payload)


def build_creative_request(request: StrategyRequest, response: dict) -> dict:
    if request.round_no != 1:
        raise ContractValidationError("当前下游适配器仅交付创意首轮请求")
    payload = request.to_dict()
    payload.update(agent="creative", strategy=deepcopy(response), attempt_count=1)
    return validate_creative_request(payload)
