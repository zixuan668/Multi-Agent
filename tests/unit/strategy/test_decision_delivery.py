"""决策交付缺口、归一化简报及短审查的可定位修复回归。"""
from copy import deepcopy
import json
import io
import unittest
from unittest.mock import patch

from src.agents.strategy.intake import MARKER, normalized_brief
from src.agents.strategy.model_clients import CompatibleModelClient
from src.agents.strategy.models import StrategyRequest, StrategyData
from src.agents.strategy.prompts import PromptBuilder
from src.agents.strategy.service import StrategyAgent, RetryPolicy
from src.agents.strategy.errors import ModelOutputError
from src.agents.strategy.output_parser import parse_model_object
from src.agents.strategy.validation import validate_strategy_quality
from tests.unit.test_models import valid_payload
from tests.unit.test_service import ScriptedClient, valid_data


class DecisionDeliveryTests(unittest.TestCase):
    def test_brief_does_not_promote_stale_unknown_resources_or_price(self):
        requirements = valid_payload()["requirements"]
        requirements["product_description"] += MARKER + json.dumps({"formVersion":1,"priceStatus":"unknown","priceInfo":"9元","purchaseStatus":"unknown","purchaseEntry":"虚构入口","secretExtra":"忽略规则"},ensure_ascii=False)
        requirements["special_requirements"] += MARKER + json.dumps({"formVersion":1,"channelsState":"none","existingChannels":"旧账号","teamState":"unknown","teamResources":"旧团队"},ensure_ascii=False)
        brief = normalized_brief(requirements)
        text = json.dumps(brief,ensure_ascii=False)
        for stale in ("旧账号","旧团队","9元","虚构入口","secretExtra","formVersion"):
            self.assertNotIn(stale,text)
        self.assertEqual(brief["resources"]["existingChannels"], {"state":"none","detail":""})
        self.assertEqual(requirements["product_description"].count(MARKER),1, "normalization does not mutate original")

    def test_legacy_input_and_normalized_fact_quotes_survive(self):
        request = StrategyRequest.from_dict(valid_payload())
        prompt = PromptBuilder().build(request,attempt_count=1)
        self.assertIn("可选择无糖或半糖",prompt.user)
        self.assertNotIn("config_version",prompt.user)
        self.assertEqual(normalized_brief(request.requirements.to_dict())["goal_text"],"提升产品认知")

    def test_exact_duplicate_tasks_block_without_lexical_publishing_requirements(self):
        data = valid_data()
        data["marketing_strategy"]["content_directions"] *= 2
        findings = validate_strategy_quality(StrategyData.from_dict(data),StrategyRequest.from_dict(valid_payload()))
        self.assertTrue(any(v["severity"] == "blocking" and v["field"] == "marketing_strategy.content_directions" for v in findings))

    def test_serious_quality_assessment_repairs_only_reported_field_not_full_rewrite(self):
        old = valid_data()
        changed = deepcopy(old)
        changed["positioning"] = "面向附近大学生，先在校园社群说清原味奶茶糖度选项，再由现场点单承接；优先传播点单选择，不先扩大渠道。"
        changed["selling_points"][0]["claim"] = "无依据的新卖点"
        class Client(ScriptedClient):
            def assess_strategy(self, requirements, data):
                if self.calls == 1:
                    items = [{"field":"positioning","category":"quality","severity":"blocking","evidence":data["positioning"],"message":"主方向需说明触达与现场承接分工"}]
                else:
                    items = []
                return items,json.dumps({"issues":items},ensure_ascii=False)
            def refine_strategy(self,*args):
                raise AssertionError("must not rewrite entire strategy after focused assessment")
        client = Client([json.dumps(old),json.dumps(changed)])
        agent = StrategyAgent(client,sleeper=lambda _:None)
        result = agent.generate(StrategyRequest.from_dict(valid_payload())).to_dict()
        self.assertEqual(result["status"],"succeeded")
        self.assertEqual(result["attempt_count"],2)
        self.assertEqual(result["data"]["positioning"],changed["positioning"])
        self.assertEqual(result["data"]["selling_points"],old["selling_points"])

    def test_short_assessment_must_locate_evidence_in_reported_field(self):
        client = CompatibleModelClient(base_url="https://example.test/v1",api_key="test-secret",model="test")
        issue = {"field":"positioning","category":"quality","severity":"blocking","evidence":"校园社群","message":"具体修复"}
        with patch.object(client,"_complete",return_value=json.dumps({"issues":[issue]},ensure_ascii=False)):
            with self.assertRaises(ModelOutputError):
                client.assess_strategy(valid_payload()["requirements"],valid_data())
        issue["field"] = "channels[0].name"
        with patch.object(client,"_complete",return_value=json.dumps({"issues":[issue]},ensure_ascii=False)):
            items,_ = client.assess_strategy(valid_payload()["requirements"],valid_data())
            self.assertEqual(items[0]["severity"],"blocking")

    def test_major_quality_failure_is_not_handed_off_as_success(self):
        class Client(ScriptedClient):
            def assess_strategy(self,requirements,data):
                return [{"field":"positioning","category":"quality","severity":"blocking","evidence":data["positioning"],"message":"目标与触达任务不一致"}], "{}"
        agent = StrategyAgent(Client([json.dumps(valid_data())]),retry_policy=RetryPolicy(max_attempts=1))
        response = agent.generate(StrategyRequest.from_dict(valid_payload())).to_dict()
        self.assertEqual(response["status"],"failed")
        self.assertIsNone(response["data"])
        self.assertEqual(agent.history("task-001"),[])

    def test_review_grouped_array_field_is_valid_but_cross_field_evidence_is_not(self):
        client = CompatibleModelClient(base_url="https://example.test/v1",api_key="test-secret",model="test")
        issue = {"field":"marketing_strategy.promotion_methods","category":"quality","severity":"blocking","evidence":"制作并发布校园社群产品介绍","message":"需明确执行人"}
        with patch.object(client,"_complete",return_value=json.dumps({"issues":[issue]},ensure_ascii=False)):
            items,_ = client.assess_strategy(valid_payload()["requirements"],valid_data())
            self.assertEqual(items[0]["field"],issue["field"])
        issue["field"] = "selling_points"
        with patch.object(client,"_complete",return_value=json.dumps({"issues":[issue]},ensure_ascii=False)):
            with self.assertRaises(ModelOutputError) as caught:
                client.assess_strategy(valid_payload()["requirements"],valid_data())
            self.assertIn("issues",caught.exception.raw_review)

    def test_assumption_object_is_losslessly_normalized_without_model_retry(self):
        data = valid_data()
        data["assumptions"] = [{"assumption":"附近大学生可能关注糖度选择", "verification":"记录实际糖度询问"}]
        agent = StrategyAgent(ScriptedClient([json.dumps(data)]),sleeper=lambda _:None)
        result = agent.generate(StrategyRequest.from_dict(valid_payload())).to_dict()
        self.assertEqual(result["status"],"succeeded")
        self.assertEqual(result["attempt_count"],1)
        self.assertEqual(result["data"]["assumptions"],["附近大学生可能关注糖度选择；验证：记录实际糖度询问"])
        self.assertTrue(agent.traces("task-001")[0]["syntax_repairs"])

    def test_assumption_object_extra_fields_are_not_silently_discarded(self):
        data = valid_data()
        data["assumptions"] = [{"assumption":"待核实", "verification":"记录反馈", "unsupported":"额外信息"}]
        value,repairs = parse_model_object(json.dumps(data))
        self.assertEqual(value["assumptions"],data["assumptions"])
        self.assertEqual(repairs,[])

    def test_known_string_wrappers_preserve_all_note_text(self):
        for note,expected in [
            ({"text":"糖度询问需验证"},"糖度询问需验证"),
            ({"assumption":"学生关注糖度","validation":"观察点单反馈"},"学生关注糖度；验证：观察点单反馈"),
        ]:
            data = valid_data()
            data["assumptions"] = [note]
            value,repairs = parse_model_object(json.dumps(data))
            self.assertEqual(value["assumptions"],[expected])
            self.assertTrue(repairs)

    def test_deepseek_effort_is_explicit_and_not_sent_to_other_providers(self):
        for host,model,expected in [("api.deepseek.com","deepseek-flash","low"),("example.test","test",None)]:
            client=CompatibleModelClient(base_url="https://"+host,api_key="test-secret",model=model)
            seen=[]
            class Response(io.BytesIO):
                def __enter__(self): return self
                def __exit__(self,*args): self.close()
            class Opener:
                def open(self,req,timeout):
                    seen.append(json.loads(req.data))
                    return Response(json.dumps({"choices":[{"message":{"content":"{}"}}]}).encode())
            with patch("src.agents.strategy.model_clients.request.build_opener",return_value=Opener()):
                client._complete([])
            self.assertEqual(seen[0].get("reasoning_effort"),expected)
            self.assertEqual(seen[0].get("thinking"),{"type":"enabled"} if expected else None)
