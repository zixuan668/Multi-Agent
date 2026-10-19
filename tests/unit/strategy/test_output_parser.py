from copy import deepcopy
import json
import unittest
from unittest.mock import patch

from src.agents.strategy.errors import ModelOutputError
from src.agents.strategy.output_parser import parse_model_object
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.service import StrategyAgent
from src.agents.strategy.validation import _has_paid_action
from src.agents.strategy.model_clients import CompatibleModelClient
from tests.unit.test_model_client import FakeResponse
from tests.unit.test_models import valid_payload
from tests.unit.test_service import ScriptedClient, valid_data


class OutputParserTests(unittest.TestCase):
    def test_missing_root_brace_and_misplaced_notes_preserve_all_values(self):
        data=valid_data()
        misplaced=deepcopy(data)
        for key in ('assumptions','missing_information','constraint_conflicts'):
            misplaced['marketing_strategy'][key]=misplaced.pop(key)
        raw=json.dumps(misplaced,ensure_ascii=False)[:-1]
        repaired,events=parse_model_object(raw)
        self.assertEqual(repaired,data)
        self.assertEqual(len(events),2)
        client=ScriptedClient([raw])
        req=StrategyRequest.from_dict(valid_payload())
        agent=StrategyAgent(client)
        self.assertEqual(agent.generate(req).value['status'],'succeeded')
        self.assertEqual(client.calls,1)
        self.assertEqual(len(agent.traces(req.task_id)[0]['syntax_repairs']),2)

    def test_omitted_array_closing_before_object_end(self):
        data=valid_data()
        raw=json.dumps(data)
        before=', "assumptions"'
        start=raw.index(before)
        self.assertEqual(raw[start-2:start],']}')
        malformed=raw[:start-2]+raw[start-1:]
        result,events=parse_model_object(malformed)
        self.assertEqual(result,data)
        self.assertEqual(len(events),1)

    def test_duplicates_missing_text_values_and_commentary_are_not_guessed(self):
        for raw in ('{"a":1,"a":2}','{"a":','{"a":"unfinished','```json\n{}\n```','{} trailing text','[1,2]'):
            with self.subTest(raw=raw):
                with self.assertRaises(ModelOutputError):parse_model_object(raw)

    def test_only_one_copy_of_root_notes_is_not_overwritten(self):
        data=valid_data()
        data['marketing_strategy']['assumptions']=['不能覆盖']
        parsed,events=parse_model_object(json.dumps(data))
        self.assertEqual(parsed['assumptions'],valid_data()['assumptions'])
        self.assertEqual(events,[])

    def test_zero_budget_negation_does_not_hide_positive_paid_action(self):
        for text in ('不付费推广','无需付费的门店展示','不做付费推广；禁止达人合作','不投放付费渠道','不新增付费物料','不使用任何付费投放','预算0，不产生付费投放','不涉及任何付费推广'):
            self.assertFalse(_has_paid_action(text))
        for text in ('付费达人合作','不付费推广，但安排达人合作','不做付费推广而使用信息流广告','不得不付费推广','不能不付费推广'):
            self.assertTrue(_has_paid_action(text))

    def test_truncated_provider_completion_is_rejected_even_if_json_is_valid(self):
        payload={'choices':[{'finish_reason':'length','message':{'content':json.dumps(valid_data())}}]}
        class Opener:
            def open(self,*args,**kwargs):return FakeResponse(json.dumps(payload).encode())
        client=CompatibleModelClient(base_url='https://example.com/v1',api_key='unit-test-only',model='test')
        with patch('src.agents.strategy.model_clients.request.build_opener',return_value=Opener()):
            with self.assertRaises(ModelOutputError):client._complete([])
