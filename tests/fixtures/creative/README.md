# 策略 → 创意首轮联调样例

本目录的 12 份 JSON 是离线合成输入。产品资料为人工构造需求，响应由规则生成器及测试变体产生；**不是真实模型质量证据，也不是创意生成结果**。每个 JSON 都是完整创意请求，元信息放在本说明中，不额外加入契约字段。

## 应接受：6 份

- `valid-milk-owned.json`：已知价格、入口、渠道、素材和人力的奶茶输入。
- `valid-milk-zero.json`：零预算、无现有渠道/素材、低人力，不能以旧资源值规划。
- `valid-missing-context.json`：预算、周期、受众等未知，用 `null` 和信息缺口保留，不补造数据。
- `valid-channel-conflict.json`：必选/禁用抖音冲突已如实记录，并未推荐禁用渠道。契约可接收不代表可直接发布；需确认受影响渠道。
- `valid-watch.json`：不同产品的完整输入。
- `valid-budget-reserve.json`：1000 元总预算中只分配 600 元，剩余 400 元合法，不强制花完。

## 应拒绝：6 份

- `invalid-cross-task.json`：内外任务编号不同。
- `invalid-wrong-round.json`：首轮请求引用第 2 轮策略。
- `invalid-over-budget.json`：1000 元预算分配为 1001 元。
- `invalid-missing-field.json`：缺少必需的可空字段 `creative`。
- `invalid-unknown-budget.json`：预算未知却填入渠道金额。
- `invalid-fake-evidence.json`：卖点引文不在产品原文中。

测试命令（项目根目录）：

```powershell
python -m unittest tests.integration.test_creative_handoff_pack
python -m ops.validate_creative_handoff --input tests/fixtures/creative/valid-budget-reserve.json
python -m ops.validate_creative_handoff --input tests/fixtures/creative/invalid-cross-task.json
```

第三条退出码 1 是预期拒绝。创意负责人用这些文件编写自己的入口测试；不要依赖策略私有服务实现。

完整开工资料见 [对接说明书](../../../docs/02-creative-handoff-guide.md)。样例生成工具 `python -m ops.prepare_creative_handoff` 仅用于首次生成，检测到已存在样例会拒绝覆盖；修改规则后应检查并按团队约定更新，不盲目重生成。
