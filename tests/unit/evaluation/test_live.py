from copy import deepcopy
from threading import Event
import time
import unittest

from src.agents.evaluation.adapter import from_b_package,strategy_handoff
from src.agents.evaluation.contracts import ContractError, validate_handoff
from src.agents.evaluation.examples import draft_template
from src.agents.evaluation.provider import EvaluationConfig, EvaluationError
from src.agents.evaluation.workspace import EvaluationWorkspace
from src.backend.creative_workspace import CreativeWorkspace
from src.agents.creative.errors import CreativeError
from tests.unit.test_creative_v6 import FakeTasks, MockProvider


class Scorer:
    def __init__(self, drafts=None, errors=None):
        self.config=EvaluationConfig('https://api.deepseek.com','unit-secret')
        self.drafts=drafts or [80]
        self.errors=list(errors or [])
        self.calls=[]
        self.gate=None

    def call(self, data):
        self.calls.append(deepcopy(data))
        if self.gate: self.gate.wait(3)
        if self.errors:
            exc=self.errors.pop(0)
            if exc: raise exc
        score=self.drafts[min(data['request']['round_no']-1,len(self.drafts)-1)]
        draft=draft_template()
        for dimension in draft['dimension_scores'].values(): dimension['score']=score
        draft['risks']=[]
        if score>=80: draft.update(feedback=[],recommended_action='accept')
        return draft


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.tasks=FakeTasks();self.task=self.tasks.h['task_id'];self.scope='owner'
        self.b=CreativeWorkspace(self.tasks,MockProvider());self.addCleanup(self.b.close)
        self.b.accept(self.task,self.scope)
        for channel in self.tasks.h['strategy']['data']['channels']:
            self.operate('generate',channel=channel['name'])

    def wait_b(self):
        until=time.monotonic()+5
        while time.monotonic()<until:
            state=self.b.get(self.task,self.scope)
            if not state['job'] or state['job']['status']!='running':
                if state['job']: self.assertEqual(state['job']['status'],'succeeded',state['job'])
                return state
            time.sleep(.005)
        self.fail('B timeout')

    def operate(self,action,**kwargs):
        state=self.b.get(self.task,self.scope)
        self.b.start(self.task,self.scope,{'action':action,'base_result_id':state['versions'][-1]['result_id'] if state['versions'] else None,**kwargs})
        return self.wait_b()

    def c(self, scorer=None):
        self.scorer=scorer or Scorer()
        self.cstore=EvaluationWorkspace(self.b,provider=self.scorer,sleep=lambda _:None)
        self.addCleanup(self.cstore.close);self.b.evaluation_dispatch=self.cstore.enqueue
        return self.cstore

    def deliver(self):
        latest=self.b.get(self.task,self.scope)['versions'][-1]
        return self.b.deliver(self.task,self.scope,latest['result_id'])

    def wait_c(self):
        until=time.monotonic()+5
        while time.monotonic()<until:
            state=self.cstore.get(self.task,self.scope)
            if state['job'] and state['job']['status']!='running':return state
            time.sleep(.005)
        self.fail('C timeout')

    def test_b_package_preserves_original_version_and_texts(self):
        base=self.b.get(self.task,self.scope)['versions'][-1]['result_id']
        package=self.b.package(self.task,self.scope,base);original=deepcopy(package)
        req=from_b_package(package,'c-test')
        self.assertEqual(validate_handoff(req)['creative'],package['creative'])
        self.assertIsInstance(req['creative']['data']['items'][0]['video_script'],str)
        self.assertEqual(package,original)
        for mutate in (lambda p:p['strategy'].update(task_id='other'),
                       lambda p:p['creative'].update(strategy_result_id='old'),
                       lambda p:p['creative'].update(strategy_version=999)):
            bad=deepcopy(package);mutate(bad)
            with self.assertRaises(ContractError):from_b_package(bad,'c-test')

    def test_real_feedback_revision_and_stable_two_round_history(self):
        self.c(Scorer([70,86]));self.deliver();first=self.wait_c()
        self.assertEqual(first['job']['status'],'succeeded',first['job'])
        first_record=deepcopy(first['bundle']['records'][0])
        b=self.b.get(self.task,self.scope)
        self.assertEqual(b['state'],'returned');self.assertEqual(b['feedback'][-1]['mode'],'real_c')
        self.assertEqual(b['feedback'][-1]['items'][0]['target_path'],'items[0].copy')
        self.operate('revision');self.deliver();second=self.wait_c()
        self.assertEqual(second['job']['status'],'succeeded',second['job'])
        self.assertEqual(second['bundle']['final']['assessment_status'],'passed')
        self.assertEqual(second['bundle']['records'][0],first_record)
        self.assertEqual(second['bundle']['records'][1]['request']['strategy'],first_record['request']['strategy'])
        self.assertEqual(second['bundle']['final']['iteration_count'],2)
        self.assertEqual(self.b.get(self.task,self.scope)['state'],'passed')

    def test_B_receives_older_unresolved_issues_with_current_feedback(self):
        class FollowupScorer(Scorer):
            def call(self,payload):
                draft=super().call(payload)
                if payload['request']['round_no']==2:
                    draft['feedback']=[{'target_agent':'creative','target_path':'creative.items[0].slogan',
                                        'issue':'短句不够明确','suggestion':'明确短句中的行动','priority':'medium'}]
                return draft
        self.c(FollowupScorer([70,70]));self.deliver();self.wait_c()
        self.operate('revision');self.deliver();state=self.wait_c()
        self.assertEqual(state['job']['status'],'succeeded',state['job'])
        paths={f['target_path'] for f in self.b.get(self.task,self.scope)['feedback'][-1]['items']}
        self.assertEqual(paths,{'items[0].copy','items[0].slogan'})

    def test_retries_do_not_add_rounds_and_auth_never_retries(self):
        self.c(Scorer(errors=[EvaluationError('MODEL_TIMEOUT','timeout',True),None]));self.deliver();state=self.wait_c()
        self.assertEqual(state['job']['status'],'succeeded',state['job'])
        self.assertEqual(state['bundle']['final']['iteration_count'],1)
        self.assertEqual(state['bundle']['final']['evaluation']['attempt_count'],2)
        self.assertEqual(len(self.scorer.calls),2)

    def test_auth_failure_keeps_b_version_and_records_no_fake_score(self):
        self.c(Scorer(errors=[EvaluationError('MODEL_AUTH_FAILED','auth')]));self.deliver();state=self.wait_c()
        self.assertEqual(state['job']['error']['code'],'MODEL_AUTH_FAILED')
        self.assertIsNone(state['bundle']);self.assertEqual(len(self.scorer.calls),1)
        self.assertEqual(self.b.get(self.task,self.scope)['state'],'pending')

    def test_b_high_risk_veto_even_when_model_supplies_90(self):
        self.operate('edit',path='items[0].copy',value='获得国际权威认证，保证效果。')
        self.c(Scorer([90]));self.deliver();state=self.wait_c()
        self.assertEqual(state['job']['status'],'succeeded',state['job'])
        self.assertNotEqual(state['bundle']['final']['decision'],'accept')
        self.assertTrue(any(r['severity']=='high' for r in state['bundle']['final']['evaluation']['data']['risks']))
        self.assertEqual(self.b.get(self.task,self.scope)['state'],'returned')

    def test_duplicate_delivery_is_one_call_and_no_secret_in_state(self):
        scorer=Scorer();scorer.gate=Event();self.c(scorer)
        first=self.deliver();second=self.deliver()
        self.assertEqual(first['delivery_id'],second['delivery_id'])
        self.assertEqual(first['evaluation_job']['job_id'],second['evaluation_job']['job_id'])
        scorer.gate.set();state=self.wait_c()
        self.assertEqual(len(scorer.calls),1)
        self.assertNotIn('unit-secret',str(state));self.assertNotIn('_provider',state)

    def test_cross_owner_and_stale_callback_rejected(self):
        self.c();self.deliver();state=self.wait_c()
        with self.assertRaises(Exception):self.cstore.get(self.task,'other')
        bundle=deepcopy(state['bundle']);bundle['final']['evaluation']['data']['creative_result_id']='old'
        with self.assertRaises(CreativeError):self.b.apply_evaluation(self.task,self.scope,'forged',bundle)

    def test_three_rounds_terminal_and_prior_history_preserved(self):
        self.c(Scorer([72,78,76]));ids=[]
        for round_no in range(1,4):
            self.deliver();state=self.wait_c()
            self.assertEqual(state['job']['status'],'succeeded',state['job'])
            ids.append(state['bundle']['final']['evaluation']['result_id'])
            if round_no<3:self.operate('revision')
        self.assertEqual(state['bundle']['selected_index'],1)
        self.assertEqual(state['bundle']['final']['assessment_status'],'not_passed')
        self.assertEqual(state['bundle']['final']['selected_evaluation_id'],ids[1])
        self.assertEqual([r['outcome']['evaluation']['result_id'] for r in state['bundle']['records']],ids)
        with self.assertRaises(CreativeError):self.operate('revision')

    def test_strategy_feedback_builds_A_compatible_request(self):
        class StrategyScorer(Scorer):
            def call(self,data):
                draft=super().call(data)
                draft['feedback']=[{'target_agent':'strategy','target_path':'strategy.positioning',
                                    'issue':'定位未回应主要目标','suggestion':'依据原始需求明确当前优先目标','priority':'medium'}]
                return draft
        self.c(StrategyScorer([70]));self.deliver();state=self.wait_c()
        self.assertEqual(state['job']['status'],'succeeded',state['job'])
        handoff=strategy_handoff(state['bundle'])
        request=handoff['strategy_revision_request']
        from src.agents.strategy.models import StrategyRequest
        self.assertEqual(StrategyRequest.from_dict(request).round_no,2)
        self.assertEqual(request['config_version'],self.tasks.h['config_version'])
        self.assertEqual(request['previous_result'],self.tasks.h['strategy'])
        self.assertEqual(self.b.get(self.task,self.scope)['state'],'needs_strategy')

    def test_second_round_technical_failure_keeps_first_round_without_selecting_it(self):
        scorer=Scorer([70]);self.c(scorer);self.deliver();first=self.wait_c()
        self.operate('revision')
        scorer.errors=[EvaluationError('MODEL_TIMEOUT','timeout',True)]*3
        self.deliver();failed=self.wait_c()
        self.assertEqual(failed['job']['status'],'failed')
        self.assertEqual(failed['bundle']['records'][0],first['bundle']['records'][0])
        self.assertEqual(failed['bundle']['final']['task_status'],'failed')
        self.assertIsNone(failed['bundle']['selected_index'])

    def test_negative_effect_statement_does_not_trigger_positive_claim_rule(self):
        self.operate('edit',path='items[0].copy',value='不保证效果，请依据实际产品信息按需选择。')
        self.c(Scorer([86]));self.deliver();state=self.wait_c()
        self.assertEqual(state['job']['status'],'succeeded',state['job'])
        self.assertEqual(state['bundle']['final']['assessment_status'],'passed')


