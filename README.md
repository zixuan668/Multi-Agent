# 智策营销策略智能体

这是智策营销第一阶段策略智能体的开发版，对应指定的需求规格说明书 V1.1 文件中 FR-001 至 FR-004、附录 C 和 AC-001 至 AC-008。使用 Python 3.11 以上及标准库，无需安装第三方依赖。

已实现真实模型生成与辅助内容复核、结构和确定性约束校验、异步任务、进程内不可变需求/配置快照/结果版本、技术重试、基本演示会话隔离和创意首轮交付校验。真实模型质量与人工验收尚未完成，不能据离线测试认定项目验收通过。

## 启动真实智能体

先把项目根目录的 `.env.example` 复制为 `.env`，填写你自己的模型服务地址、API 密钥和模型名。不要把密钥发在聊天里，也不要提交 `.env`。服务必须支持 HTTPS 的 `chat/completions` 接口和 JSON 对象输出。

在本项目目录打开 PowerShell，运行：

```powershell
python app.py
```

浏览器打开 `http://127.0.0.1:8000`。默认只使用真实模型；缺少配置会明确返回 `CONFIG_INVALID`，不静默切成模板演示。`.env` 自动读取，已有环境变量优先。配置修改后需要重启，新任务使用新快照。

页面显示“真实模型已配置”不代表连接已经验证。一次真实策略调用包括草案生成与策略编辑，通常产生两次模型请求和相应费用；默认每次模型请求超时60秒，单次完整尝试最多等待120秒。结构、事实或明确约束违规按规则修复重试，最多3次，等待1秒、2秒。一般完善建议单独展示，不阻断有效策略；这不是关闭事实与约束检查。

如果暂时没有密钥，只测试页面与接口，可以显式运行：

```powershell
python app.py --provider offline
```

离线模式仍是规则演示，不具有真实模型内容理解能力。页面和测试记录都会标注，不能计入真实模型验收。按 Ctrl+C 停止服务。

## 任务与结果

提交后立即获得任务编号，后台生成并更新状态。页面展示草案生成→结构与约束校验→策略编辑与事实复核→交付的步骤、耗时、尝试次数、配置版本、卖点原文依据、假设、信息缺口和冲突。修复时携带完整上一次输出和具体阻断问题，不再截断长JSON。

失败显示简短说明，具体问题、对应原文和每次修复记录折叠展示；失败任务也可导出，但不能交付创意请求。完善建议在成功结果旁单列，不写入下游业务数据契约。任务接口不暴露原始模型输出，诊断记录经过密钥脱敏。支持复制排版后的策略全文、单独复制卖点/渠道模块、导出 UTF-8 策略 JSON、导出当前任务、导出已通过首轮校验的创意请求。

同一标签页刷新会恢复当前任务查询及服务端保存的原始需求，不会重新生成或追加模型调用。查询网络故障可点“恢复查询”；需求表单草稿保存在当前浏览器 localStorage 中，失败后可保留需求重新生成，也可手动清空。完成后的任务快照会进入最多 20 条的本地只读归档，即使后端进程重启仍可回看结果；它不具备多人同步、检索审计或服务端恢复能力，不能当作完整任务数据库。

工作台提供“四步向导 / 完整表单”两种录入模式、必填完成度与字符计数、5 类产品模板、目标与周期快捷项、自然语言预算解析、日期区间或持续天数二选一校验。结果分为“策略概览 / 卖点与渠道 / 假设与信息缺口”三组，支持方向键切换；卖点依据可点击回到并高亮原始需求。摘要中的渠道数、预算分配及信息缺口数量全部来自当前任务，不展示虚构效果或评估分数；预算区明确展示已分配、总额与剩余。

v1.4不再把格式完整当作策略质量本身。真实模型先生成有事实边界的策略草案，第二次调用由“策略总监编辑”直接重写最终方案：删除需求复述、万能画像、重复卖点、同质渠道和机械标签，形成一个中心判断、明确主次与渠道角色，并把内容母题整理到创意智能体可直接接续的程度。编辑后的结果仍重新执行契约、事实、预算和约束校验；无法解决的问题才进入修复重试。离线模式维持确定性规则输出，不冒充这种模型编辑能力。

2026-10-03使用同一份“原味奶茶、附近大学生、5000 CNY、30天、不虚构优惠、不承诺减肥效果”的真实模型单例复测，任务task-f65247e1564d4ddd95fe5f38a1901a26成功，2次尝试、约64秒。首次失败为模型额外输出marketing_strategy_note，第二次通过。成功任务与创意首轮请求保存在artifacts/acceptance/milk-tea-real-regression-20261003.json和milk-tea-creative-request-20261003.json。仅证明本次单例与首轮接口通过，不代表50例验收、人工评估或整体可靠性已经完成。

