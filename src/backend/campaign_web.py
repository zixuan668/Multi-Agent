import argparse
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from src.agents.strategy.errors import ConfigurationError, ContractValidationError, StrategyAgentError
from src.agents.strategy.model_clients import CompatibleModelClient, RuleBasedModelClient
from .campaigns import CampaignStore
from .collaboration import PEOPLE
from .posters import render_poster
from .image_generation import CampaignImages, VolcengineImageClient, load_image_settings
from .history import CampaignHistory
from .strategy_web import StrategyApplication, make_handler


ROOT = Path(__file__).resolve().parents[2]


class CampaignApplication(StrategyApplication):
    def __init__(self, *, provider="compatible", database=None, client_factory=None, image_client_factory=None):
        factory = client_factory or (CompatibleModelClient.from_env if provider == "compatible" else RuleBasedModelClient)
        super().__init__(provider=provider, model_client=factory())
        self.campaigns = CampaignStore(database or ROOT / "artifacts" / "campaigns.sqlite3", provider=provider, client_factory=factory)
        image_client = image_client_factory() if image_client_factory else VolcengineImageClient.from_settings(load_image_settings()) if provider == 'compatible' else None
        self.images = CampaignImages(self.campaigns, client=image_client)
        self.history = CampaignHistory(self.campaigns, self.images)

    def session(self, token=None):
        return self.campaigns.repository.session(token)

    def scope(self, token):
        return self.campaigns.repository.scope(token)

    def health(self):
        return {"status": "ok", "agent": "campaign", "schema_version": "1.1", "provider": self.provider_name, "real_model_configured": self.real_model_configured, "connection_verified": False, "storage": "sqlite", "agents": ["strategy", "creative", "evaluation"], "image_generation": self.images.client is not None, "image_model": self.images.client.model if self.images.client else None, "poster_export": True, "team": PEOPLE, "public_streaming": self.campaigns.config["streaming_enabled"], "human_revisions": True, "config_version": self.campaigns.config_version}

    def close(self):
        self.images.close()
        self.campaigns.close()
        self.tasks.close()


