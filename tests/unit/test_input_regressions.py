"""少量多样输入回归，不作为正式50例或人工验收结论。"""
from __future__ import annotations

import unittest

from src.agents.strategy.downstream import build_creative_request
from src.agents.strategy.model_clients import RuleBasedModelClient
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.service import StrategyAgent


CASES = (
    ("AI学习助手", "提供错题整理和学习计划功能。", "帮助大学生了解学习工具", None, None, None),
    ("原味奶茶", "提供热饮和冷饮，可选择无糖或半糖。", "让附近大学生了解门店产品", "附近大学生", 5000, "必须使用门店自有社群；不虚构优惠"),
    ("智能手表", "支持消息提醒和运动记录。", "介绍产品特点", "通勤人群", 0, "禁止使用科技内容平台"),
    ("轻盈粉底液", "提供自然色号和哑光妆效选择。", "介绍使用场景", None, 1200, "不承诺未经验证的效果"),
    ("古城周末游", "提供两日行程规划和景点介绍服务。", "帮助游客了解服务", "周末出行游客", None, "禁止使用旅游内容社区"),
    ("企业培训", "提供线上直播课程与课后资料。", "让企业客户了解课程", "企业培训负责人", 8000, None),
)


class InputRegressionTests(unittest.TestCase):
    def test_varied_inputs_complete_once_and_keep_actionable_channel_detail(self):
        for index, (name, description, goal, audience, budget, special) in enumerate(CASES):
            with self.subTest(name=name):
                requirements = {
                    "product_name": name,
                    "product_description": description,
                    "marketing_goal": goal,
                    "target_audience": audience,
                    "budget": {"amount": budget, "currency": "CNY"} if budget is not None else None,
                    "campaign_period": {"duration_days": 21} if index % 2 == 0 else None,
                    "special_requirements": special,
                    "budget_raw": f"{budget} CNY" if budget is not None else None,
                }
                request = StrategyRequest.from_dict({
                    "schema_version": "1.0", "task_id": f"regression-{index}", "agent": "strategy",
                    "round_no": 1, "attempt_count": 1, "requirements": requirements,
                    "strategy": None, "creative": None, "feedback": [], "previous_result": None,
                    "config_version": "regression-v1",
                })
                agent = StrategyAgent(RuleBasedModelClient(), sleeper=lambda _: None)
                response = agent.generate(request).to_dict()
                self.assertEqual(response["status"], "succeeded")
                self.assertEqual(response["attempt_count"], 1)
                self.assertIn("执行前核实", response["data"]["channels"][0]["content_direction"])
                self.assertIn(description.rstrip("。"), response["data"]["selling_points"][0]["source_quote"])
                build_creative_request(request, response)


if __name__ == "__main__":
    unittest.main()
