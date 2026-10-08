import io
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

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
            path.write_text('MODEL_NAME="file-model"\nMODEL_API_KEY=$(never-execute)\n', encoding="utf-8")
            with patch.dict("os.environ", {"MODEL_NAME": "environment-model"}, clear=True):
                load_model_env(path)
                import os
                self.assertEqual(os.environ["MODEL_NAME"], "environment-model")
                self.assertEqual(os.environ["MODEL_API_KEY"], "$(never-execute)")


if __name__ == "__main__":
    unittest.main()
