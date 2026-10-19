# 效果评估智能体 C API 契约与运行交付说明

交付日期：2026-10-19。配套概述见 [C 模块交付与 A 对接说明](C模块交付与A对接说明.md)。本文件描述当前功能分支的实际实现，供 A 集成及 B 联调；模块内 Schema 为候选协议，不替代团队公共契约评审。

## 运行环境与配置

Python 3.11 以上，运行目录为仓库根目录。本工作区测试使用已有 Python 3.14 虚拟环境，接收方不需要复制该环境。

```powershell
python -m pip install -e .
if (-not (Test-Path -LiteralPath .env.evaluation)) { Copy-Item .env.evaluation.example .env.evaluation }
# 编辑本机 .env.evaluation，配置真实服务地址、模型和自己的密钥
python -m ops.run_evaluation_workspace --port 8766 --share-model
```

仅在本机配置文件不存在时复制模板，避免覆盖个人配置。启动后从 `http://127.0.0.1:8766/workspace` 开始，完成策略、创意和评估。普通 `python app.py` 默认只启用 A/B；也可用 `python app.py --evaluation` 启用评估。

`--share-model` 在 A/B 配置缺省时使用已配置的评估模型，已有 A/B 配置优先。映射仅发生在服务进程内，不输出或复制密钥。可用 `--env-file 本机文件路径` 加载已有配置，兼容 `DEEPSEEK_API_KEY/DEEPSEEK_BASE_URL/DEEPSEEK_MODEL`。

| 配置项 | 默认值或约束 |
| --- | --- |
| EVALUATION_MODEL_BASE_URL | HTTPS 服务地址，默认 https://api.deepseek.com |
| EVALUATION_MODEL_API_KEY | 必须提供有效密钥；模板占位符不被接受 |
| EVALUATION_MODEL_NAME | deepseek-flash |
| EVALUATION_TIMEOUT_SECONDS | 60，允许 10～120 整数 |
| EVALUATION_MAX_ATTEMPTS | 3，允许 1～3 整数 |
| EVALUATION_PASS_THRESHOLD | 80，允许 0～100 有限数值 |
| EVALUATION_MAX_ROUNDS | 3，允许 1～3 整数 |

非法配置在启用评估时阻止启动。当前提示词为 `prompts/evaluation/v1.2.txt`，新任务规则为 `equal-weight-v2`。配置与提示词指纹进入非敏感 `config_version`，同一任务内冻结。旧 v1 记录仍按旧版本回读；修改代码或 env 不自动改写旧任务。

当前开发机另在 `http://localhost:8770/workspace` 运行最新版，旧 `127.0.0.1:8767` 保留已有任务。这两个地址是本机运行状态，不是部署依赖。一次业务流程必须使用同一主机名和浏览器会话；不要混用 localhost 与 127.0.0.1。

## 认证和访问边界

先 `GET /api/session` 获取 HttpOnly `zhice_session` Cookie，任务接口由服务端推导 `owner_scope`。跨会话任务访问被拒绝，任务编号本身不能作为凭据。

真实任务的评估输入只来自服务端已保存的 B 交付。浏览器提交当前创意版本编号，不提交真实分数、通过状态、任意策略或回调结果。评估 POST 拒绝异源 Origin、非 JSON、未知控制字段和超过 2MB 的请求正文。

离线 `replay` 可显式接收预设评分草稿，用于规则联调；不会写入真实任务或回传 B，不能当成真实模型评分入口。

## HTTP 接口

以下响应直接返回 JSON 对象，未统一包在 `data` 中；离线 replay 的成功结果例外，使用 `{data: bundle}`。

