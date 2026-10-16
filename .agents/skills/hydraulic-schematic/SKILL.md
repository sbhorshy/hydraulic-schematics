---
name: hydraulic-schematic
description: Draw or update hydraulic system schematic sheets from a single input definition — a SysML v2 model or an L0 intent.yaml — reusing an annotated stroke-symbol SVG library (connection-points; bundled snapshot included), with orthogonal routing, a line-level traceability manifest mapping every node/edge to unique input definitions, and a geometry + perceptual validation loop. Use when asked to 绘制/更新系统原理图 or 液压原理图, to 标注新符号 (add connection-points to an element SVG), to generate a 追溯清单 for a drawing, or to 校验/回读 a rendered sheet. Also for extending the component catalog in component-catalog.json.
---

# 液压系统原理图工作流

从**唯一输入定义**（SysML v2 模型，或 L0 `intent.yaml`）出发，复用已标注描边符号库绘制系统原理图 SVG，生成行号级追溯清单，并以"几何校核 → 感知回读"闭环验证。

## 不变式（任何阶段不得违反）

1. **可追溯**：图中任一组件/端口/连接/图元必须能追溯到唯一输入定义（SysML 行号或 intent 锚点）。渲染出的 SVG 元件带 `data-node` / `data-port` / `data-edge` / `data-sysml-line` / `data-zone`；同时产出追溯清单 markdown。
2. **不编造拓扑**：类型不在目录内则其端口不存在，不得出现在 paths/连线中；数量未声明的类型按 1 实例处理；不知道怎么连就写进 intent 的 `unknown:` 段，别画。
3. **确定性优先**：优先复用显式布局；需要自动生成时使用规则引擎并保存生成的坐标。寻优固定随机种子并受评估预算约束；端口坐标从符号 SVG 的 `connection-points` 实读，不硬编码。
4. **校验不过即是失败**：结构自检失败以退出码 1 终止并报告缺项；无回读图的校核项记为"未校核"，不许静默放过。

## 规则优先级

要求冲突时从高到低裁决：用户显式要求 > 符号/风格约定 > 图类布局规则 > 通用默认。
正式交付须满足 Phase 4 三层校验；修正受两轮上限约束。未收敛时提交残差清单；若用户要求概念图，则逐条披露未通过/未校核项，不标为校验通过。

## 主链路

**SysML 窄文法 → intent → L0 全链是主链路**：SysML 模型是唯一输入定义，intent 是其转换产物，文法与转换范围见 [references/sysml-l0.md](references/sysml-l0.md)。窄文法只覆盖已登记的类型与写法；模型里出现目录没有的类型或端口时，转换被准确拒绝（fail-closed），不得靠删节点、假造目录或手写 intent 顶替。真实 1# 模型目前仍因工程事实被拒绝，这是已披露的限制，不是链路通过。整机旧模板 `render_aircraft_schematic.py` 与 `validate_sysml.py` 是两套东西，不要混用。

## 入口决策表

`<skill>` = 本 skill 目录。退出码核实方式：**实测** = 实际运行得到；**源码** = 只读自脚本，未运行。

