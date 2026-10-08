"""截图所示复核误阻断、修复上下文与失败诊断回归；全部使用测试客户端。"""
import json
import time
import unittest
from unittest.mock import patch

from src.agents.strategy.errors import ModelOutputError
from src.agents.strategy.model_clients import CompatibleModelClient
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.prompts import PromptBuilder
from src.agents.strategy.service import StrategyAgent
from src.agents.strategy.repair import discard_unknown_output_fields, mark_planning_inferences, repair_only_reported_fields
from src.backend.tasks import TaskStore
from tests.unit.test_models import valid_payload
from tests.unit.test_service import ScriptedClient, valid_data


def finding(category="quality"):
    return {"field": "strategy_data.channels[0].reason", "message": "可进一步补充社群资源来源，不应直接断言已有资源", "category": category, "evidence": "原味奶茶", "severity": "advisory" if category == "quality" else "blocking"}


class ReviewClient(ScriptedClient):
    def __init__(self, findings):
        super().__init__([json.dumps(valid_data(), ensure_ascii=False)] * 3)
        self.findings = findings
        self.prompts = []

    def generate_json(self, prompt):
        self.prompts.append(prompt)
        return super().generate_json(prompt)

    def review_strategy(self, requirements, data):
        return self.findings, json.dumps({"issues": self.findings})


