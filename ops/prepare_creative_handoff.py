"""生成明确标识为离线合成数据的契约联调样例，不调用真实模型。"""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

from ops.strategy_cases import guided_cases
from src.agents.strategy.downstream import build_creative_request
from src.agents.strategy.model_clients import RuleBasedModelClient
from src.agents.strategy.service import StrategyAgent


def build_examples():
    cases = {item['case_id']:item['request'] for item in guided_cases()}
    agent=StrategyAgent(RuleBasedModelClient(),sleeper=lambda _:None)
    examples={}
    for name in ('milk-owned','milk-zero','missing-context','channel-conflict','watch'):
        request=replace(cases[name],config_version='synthetic-offline-handoff-v1')
        response=agent.generate(request).to_dict()
        if response['status'] != 'succeeded':
            raise RuntimeError(f'合成样例 {name} 生成失败')
        examples[name]=build_creative_request(request,response)
    # 预算保留余量仍是合法输入，用于检查消费端是否误要求“全部花完”。
    reserve=deepcopy(examples['milk-owned'])
    reserve['task_id']=reserve['strategy']['task_id']='guided-budget-reserve'
    reserve['strategy']['result_id']='synthetic-strategy-budget-reserve'
    reserve['strategy']['data']['channels'][0]['allocated_amount']=600
    reserve['strategy']['data']['assumptions'].append('剩余400元暂不分配，待核对制作条件与真实反馈后再决定是否使用。')
    examples['budget-reserve']=reserve
    invalid={}
    invalid['cross-task']=deepcopy(examples['milk-owned'])
    invalid['cross-task']['strategy']['task_id']='different-task'
    invalid['wrong-round']=deepcopy(examples['milk-owned'])
    invalid['wrong-round']['strategy']['round_no']=2
    invalid['over-budget']=deepcopy(examples['milk-owned'])
    invalid['over-budget']['strategy']['data']['channels'][0]['allocated_amount']=1001
    invalid['missing-field']=deepcopy(examples['milk-owned'])
    del invalid['missing-field']['creative']
    invalid['unknown-budget']=deepcopy(examples['missing-context'])
    invalid['unknown-budget']['strategy']['data']['channels'][0]['allocated_amount']=100
    invalid['fake-evidence']=deepcopy(examples['milk-owned'])
    invalid['fake-evidence']['strategy']['data']['selling_points'][0]['source_quote']='官方认证'
    return examples,invalid


def main():
    target=Path(__file__).resolve().parents[1]/'tests/fixtures/creative'
    examples,invalid=build_examples()
    files={**{f'valid-{key}.json':value for key,value in examples.items()},
           **{f'invalid-{key}.json':value for key,value in invalid.items()}}
    # 显式工具只生成其管理的样例；已有文件时不覆盖。
    if any((target/name).exists() for name in files):
        raise SystemExit('目标样例已存在，不覆盖；请使用测试检查已有文件。')
    target.mkdir(parents=True,exist_ok=True)
    for name,payload in files.items():
        (target/name).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'生成{len(files)}份离线合成契约样例：{target}')


if __name__ == '__main__':
    main()
