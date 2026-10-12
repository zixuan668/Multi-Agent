# 创意智能体开工交接包

解压后保持目录结构，先读 `docs/02-creative-handoff-guide.md`。

这是可独立运行契约检查的资料包，不是完整网站，也不是已经实现的创意智能体。包含开工说明、三个公共请求/响应 Schema、12 份合成测试输入、策略侧参考校验器及其必要源码、配套测试。

需要 Python 3.11 或以上，无需安装第三方 Python 库。执行：

```powershell
python -m ops.validate_creative_handoff --input tests/fixtures/creative/valid-budget-reserve.json
python -m ops.validate_creative_handoff --input tests/fixtures/creative/invalid-cross-task.json
python -m unittest tests.integration.test_creative_handoff_pack
```

第一条应接受，第二条应拒绝（退出码1是预期），第三条应通过。Node.js 仅用于额外的四步表单映射对照；未安装时对应自动测试跳过，静态 JSON 校验仍可运行。

开始业务开发应进入团队完整仓库，不在本资料包里维护第二套源码。以包含本次交接文件的分支为准；先检查未提交工作，不强制覆盖已有代码。

样例仅为合成联调输入，不作为真实模型或市场效果证据。`strategy.data` 是策略业务正文；创意响应 Schema 和在线创意入口尚待团队确认。本包不包含 `.env`、密钥、Cookie、原始真实调用日志或用户需求。
