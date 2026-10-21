from copy import deepcopy
import io
import json
import threading
import time
import unittest
from unittest.mock import Mock, patch

from src.agents.strategy.errors import ContractValidationError, ModelOutputError
from src.agents.strategy.model_clients import CompatibleModelClient
from src.agents.creative.revisions import preserve_revision_scope
from src.backend.collaboration import public_excerpt
from tests.integration import test_campaigns as fixtures


ScriptedClient = fixtures.ScriptedClient
requirements = fixtures.requirements


class RevisionClient(ScriptedClient):
    def complete_json(self, system, user):
        result = super().complete_json(system,user)
        request = json.loads(user)["request"]
        if "广告创意智能体" in system and any(item["feedback_id"].startswith("human-") for item in request["feedback"]):
            result["items"][0]["headline"] = request["requirements"]["product_name"] + "：校园里的新选择"
            result["items"][0]["body"] = "这段无关正文不应覆盖已锁定内容。"
        return result


class DirectionClient(RevisionClient):
    def complete_json(self,system,user):
        if '两个真正不同的创意方向' in system:
            request=json.loads(user)['request']
            self.calls.append(('directions',deepcopy(request)))
            return {'directions':[{'title':'场景自查','idea':'使用前先按场景自查需求。','rationale':'基于已知功能。','headline':'先看看你需要什么'},{'title':'功能对照','idea':'按功能逐项对照使用流程。','rationale':'另一种表达结构。','headline':'用功能对照你的流程'}]}
        return super().complete_json(system,user)


class CollaborationTests(unittest.TestCase):
    setUp = fixtures.CampaignTests.setUp
    tearDown = fixtures.CampaignTests.tearDown
    store = fixtures.CampaignTests.store
    wait = fixtures.CampaignTests.wait

    def test_interactive_directions_pause_until_user_choice_and_survive_restart(self):
        store = self.store(provider="offline")
        task = self.wait(store,store.create(requirements(),"owner-1","interactive-1",interactive=True)["task_id"])
        self.assertEqual(task["status"],"awaiting_direction")
        self.assertIsNone(task["rounds"][0]["creative"])
        self.assertEqual(len(task["rounds"][0]["directions"]),2)
        store.close()
        store = self.store(provider="offline")
        task = store.get(task["task_id"],"owner-1")
        self.assertEqual(task["status"],"awaiting_direction")
        selection = {"option_id":"direction-2","base_round":1}
        store.choose_direction(task["task_id"],"owner-1",selection)
        finished = self.wait(store,task["task_id"])
        self.assertEqual(finished["status"],"awaiting_confirmation")
        self.assertEqual(finished["rounds"][0]["direction_choice"]["option_id"],"direction-2")
        self.assertEqual(store.choose_direction(task["task_id"],"owner-1",selection)["round_no"],1)

    def test_feedback_can_be_queued_during_generation_and_is_idempotent(self):
        client = ScriptedClient()
        client.gate = threading.Event()
        store = self.store(client)
        task = store.create(requirements(),"owner-1","queued-feedback")
        deadline = time.monotonic()+3
        while not any(call[0]=="creative" for call in client.calls) and time.monotonic()<deadline:
            time.sleep(.01)
        payload = {"message":"让下一步动作更具体。","target_path":"creative.items","base_round":1,"submission_key":"queued-message-1"}
        first = store.revise(task["task_id"],"owner-1",payload)
        again = store.revise(task["task_id"],"owner-1",payload)
        self.assertEqual(len(first["messages"]),1)
        self.assertEqual(len(again["messages"]),1)
        self.assertEqual(first["messages"][0]["status"],"pending")
        with self.assertRaises(ContractValidationError):
            store.revise(task["task_id"],"owner-1",{**payload,"message":"另一条意见"})
        client.gate.set()
        finished = self.wait(store,task["task_id"])
        self.assertEqual(finished["messages"][0]["status"],"applied")
        self.assertTrue(any(item["feedback_id"].startswith("human-") for item in finished["feedback"]))
        self.assertEqual(sum(call[0]=="strategy" for call in client.calls),1)

    def test_targeted_headline_revision_preserves_strategy_and_other_fields(self):
        store = self.store(RevisionClient())
        task = self.wait(store,store.create(requirements(),"owner-1","targeted-revision")["task_id"])
        before = deepcopy(task["rounds"][-1])
        store.revise(task["task_id"],"owner-1",{"message":"标题增加校园场景。","target_path":"creative.items[0].headline","base_round":task["round_no"],"submission_key":"headline-revision"})
        finished = self.wait(store,task["task_id"])
        after = finished["rounds"][-1]
        self.assertEqual(after["strategy"],before["strategy"])
        self.assertNotEqual(after["creative"]["data"]["items"][0]["headline"],before["creative"]["data"]["items"][0]["headline"])
        self.assertEqual(after["creative"]["data"]["items"][0]["body"],before["creative"]["data"]["items"][0]["body"])
        self.assertEqual(after["creative"]["data"]["items"][0]["visual_brief"],before["creative"]["data"]["items"][0]["visual_brief"])
        self.assertTrue(any(item["feedback_id"].startswith("human-") and item["status"]=="resolved" for item in finished["feedback"]))

    def test_polish_mode_does_not_hide_weak_dimension_behind_average(self):
        class WeakClient(ScriptedClient):
            def complete_json(self, system, user):
                data = super().complete_json(system,user)
                if "广告创意智能体" not in system:
                    request = json.loads(user)["request"]
                    if request["round_no"]==1:
                        data["feedback"]=[]
                        for score in data["dimension_scores"].values():
                            score["score"]=90
                        data["dimension_scores"]["attraction"]["score"]=72
                return data
        store = self.store(WeakClient())
        task = self.wait(store,store.create(requirements(),"owner-1","polish-dimension",quality_mode="polish")["task_id"])
        self.assertGreater(task["rounds"][0]["evaluation"]["data"]["total_score"],80)
        self.assertNotEqual(task["rounds"][0]["decision"],"accept")
        self.assertTrue(any("单项质量" in item["issue"] for item in task["feedback"]))

    def test_public_excerpt_only_extracts_allowlisted_output_fields(self):
        self.assertEqual(public_excerpt('{"private":"不应显示","positioning":"面向学生的公开方',"strategy"),[{"label":"策略方向","text":"面向学生的公开方"}])
        self.assertEqual(public_excerpt('{"analysis":"内部过程"}',"strategy"),[])
        self.assertEqual(public_excerpt('{"headline":"标题\\u4e',"creative"),[{"label":"标题草稿","text":"标题"}])

    def test_clarification_creates_linked_continuation_without_overwriting_source(self):
        store=self.store(provider="offline")
        source=self.wait(store,store.create(requirements(),"owner-1","clarification-source")["task_id"])
        original=deepcopy(source['requirements'])
        store.repository.update(source['task_id'],lambda task:task.update(status='awaiting_input'))
        answer={'message':'补充资料：本次只介绍已有功能，不设置试用入口。','submission_key':'clarification-answer'}
        child=store.clarify(source['task_id'],'owner-1',answer)
        again=store.clarify(source['task_id'],'owner-1',answer)
        self.assertEqual(child['task_id'],again['task_id'])
        self.assertEqual(child['parent_task_id'],source['task_id'])
        self.assertEqual(store.get(source['task_id'],'owner-1')['requirements'],original)
        self.assertIn(answer['message'],child['requirements']['product_description'])
        self.assertFalse(child['interactive'])
        self.wait(store,child['task_id'])

    def interactive_review(self):
        client=DirectionClient()
        store=self.store(client)
        task=self.wait(store,store.create(requirements(),'owner-1','checkpoint-task',interactive=True)['task_id'])
        store.choose_direction(task['task_id'],'owner-1',{'option_id':'direction-1','base_round':1})
        task=self.wait(store,task['task_id'])
        return store,client,task

    def test_interactive_review_pauses_before_spending_another_round(self):
        store,client,task=self.interactive_review()
        self.assertEqual(task['status'],'awaiting_revision')
        self.assertEqual(len(task['rounds']),1)
        count=len(client.calls)
        time.sleep(.03)
        self.assertEqual(len(client.calls),count)
        store.continue_review(task['task_id'],'owner-1')
        finished=self.wait(store,task['task_id'])
        self.assertEqual(finished['status'],'awaiting_confirmation')
        self.assertEqual(len(finished['rounds']),2)

    def test_human_can_direct_revision_at_the_review_checkpoint(self):
        store,client,task=self.interactive_review()
        before=deepcopy(task['rounds'][0])
        store.revise(task['task_id'],'owner-1',{'message':'标题加上校园场景，保留其他已有效内容。','target_path':'creative.items[0].headline','base_round':1,'submission_key':'checkpoint-human'})
        finished=self.wait(store,task['task_id'])
        self.assertEqual(finished['status'],'awaiting_confirmation')
        self.assertEqual(finished['rounds'][1]['strategy'],before['strategy'])
        self.assertEqual(finished['rounds'][1]['creative']['data']['items'][0]['body'],before['creative']['data']['items'][0]['body'])


