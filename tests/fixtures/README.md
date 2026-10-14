# 测试夹具

## accumulator-baseline.json

- **来源**：归档标签 `archive-main-before-cleanup-20261013`（提交 `e9cc0fc`）中的
  `research/ready-work-20261009/reservoir-49/project-result.json`，逐字节复制（sha256
  `45eb9ae105cb12b0e34daa04b8152028263a581d75c7715186f1fd1f4910d569`），未重新生成。
- **用途**：`tests/repository/test_accumulator_branch.py` 的历史回归 oracle。该测试把当前
  管线产出的失败项与本基线做差集，断言蓄压器支路迁移不引入**任何新增失败**；基线中已有的
  6 项 CASE/PRESS/B1 基线失败被显式豁免。
- **维护纪律**：不得重生成、不得删减断言或放宽阈值；如需换基线，按
  `docs/agents/repository-content.md` 以具名 fixture 记录新来源。
