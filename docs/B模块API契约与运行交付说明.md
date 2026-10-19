# B 模块 API 契约与运行交付说明

版本：1.0｜日期：2026-10-19｜依据：当前交付源码。

本文是《B 模块交付与 C 对接说明》的工程附录，描述**已经实现的接口行为**。B→C 数据仍为内部候选协议；真实 C 服务、回调鉴权及评估结果协议尚未完成，本文不将其宣布为已上线的正式公共接口。

## 1. 运行与配置

在项目根目录执行，要求 Python 3.11+；Node.js 仅用于前端验证。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "jsonschema>=4.23,<5"
.\.venv\Scripts\python.exe app.py --host 127.0.0.1 --port 8003 --provider compatible --creative-provider compatible
```

先在服务端配置模型。A 沿用根目录 `.env.example` 中的 `MODEL_*` 配置；B 使用下表。B 配置可由进程环境提供，或由根目录 `.env.creative` 加载；同名环境变量优先。模板为 `.env.creative.example`，模板不含真实密钥。密钥只留在服务端，不提交 Git，不放入前端或交付压缩包。

| B 环境变量 | 必填／默认值 | 实际约束 |
| --- | --- | --- |
| `CREATIVE_MODEL_BASE_URL` | 必填 | HTTPS、OpenAI-compatible chat/completions；服务支持 JSON mode；地址不得带凭据、查询串或片段。 |
| `CREATIVE_MODEL_API_KEY` | 必填 | 服务端模型密钥。 |
| `CREATIVE_MODEL_NAME` | 必填 | 模型服务支持的名称。 |
| `CREATIVE_MODEL_TIMEOUT_SECONDS` | 120 | 单次模型请求 10～120 秒。 |
| `CREATIVE_MODEL_TEMPERATURE` | 0.5 | 0～2 的有限数值。 |

普通启动不启用模拟 C。仅开发联调需要时在启动命令末尾加 `--creative-demo`；关闭后模拟反馈返回 `DEMO_DISABLED`。

页面入口：`http://localhost:8003/workspace`。A 成功后点击“校验并交付给创意智能体”，确认接收后进入 `/creative?task_id=实际任务ID`。访问全程使用同一主机名，不要混用 `localhost` 与 `127.0.0.1`。

`GET /api/health` 可检查服务存活，但其模型配置报告主要面向 A，**不能证明 B 密钥有效或真实 C 已接通**。B 模型配置在生成时读取；先完成不付费的 mock 测试，再按需验证真实生成。

## 2. 会话、请求与 HTTP 约定

- 先请求 `GET /api/session`，服务设置 `zhice_session` Cookie（`HttpOnly; SameSite=Strict; Path=/`）。后续由同一浏览器或同一个 HTTP Cookie 容器携带。
- 服务端据 Cookie 推导 `owner_scope`，客户端不得指定。缺少有效会话、任务不存在或属于其他会话，返回 **403 / `ACCESS_DENIED`**。
- 这是现有本地演示会话隔离，尚不是账号登录、跨设备授权或 C 服务身份认证。当前 Cookie 未设置 `Secure`；对外部署前需另行完成 HTTPS、认证及访问控制方案。
- POST 使用 `Content-Type: application/json`；请求正文为对象，大小为 **1～100000 字节**。写接口拒绝未声明的顶层字段。
- 成功 GET、接收、交付及模拟反馈返回 **200**；异步操作接收返回 **202**。响应直接是 JSON 对象，没有统一的 `data` 外壳；策略业务数据在 `handoff.strategy.data`，创意正文在 `versions[n].data`。
- B 同步业务异常目前统一返回 **400**，包括版本冲突、忙碌及真实 C 未接通；不能假定这些情况返回 409、422 或 503。

## 3. 接口清单

下表 `P` = `/api/tasks/{task_id}/creative`。除会话和健康检查外，所有接口均需要当前任务的有效会话。

