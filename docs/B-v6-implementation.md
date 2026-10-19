# B v6 实现与运行说明

## 2026-10-19 界面精简与职责调整（当前规则）

按用户新的界面要求，两处交付确认框改为同款单卡片摘要。A→B 显示产品事实与目标、受众与定位、预算与周期、特殊限制四项及 4/4 状态；B→C 显示四类创意的准备状态，不展示版本链、JSON 或协议字段。

B 工作台取消左侧来源卡片、任务历史/版本选择入口、常驻事实依据、待确认事项、校验问题、技术日志和检查列表。渠道选择移入创意简报；标题和主要操作增强紫色强调与字号。交付问题只通过弹窗提示，确认后返回工作区。后台不可覆盖的版本与反馈记录继续保存，但不提供历史查询 UI。

**B 现在只生成创意，不调用任何事实复核或评审模型。** `v6-review.txt` 已移除。一次有效生成只有一次生成请求；只有 JSON/结构/长度/字段范围等格式问题才允许一次修复。人工保存不调用模型。B 不执行营销事实/功效/价格/预算内容审查，相关内容评估由 C 负责；生成系统提示词仍要求遵守原始产品事实和策略。新结果 `checks.structure=true`，`checks.facts/constraints/semantic_review=false`，不得解释为评估通过；旧版本原有检查记录不改写。

本次部署使用一次性的、仅监听本机的维护工具保留当前已认证会话，再恢复内存快照；没有新建持久化数据库。会话凭据只在内存中传递，未写入文件。当前会话1个任务、4个版本原样恢复，恢复期间模型调用为0。一般服务停止后仍须自行导出，不能将此次维护恢复当作正式持久化能力。

下面记录了上一阶段的实现与联调细节；涉及审查模型、侧栏或历史入口的旧描述，以本节新规则为准。


工程基础是用户提供的 `Multi-Agent-main.zip`。页面的 DOM 分区、CSS、交付弹层、工作区、Tab、流程动画、反馈卡片和差异卡片移植自用户确认的 `creative_agent_interactive_prototype_v6 (1).html`；演示脚本、固定产品和模拟创意已移除。不是 iframe 或静态原型路由。

## 启动

Python 3.11+。唯一新增运行依赖为 `jsonschema`（使用本地三份真实公共 Schema 及本地引用注册表，不联网下载 Schema）。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "jsonschema>=4.23,<5"
```

服务器环境变量配置完成后：

```powershell
.\.venv\Scripts\python.exe app.py --host 127.0.0.1 --port 8003 --provider compatible --creative-provider compatible
```

本机已存在外部密钥文件时，可只读加载到进程环境，不复制或生成包含密钥的文件：

```powershell
.\.venv\Scripts\python.exe -m ops.run_b_v6_preview --credential-file D:\myhub\Multi-agent\.env.creative --port 8003 --demo-c
```

这条本机便捷命令把同一服务配置用于 A 和 B；常规启动允许两者完全独立。`--demo-c` / `app.py --creative-demo` 只开启明确标记 development/demo only 的模拟 C 决策接口；生产接入 C 前应关闭。

网页：`http://localhost:8003/workspace` → 策略成功后点击“校验并交付给创意智能体” → 查看真实校验弹层 → 确认交付 → B 动态接收 → 工作区。独立入口 `http://localhost:8003/creative` 显示本会话任务历史。

沿用同一主机名访问两页。原有 8000/8001 服务不受影响；8002 旧副本已停用。

## API 配置和费用

只在服务器环境中设置以下字段，或由操作者自行在被忽略的 `.env.creative` 中设置。此次实现没有生成包含真实密钥的 `.env` 或 `.env.creative`。

