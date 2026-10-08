"""策略智能体命令行入口。"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from uuid import uuid4

from .errors import ContractValidationError, StrategyAgentError
from .model_clients import CompatibleModelClient, RuleBasedModelClient
from .models import StrategyRequest, MarketingRequirements
from .service import StrategyAgent


def _read_payload(path: str | None) -> dict:
    if path and path != "-":
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("输入顶层必须是 JSON 对象")
    return value


def _wrap_requirements(payload: dict) -> dict:
    if "requirements" in payload:
        return payload
    return {
        "schema_version": "1.0",
        "task_id": f"task-{uuid4().hex}",
        "agent": "strategy",
        "round_no": 1,
        "attempt_count": 1,
        "requirements": MarketingRequirements.from_dict(payload).to_dict(),
        "strategy": None,
        "creative": None,
        "feedback": [],
        "previous_result": None,
        "config_version": "config-v1",
    }


def _model_client(provider: str):
    if provider == "offline":
        return RuleBasedModelClient()
    if provider == "compatible":
        return CompatibleModelClient.from_env()
    return CompatibleModelClient.from_env()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="智策营销策略智能体")
    parser.add_argument("--input", "-i", help="输入 JSON 文件；省略或使用 - 时从标准输入读取")
    parser.add_argument(
        "--provider",
        choices=("offline", "compatible", "auto"),
        default="compatible",
        help="默认真实模型，offline 为显式演示；auto 不再静默回退",
    )
    parser.add_argument("--compact", action="store_true", help="输出紧凑 JSON")
    args = parser.parse_args(argv)

    try:
        payload = _wrap_requirements(_read_payload(args.input))
        strategy_request = StrategyRequest.from_dict(payload)
        response = StrategyAgent(_model_client(args.provider)).generate(strategy_request).to_dict()
    except (OSError, json.JSONDecodeError, ValueError, StrategyAgentError) as exc:
        response = {
            "status": "failed",
            "error": {
                "code": getattr(exc, "code", "INPUT_INVALID"),
                "message": str(exc),
                "field": getattr(exc, "field", None),
                "retryable": False,
            },
        }
    print(json.dumps(response, ensure_ascii=False, indent=None if args.compact else 2))
    return 0 if response.get("status") == "succeeded" else 2
