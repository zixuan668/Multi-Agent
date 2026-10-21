from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from src.agents.creative.revisions import preserve_revision_scope
from src.agents.creative import CreativeAgent
from src.agents.strategy.errors import ContractValidationError, ModelOutputError
from src.backend.image_briefs import poster_plan, compile_image_prompt
from src.contracts.poster import validate_poster_plan


def plan():
    return {'key_message': '让今日学习安排更清楚', 'headline': '先理清今天，再开始', 'supporting_text': '学习计划、错题归纳、复盘提醒', 'action_text': None, 'layout': 'top_hero_bottom', 'visual_mode': 'editorial_scene', 'hero_description': '固定俯视角，一本打开的笔记本作为唯一主视觉，笔放在笔记本右侧，背景整洁，不出现人物或屏幕。'}


class PosterBriefTests(unittest.TestCase):
    def setUp(self):
        self.task = {'requirements': {'product_name': '知行 AI 学习助手', 'product_description': '提供个性化学习计划、错题归纳和每日复盘提醒。', 'special_requirements': '不承诺成绩提升', 'target_audience': '大学生'}}
        self.row = {'creative': {'data': {'items': [{'channel': '校园社群', 'headline': '这是一段太长的旧广告标题不能硬塞成五六行文字在海报的左上角', 'body': 'LONG_BODY_SHOULD_NOT_BE_IN_IMAGE', 'call_to_action': 'LONG_CTA_SHOULD_NOT_BE_IN_IMAGE', 'visual_brief': {'subject': 'THREE_PHONES_AND_MANY_NOTES', 'composition': 'LEGACY_CONFLICTING_LAYOUT', 'style': 'LEGACY_MOVIE_GLOW', 'aspect_ratio': '3:4'}}]}}}

    def test_only_poster_copy_is_printed_and_legacy_instructions_are_not_forwarded(self):
        compiled = compile_image_prompt(self.task, self.row, 0, plan())
        for marker in ('LONG_BODY', 'LONG_CTA', 'THREE_PHONES', 'LEGACY_CONFLICTING', 'LEGACY_MOVIE'):
            self.assertNotIn(marker, compiled)
        self.assertIn('最多两行', compiled)
        self.assertIn('四边安全边距至少8%', compiled)
        self.assertIn('一组消失点', compiled)
        self.assertIn('不绘制任何可操作界面', compiled)
        block = compiled.split('【只允许排印以下文字，逐字准确且各出现一次】\n')[1].split('\n除此之外')[0]
        copy = json.loads(block)
        self.assertEqual(set(copy), {'品牌', '主标题', '辅助文案'})
        self.assertEqual(copy['主标题'], plan()['headline'])
        self.assertNotIn('action_text', copy)

    def test_legacy_plan_warns_and_does_not_silently_truncate_a_sentence(self):
        preview = poster_plan(self.task, self.row, 0)
        self.assertEqual(preview['plan']['headline'], self.task['requirements']['product_name'])
        self.assertTrue(preview['warnings'])
        self.assertIsNone(preview['plan']['action_text'])
        self.assertEqual(preview['plan']['visual_mode'], 'graphic_concept')

    def test_long_text_multiline_unknown_fields_and_layouts_are_rejected(self):
        for field, value in (('headline', '字'*23), ('supporting_text', '字'*33), ('action_text', '字'*15), ('headline', '第一行\n第二行'), ('layout', 'free_layout'), ('visual_mode', 'multiple_screens'), ('unexpected', 'x')):
            with self.subTest(field=field), self.assertRaises(ContractValidationError):
                validate_poster_plan({**plan(), field: value})

    def test_explicit_plan_keeps_single_focus_and_is_not_mutated(self):
        original = plan()
        self.row['creative']['data']['items'][0]['visual_brief']['poster'] = original
        preview = poster_plan(self.task, self.row, 0)
        self.assertEqual(preview['plan'], original)
        preview['plan']['headline'] = 'changed'
        self.assertEqual(original['headline'], '先理清今天，再开始')

    def test_new_creative_cannot_silently_omit_poster_plan(self):
        client = Mock()
        client.complete_json.return_value = {'items': [{'visual_brief': {}}]}
        with self.assertRaises(ModelOutputError):
            CreativeAgent(client).generate({}, version=1)
        self.assertEqual(client.complete_json.call_count, 3)
        self.assertIn('poster', client.complete_json.call_args.args[1])

    def test_scoped_title_revision_updates_poster_title_without_changing_layout(self):
        before = {'strategy_result_id': 'strategy-1', 'concept': {}, 'items': [{'headline': '旧标题', 'body': '不改变的正文', 'visual_brief': {'poster': plan()}}]}
        data = deepcopy(before)
        data['items'][0]['headline'] = '新标题'
        data['items'][0]['body'] = '不应被采纳的改动'
        data['items'][0]['visual_brief']['poster']['headline'] = '新的海报标题'
        data['items'][0]['visual_brief']['poster']['layout'] = 'centered_hero'
        result = preserve_revision_scope(data, {'previous_result': {'data': before}, 'feedback': [{'feedback_id': 'human-1', 'target_path': 'creative.items[0].headline'}]})
        self.assertEqual(result['items'][0]['body'], before['items'][0]['body'])
        self.assertEqual(result['items'][0]['visual_brief']['poster']['headline'], '新的海报标题')
        self.assertEqual(result['items'][0]['visual_brief']['poster']['layout'], 'top_hero_bottom')


if __name__ == '__main__':
    unittest.main()
