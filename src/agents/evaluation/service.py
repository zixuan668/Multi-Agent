"""Deterministic SRS FR-006–009 replay. Draft scores are explicitly supplied.

This does not synthesize creative output, call models, or execute A/B agents.
"""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from time import perf_counter
from uuid import uuid4
import re

from .contracts import ContractError, DIMENSIONS, validate_config, validate_draft, validate_handoff


def now():
    return datetime.now(timezone.utc).isoformat()


def hard_risks(request):
    risks = []
    requirements = request["requirements"]
    strategy = request["strategy"]["data"]
    facts = "\n".join(str(v) for v in requirements.values() if isinstance(v, str))
    def risk(path, evidence, description, category="constraint"):
        risks.append({"category": category, "severity": "high", "target_path": path, "evidence": str(evidence), "description": description})
    for i, point in enumerate(strategy["selling_points"]):
        if re.sub(r"\s", "", point["source_quote"]) not in re.sub(r"\s", "", facts):
            risk(f"strategy.selling_points[{i}].source_quote", point["source_quote"], "卖点引用不是原始需求的可定位原文。", "fact")
    amounts = [c["allocated_amount"] for c in strategy["channels"] if c["allocated_amount"] is not None]
    budget = requirements.get("budget")
    if not budget and amounts:
        risk("strategy.channels", amounts, "预算缺省时不得填写未经确认的金额分配。")
    if budget and sum(Decimal(str(a)) for a in amounts) > Decimal(str(budget["amount"])):
        risk("strategy.channels", sum(amounts), "渠道预算分配超过用户总预算。")
    special = requirements.get("special_requirements") or ""
    channels = {c["name"] for c in strategy["channels"]}
    for expression, required in ((r"(?:禁用渠道|禁选渠道|禁止渠道)[：:\s]*([^。；;\n]+)", False), (r"(?:必选渠道|指定渠道|必须使用)[：:\s]*([^。；;\n]+)", True)):
        for match in re.finditer(expression, special):
            names = {s.strip() for s in re.split(r"[、,，/]|和|及", match.group(1)) if s.strip()}
            bad = names - channels if required else names & channels
            if bad:
                risk("strategy.channels", "、".join(sorted(bad)), "未遵守用户必选/禁选渠道约束。")
    return risks


def decide(current, history, config):
    highs = lambda r: sum(x["severity"] == "high" for x in r["outcome"]["evaluation"]["data"]["risks"])
    meds = lambda r: sum(x["severity"] == "medium" for x in r["outcome"]["evaluation"]["data"]["risks"])
    data = current["outcome"]["evaluation"]["data"]
    evaluation = current["outcome"]["evaluation"]
    score = data["total_score"]
    if score >= config["pass_threshold"] and highs(current) == 0:
        return "accept", "passed", "passed", evaluation["result_id"], "completed"
    if evaluation["round_no"] < config["max_rounds"]:
        targets = {f["target_agent"] for f in data["feedback"]}
        action = "regenerate_creative" if targets == {"creative"} else "regenerate_strategy"
        return action, "not_evaluated", None, None, "optimizing"
    candidates = history + [current]
    safe = [r for r in candidates if highs(r) == 0]
    if safe:
        chosen = max(safe, key=lambda r: (r["outcome"]["evaluation"]["data"]["total_score"], r["outcome"]["evaluation"]["version"]))
        return "stop_not_passed", "not_passed", "round_limit", chosen["outcome"]["evaluation"]["result_id"], "completed"
    chosen = min(candidates, key=lambda r: (highs(r), meds(r), -r["outcome"]["evaluation"]["data"]["total_score"], -r["outcome"]["evaluation"]["version"]))
    return "stop_needs_review", "needs_review", "round_limit", chosen["outcome"]["evaluation"]["result_id"], "completed"


