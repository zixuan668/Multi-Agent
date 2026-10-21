from copy import deepcopy
import re

from src.agents.strategy.errors import ContractValidationError


POSTER_VERSION = 'single-focus-poster-v1'
POSTER_LIMITS = {'key_message': 60, 'headline': 22, 'supporting_text': 32, 'action_text': 14, 'hero_description': 160}
POSTER_LAYOUTS = {'top_hero_bottom', 'left_copy_right_hero', 'centered_hero'}
POSTER_MODES = {'product_still_life', 'editorial_scene', 'graphic_concept'}


def validate_poster_plan(value):
    expected = set(POSTER_LIMITS) | {'layout', 'visual_mode'}
    if not isinstance(value, dict) or set(value) != expected:
        raise ContractValidationError('海报方案须包含单一诉求、短标题、辅助文案、行动文案、版式、画面类型及主体描述')
    result = deepcopy(value)
    for key, limit in POSTER_LIMITS.items():
        item = value[key]
        if key in ('supporting_text', 'action_text') and item is None:
            continue
        if not isinstance(item, str) or not item.strip() or len(item.strip()) > limit or re.search(r'[\x00-\x1f\x7f]', item):
            raise ContractValidationError(f'poster.{key} 须为1至{limit}字的单行文本；辅助文案与行动文案可设为null')
        result[key] = item.strip()
    if not isinstance(result['layout'], str) or not isinstance(result['visual_mode'], str) or result['layout'] not in POSTER_LAYOUTS or result['visual_mode'] not in POSTER_MODES:
        raise ContractValidationError('海报版式或画面类型不受支持')
    return result