|字段|含义|
|---|---|
|`CREATIVE_MODEL_BASE_URL`|支持 JSON mode 的 HTTPS chat/completions 服务|
|`CREATIVE_MODEL_API_KEY`|服务端密钥|
|`CREATIVE_MODEL_NAME`|服务商提供的实际模型名称|
|`CREATIVE_MODEL_TIMEOUT_SECONDS`|单次请求 10～120 秒，建议 120|
|`CREATIVE_MODEL_TEMPERATURE`|0～2，默认 0.5|

模板见根目录 `.env.creative.example`；A 的 `.env.example` 保留原字段并注释说明 B 配置。B 不复制 HTTP 实现，复用 A 模型客户端公开的 `generate_json` 接口和既有 HTTPS、禁止重定向、鉴权与安全错误处理。没有修改 A 的 provider 实现。

首次生成、单项重生成、AI 润色、反馈修订会调用生成模型，并独立进行一次事实语义复核；人工保存调用一次事实语义复核，不重生成正文。结构/硬规则拒绝的人工输入不发起复核。无效模型输出最多修复一次；超时、鉴权或网络失败不会自动重新收费调用。读取、切换、复制和导出不调用模型。

## 真实数据流与状态

1. A 原有任务存储通过 `creative_request(task_id, owner_scope)` 交付成功策略；B 再用 `creative-request.schema.json` 及引用契约校验结构、任务引用、原文和预算。失败不会调用模型。
2. `/creative/accept` 保存不可变 handoff 快照，`strategy.data` 用于提炼只读上下文。用户补充要求独立传入，不能覆盖策略。
3. 当前策略渠道动态显示。点击“生成本渠道创意”，在后台线程生成该渠道四类文字，并执行硬校验和独立事实语义复核；其他渠道沿用。所有渠道完成后才能交付 C。
4. 每次成功操作原子追加完整 creative 快照；失败保留上一有效版本及错误信息。包含 `task_id/result_id/version/strategy_result_id/strategy_version/round_no/attempt_count/created_at/config_version/previous_result_id`。
5. Tab 保留未保存编辑；保存后校验并创建新版本。单项重生成和润色只允许返回指定字段 patch；不让模型输出并重写全部创意。每个版本记录修改前后及来源。版本选择可读历史，历史不能编辑。
6. B→C 弹层重新核对 task → strategy → creative → evaluation round。未保存编辑、校验失败、策略冲突、遗漏渠道、版本过时均阻止交付。确认后保存完整输入候选包并锁定当前版本；不会伪造 C 调用或评分。
7. 开发模式可模拟退回/通过。反馈包含 `target_agent/target_path/issue/suggestion/priority`，并关联 evaluation、task 和 creative ID。策略字段反馈转回 A，不允许 B 修改。创意反馈修订只改指定路径，生成新版本，并显示前后差异、原因和保留字段。
8. 业务轮次只在根据 C 退回创建修订版本时增加。人工精修和 API 技术尝试不增加业务轮次。第3轮仍退回则进入 `not_passed`，没有业务 round 4。创意版本号可以因人工精修超过3，它与业务评估轮次不同。

前端动画每阶段约650～850ms，仅在浏览器等待。后端不 sleep。模型较慢停在真实等待状态；失败不显示100%完成。刷新正在运行的任务只轮询，不重复提交模型请求。

## 路由与候选契约

所有任务相关 GET 和 POST 都经原有 session + `owner_scope` 验证；前端从不提供 owner 字段。

|方法|路径|用途|
|---|---|---|
|GET|`/api/tasks/{task}/creative/handoff`|校验真实 A→B 交付|
|POST|`.../creative/accept`|确认接收，body为空对象|
|POST|`.../creative/operations`|异步 generate/edit/regenerate/refine/revision|
|GET|`.../creative/state`|读取版本、后台 job、轨迹和当前状态|
|GET|`.../creative/history`|同任务历史，包含完整快照|
|GET|`/api/creative/history`|本会话任务历史|
|GET|`.../creative/package?result_id=...`|校验并预览当前 C 候选输入|
|POST|`.../creative/delivery`|锁定并交付当前版本，body含 base_result_id|
|POST|`.../creative/demo-feedback`|显式开启时可用，仅开发模拟|
|POST|`.../creative/feedback`|真实 C 预留；认证/正式协议未确认前返回 C_NOT_CONNECTED|

