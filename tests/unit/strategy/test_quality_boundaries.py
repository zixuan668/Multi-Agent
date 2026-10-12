"""不将格式偏好包装成硬约束；事实问题不能因核实字样被放行。"""
from copy import deepcopy
import json
import unittest

from src.agents.strategy.downstream import build_creative_request, validate_creative_request
from src.agents.strategy.errors import ContractValidationError
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.service import StrategyAgent
from tests.unit.test_models import valid_payload
from tests.unit.test_service import ScriptedClient, valid_data


class QualityBoundaryTests(unittest.TestCase):
    def test_only_confirmed_legacy_price_value_is_product_evidence(self):
        for status,expected in [('known','succeeded'),('unknown','failed')]:
            with self.subTest(status=status):
                payload=valid_payload()
                payload['requirements']['product_description']+='\n\n【智策需求补充 v1】\n'+json.dumps({'formVersion':1,'priceStatus':status,'priceInfo':'12 元 / 杯'},ensure_ascii=False)
                data=valid_data()
                data['selling_points'][0]={'claim':'价格12元每杯','source_quote':'12 元 / 杯'}
                result=StrategyAgent(ScriptedClient([json.dumps(data)]*3),sleeper=lambda _:None).generate(StrategyRequest.from_dict(payload)).to_dict()
                self.assertEqual(result['status'],expected)

    def test_editor_retry_cannot_rewrite_an_unreported_valid_selling_point(self):
        class Client(ScriptedClient):
            def refine_strategy(self,requirements,draft):
                if self.calls==1:
                    issues=[{'field':'channels[0].reason','category':'fact','severity':'blocking','evidence':draft['channels'][0]['reason'],'message':'需修正理由'}]
                else:
                    draft['selling_points'][0]['claim']='保证减肥'
                    issues=[]
                return draft,issues,json.dumps({'data':draft,'issues':issues})
        client=Client([json.dumps(valid_data())]*3)
        req=StrategyRequest.from_dict(valid_payload())
        response=StrategyAgent(client,sleeper=lambda _:None).generate(req).to_dict()
        self.assertEqual(response['status'],'succeeded')
        self.assertEqual(response['attempt_count'],2)
        self.assertEqual(response['data']['selling_points'],valid_data()['selling_points'])

    def test_semantic_execution_without_lexical_markers_does_not_retry(self):
        data = valid_data()
        data['channels'][0].update(content_direction='一张糖度选项对照图配门店点单入口，群管理员同意后发出。',allocated_amount=600)
        req = StrategyRequest.from_dict(valid_payload())
        client = ScriptedClient([json.dumps(data)])
        agent = StrategyAgent(client)
        response = agent.generate(req).to_dict()
        self.assertEqual(response['status'], 'succeeded')
        self.assertEqual(client.calls, 1)
        validate_creative_request(build_creative_request(req, response))
        self.assertTrue(agent.traces(req.task_id)[0]['review_notes'])

    def test_fact_in_verification_sentence_is_not_downgraded(self):
        data = valid_data()
        data['channels'][0]['content_direction'] += '；确认本品有独家技术后宣传'
        class Client(ScriptedClient):
            def refine_strategy(self, requirements, draft):
                return draft, [{'field':'channels[0].content_direction','category':'fact','severity':'blocking','evidence':'确认本品有独家技术后宣传','message':'独家技术无依据'}], '{}'
        client = Client([json.dumps(data)] * 3)
        req = StrategyRequest.from_dict(valid_payload())
        response = StrategyAgent(client, sleeper=lambda _:None).generate(req).to_dict()
        self.assertEqual(response['status'], 'failed')
        self.assertIsNone(response['data'])

    def test_quote_cannot_use_resource_or_metadata_as_product_fact(self):
        for quote in ('店员每天可投入 30 分钟', 'formVersion'):
            with self.subTest(quote=quote):
                payload = valid_payload()
                payload['requirements']['product_description'] += '\n\n【智策需求补充 v1】\n' + json.dumps({'formVersion':1,'teamResources':'店员每天可投入 30 分钟'},ensure_ascii=False)
                data = valid_data()
                data['selling_points'][0]={'claim':quote,'source_quote':quote}
                response=StrategyAgent(ScriptedClient([json.dumps(data)]*3),sleeper=lambda _:None).generate(StrategyRequest.from_dict(payload)).to_dict()
                self.assertEqual(response['status'],'failed')

    def test_forbidden_claim_in_constraints_is_not_product_evidence(self):
        payload=valid_payload()
        payload['requirements']['special_requirements']='不承诺保证减肥'
        data=valid_data()
        data['selling_points'][0]['claim']='保证减肥'
        response=StrategyAgent(ScriptedClient([json.dumps(data)]*3),sleeper=lambda _:None).generate(StrategyRequest.from_dict(payload)).to_dict()
        self.assertEqual(response['status'],'failed')

    def test_first_round_handoff_rejects_other_strategy_round(self):
        req=StrategyRequest.from_dict(valid_payload())
        response=StrategyAgent(ScriptedClient([json.dumps(valid_data())])).generate(req).to_dict()
        payload=build_creative_request(req,response)
        payload['strategy']['round_no']=2
        with self.assertRaises(ContractValidationError): validate_creative_request(payload)

    def test_copy_does_not_mutate_saved_handoff(self):
        req=StrategyRequest.from_dict(valid_payload())
        response=StrategyAgent(ScriptedClient([json.dumps(valid_data())])).generate(req).to_dict()
        payload=build_creative_request(req,response)
        original=deepcopy(payload)
        accepted=validate_creative_request(payload)
        accepted['strategy']['data']['positioning']='外部修改'
        self.assertEqual(payload,original)
