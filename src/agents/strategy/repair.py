"""只标识规划推断，不补写产品事实；内容修复锁定未出错字段。"""
from copy import deepcopy
import re


_OBJECT_FIELDS = {
    (): {"target_audience", "positioning", "selling_points", "channels", "marketing_strategy", "assumptions", "missing_information", "constraint_conflicts"},
    ("target_audience",): {"segment", "needs", "pain_points", "age_range", "occupation", "basis"},
    ("selling_points", "[]"): {"claim", "source_quote"},
    ("channels", "[]"): {"name", "reason", "content_direction", "allocated_amount"},
    ("marketing_strategy",): {"theme", "content_directions", "promotion_methods"},
}


def discard_unknown_output_fields(candidate: dict) -> tuple[dict, list[str]]:
    """丢弃契约外字段，但不补字段、不改字段值，避免无害模型噪声触发昂贵重试。"""
    value = deepcopy(candidate)
    discarded: list[str] = []

    def visit(item, path=()):
        if isinstance(item, dict):
            shape = tuple("[]" if isinstance(part, int) else part for part in path)
            allowed = _OBJECT_FIELDS.get(shape)
            if allowed is not None:
                for key in list(item):
                    if key not in allowed:
                        discarded.append(".".join(str(part) for part in (*path, key)))
                        del item[key]
            for key, child in list(item.items()):
                visit(child, (*path, key))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, (*path, index))

    visit(value)
    return value, discarded


def mark_planning_inferences(data: dict) -> dict:
    value = deepcopy(data)
    # 需求、痛点和渠道适配是规划判断，不是已经验证的用户调研或渠道效果。
    def label(text):
        if any(marker in text for marker in ("待验证", "待核实", "假设", "推断")):
            return text
        return "待验证假设：" + text
    for field in ("needs", "pain_points"):
        value["target_audience"][field] = [label(text) for text in value["target_audience"][field]]
    for channel in value["channels"]:
        channel["reason"] = label(channel["reason"])
    return value


def repair_only_reported_fields(previous: dict, candidate: dict, issues: list[dict]) -> dict:
    """语义问题有有效字段路径才局部合并；结构/全局问题走完整重生成校验。"""
    if not issues:
        return candidate
    paths = []
    for issue in issues:
        path = issue.get("field", "")
        path = re.sub(r"^(?:strategy_data|data)\.", "", path)
        if not re.fullmatch(r"[a-z_]+(?:\[\d+\]|\.[a-z_]+)*", path):
            return candidate
        parts = [int(index) if index else name for name, index in re.findall(r"([a-z_]+)|\[(\d+)\]", path)]
        if not parts or parts[0] not in previous:
            return candidate
        # 修改一条卖点时允许同时改正文和依据，不改变其他卖点。
        if parts[0] == "selling_points" and len(parts) >= 2 and isinstance(parts[1], int):
            parts = parts[:2]
        paths.append(parts)
    result = deepcopy(previous)
    try:
        for parts in paths:
            source, target = candidate, result
            for part in parts[:-1]:
                source, target = source[part], target[part]
            target[parts[-1]] = deepcopy(source[parts[-1]])
        # 标注假设的修复可同步补充假设说明，但不准改其他业务字段。
        if "assumptions" in candidate:
            result["assumptions"] = deepcopy(candidate["assumptions"])
    except (KeyError, IndexError, TypeError):
        return candidate
    return result