`operations` 接受 `action/base_result_id/channel/instruction/path/value` 的需要子集；额外字段拒绝。示例路径 `items[0].slogan`。所有写操作都检查最新 `base_result_id`，并发重复提交不能覆盖有效版本。

候选协议位于 `src/agents/creative/schemas/`：

- `creative-result.internal.schema.json`：B 内部创意响应。
- `evaluation-request.internal.schema.json`：B→C 完整评估输入候选包。

**它们不是团队已确认的正式公共 Schema。** 原始 `packages/contracts/` 三份文件保持字节一致。C 负责人还需确认反馈路径语法、回调身份认证、评分/风险结构、通过条件、终止与最终版本选择规则。当前没有真实 C 分数或通过结论。

## 存储和边界

遵循原始工程的进程内存架构，不创建另一套 JSON 文件数据库。creative repository 分离在 `src/backend/creative_workspace.py`，同任务保留所有不可变结果、人工编辑轨迹、评估反馈和交付快照。**服务重启后全部任务/版本/会话不保留。** UI 明确提示，当前会话可以查历史，停止服务前请导出。浏览器中的未保存编辑仅作草稿恢复，不冒充服务端持久化。

自动规则+独立模型复核不是事实正确性的绝对保证；发布仍须人工复核。海报和视频是文字创意，未接图片或视频生成。未知资源使用条件式准备建议和待确认事项。

## 代码范围

修改：`src/backend/strategy_web.py`（增加 B 委托路由/实例/启动参数/关闭资源）、`web/workspace.html`（原按钮文字和加载共用弹层组件）、`web/app.js`（仅原交付函数）、`pyproject.toml`、`.env.example`、`.gitignore`、根 README。

新增：`src/agents/creative/{errors,schema,intake,provider,validation,service}.py`、两个内部候选 Schema、`src/backend/{creative_workspace,creative_web}.py`、`web/{creative.html,creative.css,creative.js,creative-api.js,creative-handoff.html}`、`prompts/creative/{v6,v6-review}.txt`、`.env.creative.example`、`ops/run_b_v6_preview.py`、B 单元与接口测试及本文。补齐原压缩包漏掉但 A 原 CSS/测试已引用的同款本地字体及许可文件。

没有修改 `src/agents/strategy/`、A 的原 CSS、task 存储业务、三份公共 Schema和原测试。浏览器联调发现原始 A 的 `fillTemplate` 会因示例里的 `periodMode` 没有同名控件而中断；按边界没有修改，联调用手工填写需求。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
node tests/frontend/test_diagnostics.cjs
node tests/frontend/test_brief.cjs
node tests/frontend/test_presentation.cjs
node tests/frontend/test_result.cjs
node tests/frontend/test_creative_v6.cjs
```

最终：原始105项 Python 测试 + 新增33项B测试，共138项通过；原始4组前端脚本及新增B控制器脚本共5组通过。B自动化全部注入 mock provider，不调用付费 API。

另行完成真实 API 浏览器联调：A首轮成功 → B四类初稿 v1 → 人工 Slogan 保存 v2（仍 round1）→ B→C 候选包交付 → 开发模式 C 退回 → B 真实模型仅修订 copy，得到 v3/round2。修订经历一次输出修复，`attempt_count=2` 没有把业务轮次变成3；Slogan、海报、视频及完整策略保持不变。真实生成的候选包也通过最终本地 Schema 和硬规则检查。

截图和真实输出在被忽略的 `artifacts/b-v6-workbench.png`、`artifacts/live-creative-v3.json`、`artifacts/live-evaluation-package.json`；不放入源码压缩包。正式 C 尚未接通，不以这次开发模拟宣称效果评估通过。