| 方法和路径 | 请求 | 成功结果 |
| --- | --- | --- |
| GET /evaluation/ | 无 | 会话任务入口，演示需明确点击 |
| GET /evaluation/?task_id=... | 当前任务编号 | 真实评估页面，恢复读取而不重发模型请求 |
| GET /api/evaluation/scenarios | 无 | products、scenarios、mode；真实评估启用时 mode 为 live_available |
| GET /api/evaluation/sample?product=0&scenario=improve | 产品索引和场景 | 离线样例来源，未调用模型 |
| GET /api/tasks/{task_id}/evaluation/state | 会话 Cookie | job、bundle、events、config_snapshot、storage；未建立评估时 job/bundle 为 null |
| GET /api/tasks/{task_id}/evaluation/strategy-handoff | 会话 Cookie | 可继续的策略修改请求及关联记录 |
| POST /api/tasks/{task_id}/evaluation/operations | base_result_id | 202，启动或复用评估后返回当前评估状态 |
| POST /api/tasks/{task_id}/creative/delivery | base_result_id | B 原交付结果；启用评估时附 evaluation_job，失败可能附 evaluation_error |
| POST /api/evaluation/replay | rounds 和 config_snapshot 等来源数据 | 200，data 为离线规则结果 |

启动评估的请求示意：

```json
{"base_result_id":"creative-current-result-id"}
```

该编号必须对应当前会话已保存的 B 创意。`202` 仅代表受理，不表示生成成功；调用方还应检查 `evaluation_error` 并读取 `evaluation/state`，不能仅凭 HTTP 成功展示通过。

配套 B 入口 `GET /api/tasks/{task_id}/creative/package?result_id=...` 可读取候选输入包；它本身不执行评估。`POST .../creative/feedback` 尚不接收外部真实回调，仍返回 `C_NOT_CONNECTED`。真实闭环由同进程的受信任协调器执行 `apply_evaluation`；开发模拟接口仅在显式启用 demo 时可用。

## B 到效果评估输入

输入包 `schema_version=b-to-c-internal-candidate-v1`，定义在 `src/agents/creative/schemas/evaluation-request.internal.schema.json`。完整公共联调样例位于 `tests/fixtures/evaluation/b-candidate-package.json`。

| 字段 | 处理要求 |
| --- | --- |
| task_id | 与完整 strategy、creative 中的任务编号一致 |
| requirements | 原始需求，后续轮次不得改写 |
| strategy | 完整成功策略响应，包括 result_id、version、data |
| creative | 完整 B 响应，引用对应 strategy_result_id 和 strategy_version |
| round_no | 连续业务轮次，从 1 开始，最多 3 |
| evaluation_status | B 交付包的候选评估状态，不当成已通过 |
| feedback_trace | 保留反馈轨迹，当前模型仍重新检查内容 |

创意必须完整覆盖策略中的全部渠道，每个渠道恰好一项。保留四个字符串 `copy/slogan/poster_concept/video_script`，不强行转成旧离线演示包里的海报或分镜对象。保留 `evidence`、`pending_confirmations`、人工及模型修改轨迹。

`checks.structure=true` 仅表示 B 的结构检查通过。`facts/constraints/semantic_review=false` 不能解释为事实或内容已通过；随附证据也可能过时，评估必须重新对照原始需求。

可先执行只读校验，不调用模型：

```powershell
python -m src.agents.evaluation.check_handoff B交付包.json
```

## 真实任务和并发

job.status 为 `running/succeeded/failed`。stage 可为 `queued/generating/retrying/applying_feedback/completed/failed`。job 还包含 job_id、attempt_count、round_no、created_at、creative_result_id、delivery_id、error；成功后附 result_id。

前端约每 700ms 读取状态。确认交付后立即进入评估页面，可先浏览本次广告创意；完成后显示结论，不播放额外固定步骤来拖延结果。刷新只恢复 GET，不自动重提或重试付费模型。

相同创意版本的重复交付复用同一 job，不重复收费调用；当前评估未结束时拒绝其他冲突交付。结果回传同时校验 task、delivery、strategy、creative 与 round，过期或跨版本结果不能覆盖当前版本。

