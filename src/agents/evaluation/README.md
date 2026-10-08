# 03 · 效果评估智能体代码区

此目录提供 C 侧独立离线联调实现。评分草稿由重放包显式提供，规则服务重新计算综合分、风险否决、反馈路由和最终版本；不调用模型或执行策略/创意生成。

- 对接与职责：[03 评估说明](../../../docs/03-evaluation-agent.md)。
- 提示词：[`prompts/evaluation/`](../../../prompts/evaluation/)。
- 协作方式：[团队协作规范](../../../docs/team-collaboration.md)。

启动：`python -m src.agents.evaluation.preview --port 8765`，访问 `http://127.0.0.1:8765/evaluation/`。

交接校验：`python -m src.agents.evaluation.check_handoff sample.json`。接受单轮 request 或包含 rounds 与 config_snapshot 的重放包。

完整对接说明：[evaluation-workbench.md](../../../docs/evaluation-workbench.md)。创意/评估契约是模块内提案，团队确认前不修改公共 Schema。策略侧的校验和此处的预设重放均不等于真实三智能体系统验收。
