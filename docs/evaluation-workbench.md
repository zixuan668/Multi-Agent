# 效果评估工作台：运行与团队交接

本分支以仓库 `main` 的 `691a952` 为基准，按工作空间需求规格说明书 V1.1（FR-006～009、FR-013）和三人分工说明书 V1.0 开发 C 侧独立模块。外观按用户指定的 [StyleKit Neumorphism](https://www.stylekit.top/styles/neumorphism/showcase#design) 调整为浅灰同色面板、凸凹双向阴影与柔和圆角，保留流动粒子、评分环及三智能体节点；所有样例明确标记为离线重放。

完整制作提示词及 18 项核对清单：[前端制作提示词 V4](evaluation-frontend-prompt.md)。其中的真实模型、数据库与权限要求是后续全站目标；当前运行范围以本文为准。

## 启动和核对

Python 3.11 及以上，无新增第三方依赖。在仓库根目录运行：

```powershell
python -m src.agents.evaluation.preview --port 8765
```

打开 `http://127.0.0.1:8765/evaluation/`。原有 `python app.py` 策略入口保持原样，两个服务可分别启动。

- [ ] 选择五种产品以及五种场景；最终结果包含通过、未达标、待人工复核。
- [ ] 点击五维评分查看理由、字段路径和关联原文。
- [ ] 风险可按等级筛选；严重风险即使高分也不能通过。
- [ ] “轮次与版本”可回看原策略、创意和评估的关联记录。
- [ ] 高分风险否决场景最终选中第二轮的安全 78 分版本，而不是首轮风险 90 分或末轮 76 分。
- [ ] “结果报告”导出的三个完整响应都来自同一个选中版本。
- [ ] 使用说明可下载当前重放模板；“导入记录”重新校验并计算该包。
- [ ] 配置快照只读；本地重放记录只保存在当前浏览器。
- [ ] 手机布局可使用顶部动效开关；系统减少动画设置会暂停粒子。

## 归属与合并边界

| 成员 | 此模块消费/提供的内容 | 合并方式 |
| --- | --- | --- |
| A 策略 | 既有公开 `MarketingRequirements` 与完整 `StrategyResponse` | C 不读取其私有状态、不改策略内容 |
| B 创意及全站前端 | 引用策略 result_id 的完整创意响应；接收定位反馈 | 创意响应结构尚未公共发布，需核对模块内提案 |
| C 评估 | 完整关联输入、评分/风险/反馈和确定性决策 | 独立代码及页面，供 B 集成 |

改动限于 `src/agents/evaluation/`、`web/evaluation/`、评估测试/样例和评估说明。没有修改 `app.py`、策略代码、公共 `packages/contracts/`、全站前端、依赖和环境配置。不要直接替换 B 的主页面；将本页面作为独立路由或同源 iframe 集成，由 B 接入既有全站状态与导出服务。

## 本地 API 与对接字段

所有路径统一在 `web/evaluation/api.js` 中，前端不直接调用 A/B 私有接口。

| 方法/路径 | 用途 |
| --- | --- |
| GET `/api/evaluation/scenarios` | 产品、场景元数据 |
| GET `/api/evaluation/sample?product=0&scenario=improve` | 完整预设重放包 |
| POST `/api/evaluation/replay` | 校验重放包，计算轮次结果；成功响应为 `{data: bundle}` |

服务仅监听本机 127.0.0.1，拒绝异源 POST，限制 JSON 为 2MB，静态资产白名单不会暴露 `.env` 或源代码。跨服务集成请由团队后端做同源代理，避免前端配置密钥或放宽跨域权限。

重放包结构如下。页面使用说明中的下载模板包含所有必需字段，可直接作为联调样例。

```text
bundle = {label?, source?, config_snapshot, rounds: [{request, draft}, ...]}
request = {schema_version, task_id, agent: "evaluation", round_no,
  attempt_count, requirements, strategy, creative,
  feedback, previous_result, config_version}
draft = {dimension_scores, risks, feedback, recommended_action}
```

`strategy` 与 `creative` 均须为成功的完整响应封装，包含 `schema_version/task_id/agent/round_no/attempt_count/status/result_id/version/data/error/created_at`。`creative.data.strategy_result_id` 必须等于输入策略的 `result_id`。五维键固定为 `attraction/audience_fit/clarity/channel_fit/call_to_action`，每项包含整数 `score`、`reason`、可解析 `target_path`。

反馈至少包含 `target_agent/target_path/issue/suggestion/priority`，输出追加 `feedback_id/evaluation_id/resolved`。定位路径使用 `strategy.positioning`、`creative.items[0].copy` 等；也接受带 `.data.` 的输入路径。目标智能体必须与路径归属一致。

配置快照独立于 request，不向已有共享请求擅自增加字段：`config_version/pass_threshold/max_rounds/timeout_seconds/max_attempts/scoring_rule_version`。任务需求、配置版本和完整快照在一次重放中固定。

本模块的 `contracts.py` 是 **SRS 对接提案**，不是已获团队确认的公共契约。A/B 应核对创意四类内容结构、反馈字段和终止状态，再由公共契约负责人发布 Schema。实际模型客户端与全站调度尚未接通，超时/重试配置仅展示快照，并未冒充已执行的模型行为。

## 决策规则与剩余集成

五维等权平均保留一位小数；默认通过线 80，存在严重风险则否决通过。评分草稿中的建议不能覆盖规则决策。原文引用、预算分配和显式必选/禁选渠道另做确定性约束检查；完整事实、合规与品牌审查仍需真实模型及人工依据。

仅创意反馈复用完整原策略；出现策略反馈时下一轮必须提交递增版本的新策略，再提交引用它的新创意。严重风险会补齐所属模块反馈，避免被创意建议掩盖。初次评估算第 1 轮，最多 3 轮；技术尝试次数不等于优化轮次。

达标即终止。到上限后，优先选无严重风险版本中最高分者，同分选较新版本；全部含严重风险时依次比较严重风险数、中等风险数、分数和版本，输出 `needs_review`。`completed` 表示流程结束，不等于 `passed`。`selected_evaluation_id` 关联相同轮次的三个完整响应。

重放只消费显式提交的各轮上游结果和预设评分，不自动执行 A/B、不连接模型、不宣称预测 CTR/ROI。事件日志只记录评估校验与规则计算。真实闭环需要全站调度器根据 `decision` 发起 A/B，再将成功响应交回 C；错误响应应由调度层处理，不得作为成功方案送入评估。

## 同源嵌入提案

父页面可使用 `<iframe src="/evaluation/" title="效果评估工作台"></iframe>`。同时代理上述 `/api/evaluation/*` 路径。可选消息均限定同源与父窗口：

- 子页面通知 `zhice:evaluation:ready`。
- 父页面发送 `{type: "zhice:evaluation:load", bundle: replayBundle}`。
- 子页面完成后通知 `zhice:evaluation:completed`，携带 `task_id/assessment_status/selected_evaluation_id`。

这是重放包适配机制，真实模型结果流可在团队确定接口后替换 `api.js` 适配器。全站历史与导出仍由 B 接管，不应把 localStorage 当作共享数据库。

## 可重复验证

```powershell
python -m unittest discover -s tests -v
node tests/frontend/test_evaluation.cjs
node tests/frontend/test_diagnostics.cjs
python -m src.agents.evaluation.check_handoff sample.json
```

规则测试覆盖 5×5 样例组合、风险否决、策略/创意反馈分流、最高安全版本选择、80 分边界、输入不变性、跨任务/旧引用拒绝、轮次上限、预算约束和错误路径。HTTP 测试验证隔离路径及输入拒绝；策略交接测试使用仓库真实 `StrategyAgent` 的规则客户端输出（不调用模型）。前端检查验证最终导出引用一致性。浏览器另核对证据弹窗、风险场景、导入/导出及窄屏布局。

这些检查证明离线交接和规则行为，不代表三智能体真实模型、端到端优化闭环、数据库历史或全套 SRS 验收完成。
