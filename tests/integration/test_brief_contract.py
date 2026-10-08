"""Frontend enrichment must reach the unchanged backend and strategy prompt."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.prompts import PromptBuilder
from src.backend.strategy_web import build_request_payload


class BriefContractTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node.js is needed for frontend mapping verification")
    def test_actual_frontend_payload_reaches_backend_and_prompt(self):
        root = Path(__file__).resolve().parents[2]
        output = subprocess.run(
            ["node", "tests/frontend/test_brief.cjs", "--payload"],
            cwd=root, check=True, capture_output=True, encoding="utf-8", timeout=10,
        )
        payload = json.loads(output.stdout)
        request = StrategyRequest.from_dict(build_request_payload(payload))
        prompt = PromptBuilder().build(request, attempt_count=1)
        self.assertEqual(request.requirements.budget.amount, 5000)
        self.assertIn('可以选择“无糖”或半糖', request.requirements.product_description)
        self.assertIn("店员每天可投入 30 分钟", prompt.user)
        self.assertIn("门店微信群", prompt.user)
        self.assertIn("12 元 / 杯", prompt.user)
        self.assertIn("none=确认没有", prompt.system)
        self.assertEqual(prompt.request.schema_version, "1.0")
