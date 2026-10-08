from copy import deepcopy
import json
import threading
import time
import unittest

from src.agents.strategy.downstream import build_creative_request, validate_creative_request
from src.agents.strategy.errors import ConfigurationError, ContractValidationError
from src.agents.strategy.model_clients import CompatibleModelClient
from src.agents.strategy.models import MarketingRequirements, StrategyData, StrategyRequest, StrategyResponse
from src.agents.strategy.service import StrategyAgent
from src.agents.strategy.validation import validate_business_rules
from src.backend.tasks import TaskStore
from tests.unit.test_models import valid_payload
from tests.unit.test_service import ScriptedClient, valid_data


class ContractTests(unittest.TestCase):
    def test_numeric_strings_are_not_json_numbers(self):
        payload = valid_payload()["requirements"]
        payload["budget"]["amount"] = "1000"
        with self.assertRaises(ContractValidationError):
            MarketingRequirements.from_dict(payload)

    def test_date_requires_dashed_format(self):
        payload = valid_payload()["requirements"]
        payload["campaign_period"] = {"start_date": "20261001", "end_date": "20261002"}
        with self.assertRaises(ContractValidationError):
            MarketingRequirements.from_dict(payload)

    def test_missing_nullable_request_field_rejected(self):
        payload = valid_payload()
        del payload["creative"]
        with self.assertRaises(ContractValidationError):
            StrategyRequest.from_dict(payload)

    def test_failed_response_cannot_have_business_result(self):
        response = StrategyAgent(ScriptedClient([json.dumps(valid_data())])).generate(StrategyRequest.from_dict(valid_payload())).to_dict()
        response["status"] = "failed"
        with self.assertRaises(ContractValidationError):
            StrategyResponse.from_dict(response)

    def test_https_and_config_limits(self):
        for extra in ({"base_url": "http://example.com/v1"}, {"timeout_seconds": 9}, {"temperature": float("nan")}, {"base_url": "https://user:password@example.com"}):
            settings = {"base_url": "https://example.com/v1", "api_key": "test-only", "model": "test-model"}
            settings.update(extra)
            with self.assertRaises(ConfigurationError):
                CompatibleModelClient(**settings)


class ConstraintTests(unittest.TestCase):
    def check(self, special, data=None, *, budget=1000):
        payload = valid_payload()
        payload["requirements"]["special_requirements"] = special
        payload["requirements"]["budget"]["amount"] = budget
        return validate_business_rules(StrategyData.from_dict(data or valid_data()), StrategyRequest.from_dict(payload))

    def test_forbidden_channel(self):
        self.assertTrue(self.check("禁止使用校园社群"))

    def test_required_channel(self):
        self.assertTrue(self.check("必须使用小红书"))

    def test_channel_conflict_is_reported_without_using_forbidden_channel(self):
        data = valid_data()
        data["channels"][0]["name"] = "门店自有社群"
        self.assertTrue(self.check("必须使用抖音；禁止使用抖音", data))
        data["constraint_conflicts"] = ["抖音同时被必选与禁用"]
        self.assertEqual(self.check("必须使用抖音；禁止使用抖音", data), [])

    def test_zero_budget_cannot_use_paid_channel_even_without_allocation(self):
        data = valid_data()
        data["channels"][0].update(name="付费达人合作", allocated_amount=None)
        self.assertTrue(self.check("", data, budget=0))

    def test_forbidden_expression(self):
        data = valid_data()
        data["marketing_strategy"]["theme"] = "全网最低价"
        self.assertTrue(self.check('禁止出现“全网最低价”', data))

    def test_false_fact(self):
        data = valid_data()
        data["selling_points"][0]["claim"] = "国家认证健康饮品"
        self.assertTrue(self.check("", data))

    def test_unknown_occupation_rejected(self):
        data = valid_data()
        data["target_audience"]["occupation"] = "律师"
        self.assertTrue(self.check("", data))

    def test_dates_outside_period(self):
        data = valid_data()
        data["marketing_strategy"]["promotion_methods"] = ["2026-12-01开展宣传"]
        self.assertTrue(self.check("", data))

    def test_duration_schedule_does_not_exceed_input(self):
        data = valid_data()
        data["marketing_strategy"]["promotion_methods"] = ["第31天开展推广"]
        self.assertTrue(self.check("", data))


