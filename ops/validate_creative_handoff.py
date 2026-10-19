"""策略侧首轮交接检查工具，不生成创意，不代替创意侧验收。"""
import argparse
import json
from pathlib import Path

from src.agents.strategy.downstream import validate_creative_request
from src.agents.strategy.errors import StrategyAgentError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8-sig"))
        accepted = validate_creative_request(payload)
    except (OSError, ValueError, StrategyAgentError) as exc:
        print(json.dumps({"accepted":False,"message":str(exc)},ensure_ascii=False))
        return 1
    print(json.dumps({"accepted":True,"task_id":accepted['task_id'],
                      "strategy_result_id":accepted['strategy']['result_id'],
                      "strategy_version":accepted['strategy']['version'],
                      "scope":"策略侧首轮契约通过，不代表创意生成或人工质量验收通过"},ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
