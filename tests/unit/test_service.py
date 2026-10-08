from __future__ import annotations

import json
import unittest

from src.agents.strategy.errors import ModelAuthError, ModelTimeoutError
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.service import StrategyAgent
from tests.unit.test_models import valid_payload


def valid_data() -> dict:
    return {
        "target_audience": {
            "segment": "附近大学生",
            "needs": ["日常饮品选择"],
            "pain_points": ["甜度选择有限"],
            "age_range": None,
            "occupation": "大学生",
            "basis": "用户明确指定目标人群为附近大学生",
        },
        "positioning": "面向附近大学生，在选择日常饮品时，以可选择无糖或半糖这一特点介绍原味奶茶，帮助了解门店产品",
        "selling_points": [
            {"claim": "可选择无糖或半糖", "source_quote": "可选择无糖或半糖"}
        ],
        "channels": [
            {
                "name": "校园社群",
                "reason": "原味奶茶可围绕冷热和甜度选择制作产品信息，校园社群用于服务附近大学生了解门店产品，适配程度需验证",
                "content_direction": "内容：制作“可选择无糖或半糖”的产品说明；发布：通过校园社群发布产品图文；执行前核实：社群发布权限、素材和产品信息；预算用途：用于产品素材制作和发布准备",
                "allocated_amount": 1000,
            }
        ],
        "marketing_strategy": {
            "theme": "清楚了解原味奶茶的冷热和甜度选择",
            "content_directions": ["内容主张：原味奶茶提供冷热和甜度选择；事实依据：可选择无糖或半糖；表现形式：产品选项图文；行动引导：了解门店产品"],
            "promotion_methods": ["执行动作：制作并发布校园社群产品介绍；核实：发布权限、产品信息和素材"],
        },
        "assumptions": ["目标人群关注甜度选择，需验证"],
        "missing_information": [],
        "constraint_conflicts": [],
    }


class ScriptedClient:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def generate_json(self, prompt):
        self.calls += 1
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class StrategyAgentTests(unittest.TestCase):
    def setUp(self):
        self.request = StrategyRequest.from_dict(valid_payload())

    def test_generates_valid_response(self):
        client = ScriptedClient([json.dumps(valid_data(), ensure_ascii=False)])
        response = StrategyAgent(client, sleeper=lambda _: None).generate(self.request).to_dict()
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["version"], 1)
        self.assertEqual(response["attempt_count"], 1)

    def test_retries_invalid_output_with_validation_feedback(self):
        client = ScriptedClient(["not-json", json.dumps(valid_data(), ensure_ascii=False)])
        delays = []
        response = StrategyAgent(client, sleeper=delays.append).generate(self.request).to_dict()
        self.assertEqual(response["status"], "succeeded")
        self.assertEqual(response["attempt_count"], 2)
        self.assertEqual(delays, [1.0])

    def test_timeout_exhaustion_returns_failed(self):
        client = ScriptedClient([ModelTimeoutError("超时")] * 3)
        response = StrategyAgent(client, sleeper=lambda _: None).generate(self.request).to_dict()
        self.assertEqual(response["status"], "failed")
        self.assertEqual(response["attempt_count"], 3)
        self.assertEqual(response["error"]["code"], "MODEL_TIMEOUT")

    def test_auth_failure_does_not_retry(self):
        client = ScriptedClient([ModelAuthError("鉴权失败")])
        response = StrategyAgent(client, sleeper=lambda _: None).generate(self.request).to_dict()
        self.assertEqual(response["status"], "failed")
        self.assertEqual(client.calls, 1)
        self.assertEqual(response["error"]["code"], "MODEL_AUTH_FAILED")

    def test_version_increments_without_overwriting(self):
        client = ScriptedClient(
            [json.dumps(valid_data(), ensure_ascii=False), json.dumps(valid_data(), ensure_ascii=False)]
        )
        agent = StrategyAgent(client, sleeper=lambda _: None)
        first = agent.generate(self.request).to_dict()
        second = agent.generate(self.request).to_dict()
        self.assertEqual((first["version"], second["version"]), (1, 2))
        self.assertNotEqual(first["result_id"], second["result_id"])

    def test_rejects_budget_over_allocation(self):
        data = valid_data()
        data["channels"][0]["allocated_amount"] = 2000
        client = ScriptedClient([json.dumps(data, ensure_ascii=False)] * 3)
        response = StrategyAgent(client, sleeper=lambda _: None).generate(self.request).to_dict()
        self.assertEqual(response["status"], "failed")
        self.assertEqual(response["error"]["code"], "OUTPUT_INVALID")


if __name__ == "__main__":
    unittest.main()