class VersionAndReviewTests(unittest.TestCase):
    def test_immutable_inputs_and_result_copies(self):
        agent = StrategyAgent(ScriptedClient([json.dumps(valid_data())] * 2))
        payload = valid_payload()
        response = agent.generate(StrategyRequest.from_dict(payload)).to_dict()
        response["data"]["positioning"] = "外部修改"
        self.assertNotEqual(agent.history(payload["task_id"])[0]["data"]["positioning"], "外部修改")
        payload["requirements"]["marketing_goal"] = "修改原始需求"
        result = agent.generate(StrategyRequest.from_dict(payload)).to_dict()
        self.assertEqual(result["error"]["code"], "INPUT_INVALID")
        self.assertEqual(len(agent.history(payload["task_id"])), 1)

    def test_previous_result_cannot_forge_version(self):
        agent = StrategyAgent(ScriptedClient([json.dumps(valid_data())] * 2))
        payload = valid_payload()
        first = agent.generate(StrategyRequest.from_dict(payload)).to_dict()
        payload.update(round_no=2, previous_result=deepcopy(first))
        payload["previous_result"]["version"] = 99
        self.assertEqual(agent.generate(StrategyRequest.from_dict(payload)).value["status"], "failed")
        self.assertEqual(len(agent.history(payload["task_id"])), 1)

    def test_valid_optimization_passes_full_previous_and_feedback(self):
        class Client(ScriptedClient):
            def generate_json(self, prompt):
                self.last_prompt = prompt
                return super().generate_json(prompt)
        client = Client([json.dumps(valid_data())] * 2)
        agent = StrategyAgent(client)
        payload = valid_payload()
        first = agent.generate(StrategyRequest.from_dict(payload)).to_dict()
        payload.update(round_no=2, previous_result=first, feedback=[{"feedback_id": "f1", "evaluation_id": "e1", "target_agent": "strategy", "target_path": "channels[0].reason", "issue": "理由不充分", "suggestion": "说明校园触达关系", "priority": "medium", "resolved": False}])
        second = agent.generate(StrategyRequest.from_dict(payload)).to_dict()
        self.assertEqual(second["version"], 2)
        self.assertIn(first["result_id"], client.last_prompt.user)
        self.assertIn("说明校园触达关系", client.last_prompt.user)
        self.assertEqual(len(agent.history(payload["task_id"])), 2)

    def test_semantic_review_causes_retry(self):
        class Client(ScriptedClient):
            def review_strategy(self, requirements, data):
                return (["selling_points[0]: 卖点引文不支持该事实"] if self.calls == 1 else []), '{"issues":[]}'
        agent = StrategyAgent(Client([json.dumps(valid_data())] * 2), sleeper=lambda _: None)
        result = agent.generate(StrategyRequest.from_dict(valid_payload())).to_dict()
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(agent.traces("task-001")[0]["error_code"], "OUTPUT_INVALID")

    def test_timeout_does_not_commit_late_success(self):
        release = threading.Event()
        class Client:
            timeout_seconds = .02
            def generate_json(self, prompt):
                release.wait(.5)
                return json.dumps(valid_data())
        agent = StrategyAgent(Client(), sleeper=lambda _: None)
        result = agent.generate(StrategyRequest.from_dict(valid_payload())).to_dict()
        release.set()
        time.sleep(.02)
        self.assertEqual(result["error"]["code"], "MODEL_TIMEOUT")
        self.assertEqual(result["attempt_count"], 3)
        self.assertEqual(agent.history("task-001"), [])

    def test_downstream_rejects_cross_task_and_invalid_schema(self):
        req = StrategyRequest.from_dict(valid_payload())
        result = StrategyAgent(ScriptedClient([json.dumps(valid_data())])).generate(req).to_dict()
        payload = build_creative_request(req, result)
        self.assertEqual(payload["strategy"]["result_id"], result["result_id"])
        payload["strategy"]["task_id"] = "other-task"
        with self.assertRaises(ContractValidationError):
            validate_creative_request(payload)

    def test_downstream_rejects_strategy_without_creative_handoff_detail(self):
        req = StrategyRequest.from_dict(valid_payload())
        result = StrategyAgent(ScriptedClient([json.dumps(valid_data())])).generate(req).to_dict()
        payload = build_creative_request(req, result)
        payload["strategy"]["data"]["channels"][0]["content_direction"] = "介绍产品"
        with self.assertRaises(ContractValidationError):
            validate_creative_request(payload)


if __name__ == "__main__":
    unittest.main()
