"""Validate the actual local contracts, with no network schema resolution."""
import json
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from .errors import CreativeError

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "packages/contracts"
SCHEMAS = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in CONTRACTS.glob("*.json")}
SCHEMAS.update({p.name: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT/"src/agents/creative/schemas").glob("*.json")})
REGISTRY = Registry().with_resources((s["$id"], Resource.from_contents(s)) for s in SCHEMAS.values())

def validate(value, filename, *, code="INPUT_INVALID"):
    errors = sorted(Draft202012Validator(SCHEMAS[filename], registry=REGISTRY,
                    format_checker=FormatChecker()).iter_errors(value), key=lambda e: str(list(e.path)))
    if errors:
        # Validator messages may contain rejected content. Return paths and rule names only.
        issues = [{"field": ".".join(map(str,e.absolute_path)) or "request",
                   "message": "不符合契约规则：" + str(e.validator)} for e in errors[:20]]
        raise CreativeError("结构校验未通过，请检查标出的字段", code, issues)
