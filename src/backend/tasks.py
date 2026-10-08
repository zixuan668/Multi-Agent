"""第一阶段进程内任务存储；不提供跨重启历史，也不冒充完整系统调度。"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import threading
from uuid import uuid4

from src.agents.strategy.downstream import build_creative_request
from src.agents.strategy.errors import AccessDeniedError, ContractValidationError, ModelUnavailableError
from src.agents.strategy.models import MarketingRequirements, StrategyRequest


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class TaskStore:
    def __init__(self, agent, config: dict):
        self.agent = agent
        self._config = deepcopy(config)
        self._tasks = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="strategy-task")
        self._closed = False

    def create(self, requirements: dict, owner_scope: str) -> dict:
        normalized = MarketingRequirements.from_dict(requirements).to_dict()
        task_id = f"task-{uuid4().hex}"
        task = {"task_id": task_id, "owner_scope": owner_scope, "requirements": normalized, "status": "pending", "stage": "queued", "assessment_status": "not_evaluated", "termination_reason": None, "iteration_count": 0, "selected_evaluation_id": None, "attempt_count": 0, "config_version": self._config["config_version"], "config_snapshot": deepcopy(self._config), "created_at": now(), "updated_at": now(), "result": None, "results": [], "error": None, "events": []}
        with self._lock:
            if self._closed or len(self._tasks) >= 1000:
                raise ModelUnavailableError("第一阶段内存任务容量已满或服务正在关闭，请导出结果并重启服务")
            self._event(task, "pending", 0)
            self._tasks[task_id] = task
            # 响应固定 pending，即使后台很快完成。
            receipt = {"task_id": task_id, "status": "pending", "config_version": task["config_version"]}
            self._executor.submit(self._run, task_id)
        return receipt

    def _event(self, task, stage, attempt):
        task["stage"] = stage
        task["attempt_count"] = attempt
        task["updated_at"] = now()
        task["events"].append({"stage": stage, "attempt_count": attempt, "created_at": task["updated_at"]})

    def _request(self, task):
        return StrategyRequest.from_dict({"schema_version": "1.0", "task_id": task["task_id"], "agent": "strategy", "round_no": 1, "attempt_count": 1, "requirements": deepcopy(task["requirements"]), "strategy": None, "creative": None, "feedback": [], "previous_result": None, "config_version": task["config_version"]})

    def _run(self, task_id):
        with self._lock:
            task = self._tasks[task_id]
            if self._closed:
                return
            task["status"] = "running"
            request = self._request(task)
        def progress(attempt, stage):
            with self._lock:
                if not self._closed and task["status"] == "running" and attempt >= task["attempt_count"]:
                    self._event(task, stage, attempt)
        try:
            result = self.agent.generate(request, on_attempt=progress).to_dict()
            # AC-008 是提交有效版本前的最后一道首轮交付检查。
            if result["status"] == "succeeded":
                build_creative_request(request, result)
            with self._lock:
                if self._closed:
                    return
                task["result"] = result
                task["results"] = self.agent.history(task_id)
                task["error"] = result["error"]
                traces = self.agent.traces(task_id)
                task["attempt_diagnostics"] = [{k: record.get(k) for k in ("attempt_count", "duration_ms", "error_code", "issues")} for record in traces]
                task["review_notes"] = traces[-1].get("review_notes", []) if traces and result["status"] == "succeeded" else []
                task["status"] = "completed" if result["status"] == "succeeded" else "failed"
                task["termination_reason"] = "strategy_completed" if result["status"] == "succeeded" else "technical_error"
                self._event(task, task["status"], result["attempt_count"])
        except Exception:
            with self._lock:
                if not self._closed:
                    task.update(status="failed", termination_reason="technical_error", error={"code": "INTERNAL_ERROR", "message": "任务执行异常，请重新提交；详细信息仅供开发者排查", "field": None, "retryable": False})
                    self._event(task, "failed", task["attempt_count"])

    def get(self, task_id: str, owner_scope: str) -> dict:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None or task["owner_scope"] != owner_scope:
                raise AccessDeniedError("任务不存在或不属于当前演示会话")
            result = deepcopy(task)
            result.pop("owner_scope")
            return result

    def creative_request(self, task_id: str, owner_scope: str) -> dict:
        task = self.get(task_id, owner_scope)
        if task["status"] != "completed" or not task["result"]:
            raise ContractValidationError("策略尚未成功完成，不能交付创意请求")
        return build_creative_request(self._request(task), task["result"])

    def close(self):
        with self._lock:
            self._closed = True
            for task in self._tasks.values():
                if task["status"] in ("pending", "running"):
                    task.update(status="failed", termination_reason="technical_error", error={"code": "INTERNAL_ERROR", "message": "服务中断，请重新提交为新任务", "field": None, "retryable": False})
                    self._event(task, "interrupted", task["attempt_count"])
        self._executor.shutdown(wait=False, cancel_futures=True)
