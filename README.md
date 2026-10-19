# 智策营销 · 多智能体协作系统

> 本分支已接入 B v6 与 C 真实评估，运行和集成请先看 [C 交付说明](docs/C模块交付与A集成说明.md)。B 原交付记录见 [B v6 实现说明](docs/B-v6-implementation.md)，其中 C 未接通的描述属于 B 原始交付时点。当前共享任务仍是进程内存，重启不保留。

一个由三人共同开发的广告营销项目，通过 **营销策略、创意生成、效果评估** 三个智能体，将产品需求逐步转化为可执行、可复核的营销方案。

> 当前进度：已在 C 功能分支合入 A 策略与 B v6，接通 B 交付 → C 真实模型评估 → B 指定字段修订 → 再评估。C 提供五维评分、事实风险否决、最多三轮与最终版本选择。策略问题交回 A 的反馈包已提供；A 在线优化回接、数据库持久化及整套系统正式验收仍待集成。接口仍为内部候选协议。

## 文档导航

- [01 · 营销策略智能体](docs/01-strategy-agent.md)：运行方式、现有功能、策略接口与阶段验收。
- [02 · 创意生成智能体](docs/02-creative-agent.md)：职责边界、已存在的首轮输入契约与开发前核对事项。
- [创意负责人开工说明书](docs/02-creative-handoff-guide.md)：完整请求读取、12 份合法/非法联调样例、文字创意制作思路与联调清单。
- [策略人工复核模板](docs/strategy-human-review.md)：AC-004～AC-006、执行性及创意接续检查；待人实际填写。
- [03 · 效果评估智能体](docs/03-evaluation-agent.md)：职责边界与待团队确认的评估对接事项。
- [C 模块交付与 A 对接说明](docs/C模块交付与A对接说明.md)：交付功能、责任流向、A/B 接续事项和验证范围。
- [C 模块 API 契约与运行交付说明](docs/C模块API契约与运行交付说明.md)：配置、HTTP 接口、数据结构、错误和联调方法。
- [C 模块需求复核与修正记录](docs/C模块需求复核与修正记录.md)：交付对象、需求核对、本次修正、验证与剩余边界。
- [效果评估评分与性能复核](docs/效果评估评分与性能复核.md)：跨轮严重问题阻断、等待时间、统一页面布局及新版入口。
- [三人协作与目录规范](docs/team-collaboration.md)：代码归属、分支流程、公共接口变更和联调要求。

## 三个智能体的顺序与分工

以下成员 A / B / C 是分工占位，请团队确认后填写实际负责人。

### 01 · 营销策略智能体 / Strategy

- **负责成员**：A（待填写姓名）。
- **职责**：分析产品事实、目标用户与资源约束，形成定位、卖点、渠道和预算建议。
- **输入 → 输出**：原始营销需求 → 结构化策略，以及通过首轮校验的创意请求。
- **代码 / 提示词**：[`src/agents/strategy/`](src/agents/strategy/) / [`prompts/strategy/`](prompts/strategy/)。
- **当前状态**：开发版可运行；真实质量回归、人工复核与正式验收尚未完成。

策略当前使用 v1.10 决策生成与独立短审查；五类页面示例补齐执行条件，结果优先展示营销选择、第一步和反馈检查。程序测试与小样本模型检查不是业务验收，正式50例与人工复核仍须按阶段执行。详见策略模块说明。

### 02 · 创意生成智能体 / Creative

- **负责成员**：B（待填写姓名）。
- **职责**：依据策略发展文案、内容创意与渠道表达，不重写产品事实或擅自修改策略预算。
- **输入 → 输出**：策略首轮交付请求 → 创意结果；输出契约与后续优化请求由团队确认。
- **代码 / 提示词**：[`src/agents/creative/`](src/agents/creative/) / [`prompts/creative/`](prompts/creative/)。
- **当前状态**：已合入 B v6 的真实生成、编辑、版本及反馈修订；详见 [B API 交付说明](docs/B模块API契约与运行交付说明.md)。

### 03 · 效果评估智能体 / Evaluation

- **负责成员**：C（待填写姓名）。
- **职责**：按团队确认的规则检查策略与创意，给出有依据的评估意见和反馈。
- **输入 → 输出**：待评方案与评估规则 → 评估结果与反馈；具体契约待确认。
- **代码 / 提示词**：[`src/agents/evaluation/`](src/agents/evaluation/) / [`prompts/evaluation/`](prompts/evaluation/)。
- **当前状态**：真实模型与 B 闭环已接入；独立页面同时保留离线规则重放。运行和交付给 A 的内容见 [C 交付说明](docs/C模块交付与A集成说明.md)。策略任务自身的 `not_evaluated` 仍不是评估通过。

业务顺序为：**用户需求 → 01 策略 → 02 创意 → 03 评估 → 按问题归属反馈**。仅创意问题可完成在线反馈闭环；策略问题在 C 明确停在交回 A，不能伪造 A 已修改。

## 仓库结构

文档采用 01 / 02 / 03 编号排序；Python 包使用稳定英文名称，不给目录添加数字前缀。

