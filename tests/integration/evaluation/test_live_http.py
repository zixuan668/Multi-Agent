import json
from http.cookiejar import CookieJar
import threading
import time
import unittest
from urllib import request,error

from src.backend.strategy_web import create_server
from tests.unit.test_creative_v6 import MockProvider,fixture
from tests.unit.evaluation.test_live import Scorer


class EvaluationHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scorer=Scorer([70,86])
        cls.server=create_server('127.0.0.1',0,provider='offline',creative_client=MockProvider(),evaluation_client=cls.scorer)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def setUp(self):
        self.client=request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        self.other=request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        self.api('/api/session');self.api('/api/session',client=self.other)

    def api(self,path,body=None,client=None,headers=None):
        req=request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                            headers=headers or {'Content-Type':'application/json'})
        with (client or self.client).open(req,timeout=3) as r:return json.load(r)

    def wait(self,path,done):
        until=time.monotonic()+5
        while time.monotonic()<until:
            value=self.api(path)
            if done(value):return value
            time.sleep(.01)
        self.fail('HTTP job timeout')

    def test_real_routes_return_feedback_and_isolate_owners(self):
        receipt=self.api('/api/tasks',fixture()['requirements']);task=receipt['task_id'];p='/api/tasks/'+task
        a=self.wait(p,lambda v:v['status']=='completed');self.api(p+'/creative/accept',{})
        current=None
        for channel in a['result']['data']['channels']:
            self.api(p+'/creative/operations',{'action':'generate','base_result_id':current,'channel':channel['name']})
            b=self.wait(p+'/creative/state',lambda v:v['job']['status']!='running');current=b['versions'][-1]['result_id']
        delivery=self.api(p+'/creative/delivery',{'base_result_id':current})
        self.assertIsNotNone(delivery.get('evaluation_job'),delivery)
        c=self.wait(p+'/evaluation/state',lambda v:v['job'] and v['job']['status']!='running')
        self.assertEqual(c['job']['status'],'succeeded',c['job'])
        self.assertEqual(c['bundle']['mode'],'live')
        self.assertEqual(self.api(p+'/creative/state')['state'],'returned')
        for suffix in ('/evaluation/state','/creative/state'):
            with self.assertRaises(error.HTTPError) as ctx:self.api(p+suffix,client=self.other)
            self.assertEqual(ctx.exception.code,403)
        with self.assertRaises(error.HTTPError) as ctx:self.api(p+'/evaluation/operations',{'base_result_id':current,'scores':99})
        self.assertEqual(ctx.exception.code,400)
        with self.assertRaises(error.HTTPError) as ctx:self.api(p+'/evaluation/operations',{'base_result_id':current},headers={'Content-Type':'application/json','Origin':'https://evil.example'})
        self.assertEqual(ctx.exception.code,403)
        with self.assertRaises(error.HTTPError) as ctx:self.api(p+'/creative/feedback',{'base_result_id':current,'decision':'pass'})
        self.assertEqual(ctx.exception.code,400)
        self.assertNotIn('unit-secret',json.dumps(c))

    def test_assets_and_offline_replay_still_work(self):
        for path in ('/evaluation/','/evaluation/app.js','/evaluation/style.css'):
            with self.client.open(self.base+path) as r:self.assertEqual(r.status,200)
        from src.agents.evaluation.examples import make_source
        self.assertEqual(self.api('/api/evaluation/replay',make_source())['data']['final']['assessment_status'],'passed')


if __name__=='__main__':unittest.main()
