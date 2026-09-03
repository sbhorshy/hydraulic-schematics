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

## 规则优先级

要求冲突时从高到低裁决：用户显式要求 > 符号/风格约定 > 图类布局规则 > 通用默认。
唯一不可豁免的下限是 Phase 4 校验闭环：任何上层要求（包括用户显式要求）都不得跳过或弱化三层闸门；
冲突时要么修图重跑直至全绿，要么把差异逐条披露后按概念图降级交付——不带病通过，也不静默截断校验。

## 运行纪律

- 渲染/校验模板脚本一律先复制到你的工作目录再修改运行，不要原地执行 skill 里的副本。
- 脚本输入输出路径以脚本自身位置解析（HERE 同级/上级常量），不假设当前工作目录 = skill 目录；
  换目标系统时只改顶部路径常量与拓扑数据，在任何 CWD 下运行同一份副本结果一致。
- 守门工具 `check_library.py` 与 `selftest.py` 是例外：它们属于 skill 基础设施，不复制，
  按「随附资产与单源纪律」的原位命令从仓库根直接运行。

## 工作流

### Phase 0 · 选定链路

| 链路 | 输入 | 模板脚本（skill 自带 `scripts/`） | 范例输入（`assets/examples/`） |
|---|---|---|---|
| 整机/SysML | `*.sysml`（SysML v2：part/port/connect） | `render_aircraft_schematic.py` | `aircraft_hydraulic_system.sysml` |
| 分系统/L0 | `intent.yaml` + `*.layout.json` | `render_l0_sheet.py`（内置 `preflight.py` 预检） | `system-1.intent.yaml`、`1#系统.layout.json` |

两条链路共享符号库、视觉常量与校验理念。L0 链路在渲染器 parse 后、布局前强制跑 `scripts/preflight.py` 预检（JSON Schema 形状层 + 端口/role/medium 语义层，一次报齐）：任何 ERROR 即扣留 layout/svg/topology 并以退出码 1 终止；也可独立同源调用：`python scripts/preflight.py <intent.yaml>`（0 过 / 1 拦，`--json` 出结构化 findings）。已有模型就用对应链路，不要混用。

L0 链路运行口径（#21 起）：`render_l0_sheet.py` 与 `validate_sheet.py` 都接受可选**工作目录**参数——

```bash
python <workdir 外的任意位置>/render_l0_sheet.py <workdir>   # 读 <workdir>/1#系统.intent.yaml + 1#系统.layout.json，出同名 svg
python <skill>/scripts/validate_sheet.py <workdir>           # 出 <workdir>/validation-report.json（V16 需先 Inkscape 回读 sheet-readback.png）
```

符号解析顺序：工作目录相对（本地覆盖，传统复制纪律仍然成立）→ **catalog 同目录**（单源化：catalog 在哪，库就在哪；不传本地 catalog 时即锚定 skill 自带库，工作目录不再需要 `symbols/` 拷贝）。缺省不带参数=脚本就地（历史复制纪律兼容）。模板脚本的文件名/输出路径常量如需按目标系统改名，仍可复制到工作目录后修改运行。

### Phase 1 · 符号准备

组件库**只有一处**：本 skill 的 `assets/component-library/` 即唯一规范源（单源化，#20/#21 定案；旧"已标注规范源→快照"两处库教义随规范源归档作废）。文件按文件名在其中定位，catalog 0.4-draft 登记 22 个组件类型。

