---
name: hydraulic-schematic
description: Draw or update hydraulic system schematic sheets from a single input definition — a SysML v2 model or an L0 intent.yaml — reusing an annotated stroke-symbol SVG library (connection-points; bundled snapshot included), with orthogonal routing, a line-level traceability manifest mapping every node/edge to unique input definitions, and a geometry + perceptual validation loop. Use when asked to 绘制/更新系统原理图 or 液压原理图, to 标注新符号 (add connection-points to an element SVG), to generate a 追溯清单 for a drawing, or to 校验/回读 a rendered sheet. Also for extending the component catalog in component-catalog.json.
---

# 液压系统原理图工作流

从**唯一输入定义**（SysML v2 模型，或 L0 `intent.yaml`）出发，复用已标注描边符号库绘制系统原理图 SVG，生成行号级追溯清单，并以"几何校核 → 感知回读"闭环验证。

## 不变式（任何阶段不得违反）

1. **可追溯**：图中任一组件/端口/连接/图元必须能追溯到唯一输入定义（SysML 行号或 intent 锚点）。渲染出的 SVG 元件带 `data-node` / `data-port` / `data-edge` / `data-sysml-line` / `data-zone`；同时产出追溯清单 markdown。
2. **不编造拓扑**：类型不在目录内则其端口不存在，不得出现在 paths/连线中；数量未声明的类型按 1 实例处理；不知道怎么连就写进 intent 的 `unknown:` 段，别画。
3. **确定性优先**：布局坐标显式给定，不做自动布局；端口坐标从符号 SVG 的 `connection-points` 实读，不硬编码。
4. **校验不过即是失败**：结构自检失败以退出码 1 终止并报告缺项；无回读图的校核项记为"未校核"，不许静默放过。

## 工作流

### Phase 0 · 选定链路

| 链路 | 输入 | 模板脚本（skill 自带 `scripts/`） | 范例输入（`assets/examples/`） |
|---|---|---|---|
| 整机/SysML | `*.sysml`（SysML v2：part/port/connect） | `render_aircraft_schematic.py` | `aircraft_hydraulic_system.sysml` |
| 分系统/L0 | `intent.yaml` + `*.layout.json` | `render_l0_sheet.py` | `system-1.intent.yaml`、`1#系统.layout.json` |

两条链路共享符号库、视觉常量与校验理念。已有模型就用对应链路，不要混用。模板脚本的文件名/输出路径常量按目标系统改——**复制到你自己的工作目录后修改运行**，不要原地执行 skill 里的副本。

### Phase 1 · 符号准备

组件库有两个位置，**优先用当前工作区的，没有才用 skill 自带快照**：

1. 当前工作区存在 `已标注/component-catalog.json` → 以它为活动库（这是规范源）。
2. 否则用本 skill 的 `assets/component-library/`（符号 SVG + 目录 JSON 的同步快照），文件按文件名在其中定位。

只有带 `<g id="connection-points">` 标注的符号可直接参与绘图。需要标注新符号时，遵循 [references/symbol-library.md](references/symbol-library.md) 的标注规范；改的是哪一份库就属于哪一份——仓库里改完记得刷新 skill 快照。

### Phase 2 · 布局与渲染

线宽/线型/走线/镜像/分区框/图签图例的完整约定见 [references/rendering-rules.md](references/rendering-rules.md)。照抄模板脚本的结构（局部回路 + 水平镜像，或 layout.json 显式坐标），只改拓扑数据，不改约定本身。

### Phase 3 · 追溯清单

对照 `scripts/render_aircraft_schematic.py` 中的 `render_manifest` / `self_check`：生成 `<name>_topology.md`，含"连接(边)映射"与"节点(part)映射"两张表，每行注明输入定义行号与实例数；概念级简化（如回油未建模）须在文末"简化说明"里逐条披露。

### Phase 4 · 校验闭环

按 [references/validation.md](references/validation.md) 执行三层：Python 结构自检（退出码门禁）→ `scripts/validate_sheet.py` 几何校核出 `validation-report.json` → 浏览器/Inkscape 渲染 PNG 回读做感知校核。任何一层不过，修图重跑，不带病交付。

## 随附资产与快照同步

本 skill 自包含三组资产（均为仓库规范源的同步快照）：

| 资产 | 内容 |
|---|---|
| `assets/component-library/` | 已标注描边符号 SVG + component-catalog.json |
| `scripts/` | 两链路渲染模板、`validate_sheet.py` 几何校核、`test_suction_markers.py` 专项测试范例 |
| `assets/examples/` | SysML 模型范例、L0 intent+layout 范例、校验负例（负例 expected-report 配对） |

依赖提示：L0 渲染器需要 `ruamel.yaml`；其余仅标准库。

在仓库里修订了符号、目录或脚本后，用随附的同步守门工具刷快照（**默认 dry run 只审计，加 `--apply` 才写入**）：

```bash
python .agents/skills/hydraulic-schematic/scripts/sync_snapshot.py            # 审计：列出三组差异
python .agents/skills/hydraulic-schematic/scripts/sync_snapshot.py --apply    # 同步 + 报告端口变化
```

工具内置闸门：源符号若丢失标准 `connection-points` 端口组而快照现版有之，拒绝拷入该文件（exit 1），确认非误伤才 `--force`。排除规则会拦截测试图/预览图混入；`--prune` 清理存量垃圾。退出码：0 一致/已同步，1 有拦截，2 有待同步差异（dry run）。

同一审计已接入 **pre-push 钩子**（`.git/hooks/pre-push`，不入库）：快照与规范源存在差异即拒绝推送，按提示跑 `--apply` 后重推即可；确需强行越过用 `git push --no-verify`（不建议）。更完整的回归自测试见「金样回归 selftest」工单。
