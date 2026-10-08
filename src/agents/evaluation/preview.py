"""Isolated offline preview. Existing app.py and strategy routes are untouched."""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .contracts import ContractError
from .examples import SCENARIOS, make_source, products
from .service import evaluate_bundle

WEB_ROOT = Path(__file__).resolve().parents[3] / "web/evaluation"
ASSETS = {"index.html", "style.css", "app.js", "api.js", "particles.js", "favicon.svg"}


class EvaluationPreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        super().end_headers()

    def json_response(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/evaluation/scenarios":
            self.json_response({"products": [{"id": i, "name": r["requirements"]["product_name"]} for i, r in enumerate(products())], "scenarios": SCENARIOS, "mode": "offline"})
        elif parsed.path == "/api/evaluation/sample":
            query = parse_qs(parsed.query)
            try:
                self.json_response(make_source(int(query.get("product", ["0"])[0]), query.get("scenario", ["improve"])[0]))
            except (ValueError, TypeError, IndexError) as exc:
                self.json_response({"error": {"code": "INPUT_INVALID", "message": str(exc), "field": "sample", "retryable": False}}, 400)
        else:
            name = parsed.path.removeprefix("/evaluation/").lstrip("/")
            if parsed.path in ("/", "/evaluation", "/evaluation/"):
                name = "index.html"
            if name not in ASSETS:
                self.send_error(404)
                return
            self.path = "/" + name
            super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/evaluation/replay":
            self.send_error(404)
            return
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + self.headers.get("Host", ""):
            self.json_response({"error": {"code": "ACCESS_DENIED", "message": "仅接受同源离线重放请求", "field": None, "retryable": False}}, 403)
            return
        try:
            if self.headers.get_content_type() != "application/json":
                raise ContractError("Content-Type", "须为application/json")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2_000_000:
                raise ContractError("body", "请求须为非空且小于2MB的JSON")
            raw = json.loads(self.rfile.read(length).decode("utf-8"), parse_constant=lambda value: (_ for _ in ()).throw(ValueError("JSON不允许非有限数值")))
            self.json_response({"data": evaluate_bundle(raw)})
        except (ContractError, ValueError, TypeError, KeyError) as exc:
            self.json_response({"error": {"code": "INPUT_INVALID", "message": str(exc), "field": getattr(exc, "field", None), "retryable": False}}, 400)
        except Exception:
            self.json_response({"error": {"code": "INTERNAL_ERROR", "message": "离线重放失败，请检查服务或输入记录", "field": None, "retryable": False}}, 500)


def main():
    parser = argparse.ArgumentParser(description="智策效果评估独立预览，不调用模型")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    print(f"Evaluation offline workbench: http://127.0.0.1:{args.port}/evaluation/", flush=True)
    ThreadingHTTPServer(("127.0.0.1", args.port), EvaluationPreviewHandler).serve_forever()


if __name__ == "__main__":
    main()
