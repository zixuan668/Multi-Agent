import base64
import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from src.agents.strategy.errors import ConfigurationError, ModelOutputError, ModelTimeoutError, ModelUnavailableError
from src.backend.image_generation import VolcengineImageClient, image_info


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jB1sAAAAASUVORK5CYII=')


class ImageClientTests(unittest.TestCase):
    def client(self, **overrides):
        return VolcengineImageClient(**{'base_url': 'https://ark.cn-beijing.volces.com/api/v3', 'api_key': 'test-secret-not-real', 'model': 'test-model', **overrides})

    @patch('src.backend.image_generation.request.build_opener')
    def test_one_request_uses_base64_and_explicit_visible_watermark_setting(self, build):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'data': [{'b64_json': base64.b64encode(PNG).decode()}]}).encode()
        build.return_value.open.return_value = response
        result = self.client(watermark=False).generate('测试广告', aspect_ratio='3:4')
        self.assertEqual(result['data'], PNG)
        self.assertEqual(result['width'], 1)
        self.assertEqual(result['usage'], {'generated_images': 1})
        call = build.return_value.open.call_args.args[0]
        payload = json.loads(call.data)
        self.assertEqual(call.full_url, 'https://ark.cn-beijing.volces.com/api/v3/images/generations')
        self.assertEqual(call.get_header('Authorization'), 'Bearer test-secret-not-real')
        self.assertEqual(payload['response_format'], 'b64_json')
        self.assertFalse(payload['watermark'])
        self.assertEqual(payload['size'], '1728x2304')
        self.assertFalse(payload['stream'])
        build.return_value.open.assert_called_once()

    @patch('src.backend.image_generation.request.build_opener')
    def test_limit_error_redacts_secret_without_retry(self, build):
        error = {'error': {'code': 'SetLimitExceeded', 'message': 'denied test-secret-not-real'}}
        build.return_value.open.side_effect = HTTPError('https://ark.cn-beijing.volces.com', 429, 'limit', {}, io.BytesIO(json.dumps(error).encode()))
        with self.assertRaises(ModelUnavailableError) as caught:
            self.client().generate('广告')
        self.assertIn('SetLimitExceeded', str(caught.exception))
        self.assertNotIn('test-secret-not-real', str(caught.exception))
        build.return_value.open.assert_called_once()

    @patch('src.backend.image_generation.request.build_opener')
    def test_timeout_does_not_retry_or_claim_no_charge(self, build):
        build.return_value.open.side_effect = TimeoutError()
        with self.assertRaises(ModelTimeoutError) as caught:
            self.client().generate('广告')
        self.assertIn('可能仍在生成或计费', str(caught.exception))
        build.return_value.open.assert_called_once()

    def test_external_hosts_and_invalid_settings_are_rejected(self):
        for base in ('http://ark.cn-beijing.volces.com/api/v3', 'https://evil.example/api/v3', 'https://ark.cn-beijing.volces.com/api/v3?key=x', 'https://user@ark.cn-beijing.volces.com/api/v3'):
            with self.subTest(base=base), self.assertRaises(ConfigurationError):
                self.client(base_url=base)
        self.assertIsNone(VolcengineImageClient.from_settings({}))
        settings = {'IMAGE_BASE_URL': 'https://ark.cn-beijing.volces.com/api/v3', 'IMAGE_API_KEY': 'not-real', 'IMAGE_MODEL': 'test-model', 'IMAGE_WATERMARK': 'true'}
        self.assertTrue(VolcengineImageClient.from_settings(settings).watermark)
        with self.assertRaises(ConfigurationError):
            VolcengineImageClient.from_settings({**settings, 'IMAGE_WATERMARK': 'maybe'})
        with self.assertRaises(ModelOutputError):
            image_info(b'<svg>not a raster image</svg>')

    @patch('src.backend.image_generation.request.build_opener')
    def test_malformed_images_and_url_only_responses_do_not_fallback(self, build):
        for data in ([], [None], [{'url': 'https://example.com/image.png'}], [{'b64_json': 'invalid'}], [{}, {}]):
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps({'data': data}).encode()
            build.return_value.open.return_value = response
            with self.subTest(data=data), self.assertRaises(ModelOutputError):
                self.client().generate('广告')
        self.assertEqual(build.return_value.open.call_count, 5)


if __name__ == '__main__':
    unittest.main()
