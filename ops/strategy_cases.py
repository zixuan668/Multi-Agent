"""通过实际前端映射构造四步表单回归需求；不调用模型。"""
import json
from pathlib import Path
import subprocess

from src.agents.strategy.models import StrategyRequest


def guided_cases(source="guided_intakes.cjs"):
    root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        ["node", "tests/fixtures/strategy/" + source], cwd=root,
        capture_output=True, text=True, encoding="utf-8", check=True, timeout=10,
    )
    result = []
    for item in json.loads(completed.stdout):
        request = StrategyRequest.from_dict({
            "schema_version": "1.0", "task_id": f"guided-{item['case_id']}",
            "agent": "strategy", "round_no": 1, "attempt_count": 1,
            "requirements": item["requirements"], "strategy": None, "creative": None,
            "feedback": [], "previous_result": None, "config_version": "guided-fixture-v1",
        })
        result.append({"case_id": item["case_id"], "category": item["category"],
                       "comparison_group": item.get("comparison_group"), "request": request})
    return result
