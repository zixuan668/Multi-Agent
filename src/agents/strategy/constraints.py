"""可确定检查的中文约束提取；未识别原文仍完整交给模型复核。"""
from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Constraints:
    required_channels: tuple[str, ...]
    forbidden_channels: tuple[str, ...]
    forbidden_content: tuple[str, ...]
    clauses: tuple[str, ...]

    @property
    def conflicts(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.required_channels) & set(self.forbidden_channels)))


def extract_constraints(text: str | None) -> Constraints:
    required, forbidden, content = [], [], []
    clauses = tuple(part.strip() for part in re.split(r"[；;。\n]", text or "") if part.strip())
    # 明确命令式渠道要求；不把“不虚构优惠”误当成渠道。
    for clause in clauses:
        for match in re.finditer(r"(必须|必选|禁止|禁用|不得)(?:渠道[：:]?|使用|选择|通过|在)?\s*[：:]?\s*[‘“\"']?([^，,；;。\n]+)", clause):
            action, value = match.groups()
            value = re.sub(r"[’”\"'].*$|(?:渠道)?(?:进行)?(?:投放|推广|发布|宣传).*$", "", value).strip()
            if not value or len(value) > 40 or value.startswith(("虚构", "编造", "承诺", "生成", "修改", "忽略", "付费", "表达", "内容", "词语", "提及", "出现", "保留", "遵守", "符合", "满足", "确保", "保持", "控制", "超过")):
                continue
            for name in re.split(r"[、和及]", value):
                name = name.strip()
                if name:
                    (required if action in ("必须", "必选") else forbidden).append(name)
        for match in re.finditer(r"(?:禁用|禁止|不得)(?:表达|内容|词语|提及|出现|使用)(?:为)?[：:]?\s*[‘“\"']([^’”\"']+)[’”\"']", clause):
            content.append(match.group(1))
    return Constraints(tuple(dict.fromkeys(required)), tuple(dict.fromkeys(forbidden)), tuple(dict.fromkeys(content)), clauses)


def channel_matches(name: str, constraint: str) -> bool:
    return constraint in name or name in constraint
