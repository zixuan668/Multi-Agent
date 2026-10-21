from copy import deepcopy
import json
import unittest
from urllib.error import HTTPError
from urllib.request import Request
from uuid import uuid4

from src.agents.strategy.errors import AccessDeniedError, ContractValidationError
from src.backend.history import CampaignHistory
from src.backend.image_generation import CampaignImages
from tests.integration import test_campaigns as fixtures
from tests.integration import test_campaign_web as http_fixtures


class HistoryTests(unittest.TestCase):
    store = fixtures.CampaignTests.store
    wait = fixtures.CampaignTests.wait

    def setUp(self):
        fixtures.CampaignTests.setUp(self)
        self.campaigns = self.store(provider='offline')
        self.task = self.wait(self.campaigns, self.campaigns.create(fixtures.requirements(), 'owner-1', 'history-test-fixture')['task_id'])
        self.images = CampaignImages(self.campaigns)
        self.history = CampaignHistory(self.campaigns, self.images)

    def tearDown(self):
        self.images.close()
        self.images.executor.shutdown(wait=True)
        fixtures.CampaignTests.tearDown(self)

    def test_archive_restore_retains_results_and_never_runs_models(self):
        task_id = self.task['task_id']
        self.history.archive(task_id, 'owner-1')
        self.assertEqual(self.campaigns.list('owner-1'), [])
        self.assertEqual(self.campaigns.list('owner-1', deleted=True)[0]['task_id'], task_id)
        with self.assertRaises(AccessDeniedError):
            self.campaigns.get(task_id, 'owner-1')
        restored = self.history.restore(task_id, 'owner-1')
        self.assertEqual(restored['rounds'], self.task['rounds'])
        self.assertEqual(restored['usage'], self.task['usage'])
        self.assertEqual(restored['status'], self.task['status'])
        self.assertNotIn(task_id, self.campaigns.active)
        self.assertFalse(self.campaigns.list('owner-1', deleted=True))

    def test_archive_restore_owner_scope_and_idempotency(self):
        for action in (self.history.archive, self.history.restore):
            with self.assertRaises(AccessDeniedError):
                action(self.task['task_id'], 'other-owner')
        self.history.archive(self.task['task_id'], 'owner-1')
        self.history.archive(self.task['task_id'], 'owner-1')
        self.assertEqual(len(self.campaigns.list('owner-1', deleted=True)), 1)
        with self.assertRaises(ContractValidationError):
            self.campaigns.create(fixtures.requirements(), 'owner-1', 'history-test-fixture')

    def test_active_text_or_images_cannot_be_deleted(self):
        task_id = self.task['task_id']
        self.campaigns.active.add(task_id)
        try:
            with self.assertRaises(ContractValidationError):
                self.history.archive(task_id, 'owner-1')
        finally:
            self.campaigns.active.discard(task_id)
        self.campaigns.repository.update(task_id, lambda task: task.update(image_jobs=[{'status': 'running'}]))
        self.assertFalse(self.campaigns.list('owner-1')[0]['deletable'])
        with self.assertRaises(ContractValidationError):
            self.history.archive(task_id, 'owner-1')
        result = self.history.clear('owner-1')
        self.assertEqual(result['task_ids'], [])
        self.assertEqual(result['skipped_ids'], [task_id])

    def test_clear_is_owner_scoped_and_not_limited_to_first_100(self):
        original = self.campaigns.repository.get(self.task['task_id'], 'owner-1')
        for index in range(104):
            task = deepcopy(original)
            task.update(task_id='campaign-'+uuid4().hex, submission_key='extra-'+str(index))
            self.campaigns.repository.insert(task)
        foreign = deepcopy(original)
        foreign.update(task_id='campaign-'+uuid4().hex, owner_scope='other-owner', submission_key='foreign-history')
        self.campaigns.repository.insert(foreign)
        result = self.history.clear('owner-1')
        self.assertEqual(len(result['task_ids']), 105)
        self.assertEqual(self.campaigns.list('owner-1'), [])
        self.assertEqual(self.campaigns.get(foreign['task_id'], 'other-owner')['task_id'], foreign['task_id'])
        self.assertEqual(self.history.clear('owner-1')['task_ids'], [])

    def test_list_review_matches_its_saved_round(self):
        summary = self.campaigns.list('owner-1')[0]
        row = next(row for row in self.task['rounds'] if row['round_no'] == summary['review']['round_no'])
        self.assertEqual(summary['review']['total_score'], row['evaluation']['data']['total_score'])
        self.assertEqual(summary['review']['provider'], 'offline')
        self.assertNotIn('owner_scope', json.dumps(summary))
        self.history.archive(self.task['task_id'], 'owner-1')
        repository = self.campaigns.repository.__class__(self.path)
        self.assertEqual(repository.list('owner-1'), [])
        self.assertEqual(len(repository.list('owner-1', deleted=True)), 1)


class HistoryHttpTests(unittest.TestCase):
    setUp = http_fixtures.CampaignHttpTests.setUp
    tearDown = http_fixtures.CampaignHttpTests.tearDown
    get = http_fixtures.CampaignHttpTests.get
    post = http_fixtures.CampaignHttpTests.post
    completed_task = http_fixtures.CampaignHttpTests.completed_task

    def test_archive_get_report_restore_and_clear_routes(self):
        task = self.completed_task()
        route = '/api/campaigns/' + task['task_id']
        self.post(route + '/archive', {})
        self.assertEqual(self.get('/api/campaigns')['tasks'], [])
        self.assertEqual(self.get('/api/campaigns?deleted=1')['tasks'][0]['task_id'], task['task_id'])
        for suffix in ('', '/report', '/poster.svg'):
            with self.assertRaises(HTTPError) as caught:
                self.get(route + suffix)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
        restored = self.post(route + '/restore', {})
        self.assertEqual(restored['usage'], task['usage'])
        self.assertEqual(restored['rounds'], task['rounds'])
        self.assertEqual(self.post('/api/campaigns/history/clear', {})['task_ids'], [task['task_id']])

    def test_foreign_origin_and_payload_cannot_modify_history(self):
        task = self.completed_task()
        route = '/api/campaigns/' + task['task_id']
        for action in ('archive', 'restore'):
            with self.assertRaises(HTTPError) as caught:
                self.post(route + '/' + action, {}, origin='https://evil.example')
            self.assertEqual(caught.exception.code, 400)
            caught.exception.close()
        with self.assertRaises(HTTPError) as caught:
            self.post('/api/campaigns/history/clear', {'owner': 'other-owner'})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        stranger = Request(self.base + route + '/archive', data=b'{}', headers={'Content-Type': 'application/json', 'Origin': self.base})
        from urllib.request import urlopen
        with self.assertRaises(HTTPError) as caught:
            urlopen(stranger)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        self.assertEqual(len(self.get('/api/campaigns')['tasks']), 1)


if __name__ == '__main__':
    unittest.main()
