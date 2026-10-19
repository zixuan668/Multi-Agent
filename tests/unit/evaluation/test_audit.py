"""Regressions found by tracing SRS FR-007/008 and historical feedback."""
from copy import deepcopy
import unittest

from src.agents.evaluation.contracts import ContractError, validate_draft, validate_feedback
from src.agents.evaluation.examples import make_source
from src.agents.evaluation.service import evaluate_bundle


class EvaluationAuditTests(unittest.TestCase):
    def pending_high_source(self):
        source=make_source();source['config_snapshot']['scoring_rule_version']='equal-weight-v2'
        first,second=source['rounds']
        first['draft']['risks']=[{'category':'constraint','severity':'high','target_path':'creative.items[0].copy','evidence':'待核对的承诺','description':'严重问题未消除'}]
        first['draft']['feedback'][0]['priority']='high'
        second['draft']['risks']=[];second['draft']['feedback']=[]
        for d in second['draft']['dimension_scores'].values():d['score']=90
        return source

    def test_high_score_cannot_silently_close_prior_severe_issue(self):
        result=evaluate_bundle(self.pending_high_source())
        self.assertEqual(result['final']['evaluation']['data']['total_score'],90)
        self.assertEqual(result['final']['decision'],'regenerate_creative')
        self.assertEqual(result['final']['pending_high_feedback_count'],1)

    def test_explicitly_verified_severe_fix_can_pass(self):
        source=self.pending_high_source();head=deepcopy(source);head['rounds']=head['rounds'][:1]
        first=evaluate_bundle(head)
        source['rounds'][1]['draft']['resolved_feedback_ids']=[f['feedback_id'] for f in first['feedback_status']]
        self.assertEqual(evaluate_bundle(source)['final']['assessment_status'],'passed')

    def test_unverified_severe_history_is_not_a_safe_final_version(self):
        source=self.pending_high_source();source['config_snapshot']['max_rounds']=2
        self.assertEqual(evaluate_bundle(source)['final']['assessment_status'],'needs_review')

    def test_unresolved_strategy_issue_keeps_priority_when_score_is_low(self):
        source=make_source(0,'strategy');source['config_snapshot']['scoring_rule_version']='equal-weight-v2'
        second=source['rounds'][1]['draft'];second['risks']=[]
        second['feedback']=[{'target_agent':'creative','target_path':'creative.items[0].copy','issue':'当前表达不清','suggestion':'简化表达','priority':'medium'}]
        for d in second['dimension_scores'].values():d['score']=70
        self.assertEqual(evaluate_bundle(source)['final']['decision'],'regenerate_strategy')

    def test_severe_risk_on_requirement_routes_to_strategy(self):
        source=make_source(0,'boundary')
        draft=source['rounds'][0]['draft']
        draft['risks']=[{'category':'constraint','severity':'high','target_path':'requirements.special_requirements',
                         'evidence':'必选渠道','description':'方案遗漏用户明确要求的渠道'}]
        draft['feedback']=[{'target_agent':'creative','target_path':'creative.items[0].copy',
                            'issue':'表达可改善','suggestion':'调整开头','priority':'low'}]
        result=evaluate_bundle(source)
        self.assertEqual(result['final']['decision'],'regenerate_strategy')
        self.assertTrue(any(f['target_agent']=='strategy' and f['priority']=='high'
                            for f in result['final']['evaluation']['data']['feedback']))

    def test_current_paths_are_canonical_before_risk_feedback_matching(self):
        source=make_source(0,'boundary');draft=source['rounds'][0]['draft']
        draft['risks']=[{'category':'fact','severity':'high','target_path':'creative.data.items[0].copy',
                         'evidence':'认证','description':'缺少认证依据'}]
        draft['feedback']=[{'target_agent':'creative','target_path':'creative.items[0].copy',
                            'issue':'缺少认证依据','suggestion':'删除未经证实的认证','priority':'high'}]
        result=evaluate_bundle(source)
        self.assertEqual(len(result['final']['evaluation']['data']['feedback']),1)

    def test_history_can_reference_previous_channel_and_exceed_one_round_limit(self):
        request=make_source()['rounds'][0]['request']
        rows=[{'feedback_id':f'f-{i}','evaluation_id':'old-evaluation','resolved':False,
               'target_agent':'creative','target_path':'creative.items[4].copy',
               'issue':'旧渠道的问题','suggestion':'在新方案中核对','priority':'medium'} for i in range(120)]
        validate_feedback(rows,request,records=True)
        with self.assertRaises(ContractError):
            validate_feedback([{k:v for k,v in rows[0].items() if k not in ('feedback_id','evaluation_id','resolved')}],request)

    def test_explicit_resolution_keeps_original_record_immutable(self):
        source=make_source();first_source=deepcopy(source);first_source['rounds']=first_source['rounds'][:1]
        first=evaluate_bundle(first_source);original=deepcopy(first['records'][0])
        feedback_id=original['outcome']['evaluation']['data']['feedback'][0]['feedback_id']
        source['rounds'][1]['draft']['resolved_feedback_ids']=[feedback_id]
        result=evaluate_bundle(source,prior_records=first['records'])
        self.assertEqual(result['records'][0],original)
        resolved=next(f for f in result['feedback_status'] if f['feedback_id']==feedback_id)
        self.assertTrue(resolved['resolved'])
        self.assertEqual(resolved['resolved_by_evaluation_id'],result['records'][1]['outcome']['evaluation']['result_id'])
        self.assertEqual(evaluate_bundle(source)['feedback_status'],result['feedback_status'],
                         'standalone replay preserves feedback identity and confirmation')

    def test_unknown_resolution_is_not_accepted(self):
        request=make_source()['rounds'][0]['request'];draft=make_source()['rounds'][0]['draft']
        draft['resolved_feedback_ids']=['invented-id']
        with self.assertRaises(ContractError):validate_draft(draft,request)


if __name__=='__main__':unittest.main()
