"""营销策略智能体错误类型。"""

from __future__ import annotations
import re


class StrategyAgentError(Exception):
    """智能体可识别的基础错误。"""

    code = "INTERNAL_ERROR"
    retryable = False


class ContractValidationError(StrategyAgentError):
    """输入或模型输出不符合数据契约。"""

    code = "INPUT_INVALID"

    def __init__(self, issues: list[str] | str):
        self.issues = [issues] if isinstance(issues, str) else issues
        match = re.match(r"(requirements(?:\.[\w.\[\]]+)?|campaign_period(?:\.[\w.\[\]]+)?|schema_version|round_no|attempt_count|previous_result|feedback(?:\[\d+\])?)\s", self.issues[0])
        self.field = match.group(1) if match else None
        if self.field and self.field.startswith("campaign_period"):
            self.field = "requirements." + self.field
        super().__init__("; ".join(self.issues))


class ModelTimeoutError(StrategyAgentError):
    code = "MODEL_TIMEOUT"
    retryable = True


class ModelUnavailableError(StrategyAgentError):
    code = "MODEL_UNAVAILABLE"
    retryable = True


class ModelAuthError(StrategyAgentError):
    code = "MODEL_AUTH_FAILED"


class ModelOutputError(StrategyAgentError):
    code = "OUTPUT_INVALID"
    retryable = True

    def __init__(self, message: str, *, issues: list | None = None):
        self.issues = issues or [{"field": "output", "message": message, "category": "structure", "severity": "blocking"}]
        super().__init__(message)


class ModelInternalError(StrategyAgentError):
    code = "INTERNAL_ERROR"


class ConfigurationError(StrategyAgentError):
    code = "CONFIG_INVALID"


class AccessDeniedError(StrategyAgentError):
    code = "ACCESS_DENIED"
