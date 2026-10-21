# 02 · 广告创意智能体

[返回项目总览](../README.md) · [协作流程与接口](multi-agent-workflow.md)

## 当前实现

`src/agents/creative/service.py` 消费原始需求和成功策略，通过独立的 `prompts/creative/v1.1.txt` 调用模型，生成创意概念、各渠道标题、正文、行动引导及视觉制作方案。显式离线模式仅用于规则联调，模型失败不自动回退。

每个策略渠道恰好对应一项创意，结果必须引用当前 `strategy_result_id`。产品事实引用必须来自用户提供的产品名称或介绍；不允许虚构链接、优惠、认证或外部资源。当前 `assets=[]`，视觉方案不等于已经生成宣传图。

## 输入、输出与修改

- 公共契约：`packages/contracts/creative-request.v1.1.schema.json` 和 `creative-response.v1.1.schema.json`。
- 运行校验：`src/contracts/campaign.py`；生成与技术修复：`src/agents/generation.py`。
- 交接保留任务、需求、配置、轮次、完整策略、上一创意与目标反馈。
- 只修创意时复用原策略；策略改变后必须生成引用新策略的创意。
- 不修改用户事实、策略预算或渠道，不自行评分或宣布任务通过。

统一调度由 `src/backend/campaigns.py` 负责。格式、引用或字段错误最多技术修复三次；业务优化最多三轮，且受累计请求数和时间限制。每轮有效结果不可变保存。

## 验证与边界

`tests/integration/test_campaigns.py` 覆盖创意定向修改、策略复用、新策略引用、证据拒绝、失败续跑和取消迟到结果。脚本模型验证程序行为，不代表真实广告质量已经验收。

旧 `GET /api/tasks/{task_id}/creative-request` 仍是 v1.0 首轮策略导出，不能替代 v1.1 完整闭环。图片生成、素材存储、品牌排版与视觉审查尚未实现。
