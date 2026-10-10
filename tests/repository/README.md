# 仓库集成回归

此目录验证真实仓库上下文：编辑器 HTTP 的规范源渲染/PNG/版本/交付门禁，活动项目油箱与蓄压器三层对账，以及只复制 skill 后的注册用例导入和公开 preflight CLI。

在仓库根目录显式运行：

```bash
python -m unittest discover -s tests/repository -v
```

这组测试需要仓库中的 `editor-proto/`、`1#系统原理图/` 和研究基线证据。它们不随 skill 分发，不是 skill `selftest.py` 的隐藏依赖，也不被独立技能的成功结果包含。运行缺少依赖时须失败，不能用自动 skip 冒充覆盖通过。

独立 skill 的完整回归入口保持为：

```bash
python .agents/skills/hydraulic-schematic/scripts/selftest.py
```

`selftest.py --list-suites` 只返回 F 组实际登记的 unittest 模块及范围，不执行测试；复制包回归据此导入真正会被自检执行的模块，再运行公开 preflight 命令。历史未登记的示例测试不作为本次可移植性通过证明。正式批次验收分别记录完整 skill 自检与本目录集成回归的计数、耗时及退出码。