class EvaluationConcurrencyTests(unittest.TestCase):
    def test_five_simultaneous_jobs_keep_task_and_result_references(self):
        class Tasks:
            def __init__(self):self.rows={}
            def get(self,task,scope):
                if scope!='owner' or task not in self.rows:raise ValueError('denied')
                return {'status':'completed','result':deepcopy(self.rows[task]['strategy'])}
            def creative_request(self,task,scope):self.get(task,scope);return deepcopy(self.rows[task])
        from tests.unit.test_creative_v6 import fixture
        tasks=Tasks();b=CreativeWorkspace(tasks,MockProvider());self.addCleanup(b.close)
        scorer=Scorer();scorer.gate=Event()
        c=EvaluationWorkspace(b,provider=scorer,sleep=lambda _:None);self.addCleanup(c.close)
        b.evaluation_dispatch=c.enqueue
        try:
            for index in range(5):
                h=fixture();task='parallel-'+str(index);h['task_id']=task;h['strategy']['task_id']=task
                h['strategy']['result_id']='strategy-'+task;tasks.rows[task]=h;b.accept(task,'owner')
                base=None
                for channel in h['strategy']['data']['channels']:
                    b.start(task,'owner',{'action':'generate','base_result_id':base,'channel':channel['name']})
                    until=time.monotonic()+3
                    while time.monotonic()<until:
                        state=b.get(task,'owner')
                        if state['job']['status']!='running':break
                        time.sleep(.005)
                    self.assertEqual(state['job']['status'],'succeeded');base=state['versions'][-1]['result_id']
                b.deliver(task,'owner',base)
            until=time.monotonic()+3
            while len(scorer.calls)<5 and time.monotonic()<until:time.sleep(.005)
            self.assertEqual(len(scorer.calls),5)
        finally:scorer.gate.set()
        for index in range(5):
            task='parallel-'+str(index);until=time.monotonic()+3
            while time.monotonic()<until:
                state=c.get(task,'owner')
                if state['job']['status']!='running':break
                time.sleep(.005)
            self.assertEqual(state['job']['status'],'succeeded',state['job'])
            data=state['bundle']['final']['evaluation']['data']
            self.assertEqual(data['strategy_result_id'],'strategy-'+task)
            self.assertEqual(state['bundle']['final']['evaluation']['task_id'],task)


if __name__=='__main__':unittest.main()
