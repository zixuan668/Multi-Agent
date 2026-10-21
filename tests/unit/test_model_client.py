import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from src.agents.strategy.errors import ConfigurationError, ModelOutputError, ModelAuthError
from src.agents.strategy.model_clients import CompatibleModelClient, NoModelRedirect, load_model_env
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.prompts import PromptBuilder
from tests.unit.test_models import valid_payload
from tests.unit.test_service import valid_data


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self
    def __exit__(self, *args):
        self.close()


class ModelClientTests(unittest.TestCase):
    def setUp(self):
        self.client = CompatibleModelClient(base_url="https://example.com/v1", api_key="unit-test-secret", model="test-model")

    def response(self, content):
        return FakeResponse(json.dumps({"choices": [{"message": {"content": content}}]}).encode())

    def test_editor_preserves_execution_and_distinguishes_optional_missing_facts(self):
        with patch.object(self.client, "_complete", return_value=json.dumps({"data":valid_data(),"issues":[]})) as complete:
            data, issues, _ = self.client.refine_strategy({}, valid_data())
        instructions = complete.call_args.args[0][0]["content"]
        self.assertIn("执行前核实事项", instructions)
        self.assertIn("未提供的可选信息", instructions)
        self.assertIn("不能归为fact或constraint阻断", instructions)
        self.assertEqual(data, valid_data())
        self.assertEqual(issues, [])

    def test_request_guard_caps_timeout_and_usage_is_observed(self):
        self.client.request_guard = Mock(return_value=3.5)
        self.client.usage_observer = Mock()
        usage = {"prompt_tokens":17,"completion_tokens":9}
        response = {"choices":[{"message":{"content":"{}"}}],"usage":usage}
        with patch("src.agents.strategy.model_clients.request.build_opener") as factory:
            factory.return_value.open.return_value = FakeResponse(json.dumps(response).encode())
            self.assertEqual(self.client.complete_json("system", "request"), {})
        self.assertEqual(factory.return_value.open.call_args.kwargs["timeout"],3.5)
        self.client.request_guard.assert_called_once_with()
        self.client.usage_observer.assert_called_once_with(usage)
        sent = json.loads(factory.return_value.open.call_args.args[0].data)
        self.assertNotIn("thinking", sent)

    def test_guard_rejection_prevents_network_request(self):
        self.client.request_guard = Mock(side_effect=ConfigurationError("execution stopped"))
        with patch("src.agents.strategy.model_clients.request.build_opener") as factory:
            with self.assertRaises(ConfigurationError):
                self.client.complete_json("system", "request")
        factory.assert_not_called()

    def test_official_deepseek_uses_explicit_low_effort_and_output_bound(self):
        client = CompatibleModelClient(base_url="https://api.deepseek.com",api_key="test-secret",model="deepseek-flash")
        with patch("src.agents.strategy.model_clients.request.build_opener") as factory:
            factory.return_value.open.return_value = self.response("{}")
            client.complete_json("system", "request")
        sent = json.loads(factory.return_value.open.call_args.args[0].data)
        self.assertEqual(sent["reasoning_effort"],"low")
        self.assertEqual(sent["thinking"],{"type":"enabled"})
        self.assertEqual(sent["max_tokens"],8192)

    def test_truncated_output_is_rejected_after_recording_usage(self):
        self.client.usage_observer = Mock()
        response = {"choices":[{"finish_reason":"length","message":{"content":"{}"}}],"usage":{"completion_tokens":8192}}
        with patch("src.agents.strategy.model_clients.request.build_opener") as factory:
            factory.return_value.open.return_value = FakeResponse(json.dumps(response).encode())
            with self.assertRaises(ModelOutputError):
                self.client.complete_json("system", "request")
        self.client.usage_observer.assert_called_once_with({"completion_tokens":8192})

    def test_real_adapter_sends_generation_and_review_requests(self):
        seen = []
        parent = self
        class Opener:
            def open(self, req, timeout):
                payload = json.loads(req.data)
                seen.append(payload)
                return parent.response(json.dumps(valid_data()) if len(seen) == 1 else '{"issues":[]}')
        prompt = PromptBuilder().build(StrategyRequest.from_dict(valid_payload()), attempt_count=1)
        with patch("src.agents.strategy.model_clients.request.build_opener", return_value=Opener()):
            output = self.client.generate_json(prompt)
            issues, raw = self.client.review_strategy(valid_payload()["requirements"], json.loads(output))
        self.assertEqual(len(seen), 2)
        self.assertEqual(issues, [])
        self.assertTrue(all(item["response_format"] == {"type": "json_object"} for item in seen))
        self.assertNotIn(self.client.api_key, json.dumps(seen))

    def test_review_structure_must_be_valid(self):
        with patch.object(self.client, "_complete", return_value='{"issues":"not-an-array"}'):
            with self.assertRaises(ModelOutputError):
                self.client.review_strategy({}, {})

    def test_refine_strategy_returns_rewritten_data_and_validated_findings(self):
        final = valid_data()
        raw = json.dumps({"data": final, "issues": []}, ensure_ascii=False)
        with patch.object(self.client, "_complete", return_value=raw):
            data, issues, evidence = self.client.refine_strategy(valid_payload()["requirements"], valid_data())
        self.assertEqual(data, final)
        self.assertEqual(issues, [])
        self.assertEqual(evidence, raw)

    def test_refine_strategy_rejects_commentary_instead_of_final_data(self):
        with patch.object(self.client, "_complete", return_value='{"advice":"写具体一点"}'):
            with self.assertRaises(ModelOutputError):
                self.client.refine_strategy({}, valid_data())

    def test_sensitive_provider_response_is_blocked(self):
        parent = self
        class Opener:
            def open(self, req, timeout):
                return parent.response(parent.client.api_key)
        prompt = PromptBuilder().build(StrategyRequest.from_dict(valid_payload()), attempt_count=1)
        with patch("src.agents.strategy.model_clients.request.build_opener", return_value=Opener()):
            with self.assertRaises(ModelOutputError) as caught:
                self.client.generate_json(prompt)
        self.assertNotIn(self.client.api_key, str(caught.exception))

    def test_redirect_is_not_followed(self):
        with self.assertRaises(ConfigurationError):
            NoModelRedirect().redirect_request(None, None, 302, "", {}, "http://unsafe.example")

    def test_env_parser_does_not_execute_and_environment_wins(self):
        # NamedTemporaryFile 是测试配置夹具，不是用户文件编辑。
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text('MODEL_NAME="file-model"\nMODEL_API_KEY=$(never-execute)\nMODEL_STREAMING=false\n', encoding="utf-8")
            with patch.dict("os.environ", {"MODEL_NAME": "environment-model"}, clear=True):
                load_model_env(path)
                import os
                self.assertEqual(os.environ["MODEL_NAME"], "environment-model")
                self.assertEqual(os.environ["MODEL_API_KEY"], "$(never-execute)")
                self.assertEqual(os.environ["MODEL_STREAMING"], "false")


if __name__ == "__main__":
    unittest.main()