| 方法与路径 | 请求 | 成功响应／作用 |
| --- | --- | --- |
| `GET P/handoff` | 无正文 | 200，`handoff/context/checks`；读取并校验真实 A 交付。 |
| `POST P/accept` | `{}` | 200，B 工作区记录；同一策略重复接收复用记录，策略变化拒绝混用。 |
| `GET P/state` | 无正文 | 200，完整工作区记录及最新后台任务。 |
| `GET P/history` | 无正文 | 200，与 state 相同的完整记录，含所有 `versions`。 |
| `GET /api/creative/history` | 无正文 | 200，`{"items":[...],"storage":"process-memory"}`；当前会话任务摘要，当前 UI 未提供历史入口。 |
| `POST P/operations` | 见下节 | 202，后台 job；不代表生成成功。 |
| `GET P/package?result_id=当前ID` | 当前创意 ID | 200，B→C 候选输入包；这是读取／检查，不记录交付。 |
| `POST P/delivery` | `{"base_result_id":"当前ID"}` | 200，交付记录；锁定版本并进入 `pending`，没有调用真实 C。 |
| `POST P/demo-feedback` | `base_result_id/decision/items` | 200，带 `development/demo only` 标识的模拟评估结果，仅开发模式可用。 |
| `POST P/feedback` | 目前同上 | **当前始终拒绝真实反馈，400 / `C_NOT_CONNECTED`**；不承诺未来正式请求沿用此格式。 |

### 3.1 异步操作请求

允许的顶层字段为 `action/base_result_id/channel/instruction/path/value`。不要提交完整 strategy 或 creative 覆盖服务端记录。`instruction` 可选，默认空字符串，最长 2000 字。

| action | 使用字段及行为 |
| --- | --- |
| `generate` | `channel` 必须精确匹配 A 的渠道名；生成该渠道四类文字，已有渠道则替换该渠道，其他渠道保留。首次 `base_result_id=null`。 |
| `edit` | `path` 与字符串 `value`；保存单字段人工修改，不调用模型。 |
| `regenerate` | `path`，可附 `instruction`；模型仅重生成该字段。 |
| `refine` | `path`，可附 `instruction`；模型基于当前字段润色。 |
| `revision` | 当前 `base_result_id`，可附 `instruction`；读取服务端最新退回反馈，只修订指定路径。 |

除首次生成外，`base_result_id` 均使用 `versions` 最后一项的真实 ID。字段路径为相对于 `creative.data` 的 `items[索引].copy/slogan/poster_concept/video_script`；不得加 `creative.data.` 前缀。索引应从待评估版本读取，不能跨版本猜测复用。

首次生成示例（渠道名必须替换为实际策略值）：

```json
{"action":"generate","base_result_id":null,"channel":"实际策略渠道名","instruction":"语气自然，不新增优惠"}
```

人工保存与单项润色示例：

```json
{"action":"edit","base_result_id":"creative-实际当前ID","path":"items[0].slogan","value":"用户修改后的短句"}
```

```json
{"action":"refine","base_result_id":"creative-实际当前ID","path":"items[0].slogan","instruction":"更简洁，保留原意"}
```

202 响应示例（ID、时间为占位示例）：

```json
{
  "job_id":"job-实际ID","status":"running","stage":"queued",
  "action":"generate","attempt_count":1,
  "created_at":"2026-10-19T00:00:00Z","error":null,
  "operation":{"action":"generate","base_result_id":null,"channel":"实际策略渠道名","instruction":"语气自然"}
}
```

job 在线程池中可能已经开始执行，收到响应时 `stage` 不保证仍为 queued。轮询 `GET P/state`（现有前端约每 700ms），直到 `job.status=succeeded` 或 `failed`。阶段包括 `queued/reading/generating/parsing/validating/saving/completed/failed`，人工保存跳过模型阶段。成功后读取 `versions` 最后一项；失败读取 `job.error` 和 `last_error`，旧版本不被替换。

### 3.2 工作区与创意数据结构

工作区包含 `handoff/context/checks/versions/deliveries/feedback/events/job/state/last_error/demo_enabled/storage`。未提交过操作时 `job=null`，`versions=[]`。接口返回的是全量记录，当前未实现分页。

