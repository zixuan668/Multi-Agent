"""Consume B's documented candidate schemas without importing B internals."""
from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .contracts import ContractError

ROOT = Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def validators():
    files = list((ROOT / 'packages/contracts').glob('*.json'))
    files += list((ROOT / 'src/agents/creative/schemas').glob('*.json'))
    files += list((ROOT / 'src/agents/evaluation/schemas').glob('*.json'))
    schemas = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in files}
    registry = Registry().with_resources((s['$id'], Resource.from_contents(s)) for s in schemas.values())
    return {name: Draft202012Validator(s, registry=registry, format_checker=FormatChecker())
            for name, s in schemas.items()}


def validate_candidate(value, schema):
    errors = list(validators()[schema].iter_errors(value))
    if errors:
        first = errors[0]
        # Do not echo rejected content or arbitrary model output into errors.
        raise ContractError('.'.join(map(str, first.absolute_path)) or 'package',
                            '不符合B交付契约：' + str(first.validator))


def validate_creative(creative, strategy, task_id, round_no):
    validate_candidate(creative, 'creative-result.internal.schema.json')
    if (creative['task_id'] != task_id or creative['round_no'] != round_no
            or creative['strategy_result_id'] != strategy['result_id']
            or creative['strategy_version'] != strategy['version']):
        raise ContractError('creative', '任务、轮次或策略引用不一致')
    actual = [i['channel'] for i in creative['data']['items']]
    expected = [c['name'] for c in strategy['data']['channels']]
    if len(set(actual)) != len(actual) or sorted(actual) != sorted(expected):
        raise ContractError('creative.data.items', '必须完整覆盖策略渠道且不能重复')


def from_b_package(package, config_version):
    validate_candidate(package, 'evaluation-request.internal.schema.json')
    task_id = package['task_id']
    if package['strategy']['task_id'] != task_id:
        raise ContractError('strategy.task_id', '跨任务策略不可评估')
    validate_creative(package['creative'], package['strategy'], task_id, package['round_no'])
    return {'schema_version': '1.0', 'task_id': task_id, 'agent': 'evaluation',
            'round_no': package['round_no'], 'attempt_count': 1,
            'requirements': deepcopy(package['requirements']), 'strategy': deepcopy(package['strategy']),
            'creative': deepcopy(package['creative']), 'feedback': [], 'previous_result': None,
            'config_version': config_version}


def feedback_for_b(evaluation, *, bundle=None):
    """B edits only four text fields; aggregate issues instead of dropping duplicates."""
    grouped = {}
    issues=deepcopy(evaluation['data']['feedback'])
    if bundle and evaluation['data']['decision']=='regenerate_creative':
        import re
        current=bundle['records'][-1]['request']['creative']['data']['items']
        sources={r['outcome']['evaluation']['result_id']:r['request']['creative']['data']['items'] for r in bundle['records']}
        issues=[]
        for old in bundle.get('feedback_status',evaluation['data']['feedback']):
            if old['resolved'] or old['target_agent']!='creative':continue
            f=deepcopy(old);match=re.match(r'creative\.(?:data\.)?items\[(\d+)\]\.(.+)',f['target_path'])
            source=sources.get(f['evaluation_id'])
            if match and source and int(match[1])<len(source):
                channel=source[int(match[1])]['channel']
                index=next((i for i,item in enumerate(current) if item['channel']==channel),None)
                # A removed channel has no editable field in this B version.
                # Its original feedback remains in C's immutable report/ledger.
                if index is None:continue
                f['target_path']=f'creative.items[{index}].{match[2]}'
            issues.append(f)
    for f in issues:
        path = f['target_path'].replace('.data.', '.', 1)
        if f['target_agent'] == 'creative':
            import re
            match = re.match(r'creative\.items\[(\d+)\]\.(\w+)', path)
            if match:
                field = match[2] if match[2] in ('copy', 'slogan', 'poster_concept', 'video_script') else 'copy'
                paths = [f'items[{match[1]}].{field}']
            else:
                paths = [f'items[{i}].copy' for i in range(5)]
        else:
            paths = [path]
        for path in paths:
            key = (f['target_agent'], path)
            if key in grouped:
                item = grouped[key]
                item['issue'] = (item['issue'] + '；' + f['issue'])[:1000]
                item['suggestion'] = (item['suggestion'] + '；' + f['suggestion'])[:1000]
                if f['priority'] == 'high': item['priority'] = 'high'
            else:
                grouped[key] = {k: f[k] for k in ('target_agent', 'issue', 'suggestion', 'priority')}
                grouped[key]['target_path'] = path
    return list(grouped.values())


def strategy_handoff(bundle):
    """A service-layer request, not an unauthenticated public optimize route."""
    from src.agents.strategy.models import StrategyRequest
    record=bundle['records'][-1]
    r=record['request'];evaluation=record['outcome']['evaluation']
    if record['outcome']['decision']!='regenerate_strategy' or r['round_no']>=bundle['config_snapshot']['max_rounds']:
        raise ContractError('decision','当前没有可继续的策略修订请求')
    ledger=bundle.get('feedback_status',r['feedback']+evaluation['data']['feedback'])
    unresolved=[{k:deepcopy(v) for k,v in f.items() if k!='resolved_by_evaluation_id'} for f in ledger if not f['resolved']]
    request={'schema_version':'1.0','task_id':r['task_id'],'agent':'strategy',
             'round_no':r['round_no']+1,'attempt_count':1,'requirements':deepcopy(r['requirements']),
             'strategy':None,'creative':None,'feedback':[f for f in unresolved if f['target_agent']=='strategy'],
             'previous_result':deepcopy(r['strategy']),
             'config_version':r['creative'].get('config_version',r['config_version'])}
    StrategyRequest.from_dict(request)
    return {'schema_version':'c-to-a-feedback-candidate-v1','task_id':r['task_id'],
            'strategy_revision_request':request,'creative':deepcopy(r['creative']),
            'evaluation':deepcopy(evaluation),'unresolved_feedback':unresolved,
            'strategy_feedback':[deepcopy(f) for f in unresolved if f['target_agent']=='strategy'],
            'pending_creative_feedback':[deepcopy(f) for f in unresolved if f['target_agent']=='creative'],
            'evaluation_config_snapshot':deepcopy(bundle['config_snapshot']),
            'next_action':'A更新策略，再由B生成引用新策略的创意，最后交C复评'}