def campaign_handler(application):
    base = make_handler(application)

    class Handler(base):
        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/api/campaigns" or path.startswith("/api/campaigns/"):
                try:
                    owner = application.scope(self._token())
                    parts = path.strip("/").split("/")
                    filename = None
                    if len(parts) == 2:
                        result = {"tasks": application.campaigns.list(owner, deleted=parse_qs(parsed.query).get('deleted') == ['1'])}
                    elif len(parts) == 3:
                        result = application.campaigns.get(parts[2], owner)
                    elif len(parts) == 4 and parts[3] == 'image-plan':
                        query = parse_qs(parsed.query)
                        try:
                            round_no = int(query.get('round', ['1'])[0])
                            index = int(query.get('item', ['0'])[0])
                        except (TypeError, ValueError):
                            raise ContractValidationError('海报版本或渠道参数无效') from None
                        result = application.images.preview(parts[2], owner, round_no, index)
                    elif len(parts) == 5 and parts[3] == 'images':
                        data, job = application.images.read(parts[2], owner, parts[4])
                        self.send_response(HTTPStatus.OK)
                        self.send_header('Content-Type', job['mime_type'])
                        self.send_header('Content-Length', str(len(data)))
                        self.send_header('Cache-Control', 'private, no-store')
                        self.send_header('X-Content-Type-Options', 'nosniff')
                        self.send_header('Content-Security-Policy', "default-src 'none'; sandbox")
                        if parse_qs(parsed.query).get('download') == ['1']:
                            extension = 'png' if job['mime_type'] == 'image/png' else 'jpg'
                            self.send_header('Content-Disposition', f'attachment; filename="{job["image_id"]}.{extension}"')
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    elif len(parts) == 4 and parts[3] == "poster.svg":
                        task = application.campaigns.get(parts[2], owner)
                        query = parse_qs(parsed.query)
                        try:
                            round_no = int(query.get("round", [task["selected_round"] or len(task["rounds"])])[0])
                            item_index = int(query.get("item", ["0"])[0])
                        except (ValueError, TypeError):
                            raise ContractValidationError("海报版本和渠道参数无效") from None
                        data = render_poster(task, round_no, item_index, query.get("theme", ["ink"])[0])
                        self.send_response(HTTPStatus.OK)
                        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
                        self.send_header("Content-Length", str(len(data)))
                        self.send_header("Cache-Control", "private, no-store")
                        self.send_header("X-Content-Type-Options", "nosniff")
                        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; sandbox")
                        if query.get("download") == ["1"]:
                            self.send_header("Content-Disposition", f'attachment; filename="{task["task_id"]}-r{round_no}-{item_index}.svg"')
                        self.end_headers()
                        self.wfile.write(data)
                        return
                    elif len(parts) == 4 and parts[3] == "report":
                        task = application.campaigns.get(parts[2], owner)
                        selected = next((row for row in task["rounds"] if row["round_no"] == task["selected_round"]), None)
                        result = {"schema_version": "1.1", "task_id": task["task_id"], "requirements": task["requirements"], "status": task["status"], "assessment_status": task["assessment_status"], "termination_reason": task["termination_reason"], "config_snapshot": task["config_snapshot"], "quality_mode": task.get("quality_mode", "balanced"), "messages": [{key:value for key,value in item.items() if key != "submission_key"} for item in task.get("messages", [])], "selected_round": task["selected_round"], "selected_results": selected, "parent_task_id": task.get("parent_task_id"), "initial_direction": task.get("initial_direction"), "rounds": task["rounds"], "feedback": task["feedback"], "events": task["events"], "usage": task["usage"], "image_jobs": task.get("image_jobs", []), "scope": "投放前文字草稿评审；图片单独生成、待人工核对；未自动投放"}
                        if parse_qs(parsed.query).get("download") == ["1"]:
                            filename = task["task_id"] + "-report.json"
                    else:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                        return
                    self._json(HTTPStatus.OK, result, filename=filename)
                except StrategyAgentError as error:
                    self._error(error)
                return
            if path in ("/workspace", "/workspace/", "/evaluation", "/evaluation/"):
                self.path = "/campaign/index.html"
                SimpleHTTPRequestHandler.do_GET(self)
                return
            if path in ("/strategy", "/strategy/"):
                self.path = "/workspace.html"
                SimpleHTTPRequestHandler.do_GET(self)
                return
            if path in ("/evaluation/demo", "/evaluation/demo/"):
                self.path = "/evaluation/index.html"
                SimpleHTTPRequestHandler.do_GET(self)
                return
            if path.startswith("/api/evaluation/"):
                self._replay_get(parsed)
                return
            if path.startswith("/api/") and path not in ("/api/health", "/api/session") and not path.startswith("/api/tasks/"):
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            super().do_GET()

        def _replay_get(self, parsed):
            from src.agents.evaluation.examples import SCENARIOS, make_source, products
            try:
                if parsed.path == "/api/evaluation/scenarios":
                    self._json(HTTPStatus.OK, {"products": [{"id": index, "name": product["requirements"]["product_name"]} for index, product in enumerate(products())], "scenarios": SCENARIOS, "mode": "offline"})
                elif parsed.path == "/api/evaluation/sample":
                    query = parse_qs(parsed.query)
                    self._json(HTTPStatus.OK, make_source(int(query.get("product", ["0"])[0]), query.get("scenario", ["improve"])[0]))
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            except (ValueError, TypeError, IndexError):
                self._error(ContractValidationError("样例参数无效"))

        def _payload(self):
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                raise ContractValidationError("拒绝异源请求")
            if self.headers.get_content_type() != "application/json":
                raise ContractValidationError("请求必须使用application/json")
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    raise ValueError()
                payload = json.loads(self.rfile.read(size))
            except (ValueError, UnicodeDecodeError):
                raise ContractValidationError("请求须为不超过1MB的有效JSON") from None
            if not isinstance(payload, dict):
                raise ContractValidationError("请求须为JSON对象")
            return payload

        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/api/campaigns" or path.startswith("/api/campaigns/"):
                try:
                    owner = application.scope(self._token())
                    payload = self._payload()
                    parts = path.strip("/").split("/")
                    if len(parts) == 2:
                        if not {"requirements", "submission_key"} <= set(payload) or set(payload) - {"requirements", "submission_key", "quality_mode", "interactive", "choose_directions"}:
                            raise ContractValidationError("仅接收需求和提交标识；评分、配置和控制字段由后台生成")
                        task = application.campaigns.create(payload["requirements"], owner, payload["submission_key"], quality_mode=payload.get("quality_mode", "balanced"), interactive=payload.get("interactive",False), choose_directions=payload.get("choose_directions",True))
                    elif parts == ['api', 'campaigns', 'history', 'clear']:
                        if payload:
                            raise ContractValidationError('清空历史不接受附加字段')
                        task = application.history.clear(owner)
                    elif len(parts) == 4 and parts[3] in ('archive', 'restore'):
                        if payload:
                            raise ContractValidationError('历史操作不接受附加字段')
                        task = getattr(application.history, parts[3])(parts[2], owner)
                    elif len(parts) == 4 and parts[3] == "choose-direction":
                        task = application.campaigns.choose_direction(parts[2], owner, payload)
                    elif len(parts) == 4 and parts[3] == 'images':
                        task = application.images.create(parts[2], owner, payload)
                    elif len(parts) == 4 and parts[3] == "clarify":
                        task = application.campaigns.clarify(parts[2], owner, payload)
                    elif len(parts) == 4 and parts[3] == "continue-review":
                        if payload:
                            raise ContractValidationError("继续评审不接受控制字段")
                        task = application.campaigns.continue_review(parts[2],owner)
                    elif len(parts) == 4 and parts[3] == "revise":
                        task = application.campaigns.revise(parts[2], owner, payload)
                    elif len(parts) == 4 and parts[3] in ("cancel", "resume", "approve"):
                        if payload:
                            raise ContractValidationError("任务动作不接受附加控制字段")
                        task = getattr(application.campaigns, parts[3])(parts[2], owner)
                    else:
                        self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                        return
                    self._json(HTTPStatus.ACCEPTED if task["status"] == "pending" else HTTPStatus.OK, task)
                except StrategyAgentError as error:
                    self._error(error)
                return
            if path == "/api/evaluation/replay":
                from src.agents.evaluation.service import evaluate_bundle
                try:
                    payload = self._payload()
                    self._json(HTTPStatus.OK, {"data": evaluate_bundle(payload)})
                except (ValueError, KeyError, TypeError, StrategyAgentError):
                    self._error(ContractValidationError("离线重放包无效；此入口只用于样例联调"))
                return
            super().do_POST()

    return Handler


def create_server(host="127.0.0.1", port=8000, *, provider="compatible", database=None, client_factory=None, image_client_factory=None):
    application = CampaignApplication(provider=provider, database=database, client_factory=client_factory, image_client_factory=image_client_factory)

    class Server(ThreadingHTTPServer):
        def server_close(self):
            application.close()
            super().server_close()

    server = Server((host, port), campaign_handler(application))
    server.application = application
    return server


def main(argv=None):
    parser = argparse.ArgumentParser(description="智策营销三智能体协作工作台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--provider", choices=("compatible", "offline"), default="compatible")
    parser.add_argument("--database", type=Path, default=ROOT / "artifacts" / "campaigns.sqlite3")
    args = parser.parse_args(argv)
    try:
        server = create_server(args.host, args.port, provider=args.provider, database=args.database)
    except ConfigurationError as error:
        print(str(error))
        return 2
    print(f"智策多智能体工作台：http://{args.host}:{server.server_port}/workspace", flush=True)
    print("真实模型模式：不自动回退离线。" if args.provider == "compatible" else "显式离线联调：不代表真实模型创意或评审质量。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
