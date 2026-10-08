"""Team CLI: validate an evaluation request or replay bundle without any model."""
import argparse
import json
from pathlib import Path
from .contracts import ContractError, validate_handoff
from .service import evaluate_bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8-sig"))
        if "rounds" in raw:
            value = evaluate_bundle(raw)
            print(json.dumps({"valid": True, "mode": "offline", "rounds": len(value["records"]), "assessment_status": value["final"]["assessment_status"]}, ensure_ascii=False))
        else:
            request = validate_handoff(raw)
            print(json.dumps({"valid": True, "task_id": request["task_id"], "strategy_result_id": request["strategy"]["result_id"], "creative_result_id": request["creative"]["result_id"]}, ensure_ascii=False))
        return 0
    except (ContractError, ValueError, KeyError) as exc:
        print(json.dumps({"valid": False, "error": "INPUT_INVALID", "message": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
