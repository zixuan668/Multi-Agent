from __future__ import annotations

import unittest

from src.agents.strategy.model_clients import RuleBasedModelClient
from src.agents.strategy.models import StrategyData, StrategyRequest
from src.agents.strategy.service import StrategyAgent
from src.agents.strategy.downstream import build_creative_request


CATEGORIES = [
    ("AI学习助手", "提供错题整理和学习计划功能。", "帮助大学生了解学习工具"),
    ("原味奶茶", "提供热饮和冷饮，可选择无糖或半糖。", "提升门店周边认知"),
    ("智能手表", "支持消息提醒和运动记录。", "让通勤人群了解产品特点"),
    ("轻盈粉底液", "提供自然色号和哑光妆效选择。", "介绍产品特点与使用场景"),
    ("古城周末游", "提供两日行程规划和景点介绍服务。", "吸引周末出行游客"),
]


def make_request(index: int, category: tuple[str, str, str]) -> StrategyRequest:
    name, description, goal = category
    payload = {
        "schema_version": "1.0",
        "task_id": f"acceptance-{index:02d}",
        "agent": "strategy",
        "round_no": 1,
        "attempt_count": 1,
        "requirements": {
            "product_name": f"{name}{index}",
            "product_description": description,
            "marketing_goal": goal,
            "target_audience": "附近大学生" if "奶茶" in name else None,
            "budget": {"amount": 1000 + index * 10, "currency": "CNY"} if index % 2 == 0 else None,
            "campaign_period": {"duration_days": 14 + index % 10} if index % 3 == 0 else None,
            "special_requirements": "不虚构优惠，不承诺未经验证的效果",
            "budget_raw": None,
        },
        "strategy": None,
        "creative": None,
        "feedback": [],
        "previous_result": None,
        "config_version": "acceptance-v1",
    }
    return StrategyRequest.from_dict(payload)


class FirstStageAcceptanceTests(unittest.TestCase):
    def test_fifty_offline_tasks_produce_downstream_usable_results(self):
        agent = StrategyAgent(RuleBasedModelClient(), sleeper=lambda _: None)
        successes = 0
        signatures = set()
        for index in range(50):
            request = make_request(index, CATEGORIES[index // 10])
            response = agent.generate(request).to_dict()
            if response["status"] == "succeeded":
                StrategyData.from_dict(response["data"])
                build_creative_request(request, response)
                successes += 1
                signatures.add(
                    (
                        response["data"]["target_audience"]["segment"],
                        response["data"]["channels"][0]["name"],
                        response["data"]["marketing_strategy"]["theme"],
                    )
                )
        self.assertGreaterEqual(successes, 48)
        self.assertGreaterEqual(len(signatures), 5)


if __name__ == "__main__":
    unittest.main()
