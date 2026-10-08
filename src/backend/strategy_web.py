"""零依赖的营销策略智能体 HTTP 服务。"""

from __future__ import annotations

import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import secrets
import threading
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs
from uuid import uuid4

from src.agents.strategy.errors import ContractValidationError, StrategyAgentError, ConfigurationError
from src.agents.strategy.model_clients import CompatibleModelClient, RuleBasedModelClient
from src.agents.strategy.models import StrategyRequest, MarketingRequirements
from src.agents.strategy.service import StrategyAgent
from .tasks import TaskStore


ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "web"


def build_request_payload(raw: dict[str, Any]) -> dict[str, Any]:
    requirements = raw.get("requirements", raw)
    if "requirements" in raw and set(raw) != {"requirements"}:
        raise ContractValidationError("公开任务入口只接收 requirements；控制字段由服务端生成")
    if not isinstance(requirements, dict):
        raise ContractValidationError("requirements 必须是对象")
    return {
        "schema_version": "1.0",
        "task_id": f"task-{uuid4().hex}",
        "agent": "strategy",
        "round_no": 1,
        "attempt_count": 1,
        "requirements": MarketingRequirements.from_dict(requirements).to_dict(),
        "strategy": None,
        "creative": None,
        "feedback": [],
        "previous_result": None,
        "config_version": "web-v1",
    }