class StreamingTests(unittest.TestCase):
    def client(self):
        client = CompatibleModelClient(base_url="https://example.com/v1",api_key="secret-for-test",model="test-model")
        client.public_output_observer = Mock()
        client.usage_observer = Mock()
        client.cancellation_check = Mock()
        return client

    def test_streaming_never_exposes_reasoning_content_and_records_usage(self):
        client = self.client()
        chunks=[{"choices":[{"delta":{"reasoning_content":"私有内部推理，不能展示"}}]}, {"choices":[{"delta":{"content":'{"headline":"'}}]}, {"choices":[{"delta":{"content":'公开标题"}'},"finish_reason":"stop"}],"usage":{"prompt_tokens":12,"completion_tokens":7}}]
        raw=b''.join(b'data: '+json.dumps(chunk,ensure_ascii=False).encode()+b'\n\n' for chunk in chunks)+b'data: [DONE]\n\n'
        response=io.BytesIO(raw)
        response.headers={"Content-Type":"text/event-stream"}
        with patch("src.agents.strategy.model_clients.request.build_opener") as factory:
            factory.return_value.open.return_value=response
            self.assertEqual(client.complete_json("system","request"),{"headline":"公开标题"})
        shown=str(client.public_output_observer.call_args_list)
        self.assertNotIn("私有内部推理",shown)
        self.assertIn("公开标题",shown)
        client.usage_observer.assert_called_once_with({"prompt_tokens":12,"completion_tokens":7})
        self.assertTrue(json.loads(factory.return_value.open.call_args.args[0].data)["stream"])

    def test_interrupted_stream_is_not_treated_as_a_finished_result(self):
        client=self.client()
        raw=b'data: {"choices":[{"delta":{"content":"{}"}}]}\n\n'
        with self.assertRaises(ModelOutputError):
            client._read_stream(io.BytesIO(raw),30)

    def test_stream_checks_cancellation_before_publishing_next_chunk(self):
        client=self.client()
        client.cancellation_check.side_effect=ContractValidationError("cancelled")
        with self.assertRaises(ContractValidationError):
            client._read_stream(io.BytesIO(b'data: {"choices":[]}\n'),30)
        client.public_output_observer.assert_not_called()
