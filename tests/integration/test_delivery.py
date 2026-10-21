from copy import deepcopy
import json
import unittest
from unittest.mock import Mock
from xml.etree import ElementTree

from src.backend.briefing import brief_questions, partition_draft_questions
from src.backend.posters import render_poster, wrap_text
from src.agents.strategy.errors import ContractValidationError, ModelOutputError
from src.agents.creative import CreativeAgent
from tests.integration import test_campaigns as fixtures
from tests.integration.test_campaigns import ScriptedClient, requirements


class DeliveryTests(unittest.TestCase):
    setUp = fixtures.CampaignTests.setUp
    tearDown = fixtures.CampaignTests.tearDown
    store = fixtures.CampaignTests.store
    wait = fixtures.CampaignTests.wait

    def test_brief_blocks_missing_action_path_without_any_model_call(self):
        client = ScriptedClient()
        store = self.store(client)
        brief = requirements()
        brief["marketing_goal"] = "让大学生申请试用"
        task = store.create(brief, "owner-1", "brief-before-calls", interactive=True, choose_directions=False)
        self.assertEqual(task["status"], "awaiting_input")
        self.assertEqual(task["usage"]["model_calls"], 0)
        self.assertEqual(client.calls, [])
        self.assertEqual(task["clarification_agent"], "strategy")
        continued = store.clarify(task["task_id"], "owner-1", {"message": "申请入口：https://example.com/trial", "submission_key": "confirmed-trial-path"})
        finished = self.wait(store, continued["task_id"])
        self.assertEqual(finished["parent_task_id"], task["task_id"])
        self.assertFalse(finished["choose_directions"])
        self.assertNotEqual(finished["termination_reason"], "brief_incomplete")
        self.assertEqual(store.get(task["task_id"], "owner-1")["requirements"], brief)

    def test_optional_facts_do_not_block_awareness_campaign(self):
        brief = requirements()
        self.assertEqual(brief_questions(brief), [])
        brief["marketing_goal"] = "介绍产品，不引导申请试用"
        self.assertEqual(brief_questions(brief), [])
        brief["marketing_goal"] = "介绍产品，引导报名"
        brief["special_requirements"] = "报名入口待确认，不要编造"
        self.assertEqual(len(brief_questions(brief)), 1)
        brief["product_description"] += " 报名链接：https://example.com/join"
        self.assertEqual(brief_questions(brief), [])

    def test_direct_delivery_skips_editor_and_directions_but_keeps_review_checkpoint(self):
        client = ScriptedClient()
        client.refine_strategy = Mock(side_effect=AssertionError("不应固定二次编辑"))
        store = self.store(client)
        task = self.wait(store, store.create(requirements(), "owner-1", "direct-first-draft", interactive=True, choose_directions=False)["task_id"])
        self.assertEqual([call[0] for call in client.calls], ["strategy", "creative", "evaluation"])
        client.refine_strategy.assert_not_called()
        self.assertEqual(task["status"], "awaiting_revision")
        self.assertNotIn("directions", task["rounds"][0])
        self.assertEqual(len(task["rounds"]), 1)
        with self.assertRaises(ContractValidationError):
            store.create(requirements(), "owner-1", "direct-first-draft", interactive=True, choose_directions=True)

    def test_poster_renders_versioned_text_and_escapes_xml(self):
        store = self.store(provider="offline")
        task = self.wait(store, store.create(requirements(), "owner-1", "poster-render-safe")["task_id"])
        modified = deepcopy(task)
        modified["rounds"][0]["creative"]["data"]["items"][0]["headline"] = '<script>alert("x")</script> & 标题'
        content = render_poster(modified, 1, 0, "paper").decode()
        root = ElementTree.fromstring(content)
        self.assertEqual(root.attrib["width"], "1080")
        self.assertEqual(root.attrib["height"], "1440")
        self.assertNotIn("<script>", content)
        self.assertIn("&lt;script&gt;", content)
        self.assertIn("排版草稿", content)
        self.assertNotIn("<image", content)
        self.assertNotIn("foreignObject", content)
        self.assertEqual(wrap_text("中文ABC", 4), ["中文", "ABC"])
        with self.assertRaises(ContractValidationError):
            render_poster(task, 999, 0)
        with self.assertRaises(ContractValidationError):
            render_poster(task, 1, -1)
        with self.assertRaises(ContractValidationError):
            render_poster(task, 1, 0, "unknown")
        modified["status"] = "approved"
        modified["selected_round"] = 1
        self.assertNotIn("排版草稿", render_poster(modified, 1, 0).decode())

    def test_near_duplicate_directions_trigger_targeted_retry(self):
        client = Mock()
        first = {"title": "方向一", "headline": "标题", "idea": "晚自习结束，用三栏表对照学习计划、错题归纳和复盘提醒，逐项核对当日备考流程。", "rationale": "适合大学生"}
        second = {**first, "title": "方向二", "idea": first["idea"] + "认真核对。"}
        client.complete_json.return_value = {"directions": [first, second]}
        with self.assertRaises(ModelOutputError):
            CreativeAgent(client).propose({}, "test", progress=lambda attempt: None)
        self.assertEqual(client.complete_json.call_count, 3)
        correction = json.loads(client.complete_json.call_args.args[1])["validation_feedback"]
        self.assertIn("过于相似", correction)

    def test_preparation_does_not_block_draft_but_real_consumer_claims_still_do(self):
        planning = {"question": "校园账号发布权限和门店位置是否确认？", "reason": "发布前准备", "target_path": "strategy.assumptions[0]", "evidence": "权限待确认"}
        factual = {"question": "申请试用的真实入口是什么？", "reason": "文案要求跳转", "target_path": "creative.items[0].call_to_action", "evidence": "申请试用"}
        missing = {"question": "售价是否确认为29元？", "reason": "不应编造价格", "target_path": "strategy.assumptions[1]", "evidence": "售价假设29元"}
        blocking, notes = partition_draft_questions([planning, factual, missing])
        self.assertEqual(blocking, [factual, missing])
        self.assertEqual(notes, [planning])

    def test_planning_questions_never_hide_severe_risks_or_change_scores(self):
        class PlanningClient(ScriptedClient):
            def complete_json(self, system, user):
                data = super().complete_json(system, user)
                if "独立方案评审" in system:
                    request = json.loads(user)["request"]
                    for score in data["dimension_scores"].values():
                        score["score"] = 85
                    data["feedback"] = []
                    data["clarifications"] = [{"question": "是否已有校园账号发布权限？", "reason": "发布前需要确认", "target_path": "strategy.channels[0].reason", "evidence": request["strategy"]["data"]["channels"][0]["reason"][:100]}]
                return data

        for unsafe in (False, True):
            client = PlanningClient(unsafe=unsafe)
            store = self.store(client)
            task = self.wait(store, store.create(requirements(), "owner-1", "planning-"+str(unsafe), interactive=True, choose_directions=False)["task_id"])
            row = task["rounds"][0]
            self.assertEqual(row["evaluation"]["data"]["total_score"], 85)
            self.assertEqual(row["evaluation"]["data"]["clarifications"], [])
            self.assertEqual(len(row["preparation_notes"]), 1)
            self.assertEqual(task["status"], "awaiting_revision" if unsafe else "awaiting_confirmation")