**新建/重绘符号一律复制 `assets/component-library/_template.svg` 起稿**（技术规范 §6.3.1 的可拷贝实现，占位符 `{{...}}`），填完过符号入库门禁 `check_symbol.py <file.svg>`（6.4 第 1–12 条 + C13 方框基准；脚本暂随工作区携带，规范源归位挂账 [#31](https://github.com/sbhorshy/hydraulic-schematics/issues/31)）再入库；模板与规范条文两处同步修订。

**用户（用油设备）不需要新符号**：intent `parts` 直接写 `<inst>: hydraulic_user`，画成"用户名+长方形框"，左压力进口/右回油出口，名字由 L0 渲染器写入框内名槽（`data-name-slot`）——详见 [references/symbol-library.md](references/symbol-library.md) 的通用用户框一节。

### Phase 2 · 布局与渲染

线宽/线型/走线/镜像/分区框/图签图例的完整约定见 [references/rendering-rules.md](references/rendering-rules.md)。照抄模板脚本的结构（局部回路 + 水平镜像，或 layout.json 显式坐标），只改拓扑数据，不改约定本身。

### Phase 3 · 追溯清单

对照 `scripts/render_aircraft_schematic.py` 中的 `render_manifest` / `self_check`：生成 `<name>_topology.md`，含"连接(边)映射"与"节点(part)映射"两张表，每行注明输入定义行号与实例数；概念级简化（如回油未建模）须在文末"简化说明"里逐条披露。

### Phase 4 · 校验闭环

按 [references/validation.md](references/validation.md) 执行三层：Python 结构自检（退出码门禁）→ `scripts/validate_sheet.py` 几何校核出 `validation-report.json` → 浏览器/Inkscape 渲染 PNG 回读做感知校核。任何一层不过，修图重跑，不带病交付。

## 随附资产与单源纪律（#20 定案）

本 skill 自包含四组资产：

| 资产 | 内容 |
|---|---|
| `assets/component-library/` | 描边符号 SVG（kebab-case 规范名）+ component-catalog.json |
| `assets/contracts/` | `l0-input-contract.schema.json`——L0 intent 结构契约（预检器形状层，也可被编辑器/CI 独立消费） |
| `scripts/` | 两链路渲染模板、`preflight.py` L0 输入预检器、`validate_sheet.py` 几何校核、`check_library.py` 库结构校验器、`test_suction_markers.py` 专项测试范例 |
| `assets/examples/` | SysML 模型范例、L0 intent+layout 范例、校验负例（负例 expected-report 配对；`negative-mixed-violations` 为七类违规混样、`positive-preflight-cleared` 为预检正例，供 preflight 回归） |

依赖提示：L0 渲染器与预检器需要 `ruamel.yaml`；预检器形状层另需 `jsonschema`（缺失时形状层降级为 WARN，语义层照跑）；其余仅标准库。

本 skill 即组件库的**唯一规范源**（单源化，2026-09-01）：`assets/component-library/`、
`scripts/`、`assets/examples/` 不再是对外副本，没有「规范源→快照」的镜像同步。
旧的镜像工具 `sync_snapshot.py` 已随规范源归档退役；其核心价值——端口回退检测
（油箱事件：符号编辑丢失 `connection-points`）——由**库结构校验器**承接：

```bash
python .agents/skills/hydraulic-schematic/scripts/check_library.py     # 0 过 / 1 断
```

- **L1** 每个 SVG 必须是合法 XML；**L2** 必须含 `connection-points` 端口组且
  组内 `data-port-id` 唯一、全文件元素 id 不得重复（渲染器按实例改名符号内
  id，文件内重 id 会在整图撞车）——已知方言缺口走 `WHITELIST`（每项带理由
  与跟踪票，白名单是挂账不是赦免）；**L3** catalog↔symbol 交叉校验：`symbol.asset`
  解析不到库内文件或 catalog 声明端口缺于符号端口组，**默认即硬失败**
  （#21 回登记完成后转正；`--lenient-catalog` 可临时降宽容档出清单）。
- 改动符号/catalog 后先跑它，再跑 selftest（见下）。**pre-push 钩子**
  （`.git/hooks/pre-push`，不入库）已接本工具：库结构不过即拒绝推送；
  确需强行越过用 `git push --no-verify`（不建议，须披露）。

改动符号、catalog 或模板脚本后，跑一条命令的基准图回归确认出图能力未被打破（详细覆盖面见 `scripts/selftest.py` 头注）：

```bash
python .agents/skills/hydraulic-schematic/scripts/selftest.py    # 0 过 / 1 断
```
