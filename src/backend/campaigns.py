from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import threading
import time
from pathlib import Path
from uuid import uuid4

from src.agents.creative import CreativeAgent
from src.agents.evaluation.agent import EvaluationAgent
from src.agents.generation import prompt_text
from src.agents.strategy.errors import ContractValidationError, ModelUnavailableError, StrategyAgentError
from src.agents.strategy.model_clients import CompatibleModelClient, RuleBasedModelClient
from src.agents.strategy.models import MarketingRequirements, StrategyRequest
from src.agents.strategy.prompts import PromptBuilder
from src.agents.strategy.service import StrategyAgent
from src.contracts.campaign import compact, handoff, locate, now
from .persistence import CampaignRepository
from .collaboration import PHASES, public_excerpt, result_message
from .briefing import brief_questions, partition_draft_questions


TERMINAL = {"awaiting_confirmation", "awaiting_direction", "awaiting_revision", "awaiting_input", "needs_revision", "needs_review", "approved", "cancelled"}


class ExecutionStopped(StrategyAgentError):
    code = "TASK_CANCELLED"


class ExecutionLimit(StrategyAgentError):
    code = "EXECUTION_LIMIT"


def event(task, agent, kind, message, **details):
    task["updated_at"] = now()
    task["events"].append({"event_id": uuid4().hex, "time": task["updated_at"], "round_no": task.get("round_no", 1), "agent": agent, "kind": kind, "message": message, **details})


def choose_version(rows):
    candidates = [row for row in rows if row.get("evaluation")]
    if not candidates:
        return None
    def rank(row):
        data = row["evaluation"]["data"]
        return (sum(risk["severity"] == "high" for risk in data["risks"]), sum(risk["severity"] == "medium" for risk in data["risks"]), -data["total_score"], -row["round_no"])
    safe = [row for row in candidates if not any(risk["severity"] == "high" for risk in row["evaluation"]["data"]["risks"])]
    return max(safe, key=lambda row: (row["evaluation"]["data"]["total_score"], row["round_no"])) if safe else min(candidates, key=rank)


def public_task(task):
    result = deepcopy(task)
    result.pop("owner_scope", None)
    result.pop("submission_key", None)
    for job in result.get('image_jobs', []):
        for key in list(job):
            if key.startswith('_'):
                job.pop(key)
    if result["selected_round"] is None and result["status"] in ("failed", "interrupted", "cancelled"):
        selected = choose_version(result["rounds"])
        if selected:
            result["selected_round"] = selected["round_no"]
    return result