策略完成时：`status=completed`、`assessment_status=not_evaluated`、`termination_reason=strategy_completed`、`iteration_count=0`；不表示完整方案通过评估。

第一阶段任务仅保存在当前进程，重启后清空，不提供跨重启历史。最多5个任务同时执行，内存最多1000个任务。浏览器会话令牌采用 HttpOnly / SameSite=Strict Cookie；其他会话不能查询任务。此服务默认只监听本机，是课程开发服务，不是生产部署。

内部策略模块支持带上一有效响应与反馈的优化调用，保存旧版本；当前网页只提供首轮策略入口，不开放伪造评估反馈。创意、评估及完整系统反馈调度尚不在本次实现范围内。

约束校验分两层：程序检查金额、日期、原文引用、明确命令式渠道和引号标注的禁用表达等可确定规则；真实模型复核完整输入的语义约束及事实支持关系。自然语言规则识别和模型复核都不能证明所有内容绝对正确，仍必须按文档做人工验收。

## 下游对接

- `GET /api/session`：取得演示会话Cookie。
- `POST /api/tasks`：提交原始需求对象或只含 `requirements` 的包装，返回202及 `task_id/pending`。
- `GET /api/tasks/{task_id}`：同会话查询状态、事件及结果版本。
- `GET /api/tasks/{task_id}/creative-request`：策略成功后交付完整创意首轮请求。
- `GET /api/health`：模式与配置状态，不等同于真实连接验证。

旧 `/api/strategy` 同步入口仅保留迁移兼容，也需要会话；网页已改用异步入口。公开入口不接受客户端指定 `task_id`、`owner_scope`、轮次、配置版本或上一结果。

创意对接以 `src/agents/strategy/downstream.py` 的 `validate_creative_request` 为准，并配合 `packages/contracts/creative-request.schema.json`。它覆盖 AC-008 首轮交付，检查完整策略响应、任务归属和业务规则，不生成创意，也不冒充完整创意优化请求校验器。

## 命令行运行

```powershell
python -m src.agents.strategy --input tests/fixtures/sample_request.json --provider offline
```

也可以从标准输入读取：

```powershell
Get-Content -Raw tests/fixtures/sample_request.json | python -m src.agents.strategy --provider offline
```

## 连接模型服务

模型适配器使用通用的 `chat/completions` JSON 协议。密钥只从环境变量读取，不会写入日志或输出。

```powershell
$env:MODEL_BASE_URL='https://your-model-service.example/v1'
$env:MODEL_API_KEY='replace-with-your-key'
$env:MODEL_NAME='your-model-name'
python -m src.agents.strategy --input tests/fixtures/sample_request.json --provider compatible
```

默认 `--provider compatible`。保留的 `auto` 参数也不会再静默回退离线。模型密钥不会进入任务快照、页面或常规日志；原始输出证据只供本地测试使用。

## 运行测试

```powershell
python -m unittest discover -s tests -v
```

测试包含契约、预算/渠道/表达/日期规则、模拟语义复核、复核类别与真实证据检查、建议不误阻断、违规仍阻断、完整修复上下文、脱敏失败诊断、重试、超时迟到结果、不可变版本、异步HTTP、会话隔离、5任务不互相覆盖和50例离线首轮交付校验。模拟的HTTPS适配器测试只证明请求处理逻辑，不证明供应商连接或真实模型效果。

配置真实模型后，运行文档要求的固定50例（会产生模型调用费用）：

```powershell
python -m ops.run_strategy_acceptance --provider compatible
```

显式生成离线联调证据：

```powershell
python -m ops.run_strategy_acceptance --provider offline
```

报告记录每次尝试的原始生成和复核输出、错误码、耗时、提示词版本/摘要及非敏感配置。默认生成带时间戳的新文件，不覆盖旧报告。报告明确标记是否为真实模型证据，人工验收默认为待完成。固定50例使用人工构造需求，五类产品各10例，包含产品事实、预算、周期和渠道约束差异。

至少48个合法结果仅是结构目标；还需每类固定2例共10例，由两人按 AC-004至AC-006独立检查，分歧由第三人复核。离线通过和模型辅助复核都不能代替这一步。

## 本次未实现

完整创意/评估智能体、三轮闭环、关系数据库持久化、跨重启历史和完整系统验收仍需团队后续集成。本期不增加RAG、复杂账号、广告投放或图片视频生成。

## 主要目录

```text
src/agents/strategy/       策略智能体实现
src/backend/tasks.py      第一阶段进程内异步任务
packages/contracts/        公共 JSON Schema
prompts/strategy/          版本化提示词
tests/unit/                单元测试
tests/acceptance/          第一阶段验收测试
tests/fixtures/            示例请求
```
