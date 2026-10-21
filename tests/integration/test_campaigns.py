from copy import deepcopy
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from src.agents.creative import CreativeAgent
from src.agents.evaluation.agent import EvaluationAgent
from src.agents.strategy.errors import AccessDeniedError, ContractValidationError, ModelUnavailableError
from src.agents.strategy.model_clients import RuleBasedModelClient
from src.backend.campaigns import CampaignStore
from src.contracts.campaign import handoff, locate


def requirements():
    return json.loads((Path(__file__).parents[1] / "fixtures/sample_request.json").read_text(encoding="utf-8"))["requirements"]


class ScriptedClient(RuleBasedModelClient):
    model = "scripted-test-model"

    def __init__(self, *, strategy_feedback=False, bad_evidence=False, fail_creative=False, unsafe=False):
        self.strategy_feedback = strategy_feedback
        self.bad_evidence = bad_evidence
        self.fail_creative = fail_creative
        self.unsafe = unsafe
        self.calls = []
        self.gate = None

    def generate_json(self, prompt):
        self.calls.append(("strategy", deepcopy(prompt.request.to_dict())))
        data = json.loads(super().generate_json(prompt))
        if prompt.request.previous_result:
            data["positioning"] += " 优先说明产品适用场景。"
        return json.dumps(data, ensure_ascii=False)

    def complete_json(self, system, user):
        request = json.loads(user)["request"]
        if "广告创意智能体" in system:
            self.calls.append(("creative", deepcopy(request)))
            if self.gate:
                self.gate.wait(5)
            if self.fail_creative:
                raise ModelUnavailableError("测试中的临时创意服务错误")
            data = CreativeAgent(offline=True).generate(request, version=request["round_no"])["data"]
            data["items"][0]["call_to_action"] = "了解更多" if request["round_no"] == 1 else "查看产品介绍，确认适用条件后再咨询。"
            if self.unsafe:
                data["items"][0]["body"] += "获得国际权威认证，保证效果。"
            return data
        self.calls.append(("evaluation", deepcopy(request)))
        data = EvaluationAgent(offline=True).assess(request, version=request["round_no"])["data"]
        for key in ("total_score", "strategy_result_id", "creative_result_id"):
            data.pop(key)
        data["risks"] = []
        data["feedback"] = []
        for score in data["dimension_scores"].values():
            score["score"] = 85
            score["reason"] = "实际内容符合当前测试量表。"
        if request["round_no"] == 1 and not self.unsafe:
            target = "strategy" if self.strategy_feedback else "creative"
            path = "strategy.positioning" if self.strategy_feedback else "creative.items[0].call_to_action"
            data["dimension_scores"]["call_to_action"]["score"] = 60
            data["feedback"] = [{"target_agent": target, "target_path": path, "issue": "需要明确产品适用场景。" if self.strategy_feedback else "下一步动作不够具体。", "suggestion": "补充产品适用场景。" if self.strategy_feedback else "说明查看产品介绍并确认适用条件。", "priority": "high"}]
        for check in data["feedback_checks"]:
            check.update(resolved=True, reason="当前新版本已包含要求的具体内容。")
        if self.bad_evidence:
            data["dimension_scores"]["clarity"]["evidence"] = "这句话根本不在原文中"
        return data


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "campaigns.sqlite3"
        self.stores = []

    def tearDown(self):
        for store in self.stores:
            store.close()
            store.executor.shutdown(wait=True)
        self.directory.cleanup()

    def store(self, client=None, provider="compatible"):
        store = CampaignStore(self.path, provider=provider, client_factory=(lambda: client) if client else None)
        self.stores.append(store)
        return store

    def wait(self, store, task_id, owner="owner-1"):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            task = store.get(task_id, owner)
            if task["status"] not in ("pending", "running") and task_id not in store.active:
                return task
            time.sleep(.01)
        self.fail("任务未能在测试时间内结束")

    def test_real_calls_receive_feedback_and_reuse_strategy(self):
        client = ScriptedClient()
        store = self.store(client)
        created = store.create(requirements(), "owner-1", "submission-1")
        task = self.wait(store, created["task_id"])
        self.assertEqual(task["status"], "awaiting_confirmation")
        self.assertEqual([call[0] for call in client.calls], ["strategy", "creative", "evaluation", "creative", "evaluation"])
        first, second = task["rounds"]
        self.assertEqual(first["strategy"], second["strategy"])
        self.assertNotEqual(first["creative"]["data"]["items"][0]["call_to_action"], second["creative"]["data"]["items"][0]["call_to_action"])
        self.assertTrue(client.calls[3][1]["feedback"])
        self.assertEqual(task["feedback"][0]["status"], "resolved")
        self.assertEqual(task["feedback"][0]["resolved_by"], second["evaluation"]["result_id"])
        self.assertEqual(store.approve(task["task_id"], "owner-1")["status"], "approved")

    def test_strategy_feedback_regenerates_strategy_and_rebinds_creative(self):
        client = ScriptedClient(strategy_feedback=True)
        store = self.store(client)
        task = self.wait(store, store.create(requirements(), "owner-1", "submission-2")["task_id"])
        self.assertEqual(task["status"], "awaiting_confirmation")
        first, second = task["rounds"]
        self.assertEqual(first["decision"], "regenerate_strategy")
        self.assertEqual(second["strategy"]["version"], 2)
        self.assertNotEqual(first["strategy"]["result_id"], second["strategy"]["result_id"])
        self.assertEqual(second["creative"]["data"]["strategy_result_id"], second["strategy"]["result_id"])
        self.assertEqual([call[0] for call in client.calls].count("strategy"), 2)

    def test_high_scores_do_not_override_unsupported_claims(self):
        store = self.store(ScriptedClient(unsafe=True))
        task = self.wait(store, store.create(requirements(), "owner-1", "submission-3")["task_id"])
        self.assertEqual(task["assessment_status"], "needs_review")
        self.assertTrue(all(any(risk["severity"] == "high" for risk in row["evaluation"]["data"]["risks"]) for row in task["rounds"]))
        self.assertLessEqual(len(task["rounds"]), 3)
        self.assertTrue(all(feedback["status"] == "open" for feedback in task["feedback"]))
        with self.assertRaises(ContractValidationError):
            store.approve(task["task_id"], "owner-1")

    def test_fabricated_evidence_is_rejected_and_upstream_is_preserved(self):
        store = self.store(ScriptedClient(bad_evidence=True))
        task = self.wait(store, store.create(requirements(), "owner-1", "submission-4")["task_id"])
        self.assertEqual(task["status"], "failed")
        self.assertIsNotNone(task["rounds"][0]["strategy"])
        self.assertIsNotNone(task["rounds"][0]["creative"])
        self.assertIsNone(task["rounds"][0]["evaluation"])

    def test_retry_resumes_failed_stage_without_regenerating_strategy(self):
        client = ScriptedClient(fail_creative=True)
        store = self.store(client)
        task = self.wait(store, store.create(requirements(), "owner-1", "submission-5")["task_id"])
        self.assertEqual(task["status"], "failed")
        strategy_id = task["rounds"][0]["strategy"]["result_id"]
        client.fail_creative = False
        store.resume(task["task_id"], "owner-1")
        task = self.wait(store, task["task_id"])
        self.assertEqual(task["status"], "awaiting_confirmation")
        self.assertEqual(task["rounds"][0]["strategy"]["result_id"], strategy_id)
        self.assertEqual([call[0] for call in client.calls].count("strategy"), 1)

    def test_cancel_prevents_late_results_from_being_committed(self):
        client = ScriptedClient()
        client.gate = threading.Event()
        store = self.store(client)
        task_id = store.create(requirements(), "owner-1", "submission-6")["task_id"]
        deadline = time.monotonic() + 5
        while not any(call[0] == "creative" for call in client.calls) and time.monotonic() < deadline:
            time.sleep(.01)
        store.cancel(task_id, "owner-1")
        client.gate.set()
        task = self.wait(store, task_id)
        self.assertEqual(task["status"], "cancelled")
        self.assertIsNone(task["rounds"][0]["creative"])
        self.assertFalse(any(call[0] == "evaluation" for call in client.calls))

    def test_idempotency_and_owner_isolation(self):
        store = self.store(provider="offline")
        task = store.create(requirements(), "owner-1", "submission-7")
        again = store.create(requirements(), "owner-1", "submission-7")
        self.assertEqual(task["task_id"], again["task_id"])
        with self.assertRaises(AccessDeniedError):
            store.get(task["task_id"], "owner-2")
        changed = requirements()
        changed["product_name"] = "另一款产品"
        with self.assertRaises(ContractValidationError):
            store.create(changed, "owner-1", "submission-7")
        self.assertEqual(self.wait(store, task["task_id"])["config_snapshot"]["provider"], "offline")

    def test_sessions_and_completed_results_survive_restart(self):
        store = self.store(provider="offline")
        token, owner = store.repository.session()
        task = self.wait(store, store.create(requirements(), owner, "submission-8")["task_id"], owner)
        store.close()
        reopened = self.store(provider="offline")
        self.assertEqual(reopened.repository.scope(token), owner)
        self.assertEqual(reopened.get(task["task_id"], owner)["rounds"], task["rounds"])

    def test_unchanged_content_cannot_be_marked_fixed_by_reviewer(self):
        class UnchangedClient(ScriptedClient):
            def complete_json(self, system, user):
                data = super().complete_json(system, user)
                if "广告创意智能体" in system:
                    data["items"][0]["call_to_action"] = "了解更多"
                return data
        store = self.store(UnchangedClient())
        task = self.wait(store, store.create(requirements(), "owner-1", "unchanged-content")["task_id"])
        self.assertEqual(task["status"], "needs_revision")
        self.assertEqual(task["termination_reason"], "no_change")
        self.assertEqual(len(task["rounds"]), 2)
        self.assertEqual(task["feedback"][0]["status"], "open")
        self.assertFalse(task["feedback"][0]["verification"]["resolved"])

    def test_model_call_budget_is_cumulative_and_stops_before_extra_request(self):
        class CountedClient(ScriptedClient):
            def generate_json(self, prompt):
                if hasattr(self, "request_guard"):
                    self.request_guard()
                return super().generate_json(prompt)
            def complete_json(self, system, user):
                if hasattr(self, "request_guard"):
                    self.request_guard()
                data = super().complete_json(system, user)
                if hasattr(self, "usage_observer"):
                    self.usage_observer({"prompt_tokens": 12, "completion_tokens": 8})
                return data
        client = CountedClient()
        store = CampaignStore(self.path, provider="compatible", client_factory=lambda: client, max_model_calls=2)
        self.stores.append(store)
        task = self.wait(store, store.create(requirements(), "owner-1", "budget-stop")["task_id"])
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["error"]["code"], "EXECUTION_LIMIT")
        self.assertEqual(task["usage"]["model_calls"], 2)
        self.assertEqual(task["usage"]["completion_tokens"], 8)
        self.assertIsNotNone(task["rounds"][0]["creative"])
        self.assertIsNone(task["rounds"][0]["evaluation"])
        with self.assertRaises(ContractValidationError):
            store.resume(task["task_id"], "owner-1")

    def test_interrupted_stage_is_recovered_without_automatic_generation(self):
        client = ScriptedClient(fail_creative=True)
        store = self.store(client)
        task = self.wait(store, store.create(requirements(), "owner-1", "recover-interrupted")["task_id"])
        saved_strategy = task["rounds"][0]["strategy"]["result_id"]
        store.repository.update(task["task_id"], lambda current: current.update(status="running", stage="creative"))
        store.close()
        calls_before = len(client.calls)
        reopened = self.store(client)
        recovered = reopened.get(task["task_id"], "owner-1")
        self.assertEqual(recovered["status"], "interrupted")
        self.assertEqual(len(client.calls), calls_before)
        client.fail_creative = False
        reopened.resume(task["task_id"], "owner-1")
        finished = self.wait(reopened, task["task_id"])
        self.assertEqual(finished["status"], "awaiting_confirmation")
        self.assertEqual(finished["rounds"][0]["strategy"]["result_id"], saved_strategy)

    def test_missing_external_facts_pause_for_user_instead_of_repeated_generation(self):
        class ClarifyingClient(ScriptedClient):
            def complete_json(self, system, user):
                data = super().complete_json(system, user)
                if "独立方案评审智能体" in system:
                    request = json.loads(user)["request"]
                    data["clarifications"] = [{"question": "请提供真实的申请入口，或确认先改为产品认知目标。", "reason": "申请路径属于外部事实，不能由创意智能体编造。", "target_path": "creative.items[0].call_to_action", "evidence": request["creative"]["data"]["items"][0]["call_to_action"]}]
                return data
        client = ClarifyingClient()
        store = self.store(client)
        task = self.wait(store, store.create(requirements(), "owner-1", "needs-user-information")["task_id"])
        self.assertEqual(task["status"], "awaiting_input")
        self.assertEqual(len(task["rounds"]), 1)
        self.assertEqual(len(task["clarifications"]), 1)
        self.assertEqual([call[0] for call in client.calls], ["strategy", "creative", "evaluation"])

    def test_failure_exposes_best_already_reviewed_version(self):
        class FailingSecondReview(ScriptedClient):
            def complete_json(self, system, user):
                request = json.loads(user)["request"]
                if "独立方案评审智能体" in system and request["round_no"] == 2:
                    raise ModelUnavailableError("测试中的评审服务错误")
                return super().complete_json(system, user)
        store = self.store(FailingSecondReview())
        task = self.wait(store, store.create(requirements(), "owner-1", "save-best-on-failure")["task_id"])
        self.assertEqual(task["status"], "failed")
        self.assertEqual(task["selected_round"], 1)
        self.assertIsNotNone(task["rounds"][0]["evaluation"])
        self.assertIsNone(task["rounds"][1]["evaluation"])


if __name__ == "__main__":
    unittest.main()
