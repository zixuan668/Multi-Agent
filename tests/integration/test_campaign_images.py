from http.cookiejar import CookieJar
import json
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, build_opener

from src.agents.strategy.errors import AccessDeniedError, ConfigurationError, ContractValidationError, ModelUnavailableError
from src.backend.image_generation import CampaignImages, image_info
from tests.integration import test_campaigns as fixtures
from tests.integration import test_campaign_web as http_fixtures
from tests.unit.test_image_generation import PNG


class FakeImageClient:
    model = 'fake-image-model'

    def __init__(self):
        self.calls = []
        self.gate = threading.Event()
        self.gate.set()
        self.fail = False

    def generate(self, prompt, *, aspect_ratio=None):
        self.calls.append(prompt)
        self.gate.wait(5)
        if self.fail:
            raise ModelUnavailableError('SetLimitExceeded: test error')
        return {'data': PNG, **image_info(PNG), 'model': self.model, 'usage': {'generated_images': 1}}


class CampaignImageTests(unittest.TestCase):
    store = fixtures.CampaignTests.store
    wait = fixtures.CampaignTests.wait

    def setUp(self):
        fixtures.CampaignTests.setUp(self)
        self.campaigns = self.store(provider='offline')
        self.task = self.wait(self.campaigns, self.campaigns.create(fixtures.requirements(), 'owner-1', 'image-fixture')['task_id'])
        self.client = FakeImageClient()
        self.images = CampaignImages(self.campaigns, client=self.client)

    def tearDown(self):
        self.client.gate.set()
        self.images.close()
        self.images.executor.shutdown(wait=True)
        fixtures.CampaignTests.tearDown(self)

    def create(self, key='image-request-1', **overrides):
        return self.images.create(self.task['task_id'], 'owner-1', {'round_no': 1, 'item_index': 0, 'submission_key': key, **overrides})

    def finished(self):
        for attempt in range(300):
            task = self.campaigns.get(self.task['task_id'], 'owner-1')
            if not self.images.active:
                return task
            time.sleep(.01)
        self.fail('image job did not finish')

    def test_success_is_versioned_private_and_idempotent(self):
        self.create()
        task = self.finished()
        job = task['image_jobs'][0]
        self.assertEqual(job['status'], 'succeeded')
        self.assertEqual(job['review_status'], 'pending_human')
        self.assertEqual(job['creative_result_id'], task['rounds'][0]['creative']['result_id'])
        self.assertNotIn('_filename', json.dumps(task))
        self.assertNotIn('_request_key', json.dumps(task))
        self.assertEqual(self.images.read(task['task_id'], 'owner-1', job['image_id'])[0], PNG)
        self.create()
        self.assertEqual(len(self.client.calls), 1)
        self.assertEqual(task['usage'], self.task['usage'])
        with self.assertRaises(AccessDeniedError):
            self.images.read(task['task_id'], 'stranger', job['image_id'])

    def test_active_requests_merge_and_failed_regeneration_preserves_image(self):
        self.client.gate.clear()
        first = self.create()
        second = self.create('different-request')
        self.assertEqual(first['image_jobs'][0]['image_id'], second['image_jobs'][0]['image_id'])
        self.client.gate.set()
        job = self.finished()['image_jobs'][0]
        self.client.fail = True
        self.create('second-deliberate-request')
        task = self.finished()
        self.assertEqual([item['status'] for item in task['image_jobs']], ['succeeded', 'failed'])
        self.assertEqual(self.images.read(task['task_id'], 'owner-1', job['image_id'])[0], PNG)
        self.assertEqual(len(self.client.calls), 2)

    def test_invalid_refs_and_missing_config_do_not_call(self):
        for overrides in ({'round_no': 999}, {'item_index': -1}, {'item_index': True}, {'submission_key': 'short'}):
            with self.subTest(overrides=overrides), self.assertRaises(ContractValidationError):
                self.create(**overrides)
        self.images.client = None
        with self.assertRaises(ConfigurationError):
            self.create()
        self.assertEqual(self.client.calls, [])

    def test_per_task_limit_prevents_extra_paid_requests(self):
        for index in range(6):
            self.create('request-number-' + str(index))
            self.finished()
        with self.assertRaises(ModelUnavailableError):
            self.create('request-number-7')
        self.assertEqual(len(self.client.calls), 6)

    def test_restart_marks_job_interrupted_without_calling(self):
        self.campaigns.repository.update(self.task['task_id'], lambda task: task.update(image_jobs=[{'image_id': 'pending-job', 'status': 'running'}]))
        self.images.close()
        self.images.executor.shutdown(wait=True)
        self.images = CampaignImages(self.campaigns, client=self.client)
        task = self.campaigns.get(self.task['task_id'], 'owner-1')
        self.assertEqual(task['image_jobs'][0]['status'], 'interrupted')
        self.assertEqual(self.client.calls, [])

    def test_preview_is_free_and_edited_plan_is_persisted_with_version(self):
        preview = self.images.preview(self.task['task_id'], 'owner-1', 1, 0)
        self.assertEqual(self.client.calls, [])
        plan = {**preview['plan'], 'headline': '温度你定，糖度你选'}
        self.create(poster_plan=plan)
        job = self.finished()['image_jobs'][0]
        self.assertEqual(job['poster_plan']['headline'], plan['headline'])
        self.assertEqual(job['prompt_version'], preview['version'])
        self.assertIn(plan['headline'], job['prompt'])
        self.assertFalse(job['visible_watermark'])
        with self.assertRaises(ContractValidationError):
            self.create(poster_plan={**plan, 'headline': '不同的方案'})
        self.assertEqual(len(self.client.calls), 1)

    def test_unsupported_poster_claim_is_blocked_before_paid_call(self):
        preview = self.images.preview(self.task['task_id'], 'owner-1', 1, 0)
        with self.assertRaises(ContractValidationError):
            self.create(poster_plan={**preview['plan'], 'headline': '保证通过考试'})
        self.assertEqual(self.client.calls, [])


