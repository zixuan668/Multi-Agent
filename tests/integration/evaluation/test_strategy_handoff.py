"""Use A's actual public API rather than a self-authored strategy response."""
from copy import deepcopy
import unittest
from src.agents.strategy.models import StrategyRequest
from src.agents.strategy.service import StrategyAgent
from src.agents.strategy.model_clients import RuleBasedModelClient
from src.agents.evaluation import evaluate_bundle
from src.agents.evaluation.examples import make_source


class StrategyEvaluationHandoffTests(unittest.TestCase):
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
