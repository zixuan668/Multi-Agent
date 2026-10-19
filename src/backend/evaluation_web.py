"""C routes share the existing session and task ownership boundary."""
import json
from urllib.parse import urlparse

from src.agents.evaluation.contracts import ContractError
from src.agents.evaluation.examples import products, SCENARIOS, make_source
from src.agents.evaluation.provider import EvaluationError
from src.agents.evaluation.service import evaluate_bundle
from src.agents.creative.errors import CreativeError
from src.agents.strategy.errors import StrategyAgentError


def dispatch(handler, app, method):
    parsed=urlparse(handler.path);path=parsed.path
    if path in ('/evaluation','/evaluation/') and method=='GET':
        handler.path='/evaluation/index.html';return False
    if not (path.startswith('/api/evaluation/') or (path.startswith('/api/tasks/') and '/evaluation/' in path)):
        return False
    try:
        if method=='GET' and path=='/api/evaluation/scenarios':
            value={'products':[{'id':i,'name':p['requirements']['product_name']} for i,p in enumerate(products())],
                   'scenarios':SCENARIOS,'mode':'live_available' if app.evaluation.enabled else 'offline'}
        elif method=='GET' and path=='/api/evaluation/sample':
            from urllib.parse import parse_qs
            query=parse_qs(parsed.query)
            value=make_source(int(query.get('product',['0'])[0]),query.get('scenario',['improve'])[0])
        else:
            if method=='POST':
                length=int(handler.headers.get('Content-Length','0'))
                if handler.headers.get_content_type()!='application/json' or not 0<length<=2_000_000:
                    raise ContractError('body','需要不超过2MB的JSON对象')
                raw=handler.rfile.read(length)
                # Drain the bounded request before responding: unread bytes can
                # cause TCP reset instead of the intended 403 on Windows.
                origin=handler.headers.get('Origin')
                if origin and origin!='http://'+handler.headers.get('Host',''):
                    handler._json(403,{'error':{'code':'ACCESS_DENIED','message':'只接受同源评估请求'}});return True
                body=json.loads(raw.decode('utf-8'),parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
                if not isinstance(body,dict): raise ContractError('body','须为对象')
            if method=='POST' and path=='/api/evaluation/replay':
                value={'data':evaluate_bundle(body)}
            else:
                scope=app.scope(handler._token())
                parts=path.strip('/').split('/')
                if len(parts)!=5: raise ContractError('path','评估接口不存在')
                task_id,operation=parts[2],parts[4]
                app.tasks.get(task_id,scope)
                if method=='GET' and operation=='state': value=app.evaluation.public_get(task_id,scope)
                elif method=='GET' and operation=='strategy-handoff':
                    from src.agents.evaluation.adapter import strategy_handoff
                    state=app.evaluation.public_get(task_id,scope)
                    if not state['bundle'] or not state['job'] or state['job']['status']!='succeeded':
                        raise ContractError('evaluation','策略反馈尚未就绪')
                    value=strategy_handoff(state['bundle'])
                elif method=='POST' and operation=='operations':
                    if set(body)!={'base_result_id'}: raise ContractError('body','仅接受当前创意版本引用')
                    if not app.evaluation.enabled: raise EvaluationError('CONFIG_INVALID','C真实模型评估未启用')
                    delivery=app.creative.deliver(task_id,scope,body['base_result_id'])
                    if delivery.get('evaluation_error'):
                        raise EvaluationError(delivery['evaluation_error']['code'],delivery['evaluation_error']['message'])
                    value=app.evaluation.public_get(task_id,scope)
                else: raise ContractError('path','评估接口不存在或请求方法不支持')
        handler._json(202 if method=='POST' and path.endswith('/operations') else 200,value)
    except (EvaluationError,CreativeError) as exc:
        handler._json(400,{'error':exc.public()})
    except StrategyAgentError as exc: handler._error(exc)
    except (ValueError,TypeError,KeyError,UnicodeError,IndexError):
        handler._json(400,{'error':{'code':'INPUT_INVALID','message':'评估输入、字段或版本不合法'}})
    return True