class ImageHttpTests(unittest.TestCase):
    get = http_fixtures.CampaignHttpTests.get
    post = http_fixtures.CampaignHttpTests.post
    completed_task = http_fixtures.CampaignHttpTests.completed_task

    def setUp(self):
        import tempfile
        from pathlib import Path
        from src.backend.campaign_web import create_server

        self.directory = tempfile.TemporaryDirectory()
        self.fake = FakeImageClient()
        self.server = create_server(port=0, provider='offline', database=Path(self.directory.name) / 'images.sqlite3', image_client_factory=lambda: self.fake)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.client = build_opener(HTTPCookieProcessor(CookieJar()))
        self.get('/api/session')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.application.images.executor.shutdown(wait=True)
        self.server.application.campaigns.executor.shutdown(wait=True)
        self.thread.join()
        self.directory.cleanup()

    def test_owner_download_report_and_duplicate_post(self):
        task = self.completed_task()
        route = '/api/campaigns/' + task['task_id']
        preview = self.get(route + '/image-plan?round=1&item=0')
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(preview['plan']['layout'], 'top_hero_bottom')
        payload = {'round_no': 1, 'item_index': 0, 'submission_key': 'http-image-request'}
        self.post(route + '/images', payload)
        for attempt in range(300):
            task = self.get(route)
            if task['image_jobs'][0]['status'] == 'succeeded':
                break
            time.sleep(.01)
        job = task['image_jobs'][0]
        with self.client.open(self.base + job['uri'] + '?download=1') as response:
            self.assertEqual(response.headers.get_content_type(), 'image/png')
            self.assertIn('attachment', response.headers['Content-Disposition'])
            self.assertEqual(response.read(), PNG)
        self.post(route + '/images', payload)
        self.assertEqual(len(self.fake.calls), 1)
        report = self.get(route + '/report')
        self.assertEqual(report['image_jobs'][0]['image_id'], job['image_id'])
        self.assertNotIn('_filename', json.dumps(report))
        self.assertNotIn('_request_key', json.dumps(report))
        stranger = build_opener(HTTPCookieProcessor(CookieJar()))
        stranger.open(self.base + '/api/session').close()
        with self.assertRaises(HTTPError) as caught:
            stranger.open(self.base + job['uri'])
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()


if __name__ == '__main__':
    unittest.main()
