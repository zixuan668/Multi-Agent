# 三人协作与目录规范

[返回项目总览](../README.md) · [01 策略](01-strategy-agent.md) · [02 创意](02-creative-agent.md) · [03 评估](03-evaluation-agent.md)

本规范用于让三位成员在同一仓库中独立开发、清晰交付。负责人姓名及公共集成人选由团队自行确认；这里不替成员指定姓名或创建 GitHub 权限。

## 1. 固定模块顺序，稳定代码路径

文档展示顺序固定为 **01 策略 → 02 创意 → 03 评估**，对应文件：

- `docs/01-strategy-agent.md`
- `docs/02-creative-agent.md`
- `docs/03-evaluation-agent.md`

Python 包分别使用 `strategy`、`creative`、`evaluation`。不要改成 `01_strategy` 等名称，不要用“最新版”“最终版2”等目录区分版本；版本交给 Git、提示词文件版本及接口版本管理。

### 01 · 策略成员的独立区域

- `src/agents/strategy/`
- `prompts/strategy/`
- `docs/01-strategy-agent.md`
- 现有策略单元测试仍保留在 `tests/unit/test_*.py`，不在本次整理中搬迁，以免破坏已有测试引用。
- 新增策略单元测试逐步放入 `tests/unit/strategy/`；新样例放入 `tests/fixtures/strategy/`。

### 02 · 创意成员的独立区域

- `src/agents/creative/`
- `prompts/creative/`
- `docs/02-creative-agent.md`
- 新测试：`tests/unit/creative/`；新样例：`tests/fixtures/creative/`。

### 03 · 评估成员的独立区域

- `src/agents/evaluation/`
- `prompts/evaluation/`
- `docs/03-evaluation-agent.md`
- 新测试：`tests/unit/evaluation/`；新样例：`tests/fixtures/evaluation/`。

未来创建测试子目录时包含 `__init__.py`；以项目根目录的 unittest 命令验证发现情况。上述新测试目录是后续落位约定，目前未放入虚构测试。

## 2. 公共集成区，先协调再修改

以下文件不是某个智能体的私有区域：

- `packages/contracts/`：跨模块请求 / 响应 Schema。
- `src/backend/`、`app.py`：HTTP 服务、任务管理和未来的调度集成；当前仅接策略模块。
- `web/`：共享首页、工作台和交互逻辑。
- `tests/integration/`、`tests/acceptance/`、`ops/`：跨模块联调及阶段验收。
- `README.md`、`pyproject.toml`、`.env.example`、`.gitignore`：项目总入口和公共配置。

由团队指定公共集成负责人协调这些改动。不要在三个功能分支里各维护一份不同的公共 Schema、启动入口或页面；出现交叉修改时，在 PR 中列出受影响模块并邀请相关成员复核。

## 3. 接口先行，避免模块互相侵入

1. 请求和响应字段以团队确认后的 `packages/contracts/` 为准，不能靠聊天描述或页面文案猜测。
2. 变更公共字段时，先说明兼容性与受影响模块，再同步生产方、消费方和测试，必要时升级接口版本。
3. 不直接导入其他模块的私有类、读取其内部任务存储或更改其结果对象；通过双方确认的公开入口交付数据。
4. 已有策略内部的模型适配器不直接当作三个智能体的公共工具。确需复用时，再由团队设计并抽取共享层，不复制成三套后分别修改。
5. 保留任务归属、版本、原始事实与阶段状态；技术重试不是业务反馈轮次，策略完成也不是评估完成。

当前唯一已落地的跨模块首轮交付为策略 → 创意请求校验。创意输出、评估契约和完整调度尚未发布。

## 4. 每人一个功能分支，PR 合并

首次加入：

```powershell
git clone https://github.com/zixuan668/Multi-Agent.git
cd Multi-Agent
```

开始新任务前先确认 `git status`；如果有未提交修改，先正常提交或自行保存，不要用强制重置清理。

```powershell
git switch main
git pull --ff-only origin main
git switch -c feature/creative-content
```

分支名包含模块与具体任务，例如 `feature/strategy-channel-plan`、`feature/creative-content`、`feature/evaluation-feedback`。一次分支只处理一个清晰任务。

提交时显式选择自己改过的文件，不盲目 `git add .`；下面是创意成员的示例，按实际改动选择路径：

```powershell
git add src/agents/creative prompts/creative docs/02-creative-agent.md
git commit -m "feat(creative): implement first-round content generation"
git push -u origin feature/creative-content
```

测试文件也应一同暂存。随后在 GitHub 创建以 `main` 为目标的 Pull Request，由至少一位其他成员复核；涉及公共接口时由上下游负责人一起检查。

PR 说明应包含：改了什么、影响哪些目录 / 接口、运行了哪些测试、是否改变配置，以及哪些事项仍待完成。出现冲突逐文件处理，不使用 `--force` 或整目录覆盖别人的改动。

> 建议仓库管理员邀请其余两位成员为协作者，并为 `main` 配置要求 PR 与复核的分支规则。这些设置尚未由本次文档整理启用，写入规范本身不会自动保护分支。

## 5. 本地配置与数据隔离

- 每人使用自己的 `.env`，仅在模板 `.env.example` 中提交不含密钥的配置名称和示例。
- 不提交真实 API 密钥、令牌、账号密码、任务 Cookie、个人日志或用户敏感需求。
- 公共可复现样例放入对应 `tests/fixtures/`，真实运行产物放入本地 `artifacts/`；后者由 `.gitignore` 排除。
- 不把课程文档生成脚本、临时渲染目录或“结果最终版.json”混入智能体源码；其他项目资料如需共享，应单独整理并检查内容后提交。

## 6. 合并前检查

- [ ] 代码、提示词与文档放在对应模块目录，未顺手搬动别人的代码。
- [ ] 公共契约变更已经协调，生产方与消费方使用同一版本。
- [ ] 自己新增的测试能被发现并通过。
- [ ] `python -m unittest discover -s tests -v` 通过；前端改动补跑 `node tests/frontend/test_diagnostics.cjs`。
- [ ] `git diff --cached` 中没有密钥、缓存、敏感需求和生成结果。
- [ ] PR 标注真实实现状态，不伪造其他智能体的测试、评分或人工复核结果。
- [ ] 正式真实模型批量验收由团队确认后运行，费用与证据范围明确。

## 7. 本次整理的边界

保留现有策略代码、提示词和测试入口；新增总览、顺序清晰的模块文档及创意 / 评估预留目录。不实现其他成员的业务模块，不擅自定义完整评估 Schema，也不把策略侧校验冒充评估智能体。
