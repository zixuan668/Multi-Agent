"""固定50例真实模型测试入口；显式离线模式只产生联调证据。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import hashlib
from dataclasses import replace

from src.agents.strategy.model_clients import RuleBasedModelClient, CompatibleModelClient
from src.agents.strategy.errors import StrategyAgentError
from src.agents.strategy.downstream import build_creative_request
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.service import StrategyAgent, RetryPolicy
from src.agents.strategy.validation import VALIDATION_VERSION
from src.agents.strategy.configuration import implementation_fingerprint
from ops.strategy_cases import guided_cases


CATEGORIES = [
    ("AI学习产品", "提供错题整理和学习计划功能。", "帮助学生了解学习工具", "学生"),
    ("奶茶", "提供热饮和冷饮，可选择无糖或半糖。", "提升门店周边认知", "附近大学生"),
    ("智能手表", "支持消息提醒和运动记录。", "介绍产品特点", "通勤人群"),
    ("化妆品", "提供自然色号和哑光妆效选择。", "介绍使用场景", "关注妆容的消费者"),
    ("旅游产品", "提供两日行程规划和景点介绍服务。", "吸引周末出行游客", "周末出行游客"),
]

# 人工构造的固定需求，不代表真实商品资料；每类10个输入有事实与约束差异。
FEATURES = [
    ["支持按课程归类错题", "可设置每日学习提醒", "支持导出学习计划", "提供章节练习入口", "可查看历史错题", "支持手动标记掌握情况", "支持按知识点检索", "提供周计划视图", "支持收藏题目", "可调整计划顺序"],
    ["可选择小杯或大杯", "提供到店自取", "菜单标明原料", "可选择少冰", "提供独立包装", "支持现场点单", "可选择常温", "提供纸质菜单", "可选择不加配料", "可选择燕麦奶基底"],
    ["提供两种表带尺寸", "支持闹钟设置", "可查看历史运动记录", "提供触控界面", "支持调节屏幕亮度", "可设置提醒时间", "表带可拆换", "支持计时器", "提供充电底座", "可选择不同表盘"],
    ["提供试色卡", "包装标注成分", "提供两种包装容量", "附使用说明", "可选择不同自然色号", "提供便携包装", "附赠取用工具", "包装标注保质期", "提供密封包装", "可通过柜台查看样品"],
    ["行程包含古城步行路线", "提供电子行程单", "行程包含博物馆参观安排", "提供集合地点说明", "行程包含自由活动时段", "可查看路线介绍", "提供景点开放时间说明", "行程包含公共交通路线", "提供出行物品清单", "行程包含休息时段"],
]


def build_request(index: int, category: tuple[str, str, str, str]) -> StrategyRequest:
    name, description, goal, audience = category
    variant = index % 10
    category_index = CATEGORIES.index(category)
    special = ["不虚构优惠、认证、销量或效果承诺", "禁止使用抖音；不得付费推广", "必须使用自有内容渠道", "禁止出现“全网最低价”", "不编造市场价格", "必须使用校园社群", "必须使用门店自有社群", "禁止使用抖音和快手", "必须保留产品事实，不保证营销效果", "不虚构优惠、认证、销量或效果承诺"][variant]
    return StrategyRequest.from_dict(
        {
            "schema_version": "1.0",
            "task_id": f"evidence-{index + 1:02d}",
            "agent": "strategy",
            "round_no": 1,
            "attempt_count": 1,
            "requirements": {
                "product_name": f"{name}样例{index % 10 + 1}",
                "product_description": description + FEATURES[category_index][variant] + "。",
                "marketing_goal": goal,
                "target_audience": audience if index % 2 == 0 else None,
                "budget": {"amount": 0 if variant == 1 else 5000 + index * 100, "currency": "CNY"} if variant in (0, 1, 3, 6, 9) else None,
                "campaign_period": {"start_date": "2026-10-01", "end_date": "2026-10-07"} if variant == 7 else ({"duration_days": 7 + variant} if variant % 2 == 0 else None),
                "special_requirements": special,
                "budget_raw": None,
            },
            "strategy": None,
            "creative": None,
            "feedback": [],
            "previous_result": None,
            "config_version": "acceptance-v2",
        }
    )


def select_cases(suite="fixed", limit=None, case_ids=None):
    if suite in ("guided", "examples"):
        cases = guided_cases("workspace_examples.cjs" if suite == "examples" else "guided_intakes.cjs")
    else:
        cases = [{"case_id": f"ACCEPT-{index+1:02d}", "category": CATEGORIES[index//10][0],
                  "request": build_request(index, CATEGORIES[index//10])} for index in range(50)]
        if limit is not None:
            # 小样本交错选择五类产品，不只测试前几个学习产品。
            cases = [cases[category * 10 + variant] for variant in range(10) for category in range(5)]
    if case_ids:
        wanted = case_ids.split(",")
        lookup = {item["case_id"]: item for item in cases}
        if len(set(wanted)) != len(wanted) or any(key not in lookup for key in wanted):
            raise ValueError("case-ids 含未知或重复样例")
        cases = [lookup[key] for key in wanted]
    return cases if limit is None else cases[:limit]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="运行固定50例，真实模型模式会调用模型服务并可能产生费用")
    parser.add_argument("--provider", choices=("compatible", "offline"), default="compatible")
    parser.add_argument("--suite", choices=("fixed", "guided", "examples"), default="fixed", help="fixed=正式50例；guided=表单边界；examples=页面实际5类示例")
    parser.add_argument("--limit", type=int, help="只执行少量样例，不计为正式50例验收")
    parser.add_argument("--case-ids", help="以逗号分隔的样例ID，例如 milk-owned,milk-unknown,milk-zero")
    parser.add_argument("--max-attempts", type=int, choices=(1,2,3), default=3, help="小样本成本上限；正式验收必须为3")
    parser.add_argument("--confirm-formal", action="store_true", help="团队已确认正式50例真实调用及费用")
    parser.add_argument(
        "--output",
        default=None,
        help="证据输出路径",
    )
    args = parser.parse_args(argv)
    if args.limit is not None and not 1 <= args.limit <= 10:
        parser.error("小样本 limit 必须为1至10；正式50例使用默认 fixed 套件并确认费用")
    try:
        cases = select_cases(args.suite, args.limit, args.case_ids)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.case_ids and len(cases) > 10:
        parser.error("小样本最多选择10例，不能绕过正式验收确认")
    formal = args.suite == "fixed" and args.limit is None and args.case_ids is None
    if formal and args.provider == "compatible" and not args.confirm_formal:
        parser.error("正式50例会产生费用，请团队确认后添加 --confirm-formal；先用 --limit 5 小样本检查")
    if formal and args.max_attempts != 3:
        parser.error("正式验收必须使用3次最大尝试")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = Path(args.output or f"artifacts/acceptance/strategy-{args.provider}-{args.suite}-{len(cases)}-{stamp}.json")
    if output.exists():
        parser.error("输出文件已存在，请指定新文件名，不覆盖原有证据")
    try:
        client = CompatibleModelClient.from_env() if args.provider == "compatible" else RuleBasedModelClient()
    except StrategyAgentError as exc:
        print(f"{exc.code}: {exc}")
        return 2
    agent = StrategyAgent(client, retry_policy=RetryPolicy(max_attempts=args.max_attempts))
    config = {"provider": args.provider, "model": getattr(client, "model", "offline-rule-based"), "temperature": getattr(client, "temperature", None), "timeout_seconds": getattr(client, "timeout_seconds", 60), "prompt_version": agent.prompt_builder.version, "prompt_sha256": agent.prompt_builder.sha256, "semantic_review": hasattr(client, "assess_strategy") or hasattr(client, "review_strategy"), "strategy_quality_review": hasattr(client, "assess_strategy"), "strategy_editor": hasattr(client, "refine_strategy") and not hasattr(client, "assess_strategy"), "strategy_editor_version": getattr(client, "editor_version", None), "validation_version": VALIDATION_VERSION, "implementation_sha256": implementation_fingerprint(), "max_attempts": args.max_attempts}
    config["reasoning_effort"] = getattr(client, "reasoning_effort", None)
    config["assessment_prompt_sha256"] = getattr(client, "assessment_prompt_sha256", None)
    config_version = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    records = []
    passed = 0
    for index, case in enumerate(cases):
        request_value = replace(case["request"], config_version=config_version)
        response = agent.generate(request_value).to_dict()
        ok = response["status"] == "succeeded"
        handoff = None
        handoff_error = None
        if ok:
            try:
                handoff = build_creative_request(request_value, response)
            except StrategyAgentError as exc:
                ok = False
                handoff_error = str(exc)
        passed += int(ok)
        records.append(
            {
                "case_id": case["case_id"],
                "category": case["category"],
                "comparison_group": case.get("comparison_group"),
                "input": request_value.to_dict(),
                "actual": response,
                "passed": ok,
                "attempts": agent.traces(request_value.task_id),
                "creative_request": handoff,
                "handoff_error": handoff_error,
            }
        )
        # 每例落盘，进程中断后也能查已完成证据；最后以完整报告替换本工具的检查点。
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"run_status":"running", "formal_acceptance_run":formal,
                                     "model_mode":args.provider,"config":config,
                                     "records":records},ensure_ascii=False,indent=2),encoding="utf-8")
        print(f"[{index + 1}/{len(cases)}] {case['case_id']} {response['status']} attempts={response['attempt_count']}", flush=True)
        if not ok:
            print(f"  error={(response.get('error') or {}).get('code', 'HANDOFF_INVALID')}", flush=True)
    human_cases = [record["case_id"] for record in records if not formal or int(record["case_id"].split("-")[1]) % 10 in (1, 2)]
    report = {
        "title": "营销策略智能体正式50例测试记录" if formal else "营销策略智能体小样本回归记录（非正式验收）",
        "suite": args.suite,
        "run_status": "finished",
        "formal_acceptance_run": formal,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "model_mode": args.provider,
        "config": config,
        "config_version": config_version,
        "real_model_evidence": args.provider == "compatible",
        "human_review": {"status": "pending", "case_ids": human_cases, "instructions": "正式验收每类2例共10例，两人独立检查，分歧由第三人复核；小样本全检。检查相关性、事实、渠道理由、差异、执行资源和创意接续。不得以模型复核代替人工。"},
        "summary": {
            "total": len(cases),
            "passed": passed,
            "failed": len(cases) - passed,
            "pass_rate": passed / len(cases),
            "first_attempt_passed": sum(record["passed"] and record["actual"]["attempt_count"] == 1 for record in records),
            "total_duration_ms": sum(attempt["duration_ms"] for record in records for attempt in record["attempts"]),
            "meets_structure_target": passed >= 48 if formal else None,
            "first_stage_accepted": False,
        },
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(output.resolve())
    return 0 if (passed >= 48 if formal else passed == len(cases)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
