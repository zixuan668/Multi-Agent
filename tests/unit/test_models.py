from __future__ import annotations

import unittest

from src.agents.strategy.errors import ContractValidationError
from src.agents.strategy.models import MarketingRequirements, StrategyRequest


def valid_payload() -> dict:
    return {
        "schema_version": "1.0",
        "task_id": "task-001",
        "agent": "strategy",
        "round_no": 1,
        "attempt_count": 1,
        "requirements": {
            "product_name": "原味奶茶",
            "product_description": "提供热饮和冷饮，可选择无糖或半糖。",
            "marketing_goal": "提升产品认知",
            "target_audience": "附近大学生",
            "budget": {"amount": 1000, "currency": "CNY"},
            "campaign_period": {"duration_days": 30},
            "special_requirements": "不虚构优惠",
            "budget_raw": "1000元",
        },
        "strategy": None,
        "creative": None,
        "feedback": [],
        "previous_result": None,
        "config_version": "config-v1",
    }


class MarketingRequirementsTests(unittest.TestCase):
    def test_normalizes_blank_optionals(self):
        raw = valid_payload()["requirements"]
        raw["target_audience"] = "  "
        result = MarketingRequirements.from_dict(raw)
        self.assertIsNone(result.target_audience)
        self.assertEqual(result.budget.currency, "CNY")

    def test_rejects_lowercase_currency(self):
        raw = valid_payload()["requirements"]
        raw["budget"]["currency"] = "cny"
        with self.assertRaises(ContractValidationError):
            MarketingRequirements.from_dict(raw)

    def test_rejects_missing_required_field(self):
        raw = valid_payload()["requirements"]
        del raw["product_name"]
        with self.assertRaises(ContractValidationError):
            MarketingRequirements.from_dict(raw)

    def test_rejects_conflicting_period_forms(self):
        raw = valid_payload()["requirements"]
        raw["campaign_period"] = {
            "start_date": "2026-10-01",
            "end_date": "2026-10-31",
            "duration_days": 30,
        }
        with self.assertRaises(ContractValidationError):
            MarketingRequirements.from_dict(raw)

    def test_rejects_budget_with_more_than_two_decimals(self):
        raw = valid_payload()["requirements"]
        raw["budget"]["amount"] = "12.345"
        with self.assertRaises(ContractValidationError):
            MarketingRequirements.from_dict(raw)


class StrategyRequestTests(unittest.TestCase):
    def test_accepts_valid_request(self):
        result = StrategyRequest.from_dict(valid_payload())
        self.assertEqual(result.agent, "strategy")
        self.assertEqual(result.requirements.budget.currency, "CNY")

    def test_rejects_non_null_creative(self):
        raw = valid_payload()
        raw["creative"] = {}
        with self.assertRaises(ContractValidationError):
            StrategyRequest.from_dict(raw)


if __name__ == "__main__":
    unittest.main()