业务轮次与技术尝试分开：创意/策略修订后复评增加 round_no；超时、暂时错误或格式修复仅增加 attempt_count。鉴权错误不重试；可重试错误在配置上限内按 1 秒、2 秒间隔重试。技术尝试耗尽后保留已有记录，不生成虚假新分数。

评估执行池当前最多 5 个 worker；这只是实现配置，不等于已经完成真实并发性能或 P95 验收。

## 输出结构

成功评估响应由 `src/agents/evaluation/schemas/evaluation-result.internal.schema.json` 校验，主要字段如下。

| 层级 | 字段 |
| --- | --- |
| 响应头 | schema_version、task_id、agent=evaluation、round_no、attempt_count、status=succeeded、result_id、version、created_at、error=null |
| data 引用 | strategy_result_id、creative_result_id |
| data 评分 | dimension_scores、total_score |
| data 内容 | risks、feedback、recommended_action、decision |

五维固定为 attraction、audience_fit、clarity、channel_fit、call_to_action。每维含 score（0～100 整数）、reason、target_path。平均分由程序等权计算并保留一位小数，模型不能直接决定总分或最终通过。

风险项含 category、severity、target_path、evidence、description。category 允许 fact/constraint/compliance/brand/audience；severity 为 low/medium/high。事实错误风险保守提升 high；原始模型草稿仍保留在来源记录供核对。

反馈项含 feedback_id、evaluation_id、resolved、target_agent、target_path、issue、suggestion、priority。target_agent 为 strategy 或 creative；priority 为 low/medium/high。路径示例为 `strategy.positioning`、`strategy.channels[0].reason`、`creative.items[0].copy`，相对于各 agent 的 data；不要再添加 `.data`。

模型草稿可提供 `resolved_feedback_ids`，仅允许确认输入中已存在且本轮已消除的问题；未知 ID、重复 ID，或当前同一位置仍有问题时的确认会被拒绝。完整历史行不可变，解决状态保存在独立 `feedback_status` 中。

bundle 中 records 保留各轮输入与输出；final 记录 decision、assessment_status、termination_reason、selected_evaluation_id、task_status 等。v2 的 pending_feedback、pending_high_feedback_count 表示上轮仍待确认的反馈，它们不是本轮新识别风险的重复分数。页面单独说明上轮严重问题待复核。

## 决策和终止

| 系统 decision | 含义 | B 状态 |
| --- | --- | --- |
| accept | 达到通过线、无当前严重风险且无 v2 未确认历史严重问题 | passed |
| regenerate_creative | 仍需优化且只有创意问题 | returned |
| regenerate_strategy | 仍需优化且涉及未解决策略问题，策略优先 | needs_strategy |
| stop_not_passed | 轮次到上限，从安全版本中选择较优版本 | not_passed |
| stop_needs_review | 到上限仍无安全版本，保留风险较少版本人工复核 | not_passed，另保留 assessment_status=needs_review |

safe 版本排除严重风险及 v2 未确认历史严重问题。安全版本按分数高、同分版本新选择；全都不安全时按严重问题少、中等风险少、分数高、版本新选择。技术失败不伪装成业务未达标。

最终复制或导出必须绑定 `selected_evaluation_id` 指向的整组策略、创意与评估。查看历史不能改变最终交付对象，不能拿最后一轮评估拼接较早创意。

## 回传 B

创意路径去掉 `creative.` 前缀，例如 `creative.items[0].copy` 转成 `items[0].copy`。同一字段多个问题合并；历史未解决问题按源渠道名称对应到当前渠道，不能直接套用旧数组下标。

B 单次修订最多 15 个路径。超过时优先传严重问题，余项保留在 `deferred_items` 和完整报告中，不丢弃也不把整次评估变成技术失败。已移除渠道的旧问题仍留在历史中，不能强行创建不存在的编辑字段。

只涉及创意时保留原策略，B 定向修订后产生新创意编号及版本，再交付评估。策略问题不能让 B 擅自改写策略。

## 交回 A

