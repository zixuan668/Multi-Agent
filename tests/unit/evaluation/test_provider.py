from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch
from urllib import error

from src.agents.evaluation.provider import EvaluationConfig,EvaluationError,EvaluationProvider
from src.agents.evaluation.examples import draft_template


class Response:
    def __init__(self,raw):self.raw=raw
    def __enter__(self):return self
    def __exit__(self,*_):pass
    def read(self,*_):return self.raw


class ProviderTests(unittest.TestCase):
    def config(self,**kwargs):return EvaluationConfig('https://api.deepseek.com','never-print-this',**kwargs)

    def test_safe_snapshot_and_invalid_configuration(self):
        config=self.config()
        self.assertNotIn(config.api_key,repr(config));self.assertNotIn(config.api_key,json.dumps(config.snapshot()))
        for kwargs in ({'pass_threshold':math.nan},{'timeout_seconds':9},{'max_attempts':4},{'max_rounds':4},{'max_rounds':True}):
            with self.assertRaises(ValueError):self.config(**kwargs)
        for url in ('http://api.deepseek.com','https://user:pass@example.com','https://example.com/?token=secret'):
            with self.assertRaises(ValueError):EvaluationConfig(url,'secret')

    @patch('src.agents.evaluation.provider.request.build_opener')
    def test_json_mode_and_context_transmitted_with_no_model_control_fields(self,build):
        draft=draft_template();wire={'choices':[{'message':{'content':json.dumps(draft)},'finish_reason':'stop'}]}
        build.return_value.open.return_value=Response(json.dumps(wire).encode())
        provider=EvaluationProvider(self.config());payload={'request':{'requirements':{'product_name':'demo'}}}
        self.assertEqual(provider.call(payload),draft)
        req=build.return_value.open.call_args.args[0];body=json.loads(req.data)
        self.assertEqual(body['response_format'],{'type':'json_object'})
        self.assertIn('json',body['messages'][0]['content'])
        self.assertEqual(json.loads(body['messages'][1]['content']),payload)

    @patch('src.agents.evaluation.provider.request.build_opener')
    def test_auth_and_truncated_output_are_classified_without_leaking_body(self,build):
        provider=EvaluationProvider(self.config())
        build.return_value.open.side_effect=error.HTTPError('https://api.deepseek.com',401,'contains-secret',{},None)
        with self.assertRaises(EvaluationError) as ctx:provider.call({})
        self.assertEqual(ctx.exception.code,'MODEL_AUTH_FAILED');self.assertNotIn('contains-secret',str(ctx.exception))
        build.return_value.open.side_effect=None
        build.return_value.open.return_value=Response(json.dumps({'choices':[{'message':{'content':'{}'},'finish_reason':'length'}]}).encode())
        with self.assertRaises(EvaluationError) as ctx:provider.call({})
        self.assertEqual(ctx.exception.code,'OUTPUT_INVALID')


if __name__=='__main__':unittest.main()
