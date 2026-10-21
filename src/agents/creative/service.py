from src.agents.generation import generate_validated, prompt_text
from src.contracts.campaign import envelope, validate_creative, fields, items, text, compact
from src.agents.strategy.errors import ContractValidationError
from .revisions import preserve_revision_scope
from difflib import SequenceMatcher


class CreativeAgent:
    def __init__(self, client=None, *, offline=False, system_prompt=None):
        if client is None and not offline:
            raise ValueError("真实创意生成需要模型客户端")
        self.client = client
        self.offline = offline
        self.system_prompt = system_prompt or prompt_text("creative")

    def propose(self, request, system_prompt, *, check=lambda: None, progress=lambda attempt: None):
        def validate(data, payload):
            fields(data, {"directions"}, "directions")
            options = items(data["directions"], "directions", maximum=2, minimum=2)
            for option in options:
                fields(option, {"title", "idea", "rationale", "headline"}, "direction")
                for key, limit in (("title",30),("idea",300),("rationale",300),("headline",100)):
                    text(option[key], key, limit)
            if compact(options[0]["idea"]) == compact(options[1]["idea"]) or options[0]["title"] == options[1]["title"]:
                raise ContractValidationError("两个创意方向必须不同")
            if SequenceMatcher(None, compact(options[0]["idea"]), compact(options[1]["idea"])).ratio() > .82:
                raise ContractValidationError("两个方向的表达过于相似，请改变创意机制，而不是改写同一份说明")
            return [{**option, "option_id": f"direction-{index+1}"} for index, option in enumerate(options)]
        if self.offline:
            progress(1)
            product = request["requirements"]["product_name"][:30]
            return validate({"directions":[{"title":"功能对照","idea":"按产品已有功能做清晰对照，帮助读者判断适用场景。","rationale":"离线规则提案，仅用于交互联调。","headline":product+"：看看哪些功能适合你"},{"title":"场景自查","idea":"从使用者的一次具体场景出发，用自查问题组织已知事实。","rationale":"离线规则提案，仅用于交互联调。","headline":product+"：从一个使用场景开始"}]},request)
        result, _ = generate_validated(self.client, system_prompt, request, validate, check=check, progress=progress)
        return result

    def generate(self, request, *, version, check=lambda: None, progress=lambda attempt: None, direction=None):
        check()
        if self.offline:
            progress(1)
            strategy = request["strategy"]["data"]
            description = request["requirements"]["product_description"]
            quote = strategy["selling_points"][0]["source_quote"]
            data = {
                "strategy_result_id": request["strategy"]["result_id"],
                "concept": {"idea": strategy["marketing_strategy"]["theme"], "rationale": "围绕已确认的策略定位，将产品原文转化为渠道内容。"},
                "items": [{
                    "channel": channel["name"], "headline": request["requirements"]["product_name"][:60],
                    "body": description[:1000], "call_to_action": "先了解产品详情，确认功能与适用条件。",
                    "visual_brief": {"subject": request["requirements"]["product_name"][:500], "composition": "单一主视觉，顶部标题，底部一行辅助信息。", "style": "清晰、克制，概念示意不冒充真实产品。", "aspect_ratio": "3:4", "poster": {'key_message': '了解一个已确认的产品特点', 'headline': request['requirements']['product_name'][:22], 'supporting_text': None, 'action_text': None, 'layout': 'top_hero_bottom', 'visual_mode': 'graphic_concept', 'hero_description': '一个与产品核心特点相关的主形体，留白完整；不绘制虚构界面、包装或额外文字。'}},
                    "fact_references": [{"claim": strategy["selling_points"][0]["claim"][:500], "source_quote": quote[:500]}], "assets": [],
                } for channel in strategy["channels"]],
                "assumptions": ["离线规则生成仅供流程联调，创意质量需真实模型与人工复核。"],
            }
            data = validate_creative(data, request)
            attempt = 1
        else:
            def validate(data, payload):
                for item in data.get('items', []):
                    if 'poster' not in item.get('visual_brief', {}):
                        raise ContractValidationError('新版创意必须在每个visual_brief中交付独立poster海报稿，不能只返回长段制作说明')
                return validate_creative(preserve_revision_scope(data, payload), payload)
            data, attempt = generate_validated(self.client, self.system_prompt, request, validate, check=check, progress=progress, context={"selected_creative_direction": direction} if direction else None)
        check()
        return envelope("creative", request, data, version, attempt)
