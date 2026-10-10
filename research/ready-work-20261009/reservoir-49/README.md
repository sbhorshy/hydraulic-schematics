# 旧油箱退出活动工程（#49）

项目现在使用规范源 `bootstrap-type-reservoir.svg` 的逐字节受管副本，目录状态为真实的 draft，旧活动符号已删除。规范源 catalog、FOOTPRINT、rendering-rules 原本已指向新符号；symbol-library 中旧 viewBox 示例补上历史标识，并记载 campaign 早期待办 4 → 3（其余三件未扩范围）。

迁移不是只换文件名：保留 TANK 的位置与 218×564 足迹，依据新 SVG 重新渲染端口与连线。旧 viewBox `20 10 218 564` 变为新 `0 0 218 564`；回油/吸油口归一化几何不变，增压口从局部 x=172 变 x=155（全局 x=232 → 215），新增 body_sense_tap=(50,564)。新 SVG 元数据及现行 validator 共同验证这些真实几何，未编造端口或更改拓扑。

TDD 使用此前已授权的 driver / SVG / PNG / report 公开接口：`test_reservoir_retirement.py` 红态重现 render V5 缺 body_sense_tap；迁移后测试通过，验证 render 完成、两个新版端口坐标、PNG 已刷新与 TANK 无 V5/V8 错误。该回归已登记 selftest。`check_library` 当前通过（既有 QD whitelist 如实披露）。本票未重跑全量 selftest，批次整合后由根代理统一执行，不把历史全量证明冒充新跑。

新项目 driver 从 preflight 到渲染、PNG、validate、134 对象/62 局部回读全部执行，exit 1、13 FAIL / 9 WARN；旧 TANK 契约故障已消除，但气侧折返/穿体、压力与壳体网络误接、B1 交叉等既有残差仍在，详见 [project-result.json](project-result.json) 与 [project.log](project.log)。未签认感知、未升档 maturity，`delivery.ready=false`。完整 SVG/PNG/报告在 `.scratch/ready-work/issue-49-evidence/project-run/`，公开摘要记录 SHA-256 和原始失败条目。

引用清点覆盖 catalog symbol.asset、引擎/原型 FOOTPRINT、规范文档、项目 symbols、编辑器和历史夹具；[剩余引用分类](remaining-references.json) 对所有仍提及旧名的跟踪文件标明历史/规格用途。`proto/` 包括 frozen 的旧资产、布局和脚本按整个历史版本保留，不能将其旧 PNG 来源冒充新版；活动目录中的旧 SVG/PNG/topology/report 是捕获提交 f3a00952 的历史输出，版本边界见项目 README。编辑器仓库仅有入口代码，无跟踪的 scratch 副本；用户原工作区未跟踪 scratch 未在本票擅自改写。

活动 `build_catalog.py` 在文件 I/O 前明确停止，防旧硬编码生成器覆盖迁移结果；这只是防回退出口，[生成器重构](https://github.com/sbhorshy/hydraulic-schematics/issues/48)继续独立处理。不执行旧生成器，不改 frozen 脚本，不把旧基线的引用清理伪装成当前重渲染。

复现（仓库根目录，新的独立工作目录）：

```bash
python .agents/skills/hydraulic-schematic/scripts/test_reservoir_retirement.py
python .agents/skills/hydraulic-schematic/scripts/check_library.py
python .agents/skills/hydraulic-schematic/scripts/validate_driver.py \
  --intent '1#系统原理图/1#系统.intent.yaml' \
  --catalog '1#系统原理图/component-catalog.json' \
  --layout-seed '1#系统原理图/1#系统.layout.json' \
  --workdir /tmp/reservoir-49-fresh
```
