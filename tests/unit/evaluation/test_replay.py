from copy import deepcopy
import unittest
from src.agents.evaluation import ContractError, evaluate_bundle, validate_handoff
from src.agents.evaluation.examples import make_source, SCENARIOS


class EvaluationReplayTests(unittest.TestCase):
    def test_all_five_products_and_scenarios(self):
        expected = {"improve": "passed", "strategy": "passed", "risk": "not_passed", "review": "needs_review", "boundary": "passed"}
        for product in range(5):
            for scenario in SCENARIOS:
                with self.subTest(product=product, scenario=scenario["id"]):
                    result = evaluate_bundle(make_source(product, scenario["id"]))
                    self.assertEqual(result["final"]["assessment_status"], expected[scenario["id"]])
                    for r in result["records"]:
                        d = r["outcome"]["evaluation"]["data"]
                        self.assertEqual(d["total_score"], sum(s["score"] for s in d["dimension_scores"].values()) / 5)
                        self.assertEqual(d["strategy_result_id"], r["request"]["creative"]["data"]["strategy_result_id"])

    def test_high_score_cannot_override_risk_and_final_picks_earlier_safe(self):
        result = evaluate_bundle(make_source(0, "risk"))
        self.assertEqual(result["records"][0]["outcome"]["evaluation"]["data"]["total_score"], 90)
        self.assertNotEqual(result["records"][0]["outcome"]["assessment_status"], "passed")
        self.assertEqual(result["selected_index"], 1)
        self.assertEqual(result["final"]["assessment_status"], "not_passed")
        self.assertEqual(result["records"][1]["outcome"]["evaluation"]["data"]["total_score"], 78)

    def test_risk_counts_take_priority_over_score(self):
        result = evaluate_bundle(make_source(0, "review"))
        self.assertEqual(result["selected_index"], 2)
        self.assertEqual(result["final"]["assessment_status"], "needs_review")

    def test_creative_only_reuses_strategy_and_strategy_route_has_new_reference(self):
        creative = evaluate_bundle(make_source())
        self.assertEqual(creative["records"][0]["outcome"]["decision"], "regenerate_creative")
        self.assertEqual(creative["records"][0]["request"]["strategy"], creative["records"][1]["request"]["strategy"])
        strategy = evaluate_bundle(make_source(0, "strategy"))
        self.assertEqual(strategy["records"][0]["outcome"]["decision"], "regenerate_strategy")
        self.assertNotEqual(strategy["records"][0]["request"]["strategy"]["result_id"], strategy["records"][1]["request"]["strategy"]["result_id"])

    def test_boundary_and_advisory_action_cannot_override_system(self):
        source = make_source(0, "boundary")
        source["rounds"][0]["draft"]["recommended_action"] = "regenerate_strategy"
        self.assertEqual(evaluate_bundle(source)["final"]["decision"], "accept")
        source["rounds"][0]["draft"]["dimension_scores"]["attraction"]["score"] = 79
        self.assertEqual(evaluate_bundle(source)["records"][0]["outcome"]["evaluation"]["data"]["total_score"], 79.8)
        self.assertEqual(evaluate_bundle(source)["final"]["assessment_status"], "not_evaluated")

    def test_replay_does_not_mutate_input(self):
        source = make_source()
        copy = deepcopy(source)
        evaluate_bundle(source)
        self.assertEqual(source, copy)

    def test_invalid_cross_task_and_stale_strategy_are_rejected(self):
        source = make_source()
        for field in ("task_id",):
            invalid = deepcopy(source)
            invalid["rounds"][0]["request"]["creative"][field] = "other-task"
            with self.assertRaises(ContractError):
                evaluate_bundle(invalid)
        source["rounds"][0]["request"]["creative"]["data"]["strategy_result_id"] = "other-strategy"
        with self.assertRaises(ContractError):
            evaluate_bundle(source)

    def test_fourth_round_or_continuing_after_success_rejected(self):
        source = make_source(0, "review")
        source["rounds"].append(deepcopy(source["rounds"][-1]))
        with self.assertRaises(ContractError):
            evaluate_bundle(source)
        source = make_source(0, "boundary")
        source["rounds"].append(deepcopy(source["rounds"][-1]))
        source["rounds"][-1]["request"]["round_no"] = 2
        with self.assertRaises(ContractError):
            evaluate_bundle(source)

    def test_bool_scores_unknown_fields_and_invalid_paths_rejected(self):
        for mutate in (lambda s: s["rounds"][0]["draft"]["dimension_scores"]["attraction"].update(score=True), lambda s: s["rounds"][0]["request"].update(owner_scope="forged"), lambda s: s["rounds"][0]["draft"]["dimension_scores"]["attraction"].update(target_path="creative.items[99].copy")):
            source = make_source()
            mutate(source)
            with self.assertRaises(ContractError):
                evaluate_bundle(source)

    def test_hard_budget_constraint_and_frozen_requirements(self):
        source = make_source()
        source["rounds"] = source["rounds"][:1]
        source["rounds"][0]["request"]["strategy"]["data"]["channels"][0]["allocated_amount"] = 6000
        result = evaluate_bundle(source)
        self.assertTrue(any(r["severity"] == "high" for r in result["records"][0]["outcome"]["evaluation"]["data"]["risks"]))
        self.assertEqual(result["records"][0]["outcome"]["decision"], "regenerate_strategy")
        self.assertTrue(any(f["target_agent"] == "strategy" for f in result["records"][0]["outcome"]["evaluation"]["data"]["feedback"]))
        source = make_source()
        source["rounds"][1]["request"]["requirements"]["product_name"] = "changed"
        with self.assertRaises(ContractError):
            evaluate_bundle(source)

    def test_feedback_agent_must_match_path(self):
        source = make_source()
        source["rounds"][0]["draft"]["feedback"][0]["target_agent"] = "strategy"
        with self.assertRaises(ContractError):
            evaluate_bundle(source)


if __name__ == "__main__":
    unittest.main()
