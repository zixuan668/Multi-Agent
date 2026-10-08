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
from src.agents.strategy.service import StrategyAgent


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


def main() -> int:
    parser = argparse.ArgumentParser(description="运行固定50例，真实模型模式会调用模型服务并可能产生费用")
    parser.add_argument("--provider", choices=("compatible", "offline"), default="compatible")
    parser.add_argument(
        "--output",
        default=None,
        help="证据输出路径",
    )
    args = parser.parse_args()
    try:
        client = CompatibleModelClient.from_env() if args.provider == "compatible" else RuleBasedModelClient()
    except StrategyAgentError as exc:
        print(f"{exc.code}: {exc}")
        return 2
    agent = StrategyAgent(client)
    config = {"provider": args.provider, "model": getattr(client, "model", "offline-rule-based"), "temperature": getattr(client, "temperature", None), "timeout_seconds": getattr(client, "timeout_seconds", 60), "prompt_version": agent.prompt_builder.version, "prompt_sha256": agent.prompt_builder.sha256, "semantic_review": hasattr(client, "review_strategy"), "validation_version": "strategy-rules-v2"}
    config_version = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]
    records = []
    passed = 0
    for index in range(50):
        category = CATEGORIES[index // 10]
        request_value = replace(build_request(index, category), config_version=config_version)
        response = agent.generate(request_value).to_dict()
        ok = response["status"] == "succeeded"
        if ok:
            build_creative_request(request_value, response)
        passed += int(ok)
        records.append(
            {
                "case_id": f"ACCEPT-{index + 1:02d}",
                "category": category[0],
                "input": request_value.to_dict(),
                "actual": response,
                "passed": ok,
                "attempts": agent.traces(request_value.task_id),
            }
        )
        print(f"[{index + 1}/50] {category[0]} {response['status']} attempts={response['attempt_count']}", flush=True)
    report = {
        "title": "营销策略智能体固定50例测试记录",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "model_mode": args.provider,
        "config": config,
        "config_version": config_version,
        "real_model_evidence": args.provider == "compatible",
        "human_review": {"status": "pending", "case_ids": [f"ACCEPT-{index + 1:02d}" for index in range(50) if index % 10 in (0, 1)], "instructions": "每类2例共10例，两人按 AC-004至AC-006独立检查，分歧由第三人复核；离线记录不能代替真实模型验收"},
        "summary": {
            "total": 50,
            "passed": passed,
            "failed": 50 - passed,
            "pass_rate": passed / 50,
            "meets_structure_target": passed >= 48,
            "first_stage_accepted": False,
        },
        "records": records,
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = Path(args.output or f"artifacts/acceptance/strategy-{args.provider}-50-{stamp}.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    print(output.resolve())
    return 0 if passed >= 48 else 1


if __name__ == "__main__":
    raise SystemExit(main())
