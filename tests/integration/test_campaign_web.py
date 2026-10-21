from http.cookiejar import CookieJar
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from src.backend.campaign_web import create_server
from tests.integration.test_campaigns import requirements


class CampaignHttpTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.server = create_server(port=0, provider="offline", database=Path(self.directory.name) / "campaigns.sqlite3")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.client = build_opener(HTTPCookieProcessor(CookieJar()))
        self.get("/api/session")

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server.application.campaigns.executor.shutdown(wait=True)
        self.thread.join()
        self.directory.cleanup()

    def get(self, path):
        with self.client.open(self.base + path, timeout=5) as response:
            return json.load(response)

    def post(self, path, value, origin=None):
        headers = {"Content-Type": "application/json", "Origin": origin or self.base}
        request = Request(self.base + path, data=json.dumps(value).encode(), headers=headers)
        with self.client.open(request, timeout=5) as response:
            return json.load(response)

    def completed_task(self):
        task = self.post("/api/campaigns", {"requirements": requirements(), "submission_key": "http-submission"})
        for attempt in range(200):
            task = self.get("/api/campaigns/" + task["task_id"])
            if task["status"] not in ("pending", "running") and task['task_id'] not in self.server.application.campaigns.active:
                return task
            time.sleep(.01)
        self.fail("任务未结束")

    def test_unified_routes_and_honest_provider_health(self):
        for path in ("/", "/workspace", "/evaluation/", "/strategy", "/evaluation/demo/", "/campaign/app.js", "/campaign/presentation.js", "/campaign/navigation.js", "/campaign/style.css"):
            with self.client.open(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
        health = self.get("/api/health")
        self.assertEqual(health["agents"], ["strategy", "creative", "evaluation"])
        self.assertEqual(health["storage"], "sqlite")
        self.assertFalse(health["connection_verified"])
        self.assertFalse(health["image_generation"])

    def test_complete_report_has_consistent_selected_results(self):
        task = self.completed_task()
        report = self.get("/api/campaigns/" + task["task_id"] + "/report")
        selected = report["selected_results"]
        self.assertEqual(selected["creative"]["data"]["strategy_result_id"], selected["strategy"]["result_id"])
        self.assertEqual(selected["evaluation"]["data"]["creative_result_id"], selected["creative"]["result_id"])
        self.assertNotIn("owner_scope", json.dumps(report))
        self.assertNotIn("submission_key", json.dumps(report))
        with self.client.open(self.base + "/api/campaigns/" + task["task_id"] + "/report?download=1") as response:
            self.assertIn("attachment", response.headers["Content-Disposition"])
        approved = self.post("/api/campaigns/" + task["task_id"] + "/approve", {})
        self.assertEqual(approved["status"], "approved")

    def test_foreign_session_and_client_control_fields_are_rejected(self):
        task = self.completed_task()
        stranger = build_opener(HTTPCookieProcessor(CookieJar()))
        stranger.open(self.base + "/api/session").close()
        with self.assertRaises(HTTPError) as caught:
            stranger.open(self.base + "/api/campaigns/" + task["task_id"])
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        with self.assertRaises(HTTPError) as caught:
            self.post("/api/campaigns", {"requirements": requirements(), "submission_key": "bad-payload", "pass_threshold": 0})
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        with self.assertRaises(HTTPError) as caught:
            self.post("/api/campaigns", {"requirements": requirements(), "submission_key": "bad-origin"}, origin="https://foreign.example")
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()

    def test_unknown_api_is_not_a_static_directory_listing(self):
        for path in ("/api/campaigns/fake/unknown", "/api/unknown", "/.env"):
            with self.assertRaises(HTTPError) as caught:
                self.client.open(self.base + path)
            self.assertIn(caught.exception.code, (403, 404))
            caught.exception.close()

    def test_poster_endpoint_uses_owner_and_version_without_model_calls(self):
        task = self.completed_task()
        route = self.base + '/api/campaigns/' + task['task_id'] + '/poster.svg?round=1&item=0&theme=paper'
        with self.client.open(route) as response:
            self.assertEqual(response.headers.get_content_type(), 'image/svg+xml')
            self.assertIn(b'<svg', response.read())
        self.assertEqual(self.get('/api/campaigns/' + task['task_id'])['usage']['model_calls'], task['usage']['model_calls'])
        stranger = build_opener(HTTPCookieProcessor(CookieJar()))
        stranger.open(self.base + '/api/session').close()
        with self.assertRaises(HTTPError) as caught:
            stranger.open(route)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        with self.assertRaises(HTTPError) as caught:
            self.client.open(route.replace('round=1', 'round=999'))
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()

    def test_interactive_choice_is_a_real_user_checkpoint(self):
        task=self.post('/api/campaigns',{'requirements':requirements(),'submission_key':'interactive-http','interactive':True,'quality_mode':'polish'})
        for attempt in range(200):
            task=self.get('/api/campaigns/'+task['task_id'])
            if task['status']=='awaiting_direction':
                break
            time.sleep(.01)
        self.assertEqual(task['status'],'awaiting_direction')
        self.assertIsNone(task['rounds'][0]['creative'])
        selected=self.post('/api/campaigns/'+task['task_id']+'/choose-direction',{'option_id':'direction-1','base_round':1})
        self.assertEqual(selected['rounds'][0]['direction_choice']['option_id'],'direction-1')

    def test_revision_endpoint_preserves_owner_boundary_and_report_redaction(self):
        task=self.completed_task()
        payload={'message':'把标题写得更简短。','target_path':'creative.items[0].headline','base_round':1,'submission_key':'http-human-feedback'}
        response=self.post('/api/campaigns/'+task['task_id']+'/revise',payload)
        self.assertEqual(len(response['messages']),1)
        report=self.get('/api/campaigns/'+task['task_id']+'/report')
        self.assertNotIn('submission_key',json.dumps(report))
        stranger=build_opener(HTTPCookieProcessor(CookieJar()))
        stranger.open(self.base+'/api/session').close()
        request=Request(self.base+'/api/campaigns/'+task['task_id']+'/revise',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Origin':self.base})
        with self.assertRaises(HTTPError) as caught:
            stranger.open(request)
        self.assertEqual(caught.exception.code,403)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()
