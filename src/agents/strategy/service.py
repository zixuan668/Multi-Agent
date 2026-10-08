"""营销策略智能体主流程、重试、版本和响应封装。"""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
from datetime import datetime, timezone
import json
import logging
import re
import threading
import time
import queue
from typing import Callable
from uuid import uuid4

from .errors import (
    ContractValidationError,
    ModelInternalError,
    ModelOutputError,
    StrategyAgentError,
    ModelTimeoutError,
    ModelUnavailableError,
)
from .model_clients import ModelClient
from .models import StrategyData, StrategyRequest, StrategyResponse
from .prompts import PromptBuilder
from .validation import validate_business_rules, validate_strategy_quality
from .repair import discard_unknown_output_fields, mark_planning_inferences, repair_only_reported_fields


logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    delays_seconds: tuple[float, ...] = (1.0, 2.0)

    def delay_after(self, attempt_count: int) -> float:
        index = attempt_count - 1
        return self.delays_seconds[index] if 0 <= index < len(self.delays_seconds) else 0.0


class StrategyAgent:
    def __init__(
        self,
        model_client: ModelClient,
        *,
        prompt_builder: PromptBuilder | None = None,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        self.model_client = model_client
        self.prompt_builder = prompt_builder or PromptBuilder()
        self.retry_policy = retry_policy or RetryPolicy()
        self.sleeper = sleeper
        self._versions: dict[str, int] = {}
        self._version_lock = threading.Lock()
        self._task_locks: dict[str, threading.Lock] = {}
        self._inputs: dict[str, dict] = {}
        self._results: dict[str, list[dict]] = {}
        self._traces: dict[str, list[dict]] = {}
        self._model_slots = threading.BoundedSemaphore(5)

    def generate(self, request: StrategyRequest, *, on_attempt: Callable | None = None) -> StrategyResponse:
        # 重新验证防止调用方修改 frozen dataclass 中的嵌套对象。
        request = StrategyRequest.from_dict(request.to_dict())
        with self._version_lock:
            lock = self._task_locks.setdefault(request.task_id, threading.Lock())
        with lock:
            original = {"requirements": request.requirements.to_dict(), "config_version": request.config_version}
            existing = self._inputs.get(request.task_id)
            if existing is not None and existing != original:
                return self._failure_response(request, ContractValidationError("同任务原始需求与配置不可修改"), request.attempt_count)
            history = self._results.get(request.task_id, [])
            if request.previous_result is not None and (not history or request.previous_result != history[-1]):
                return self._failure_response(request, ContractValidationError("previous_result 不属于服务端保存的上一有效版本"), request.attempt_count)
            self._inputs[request.task_id] = deepcopy(original)
            response = self._generate(request, on_attempt=on_attempt)
            StrategyResponse.from_dict(response.to_dict(), task_id=request.task_id)
            if response.value["status"] == "succeeded":
                with self._version_lock:
                    self._results.setdefault(request.task_id, []).append(response.to_dict())
            return response

    def history(self, task_id: str) -> list[dict]:
        with self._version_lock:
            return deepcopy(self._results.get(task_id, []))

    def traces(self, task_id: str) -> list[dict]:
        with self._version_lock:
            return deepcopy(self._traces.get(task_id, []))

    def _execute_attempt(self, request: StrategyRequest, prompt, on_attempt=None, attempt=1, previous_raw=None, repair_issues=None) -> tuple[StrategyData, dict]:
        """生成和语义复核共享一次尝试的总超时；迟到线程不得提交版本。"""
        output = queue.Queue(maxsize=1)
        active = threading.Event()
        active.set()
        def stage(name):
            if on_attempt and active.is_set():
                on_attempt(attempt, name)
        if not self._model_slots.acquire(blocking=False):
            raise ModelUnavailableError("模型调用达到并发上限，可能仍有超时请求待释放，请稍后重试")
        def run():
            trace = {"raw_output": None, "review_output": None}
            try:
                trace["raw_output"] = self.model_client.generate_json(prompt)
                if not active.is_set():
                    raise ModelTimeoutError("本次尝试已超时，不再发起内容复核")
                stage("validating")
                candidate = self._parse_json_object(trace["raw_output"])
                candidate, discarded = discard_unknown_output_fields(candidate)
                if discarded:
                    trace["discarded_fields"] = discarded
                if previous_raw and repair_issues:
                    try:
                        previous = self._parse_json_object(previous_raw)
                        candidate = repair_only_reported_fields(previous, candidate, repair_issues)
                    except ModelOutputError:
                        pass  # 非JSON的上一输出只能完整重生成。
                data = StrategyData.from_dict(candidate)
                # 原始模型输出与实际复核的候选对象分别保留，便于真实问题追溯。
                data = StrategyData.from_dict(mark_planning_inferences(data.to_dict()))
                trace["candidate_output"] = json.dumps(data.to_dict(), ensure_ascii=False)
                business_issues = validate_business_rules(data, request)
                findings = [{"field": "business_rules", "message": issue, "category": "constraint", "severity": "blocking"} for issue in business_issues]
                if not getattr(self.model_client, "refine_strategy", None):
                    findings.extend(validate_strategy_quality(data, request))
                if findings:
                    raise ModelOutputError("策略存在事实、约束或明确的可执行性缺口", issues=findings)
                refine = getattr(self.model_client, "refine_strategy", None)
                review = getattr(self.model_client, "review_strategy", None)
                if refine:
                    if not active.is_set():
                        raise ModelTimeoutError("本次尝试已超时，不再发起策略编辑")
                    stage("reviewing")
                    trace["draft_output"] = trace["candidate_output"]
                    refined, issues, trace["review_output"] = refine(request.requirements.to_dict(), data.to_dict())
                    refined, discarded = discard_unknown_output_fields(refined)
                    if discarded:
                        trace["discarded_refined_fields"] = discarded
                    data = StrategyData.from_dict(mark_planning_inferences(refined))
                    trace["candidate_output"] = json.dumps(data.to_dict(), ensure_ascii=False)
                    business_issues = validate_business_rules(data, request)
                    findings = [{"field": "business_rules", "message": issue, "category": "constraint", "severity": "blocking"} for issue in business_issues]
                    findings.extend(validate_strategy_quality(data, request))
                    for item in issues:
                        field = item.get("field", "")
                        evidence = item.get("evidence", "")
                        # 已记录的信息缺口和明确的执行前核实，不是策略违规。
                        if field.startswith(("missing_information", "assumptions")) or (
                            field.startswith("channels[") and ".content_direction" in field and re.search(r"核实|确认", evidence)
                        ):
                            item = {**item, "category": "quality", "severity": "advisory"}
                        findings.append(item)
                    trace["review_notes"] = [item for item in findings if item.get("category") == "quality" and item.get("severity") == "advisory"]
                    blocking = [item for item in findings if item not in trace["review_notes"]]
                    if blocking:
                        raise ModelOutputError("策略编辑后仍有事实、约束或交付质量问题", issues=blocking)
                elif review:
                    if not active.is_set():
                        raise ModelTimeoutError("本次尝试已超时，不再发起内容复核")
                    stage("reviewing")
                    issues, trace["review_output"] = review(request.requirements.to_dict(), data.to_dict())
                    # 旧式测试/自定义客户端的字符串意见保守视为阻断。
                    findings = [{"field": "content_review", "message": i, "category": "fact", "severity": "blocking"} if isinstance(i, str) else i for i in issues]
                    trace["review_notes"] = [i for i in findings if i.get("category") == "quality" and i.get("severity") == "advisory"]
                    blocking = [i for i in findings if i not in trace["review_notes"]]
                    if blocking:
                        raise ModelOutputError("内容复核发现事实或约束问题", issues=blocking)
                output.put((data, trace, None))
            except Exception as exc:
                output.put((None, trace, exc))
            finally:
                self._model_slots.release()
        threading.Thread(target=run, daemon=True).start()
        try:
            base_timeout = getattr(self.model_client, "timeout_seconds", 60.0)
            attempt_timeout = min(base_timeout * 2, 120.0) if getattr(self.model_client, "refine_strategy", None) else base_timeout
            data, trace, error = output.get(timeout=attempt_timeout)
        except queue.Empty:
            raise ModelTimeoutError("策略生成与内容复核达到本次调用超时，请稍后重试") from None
        finally:
            active.clear()
        if error is not None:
            error.attempt_trace = trace
            raise error
        return data, trace

    def _generate(self, request: StrategyRequest, *, on_attempt: Callable | None = None) -> StrategyResponse:
        attempt = request.attempt_count
        feedback: list[str] | None = None
        previous_raw: str | None = None
        last_error: StrategyAgentError | None = None
        repair_issues = None

        while attempt <= self.retry_policy.max_attempts:
            started_at = time.monotonic()
            raw: str | None = None
            trace = {}
            if on_attempt:
                on_attempt(attempt, "generating")
            logger.info(
                "strategy_call_started task_id=%s round_no=%s attempt=%s config_version=%s",
                request.task_id,
                request.round_no,
                attempt,
                request.config_version,
            )
            try:
                prompt = self.prompt_builder.build(request, attempt_count=attempt, validation_feedback=feedback, previous_raw_output=previous_raw)
                data, trace = self._execute_attempt(request, prompt, on_attempt, attempt, previous_raw, repair_issues)
                response = self._success_response(request, data, attempt)
                self._save_trace(request, attempt, trace, started_at, None)
                logger.info(
                    "strategy_call_succeeded task_id=%s round_no=%s attempt=%s duration_ms=%s",
                    request.task_id,
                    request.round_no,
                    attempt,
                    round((time.monotonic() - started_at) * 1000),
                )
                return response
            except ContractValidationError as exc:
                trace = getattr(exc, "attempt_trace", {})
                raw = trace.get("raw_output")
                last_error = ModelOutputError(str(exc))
                feedback = exc.issues
                trace["issues"] = [{"field": "output", "message": i, "category": "structure", "severity": "blocking"} for i in exc.issues]
                previous_raw = raw
                repair_issues = None
            except ModelOutputError as exc:
                trace = getattr(exc, "attempt_trace", {})
                raw = trace.get("candidate_output") or trace.get("raw_output")
                last_error = exc
                trace["issues"] = exc.issues
                feedback = [f"{i.get('field', 'output')}: {i['message']}" for i in exc.issues]
                previous_raw = raw
                repair_issues = exc.issues
            except StrategyAgentError as exc:
                trace = getattr(exc, "attempt_trace", {})
                last_error = exc
                feedback = [str(exc)]
                previous_raw = None
                repair_issues = None
            except Exception:
                last_error = ModelInternalError("策略智能体发生未预期内部错误")
                feedback = [str(last_error)]
                previous_raw = None

            assert last_error is not None
            self._save_trace(request, attempt, trace, started_at, last_error.code)
            logger.warning(
                "strategy_call_failed task_id=%s round_no=%s attempt=%s code=%s retryable=%s duration_ms=%s",
                request.task_id,
                request.round_no,
                attempt,
                last_error.code,
                last_error.retryable,
                round((time.monotonic() - started_at) * 1000),
            )
            if not last_error.retryable or attempt >= self.retry_policy.max_attempts:
                return self._failure_response(request, last_error, attempt)
            delay = self.retry_policy.delay_after(attempt)
            if on_attempt:
                on_attempt(attempt, "retrying")
            if delay > 0:
                self.sleeper(delay)
            attempt += 1

        return self._failure_response(
            request,
            last_error or ModelInternalError("策略智能体未产生结果"),
            attempt,
        )

    @staticmethod
    def _parse_json_object(raw: str) -> dict:
        text = raw.strip()
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            raise ModelOutputError("模型必须只输出 JSON 对象，不接受说明文本或代码围栏") from None
        if not isinstance(value, dict):
            raise ModelOutputError("模型输出顶层必须是 JSON 对象")
        return value

    def _next_version(self, request: StrategyRequest) -> int:
        with self._version_lock:
            current = self._versions.get(request.task_id, 0)
            version = current + 1
            self._versions[request.task_id] = version
            return version

    def _save_trace(self, request, attempt, trace, started_at, error_code):
        secret = getattr(self.model_client, "api_key", None)
        if secret:
            trace = json.loads(json.dumps(trace, ensure_ascii=False).replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]"))
        record = {**deepcopy(trace), "task_id": request.task_id, "round_no": request.round_no, "attempt_count": attempt, "config_version": request.config_version, "prompt_version": self.prompt_builder.version, "prompt_sha256": self.prompt_builder.sha256, "duration_ms": round((time.monotonic() - started_at) * 1000), "error_code": error_code}
        with self._version_lock:
            self._traces.setdefault(request.task_id, []).append(record)

    def _success_response(
        self,
        request: StrategyRequest,
        data: StrategyData,
        attempt: int,
    ) -> StrategyResponse:
        return StrategyResponse(
            {
                "schema_version": request.schema_version,
                "task_id": request.task_id,
                "agent": "strategy",
                "round_no": request.round_no,
                "attempt_count": attempt,
                "status": "succeeded",
                "result_id": f"strategy-{uuid4().hex}",
                "version": self._next_version(request),
                "data": data.to_dict(),
                "error": None,
                "created_at": self._now(),
            }
        )

    def _failure_response(
        self,
        request: StrategyRequest,
        error: StrategyAgentError,
        attempt: int,
    ) -> StrategyResponse:
        return StrategyResponse(
            {
                "schema_version": request.schema_version,
                "task_id": request.task_id,
                "agent": "strategy",
                "round_no": request.round_no,
                "attempt_count": min(attempt, self.retry_policy.max_attempts),
                "status": "failed",
                "result_id": None,
                "version": None,
                "data": None,
                "error": {
                    "code": error.code,
                    "message": self._user_message(error),
                    "field": getattr(error, "field", None),
                    "retryable": error.retryable,
                },
                "created_at": self._now(),
            }
        )

    @staticmethod
    def _user_message(error: StrategyAgentError) -> str:
        if error.code == "OUTPUT_INVALID":
            return "模型结果仍有事实或格式问题，自动修复未成功。本次没有生成有效策略，请查看问题详情。"
        return str(error) or "策略生成失败，请根据错误码检查配置后重试"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
