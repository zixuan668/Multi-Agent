import json
import re


PEOPLE = {
    "strategy": {"name": "李智信", "role": "策略负责人", "initial": "信"},
    "creative": {"name": "李莉", "role": "创意负责人", "initial": "莉"},
    "evaluation": {"name": "毛小纯", "role": "独立评审", "initial": "纯"},
}

PHASES = {
    "strategy": {
        "generating": "先核对产品事实、推广目标和限制，再确定受众与传播方向。",
        "validating": "正在检查策略的事实引用、预算与渠道约束。",
        "reviewing": "正在编辑策略，检查渠道分工和可执行性，再交给李莉。",
        "retrying": "这次策略未通过校验，正在修正；不会把无效结果交给李莉。",
    },
    "creative": {
        "generating": "正在依据已保存策略写标题、正文、行动引导和视觉方案。",
        "retrying": "创意草稿需要修正，正在保留有效部分并重新检查。",
    },
    "evaluation": {
        "generating": "正在逐项核对实际文案、产品依据、渠道适配与上一轮问题。",
        "retrying": "评审输出的格式或引用需要修正，不会直接使用未验证的评分。",
    },
}


def public_excerpt(content, agent):
    allowed = {
        "strategy": {"positioning": "策略方向", "theme": "传播主线", "claim": "事实卖点"},
        "creative": {"idea": "创意方向", "headline": "标题草稿", "body": "文案草稿", "call_to_action": "行动引导"},
        "evaluation": {"reason": "评审依据", "description": "风险检查", "suggestion": "修改建议"},
    }.get(agent, {})
    fragments = []
    pattern = r'"(' + "|".join(allowed) + r')"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)'
    for match in re.finditer(pattern, content):
        value = match.group(2)
        value = re.sub(r'\\(?:u[0-9a-fA-F]{0,3}|)$', '', value)
        try:
            value = json.loads('"' + value + '"')
        except (ValueError, TypeError):
            continue
        if value.strip():
            fragments.append({"label": allowed[match.group(1)], "text": value[:800]})
    return fragments[-4:]


def result_message(agent, response):
    data = response["data"]
    if agent == "strategy":
        return "策略已完成：" + data["positioning"] + "\n交给李莉的渠道：" + "、".join(item["name"] for item in data["channels"]) + "。"
    if agent == "creative":
        return "这一版创意已经交付：" + data["concept"]["idea"] + "\n请毛小纯检查实际文案和事实依据。"
    weakest = min(data["dimension_scores"].items(), key=lambda item: item[1]["score"])
    return f"本轮综合质量参考 {data['total_score']} 分。" + "\n" + weakest[1]["reason"] + ("\n主要修改意见：" + "；".join(item["issue"] for item in data["feedback"][:3]) if data["feedback"] else "\n本轮没有新增修改反馈。")