class CampaignStore:
    def __init__(self, path, *, provider="compatible", client_factory=None, max_workers=3, max_model_calls=16, max_seconds=360):
        if provider not in ("compatible", "offline"):
            raise ValueError("provider 必须显式指定 compatible 或 offline")
        self.provider = provider
        self.client_factory = client_factory or (CompatibleModelClient.from_env if provider == "compatible" else RuleBasedModelClient)
        prototype = self.client_factory()
        self.strategy_prompt = PromptBuilder()
        self.creative_prompt = prompt_text("creative")
        self.directions_prompt = (Path(__file__).resolve().parents[2] / "prompts" / "creative" / "directions.v1.0.txt").read_text(encoding="utf-8")
        self.evaluation_prompt = prompt_text("evaluation")
        self.config = {"provider": provider, "model": getattr(prototype, "model", "offline-rules"), "reasoning_effort": getattr(prototype, "reasoning_effort", None), "timeout_seconds": getattr(prototype, "timeout_seconds", 60), "temperature": getattr(prototype, "temperature", None), "endpoint_fingerprint": hashlib.sha256(getattr(prototype, "endpoint", "offline").encode()).hexdigest(), "max_rounds": 3, "pass_threshold": 80, "max_model_calls": max_model_calls, "max_seconds": max_seconds, "scoring_rule_version": "evidence-five-dimensions-v1.1", "prompt_hashes": {"strategy": self.strategy_prompt.sha256, "creative": hashlib.sha256(self.creative_prompt.encode()).hexdigest(), "evaluation": hashlib.sha256(self.evaluation_prompt.encode()).hexdigest()}}
        self.config["strategy_editor_version"] = CompatibleModelClient.EDITOR_VERSION
        self.config["streaming_enabled"] = getattr(prototype,"streaming_enabled",False)
        self.config["collaboration_version"] = "delivery-first-preflight-v2.0"
        self.config["strategy_review_policy"] = "deterministic-first-final-agent-review"
        self.config["prompt_hashes"]["directions"] = hashlib.sha256(self.directions_prompt.encode()).hexdigest()
        self.config_version = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()[:20]
        self.repository = CampaignRepository(path)
        self.repository.recover()
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="campaign")
        self.lock = threading.RLock()
        self.active = set()
        self.closed = False

    def create(self, requirements, owner, submission_key, *, quality_mode="balanced", interactive=False, choose_directions=True, parent_task_id=None, initial_direction=None):
        if type(interactive) is not bool:
            raise ContractValidationError("interactive 须为布尔值")
        if type(choose_directions) is not bool:
            raise ContractValidationError("choose_directions 须为布尔值")
        if quality_mode not in ("balanced", "polish"):
            raise ContractValidationError("quality_mode 须为 balanced 或 polish")
        normalized = MarketingRequirements.from_dict(requirements).to_dict()
        if not isinstance(submission_key, str) or not 8 <= len(submission_key) <= 100:
            raise ContractValidationError("submission_key 须为8至100字符的提交标识")
        with self.lock:
            previous = self.repository.find_submission(owner, submission_key)
            if previous:
                if previous.get('deleted_at'):
                    raise ContractValidationError("这个提交已移入回收站，请恢复原任务或使用新的提交标识")
                if previous["requirements"] != normalized or previous.get("quality_mode", "balanced") != quality_mode or previous.get("interactive",False) != interactive or previous.get("choose_directions",True) != choose_directions:
                    raise ContractValidationError("同一提交标识不能对应不同需求")
                return public_task(previous)
            if self.closed or len(self.active) >= 30 or sum(task["status"] in ("pending", "running") for task in self.repository.list(owner)) >= 5:
                raise ModelUnavailableError("当前排队任务较多，请等待或取消已有任务")
            task = {"schema_version": "1.1", "task_id": f"campaign-{uuid4().hex}", "owner_scope": owner, "submission_key": submission_key, "requirements": normalized, "config_version": self.config_version, "config_snapshot": deepcopy(self.config), "status": "pending", "stage": "queued", "round_no": 1, "assessment_status": "not_evaluated", "termination_reason": None, "selected_round": None, "created_at": now(), "updated_at": now(), "rounds": [], "feedback": [], "events": [], "error": None, "usage": {"model_calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "usage_available": False, "active_seconds": 0.0}}
            task.update(quality_mode=quality_mode, interactive=interactive, choose_directions=choose_directions, messages=[], live_draft=None)
            if parent_task_id:
                task.update(parent_task_id=parent_task_id, initial_direction=deepcopy(initial_direction))
                event(task,"coordinator","context_continued","这是补充真实资料后的关联续作，原任务和所有版本保持不变。已选择的创意方向会继续作为公开上下文。")
            event(task, "human", "brief", f"我想推广{normalized['product_name']}。目标：{normalized['marketing_goal']}\n产品事实：{normalized['product_description']}")
            event(task, "coordinator", "created", "李智信先梳理策略，李莉接手创意，毛小纯独立评审。你可以在下面随时补充修改意见。")
            questions = brief_questions(normalized)
            if questions:
                task.update(status="awaiting_input", stage="awaiting_input", assessment_status="needs_input", termination_reason="brief_incomplete", clarifications=questions, clarification_agent="strategy")
                event(task, "strategy", "input_requested", "在开始前，先确认推广目标需要的真实入口。补充资料前不会调用模型。")
            self.repository.insert(task)
            if not questions:
                self._submit(task["task_id"])
            return public_task(task)

    def _submit(self, task_id):
        self.active.add(task_id)
        self.executor.submit(self._run, task_id)

    def get(self, task_id, owner):
        return public_task(self.repository.get(task_id, owner))

    def list(self, owner, *, deleted=False):
        keys = ("task_id", "status", "stage", "assessment_status", "created_at", "updated_at", "round_no", "termination_reason")
        result = []
        for task in self.repository.list(owner, deleted=deleted):
            row = next((row for row in task['rounds'] if row['round_no'] == task['selected_round']), None)
            row = row if row and row.get('evaluation') else next((row for row in reversed(task['rounds']) if row.get('evaluation')), None)
            review = row['evaluation']['data'] if row else None
            result.append({**{key: task[key] for key in keys}, 'product_name': task['requirements']['product_name'], 'deleted_at': task.get('deleted_at'), 'deletable': task['task_id'] not in self.active and task['status'] not in ('pending', 'running') and not any(job['status'] in ('pending', 'running') for job in task.get('image_jobs', [])), 'review': {'round_no': row['round_no'], 'total_score': review['total_score'], 'high_risks': sum(risk['severity'] == 'high' for risk in review['risks']), 'provider': task['config_snapshot']['provider']} if review else None})
        return result

    def cancel(self, task_id, owner):
        self.repository.get(task_id, owner)
        def update(task):
            if task["status"] in ("pending", "running", "awaiting_direction", "awaiting_revision", "interrupted", "failed"):
                task.update(status="cancelled", stage="cancelled", termination_reason="user_cancelled")
                event(task, "coordinator", "cancelled", "任务已取消；已完成阶段保留，后续结果不会提交。")
        return public_task(self.repository.update(task_id, update))

    def resume(self, task_id, owner):
        with self.lock:
            task = self.repository.get(task_id, owner)
            if task_id in self.active or self.closed or len(self.active) >= 30:
                raise ModelUnavailableError("任务仍在结束或服务繁忙，请稍后再继续")
            if task["status"] not in ("interrupted", "failed") or task["config_version"] != self.config_version:
                raise ContractValidationError("仅能恢复相同配置的失败或中断任务；其他情况请新建任务")
            if task["usage"]["model_calls"] >= self.config["max_model_calls"] or task["usage"]["active_seconds"] >= self.config["max_seconds"]:
                raise ContractValidationError("本任务执行额度已用完，请查看已有结果或新建任务")
            def update(current):
                current.update(status="pending", stage="queued", error=None)
                event(current, "coordinator", "resumed", "继续未完成阶段，复用已保存的有效版本。")
            task = self.repository.update(task_id, update)
            self._submit(task_id)
            return public_task(task)

    def approve(self, task_id, owner):
        self.repository.get(task_id, owner)
        def update(task):
            if task["status"] != "awaiting_confirmation" or task["assessment_status"] != "passed":
                raise ContractValidationError("仅能确认已经通过方案评审的选中版本")
            task.update(status="approved", stage="approved")
            event(task, "human", "approved", "用户已确认选中方案；未自动发布或投放。")
        return public_task(self.repository.update(task_id, update))

    def choose_direction(self, task_id, owner, payload):
        if not isinstance(payload,dict) or set(payload) != {"option_id", "base_round"}:
            raise ContractValidationError("请选择创意方向和当前轮次")
        with self.lock:
            task = self.repository.get(task_id, owner)
            row = task["rounds"][-1] if task["rounds"] else {}
            if row.get("direction_choice",{}).get("option_id") == payload["option_id"] and payload["base_round"] == task["round_no"]:
                return public_task(task)
            if task["status"] != "awaiting_direction" or task["config_version"] != self.config_version or task_id in self.active or self.closed:
                raise ContractValidationError("当前不在选择创意方向的阶段，请刷新后重试")
            option = next((item for item in row.get("directions",[]) if item["option_id"] == payload["option_id"]),None)
            if option is None or type(payload["base_round"]) is not int or payload["base_round"] != task["round_no"]:
                raise ContractValidationError("创意方向不存在或轮次已更新")
            if len(self.active) >= 30 or task["usage"]["model_calls"] >= self.config["max_model_calls"] or task["usage"]["active_seconds"] >= self.config["max_seconds"]:
                raise ModelUnavailableError("服务繁忙或本任务额度已用完")
            def update(current):
                current["rounds"][-1]["direction_choice"] = deepcopy(option)
                current.update(status="pending",stage="queued",live_draft=None)
                event(current,"human","direction_chosen","我选择“"+option["title"]+"”，请沿这个方向深化。")
                event(current,"creative","acknowledged","收到。我会沿你选的方向制作成稿，再交给毛小纯评审。")
            task = self.repository.update(task_id,update)
            self._submit(task_id)
            return public_task(task)

    def clarify(self, task_id, owner, payload):
        if not isinstance(payload,dict) or set(payload) != {"message","submission_key"}:
            raise ContractValidationError("请填写补充事实与提交标识")
        message, key = payload["message"],payload["submission_key"]
        if not isinstance(message,str) or not 1 <= len(message.strip()) <= 1000 or not isinstance(key,str) or not 8 <= len(key) <= 100:
            raise ContractValidationError("补充事实须为1至1000字，提交标识须为8至100字符")
        source = self.repository.get(task_id,owner)
        if source["status"] != "awaiting_input":
            raise ContractValidationError("当前没有等待补充的事实问题")
        requirements = deepcopy(source["requirements"])
        requirements["product_description"] += "\n补充的已确认资料：" + message.strip()
        direction = next((row.get("direction_choice") for row in reversed(source["rounds"]) if row.get("direction_choice")),source.get("initial_direction"))
        submission = "clarification-"+hashlib.sha256((task_id+key).encode()).hexdigest()
        return self.create(requirements,owner,submission,quality_mode=source.get("quality_mode","balanced"),interactive=source.get("interactive",False),choose_directions=source.get("choose_directions",True),parent_task_id=task_id,initial_direction=direction)

    def continue_review(self, task_id, owner):
        with self.lock:
            task = self.repository.get(task_id,owner)
            if task["status"] != "awaiting_revision" or task["config_version"] != self.config_version:
                raise ContractValidationError("当前不在等待确认修改的阶段")
            if self.closed or task_id in self.active or len(self.active)>=30 or task["usage"]["model_calls"] >= self.config["max_model_calls"] or task["usage"]["active_seconds"] >= self.config["max_seconds"]:
                raise ModelUnavailableError("任务仍在收尾、服务繁忙或执行额度已用完")
            def update(current):
                current.update(status="pending",stage="queued",selected_round=None)
                event(current,"human","continue_review","按毛小纯列出的评审建议继续修改，保留已有效的内容。")
            task=self.repository.update(task_id,update)
            self._submit(task_id)
            return public_task(task)

    def revise(self, task_id, owner, payload):
        expected = {"message", "target_path", "base_round", "submission_key"}
        if not isinstance(payload, dict) or set(payload) != expected:
            raise ContractValidationError("修改需要意见、目标字段、基础轮次与提交标识")
        message, path, key = payload["message"], payload["target_path"], payload["submission_key"]
        if not isinstance(message, str) or not 1 <= len(message.strip()) <= 1000 or not isinstance(key, str) or not 8 <= len(key) <= 100:
            raise ContractValidationError("修改意见须为1至1000字，提交标识须为8至100字符")
        paths = {"creative.items", "strategy.positioning"} | {f"creative.items[{index}].{field}" for index in range(5) for field in ("headline", "body", "call_to_action", "visual_brief")}
        if path not in paths or type(payload["base_round"]) is not int:
            raise ContractValidationError("请选择有效的修改目标与轮次")
        with self.lock:
            task = self.repository.get(task_id, owner)
            previous = next((item for item in task.get("messages", []) if item["submission_key"] == key), None)
            if previous:
                if any(previous[field] != payload[field] for field in ("message", "target_path", "base_round")):
                    raise ContractValidationError("同一提交标识不能对应不同修改意见")
                return public_task(task)
            if task["config_version"] != self.config_version or task["status"] in ("cancelled", "awaiting_input", "awaiting_direction", "interrupted", "failed"):
                raise ContractValidationError("请先恢复当前阶段或补充原始需求；旧配置任务请新建")
            if payload["base_round"] != task["round_no"]:
                raise ContractValidationError("方案已经更新，请基于最新轮次重新提交意见")
            if "[" in path:
                row = task["rounds"][-1] if task["rounds"] else None
                if not row or not row.get("creative"):
                    raise ContractValidationError("具体文案尚未交付，请先选择整份创意")
                locate({"strategy": row["strategy"], "creative": row["creative"]}, path)
            if task["round_no"] >= self.config["max_rounds"] or task["usage"]["model_calls"] >= self.config["max_model_calls"] or task["usage"]["active_seconds"] >= self.config["max_seconds"]:
                raise ContractValidationError("本任务修改额度已用完，请保留结果并新建任务")
            if sum(item["status"] == "pending" for item in task.get("messages", [])) >= 5:
                raise ContractValidationError("已有5条意见待处理，请等待当前交付")
            working = task["status"] in ("pending", "running")
            if not working and (task_id in self.active or self.closed or len(self.active) >= 30):
                raise ModelUnavailableError("当前任务正在收尾或服务繁忙，请稍后再发送")
            def update(current):
                if current["status"] != task["status"] or current["round_no"] != task["round_no"]:
                    raise ContractValidationError("任务状态刚刚更新，请刷新后再发送；意见尚未提交")
                item = {**deepcopy(payload), "message_id": f"human-{uuid4().hex}", "status": "pending", "created_at": now()}
                current.setdefault("messages", []).append(item)
                event(current, "human", "user_feedback", message.strip(), target_path=path, message_id=item["message_id"])
                event(current, path.split(".")[0], "acknowledged", "已收到你的意见。当前轮交付后，我会按指定范围修改，保留其他有效内容。" if working else "已收到你的意见。我会按指定范围形成新版本，再请毛小纯复核。")
                if not working:
                    self.apply_messages(current)
                    current.update(status="pending", stage="queued", assessment_status="not_evaluated", error=None, selected_round=None)
            task = self.repository.update(task_id, update)
            if not working:
                self._submit(task_id)
            return public_task(task)

    @staticmethod
    def apply_messages(task):
        row = task["rounds"][-1]
        targets = set()
        for item in task.get("messages", []):
            if item["status"] != "pending":
                continue
            path = item["target_path"]
            source = locate({"strategy": row["strategy"], "creative": row["creative"]}, path)
            owner = path.split(".")[0]
            task["feedback"].append({"feedback_id": item["message_id"], "evaluation_id": row["evaluation"]["result_id"], "target_agent": owner, "target_path": path, "issue": "用户要求：" + item["message"][:790], "suggestion": item["message"], "priority": "high", "status": "open", "resolved": False, "created_round": row["round_no"], "source_content": deepcopy(source), "source_result_id": row[owner]["result_id"]})
            item.update(status="applied", applied_after_round=row["round_no"])
            targets.add(owner)
        if targets:
            targets.update(item["target_agent"] for item in task["feedback"] if item["status"] == "open")
            row["decision"] = "regenerate_strategy" if "strategy" in targets else "regenerate_creative"
            event(task, "coordinator", "routed", "用户意见已交给李智信调整方向，随后由李莉更新创意。" if "strategy" in targets else "用户意见已交给李莉，李智信的策略保持不变。", decision=row["decision"])
        return bool(targets)

    def _run(self, task_id):
        runner = CampaignRunner(self, task_id)
        try:
            runner.run()
        except ExecutionStopped:
            pass
        except Exception as error:
            def fail(task):
                if task["status"] not in TERMINAL:
                    message = str(error) if isinstance(error, StrategyAgentError) else "当前阶段执行异常，已保留成功结果；可继续或检查服务配置。"
                    task.update(status="failed", error={"code": getattr(error, "code", "INTERNAL_ERROR"), "message": message[:1000], "retryable": getattr(error, "retryable", False)})
                    task["usage"]["active_seconds"] = round(max(task["usage"]["active_seconds"], runner.initial_seconds + time.monotonic() - runner.started), 2)
                    event(task, "coordinator", "failed", task["error"]["message"])
            self.repository.update(task_id, fail)
        finally:
            elapsed = time.monotonic() - runner.started
            self.repository.update(task_id, lambda task: task["usage"].update(active_seconds=round(max(task["usage"]["active_seconds"], runner.initial_seconds + elapsed), 2)))
            with self.lock:
                self.active.discard(task_id)

    def close(self):
        with self.lock:
            self.closed = True
            for task_id in self.active:
                def interrupt(task):
                    if task["status"] in ("pending", "running"):
                        task.update(status="interrupted", stage="interrupted", error={"code": "INTERRUPTED", "message": "服务已停止，可在重启后继续。", "retryable": True})
                        event(task, "coordinator", "interrupted", "服务中断，保留成功阶段。")
                self.repository.update(task_id, interrupt)
            self.executor.shutdown(wait=False, cancel_futures=True)


class CampaignRunner:
    def __init__(self, store, task_id):
        self.store, self.task_id = store, task_id
        self.started = time.monotonic()
        self.initial_seconds = self.task()["usage"]["active_seconds"]
        self.client = None
        self.agent_name = "coordinator"
        self.last_draft_at = 0
        self.last_draft = None

    def task(self):
        return self.store.repository.get(self.task_id)

    def check(self):
        task = self.task()
        if self.store.closed or task["status"] in TERMINAL | {"interrupted"}:
            raise ExecutionStopped("任务已停止")
        remaining = self.store.config["max_seconds"] - self.initial_seconds - (time.monotonic() - self.started)
        if remaining <= 0:
            raise ExecutionLimit("已达到任务总执行时间上限；已保留生成结果。")
        return max(.1, remaining)

    def request_guard(self):
        remaining = self.check()
        def update(task):
            if task["status"] != "running":
                raise ExecutionStopped("任务已停止")
            if task["usage"]["model_calls"] >= self.store.config["max_model_calls"]:
                raise ExecutionLimit("已达到本任务模型调用上限；已保留生成结果。")
            task["usage"]["model_calls"] += 1
            task["live_draft"] = None
            task["usage"]["active_seconds"] = round(self.initial_seconds + time.monotonic() - self.started, 2)
            event(task, self.agent_name, "model_call", "开始模型请求。", call_no=task["usage"]["model_calls"])
        self.store.repository.update(self.task_id, update)
        return remaining

    def observe_usage(self, usage):
        def update(task):
            if not isinstance(usage, dict):
                return
            for key in ("prompt_tokens", "completion_tokens"):
                value = usage.get(key)
                if type(value) is int and value >= 0:
                    task["usage"][key] += value
                    task["usage"]["usage_available"] = True
        self.store.repository.update(self.task_id, update)

    def progress(self, attempt, detail="generating"):
        self.check()
        def update(task):
            if task["status"] != "running":
                raise ExecutionStopped("任务已停止")
            task["stage"] = self.agent_name
            prior = next((item for item in reversed(task["events"]) if item["kind"] == "progress"), None)
            if prior and prior["agent"] == self.agent_name and prior.get("attempt_count") == attempt and prior.get("detail") == detail and prior["round_no"] == task["round_no"]:
                return
            text = PHASES.get(self.agent_name, {}).get(detail, PHASES.get(self.agent_name, {}).get("generating", "正在处理本次任务。"))
            event(task, self.agent_name, "progress", text, attempt_count=attempt, detail=detail)
        self.store.repository.update(self.task_id, update)

    def observe_public_output(self, content):
        fragments = public_excerpt(content, self.agent_name)
        if not fragments or fragments == self.last_draft or time.monotonic() - self.last_draft_at < .65:
            return
        self.check()
        self.last_draft_at, self.last_draft = time.monotonic(), fragments
        def update(task):
            if task["status"] == "running":
                task["live_draft"] = {"agent": self.agent_name, "fragments": fragments, "updated_at": now(), "status": "unverified", "request_no": task["usage"]["model_calls"]}
        self.store.repository.update(self.task_id, update)

    def save_result(self, agent, response):
        self.check()
        def update(task):
            if task["status"] != "running":
                raise ExecutionStopped("任务已停止")
            task["rounds"][-1][agent] = deepcopy(response)
            task["live_draft"] = None
            event(task, agent, "succeeded", result_message(agent, response), result_id=response["result_id"], version=response["version"])
            for feedback in task["feedback"]:
                if feedback["status"] == "open" and feedback["target_agent"] == agent:
                    feedback["candidate_result_id"] = response["result_id"]
        self.store.repository.update(self.task_id, update)

    def strategy_progress(self, agent, attempt, detail):
        self.progress(attempt, detail)
        if detail == "retrying":
            self.save_strategy_diagnostics(agent)

    def save_strategy_diagnostics(self, agent):
        traces = agent.traces(self.task_id)
        diagnostics = [{key: trace.get(key) for key in ("attempt_count", "duration_ms", "error_code", "issues")} for trace in traces]
        def update(task):
            if task["status"] == "running":
                task["rounds"][-1]["strategy_diagnostics"] = diagnostics
        self.store.repository.update(self.task_id, update)

    def run(self):
        self.check()
        def start(task):
            if task["status"] == "cancelled":
                raise ExecutionStopped("任务已取消")
            task.update(status="running", error=None)
        self.store.repository.update(self.task_id, start)
        self.client = self.store.client_factory()
        if self.store.provider == "compatible":
            self.client.request_guard = self.request_guard
            self.client.usage_observer = self.observe_usage
            self.client.public_output_observer = self.observe_public_output
            self.client.cancellation_check = self.check
        strategy_agent = StrategyAgent(self.client, prompt_builder=self.store.strategy_prompt, semantic_review=False)
        saved = self.task()
        strategy_results = {row["strategy"]["version"]: row["strategy"] for row in saved["rounds"] if row.get("strategy")}
        strategy_agent.restore_history(self.task_id, saved["requirements"], saved["config_version"], [strategy_results[version] for version in sorted(strategy_results)])
        creative_agent = CreativeAgent(self.client if self.store.provider == "compatible" else None, offline=self.store.provider == "offline", system_prompt=self.store.creative_prompt)
        evaluator = EvaluationAgent(self.client if self.store.provider == "compatible" else None, offline=self.store.provider == "offline", system_prompt=self.store.evaluation_prompt)
        while True:
            self.check()
            task = self.task()
            if not task["rounds"] or task["rounds"][-1].get("decision"):
                if task["rounds"] and task["rounds"][-1]["decision"] not in ("regenerate_strategy", "regenerate_creative"):
                    return
                previous = task["rounds"][-1] if task["rounds"] else None
                def add_round(current):
                    if current["status"] != "running":
                        raise ExecutionStopped("任务已停止")
                    current["round_no"] = len(current["rounds"]) + 1
                    current["rounds"].append({"round_no": current["round_no"], "strategy": deepcopy(previous["strategy"]) if previous and previous["decision"] == "regenerate_creative" else None, "creative": None, "evaluation": None, "decision": None})
                    if previous and previous["decision"] == "regenerate_creative":
                        event(current, "coordinator", "strategy_reused", "仅修改创意，复用已确认策略。", result_id=previous["strategy"]["result_id"])
                self.store.repository.update(self.task_id, add_round)
                task = self.task()
            row = task["rounds"][-1]
            feedback = [self.legacy_feedback(item) for item in task["feedback"] if item["status"] == "open"]
            if not row["strategy"]:
                self.agent_name = "strategy"
                self.progress(1)
                history = strategy_agent.history(self.task_id)
                request = StrategyRequest.from_dict({"schema_version": "1.0", "task_id": self.task_id, "agent": "strategy", "round_no": row["round_no"], "attempt_count": 1, "requirements": task["requirements"], "strategy": None, "creative": None, "feedback": [item for item in feedback if item["target_agent"] == "strategy"], "previous_result": history[-1] if history else None, "config_version": task["config_version"]})
                response = strategy_agent.generate(request, on_attempt=lambda attempt, detail: self.strategy_progress(strategy_agent, attempt, detail)).to_dict()
                self.save_strategy_diagnostics(strategy_agent)
                self.check()
                if response["status"] != "succeeded":
                    error = StrategyAgentError(response["error"]["message"])
                    error.code, error.retryable = response["error"]["code"], response["error"]["retryable"]
                    raise error
                self.save_result("strategy", response)
            task = self.task()
            row = task["rounds"][-1]
            if task.get("interactive") and task.get("choose_directions", True) and not task.get("initial_direction") and row["round_no"] == 1 and not row.get("direction_choice"):
                self.agent_name = "creative"
                if not row.get("directions"):
                    self.progress(1)
                    request = handoff(task,row["round_no"],row["strategy"])
                    directions = creative_agent.propose(request,self.store.directions_prompt,check=self.check,progress=self.progress)
                    self.check()
                    def save_directions(current):
                        if current["status"] != "running":
                            raise ExecutionStopped("任务已停止")
                        current["rounds"][-1]["directions"] = directions
                        current.update(status="awaiting_direction",stage="awaiting_direction",live_draft=None)
                        event(current,"creative","directions_ready","我准备了两个不同的创意方向。请你选一个，我再深化成完整文案。")
                    self.store.repository.update(self.task_id,save_directions)
                return
            task, self.agent_name = self.task(), "creative"
            row = task["rounds"][-1]
            if not row["creative"]:
                self.progress(1)
                previous = task["rounds"][-2]["creative"] if len(task["rounds"]) > 1 else None
                request = handoff(task, row["round_no"], row["strategy"], previous=previous, feedback=[item for item in feedback if item["target_agent"] == "creative"])
                choice = next((item.get("direction_choice") for item in reversed(task["rounds"]) if item.get("direction_choice")),task.get("initial_direction"))
                self.save_result("creative", creative_agent.generate(request, version=row["round_no"], check=self.check, progress=self.progress, direction=choice))
            task, self.agent_name = self.task(), "evaluation"
            row = task["rounds"][-1]
            if not row["evaluation"]:
                self.progress(1)
                previous = task["rounds"][-2]["evaluation"] if len(task["rounds"]) > 1 else None
                request = handoff(task, row["round_no"], row["strategy"], row["creative"], previous, feedback)
                self.save_result("evaluation", evaluator.assess(request, version=row["round_no"], check=self.check, progress=self.progress))
            self.finish_round()

    @staticmethod
    def legacy_feedback(feedback):
        return {key: feedback[key] for key in ("feedback_id", "evaluation_id", "target_agent", "target_path", "issue", "suggestion", "priority", "resolved")}

    def finish_round(self):
        self.check()
        def update(task):
            if task["status"] != "running":
                raise ExecutionStopped("任务已停止")
            row = task["rounds"][-1]
            result = row["evaluation"]["data"]
            result["clarifications"], row["preparation_notes"] = partition_draft_questions(result.get("clarifications", []))
            severe_owners = {risk["target_path"].split(".")[0] for risk in result["risks"] if risk["severity"] == "high"}
            checks = {check["feedback_id"]: check for check in result["feedback_checks"]}
            if task.get("quality_mode") == "polish":
                for dimension in result["dimension_scores"].values():
                    if dimension["score"] < 75:
                        result["feedback"].append({"target_agent": dimension["target_path"].split(".")[0], "target_path": dimension["target_path"], "issue": "精修要求：单项质量低于75分。" + dimension["reason"], "suggestion": "针对当前维度和引用内容改进，不能只用其他维度的高分抵消。", "priority": "high"})
            brand = compact(task["requirements"]["product_name"])
            brand_present = any(brand in compact(item["headline"] + item["body"]) for item in row["creative"]["data"]["items"])
            row["delivery_checks"] = [{"code": "brand_identity", "label": "正文或标题包含产品名称", "passed": brand_present}]
            if task.get("quality_mode") == "polish" and not brand_present:
                result["feedback"].append({"target_agent": "creative", "target_path": "creative.items", "issue": "精修要求：成品标题和正文缺少产品名称。", "suggestion": "在合适的标题或正文中自然加入产品名称，保持原始事实与渠道选择。", "priority": "high"})
            if result["total_score"] < self.store.config["pass_threshold"] and not result["feedback"]:
                dimension = min(result["dimension_scores"].values(), key=lambda item: item["score"])
                result["feedback"].append({"target_agent": dimension["target_path"].split(".")[0], "target_path": dimension["target_path"], "issue": "该维度尚未达到质量要求：" + dimension["reason"], "suggestion": "针对引用原文和该维度理由修改对应内容，再交由独立评审确认。", "priority": "high"})
            for feedback in task["feedback"]:
                check = checks.get(feedback["feedback_id"])
                if feedback["status"] == "open" and check:
                    feedback["verification"] = deepcopy(check)
                    request = {"strategy": row["strategy"], "creative": row["creative"]}
                    try:
                        changed = compact(locate(request, feedback["target_path"])) != compact(feedback.get("source_content", ""))
                    except ContractValidationError:
                        changed = True
                    if check["resolved"] and not changed:
                        feedback["verification"].update(resolved=False, reason="对应内容没有实际变化，不能确认已经修复。")
                    if check["resolved"] and changed and feedback["target_agent"] not in severe_owners:
                        feedback.update(status="resolved", resolved=True, resolved_by=row["evaluation"]["result_id"])
                        event(task, "evaluation", "feedback_resolved", "后续评审已确认问题修复。", feedback_id=feedback["feedback_id"])
            for feedback in result["feedback"]:
                existing = next((item for item in task["feedback"] if item["status"] == "open" and item["target_path"] == feedback["target_path"] and item["issue"] == feedback["issue"]), None)
                if existing:
                    continue
                request = {"strategy": row["strategy"], "creative": row["creative"]}
                task["feedback"].append({**deepcopy(feedback), "feedback_id": f"feedback-{uuid4().hex}", "evaluation_id": row["evaluation"]["result_id"], "status": "open", "resolved": False, "created_round": row["round_no"], "source_content": deepcopy(locate(request, feedback["target_path"])), "source_result_id": row[feedback["target_agent"]]["result_id"]})
            human_revision = self.store.apply_messages(task) if not result.get("clarifications") else False
            blockers = [item for item in task["feedback"] if item["status"] == "open" and item["priority"] == "high"]
            row["feedback_snapshot"] = deepcopy(task["feedback"])
            high_risks = [risk for risk in result["risks"] if risk["severity"] == "high"]
            passed = result["total_score"] >= self.store.config["pass_threshold"] and not high_risks and not blockers
            same_content = False
            if len(task["rounds"]) > 1:
                previous = task["rounds"][-2]
                before, after = deepcopy(previous["creative"]["data"]), deepcopy(row["creative"]["data"])
                before.pop("strategy_result_id", None)
                after.pop("strategy_result_id", None)
                same_content = before == after and previous["strategy"]["data"] == row["strategy"]["data"]
            if human_revision:
                event(task, "coordinator", "revision_started", "先处理你刚刚提出的修改意见，再重新评审。")
            elif result.get("clarifications"):
                row["decision"] = "request_input"
                task.update(status="awaiting_input", stage="awaiting_input", assessment_status="needs_input", termination_reason="needs_user_input", selected_round=row["round_no"], clarifications=deepcopy(result["clarifications"]))
                event(task, "coordinator", "input_requested", "存在不能由AI补写的信息，已暂停并提出具体问题。")
            elif passed:
                row["decision"] = "accept"
                task.update(status="awaiting_confirmation", stage="awaiting_confirmation", assessment_status="passed", termination_reason="quality_passed", selected_round=row["round_no"])
                event(task, "coordinator", "completed", "方案通过质量评审，等待人工确认；尚未发布或投放。")
            elif row["round_no"] >= self.store.config["max_rounds"] or same_content:
                selected = choose_version(task["rounds"])
                safe = not any(risk["severity"] == "high" for risk in selected["evaluation"]["data"]["risks"])
                row["decision"] = "stop"
                task.update(status="needs_revision" if safe else "needs_review", stage="completed", assessment_status="not_passed" if safe else "needs_review", termination_reason="no_change" if same_content else "round_limit", selected_round=selected["round_no"])
                event(task, "coordinator", "stopped", "修改未产生内容变化，已停止重复调用。" if same_content else "已达到轮次上限；保留最合适版本并列出待处理问题。")
            else:
                targets = {item["target_agent"] for item in task["feedback"] if item["status"] == "open"}
                row["decision"] = "regenerate_strategy" if "strategy" in targets else "regenerate_creative"
                event(task, "coordinator", "routed", "评审反馈已交回策略，随后重新生成关联创意。" if "strategy" in targets else "评审反馈已交回创意，保留当前策略。", decision=row["decision"])
                if task.get("interactive"):
                    task.update(status="awaiting_revision",stage="awaiting_revision",selected_round=row["round_no"],assessment_status="not_passed")
                    event(task,"evaluation","review_checkpoint","修改建议已经列好。你可以补充自己的意见，或者让我按现有建议继续；在你确认前，不会自动开始下一轮。")
            task["usage"]["active_seconds"] = round(max(task["usage"]["active_seconds"], self.initial_seconds + time.monotonic() - self.started), 2)
        self.store.repository.update(self.task_id, update)
