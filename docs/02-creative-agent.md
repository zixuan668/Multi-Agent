# 02 · 创意生成智能体

[返回项目总览](../README.md) · [上一模块：策略智能体](01-strategy-agent.md) · [下一模块：评估智能体](03-evaluation-agent.md)

> 状态：待开发。当前仅预留代码和提示词位置；已存在的首轮输入契约不代表创意生成实现已完成。

## 职责与代码归属

- 负责人：成员 B，实际姓名待团队填写。
- 业务代码：[`src/agents/creative/`](../src/agents/creative/)。
- 提示词：[`prompts/creative/`](../prompts/creative/)。
- 职责：将策略定位、卖点与渠道内容方向发展为创意表达，保留事实依据与约束。
- 边界：不伪造产品能力、优惠或效果，不擅自改写策略预算，也不替评估智能体给出通过结论。

## 已存在的首轮输入

策略成功后可通过 `GET /api/tasks/{task_id}/creative-request` 导出首轮请求。现有依据为：

- [`creative-request.schema.json`](../packages/contracts/creative-request.schema.json)。
- [`validate_creative_request`](../src/agents/strategy/downstream.py)：策略侧首轮交付校验，不是创意生成器。
- [`strategy-response.schema.json`](../packages/contracts/strategy-response.schema.json)：请求中的完整策略响应结构。

当前首轮约束：

- `schema_version=1.0`，`agent=creative`。
- `round_no=1`，`attempt_count=1`。
- `strategy` 是同一任务已成功的完整策略响应，不是仅有策略正文的对象。
- `creative=null`，`previous_result=null`，`feedback=[]`。
- 保留 `requirements`、`task_id` 与 `config_version`，不得任意重新编号或覆盖原始需求。

首轮契约尚不支持完整创意优化轮次；扩展前必须与策略、评估负责人一起核对。不要直接从工作台 DOM、文本截图或未公开的内部类取数据。

## 开发前需要团队确认

1. 创意输出应包含哪些文案、内容形态、渠道映射及事实引用。
2. 创意请求 / 响应的公共入口、版本、错误码与失败处理方式。
3. 向评估模块交付的数据范围与对应契约。
4. 接收反馈时哪些字段允许修改，哪些原始事实与预算约束必须保持。

这些是待确认事项，不是已发布的响应契约；确认后将 Schema 放在公共 `packages/contracts/`，再实现对应模块。

## 交付检查

- 模块实现只放入自己的目录，公开入口与私有实现分开。
- 新单元测试放在 `tests/unit/creative/`；创建测试包时包含 `__init__.py`，确保现有 unittest 命令可发现测试。
- 跨模块测试放在 `tests/integration/`，文件名包含 `creative` 或明确的交付链路名称。
- 联调使用经过脱敏的固定输入；样例存放于 `tests/fixtures/creative/`，真实生成报告存放于本地 `artifacts/`。
- 更新本文状态时写明实际实现、测试依据与未完成事项，不填写未经运行的通过结果。

协作流程见 [三人协作规范](team-collaboration.md)。