每个创意版本包含：

| 字段 | 含义 |
| --- | --- |
| `schema_version` / `agent` / `status` | 当前分别为 `b-internal-candidate-v1` / `creative` / `succeeded`。这里只代表 B 成功生成保存。 |
| `task_id/result_id/version` | 原任务、唯一创意结果 ID、递增创意版本号。 |
| `strategy_result_id/strategy_version` | 所依据的 A 策略 ID 与版本，不能由 B 改写。 |
| `previous_result_id` | 上一创意版本 ID，首版为 null。 |
| `round_no/attempt_count` | 业务评估轮次 1～3／本次操作技术尝试 1～2，二者独立。 |
| `created_at/config_version/creative_instruction` | UTC ISO 时间、配置引用及本次创意补充要求。 |
| `data.items` | 1～5 个渠道结果，结构见下例。 |
| `checks` | 新结果 `structure=true`，`facts/constraints/semantic_review=false`；不是 C 通过标志。 |
| `edit_trace/feedback_applied/error` | 修改路径、修改前后与来源；本版应用的反馈；成功结果 error 为 null。 |

`data` 结构示例（仅解释格式，不是产品案例或真实生成结果）：

```json
{
  "items":[{
    "channel":"实际策略渠道名",
    "copy":"广告正文及行动引导",
    "slogan":"核心短句",
    "poster_concept":"【标题】海报标题\n画面及文字构思",
    "video_script":"0–5s 开场画面\n5–15s 产品说明与行动引导",
    "evidence":[{"claim":"创意中的对应表述","source_quote":"产品原文引用"}],
    "pending_confirmations":["发布前需确认的信息"]
  }]
}
```

长度按 Python 字符串 `len` 计算：copy ≤500、slogan ≤30、poster_concept ≤1000、video_script ≤2000，四项均非空。海报必须有 `【标题】`，标题 1～40 字；视频分镜从 0 开始连续不重叠，总时长 15～60 秒。每渠道 evidence 1～5 条，claim/source_quote 各 1～1000 字；pending_confirmations 最多 12 条，每条 1～300 字，可为空数组。

这些检查只验证格式和渠道引用，不保证 evidence 在语义上真实支持广告正文。人工修改后 evidence 文本可能仅作随附依据，C 必须重新核验原文、表述及约束。

## 4. B→C 交付及反馈契约边界

### 4.1 当前实际交付

交付前检查当前版本、结构、全部策略渠道已生成、没有待处理退回、没有上游约束冲突、任务与策略引用一致。未保存编辑由前端阻止；服务端只认识已保存版本，无法感知浏览器中尚未提交的草稿。

候选包顶层字段如下，**完整对象以 Schema 为准，不可把下面的字段表当成简化请求**：

| 字段 | 内容 |
| --- | --- |
| `schema_version` | 固定 `b-to-c-internal-candidate-v1`。 |
| `task_id` | 同一任务。 |
| `requirements` | 完整原始用户需求。 |
| `strategy` | A 的完整响应对象，业务内容在其 `data` 内。 |
| `creative` | 当前完整 B 版本，含来源、正文、版本及修改记录。 |
| `round_no` | 当前业务轮次 1～3。 |
| `evaluation_status` | 固定 `pending`，不是已评估。 |
| `feedback_trace` | 既往评估反馈记录；首轮为空数组。 |

交付响应形状：

```json
{
  "delivery_id":"delivery-实际ID","created_at":"2026-10-19T00:00:00Z",
  "status":"pending","evaluation_id":null,"mode":"pending_real_c",
  "package":{}
}
```

上例仅省略了 `package` 正文；实际响应含上述完整候选包，不是空对象。此时已记录交付但**没有真实队列投递、C 网络调用或真实评估结果**。同一版本处于 pending 时重复 delivery 返回原交付记录。C 模拟完成后交付记录的 mode 会变为 `development/demo only`。

### 4.2 模拟反馈与 B 修订

以下请求只用于 `POST P/demo-feedback`，不是正式 C 回调契约：

