from __future__ import annotations

import json
import threading
import unittest
from urllib import request
from http.cookiejar import CookieJar

from src.backend.strategy_web import create_server


class StrategyWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server("127.0.0.1", 0, provider="offline")
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        cls.opener.open(cls.base_url + "/api/session").close()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_health_endpoint(self):
        with request.urlopen(self.base_url + "/api/health", timeout=2) as response:
            value = json.loads(response.read().decode("utf-8"))
        self.assertEqual(value["status"], "ok")
        self.assertEqual(value["agent"], "strategy")

    def test_updated_assets_not_stale_cached(self):
        for path in ("/", "/workspace", "/styles.css?v=20261008-heros1", "/brief.js?v=20261008-brief1", "/app.js?v=20261008-clean1"):
            with request.urlopen(self.base_url + path, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-store")
                self.assertIn("default-src 'self'", response.headers["Content-Security-Policy"])

    def test_workbench_has_draft_recovery_and_separate_exports(self):
        with request.urlopen(self.base_url + "/workspace", timeout=2) as response:
            page = response.read().decode("utf-8")
        with request.urlopen(self.base_url + "/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")
        for element_id in ("draftStatus", "clearDraft", "retryTask", "exportStrategy", "exportResult", "exportCreative"):
            self.assertIn(f'id="{element_id}"', page)
        self.assertIn("localStorage.setItem(draftKey", script)
        self.assertIn('requestSubmit()', script)

    def test_workbench_has_guided_brief_templates_and_evidence_tools(self):
        with request.urlopen(self.base_url + "/workspace", timeout=2) as response:
            page = response.read().decode("utf-8")
        with request.urlopen(self.base_url + "/app.js", timeout=2) as response:
            script = response.read().decode("utf-8")
        for element_id in (
            "templatePanel",
            "budgetRaw",
            "startDate",
            "endDate",
            "wizardProgress",
            "recentTasks",
            "budgetSummary",
        ):
            self.assertIn(f'id="{element_id}"', page)
        for template_name in ("AI 学习产品", "奶茶门店", "智能手表", "护肤产品", "旅游产品"):
            self.assertIn(template_name, script)
        self.assertIn("formattedStrategy", script)
        self.assertIn("locateSource", script)
        self.assertIn("strategyResultArchive.v1", script)
        self.assertNotIn('id="workspaceDescription"', page)
        self.assertNotIn('class="field-help"', page)

    def test_workspace_serves_local_fonts(self):
        for face in ("regular", "bold"):
            with request.urlopen(self.base_url + f"/fonts/tex-gyre-heros/texgyreheros-{face}.otf", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(4), b"OTTO")

    def test_homepage_introduces_agent_and_links_to_workspace(self):
        with request.urlopen(self.base_url + "/", timeout=2) as response:
            page = response.read().decode("utf-8")
        for text in ("智策营销智能体", "有依据的营销策略", "策略取舍", "事实溯源", "创意接续"):
            self.assertIn(text, page)
        self.assertIn('href="/workspace"', page)
        self.assertIn('id="networkCanvas"', page)

    def test_generate_strategy_endpoint(self):
        payload = {
            "product_name": "原味奶茶",
            "product_description": "提供热饮和冷饮，可选择无糖或半糖。",
            "marketing_goal": "让附近大学生了解门店产品",
            "target_audience": "附近大学生",
            "budget": None,
            "campaign_period": None,
            "special_requirements": "不虚构优惠",
            "budget_raw": None,
        }
        http_request = request.Request(
            self.base_url + "/api/strategy",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener.open(http_request, timeout=2) as response:
            value = json.loads(response.read().decode("utf-8"))
        self.assertEqual(value["status"], "succeeded")
        self.assertEqual(value["data"]["target_audience"]["segment"], "附近大学生")


if __name__ == "__main__":
    unittest.main()
