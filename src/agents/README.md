# 智能体代码导航

[返回项目总览](../../README.md) · [团队协作规范](../../docs/team-collaboration.md)

业务顺序固定为：

1. [01 · 营销策略 / strategy](strategy/)：真实策略生成、编辑与约束校验。
2. [02 · 创意生成 / creative](creative/)：真实创意生成、事实引用与定向修改。
3. [03 · 独立评审 / evaluation](evaluation/)：`agent.py` 执行真实评审，原有服务保留规则回放。

统一调度、反馈路由及持久化见[协作流程说明](../../docs/multi-agent-workflow.md)。

编号用于文档和业务顺序；目录名保持稳定，不为排序改动 Python 包名。各模块独立维护私有实现，通过团队确认的公共契约对接；公共 HTTP 服务和任务管理仍位于 `src/backend/`。
