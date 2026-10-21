import re


def brief_questions(requirements):
    goal = requirements["marketing_goal"]
    facts = requirements["product_description"] + "\n" + (requirements.get("special_requirements") or "")
    actions = re.finditer(r"申请试用|报名|预约(?:体验|到店|咨询)?|下单|购买转化|领取(?:优惠|优惠券|试用)", goal)
    action = next((match for match in actions if not re.search(r"(?:不|无需|不用|避免|禁止)[^，。；]{0,5}$", goal[max(0, match.start()-8):match.start()])), None)
    if not action:
        return []
    paths = re.search(r"https?://[^\s]+|(?:微信|公众号|小程序|官网|门店|电话|邮箱|客服|表单|店铺|淘宝|京东|天猫)[：:为是\s]*[^，。；\n\s]{2,40}", facts)
    unknown = re.search(r"(?:入口|链接|微信|官网|电话|表单|店铺).{0,8}(?:待确认|未知|没有|未提供|暂未|未开通)", facts)
    if re.search(r"https?://[^\s，。；]+", facts) or paths and not unknown:
        return []
    return [{"question": "你希望用户通过哪个真实入口“" + action.group() + "”？请补充链接、账号或明确的到店方式。", "reason": "先确认行动入口，避免生成后才发现广告无法执行；现在尚未调用模型。", "target_path": "requirements.marketing_goal", "evidence": action.group()}]


def partition_draft_questions(questions):
    blocking, preparation = [], []
    for question in questions:
        path = question["target_path"]
        planning_field = re.match(r"strategy\.(?:assumptions|missing_information)\[\d+\]$|strategy\.channels\[\d+\]\.(?:reason|content_direction)$", path)
        resource_question = re.search(r"账号|权限|许可|授权|拍摄|素材|门店|营业时间|地址|位置", question["question"])
        factual_question = re.search(r"价格|售价|优惠|功效|认证|销量|规格|尺寸|成分|试用入口|购买入口|报名入口", question["question"])
        (preparation if planning_field and resource_question and not factual_question else blocking).append(question)
    return blocking, preparation
