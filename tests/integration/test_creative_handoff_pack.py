"""可交给队友的静态样例始终与生产校验规则一致。"""
import json
from pathlib import Path
import shutil
import unittest

from src.agents.strategy.downstream import validate_creative_request
from src.agents.strategy.errors import ContractValidationError
from ops.run_strategy_acceptance import select_cases


class HandoffPackTests(unittest.TestCase):
    def test_saved_examples_accept_and_reject_as_documented(self):
        root=Path(__file__).resolve().parents[2]/'tests/fixtures/creative'
        paths=list(root.glob('*.json'))
        self.assertEqual(len(paths),12)
        for path in paths:
            with self.subTest(path=path.name):
                payload=json.loads(path.read_text(encoding='utf-8'))
                if path.name.startswith('valid-'):
                    self.assertEqual(validate_creative_request(payload),payload)
                else:
                    with self.assertRaises(ContractValidationError): validate_creative_request(payload)

    def test_small_fixed_suite_spans_all_five_products(self):
        cases=select_cases('fixed',5)
        self.assertEqual(len(set(item['category'] for item in cases)),5)
        self.assertEqual(len(select_cases()),50)
        with self.assertRaises(ValueError):select_cases('fixed',case_ids='unknown')

    @unittest.skipUnless(shutil.which('node'),'guided form mapping requires Node.js')
    def test_guided_resources_change_without_changing_product_facts(self):
        cases={item['case_id']:item['request'] for item in select_cases('guided')}
        known,unknown,zero=(cases[key].requirements for key in ('milk-owned','milk-unknown','milk-zero'))
        self.assertEqual(known.product_description,unknown.product_description)
        self.assertEqual(known.product_description,zero.product_description)
        self.assertIn('店员每天可投入 30 分钟',known.special_requirements)
        self.assertNotIn('店员每天可投入 30 分钟',unknown.special_requirements)
        self.assertIn('"channelsState":"unknown"',unknown.special_requirements)
        self.assertEqual(zero.budget.amount,0)
        self.assertIn('"channelsState":"none"',zero.special_requirements)
        self.assertIsNone(cases['missing-context'].requirements.target_audience)
