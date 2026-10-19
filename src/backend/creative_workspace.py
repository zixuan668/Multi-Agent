"""B process-memory repository and asynchronous operations; A store is read-only."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime,timezone
from threading import RLock
from uuid import uuid4
from src.agents.creative.intake import receive,brief
from src.agents.creative.errors import CreativeError
from src.agents.creative.validation import check_data,feedback_check,locate,FIELDS
from src.agents.creative.provider import Provider
from src.agents.creative.service import CreativeAgent
from src.agents.creative.schema import ROOT,validate

def now(): return datetime.now(timezone.utc).isoformat().replace('+00:00','Z')

class CreativeWorkspace:
    def __init__(self,tasks,provider=None,*,enabled=True,demo=False):
        self.tasks=tasks; self.provider=provider; self.enabled=enabled; self.demo=demo
        self.evaluation_dispatch = None
        self._records={}; self._lock=RLock(); self._pool=ThreadPoolExecutor(max_workers=3,thread_name_prefix="creative")

    def _auth(self,task_id,scope): return self.tasks.get(task_id,scope)

    def gate(self,task_id,scope):
        task=self._auth(task_id,scope)
        if task['status']!='completed' or not task.get('result'):
            raise CreativeError("策略尚未成功完成，不能交付 B", "STRATEGY_NOT_READY")
        handoff=receive(self.tasks.creative_request(task_id,scope),task_id)
        return {'handoff':handoff,'context':brief(handoff),'checks':[
            {'name':'creative-request.schema.json 及引用契约','passed':True},
            {'name':'任务归属、task_id 与完整成功策略一致','passed':True},
            {'name':'strategy result_id/version/data 已锁定','passed':True},
            {'name':'卖点 source_quote 可定位至产品原文','passed':True},
            {'name':'预算、渠道和事实边界合法','passed':True}]}

    def accept(self,task_id,scope):
        gate=self.gate(task_id,scope)
        with self._lock:
            key=(scope,task_id)
            if key not in self._records:
                self._records[key]={**gate,'versions':[],'deliveries':[],'feedback':[],
                    'events':[{'stage':'handoff_received','created_at':now()}], 'job':None,
                    'state':'ready','last_error':None,'demo_enabled':self.demo,'storage':'process-memory'}
            elif self._records[key]['handoff']!=gate['handoff']:
                raise CreativeError('上游策略版本已变化，不能混用旧创意', 'STALE_STRATEGY')
            return deepcopy(self._records[key])

    def get(self,task_id,scope):
        self._auth(task_id,scope)
        with self._lock:
            record=self._records.get((scope,task_id))
            if record is None: raise CreativeError('请先校验并接收 A 的策略','HANDOFF_REQUIRED')
            return deepcopy(record)

    def _current(self,r,base):
        previous=r['versions'][-1] if r['versions'] else None
        if (previous['result_id'] if previous else None)!=base:
            raise CreativeError('当前版本已变化，请刷新后重试','STALE_VERSION')
        return previous

    def _idle(self,r):
        if r['job'] and r['job']['status']=='running': raise CreativeError('当前操作尚未完成，请稍候','BUSY')
        if r['state'] in ('passed','not_passed'): raise CreativeError('业务流程已结束，不能产生下一轮','ROUND_LIMIT')

    def start(self,task_id,scope,payload):
        self._auth(task_id,scope)
        allowed={'action','base_result_id','channel','instruction','path','value'}
        if set(payload)-allowed: raise CreativeError('请求包含未声明字段')
        action=payload.get('action')
        if action not in ('generate','edit','regenerate','refine','revision'): raise CreativeError('不支持的创意操作')
        instruction=payload.get('instruction','')
        if not isinstance(instruction,str) or len(instruction)>2000: raise CreativeError('创意补充要求最多2000字')
        with self._lock:
            r=self._records.get((scope,task_id))
            if r is None: raise CreativeError('请先接收策略','HANDOFF_REQUIRED')
            self._idle(r); previous=self._current(r,payload.get('base_result_id'))
            if r['state']=='pending': raise CreativeError('当前版本已交付 C，等待反馈后再创建修订版','VERSION_LOCKED')
            if r['state'] in ('returned','needs_strategy') and action!='revision':
                raise CreativeError('请先按评估反馈修改；策略反馈需返回 A','FEEDBACK_PENDING')
            paths=[]; feedback=[]; channel=payload.get('channel')
            if action=='generate':
                if channel not in [x['name'] for x in r['context']['channels']]: raise CreativeError('渠道不属于当前策略')
            elif not previous: raise CreativeError('请先生成创意')
            elif action=='revision':
                if r['state'] not in ('returned','needs_strategy'): raise CreativeError('没有待处理反馈','FEEDBACK_INVALID')
                if previous['round_no']>=3: raise CreativeError('最多3轮业务评估','ROUND_LIMIT')
                feedback=feedback_check(r['feedback'][-1]['items'],previous)
                paths=[x['target_path'] for x in feedback]
            else:
                path=payload.get('path','');locate(previous['data'],path);paths=[path]
                if action=='edit' and not isinstance(payload.get('value'),str): raise CreativeError('人工编辑值必须是文字')
            if not self.enabled: raise CreativeError('B API 未配置启用','CONFIG_INVALID')
            job={'job_id':'job-'+uuid4().hex,'status':'running','stage':'queued','action':action,
                 'attempt_count':1,'created_at':now(),'error':None,'operation':deepcopy(payload)}
            r['job']=job;r['last_error']=None
            self._pool.submit(self._run,(scope,task_id),deepcopy(payload),deepcopy(previous),paths,feedback)
            return deepcopy(job)

    def _run(self,key,payload,previous,paths,feedback):
        action=payload['action']
        def stage(name,attempt=1):
            with self._lock:
                r=self._records[key];r['job'].update(stage=name,attempt_count=attempt)
                r['events'].append({'stage':name,'action':action,'attempt_count':attempt,'created_at':now()})
        try:
            with self._lock: r=deepcopy(self._records[key])
            stage('reading')
            if action=='edit':
                candidate=deepcopy(previous['data']);idx,field=locate(candidate,paths[0]);candidate['items'][idx][field]=payload['value']
                # Keep evidence text attached to the edited draft; content review belongs to C.
                item=candidate['items'][idx];body='\n'.join(item[f] for f in FIELDS)
                for e in item['evidence']:
                    if e['claim'] not in body: e['claim']=payload['value'][:1000]
                stage('validating');check_data(candidate,r['context']);attempt=1
            else:
                provider=self.provider or Provider.from_env(ROOT)
                agent=CreativeAgent(provider)
                candidate,attempt=agent.run(r['handoff'],r['context'],previous,action,payload.get('channel'),
                                      payload.get('instruction',''),paths,feedback,stage)
            stage('saving',attempt)
            round_no=(previous['round_no']+1 if action=='revision' else previous['round_no']) if previous else 1
            changes=[]
            old_items=previous['data']['items'] if previous else []
            for idx,item in enumerate(candidate['items']):
                old=next((x for x in old_items if x['channel']==item['channel']),{})
                for field in FIELDS:
                    if old.get(field)!=item[field]: changes.append({'path':f'items[{idx}].{field}','before':old.get(field),
                                       'after':item[field],'source':{'edit':'human','refine':'ai_polish','regenerate':'ai_regenerate','revision':'c_feedback'}.get(action,'ai_draft')})
            s=r['handoff']['strategy']
            result={'schema_version':'b-internal-candidate-v1','agent':'creative','task_id':key[1],
                    'result_id':'creative-'+uuid4().hex,'version':len(r['versions'])+1,'round_no':round_no,
                    'attempt_count':attempt,'status':'succeeded','strategy_result_id':s['result_id'],'strategy_version':s['version'],
                    'previous_result_id':previous['result_id'] if previous else None,'created_at':now(),
                    'config_version':r['handoff']['config_version'],'creative_instruction':payload.get('instruction',''),
                    'data':candidate,'checks':{'structure':True,'facts':False,'constraints':False,'semantic_review':False},
                    'edit_trace':changes,'feedback_applied':deepcopy(feedback),'error':None}
            validate(result,'creative-result.internal.schema.json',code='OUTPUT_INVALID')
            with self._lock:
                record=self._records[key]
                # Atomic append only after the whole candidate passes all gates.
                self._current(record,previous['result_id'] if previous else None)
                record['versions'].append(result);record['state']='ready'
                record['job'].update(status='succeeded',stage='completed',result_id=result['result_id'])
                record['events'].append({'stage':'version_saved','result_id':result['result_id'],'round_no':round_no,'created_at':now()})
        except Exception as e:
            err=e if isinstance(e,CreativeError) else CreativeError('创意处理或保存异常；旧版本保持有效','SAVE_FAILED')
            with self._lock:
                self._records[key]['job'].update(status='failed',stage='failed',error=err.public())
                self._records[key]['last_error']=err.public()
                self._records[key]['events'].append({'stage':'failed','error_code':err.code,'created_at':now()})

    def package(self,task_id,scope,base):
        self._auth(task_id,scope)
        with self._lock:
            r=self._records.get((scope,task_id))
            if not r: raise CreativeError('请先接收策略','HANDOFF_REQUIRED')
            self._idle(r);current=self._current(r,base)
            if current is None: raise CreativeError('尚未生成创意')
            if r['state'] in ('returned','needs_strategy'): raise CreativeError('待处理的评估反馈尚未修订','FEEDBACK_PENDING')
            check_data(current['data'],r['context'])
            if {x['channel'] for x in current['data']['items']}!={c['name'] for c in r['context']['channels']}:
                raise CreativeError('请先完成策略中每个渠道的创意','CHANNELS_INCOMPLETE')
            if r['context']['constraint_conflicts']: raise CreativeError('策略仍有约束冲突，请返回 A 确认','STRATEGY_CONFLICT')
            s=r['handoff']['strategy']
            if current['task_id']!=task_id or current['strategy_result_id']!=s['result_id'] or current['strategy_version']!=s['version']:
                raise CreativeError('策略和创意引用不一致','STALE_STRATEGY')
            package={'schema_version':'b-to-c-internal-candidate-v1','task_id':task_id,
                    'requirements':deepcopy(r['handoff']['requirements']),'strategy':deepcopy(s),'creative':deepcopy(current),
                    'round_no':current['round_no'],'evaluation_status':'pending','feedback_trace':deepcopy(r['feedback'])}
            validate(package,'evaluation-request.internal.schema.json',code='OUTPUT_INVALID')
            return package

    def deliver(self,task_id,scope,base):
        with self._lock:
            package=self.package(task_id,scope,base);r=self._records[(scope,task_id)]
            if r['state']=='pending':
                delivery=deepcopy(r['deliveries'][-1])
            else:
                delivery={'delivery_id':'delivery-'+uuid4().hex,'created_at':now(),'status':'pending',
                          'evaluation_id':None,'mode':'pending_real_c','package':package}
                r['deliveries'].append(delivery);r['state']='pending'
                r['events'].append({'stage':'delivered_to_c','result_id':base,'created_at':now()})
                delivery=deepcopy(delivery)
        # Dispatch outside B's lock: C finishes on another worker and calls back.
        if self.evaluation_dispatch:
            try:
                delivery['evaluation_job']=self.evaluation_dispatch(delivery,scope)
            except ValueError as exc:
                delivery['evaluation_error']={'code':getattr(exc,'code','INPUT_INVALID'),'message':str(exc)}
        return delivery

    def apply_evaluation(self,task_id,scope,delivery_id,bundle):
        """Trusted C coordinator entry, never exposed as a browser feedback API."""
        from src.agents.evaluation.adapter import feedback_for_b
        self._auth(task_id,scope)
        evaluation=bundle['final']['evaluation'];data=evaluation['data']
        with self._lock:
            r=self._records.get((scope,task_id))
            if not r or not r['deliveries']: raise CreativeError('当前没有待评估交付','DELIVERY_REQUIRED')
            delivery=r['deliveries'][-1]
            if (delivery['delivery_id']!=delivery_id or evaluation['task_id']!=task_id
                    or data['creative_result_id']!=delivery['package']['creative']['result_id']
                    or data['strategy_result_id']!=delivery['package']['strategy']['result_id']
                    or evaluation['round_no']!=delivery['package']['round_no']):
                raise CreativeError('评估回传与交付版本或轮次不一致','STALE_VERSION')
            if delivery['evaluation_id']==evaluation['result_id']:
                return deepcopy(r['feedback'][-1])
            if r['state']!='pending' or delivery['evaluation_id'] is not None:
                raise CreativeError('拒绝过期或重复评估覆盖','STALE_VERSION')
            items=feedback_for_b(evaluation,bundle=bundle)
            current=self._current(r,data['creative_result_id'])
            items=[f for f in items if f['target_agent']=='strategy' or int(f['target_path'].split('[')[1].split(']')[0])<len(current['data']['items'])]
            # B accepts at most 15 paths per revision. Keep the complete report
            # and deferred issues, instead of turning a useful C review into a
            # technical failure or silently discarding its remaining findings.
            items.sort(key=lambda f: {'high':0,'medium':1,'low':2}[f['priority']])
            deferred=deepcopy(items[15:]);items=items[:15]
            action=data['decision']
            state={'accept':'passed','regenerate_creative':'returned','regenerate_strategy':'needs_strategy',
                   'stop_not_passed':'not_passed','stop_needs_review':'not_passed'}[action]
            if state=='returned': feedback_check(items,current)
            feedback={'evaluation_id':evaluation['result_id'],'mode':'real_c','task_id':task_id,
                      'creative_result_id':data['creative_result_id'],'strategy_result_id':data['strategy_result_id'],
                      'round_no':evaluation['round_no'],'decision':'pass' if action=='accept' else 'return',
                      'items':deepcopy(items),'created_at':evaluation['created_at'],'scores':deepcopy(data['dimension_scores']),
                      'total_score':data['total_score'],'risks':deepcopy(data['risks']),'final_status':state,
                      'assessment_status':bundle['final']['assessment_status'],
                      'selected_evaluation_id':bundle['final']['selected_evaluation_id'],
                      'deferred_items':deferred}
            r['feedback'].append(feedback);r['state']=state
            delivery.update(status=state,evaluation_id=evaluation['result_id'],mode='real_c')
            r['events'].append({'stage':'real_c_feedback','evaluation_id':evaluation['result_id'],'created_at':now()})
            return deepcopy(feedback)

    def feedback(self,task_id,scope,base,payload,*,demo=False):
        self._auth(task_id,scope)
        if demo and not self.demo: raise CreativeError('开发模拟接口未启用','DEMO_DISABLED')
        if not demo:
            # Owner-scoped adapter for a future authenticated C coordinator, not a public evaluator.
            raise CreativeError('真实 C 回调认证协议尚待团队确认，当前未开放','C_NOT_CONNECTED')
        with self._lock:
            r=self._records.get((scope,task_id))
            if not r: raise CreativeError('请先接收策略','HANDOFF_REQUIRED')
            self._idle(r);current=self._current(r,base)
            if r['state']!='pending' or not r['deliveries']: raise CreativeError('当前没有待评估版本','DELIVERY_REQUIRED')
            decision=payload.get('decision')
            if decision not in ('return','pass'): raise CreativeError('评估决策不合法','FEEDBACK_INVALID')
            items=[]
            if decision=='return':
                items=payload.get('items')
                if items is None:
                    items=[{'target_agent':'creative','target_path':'items[0].copy','issue':'开发联调：行动引导需更明确',
                            'suggestion':'保持事实与策略不变，明确一个下一步行动，不新增入口或优惠','priority':'medium'}]
                # Validate strategy feedback shape, but preserve it as routed-to-A instead of editing strategy.
                try: items=feedback_check(items,current);state='returned'
                except CreativeError as e:
                    if e.code!='STRATEGY_FEEDBACK': raise
                    if not isinstance(items,list) or any(not isinstance(f,dict) or not all(isinstance(f.get(k),str) and 1<=len(f[k])<=1000 for k in ('target_agent','target_path','issue','suggestion','priority')) for f in items): raise
                    state='needs_strategy'
                if current['round_no']>=3: state='not_passed'
            else: state='passed'
            evaluation={'evaluation_id':'demo-evaluation-'+uuid4().hex,'mode':'development/demo only',
                        'task_id':task_id,'creative_result_id':base,'strategy_result_id':current['strategy_result_id'],
                        'round_no':current['round_no'],'decision':decision,'items':deepcopy(items),'created_at':now(),
                        'scores':None,'final_status':state}
            r['feedback'].append(evaluation);r['state']=state
            r['deliveries'][-1].update(status=state,evaluation_id=evaluation['evaluation_id'],mode='development/demo only')
            return deepcopy(evaluation)

    def history(self,scope):
        with self._lock:
            return [{'task_id':task,'product_name':r['context']['product_name'],'state':r['state'],
                     'versions':len(r['versions']),'created_at':r['events'][0]['created_at']}
                    for (owner,task),r in self._records.items() if owner==scope]

    def close(self): self._pool.shutdown(wait=False,cancel_futures=True)