def evaluate_bundle(source):
    if not isinstance(source, dict) or set(source) - {"label", "source", "rounds", "config_snapshot"}:
        raise ContractError("bundle", "须包含rounds及非敏感config_snapshot，不能含未声明字段")
    config = validate_config(source.get("config_snapshot"))
    rows = source.get("rounds")
    if not isinstance(rows, list) or not 1 <= len(rows) <= config["max_rounds"]:
        raise ContractError("rounds", "须为1至max_rounds轮的连续记录")
    records, events = [], []
    unresolved_feedback = []
    original = None
    for index, row in enumerate(rows, start=1):
        clock = perf_counter()
        if not isinstance(row, dict) or set(row) != {"request", "draft"}:
            raise ContractError("rounds", "每轮须包含request和draft")
        request = deepcopy(row["request"])
        if records:
            request["previous_result"] = records[-1]["outcome"]["evaluation"]
            request["feedback"] = deepcopy(unresolved_feedback)
        request = validate_handoff(request)
        if request["round_no"] != index or request["config_version"] != config["config_version"]:
            raise ContractError("round_no/config_version", "轮次须从1连续递增，配置版本须对应冻结快照")
        if original is None:
            original = request
        elif request["task_id"] != original["task_id"] or request["requirements"] != original["requirements"]:
            raise ContractError("task_id/requirements", "同一任务的原始需求与任务标识不可变")
        if records:
            previous = records[-1]
            if previous["outcome"]["task_status"] == "completed":
                raise ContractError("rounds", "任务已终止，不得追加轮次")
            strategy_changed = request["strategy"]["result_id"] != previous["request"]["strategy"]["result_id"]
            if previous["outcome"]["decision"] == "regenerate_creative" and request["strategy"] != previous["request"]["strategy"]:
                raise ContractError("strategy", "仅创意反馈须复用原策略，不能改写版本正文")
            if previous["outcome"]["decision"] == "regenerate_strategy" and not strategy_changed:
                raise ContractError("strategy", "策略路径须先提供新策略，创意引用该新结果")
            if strategy_changed and request["strategy"]["version"] <= previous["request"]["strategy"]["version"]:
                raise ContractError("strategy.version", "新策略版本须递增")
            if request["creative"]["version"] <= previous["request"]["creative"]["version"] or request["creative"]["result_id"] == previous["request"]["creative"]["result_id"]:
                raise ContractError("creative", "新创意标识与递增版本不能复用")
        draft = validate_draft(row["draft"], request)
        score = float((sum(Decimal(s["score"]) for s in draft["dimension_scores"].values()) / 5).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
        risks = draft["risks"] + hard_risks(request)
        seen = set()
        risks = [r for r in risks if not ((key := (r["category"], r["severity"], r["target_path"], r["description"])) in seen or seen.add(key))]
        feedback = deepcopy(draft["feedback"])
        # A severe rule violation must reach the owner even when the supplied
        # draft only contains creative feedback. Advice cannot hide that route.
        for risk in risks:
            owner = risk["target_path"].split(".")[0]
            if risk["severity"] == "high" and owner in ("strategy", "creative") and not any(f["target_agent"] == owner and f["target_path"] == risk["target_path"] for f in feedback):
                feedback.append({"target_agent": owner, "target_path": risk["target_path"], "issue": risk["description"], "suggestion": "根据原始需求消除该严重风险，并在下一轮提供可核验依据。", "priority": "high"})
        if (score < config["pass_threshold"] or any(r["severity"] == "high" for r in risks)) and not feedback:
            key = min(DIMENSIONS, key=lambda k: draft["dimension_scores"][k]["score"])
            path = draft["dimension_scores"][key]["target_path"].replace(".data.", ".", 1)
            feedback = [{"target_agent": path.split(".")[0] if path.split(".")[0] in ("strategy", "creative") else "strategy", "target_path": path if not path.startswith("requirements.") else "strategy.positioning", "issue": f"{key}为最低分维度，尚未达到通过条件。", "suggestion": "依据该维度理由和原始约束修改对应内容，并在下一轮复核。", "priority": "high" if any(r["severity"] == "high" for r in risks) else "medium"}]
        result_id = f"evaluation-{uuid4().hex}"
        feedback = [{**f, "feedback_id": f"feedback-{uuid4().hex}", "evaluation_id": result_id, "resolved": False} for f in feedback]
        data = {"strategy_result_id": request["strategy"]["result_id"], "creative_result_id": request["creative"]["result_id"], "dimension_scores": draft["dimension_scores"], "total_score": score, "risks": risks, "feedback": feedback, "recommended_action": draft["recommended_action"], "decision": None}
        response = {"schema_version": "1.0", "task_id": request["task_id"], "agent": "evaluation", "round_no": index, "attempt_count": request["attempt_count"], "status": "succeeded", "result_id": result_id, "version": index, "data": data, "error": None, "created_at": now()}
        record = {"request": request, "outcome": {"evaluation": response}}
        action, assessment, termination, selected, status = decide(record, records, config)
        data["decision"] = action
        record["outcome"].update(decision=action, assessment_status=assessment, termination_reason=termination, selected_evaluation_id=selected, task_status=status, iteration_count=index, remaining_issues=[f["issue"] for f in feedback])
        events.extend([{"time": response["created_at"], "round_no": index, "agent": "evaluation", "status": "started", "attempt_count": request["attempt_count"], "summary": "载入上游关联结果，校验公开契约与版本引用。"}, {"time": now(), "round_no": index, "agent": "evaluation", "status": "succeeded", "attempt_count": request["attempt_count"], "elapsed_ms": round((perf_counter() - clock) * 1000, 2), "summary": f"综合分 {score:.1f} · 系统动作 {action}"}])
        records.append(record)
        unresolved_feedback.extend(deepcopy(feedback))
    final = deepcopy(records[-1]["outcome"])
    selected_index = next((i for i, r in enumerate(records) if r["outcome"]["evaluation"]["result_id"] == final["selected_evaluation_id"]), None)
    if selected_index is not None:
        selected_data = records[selected_index]["outcome"]["evaluation"]["data"]
        final["remaining_issues"] = [r["description"] for r in selected_data["risks"] if r["severity"] in ("high", "medium")] + [f["issue"] for f in selected_data["feedback"]]
    return {"label": str(source.get("label", "导入记录"))[:100], "mode": "offline", "source": "预设评分 / 离线规则重放 · 未调用模型", "config_snapshot": config, "records": records, "events": events, "selected_index": selected_index, "final": final, "replay_source": deepcopy(source)}
