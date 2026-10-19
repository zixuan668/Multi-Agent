"""Reuse A's HTTP client through its public generate_json interface, independently configured."""
import os
import json
from types import SimpleNamespace
from .errors import CreativeError
from src.agents.strategy.model_clients import CompatibleModelClient
from src.agents.strategy.errors import StrategyAgentError

FIELDS = ("BASE_URL", "API_KEY", "NAME", "TIMEOUT_SECONDS", "TEMPERATURE")

def load_env(path):
    if not path.is_file(): return
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(),1):
        line=line.strip()
        if not line or line.startswith("#"): continue
        k, sep, value=line.partition("=")
        if not sep or k.strip() not in {"CREATIVE_MODEL_"+s for s in FIELDS}:
            raise CreativeError(f"创意配置第 {number} 行字段不合法", "CONFIG_INVALID")
        os.environ.setdefault(k.strip(),value.strip().strip("\"'"))

class Provider:
    def __init__(self, client): self.client=client

    @classmethod
    def from_env(cls, root):
        load_env(root/".env.creative")
        try:
            return cls(CompatibleModelClient(base_url=os.environ.get("CREATIVE_MODEL_BASE_URL",""),
                       api_key=os.environ.get("CREATIVE_MODEL_API_KEY",""), model=os.environ.get("CREATIVE_MODEL_NAME",""),
                       timeout_seconds=float(os.environ.get("CREATIVE_MODEL_TIMEOUT_SECONDS","120")),
                       temperature=float(os.environ.get("CREATIVE_MODEL_TEMPERATURE","0.5"))))
        except (ValueError, StrategyAgentError):
            raise CreativeError("B 模型配置缺失或不合法，请检查服务端 CREATIVE_MODEL_* 环境变量", "CONFIG_INVALID") from None

    def call(self, system, data):
        try:
            raw=self.client.generate_json(SimpleNamespace(system=system,user=json.dumps(data,ensure_ascii=False)))
            value=json.loads(raw)
            if not isinstance(value,dict): raise ValueError()
            return value
        except StrategyAgentError as e:
            raise CreativeError(str(e),e.code) from None
        except (ValueError,TypeError):
            raise CreativeError("模型未返回合法 JSON 对象，未保存也未交付", "OUTPUT_INVALID") from None