```json
{
  "base_result_id":"creative-本次交付ID",
  "decision":"return",
  "items":[{
    "target_agent":"creative","target_path":"items[0].slogan",
    "issue":"行动方向不够明确","suggestion":"保留事实并明确下一步行动","priority":"medium"
  }]
}
```

通过时使用 `decision=pass`，不传 items。退回反馈 1～15 条，同一路径不可重复；priority 为 low/medium/high，issue/suggestion/target_path 各 1～1000 字。目标为 strategy 或涉及策略字段时进入 `needs_strategy`，B 不修改策略。

模拟结果包含 `evaluation_id`（`demo-evaluation-` 前缀）、`mode=development/demo only`、`task_id`、`creative_result_id`、`strategy_result_id`、`round_no`、`decision`、`items`、`created_at`、`scores=null`、`final_status`。没有真实分数。B 收到可修订反馈后提交：

```json
{"action":"revision","base_result_id":"creative-被退回ID"}
```

B 再次调用生成模型，保留旧结果，新增版本。真实 C 接入后可复用 B 修订能力，但须先实现真实认证与反馈写入，不能只把 demo 地址换成 feedback。

### 4.3 C 负责人待确认／实现

- 实现评估模型与事实、约束、风险检查，约定评分、通过阈值和报告结构。
- 确认候选 Schema，增加真实服务调用／调度、C 服务身份认证、回调权限、超时与失败状态处理。
- 确认反馈绑定的 task、strategy、creative、evaluation 及轮次；防止过期、重复或乱序反馈。当前真实回调尚无可验收的幂等契约。
- 反馈精确定位创意字段，策略类反馈交 A；与 B 联调最多三轮的返回、修订、再次交付及终止。
- 正式部署前共同明确持久化、恢复、审计及最终结果选取规则。上述待办均不能以当前模拟测试代替验收。

## 5. 状态、并发与重试

| 工作区 state | 当前含义／后续操作 |
| --- | --- |
| `ready` | 已接收或成功保存，可继续创作；判断是否已有创意还需查看 versions。 |
| `pending` | 版本已交付，等待评估；禁止继续编辑该版本。 |
| `returned` | 创意被退回，可提交 revision。 |
| `needs_strategy` | 反馈涉及策略，应返回 A，B 不可自行修复策略。 |
| `passed` | 当前仅模拟评估可到达的通过终态；禁止继续操作。 |
| `not_passed` | 第 3 轮仍退回的终态；禁止生成业务 round 4。 |

job 状态独立为 `running/succeeded/failed`。业务轮次首轮为 1，仅反馈 revision 成功后递增；人工保存、润色、单项重生成不会增加 round_no，版本号则随每次成功保存递增，因此 version 可以大于 3。

每次写入用 `base_result_id` 比较最新版本；过期返回 `STALE_VERSION`，有正在运行操作返回 `BUSY`。当前不是通用 Idempotency-Key 方案。操作请求超时或响应丢失时先读 state，核对 job 及最新结果，不要直接重发付费生成；刷新页面只恢复轮询。

仅模型 JSON／结构输出不合格允许最多一次格式修复，总计最多两次生成调用。超时、鉴权和网络错误不自动再次调用；单次 timeout 不是整个任务的总时限。人工保存不调用模型。服务线程池为进程内最多 3 个 B 工作线程，无持久化队列、取消接口或断点恢复保证。

## 6. 错误契约

B 同步业务错误示例：

```json
{
  "status":"failed",
  "error":{"code":"STALE_VERSION","message":"当前版本已变化，请刷新后重试","issues":[],"retryable":false}
}
```

