# hydraulic-schematics · 液压系统原理图生成技能

**唯一输入定义 → 闸门全绿出图。** 一套让 AI agent 可靠绘制液压系统原理图的技能、描边符号库与校验工具链：从 SysML v2 模型或 L0 `intent.yaml` 出发，全自动产出可逐元件追溯的原理图 SVG、追溯清单与校验报告。

> An agent skill + annotated stroke-symbol SVG library + gate toolchain that renders hydraulic schematic sheets from a single input definition (a SysML v2 model or an L0 `intent.yaml`), with line-level traceability and a geometry + perceptual validation loop.

![图面成熟度](https://img.shields.io/badge/图面成熟度-concept_概念档-orange) ![catalog](https://img.shields.io/badge/catalog-0.4--draft-blue) ![selftest](https://img.shields.io/badge/selftest-PASS_3/3-brightgreen)

> **成熟度承诺上限：concept 概念档**（图签口径「成熟度： concept 概念图，非工程放行图」）。本工具链交付的是设计支持与评审辅助用的概念图；**工程放行永远须经人工原图级签认**，不在承诺范围内。

---

## 这是什么

仓库核心是 agent 技能 [`.agents/skills/hydraulic-schematic/`](.agents/skills/hydraulic-schematic/SKILL.md)，工作流五阶段：**选链路 → 符号准备 → 布局渲染 → 追溯清单 → 校验闭环**。设计目标是「agent 会话为主、工程师复核为辅」：契约刚性、退出码语义明确、失败即停，工程师只需给意图（intent/layout）、审签认（拓扑确认单）、收未收敛项决策。

四条不变式贯穿所有阶段：

1. **可追溯** —— 图中任一组件/端口/连接/图元都能追溯到唯一输入定义（SVG 带 `data-node`/`data-port`/`data-edge`/`data-sysml-line`/`data-zone`，另出追溯清单 markdown）。
2. **不编造拓扑** —— 类型不在目录内则其端口不存在，不得出现在连线中；不知道怎么连就写进 intent 的 `unknown:` 段，不画。
3. **确定性优先** —— 布局坐标显式给定，不做自动布局；端口坐标从符号 SVG 的 `connection-points` 实读，不硬编码。
4. **校验不过即是失败** —— 结构自检失败以退出码 1 终止；无回读图的校核项记「未校核」，不静默放过。

## 成品示例

`1#系统原理图/` 是端到端实证工作区：从工程师 18 项清单出图（concept 档）：

![1#系统液压原理图](<1#系统原理图/1#系统原理图.svg>)

## 双链路

| 链路 | 输入 | 渲染模板脚本 | 范例 |
|---|---|---|---|
| **整机 / SysML** | `*.sysml`（SysML v2：`part`/`port`/`connect`） | `render_aircraft_schematic.py` | [`assets/examples/aircraft_hydraulic_system.sysml`](.agents/skills/hydraulic-schematic/assets/examples/aircraft_hydraulic_system.sysml) |
| **分系统 / L0** | `intent.yaml` + `layout.json` | `render_l0_sheet.py`（内置 preflight 强制预检） | [`assets/examples/system-1.intent.yaml`](.agents/skills/hydraulic-schematic/assets/examples/system-1.intent.yaml) |

两条链路共享符号库、视觉常量与校验理念，不混用。接入新系统零改 skill：只新增该系统的 intent/layout（必要时扩符号/catalog，走入库门禁流程）。

## 仓库导览

```
├── .agents/skills/hydraulic-schematic/   # 核心：agent 技能（唯一规范源）
│   ├── SKILL.md                          # 工作流、不变式、运行纪律（规范性来源）
│   ├── references/                       # 符号库 / 渲染规则 / 校验 三篇规范
│   ├── scripts/                          # 闸门工具链（见下表）
│   └── assets/
│       ├── component-library/            # 22 只描边符号 SVG + component-catalog.json
│       ├── contracts/                    # L0 输入契约 JSON Schema
│       ├── examples/                     # 正例 / 负例（含期望报告）/ 预检放行样例
│       └── fixtures/                     # selftest 金样基准
├── 1#系统原理图/                          # 1# 系统端到端实证工作区（intent/layout/SVG/校验报告）
├── docs/规格与需求.md                     # spec + PRD 合一评审稿（现状快照，非规范源）
├── issues/                               # wayfinder 决策票（本地镜像）
├── research/                             # spec 素材
└── archive/                              # 旧规范源存档（背景参照，与现状冲突处以 skill 为准）
```

## 快速开始

依赖：Python 3 + `ruamel.yaml`；`jsonschema` 可选（缺失时预检形状层降级 WARN，语义层照跑）；其余仅标准库。

```bash
pip install ruamel.yaml jsonschema

# 1) 出图能力回归（金样逐字节 + 闸门沙箱 + 负正例），应 PASS 3/3
python .agents/skills/hydraulic-schematic/scripts/selftest.py

# 2) 符号库结构校验（L1 合法 XML / L2 端口组唯一 / L3 catalog↔symbol 交叉）
python .agents/skills/hydraulic-schematic/scripts/check_library.py

# 3) L0 输入预检：形状层（JSON Schema）+ 语义层七类，一次报齐；ERROR 扣留产物
python .agents/skills/hydraulic-schematic/scripts/preflight.py "1#系统原理图/1#系统.intent.yaml"

# 4) 出图 + 几何校核（渲染/校验为模板脚本：复制到你的工作目录改顶部路径常量后运行；
#    或用工作目录参数就地运行）
python render_l0_sheet.py <workdir>
python validate_sheet.py <workdir>       # 产出 validation-report.json（V1–V19 + 构图预算 B 面板）
```

SysML 链路：`python render_aircraft_schematic.py`（以 `assets/examples/aircraft_hydraulic_system.sysml` 为范例输入，出 SVG + `<name>_topology.md` 追溯清单）。

改符号/catalog 后的库演进流程：`check_library.py` → `selftest.py` → 提交。

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

交付判据三者齐备：渲染脚本退出码 0 + `validation-report.json` 全绿 + 最新 PNG 已回读并记录校了什么。

## 端到端实证（1# 系统）

- 工程师 **18 项清单** → **22 个受控实例**（含 8 只通用用户名框）+ 2 条感温支路；33 条二元 connect = 37 条液压边（nets 37 / segments 48 / junctions 20）。
- `validation-report.json` **fail 0 / warn 6**。
- 技能链端到端全自动出图 **77.7 秒**，零手工坐标、零返工轮、零人工介入；对照手工基线约 2 小时 / 4 轮返工。

## 符号库与组件目录

`assets/component-library/` 是组件库**唯一规范源**（没有镜像同步）：

- **22 只描边符号 SVG**（kebab-case 规范名）+ `_template.svg` 起稿模板；每符号恰一个 `<g id="connection-points">`，端口五件套属性与 catalog `ports[]` 一一对应。
- **component-catalog.json**（`comac-hydraulic-components` 0.4-draft，22 个组件类型）：`component_type` / `connection_role` / `symbol.asset` / `ports[]` / `enums` / `drawing_blockers`。
- 符号成熟度三档：`annotated`（可直接绘图）/ `provisional` / `draft`——后两档按 concept 档降级使用并在图签披露。
- 用油设备不需新符号：`parts` 写 `<inst>: hydraulic_user`，渲染器自动生成带名框的用户符号。

## 路线图

按 [docs/规格与需求.md](docs/规格与需求.md) §13 三档分期：

- **P0 沉淀收口**：五件套沉淀进 skill（[#22](https://github.com/sbhorshy/hydraulic-schematics/issues/22)）、坐标契约 v2（[#23](https://github.com/sbhorshy/hydraulic-schematics/issues/23)）、门禁归位 `check_symbol.py`（[#31](https://github.com/sbhorshy/hydraulic-schematics/issues/31)）
- **P1 实践与增强**：拓扑确认单签认实践 + concept→draft 升档首例（[#24](https://github.com/sbhorshy/hydraulic-schematics/issues/24)）、布局寻优通用化到第二套系统
- **P2 卫生项**：早期符号重绘收尾（4 只）、doctor 体检工具

**非目标**：工程放行档（承诺上限 concept 档）、对外多租户产品化、黑盒自动布局。

## 文档地图

| 文档 | 定位 |
|---|---|
| [`.agents/skills/hydraulic-schematic/SKILL.md`](.agents/skills/hydraulic-schematic/SKILL.md) | **规范性来源**：工作流与不变式 |
| [`references/symbol-library.md`](.agents/skills/hydraulic-schematic/references/symbol-library.md) / [`rendering-rules.md`](.agents/skills/hydraulic-schematic/references/rendering-rules.md) / [`validation.md`](.agents/skills/hydraulic-schematic/references/validation.md) | 规范性来源：符号/渲染/校验三篇 |
| [`docs/规格与需求.md`](docs/规格与需求.md) | spec + PRD 合一评审稿（现状快照与需求登记；与 skill 冲突时以 skill 为准） |
| [`research/spec-materials.md`](research/spec-materials.md) | spec 立稿素材 |

> 文档冲突裁决顺序：skill `SKILL.md` + `references/` 为规范性来源，其余为快照；规则冲突时 用户显式要求 > 符号/风格约定 > 图类布局规则 > 通用默认，唯一不可豁免下限是 Phase 4 校验闭环。