class StrategyApplication:
    def __init__(self, provider="compatible", model_client=None) -> None:
        if provider not in ("compatible", "offline"):
            raise ConfigurationError("provider 必须为 compatible 或显式 offline")
        self.provider_name = provider
        self.real_model_configured = provider == "compatible"
        model_client = model_client or (CompatibleModelClient.from_env() if provider == "compatible" else RuleBasedModelClient())
        self.agent = StrategyAgent(model_client)
        config = {"provider": provider, "model": getattr(model_client, "model", "offline-rule-based"), "timeout_seconds": getattr(model_client, "timeout_seconds", 60), "temperature": getattr(model_client, "temperature", None), "prompt_version": self.agent.prompt_builder.version, "prompt_sha256": self.agent.prompt_builder.sha256, "validation_version": "strategy-rules-v5-editorial", "semantic_review": hasattr(model_client, "review_strategy"), "strategy_editor": hasattr(model_client, "refine_strategy"), "max_rounds": 3, "pass_threshold": 80, "scoring_rule_version": "equal-weight-v1", "max_attempts": 3}
        config["config_version"] = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
        self.config_version = config["config_version"]
        self.tasks = TaskStore(self.agent, config)
        self._sessions = {}
        self._session_lock = threading.Lock()

    def session(self, token=None):
        with self._session_lock:
            if token not in self._sessions:
                token = secrets.token_urlsafe(32)
                self._sessions[token] = f"scope-{uuid4().hex}"
            return token, self._sessions[token]

    def scope(self, token):
        from src.agents.strategy.errors import AccessDeniedError
        with self._session_lock:
            if token not in self._sessions:
                raise AccessDeniedError("缺少有效演示会话，请先获取 /api/session")
            return self._sessions[token]

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "agent": "strategy",
            "schema_version": "1.0",
            "provider": self.provider_name,
            "real_model_configured": self.real_model_configured,
            "connection_verified": False,
            "semantic_review": self.real_model_configured,
            "storage": "process-memory",
        }

    def generate(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        try:
            request_payload = build_request_payload(payload)
            request_payload["config_version"] = self.config_version
            request_value = StrategyRequest.from_dict(request_payload)
        except ContractValidationError as exc:
            return HTTPStatus.BAD_REQUEST, {
                "status": "failed",
                "error": {
                    "code": "INPUT_INVALID",
                    "message": str(exc),
                    "field": exc.field,
                    "retryable": False,
                },
            }
        response = self.agent.generate(request_value).to_dict()
        status = HTTPStatus.OK if response["status"] == "succeeded" else HTTPStatus.BAD_GATEWAY
        return status, response


def make_handler(application: StrategyApplication):
    class StrategyRequestHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

        def end_headers(self):
            if not urlparse(self.path).path.startswith("/api/"):
                # 开发阶段避免旧CSS/JS与新页面混用；API已有独立no-store。
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
            super().end_headers()

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/health":
                self._json(HTTPStatus.OK, application.health())
                return
            if path == "/api/session":
                token, _ = application.session(self._token())
                self._json(HTTPStatus.OK, {"status": "ok"}, cookie=token)
                return
            if path.startswith("/api/tasks/"):
                try:
                    scope = application.scope(self._token())
                    parts = path.strip("/").split("/")
                    if len(parts) == 3:
                        value = application.tasks.get(parts[2], scope)
                    elif len(parts) == 4 and parts[3] == "creative-request":
                        value = application.tasks.creative_request(parts[2], scope)
                    else:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                        return
                    download = parse_qs(urlparse(self.path).query).get("download") == ["1"]
                    kind = "creative-request" if len(parts) == 4 else "strategy-task"
                    self._json(HTTPStatus.OK, value, filename=f"{parts[2]}-{kind}.json" if download else None)
                except StrategyAgentError as exc:
                    self._error(exc)
                return
            if path == "/":
                self.path = "/index.html"
            elif path in ("/workspace", "/workspace/"):
                self.path = "/workspace.html"
            super().do_GET()

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in ("/api/strategy", "/api/tasks"):
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("请求必须使用 application/json")
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    raise ValueError("请求正文为空或过大")
                raw = self.rfile.read(length).decode("utf-8")
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    raise ValueError("请求顶层必须是对象")
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "status": "failed",
                        "error": {
                            "code": "INPUT_INVALID",
                            "message": str(exc),
                            "field": None,
                            "retryable": False,
                        },
                    },
                )
                return
            try:
                scope = application.scope(self._token())
                normalized = build_request_payload(payload)["requirements"]
                if path == "/api/tasks":
                    self._json(HTTPStatus.ACCEPTED, application.tasks.create(normalized, scope))
                else:
                    # 旧同步入口仅用于迁移；网页使用异步任务入口。
                    status, response = application.generate({"requirements": normalized})
                    self._json(status, response)
            except StrategyAgentError as exc:
                self._error(exc)

        def _token(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get("Cookie", ""))
                return cookie["zhice_session"].value if "zhice_session" in cookie else None
            except Exception:
                return None

        def _error(self, exc):
            status = HTTPStatus.FORBIDDEN if exc.code == "ACCESS_DENIED" else HTTPStatus.BAD_REQUEST
            if exc.code == "MODEL_UNAVAILABLE":
                status = HTTPStatus.SERVICE_UNAVAILABLE
            self._json(status, {"status": "failed", "error": {"code": exc.code, "message": str(exc), "field": getattr(exc, "field", None), "retryable": exc.retryable}})

        def log_message(self, format: str, *args: Any) -> None:
            # 不记录请求正文、密钥或用户输入，只保留 HTTP 摘要。
            print(f"[http] {self.client_address[0]} {format % args}")

        def _json(self, status: int, value: dict[str, Any], cookie=None, filename=None) -> None:
            body = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            if cookie:
                self.send_header("Set-Cookie", f"zhice_session={cookie}; HttpOnly; SameSite=Strict; Path=/")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'")
            self.end_headers()
            self.wfile.write(body)

    return StrategyRequestHandler


def create_server(host: str = "127.0.0.1", port: int = 8000, *, provider="compatible", model_client=None) -> ThreadingHTTPServer:
    application = StrategyApplication(provider, model_client)
    class Server(ThreadingHTTPServer):
        def server_close(self):
            application.tasks.close()
            super().server_close()
    return Server((host, port), make_handler(application))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="智策营销策略智能体网页应用")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--provider", choices=("compatible", "offline"), default="compatible")
    args = parser.parse_args(argv)
    try:
        server = create_server(args.host, args.port, provider=args.provider)
    except ConfigurationError as exc:
        print(f"{exc.code}: {exc}")
        return 2
    mode = "真实模型配置模式（调用成功前不表示连接已验证）" if args.provider == "compatible" else "显式离线演示（不计入真实模型验收）"
    print(f"智策营销策略智能体已启动： http://{args.host}:{server.server_port}")
    print(f"当前模式：{mode}")
    print("按 Ctrl+C 停止服务")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止")
    finally:
        server.server_close()
    return 0
