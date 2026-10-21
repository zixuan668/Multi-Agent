import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.agents.strategy.model_clients import CompatibleModelClient
from src.backend.campaigns import CampaignStore


def run_comparison(requirements, output, reuse_baseline=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    client = CompatibleModelClient.from_env()
    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}

    def record(values):
        for key in ("prompt_tokens", "completion_tokens"):
            usage[key] += values.get(key, 0)

    client.usage_observer = record
    baseline_prompt = "你是广告营销助手。根据用户的真实产品事实和目标，直接交付具体策略与可使用的广告。不要编造价格、优惠、入口、认证或效果。不输出思维链。只输出JSON，包含strategy（一段策略）、items（渠道文案数组，每项包含channel、headline、body、call_to_action、visual_brief）。正文优先80至180字；视觉方案不是已生成图片。"
    report = {"scope": "同一份需求、同一模型；只记录输出、耗时和用量，质量待盲评，不自动宣布赢家", "requirements": requirements, "model": client.model, "quality_winner": None}
    started = time.monotonic()
    usage["calls"] = 1
    if reuse_baseline:
        previous = json.loads(Path(reuse_baseline).read_text(encoding='utf-8'))
        if previous['requirements'] != requirements or previous['model'] != client.model:
            raise ValueError('只能复用相同需求和模型的基线')
        report['single_call'] = previous['single_call']
        report['baseline_reused_from'] = str(reuse_baseline)
    else:
        try:
            baseline = client.complete_json(baseline_prompt, json.dumps(requirements, ensure_ascii=False))
            report["single_call"] = {"output": baseline, "seconds": round(time.monotonic()-started, 2), "usage": usage}
        except Exception as error:
            report["single_call"] = {"error_type": type(error).__name__, "seconds": round(time.monotonic()-started, 2), "usage": usage}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    store = CampaignStore(output.with_suffix('.sqlite3'), max_model_calls=5, max_seconds=180)
    task = None
    started = time.monotonic()
    try:
        created = store.create(requirements, "benchmark", "comparison-"+str(time.time_ns()), interactive=True, choose_directions=False)
        deadline = time.monotonic() + 190
        while time.monotonic() < deadline:
            task = store.get(created["task_id"], "benchmark")
            if task["status"] not in ("pending", "running") and task["task_id"] not in store.active:
                break
            time.sleep(.2)
        if task["status"] in ("pending", "running"):
            task = store.cancel(task["task_id"], "benchmark")
        report["multi_agent"] = {"task_id": task["task_id"], "status": task["status"], "seconds": round(time.monotonic()-started, 2), "usage": task["usage"], "rounds": task["rounds"], "feedback": task["feedback"], "error": task["error"]}
    finally:
        store.close()
        store.executor.shutdown(wait=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description="显式付费对照：单次模型 vs 三角色首轮，不自动续轮或判定质量胜负")
    parser.add_argument('--requirements', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'artifacts'/'baseline-comparison.json')
    parser.add_argument('--live', action='store_true', help="明确允许调用已配置模型；单次基线1次，多角色最多5次")
    parser.add_argument('--reuse-baseline', type=Path, help="复用相同模型、相同需求的已有单次基线，避免重复收费")
    args = parser.parse_args()
    if not args.live:
        parser.error('需要 --live 才会执行收费模型调用；不提供此参数不会调用API')
    value = json.loads(args.requirements.read_text(encoding='utf-8'))
    report = run_comparison(value.get('requirements', value), args.output, args.reuse_baseline)
    print(json.dumps({"output": str(args.output), "single_call_seconds": report['single_call']['seconds'], "multi_agent_seconds": report['multi_agent']['seconds'], "multi_agent_status": report['multi_agent']['status'], "multi_agent_calls": report['multi_agent']['usage']['model_calls'], "quality_winner": None}, ensure_ascii=False))


if __name__ == '__main__':
    main()
