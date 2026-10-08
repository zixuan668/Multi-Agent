# 智能体代码导航

[返回项目总览](../../README.md) · [团队协作规范](../../docs/team-collaboration.md)

业务顺序固定为：

1. [01 · 营销策略 / strategy](strategy/)：已有第一阶段实现。
2. [02 · 创意生成 / creative](creative/)：待创意负责人开发。
3. [03 · 效果评估 / evaluation](evaluation/)：待评估负责人开发。

编号用于文档和业务顺序；目录名保持稳定，不为排序改动 Python 包名。各模块独立维护私有实现，通过团队确认的公共契约对接；公共 HTTP 服务和任务管理仍位于 `src/backend/`。
