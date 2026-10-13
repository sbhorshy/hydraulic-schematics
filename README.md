# hydraulic-schematics · 液压系统原理图生成技能

**唯一输入定义 → 闸门全绿出图。** 一套让 AI agent 可靠绘制液压系统原理图的技能、描边符号库与校验工具链：从 SysML v2 模型或 L0 `intent.yaml` 出发，全自动产出可逐元件追溯的原理图 SVG、追溯清单与校验报告。

> An agent skill + annotated stroke-symbol SVG library + gate toolchain that renders hydraulic schematic sheets from a single input definition (a SysML v2 model or an L0 `intent.yaml`), with line-level traceability and a geometry + perceptual validation loop.

![图面成熟度](https://img.shields.io/badge/图面成熟度-concept_概念档-orange) ![catalog](https://img.shields.io/badge/catalog-0.4--draft-blue)

> **成熟度承诺上限：concept 概念档**（图签口径「成熟度： concept 概念图，非工程放行图」）。本工具链交付的是设计支持与评审辅助用的概念图；**工程放行永远须经人工原图级签认**，不在承诺范围内。

---

## 这是什么

仓库核心是 agent 技能 [`.agents/skills/hydraulic-schematic/`](.agents/skills/hydraulic-schematic/SKILL.md)，工作流五阶段：**选链路 → 符号准备 → 布局渲染 → 追溯清单 → 校验闭环**。设计目标是「agent 会话为主、工程师复核为辅」：契约刚性、退出码语义明确、失败即停，工程师只需给意图（intent/layout）、审签认（拓扑确认单）、收未收敛项决策。

四条不变式贯穿所有阶段：

1. **可追溯** —— 图中任一组件/端口/连接/图元都能追溯到唯一输入定义（SVG 带 `data-node`/`data-port`/`data-edge`/`data-sysml-line`/`data-zone`，另出追溯清单 markdown）。
2. **不编造拓扑** —— 类型不在目录内则其端口不存在，不得出现在连线中；不知道怎么连就写进 intent 的 `unknown:` 段，不画。
3. **确定性优先** —— 布局坐标显式给定，不做自动布局；端口坐标从符号 SVG 的 `connection-points` 实读，不硬编码。
4. **校验不过即是失败** —— 结构自检失败以退出码 1 终止；无回读图的校核项记「未校核」，不静默放过。

## main 分支定位与产物边界

**main 是维护源码树**：只保留技能源码、测试、项目活动输入（intent/layout/catalog/组件JSON/symbols）与必要说明文档。

- **生成产物不随 main**。渲染出的 SVG/PNG、校验报告、回读截图、验收证据等运行产物放在被忽略的工作目录（`.artifacts/` 或任意仓库外目录），不入库；历史验收证据统一在归档标签 [`archive-main-before-cleanup-20261013`](https://github.com/sbhorshy/hydraulic-schematics/tree/archive-main-before-cleanup-20261013)（见 [docs/archive.md](docs/archive.md) 索引），按需从标签取回，不在 main 留副本。
- **skill 分发取完整 skill 目录**：`.agents/skills/hydraulic-schematic/` 整目录（含 SKILL.md、references、scripts、assets）自包含可分发；仓库其余部分是它的集成测试与项目输入，不随 skill 走。
- **成品示例**（历史存档，非 main 当前产物）：[1# 系统原理图 SVG @ 归档标签](https://github.com/sbhorshy/hydraulic-schematics/blob/archive-main-before-cleanup-20261013/1%23%E7%B3%BB%E7%BB%9F%E5%8E%9F%E7%90%86%E5%9B%BE/1%23%E7%B3%BB%E7%BB%9F%E5%8E%9F%E7%90%86%E5%9B%BE.svg)。
- 仓库内容取舍规则见 [docs/agents/repository-content.md](docs/agents/repository-content.md)。

## 双链路

| 链路 | 输入 | 渲染模板脚本 | 范例 |
|---|---|---|---|
| **整机 / SysML** | `*.sysml`（SysML v2：`part`/`port`/`connect`） | `render_aircraft_schematic.py` | [`assets/examples/aircraft_hydraulic_system.sysml`](.agents/skills/hydraulic-schematic/assets/examples/aircraft_hydraulic_system.sysml) |
| **分系统 / L0** | `intent.yaml` + `layout.json` | `render_l0_sheet.py`（内置 preflight 强制预检） | [`assets/examples/system-1.intent.yaml`](.agents/skills/hydraulic-schematic/assets/examples/system-1.intent.yaml) |

两条链路共享符号库、视觉常量与校验理念，不混用。接入新系统零改 skill：只新增该系统的 intent/layout（必要时扩符号/catalog，走入库门禁流程）。

## 仓库导览

```
├── .agents/skills/hydraulic-schematic/   # 核心：agent 技能（唯一规范源；分发取整个目录）
│   ├── SKILL.md                          # 工作流、不变式、运行纪律（规范性来源）
│   ├── references/                       # 符号库 / 渲染规则 / 校验 三篇规范
│   ├── scripts/                          # 闸门工具链 + skill 自检（test_*.py）
│   └── assets/
│       ├── component-library/            # 22 只描边符号 SVG + component-catalog.json
│       ├── contracts/                    # L0 输入契约 JSON Schema
│       ├── examples/                     # 正例 / 负例（含期望报告）/ 预检放行样例
│       └── fixtures/                     # selftest 金样基准
├── 1#系统原理图/                          # 1# 系统活动输入（intent/layout/catalog/组件JSON/symbols/薄入口）
│   ├── CDF-001装配图/                     # CDF 装配活动输入（诊断用例 filter-series 种子）
│   └── skill-chain-e2e/                   # 技能链种子一对（诊断用例 compatible-22 输入）
├── editor-proto/                         # #60/#58/#59 拖拽写回闭环原型 + #63 镜像操作面（无导出）
├── tests/
│   ├── repository/                       # 仓库集成回归（编辑器 HTTP、活动项目对账、桥线许可）
│   ├── scheduler/                        # skill 自检 CLI 契约测试
│   └── fixtures/                         # 历史回归 oracle（来源见其 README）
├── docs/                                 # 规格需求、验收票面、agent 约定、archive 索引
├── research/                             # 仅规范/许可仍引用的必要依据（见 research/README.md）
└── CONTEXT.md                            # 领域术语表（single-context）
```

## 快速开始

依赖：Python 3 + `ruamel.yaml`；`jsonschema` 可选（缺失时预检形状层降级 WARN，语义层照跑）；PNG 光栅化需 Inkscape 或 headless Chrome（`rasterize_sheet.py` 自动选择）；其余仅标准库。

```bash
pip install ruamel.yaml jsonschema

# 1) skill 自包含回归，不依赖外层项目/编辑器目录
python .agents/skills/hydraulic-schematic/scripts/selftest.py

# 1b) 本仓库集成回归（编辑器 HTTP、活动项目油箱/蓄压器、独立 skill 包）
#     此项不包含在 skill 自检中；在仓库内另行执行并单独记录结果。
python -m unittest discover -s tests/repository -v

# 2) 符号库结构校验（L1 合法 XML / L2 端口组唯一 / L3 catalog↔symbol 交叉）
python .agents/skills/hydraulic-schematic/scripts/check_library.py

# 3) L0 输入预检：形状层（JSON Schema）+ 语义层七类，一次报齐；ERROR 扣留产物
python .agents/skills/hydraulic-schematic/scripts/preflight.py "1#系统原理图/1#系统.intent.yaml"
```

### 全新检出后生成 1# 系统图纸（SVG → PNG → validate）

产物目录用被忽略的 `.artifacts/`（或任意仓库外工作目录），不污染源码树：

```bash
WORK=.artifacts/one-system
mkdir -p "$WORK"
cp "1#系统原理图/1#系统.intent.yaml" "1#系统原理图/1#系统.layout.json" \
   "1#系统原理图/1#系统组件.json" "1#系统原理图/component-catalog.json" "$WORK/"
cp -r "1#系统原理图/symbols" "$WORK/symbols"

# 渲染（SVG + 追溯清单）
python .agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py "$WORK"
# 光栅化回读 PNG（1:1）
python .agents/skills/hydraulic-schematic/scripts/rasterize_sheet.py \
  "$WORK/1#系统原理图.svg" -o "$WORK/sheet-readback.png"
# 几何校核（V1–V19 + 构图预算 B 面板；产出 validation-report.json，退出码 1=failed）
python .agents/skills/hydraulic-schematic/scripts/validate_sheet.py "$WORK"
```

诊断/收敛驱动器（带有界两轮与处方表，自动产出回读 PNG 与 validation-report）：

```bash
python .agents/skills/hydraulic-schematic/scripts/validate_driver.py \
  --intent "1#系统原理图/1#系统.intent.yaml" \
  --catalog "1#系统原理图/component-catalog.json" \
  --layout-seed "1#系统原理图/1#系统.layout.json" \
  --workdir .artifacts/one-system-driver
```

注意：`validation-report.json` 全绿不等于交付完成——**没有回读签认时 `delivery.ready` 仍为 false**，交付判据三者齐备：渲染脚本退出码 0 + 报告全绿 + 最新 PNG 已回读并记录校了什么。

### 启动编辑器原型

```bash
python editor-proto/server.py --workdir "1#系统原理图" --port 8763
# 浏览器打开 http://127.0.0.1:8763
```

原型口径：手调直改 layout.json（写回唯一路径），画布每帧=标准链产物，**无导出能力**；自测请复制沙箱工作目录，勿对脏树试刀。

SysML 链路：`python render_aircraft_schematic.py`（以 `assets/examples/aircraft_hydraulic_system.sysml` 为范例输入，出 SVG + `<name>_topology.md` 追溯清单；模板脚本复制到工作目录改顶部路径常量后运行）。

改符号/catalog 后的库演进流程：`check_symbol.py` → `check_library.py` → `selftest.py` → 提交。

## 校验闭环：7 道闸门

| 闸门 | 守什么 | 失败行为 |
|---|---|---|
| 1. 渲染器结构自检 | 拓扑完整性：connect↔边、part↔节点 | 退出码 1，不产出成品 |
| 2. `preflight.py`（L0 强制） | 输入合法性：形状 + 语义七类 + 模板对账/签认分级 | ERROR 扣留产物 |
| 3. `check_library.py` | 库结构 L1/L2/L3（pre-push 兜底） | 退出码 1 |
| 4. `selftest.py` | 出图能力回归（金样/沙箱/负正例） | 退出码 1 |
| 5. `validate_sheet.py` | 几何校核 V1–V19 + 构图预算 B1–B7 + 三件套互核 | `validation-report.json`，1=failed |
| 6. 感知回读（PNG） | 符号变形/镜像/穿越/标签对位/图签图例 | 疑点修正后重光栅化再回读 |
| 7. 有界收敛 | 修正最多两轮，每轮只修上一轮列出的缺陷 | 两轮不绿即停，交「未收敛项清单」 |

## 符号库与组件目录

`assets/component-library/` 是组件库**唯一规范源**（没有镜像同步）：

- **22 只描边符号 SVG**（kebab-case 规范名）+ `_template.svg` 起稿模板；每符号恰一个 `<g id="connection-points">`，端口五件套属性与 catalog `ports[]` 一一对应。
- **component-catalog.json**（`comac-hydraulic-components` 0.4-draft，22 个组件类型）：`component_type` / `connection_role` / `symbol.asset` / `ports[]` / `enums` / `drawing_blockers`。
- 符号成熟度三档：`annotated`（可直接绘图）/ `provisional` / `draft`——后两档按 concept 档降级使用并在图签披露。
- 存量符号全量绿跑基线尚未建立（`fsov-provisional-stroke.svg` 与接通位 `quick-disconnect-coupling.svg` 两件已知 ERROR，见 [#31](https://github.com/sbhorshy/hydraulic-schematics/issues/31)），不得以跳过或 WARN 冒充通过。
- 用油设备不需新符号：`parts` 写 `<inst>: hydraulic_user`，渲染器自动生成带名框的用户符号。

## 状态与路线图

工单与规格在 GitHub Issues：`sbhorshy/hydraulic-schematics`（约定见 [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md)）。票面状态以 Issues 为准，本仓库不留本地票镜像；未完成工单（如 [#31](https://github.com/sbhorshy/hydraulic-schematics/issues/31) 存量符号全量绿跑、[#60](https://github.com/sbhorshy/hydraulic-schematics/issues/60) 拖拽写回闭环等）不得因本 README 或历史归档证据视为已完成。

分期规划见 [docs/规格与需求.md](docs/规格与需求.md) §13。**非目标**：工程放行档（承诺上限 concept 档）、对外多租户产品化、黑盒自动布局。

## 文档地图

| 文档 | 定位 |
|---|---|
| [`.agents/skills/hydraulic-schematic/SKILL.md`](.agents/skills/hydraulic-schematic/SKILL.md) | **规范性来源**：工作流与不变式 |
| [`references/symbol-library.md`](.agents/skills/hydraulic-schematic/references/symbol-library.md) / [`rendering-rules.md`](.agents/skills/hydraulic-schematic/references/rendering-rules.md) / [`validation.md`](.agents/skills/hydraulic-schematic/references/validation.md) | 规范性来源：符号/渲染/校验三篇 |
| [`docs/规格与需求.md`](docs/规格与需求.md) | spec + PRD 合一评审稿（现状快照与需求登记；与 skill 冲突时以 skill 为准） |
| [`docs/archive.md`](docs/archive.md) | 归档索引：历史验收证据与批次资料的位置 |
| [`docs/agents/repository-content.md`](docs/agents/repository-content.md) | main 内容取舍规则 |
| [`research/README.md`](research/README.md) | 仅存的必要依据说明 |

> 文档冲突裁决顺序：skill `SKILL.md` + `references/` 为规范性来源，其余为快照；规则冲突时 用户显式要求 > 符号/风格约定 > 图类布局规则 > 通用默认，唯一不可豁免下限是 Phase 4 校验闭环。
