from http.server import ThreadingHTTPServer
import json
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from src.agents.evaluation.preview import EvaluationPreviewHandler
from src.agents.evaluation.examples import make_source


class PreviewHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), EvaluationPreviewHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_isolated_assets_and_namespace(self):
        for path in ("/evaluation/", "/evaluation/app.js", "/evaluation/style.css", "/evaluation/particles.js"):
            with urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertTrue(response.read())
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/.env")
        self.assertEqual(error.exception.code, 404)

    def test_replay_rejects_invalid_input_and_cross_origin(self):
        body = json.dumps(make_source()).encode()
        request = Request(self.url + "/api/evaluation/replay", data=body, headers={"Content-Type": "application/json"})
        with urlopen(request) as response:
            value = json.load(response)["data"]
            self.assertEqual(value["final"]["assessment_status"], "passed")
        for headers, expected in (({"Content-Type": "application/json", "Origin": "https://example.org"}, 403), ({"Content-Type": "text/plain"}, 400)):
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(self.url + "/api/evaluation/replay", data=body, headers=headers))
            self.assertEqual(error.exception.code, expected)


if __name__ == "__main__":
    unittest.main()