```text
Multi-Agent/
├── README.md                       项目总入口
├── docs/
│   ├── 01-strategy-agent.md         01 策略说明
│   ├── 02-creative-agent.md         02 创意对接说明
│   ├── 03-evaluation-agent.md       03 评估对接说明
│   └── team-collaboration.md        三人协作规范
├── src/
│   ├── agents/
│   │   ├── strategy/               01 策略实现
│   │   ├── creative/               02 B v6 创意生成
│   │   └── evaluation/             03 C 评估、适配与规则
│   └── backend/                    HTTP 服务与任务管理，公共集成区
├── prompts/
│   ├── strategy/                   01 策略提示词
│   ├── creative/                   02 创意提示词 v6
│   └── evaluation/                 03 评估提示词 v1.2（保留旧版）
├── packages/contracts/             跨智能体公共 JSON Schema
├── web/                            首页与工作台，公共前端
├── tests/                          单元、集成、前端与阶段验收测试
├── ops/                            验收与运行辅助工具
├── app.py                          当前策略网页启动入口
├── pyproject.toml                  项目配置
└── .env.example                    本地模型配置模板，无真实密钥
```

创意与评估目录均有实现。公共 `packages/contracts/` 未改；B/C 候选 Schema 分别保留在模块内，供 A/B/C 评审后发布。

## 快速启动当前开发版

需要 Python 3.11 或以上；B/C 候选 Schema 校验依赖 `jsonschema>=4.23,<5`。以下命令在项目根目录执行。

```powershell
git clone https://github.com/zixuan668/Multi-Agent.git
cd Multi-Agent
if (-not (Test-Path -LiteralPath .env)) { Copy-Item .env.example .env }
```

只在首次启动且 `.env` 不存在时复制模板。编辑本地 `.env`，填写模型服务地址、模型名和自己的 API 密钥，然后启动：

```powershell
python app.py
```

- 首页：<http://127.0.0.1:8000/>。
- 策略工作台：<http://127.0.0.1:8000/workspace>。
- 默认使用真实模型，配置缺失会明确报错，不自动回退离线。
- 普通启动提供 A/B；C 需要下文的 `--evaluation` 或集成启动器显式启用。
- `.env`、密钥、缓存和 `artifacts/` 均不提交；每位成员使用自己的本地配置。

模型请求耗时、重试、离线联调及命令行用法见 [01 策略说明](docs/01-strategy-agent.md)。

## 启动包含真实 C 的集成版

复制 `.env.evaluation.example` 为本地 `.env.evaluation`，配置 C 模型。A/B 沿用各自配置；如明确希望三者使用同一模型，可用 `--share-model` 在进程内填充缺省的 A/B 配置，不复制或输出密钥。

```powershell
python -m pip install -e .
python -m ops.run_evaluation_workspace --port 8766 --share-model
```

从 `http://127.0.0.1:8766/workspace` 开始，A 交给 B，B 完成全部渠道后确认交给 C，立即进入 C 查看创意和实际评估阶段，完成后显示结论。`/evaluation/` 无 task_id 时列出当前会话任务，演示须明确点击；`/evaluation/?task_id=...` 消费当前会话真实任务。仅策略问题交回 A 修改，最终方案导出交用户。默认 `python app.py` 仍不启用 C；使用 `--evaluation` 可显式启用。

## 测试与验收

```powershell
python -m unittest discover -s tests -v
```

前端校验记录回归使用 Node.js 运行，无需安装 npm 依赖：

```powershell
node tests/frontend/test_diagnostics.cjs
node tests/frontend/test_brief.cjs
```

自动化测试、离线规则示例和模型辅助复核都不能代替真实模型质量检查及人工验收。正式 50 例真实模型验收会产生费用，应先完成少量案例检查，再由团队确认后执行；不能据策略成功生成，宣称创意、评估或整个系统验收通过。

## 三人协作：先看这五条

1. 各自智能体的业务代码放在自己的 `src/agents/<模块>/` 下，提示词放在对应 `prompts/<模块>/` 下；不要放进根目录或其他智能体目录。
2. 从最新 `main` 建立个人功能分支，完成后通过 Pull Request 合并；不要三个人同时直接向 `main` 提交。
3. `packages/contracts/`、`src/backend/`、`web/` 和公共配置是集成区，修改前先协调，公共接口变更必须由上下游负责人复核。
4. 不直接读取其他模块内部类，不复制其他模块的私有校验或模型适配器；先确认公共契约，再接公开入口。
5. 每次提交带上对应测试和文档；生成结果、密钥及本地临时文件不要混入源码提交。

具体分支操作、测试落位与交付检查见 [三人协作规范](docs/team-collaboration.md)。这些是协作约定，不是已启用的 GitHub 权限限制。

## 后续集成顺序

1. A/B/C 复核 B 候选输入、C 输出及共享后端改动，再发布正式公共 Schema。
2. A 对接策略反馈包和新策略接收入口，补齐策略优先优化的在线闭环。
3. B 牵头任务/会话/版本数据库持久化及恢复，避免把进程内存当历史数据库。
4. 继续人工质量复核和完整性能验收；小样本真实调用不替代正式 50 例。

跨重启数据库、完整三轮闭环、创意生成与评估规则均不得在未实现、未验证前标记为已完成。
