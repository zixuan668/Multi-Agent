"""Explicit small live A/B/C regression. No mock is used by this runner.

Run against a server started with real A/B/C providers. Inputs are the public
fictional page examples. A strategy-feedback branch stops with an A handoff;
it is never counted as a passing closed loop.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
from pathlib import Path
import subprocess
import time
from urllib import request,error

ROOT=Path(__file__).resolve().parents[1]


def examples():
    script="const b=require('./web/brief.js');console.log(JSON.stringify(require('./web/examples.js').templates.map(t=>({id:t.id,requirements:b.payload({...b.defaults,...t.values})}))));"
    return json.loads(subprocess.check_output(['node','-e',script],cwd=ROOT,encoding='utf-8'))


def execute(base,case,output):
    client=request.build_opener(request.HTTPCookieProcessor(CookieJar()))
    def api(path,body=None):
        req=request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        try:
            with client.open(req,timeout=10) as response:return json.load(response)
        except error.HTTPError as exc:
            try:value=json.load(exc)
            except Exception:value={'error':{'code':'HTTP_ERROR','message':'HTTP '+str(exc.code)}}
            finally:exc.close()
            raise RuntimeError(json.dumps(value,ensure_ascii=False)) from None
    def wait(path,done):
        until=time.monotonic()+1200
        while time.monotonic()<until:
            value=api(path)
            if done(value):return value
            time.sleep(.7)
        raise TimeoutError('logical task timeout')
    started=time.monotonic()
    record={'case_id':case['id'],'source':'真实A/B/C模型调用；输入为公开虚构演示简报',
            'executed_at':datetime.now(timezone.utc).isoformat(),'requirements':case['requirements']}
    try:
        api('/api/session');receipt=api('/api/tasks',case['requirements']);task=receipt['task_id'];prefix='/api/tasks/'+task
        record['task_id']=task
        a=wait(prefix,lambda v:v['status'] in ('completed','failed'))
        record['strategy']=a.get('result')
        if a['status']!='completed':raise RuntimeError(json.dumps(a.get('error'),ensure_ascii=False))
        api(prefix+'/creative/accept',{});current=None
        for channel in a['result']['data']['channels']:
            api(prefix+'/creative/operations',{'action':'generate','channel':channel['name'],'base_result_id':current})
            b=wait(prefix+'/creative/state',lambda v:v['job']['status']!='running')
            if b['job']['status']!='succeeded':raise RuntimeError(json.dumps(b['job']['error'],ensure_ascii=False))
            current=b['versions'][-1]['result_id']
        for _ in range(3):
            receipt=api(prefix+'/evaluation/operations',{'base_result_id':current})
            c=wait(prefix+'/evaluation/state',lambda v:v['job'] and v['job']['status']!='running')
            record['evaluation_state']=c
            if c['job']['status']!='succeeded':raise RuntimeError(json.dumps(c['job']['error'],ensure_ascii=False))
            decision=c['bundle']['final']['decision']
            if decision!='regenerate_creative':break
            api(prefix+'/creative/operations',{'action':'revision','base_result_id':current})
            b=wait(prefix+'/creative/state',lambda v:v['job']['status']!='running')
            if b['job']['status']!='succeeded':raise RuntimeError(json.dumps(b['job']['error'],ensure_ascii=False))
            current=b['versions'][-1]['result_id']
        record['creative_state']=api(prefix+'/creative/state')
        final=c['bundle']['final']
        record.update(result='handoff_to_A' if final['decision']=='regenerate_strategy' else final['assessment_status'],
                      score=final['evaluation']['data']['total_score'],rounds=final['iteration_count'])
    except Exception as exc:
        record.update(result='technical_failure',error=str(exc)[:1200])
    record['elapsed_seconds']=round(time.monotonic()-started,2)
    (output/(case['id']+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    return {k:record.get(k) for k in ('case_id','task_id','result','score','rounds','elapsed_seconds','error')}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:8766')
    p.add_argument('--case-ids',nargs='*')
    p.add_argument('--output',type=Path,default=ROOT/'artifacts/evaluation-acceptance')
    p.add_argument('--workers',type=int,choices=(1,2),default=2)
    args=p.parse_args()
    if not args.url.startswith(('http://127.0.0.1:','http://localhost:')):p.error('只允许本机联调服务')
    args.output.mkdir(parents=True,exist_ok=True)
    cases=[c for c in examples() if not args.case_ids or c['id'] in args.case_ids]
    if not cases:p.error('没有匹配的公开样例')
    print('Live cases: '+', '.join(c['id'] for c in cases),flush=True)
    results=[]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in as_completed([pool.submit(execute,args.url,c,args.output) for c in cases]):
            results.append(future.result());print(json.dumps(results[-1],ensure_ascii=False),flush=True)
    (args.output/'summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    return 1 if any(r['result']=='technical_failure' for r in results) else 0


if __name__=='__main__':raise SystemExit(main())
