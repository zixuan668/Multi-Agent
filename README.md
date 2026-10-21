# 智策营销 · 多智能体交互广告营销工作台

从真实产品需求出发，完成 **策略方向 → 创意成品 → 效果评估与修改**。三个智能体共享带版本的结果与原文依据，用户参与选方向、补充事实、指定修改范围和确认交付，而不是面对三个互不关联的聊天窗口。

- **李智信｜策略负责人**：梳理目标、受众、产品事实与渠道，形成营销策略。
- **李莉｜创意负责人**：依据策略生成渠道文案、独立海报短稿与画面制作方案。
- **毛小纯｜独立评估**：核对实际策略和创意，给出五维参考分、风险、原文依据及修改建议。

评估针对投放前方案，不预测真实点击率、转化率或销量；生成的宣传图仍需人工验收。

## 已实现功能

- **可见的协作过程**：实际阶段、公开草稿、角色交接与修改记录，不展示内部思维链。
- **两种创作路径**：默认直接成稿，也可先选择两个创意方向再深化。
- **有依据的修改闭环**：创意问题复用策略，策略问题先修改策略；支持只改标题、正文、CTA或视觉方案。
- **真实任务评估**：顶部、侧栏或毛小纯角色卡均可直达，直接查看评分、风险、建议与历史版本。
- **火山引擎宣传图**：先预览和编辑海报方案，再显式确认单张付费生图，支持原图预览、下载与历史结果。
- **任务管理**：SQLite保存、失败阶段续跑、取消、单条删除、批量清空及回收站恢复。
- **离线联调**：独立规则样例验证接口和交互，不冒充真实模型输出。

## 快速启动

### 1. 环境与代码

Python **3.11及以上**，应用运行时仅依赖Python标准库；Node.js仅用于前端测试。文字服务须支持HTTPS `chat/completions` 和JSON对象输出。