| 手上有什么 | 命令 | 退出码 |
|---|---|---|
| SysML 模型（**主链路**） | `python <skill>/scripts/validate_sysml.py --sysml IN.sysml [--layout-seed SEED] --workdir DIR` | 0 交付证据齐备 / 1 轮次耗尽仍有 fail / 2 转换被拦或 preflight 残差 / 3 工具链故障（含追溯链核验不成立）/ 4 零失败但交付证据未齐备 / 5 用法、IO、路径拒绝。**实测**：2（blocked 夹具）、5（缺 `--sysml`）、4（`l0-small-seed.sysml` 正例：追溯链 current、校核零失败，但缺感知签认，`delivery.ready=False`，无人工签认到不了 0）；0、1、3 为 **源码**，未触发 |
| 手写 intent | `python <skill>/scripts/validate_driver.py --intent INTENT.yaml [--layout-seed SEED] --workdir DIR` | 0 完整证据通过 / 1 轮次耗尽 / 2 preflight 残差 / 3 工具链故障 / 4 必检证据或感知签认未齐备。**实测**：缺 `--intent` 得 2（argparse 用法错误，与"preflight 残差"同码，需看输出区分）；其余 **源码** |
| 已有工作目录，只渲染 / 只校核 | `render_l0_sheet.py <workdir>`；`validate_sheet.py <workdir>` | 失败均为 1（**实测**：目录不存在得 1）；`validate_sheet` 校核失败也是 1（**源码**） |
| 只想预检 intent | `python <skill>/scripts/preflight.py INTENT.yaml [--json]` | 0 过 / 1 拦截 / 2 缺参数。**实测**：正例 0、文件不存在 1 |
| 只想把 SysML 转 intent | `python <skill>/scripts/sysml_to_intent.py IN.sysml [-o OUT]` | 0 成功 / 1 被诊断拦截 / 2 用法或 IO。**实测**：blocked 夹具 1 |
| 核验已有 SysML 追溯链 | `python <skill>/scripts/validate_sysml.py --verify WORKDIR` | 0 链 current / 1 不成立或与当前产物不符（**实测**：目录不存在得 1） |
| 改了符号或 catalog | `check_library.py`；单件用 `check_symbol.py FILE.svg` | check_library：0 过 / 1 断（**实测** 0）。check_symbol：0 过 / 1 ERROR / 2 用法（**实测** 1、2） |
| 改了脚本、符号、模板，要回归 | `python <skill>/scripts/selftest.py` | 0 过 / 1 断 / 2 用法或输出路径预检失败（**实测**：`--list-suites` 0、未知选项 2） |
| 整机 SysML（旧模板，非主链路） | 复制 `render_aircraft_schematic.py` 到工作目录再运行 | 以脚本自检输出为准（本表未核实） |

## 运行纪律

以下约定对上表所有 L0 入口通用，**只在此处定义**，别处只引用：

- **工作目录**：显式传独立 `--workdir`；驱动器复制执行依赖并刷新本轮产物，未传时用新的临时目录。工作目录不能位于 skill 规范源内，SysML 入口还拒绝输入与工作目录重叠。
- **布局来源**：已有布局传 `--layout-seed`；只有主动要求重新寻优才加 `--optimize`（该参数优先于 seed）。已有布局仍需完成本轮渲染与校验。
- **复用**：`--keep` 只复用未变化的依赖；输入重新读取，旧 SVG/PNG/校验报告失效后重建。
- **定制模板代码**时先复制到工作目录再改，不要改 skill 原位文件。
- **符号与路径**：种子引用的本地符号按实际文件复制，来源写入报告；端口坐标不同的旧符号不可仅改文件名替换。路径按脚本/输入文件位置解析；守门工具、布局引擎与确认单原位运行。

## 工作流

Phase 0–2.5（链路、符号准备、布局渲染、布局引擎/确认单/模板门禁/校核驱动器/搜索预算）与资产单源纪律见 [references/operations.md](references/operations.md)。该文件是自本文档下沉的原文，其中计数、基线状态、票号进度是写入时的陈述，现状以命令输出为准。

### Phase 3 · 追溯清单

对照 `scripts/render_aircraft_schematic.py` 中的 `render_manifest` / `self_check`：生成 `<name>_topology.md`，含"连接(边)映射"与"节点(part)映射"两张表，每行注明输入定义行号与实例数；概念级简化（如回油未建模）须在文末"简化说明"里逐条披露。

### Phase 4 · 校验闭环

按 [references/validation.md](references/validation.md) 执行三层：Python 结构自检（退出码门禁）→ `scripts/validate_sheet.py` 几何校核出 `validation-report.json` → 浏览器/Inkscape 渲染 PNG 回读做感知校核。任何一层不过，修图重跑，不带病交付。

## 细节索引

- [references/operations.md](references/operations.md)：Phase 0–2.5 流程、资产与单源纪律、库校验与 selftest 用法
- [references/sysml-l0.md](references/sysml-l0.md)：主链路的窄文法、CLI、追溯 sidecar、blocked 夹具
- [references/rendering-rules.md](references/rendering-rules.md)：线宽、走线、镜像、围框、构图预算
- [references/symbol-library.md](references/symbol-library.md)：符号与 connection-points 标注、入库步骤
- [references/validation.md](references/validation.md)：三层校验、处方对照表、交付判据