| code | 常见原因／处理 |
| --- | --- |
| `ACCESS_DENIED` | 403；检查会话和任务归属。A 公共错误对象含 field 而非 issues。 |
| `INPUT_INVALID` | 400；JSON、字段或参数非法。JSON 解析错误的响应可能仅有 code/message。 |
| `STRATEGY_NOT_READY` / `HANDOFF_REQUIRED` | A 尚未完成／B 尚未接收。 |
| `STALE_STRATEGY` / `STALE_VERSION` | 策略引用／最新创意版本不一致，重新读取，勿覆盖旧数据。 |
| `BUSY` / `VERSION_LOCKED` | 等待当前任务完成／等待已交付版本反馈。 |
| `CHANNELS_INCOMPLETE` / `STRATEGY_CONFLICT` | 尚有策略渠道未生成／策略约束冲突。 |
| `FEEDBACK_INVALID` / `FEEDBACK_PENDING` / `STRATEGY_FEEDBACK` | 反馈非法、未处理或涉及 A。 |
| `ROUND_LIMIT` | 已终止或超过业务轮次限制。 |
| `CONFIG_INVALID` / `MODEL_AUTH_FAILED` | 模型未启用、配置非法、密钥或模型权限无效。 |
| `MODEL_TIMEOUT` / `MODEL_UNAVAILABLE` | 模型超时／服务不可用；查明状态后由用户决定重试。 |
| `OUTPUT_INVALID` / `SAVE_FAILED` | 响应非法或处理保存失败；保留原有效版本。 |
| `DEMO_DISABLED` / `C_NOT_CONNECTED` | 未开启模拟／真实 C 尚未接通。 |

异步失败不会把先前 202 改成 HTTP 错误；读取 state 仍是 200，应检查 job.error。`retryable` 不是自动重发授权，客户端应容忍该字段缺失。B 的上述模型错误经 CreativeError 处理时同步返回400，异步则记录于 job；不要把模型服务原始 HTTP 状态当作本 API 状态。

## 7. 联调、验收与运行限制

最小联调顺序：

1. 同一会话在 A 生成成功策略，记录 task_id；检查 handoff，POST accept。
2. 按实际渠道 generate，轮询 job；逐一完成全部策略渠道，确认四类字段与策略引用。
3. 人工保存一个字段，核对新增版本；单项润色后核对其余字段保持不变。
4. GET package，POST delivery，确认 pending、evaluation_id=null、完整输入包与锁定版本一致。
5. **开发模式**提交模拟退回，执行 revision，确认新旧版本及轮次；再交付测试第 3 轮终止。另测模拟通过。以上不能证明真实 C 正常。
6. 换一个独立 Cookie 容器请求同一 task，应为403。正式 C 接入后还须另行验收服务认证、真实评估、反馈幂等及完整业务闭环。

自动化命令（mock 模型，不消耗付费 API）：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
node tests/frontend/test_diagnostics.cjs
node tests/frontend/test_brief.cjs
node tests/frontend/test_presentation.cjs
node tests/frontend/test_result.cjs
node tests/frontend/test_creative_v6.cjs
```

代码阶段已记录 138 项 Python 测试、5 组前端验证通过；本次仅补文档，没有重新执行付费生成，也未重新运行测试。多轮、会话隔离及异常测试范围见 `tests/unit/test_creative_v6.py`。

当前是单进程内存存储，重启后任务、会话和版本不保留。停止前导出已保存 JSON／文字，导出文件不等于可自动恢复的数据库备份；当前无正式导入恢复接口。不要部署多个不共享内存的工作进程来承接同一会话。

正文日志仅有 HTTP 摘要，错误返回不暴露密钥或模型内部推理；没有完整生产监控或审计平台。本交付适合本地运行与 C 联调，不以“已启动”“已交付”冒充生产持久化或真实效果评估完成。

## 8. 契约定位

- B HTTP 路由：`src/backend/creative_web.py`。
- 状态、版本与交付规则：`src/backend/creative_workspace.py`。
- 字段限制与反馈路径：`src/agents/creative/validation.py`。
- 内部候选输出：`src/agents/creative/schemas/creative-result.internal.schema.json`。
- B→C 内部候选输入：`src/agents/creative/schemas/evaluation-request.internal.schema.json`。
- 原公共 A→B 契约：`packages/contracts/`，本次未修改。

如实现与说明有差异，应先据源码及测试核实；对正式公共协议的变更须由 A/B/C 共同确认，不由本说明替代团队确认。
