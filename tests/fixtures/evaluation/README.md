# C 评估联调样例

- `products.json`：旧版五类完整契约样例，供明确标注的离线规则重放使用，评分并非真实模型结果。
- `b-candidate-package.json`：通过 B v6 公开工作区生成路径与测试模型构造的合成输入，四类内容为 B 的字符串格式。用于 B→C 契约校验，不作为真实模型效果证据。

校验候选包：`python -m src.agents.evaluation.check_handoff tests/fixtures/evaluation/b-candidate-package.json`。

真实调用原始记录留在被忽略的 `artifacts/`，本目录不含密钥、Cookie 或私人业务输入。
