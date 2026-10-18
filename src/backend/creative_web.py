"""Additive B routes delegated from the existing HTTP handler."""
import json
from urllib.parse import urlparse,parse_qs
from src.agents.creative.errors import CreativeError
from src.agents.strategy.errors import StrategyAgentError

def dispatch(handler,app,method):
    path=urlparse(handler.path).path
    if method=='GET' and path in ('/creative','/creative/'):
        handler.path='/creative.html';return False
    if not (path=='/api/creative/history' or (path.startswith('/api/tasks/') and '/creative/' in path)):
        return False
    try:
        scope=app.scope(handler._token())
        if path=='/api/creative/history':
            if method!='GET': raise CreativeError('请求方法不支持')
            value={'items':app.creative.history(scope),'storage':'process-memory'}
        else:
            parts=path.strip('/').split('/')
            if len(parts)!=5: raise CreativeError('B API 路径不支持')
            task_id,operation=parts[2],parts[4]
            if method=='GET':
                if operation=='handoff': value=app.creative.gate(task_id,scope)
                elif operation in ('state','history'): value=app.creative.get(task_id,scope)
                elif operation=='package':
                    base=parse_qs(urlparse(handler.path).query).get('result_id',[None])[0]
                    value=app.creative.package(task_id,scope,base)
                else: raise CreativeError('B API 路径不支持')
            else:
                length=int(handler.headers.get('Content-Length','0'))
                if handler.headers.get_content_type()!='application/json' or not 0<length<=100000:
                    raise CreativeError('需要大小合法的 JSON 请求')
                body=json.loads(handler.rfile.read(length).decode('utf-8'))
                if not isinstance(body,dict): raise CreativeError('请求必须是对象')
                if operation=='accept':
                    if body: raise CreativeError('接收入口不接受上游覆盖字段')
                    value=app.creative.accept(task_id,scope)
                elif operation=='operations': value=app.creative.start(task_id,scope,body)
                elif operation=='delivery':
                    if set(body)!={'base_result_id'}: raise CreativeError('交付只接受当前版本引用')
                    value=app.creative.deliver(task_id,scope,body['base_result_id'])
                elif operation in ('demo-feedback','feedback'):
                    if set(body)-{'base_result_id','decision','items'}: raise CreativeError('反馈包含未声明字段')
                    value=app.creative.feedback(task_id,scope,body.get('base_result_id'),body,demo=operation=='demo-feedback')
                else: raise CreativeError('B API 路径不支持')
        handler._json(202 if method=='POST' and path.endswith('/operations') else 200,value)
    except CreativeError as e:
        handler._json(400,{'status':'failed','error':e.public()})
    except StrategyAgentError as e: handler._error(e)
    except (ValueError,UnicodeError):
        handler._json(400,{'status':'failed','error':{'code':'INPUT_INVALID','message':'请求无法解析'}})
    return True
