from copy import deepcopy
import json
from pathlib import Path
from uuid import uuid4

def products():
    return json.loads((Path(__file__).resolve().parents[3] / "tests/fixtures/evaluation/products.json").read_text(encoding="utf-8"))

def draft_template():
    return {'dimension_scores': {'attraction': {'score': 82, 'reason': '主题明确，能够从具体功能切入。', 'target_path': 'creative.items[0].slogan'}, 'audience_fit': {'score': 80, 'reason': '受众和场景与输入一致。', 'target_path': 'strategy.target_audience'}, 'clarity': {'score': 80, 'reason': '产品功能和限制表达清楚。', 'target_path': 'creative.items[0].copy'}, 'channel_fit': {'score': 79, 'reason': '渠道与内容形式匹配，但行动路径仍可更具体。', 'target_path': 'strategy.channels'}, 'call_to_action': {'score': 79, 'reason': '引导动作存在，但未明确用户下一步。', 'target_path': 'creative.items[0].copy'}}, 'risks': [{'category': 'audience', 'severity': 'low', 'target_path': 'strategy.target_audience', 'evidence': 'target_audience', 'description': '目标人群仍可进一步细分。'}], 'feedback': [{'target_agent': 'creative', 'target_path': 'creative.items[0].copy', 'issue': '行动引导不够具体。', 'suggestion': '补充可执行的下一步动作，但不得虚构购买入口或优惠。', 'priority': 'medium'}], 'recommended_action': 'regenerate_creative'}

SCENARIOS = [
    {"id": "improve", "name": "创意优化后通过", "description": "两轮样例 · 保留策略，优化行动引导"},
    {"id": "strategy", "name": "策略优先优化", "description": "两轮样例 · 策略与创意反馈并存"},
    {"id": "risk", "name": "高分风险否决", "description": "三轮样例 · 90分有风险，最终选择78分安全版本"},
    {"id": "review", "name": "全部版本需复核", "description": "三轮样例 · 全部存在严重风险"},
    {"id": "boundary", "name": "80分通过边界", "description": "单轮样例 · 80.0分，无严重风险"},
]


def make_source(product: int = 0, scenario: str = "improve") -> dict:
    if scenario not in {s["id"] for s in SCENARIOS} or not 0 <= product < 5:
        raise ValueError("请选择有效产品与样例场景。")
    base = deepcopy(products()[product])
    base["task_id"] = "preview_" + uuid4().hex[:12]
    for agent in ("strategy", "creative"):
        base[agent]["task_id"] = base["task_id"]
        base[agent]["result_id"] = f"{agent}_{base['task_id']}_v1"
    base["creative"]["data"]["strategy_result_id"] = base["strategy"]["result_id"]
    plans = {
        "improve": [(78, 80, 76, 80, 65), (90, 88, 86, 91, 87)],
        "strategy": [(72, 64, 74, 62, 70), (86, 88, 85, 89, 86)],
        "risk": [(90,) * 5, (78,) * 5, (76,) * 5],
        "review": [(90,) * 5, (82,) * 5, (85,) * 5],
        "boundary": [(80,) * 5],
    }
    rows = []
    strategy_version = 1
    for index, scores in enumerate(plans[scenario], start=1):
        request = deepcopy(base)
        request["round_no"] = index
        request["strategy"]["round_no"] = 1 if strategy_version == 1 else index
        if scenario == "strategy" and index > 1:
            strategy_version = 2
            request["strategy"]["version"] = 2
            request["strategy"]["round_no"] = index
            request["strategy"]["result_id"] = f"strategy_{base['task_id']}_v2"
            request["strategy"]["data"]["target_audience"]["needs"] = ["明确了解真实功能与适用场景", "了解如何进一步查看产品信息"]
        request["creative"]["round_no"] = index
        request["creative"]["version"] = index
        request["creative"]["result_id"] = f"creative_{base['task_id']}_v{index}"
        request["creative"]["data"]["strategy_result_id"] = request["strategy"]["result_id"]
        if index > 1:
            request["creative"]["data"]["items"][0]["copy"] += "先阅读产品介绍，确认功能是否适合自己的使用场景。"
        draft = draft_template()
        for (key, dimension), score in zip(draft["dimension_scores"].items(), scores):
            dimension["score"] = score
            if index > 1 and scenario in {"improve", "strategy"}:
                dimension["reason"] = {
                    "attraction": "主题以可验证的产品特点切入，开头清晰且易于理解。",
                    "audience_fit": "诉求和使用场景与用户指定受众保持一致，推断内容已明确标注。",
                    "clarity": "产品特点与必要限制表达一致，未添加输入之外的承诺。",
                    "channel_fit": "内容结构符合推荐渠道，预算与渠道约束保持一致。",
                    "call_to_action": "补充先阅读产品介绍的具体动作，没有虚构链接或优惠。",
                }[key]
        draft["risks"] = []
        if index == 1 and scenario in {"improve", "strategy"}:
            draft["risks"] = [{"category": "audience", "severity": "low", "target_path": "strategy.target_audience", "evidence": request["requirements"]["target_audience"], "description": "受众内部需求差异仍待验证，建议后续通过访谈进一步细分。"}]
        high = scenario == "review" or (scenario == "risk" and index == 1)
        if high:
            request["creative"]["data"]["items"][0]["copy"] += "获得国际权威认证，保证效果。"
            draft["risks"].append({"category": "fact", "severity": "high", "target_path": "creative.items[0].copy", "evidence": "获得国际权威认证，保证效果。", "description": "原始输入没有提供认证或效果保证的依据，存在虚构承诺。"})
            if scenario == "review" and index == 1:
                draft["risks"].append({"category": "constraint", "severity": "high", "target_path": "creative.items[0].copy", "evidence": request["requirements"]["special_requirements"], "description": "保证效果的表述违反用户“不得承诺实际效果”的明确要求。"})
        if scores[0] >= 80 and not high and (scenario != "improve" or index > 1):
            draft["feedback"] = []
            draft["recommended_action"] = "accept"
        else:
            draft["feedback"][0]["issue"] = "文案包含缺乏依据的认证与效果承诺。" if high else "行动引导不够具体，用户下一步不清晰。"
            draft["feedback"][0]["suggestion"] = "删除认证和保证效果的表述，保留用户输入中的可验证特点。" if high else "说明先查看产品信息的具体步骤，不添加未经确认的入口或优惠。"
            draft["feedback"][0]["priority"] = "high" if high else "medium"
        if scenario == "strategy" and index == 1:
            draft["feedback"].append({"target_agent": "strategy", "target_path": "strategy.target_audience.needs", "issue": "受众需求描述过于宽泛，缺少产品特定场景。", "suggestion": "围绕输入产品特点，具体描述目标受众需要了解的信息。", "priority": "high"})
            draft["recommended_action"] = "regenerate_strategy"
        rows.append({"request": request, "draft": draft})
    label = next(s["name"] for s in SCENARIOS if s["id"] == scenario)
    return {"label": label, "source": "契约样例 · 离线重放", "rounds": rows, "config_snapshot": {"config_version": base["config_version"], "pass_threshold": 80, "max_rounds": 3, "timeout_seconds": 60, "max_attempts": 3, "scoring_rule_version": "equal-weight-v1"}}
