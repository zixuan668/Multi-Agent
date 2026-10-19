"""Owner-scoped C jobs. B delivery is the only source of authoritative input.

No HTTP endpoint accepts client-supplied scores or evaluation callbacks.
Technical retries never append business rounds; successful history is immutable.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading
import time
from uuid import uuid4

from .adapter import from_b_package, validate_candidate
from .contracts import ContractError, validate_draft, validate_handoff
from .provider import EvaluationConfig, EvaluationError, EvaluationProvider, PROMPT_VERSION
from .service import evaluate_bundle, now


class EvaluationWorkspace:
    def __init__(self, creative, *, provider=None, enabled=False, sleep=time.sleep):
        self.creative, self.provider, self.enabled = creative, provider, enabled or provider is not None
        self.sleep = sleep
        self._records, self._lock = {}, threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=5, thread_name_prefix='evaluation')

    def get(self, task_id, scope):
        return self.public_get(task_id, scope)

    def enqueue(self, delivery, scope):
        if not self.enabled: return None
        package = delivery['package']
        key = (scope, package['task_id'])
        with self._lock:
            previous = self._records.get(key)
            if previous and previous['job']['creative_result_id'] == package['creative']['result_id']:
                return deepcopy(previous['job'])
            if previous and previous['job']['status'] == 'running':
                raise EvaluationError('BUSY', '当前评估尚未结束')
            provider = self.provider or EvaluationProvider(EvaluationConfig.from_env())
            snapshot=getattr(provider,'snapshot',provider.config.snapshot)()
            config = previous['config_snapshot'] if previous else snapshot
            if previous and snapshot != config:
                # Existing task keeps its model and configuration instance.
                provider = previous['_provider']
            req = from_b_package(package, config['config_version'])
            rows = deepcopy(previous['_rows']) if previous else []
            if req['round_no'] != len(rows) + 1 or req['round_no'] > config['max_rounds']:
                raise EvaluationError('ROUND_LIMIT', 'C仅接受连续有效评估轮次，最多三轮')
            if previous and previous['bundle'] and previous['bundle']['final']['task_status'] == 'completed':
                raise EvaluationError('ROUND_LIMIT', '评估已经终止')
            if previous and previous['bundle']:
                req['previous_result'] = deepcopy(previous['bundle']['final']['evaluation'])
                ledger=previous['bundle'].get('feedback_status')
                if ledger is None:ledger=[f for r in previous['bundle']['records'] for f in r['outcome']['evaluation']['data']['feedback']]
                req['feedback'] = [{k:deepcopy(v) for k,v in f.items() if k!='resolved_by_evaluation_id'} for f in ledger if not f['resolved']]
            # Validate history before paying for model work; no synthetic scores.
            validate_handoff(req)
            if previous and previous['bundle']:
                old=previous['bundle']['records'][-1]
                first=previous['bundle']['records'][0]['request']
                if req['requirements']!=first['requirements']:
                    raise EvaluationError('STALE_VERSION','原始需求不能在同一评估任务内变更')
                if (req['creative']['result_id']==old['request']['creative']['result_id']
                        or req['creative']['version']<=old['request']['creative']['version']):
                    raise EvaluationError('STALE_VERSION','新创意标识和版本须递增')
                if old['outcome']['decision']=='regenerate_creative' and req['strategy']!=old['request']['strategy']:
                    raise EvaluationError('STALE_VERSION','仅创意反馈须保留原策略')
                if old['outcome']['decision']=='regenerate_strategy' and (
                        req['strategy']['result_id']==old['request']['strategy']['result_id']
                        or req['strategy']['version']<=old['request']['strategy']['version']):
                    raise EvaluationError('STRATEGY_FEEDBACK','策略反馈必须先由A提供新策略')
            job = {'job_id': 'evaluation-job-' + uuid4().hex, 'status': 'running', 'stage': 'queued',
                   'attempt_count': 0, 'round_no': req['round_no'], 'created_at': now(),
                   'creative_result_id': req['creative']['result_id'], 'delivery_id': delivery['delivery_id'], 'error': None}
            record = {'job': job, 'bundle': deepcopy(previous['bundle']) if previous else None,
                      'events': deepcopy(previous['events']) if previous else [], 'config_snapshot': config,
                      'storage': 'process-memory', '_rows': rows, '_provider': provider}
            self._records[key] = record
            self._pool.submit(self._run, key, req, deepcopy(delivery), provider)
            return deepcopy(job)

    def public_get(self, task_id, scope):
        # Provider objects carry credentials and must never be serialized.
        self.creative.tasks.get(task_id, scope)
        with self._lock:
            r = self._records.get((scope, task_id))
            return deepcopy({k: v for k, v in r.items() if not k.startswith('_')}) if r else {
                'job': None, 'bundle': None, 'events': [], 'storage': 'process-memory'}

    def _event(self, key, stage, attempt, summary):
        with self._lock:
            r = self._records[key]
            r['job'].update(stage=stage, attempt_count=attempt)
            r['events'].append({'time': now(), 'agent': 'evaluation', 'status': stage,
                                'round_no': r['job']['round_no'], 'attempt_count': attempt, 'summary': summary})

    def _run(self, key, req, delivery, provider):
        try:
            with self._lock:
                record = self._records[key]
                config, rows = deepcopy(record['config_snapshot']), deepcopy(record['_rows'])
                prior = deepcopy(record['bundle']['records']) if record['bundle'] else []
            payload = {'request': req, 'rubric': {'pass_threshold': config['pass_threshold'],
                        'dimensions': 'fixed-five-equal-weight'}, 'repair_issues': []}
            for attempt in range(1, config['max_attempts'] + 1):
                self._event(key, 'generating', attempt, '正在核对原始事实、全部渠道与四类创意，生成五维评分及反馈。')
                try:
                    draft = validate_draft(provider.call(payload), req)
                    req['attempt_count'] = attempt
                    source = {'label': '真实模型评估', 'config_snapshot': config,
                              'rounds': rows + [{'request': req, 'draft': draft}]}
                    bundle = evaluate_bundle(source, prior_records=prior)
                    validate_candidate(bundle['final']['evaluation'],'evaluation-result.internal.schema.json')
                    break
                except (EvaluationError, ContractError) as exc:
                    failure = exc if isinstance(exc, EvaluationError) else EvaluationError(
                        'OUTPUT_INVALID', '模型评分、反馈或定位字段不符合C契约', True)
                    if not failure.retryable or attempt == config['max_attempts']: raise failure
                    payload['repair_issues'] = [({'field':exc.field,'message':'请修正该字段的类型、范围或引用，只输出合法json。'}
                                                 if isinstance(exc,ContractError) else {'field':None,'message':'请返回完整合法的评分json。'})]
                    self._event(key, 'retrying', attempt, f'{failure.code}，将在{attempt}秒后进行技术重试；业务轮次不增加。')
                    self.sleep(attempt)
            bundle.update(mode='live', source='服务端真实模型评分 + 确定性风险与决策规则')
            bundle['model_metadata'] = {'model': provider.config.model, 'prompt_version': PROMPT_VERSION}
            self._event(key, 'applying_feedback', attempt, '评分完成，正在将绑定当前版本的反馈交回B。')
            # Trusted in-process callback; the public /creative/feedback route stays closed.
            self.creative.apply_evaluation(key[1], key[0], delivery['delivery_id'], bundle)
            with self._lock:
                record = self._records[key]
                record.update(bundle=bundle, _rows=deepcopy(source['rounds']))
                record['job'].update(status='succeeded', stage='completed', result_id=bundle['final']['evaluation']['result_id'])
            self._event(key, 'completed', attempt, '评估与反馈已保存；可查看报告或依据反馈修订。')
        except Exception as exc:
            failure = exc if isinstance(exc, EvaluationError) else EvaluationError('EVALUATION_FAILED', '评估未完成；保留已有结果，请检查服务端配置或联调状态')
            with self._lock:
                self._records[key]['job'].update(status='failed', stage='failed', error=failure.public())
                bundle=self._records[key]['bundle']
                if bundle:
                    bundle['final'].update(task_status='failed',termination_reason='technical_error',selected_evaluation_id=None)
                    bundle['selected_index']=None
            self._event(key, 'failed', self._records[key]['job']['attempt_count'], str(failure))

    def close(self):
        self._pool.shutdown(wait=True, cancel_futures=True)
