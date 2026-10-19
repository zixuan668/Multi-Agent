"""C-owned DeepSeek/compatible JSON client. Secrets never leave the server."""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import socket
from urllib import request, error
from urllib.parse import urlsplit

from .contracts import validate_config

ROOT = Path(__file__).resolve().parents[3]
PROMPT_VERSION='evaluation-v1.2'


class EvaluationError(ValueError):
    def __init__(self, code, message, retryable=False):
        self.code, self.retryable = code, retryable
        super().__init__(message)

    def public(self):
        return {'code': self.code, 'message': str(self), 'field':None, 'retryable': self.retryable}


def load_env(path):
    """Explicit file only; environment takes precedence. Never print values."""
    path = Path(path)
    if not path.is_file(): return
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            if key.strip().startswith(('EVALUATION_', 'DEEPSEEK_')):
                os.environ.setdefault(key.strip(), value.strip().strip('\"\''))


@dataclass(frozen=True)
class EvaluationConfig:
    base_url: str
    api_key: str = field(repr=False)
    model: str = 'deepseek-flash'
    timeout_seconds: int = 60
    max_attempts: int = 3
    pass_threshold: float = 80
    max_rounds: int = 3

    def __post_init__(self):
        url = urlsplit(self.base_url)
        if (url.scheme != 'https' or not url.netloc or not url.hostname or url.username or url.password
                or url.query or url.fragment or not self.api_key.strip() or not self.model.strip()
                or self.api_key=='replace-with-your-key' or url.hostname.endswith('.example')):
            raise EvaluationError('CONFIG_INVALID', 'C模型配置缺失或非法；检查服务端EVALUATION_*配置')
        self.snapshot()

    @classmethod
    def from_env(cls, env_file=None):
        load_env(env_file or ROOT / '.env.evaluation')
        try:
            return cls(base_url=os.getenv('EVALUATION_MODEL_BASE_URL', os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')),
                       api_key=os.getenv('EVALUATION_MODEL_API_KEY', os.getenv('DEEPSEEK_API_KEY', '')),
                       model=os.getenv('EVALUATION_MODEL_NAME', os.getenv('DEEPSEEK_MODEL', 'deepseek-flash')),
                       timeout_seconds=int(os.getenv('EVALUATION_TIMEOUT_SECONDS', '60')),
                       max_attempts=int(os.getenv('EVALUATION_MAX_ATTEMPTS', '3')),
                       pass_threshold=float(os.getenv('EVALUATION_PASS_THRESHOLD', '80')),
                       max_rounds=int(os.getenv('EVALUATION_MAX_ROUNDS', '3')))
        except (ValueError, TypeError):
            raise EvaluationError('CONFIG_INVALID', 'C配置非法，阈值、轮次、重试或超时不在允许范围') from None

    def snapshot(self, instructions=None):
        public = {'config_version': 'pending', 'pass_threshold': self.pass_threshold,
                  'max_rounds': self.max_rounds, 'timeout_seconds': self.timeout_seconds,
                  'max_attempts': self.max_attempts, 'scoring_rule_version': 'equal-weight-v2'}
        validate_config(public)
        signature = {**public, 'model': self.model, 'base_url': self.base_url,
                     'prompt_sha256': hashlib.sha256((prompt() if instructions is None else instructions).encode()).hexdigest()}
        public['config_version'] = 'evaluation-' + hashlib.sha256(json.dumps(signature, sort_keys=True).encode()).hexdigest()[:16]
        return public


def prompt():
    return (ROOT / 'prompts/evaluation/v1.2.txt').read_text(encoding='utf-8')


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


class EvaluationProvider:
    def __init__(self, config):
        self.config = config
        self.instructions=prompt()
        self._snapshot=config.snapshot(self.instructions)

    def snapshot(self):
        return dict(self._snapshot)

    def call(self, payload):
        body = {'model': self.config.model, 'messages': [
            {'role': 'system', 'content': self.instructions},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'response_format': {'type': 'json_object'}, 'temperature': 0,
            'max_tokens': 8192}
        url = self.config.base_url.rstrip('/')
        if not url.endswith('/chat/completions'):url += '/chat/completions'
        req = request.Request(url, data=json.dumps(body).encode(), headers={
            'Authorization': 'Bearer ' + self.config.api_key, 'Content-Type': 'application/json'})
        try:
            with request.build_opener(NoRedirect()).open(req, timeout=self.config.timeout_seconds) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000: raise ValueError()
                value = json.loads(raw)
            message = value['choices'][0]
            if message.get('finish_reason') not in (None, 'stop'): raise ValueError()
            output = json.loads(message['message']['content'])
            if not isinstance(output, dict): raise ValueError()
            return output
        except error.HTTPError as exc:
            status=exc.code
            exc.close()
            if status in (401, 403):
                raise EvaluationError('MODEL_AUTH_FAILED', 'C模型鉴权失败，请检查服务端密钥及模型权限') from None
            raise EvaluationError('MODEL_UNAVAILABLE', 'C模型服务暂不可用', status == 429 or status >= 500) from None
        except (TimeoutError, socket.timeout):
            raise EvaluationError('MODEL_TIMEOUT', 'C模型请求超时', True) from None
        except error.URLError as exc:
            code = 'MODEL_TIMEOUT' if isinstance(exc.reason, (TimeoutError, socket.timeout)) else 'MODEL_UNAVAILABLE'
            raise EvaluationError(code, 'C模型连接失败或超时', True) from None
        except (ValueError, KeyError, TypeError, IndexError, UnicodeError):
            raise EvaluationError('OUTPUT_INVALID', 'C模型未返回完整合法的评分JSON', True) from None
