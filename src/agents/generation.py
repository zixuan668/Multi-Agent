from pathlib import Path
import json

from src.agents.strategy.errors import ContractValidationError, ModelOutputError, StrategyAgentError


def prompt_text(agent):
    return (Path(__file__).resolve().parents[2] / "prompts" / agent / "v1.1.txt").read_text(encoding="utf-8")


def generate_validated(client, system, request, validator, *, check, progress, max_attempts=3, context=None):
    correction = None
    for attempt in range(1, max_attempts + 1):
        check()
        progress(attempt)
        payload = {"request": request, "validation_feedback": correction}
        if context is not None:
            payload["context"] = context
        try:
            data = client.complete_json(system, json.dumps(payload, ensure_ascii=False))
            check()
            return validator(data, request), attempt
        except (ContractValidationError, ModelOutputError, ValueError, TypeError, KeyError, AttributeError) as error:
            correction = str(error)[:2000]
            if attempt == max_attempts:
                raise ModelOutputError("内容未通过结构或原文证据校验，已保留上游结果，可重试此阶段") from None
        except StrategyAgentError as error:
            if not error.retryable or attempt == max_attempts:
                raise
    raise ModelOutputError("内容生成失败")
