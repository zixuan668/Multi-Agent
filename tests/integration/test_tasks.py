from copy import deepcopy
import json
import threading
import time
import unittest
from urllib import request, error
from http.cookiejar import CookieJar

from src.backend.strategy_web import create_server
from tests.unit.test_models import valid_payload
from tests.unit.test_service import valid_data


class AsyncTasksTests(unittest.TestCase):
    def setUp(self):
        self.release = threading.Event()
        self.calls = 0
        parent = self
        class Client:
            def generate_json(self, prompt):
                parent.calls += 1
                parent.release.wait(2)
                return json.dumps(valid_data())
        self.server = create_server("127.0.0.1", 0, provider="offline", model_client=Client())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        self.opener.open(self.base + "/api/session").close()

    def tearDown(self):
        self.release.set()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def post(self, payload):
        req = request.Request(self.base + "/api/tasks", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with self.opener.open(req, timeout=2) as response:
            return response.status, json.load(response)

    def get(self, task_id, suffix=""):
        with self.opener.open(self.base + f"/api/tasks/{task_id}{suffix}", timeout=2) as response:
            return json.load(response)

    def await_completed(self, task_id):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            task = self.get(task_id)
            if task["status"] in ("completed", "failed"):
                return task
            time.sleep(.01)
        self.fail("任务未在测试期限内完成")

    def test_pending_without_waiting_then_completed_and_downstream_ready(self):
        started = time.monotonic()
        status, receipt = self.post(valid_payload()["requirements"])
        self.assertEqual(status, 202)
        self.assertEqual(receipt["status"], "pending")
        self.assertLess(time.monotonic() - started, .5)
        self.assertIn(self.get(receipt["task_id"])["status"], ("pending", "running"))
        self.release.set()
        task = self.await_completed(receipt["task_id"])
        self.assertEqual(task["status"], "completed")
        self.assertEqual(task["assessment_status"], "not_evaluated")
        self.assertEqual(task["iteration_count"], 0)
        self.assertEqual(task["termination_reason"], "strategy_completed")
        self.assertIsNone(task["selected_evaluation_id"])
        self.assertEqual(len(task["results"]), 1)
        creative = self.get(receipt["task_id"], "/creative-request")
        self.assertEqual(creative["strategy"], task["result"])
        with self.opener.open(self.base + f"/api/tasks/{receipt['task_id']}/creative-request?download=1") as response:
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertEqual(json.load(response), creative)

    def test_invalid_input_does_not_create_or_call(self):
        with self.assertRaises(error.HTTPError) as caught:
            self.post({"product_name": ""})
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)["error"]["field"], "requirements.product_name")
        caught.exception.close()
        self.assertEqual(self.calls, 0)

    def test_client_cannot_supply_control_fields(self):
        with self.assertRaises(error.HTTPError) as caught:
            self.post({"requirements": valid_payload()["requirements"], "task_id": "forged"})
        caught.exception.close()
        self.assertEqual(self.calls, 0)

    def test_other_session_cannot_read_task(self):
        _, receipt = self.post(valid_payload()["requirements"])
        other = request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        other.open(self.base + "/api/session").close()
        with self.assertRaises(error.HTTPError) as caught:
            other.open(self.base + f"/api/tasks/{receipt['task_id']}")
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()

    def test_five_tasks_do_not_overwrite_each_other(self):
        ids = [self.post(valid_payload()["requirements"])[1]["task_id"] for _ in range(5)]
        self.release.set()
        tasks = [self.await_completed(task_id) for task_id in ids]
        self.assertEqual(len(set(ids)), 5)
        self.assertTrue(all(task["status"] == "completed" for task in tasks))
        self.assertEqual(len({task["result"]["result_id"] for task in tasks}), 5)
        self.assertTrue(all(task["result"]["version"] == 1 for task in tasks))


if __name__ == "__main__":
    unittest.main()
