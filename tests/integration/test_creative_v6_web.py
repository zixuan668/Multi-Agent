import json
import threading
import time
import unittest
from urllib import request,error
from http.cookiejar import CookieJar
from src.backend.strategy_web import create_server
from tests.unit.test_creative_v6 import MockProvider,fixture

class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.provider=MockProvider();cls.server=create_server('127.0.0.1',0,provider='offline',creative_client=cls.provider,creative_demo=True)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start();cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def setUp(self):
        self.client=request.build_opener(request.HTTPCookieProcessor(CookieJar()));self.other=request.build_opener(request.HTTPCookieProcessor(CookieJar()))
        self.client.open(self.base+'/api/session').close();self.other.open(self.base+'/api/session').close()
    def api(self,path,body=None,client=None):
        req=request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json'})
        with (client or self.client).open(req,timeout=3) as r:return json.load(r)
    def test_full_real_routes_and_owner_gates(self):
        receipt=self.api('/api/tasks',fixture()['requirements']);t=receipt['task_id']
        for _ in range(100):
            task=self.api('/api/tasks/'+t)
            if task['status']=='completed':break
            time.sleep(.01)
        base='/api/tasks/'+t+'/creative/'
        self.assertEqual(self.api(base+'handoff')['handoff']['task_id'],t)
        self.api(base+'accept',{})
        self.api(base+'operations',{'action':'generate','channel':task['result']['data']['channels'][0]['name'],'base_result_id':None})
        for _ in range(200):
            state=self.api(base+'state')
            if state['job']['status']!='running':break
            time.sleep(.01)
        self.assertEqual(state['job']['status'],'succeeded',state['job']);v=state['versions'][-1]
        self.assertEqual(self.api(base+'package?result_id='+v['result_id'])['creative'],v)
        delivery=self.api(base+'delivery',{'base_result_id':v['result_id']});self.assertEqual(delivery['status'],'pending')
        feedback=self.api(base+'demo-feedback',{'base_result_id':v['result_id'],'decision':'return'});self.assertEqual(feedback['round_no'],1)
        for op,body in [('handoff',None),('state',None),('history',None),('package?result_id='+v['result_id'],None),('accept',{}),('operations',{}),('delivery',{'base_result_id':v['result_id']}),('demo-feedback',{'base_result_id':v['result_id'],'decision':'pass'})]:
            with self.assertRaises(error.HTTPError) as e:self.api(base+op,body,self.other)
            self.assertEqual(e.exception.code,403,op)
        self.assertEqual(self.api('/api/creative/history',client=self.other)['items'],[])
    def test_assets_no_secret_or_inline_demo(self):
        for path in ['/workspace','/creative','/creative.css','/creative.js','/creative-api.js','/creative-handoff.html']:
            with self.client.open(self.base+path) as r:
                body=r.read().decode();self.assertIn("default-src 'self'",r.headers['Content-Security-Policy'])
                if path=='/creative':
                    self.assertNotIn('creative-demo-v1',body);self.assertNotIn('guided-milk-owned',body);self.assertNotIn('<iframe',body)
        for path in ['/.env','/.env.creative']:
            with self.assertRaises(error.HTTPError):self.client.open(self.base+path)

if __name__=='__main__':unittest.main()