```powershell
git clone --branch main https://github.com/zixuan668/Multi-Agent.git
cd Multi-Agent
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

### 2. 配置文字模型

在本机 `.env` 填入服务信息，以下仅为占位示例：

```dotenv
MODEL_BASE_URL=https://your-model-service.example/v1
MODEL_API_KEY=replace-with-your-key
MODEL_NAME=your-model-name
MODEL_TIMEOUT_SECONDS=60
MODEL_TEMPERATURE=0.2
MODEL_STREAMING=true
```

其他参数以 `.env.example` 和服务支持情况为准；不支持SSE的兼容服务可设置 `MODEL_STREAMING=false`。默认使用真实模式，配置缺失会报错，不自动切换到离线样例。

### 3. 启动工作台

```powershell
python app.py --provider compatible --port 8765
```

- [创作工作台](http://127.0.0.1:8765/workspace)
- [已保存任务的效果评估](http://127.0.0.1:8765/workspace?view=evaluation)
- 单个任务评估：`/workspace?task=任务ID&pane=review`
- `/strategy` 保留策略专用页面；`/evaluation/demo/` 是预设规则演示，不是业务任务评估。

不传 `--port` 时默认端口为8000。配置修改后重启服务，不要覆盖已有密钥文件。

## 配置宣传图生成

图片服务与文字模型使用独立配置：

```powershell
if (-not (Test-Path -LiteralPath .env.images)) { Copy-Item .env.images.example .env.images }
```

填写本机 `.env.images`，然后重启服务：

```dotenv
IMAGE_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
IMAGE_API_KEY=replace-with-your-image-key
IMAGE_MODEL=your-purchased-model-or-endpoint-id
IMAGE_SIZE=2K
IMAGE_TIMEOUT_SECONDS=180
IMAGE_WATERMARK=false
```

模型须已开通且额度可用。标准按量服务与Agent Plan套餐的调用地址不同，须使用购买服务对应的控制台配置，不混用计费接口。

### 海报制作流程

1. 在“创意成品”点击“制作宣传图”，免费读取本轮方案，不调用文字或图片模型。
2. 确认一个传播诉求、22字以内标题、一行辅助文字、可选短行动、版式和唯一主视觉；这些内容均可编辑。
3. 点击“确认并生成1张（计费）”，向已配置的火山引擎服务提交一次请求。
4. 返回后查看、下载原图，人工核对中文、产品事实、画面空间及产品外观。

李莉的新交付必须包含 `visual_brief.poster`。生图编译器不再把长正文、长CTA和旧版复杂场景说明整段传入，而是限定文字白名单、最多两行标题、8%安全边距、单一透视与光向，避免多屏拼贴、密集小字和虚构App界面。默认2K时用明确像素尺寸约束所选比例。旧版任务可先编辑带提示的保守方案，不自动重跑。

`IMAGE_WATERMARK=false` 关闭供应商可选的可见角标，设为 `true` 可开启。工作台始终保留AI来源与待审核说明，不修抹已有图片或移除返回文件中的来源元数据。已有图片不会因提示词更新自动改变；约束也不能保证模型每次都正确，发布前仍需验收并核对渠道标识要求。

**计费保护**：刷新、轮询、预览方案和恢复历史不会自动生图；不自动重试、换模型或关闭费用保护。同一提交标识去重，进行中的同一创意请求合并，每个任务最多6次生图请求。超时、中断或重启不意味着供应商未计费，重新提交前应核对结果。

## 日常使用与任务管理

1. 填写产品事实、目标、受众和明确约束。必要转化入口缺失时先补充，不让模型编造。
2. 直接成稿，或先选择创意方向。正常无重试的直接成稿首轮为策略、创意、评估各一次调用。
3. 查看毛小纯的风险与建议。未达标时由用户决定继续，不自动连跑多轮。
4. 发送修改意见或指定修改范围；需要补充原始事实时创建关联续作，保留原任务。
5. 确认采用方案，复制文案、下载报告，或按需制作宣传图。不会自动发布广告。

**保存**：默认数据库为 `artifacts/campaigns.sqlite3`；原图保存在数据库同级 `images/` 中。任务记录对应文字版本、海报方案、提示词版本、模型、状态、尺寸和文件指纹。重启保留结果，中断的文字任务由用户决定是否续跑。

**删除与恢复**：侧栏支持单条删除与批量清空已结束任务，操作前确认并移入回收站，保留版本与图片。正在生成文字或图片的任务不可删除，批量清空会跳过。恢复不触发模型调用；删除后的详情、报告及图片接口在恢复前不可访问。

**执行上限**：默认3个并行文字任务，同一会话最多5个活动任务；每个任务最多三轮、16次文字模型请求和360秒活动执行时间。取消会阻止后续结果提交，已发出的供应商请求可能继续执行。

## 离线演示与验证

仅验证流程、不希望调用真实模型时，显式启动离线实例并使用独立数据库：

```powershell
python app.py --provider offline --port 8766 --database artifacts/campaign-offline.sqlite3
```

离线模式默认禁用付费生图，界面明确标记规则输出，不能验证真实创意质量。

运行Python测试与全部前端测试：

```powershell
python -m unittest discover -s tests -v
Get-ChildItem tests/frontend/test_*.cjs | ForEach-Object {
    node $_.FullName
    if ($LASTEXITCODE -ne 0) { throw "Frontend test failed: $($_.Name)" }
}
```

自动测试覆盖契约、事实依据、反馈路由、局部修改、版本一致性、恢复与取消、会话隔离、任务回收站、海报方案编译及生图请求去重。图片接口测试使用本地替身，不消费真实生图额度。

`scripts/benchmark_campaign.py` 可对比同一需求、同一文字模型的单次直出与多角色首轮结果。默认不调用付费服务，必须显式加 `--live`；可复用同需求、同模型的基线。报告记录输出、耗时和用量，不按模型自评分宣布赢家，质量需要人工盲评。

## 安全与能力边界

- `.env`、`.env.images`、密钥、数据库、报告与生成图片均不提交Git；仓库只保留配置示例。
- 默认仅监听本机。Cookie用于工作空间隔离，不是完整账号系统，不应直接暴露到公网。
- 文字评估会核对海报制作稿，但未实现对真实生成图片的自动视觉审核。
- 无实物参考时，产品外观是创意示意，不代表真实产品摄影；未实现视频生成、自动投放或真实效果预测。
- 记录调用次数及供应商返回用量，不虚构费用；多智能体尚未证明始终优于单次LLM调用。

## 代码与文档

- `src/agents/strategy/`、`creative/`、`evaluation/`：三类智能体。
- `src/backend/`：调度、SQLite存储、回收站、生图方案编译与HTTP接口。
- `src/contracts/`、`packages/contracts/`：公共校验与JSON Schema。
- `prompts/`：角色职责、交付要求与版本化提示词。
- `web/campaign/`：统一工作台；`web/evaluation/`：独立离线规则演示。
- [三智能体实现与接口边界](docs/multi-agent-workflow.md)
- [实时协作与人工修改](docs/interactive-collaboration.md)
- [01 策略模块](docs/01-strategy-agent.md) · [02 创意模块](docs/02-creative-agent.md) · [03 评估模块](docs/03-evaluation-agent.md)
- [离线评估演示说明](docs/evaluation-workbench.md)
- [策略人工复核模板](docs/strategy-human-review.md)
- [首轮创意交接指南与联调样例](docs/02-creative-handoff-guide.md)：保留v1.0策略交接参考，统一三智能体流程使用v1.1契约。