class ClassifiedReviewTests(unittest.TestCase):
    def setUp(self):
        self.req = StrategyRequest.from_dict(valid_payload())

    def test_quality_advisory_does_not_block_or_retry(self):
        client = ReviewClient([finding()])
        agent = StrategyAgent(client, sleeper=lambda _: None)
        result = agent.generate(self.req).to_dict()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(client.calls, 1)
        self.assertEqual(len(agent.traces(self.req.task_id)[0]["review_notes"]), 1)
        self.assertNotIn("review_notes", result["data"])

    def test_planning_labels_do_not_change_product_facts(self):
        original = valid_data()
        labeled = mark_planning_inferences(original)
        self.assertTrue(labeled["channels"][0]["reason"].startswith("待验证假设："))
        self.assertTrue(labeled["target_audience"]["needs"][0].startswith("待验证假设："))
        self.assertEqual(labeled["selling_points"], original["selling_points"])
        self.assertEqual(labeled["positioning"], original["positioning"])
        self.assertEqual(mark_planning_inferences(labeled), labeled)

    def test_unknown_fields_are_discarded_without_changing_contract_values(self):
        original = valid_data()
        noisy = json.loads(json.dumps(original, ensure_ascii=False))
        noisy["marketing_strategy_note"] = "模型擅自增加的说明"
        noisy["channels"][0]["estimated_ctr"] = "20%"
        cleaned, discarded = discard_unknown_output_fields(noisy)
        self.assertEqual(cleaned, original)
        self.assertEqual(discarded, ["marketing_strategy_note", "channels.0.estimated_ctr"])

    def test_unknown_fields_do_not_trigger_a_model_retry(self):
        noisy = valid_data()
        noisy["marketing_strategy_note"] = "额外字段"
        client = ScriptedClient([json.dumps(noisy, ensure_ascii=False)])
        agent = StrategyAgent(client, sleeper=lambda _: None)
        result = agent.generate(self.req).to_dict()
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(result["attempt_count"], 1)
        self.assertEqual(client.calls, 1)
        self.assertEqual(agent.traces(self.req.task_id)[0]["discarded_fields"], ["marketing_strategy_note"])

    def test_incomplete_channel_execution_detail_is_rejected_as_quality_gap(self):
        weak = valid_data()
        weak["channels"][0]["content_direction"] = "介绍产品"
        client = ScriptedClient([json.dumps(weak, ensure_ascii=False)] * 3)
        agent = StrategyAgent(client, sleeper=lambda _: None)
        result = agent.generate(self.req).to_dict()
        self.assertEqual(result["status"], "failed")
        issue = agent.traces(self.req.task_id)[0]["issues"][0]
        self.assertEqual(issue["field"], "channels[0].content_direction")
        self.assertEqual((issue["category"], issue["severity"]), ("quality", "blocking"))

    def test_default_prompt_builds_strategic_choices_v14(self):
        builder = PromptBuilder()
        self.assertEqual(builder.version, "v1.4")
        self.assertIn("形成多个方向", builder.system_prompt)
        self.assertIn("一份有价值的策略必须做出选择", builder.system_prompt)

    def test_provided_budget_must_be_fully_assigned_with_purpose(self):
        weak = valid_data()
        weak["channels"][0]["allocated_amount"] = 600
        weak["channels"][0]["content_direction"] = weak["channels"][0]["content_direction"].replace("；预算用途：用于产品素材制作和发布准备", "")
        agent = StrategyAgent(ScriptedClient([json.dumps(weak, ensure_ascii=False)] * 3), sleeper=lambda _: None)
        result = agent.generate(self.req).to_dict()
        self.assertEqual(result["status"], "failed")
        messages = [item["message"] for item in agent.traces(self.req.task_id)[0]["issues"]]
        self.assertTrue(any("等于输入总预算" in message for message in messages))
        self.assertTrue(any("说明预算用于" in message for message in messages))

    def test_repair_freezes_unaffected_fields_and_channels(self):
        original = valid_data()
        new = valid_data()
        new["channels"][0]["reason"] = "待验证假设：面向大学生的社群发布须核实许可"
        new["channels"].append({**new["channels"][0], "name": "新增的未经核实地推"})
        new["selling_points"][0]["claim"] = "保证减肥"
        repaired = repair_only_reported_fields(original, new, [finding("fact")])
        self.assertEqual(repaired["selling_points"], original["selling_points"])
        self.assertEqual(len(repaired["channels"]), 1)
        self.assertEqual(repaired["channels"][0]["reason"], new["channels"][0]["reason"])

    def test_invalid_repair_path_does_not_skip_full_validation(self):
        original = valid_data()
        new = valid_data()
        new["channels"][0]["allocated_amount"] = 100000
        self.assertEqual(repair_only_reported_fields(original, new, [{"field": "__invalid__"}]), new)

    def test_labeled_reason_cannot_bypass_invented_product_claim(self):
        data = mark_planning_inferences(valid_data())
        data["selling_points"][0]["claim"] = "保证减肥"
        agent = StrategyAgent(ScriptedClient([json.dumps(data)] * 3), sleeper=lambda _: None)
        self.assertEqual(agent.generate(self.req).value["status"], "failed")

    def test_facts_and_constraints_still_block(self):
        for category in ("fact", "constraint"):
            with self.subTest(category=category):
                client = ReviewClient([finding(category)])
                agent = StrategyAgent(client, sleeper=lambda _: None)
                result = agent.generate(self.req).to_dict()
                self.assertEqual(result["status"], "failed")
                self.assertEqual(client.calls, 3)
                self.assertIsNone(result["data"])
                self.assertEqual(agent.history(self.req.task_id), [])
                self.assertNotIn(finding()["message"], result["error"]["message"])
                self.assertEqual(agent.traces(self.req.task_id)[-1]["issues"][0]["category"], category)
                self.assertIn(finding()["message"], client.prompts[1].user)

    def test_cannot_label_fact_as_advisory_to_bypass(self):
        item = finding("fact")
        item["severity"] = "advisory"
        result = StrategyAgent(ReviewClient([item]), sleeper=lambda _: None).generate(self.req).to_dict()
        self.assertEqual(result["status"], "failed")

    def test_deterministic_constraint_checks_not_relaxed(self):
        data = valid_data()
        data["channels"][0]["allocated_amount"] = 100000
        agent = StrategyAgent(ScriptedClient([json.dumps(data)] * 3), sleeper=lambda _: None)
        self.assertEqual(agent.generate(self.req).value["status"], "failed")

    def test_repair_context_not_truncated_at_6000(self):
        previous = json.dumps({"first": "x" * 7000, "last": "完整对象结尾"})
        prompt = PromptBuilder().build(self.req, attempt_count=2, validation_feedback=["修复字段"], previous_raw_output=previous)
        self.assertIn(previous, prompt.user)
        self.assertIn("最小修复", prompt.user)

    def test_progress_contains_validation_and_review_for_each_attempt(self):
        stages = []
        agent = StrategyAgent(ReviewClient([finding("fact")]), sleeper=lambda _: None)
        agent.generate(self.req, on_attempt=lambda n, s: stages.append((n, s)))
        for n in (1, 2, 3):
            self.assertIn((n, "validating"), stages)
            self.assertIn((n, "reviewing"), stages)

    def test_review_parser_classifies_and_requires_real_evidence(self):
        client = CompatibleModelClient(base_url="https://example.com/v1", api_key="test-only", model="test")
        for category in ("quality", "fact", "constraint"):
            item = finding(category)
            del item["severity"]
            with patch.object(client, "_complete", return_value=json.dumps({"issues": [item]})):
                issues, _ = client.review_strategy({}, valid_data())
                self.assertEqual(issues[0]["severity"], "advisory" if category == "quality" else "blocking")
        item["evidence"] = "复核器杜撰的证据"
        with patch.object(client, "_complete", return_value=json.dumps({"issues": [item]})):
            with self.assertRaises(ModelOutputError):
                client.review_strategy({}, valid_data())

    def test_failed_task_keeps_sanitized_diagnostics_not_raw_output(self):
        client = ReviewClient([finding("fact")])
        client.api_key = "not-a-real-key"
        client.findings[0]["message"] += client.api_key
        store = TaskStore(StrategyAgent(client, sleeper=lambda _: None), {"config_version": "test"})
        try:
            receipt = store.create(valid_payload()["requirements"], "owner")
            deadline = time.monotonic() + 2
            task = store.get(receipt["task_id"], "owner")
            while task["status"] not in ("completed", "failed") and time.monotonic() < deadline:
                time.sleep(.005)
                task = store.get(receipt["task_id"], "owner")
            self.assertEqual(task["status"], "failed")
            self.assertEqual(len(task["attempt_diagnostics"]), 3)
            self.assertNotIn("raw_output", json.dumps(task))
            self.assertNotIn(client.api_key, json.dumps(task))
            self.assertEqual(task["requirements"], valid_payload()["requirements"])
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
