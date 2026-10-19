"""Use A's actual public API rather than a self-authored strategy response."""
from copy import deepcopy
import unittest
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.service import StrategyAgent
from src.agents.strategy.model_clients import RuleBasedModelClient
from src.agents.evaluation import evaluate_bundle
from src.agents.evaluation.examples import make_source


class StrategyEvaluationHandoffTests(unittest.TestCase):
    def test_strategy_change_order_is_consumable_by_existing_A_service(self):
        from src.agents.evaluation.adapter import strategy_handoff
        source=make_source(0,'boundary');request=source['rounds'][0]['request']
        initial=deepcopy(request);initial.update(agent='strategy',strategy=None,creative=None)
        agent=StrategyAgent(RuleBasedModelClient())
        strategy=agent.generate(StrategyRequest.from_dict(initial)).to_dict()
        request['strategy']=strategy
        request['creative']['data']['strategy_result_id']=strategy['result_id']
        item=request['creative']['data']['items'][0]
        request['creative']['data']['items']=[{**deepcopy(item),'channel':c['name']} for c in strategy['data']['channels']]
        draft=source['rounds'][0]['draft']
        for dimension in draft['dimension_scores'].values():dimension['score']=70
        draft['feedback']=[{'target_agent':target,'target_path':position,'issue':'需调整表达','suggestion':'依据原始事实调整','priority':'medium'}
                           for target,position in [('strategy','strategy.positioning'),('creative','creative.items[0].copy')]]
        bundle=evaluate_bundle(source);handoff=strategy_handoff(bundle)
        self.assertEqual({f['target_agent'] for f in handoff['strategy_revision_request']['feedback']},{'strategy'})
        self.assertEqual(len(handoff['pending_creative_feedback']),1)
        revised=agent.generate(StrategyRequest.from_dict(handoff['strategy_revision_request'])).to_dict()
        self.assertEqual(revised['status'],'succeeded',revised.get('error'))
        self.assertEqual(revised['version'],strategy['version']+1)
        self.assertEqual(agent.history(request['task_id'])[0],strategy)

    def test_published_strategy_response_consumed_without_mutation(self):
        source = make_source(0, "boundary")
        request = source["rounds"][0]["request"]
        strategy_request = deepcopy(request)
        strategy_request.update(agent="strategy", strategy=None, creative=None)
        agent = StrategyAgent(RuleBasedModelClient())
        response = agent.generate(StrategyRequest.from_dict(strategy_request)).to_dict()
        self.assertEqual(response["status"], "succeeded")
        original = deepcopy(response)
        request["strategy"] = response
        request["creative"]["data"]["strategy_result_id"] = response["result_id"]
        template = request["creative"]["data"]["items"][0]
        request["creative"]["data"]["items"] = [{**deepcopy(template), "channel": channel["name"]} for channel in response["data"]["channels"]]
        result = evaluate_bundle(source)
        self.assertEqual(result["final"]["assessment_status"], "passed")
        self.assertEqual(response, original)
        self.assertEqual(result["records"][0]["outcome"]["evaluation"]["data"]["strategy_result_id"], response["result_id"])