`GET .../evaluation/strategy-handoff` 仅在评估成功、decision 为 regenerate_strategy 且未达到上限时提供内容，schema_version 为 `c-to-a-feedback-candidate-v1`。

主要字段为 task_id、strategy_revision_request、creative、evaluation、unresolved_feedback、strategy_feedback、pending_creative_feedback、evaluation_config_snapshot、next_action。

strategy_revision_request 经 A 的 `StrategyRequest.from_dict` 校验：agent=strategy、round_no 增一、attempt_count=1、requirements 保持原样、strategy/creative 为 null、previous_result 为当前完整策略、feedback 仅含未解决策略问题。原 A/B config_version 与评估冻结配置分开保留。

服务层接收该请求并生成新策略版本已有测试，但 A 的公开网页修订路由和 B 新策略在线接收尚未接通。不可据此标记 A 在线闭环完成。

页面默认导出本地生成的 `.docx` Word 策略修改单，供人工阅读与编辑，不上传任务数据生成文档。系统内部的 `c-to-a-delivery-candidate-v1` 快照和 JSON 报告保留程序引用。Word 不用于机器报告回读；下载不等于 A 已接收。最终通过或终止方案交用户，不一概交给 A。

## 错误处理

错误对象至少有 code 和 message；模型错误可能另有 field、retryable。业务/输入错误通常返回 HTTP 400，会话/归属错误按共享后端返回，不假定所有错误都使用同一状态码。

| 错误码 | 处理 |
| --- | --- |
| CONFIG_INVALID | 模型或受控参数缺失/非法，修正服务端配置 |
| MODEL_AUTH_FAILED | 密钥或权限错误，不重试、不暴露原始供应商正文 |
| MODEL_TIMEOUT / MODEL_UNAVAILABLE | 在技术尝试上限内重试，耗尽后保留旧版本 |
| OUTPUT_INVALID | 非法评分、类型或路径，按具体字段有限修复 |
| INPUT_INVALID | 契约、正文或请求字段非法，不启动真实评估 |
| STALE_VERSION | 创意/策略/交付引用过期，重新读取当前版本 |
| BUSY | 已有冲突任务运行，读取原任务状态 |
| ROUND_LIMIT | 已终止、超过上限或轮次不连续 |
| STRATEGY_FEEDBACK | 策略问题尚未提供合法新策略 |
| EVALUATION_FAILED | 其他执行失败，已有结果保留 |

HTTP 状态成功也要检查 B delivery 中的 evaluation_error。响应、事件、导出和文档不得包含密钥、供应商原始异常正文或内部推理。

## 测试与验收

```powershell
python -m unittest discover -s tests -q
node tests/frontend/test_evaluation.cjs
node tests/frontend/test_creative_v6.cjs
node tests/frontend/test_brief.cjs
node tests/frontend/test_diagnostics.cjs
node tests/frontend/test_presentation.cjs
node tests/frontend/test_result.cjs
```

本次 182 项 Python 测试、6 组前端测试通过。单元和 HTTP 测试使用注入模型，真实模型证据另外记录，不混算。

离线页面 `python -m src.agents.evaluation.preview --port 8765` 可验证确定性规则，不产生真实模型结论。`python -m ops.run_evaluation_acceptance --url 服务地址 --output artifacts/目录` 会收费调用真实 A/B/C；使用公开虚构输入，策略交回 A 只记为交接，不算闭环成功。正式 50 例和人工复核未完成。

最新独立真实评估使用公开 B 输入，57.4 分、策略反馈、1 次技术尝试、17.04 秒；不代表整体方案生成时间，也不是普遍时延保证。详细记录见 [评分与性能复核](效果评估评分与性能复核.md)。

## 集成边界

任务、会话和版本仍在进程内存，重启不恢复。A 在线策略修订、B 接收新策略、数据库与生产恢复、独立服务认证及正式性能验收仍待集成。源码不含 env、密钥、Cookie、虚拟环境、用户实际任务及运行日志；本机运行记录不作为仓库配置依赖。
