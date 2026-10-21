from html import escape
import unicodedata
import re

from src.agents.strategy.errors import ContractValidationError


THEMES = {
    "ink": {"background": "#15142b", "surface": "#262244", "text": "#faf7ff", "muted": "#d1c6ec", "accent": "#ba9bff", "button": "#d9c9ff", "button_text": "#231b39"},
    "paper": {"background": "#f4efdf", "surface": "#e9e1cd", "text": "#222d27", "muted": "#465c4f", "accent": "#45705a", "button": "#244b38", "button_text": "#ffffff"},
}


def xml_text(value):
    return escape(re.sub(r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD\U00010000-\U0010FFFF]", "", str(value)))


def wrap_text(value, width):
    lines = []
    for paragraph in str(value).splitlines():
        line = ""
        used = 0
        for character in paragraph:
            size = 2 if unicodedata.east_asian_width(character) in ("W", "F") else 1
            if used + size > width and line:
                lines.append(line)
                line, used = "", 0
            line += character
            used += size
        if line.strip():
            lines.append(line)
    return lines


def render_poster(task, round_no, item_index, theme="ink"):
    if theme not in THEMES:
        raise ContractValidationError("请选择支持的海报配色")
    row = next((row for row in task["rounds"] if row["round_no"] == round_no), None)
    if not row or not row.get("creative") or type(item_index) is not int or not 0 <= item_index < len(row["creative"]["data"]["items"]):
        raise ContractValidationError("该版本或渠道没有有效文案")
    item = row["creative"]["data"]["items"][item_index]
    palette = THEMES[theme]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440" role="img"><title>{xml_text(task["requirements"]["product_name"])} · 排版海报</title><rect width="1080" height="1440" fill="{palette["background"]}"/><circle cx="1030" cy="110" r="300" fill="{palette["accent"]}" opacity=".12"/><circle cx="40" cy="1100" r="260" fill="{palette["accent"]}" opacity=".07"/><rect x="48" y="48" width="984" height="1344" rx="38" fill="none" stroke="{palette["accent"]}" stroke-opacity=".4"/>']

    def draw(lines, top, size, line_height, color, weight=400, left=96):
        parts.append(f'<text x="{left}" y="{top}" fill="{color}" font-family="Microsoft YaHei, PingFang SC, sans-serif" font-size="{size}" font-weight="{weight}">')
        for index, line in enumerate(lines):
            parts.append(f'<tspan x="{left}" dy="{0 if index == 0 else line_height}">{xml_text(line)}</tspan>')
        parts.append('</text>')
        return top + len(lines) * line_height

    top = draw(wrap_text(task["requirements"]["product_name"], 58), 112, 30, 42, palette["muted"], 600)
    top = draw(wrap_text(item["headline"], 28), top + 70, 62, 86, palette["text"], 700)
    parts.append(f'<path d="M96 {top+20}H984" stroke="{palette["accent"]}" stroke-opacity=".45" stroke-width="2"/>')
    claims = [reference["claim"] for reference in item["fact_references"] if len(reference["claim"]) <= 80][:2]
    top = max(top + 90, 650)
    for index, claim in enumerate(claims):
        lines = wrap_text(claim, 44)
        height = len(lines) * 46 + 54
        if top + height > 1050:
            break
        parts.append(f'<rect x="80" y="{top}" width="920" height="{height}" rx="24" fill="{palette["surface"]}"/>')
        draw([f'{index+1:02}'], top + 60, 24, 32, palette["accent"], 600, left=108)
        draw(lines, top + 60, 33, 46, palette["text"], left=180)
        top += height + 24
    cta = wrap_text(item["call_to_action"], 48)
    height = max(104, len(cta) * 42 + 48)
    parts.append(f'<rect x="80" y="{1340-height}" width="920" height="{height}" rx="24" fill="{palette["button"]}"/>')
    draw(cta, 1340 - height + 58, 31, 42, palette["button_text"], 600, left=108)
    if task["status"] != "approved" or task.get("selected_round") != round_no:
        draw(["排版草稿 · 使用前请核实文案"], 1374, 19, 26, palette["muted"])
    parts.append('</svg>')
    return ''.join(parts).encode("utf-8")
