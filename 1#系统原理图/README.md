# 1# 系统活动输入

活动输入为本目录 `1#系统.intent.yaml`、`1#系统.layout.json`、`1#系统组件.json`、`component-catalog.json`、`symbols/`（项目符号副本）与 `1#系统.sysml`。使用规范源驱动器，并指定仓库外或被忽略的独立 `--workdir`；本目录 `render.py`/`validate_sheet.py`/`check_symbol.py`/`preflight.py` 现为规范源薄入口（前两者支持显式工作目录；`check_symbol.py` 透传参数，无位置参数时由规范源全量扫 skill 自带符号库——入库门禁规范源已随 [#31](https://github.com/sbhorshy/hydraulic-schematics/issues/31) 归位 `.agents/skills/hydraulic-schematic/scripts/`）；没有第二份渲染/校核/门禁实现。**本目录不再存放生成产物**：SVG/PNG/拓扑清单/校验报告/回读裁剪等运行产物写入 `.artifacts/` 或其他被忽略目录（见根 `.gitignore`），不构成通过证明。

## 全新检出生成链（SVG → PNG → validate）

```bash
mkdir -p .artifacts
WORK=$(mktemp -d "$PWD/.artifacts/one-system.XXXXXX")
cp 1#系统原理图/1#系统.intent.yaml 1#系统原理图/1#系统.layout.json \
   1#系统原理图/1#系统组件.json 1#系统原理图/component-catalog.json "$WORK/"
cp -r 1#系统原理图/symbols "$WORK/symbols"

python3 .agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py "$WORK"
python3 .agents/skills/hydraulic-schematic/scripts/rasterize_sheet.py \
  "$WORK/1#系统原理图.svg" -o "$WORK/sheet-readback.png"
python3 .agents/skills/hydraulic-schematic/scripts/validate_sheet.py "$WORK"
```

诊断/收敛驱动器（自动产出回读 PNG 与 validation-report）：

```bash
python3 .agents/skills/hydraulic-schematic/scripts/validate_driver.py \
  --intent '1#系统原理图/1#系统.intent.yaml' \
  --catalog '1#系统原理图/component-catalog.json' \
  --layout-seed '1#系统原理图/1#系统.layout.json' \
  --workdir .artifacts/one-system-driver
```

编辑器原型：`python3 editor-proto/server.py --workdir "$WORK" --port 8763`（沿用上一步的输出目录，在同一个终端运行）。

## 当前状态与边界

- 活动 intent 的液端接 PRV-002 下游，气侧按 ACC→PG→ACV 两条 taps 表达（[#46](https://github.com/sbhorshy/hydraulic-schematics/issues/46)）；项目显式 seed 是本支路当前受支持的布局入口，不带 seed 的 R1–R16 引擎仍报告 ACC/PG/ACV 未布。回归 oracle 具名保存在 `tests/fixtures/accumulator-baseline.json`（来源见其 README）。
- #23 将活动 seed 转为根 SVG 坐标，内容物理位置不变，画布右扩 30px 留足显式 EDGE_MARGIN；单桥许可登记见 `tests/repository/test_bridge_registration.py`。
- 旧 `build_catalog.py` 在任何文件 I/O 前 fail-closed，防止硬编码 Windows 写路径/旧覆盖策略把活动目录回退；[#48](https://github.com/sbhorshy/hydraulic-schematics/issues/48) 负责后续正式生成入口。旧 `build_render.py` 同样 fail-closed，不能再用过期脚本覆盖薄入口。
- **没有回读签认时 `delivery.ready` 仍为 false**；报告全绿 + 未签认 ≠ 完整交付绿灯，不得伪装。
- 历史实证（旧 SVG/PNG/报告、`proto/frozen/` 冻结原型、`f3a00952` 等捕获）已整体移出 main，见 [docs/archive.md](../docs/archive.md) 索引与归档标签 `archive-main-before-cleanup-20261013`；复现实验应从该标签导出整套历史目录到独立工作区，不混用活动 seed，不把旧图像来源替换成新油箱。
- `skill-chain-e2e/` 现仅存技能链种子一对（intent+layout），是诊断用例 `compatible-22` 的输入；`CDF-001装配图/` 为 CDF 活动输入（诊断用例 `filter-series`），边界见其子目录 README。
