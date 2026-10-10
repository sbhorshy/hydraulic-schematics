# 1# 系统活动输入与历史证据

活动输入为本目录 `1#系统.intent.yaml`、`1#系统.layout.json`、`component-catalog.json`。使用规范源驱动器，并指定新的独立 `--workdir`；本目录老 `render.py`/`validate_sheet.py` 与旧 SVG/PNG/topology/report 不构成当前交付入口或通过证明。

```bash
python .agents/skills/hydraulic-schematic/scripts/validate_driver.py \
  --intent '1#系统原理图/1#系统.intent.yaml' \
  --catalog '1#系统原理图/component-catalog.json' \
  --layout-seed '1#系统原理图/1#系统.layout.json' \
  --workdir /tmp/one-system-new-run
```

本目录已有图像/追溯清单/校核报告保留为输入捕获 `f3a00952fd5d13fffe85db4740c00fd064d60918` 的历史实证，旧清单中符号名称据当时实际资产保留；不得把它们冒充换版后的输出。当前红面见 `research/ready-work-20261009/baseline-44/`；油箱迁移的新证据见同目录 `reservoir-49/`。

`proto/`（包括 `proto_b_rules.py` 与 `frozen/` 全套脚本、布局和旧符号）是版本化原型/冻结证据；它的 FOOTPRINT、catalog、符号和 PNG 必须作为一套历史版本解释。禁止在活动项目里调用这些原型生成器。若需复现实验，请从上述 Git 提交导出整个历史目录到独立工作区；保留其旧输入，不将旧图像的来源替换成新油箱。`skill-chain-e2e/` 同为历史冻结样本，其已知旧端口预检红由冻结重钉票处理。

活动 `build_catalog.py` 暂时在任何文件 I/O 前 fail-closed，防止硬编码 Windows 写路径/旧覆盖策略把活动目录回退。[build_catalog 重构与双册对齐](https://github.com/sbhorshy/hydraulic-schematics/issues/48)负责后续正式生成入口，本次未执行旧生成器、未重构生成策略。

2026-10-10，[蓄压器同步](https://github.com/sbhorshy/hydraulic-schematics/issues/46)已把活动 intent 的液端改接 PRV-002 下游，气侧按 ACC→PG→ACV 两条 taps 表达。项目显式 seed 是本支路当前受支持的布局入口；不带 seed 的 R1–R16 引擎仍报告 ACC/PG/ACV 未布。三层对账、新 PNG 与实际残差见 `research/ready-work-20261009/accumulator-46/`；历史图像不因这段说明升级为新交付。
