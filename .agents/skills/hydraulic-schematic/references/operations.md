# 流程细节与资产纪律（自 SKILL.md 下沉）

> 这些章节原在 `SKILL.md` 中，为让主文档只留不变式、入口与主路径而整段下沉，
> **正文未改动**。其中的计数、基线状态、票号进度是写入时的历史陈述；
> 现状以命令输出为准（`check_library.py --json`、`check_symbol.py --all`、
> `selftest.py --list-suites`），不要把这里的数字当作当前事实。

## Phase 0 · 选定链路

| 链路 | 输入 | 入口脚本（skill 自带 `scripts/`） | 范例输入 |
|---|---|---|---|
| **主链路 · 分系统 SysML→L0** | `*.sysml`（窄文法，见 [references/sysml-l0.md](references/sysml-l0.md)） | `validate_sysml.py`（内置 `sysml_to_intent.py` 转换 → preflight → `validate_driver.py`，不要求先手工生成 intent） | `assets/fixtures/sysml-l0/l0-small-seed.sysml`（配 l0-small-seed 布局 seed） |
| 分系统/L0（手写 intent，主链路的下游） | `intent.yaml` + `*.layout.json` | `validate_driver.py` / `render_l0_sheet.py`（内置 `preflight.py` 预检） | `assets/fixtures/l0-current/` 当前 23 部件；`assets/fixtures/l0-small-seed/` 最小通过基准 |
| 整机 SysML（旧模板，非主链路） | `*.sysml`（SysML v2：part/port/connect） | `render_aircraft_schematic.py` | `assets/examples/aircraft_hydraulic_system.sysml` |

**主链路是 SysML 窄文法 → intent → L0 全链**：SysML 模型是唯一输入定义，intent 是其转换产物。窄文法只覆盖已登记的类型与写法；模型里出现目录没有的类型或端口时，转换被准确拒绝（fail-closed），不得靠删节点、假造目录或手写 intent 顶替。真实 1# 模型目前仍因工程事实被拒绝（ECO/接通位 QD 无目录类型、EMP overflow 端口不存在），详见 reference 的 blocked 夹具；这是已披露的限制，不是链路通过。整机旧模板与 `validate_sysml.py` 是两套东西，不要混用。

三条链路共享符号库、视觉常量与校验理念。L0 链路在渲染器 parse 后、布局前强制跑 `scripts/preflight.py` 预检（JSON Schema 形状层 + 端口/role/medium 语义层，一次报齐）：任何 ERROR 即扣留 layout/svg/topology 并以退出码 1 终止；也可独立同源调用：`python scripts/preflight.py <intent.yaml>`（0 过 / 1 拦，`--json` 出结构化 findings）。已有模型就用对应链路，不要混用。

L0 链路运行口径（#21 起）：`render_l0_sheet.py` 与 `validate_sheet.py` 都接受可选**工作目录**参数——

```bash
python <workdir 外的任意位置>/render_l0_sheet.py <workdir>   # 读 <workdir>/1#系统.intent.yaml + 1#系统.layout.json，出同名 svg
python <skill>/scripts/validate_sheet.py <workdir>           # 出 <workdir>/validation-report.json（V16 需先生成 1:1 sheet-readback.png）
```

符号解析顺序：工作目录相对（本地覆盖，传统复制纪律仍然成立）→ **catalog 同目录**（单源化：catalog 在哪，库就在哪；不传本地 catalog 时即锚定 skill 自带库，工作目录不再需要 `symbols/` 拷贝）。缺省不带参数=脚本就地（历史复制纪律兼容）。模板脚本的文件名/输出路径常量如需按目标系统改名，仍可复制到工作目录后修改运行。

## Phase 1 · 符号准备

组件库**只有一处**：本 skill 的 `assets/component-library/` 即唯一规范源（单源化，#20/#21 定案；旧"已标注规范源→快照"两处库教义随规范源归档作废）。文件按文件名在其中定位，catalog 0.6-draft 登记 22 个组件类型（0.6 增油箱本体感测口 body_sense_tap 与 port_kind 枚举，2026-09-07 签认 B 类）。

**新建/重绘符号一律复制 `assets/component-library/_template.svg` 起稿**（技术规范 §6.3.1 的可拷贝实现，占位符 `{{...}}`），填完过符号入库门禁 `scripts/check_symbol.py <file.svg>`（6.4 第 1–12 条 + C13 方框基准；#31 已归位 skill scripts：默认库与 catalog 锚定本 skill 自带 `assets/component-library/`，任意 cwd 可用，`--all` 全量扫默认库（与显式文件互斥），退出码 0 过 / 1 ERROR，文件/库目录/catalog 缺失或畸形一律 fail-closed——空/坏 JSON/类型重复/端口 id 重复同拦）再入库；模板与规范条文两处同步修订。

**用户（用油设备）不需要新符号**：intent `parts` 直接写 `<inst>: hydraulic_user`，画成"用户名+长方形框"，左压力进口/右回油出口，名字由 L0 渲染器写入框内名槽（`data-name-slot`）——详见 [references/symbol-library.md](references/symbol-library.md) 的通用用户框一节。

## Phase 2 · 布局与渲染

线宽/线型/走线/镜像/分区框/图签图例的完整约定见 [references/rendering-rules.md](references/rendering-rules.md)。照抄模板脚本的结构（局部回路 + 水平镜像，或 layout.json 显式坐标），只改拓扑数据，不改约定本身。L0 链路镜像默认禁止（#63 条件解禁）：布局节点 `mirror: 'x'/'y'` 仅对目录完成三道闸登记（`mirror_safe` + `layout.allow_mirror` + `mirror_registration`）的组件放行——当前生产仅发动机驱动泵与电动泵（axes x/y），端口 id/role/medium/flow 不交换，实例记 `data-mirror` 并入追溯清单，登记不提升成熟度；SysML 模板的"局部回路 + 水平镜像"是整图 `<image>` 翻转技法，不经此闸。

## Phase 2.5 · 自动布局与自动收敛（#22 沉淀）

L0 链路「人工给坐标」可由三件工具接管（驱动器自带沙箱复制纪律，可直接原位运行）：

- **布局引擎 `layout_engine.py`**：`python layout_engine.py <intent> <catalog> <ref|-> -o <out.layout.json> [--guard-report R.json] [--param KEY=VAL] [--optimize]`。两段式：规则定行位（自由度全收参数表 `P`，`--param` 可覆写；**缺省值按 1# 系统调校，披露**）+ kiwi REQUIRED 守门（规则解自洽即零漂移，不可满足则报错退出，绝不静默出图）。`--optimize` 叠加第三阶段寻优（B1–B5 指标 + V2/V13 硬缺陷 + 不劣化下限，固定种子首改进下降）。B3 边界走廊豁免判点可由布局 json 的 `boundary_terminals` 键给出（`[[x,y],...]`），缺省为 1# 实测值——新系统接入应在布局中显式给出。
- **拓扑确认单 `topology_confirm.py`**：`python topology_confirm.py <intent> <受控模板.yaml> -o <确认单.md>`——分段拓扑逐行签认 + 三向机器对账（intent↔受控模板互为背书，对账差异=退出码 1，确认单仍生成供工程师签认或退回）。
- **模板门禁**：preflight（渲染器钩子与 CLI 同源）在 intent 同目录发现唯一 `*受控模板.yaml` 即启用三向对账；签认按 maturity 分级——**concept 未签认=WARN 披露放行，其余 maturity 未签认=ERROR 扣留产物**（正式出图必须先逐行签认确认单并在模板签认区登记 signed）。
- **校核驱动器 `validate_driver.py`**：`python validate_driver.py --intent <intent> [--layout-seed S.json] [--ref R.json] [--optimize] [--workdir DIR] [--readback-w W]`——preflight 门禁 → 布局（种子或引擎）→ 渲染 → 校核，按处方表有界收敛（默认两轮）：**P1** 纯传感链误入 paths 自动降级 taps；**P3** 几何硬缺陷（V2/V13/V19）引擎重推+寻优；其余残差上报不烧轮次。退出码 0 完整证据通过 / 1 轮次耗尽 / 2 preflight 残差 / 3 工具链故障 / 4 必检证据或感知签认未齐备。每轮渲染后由 `rasterize_sheet.py` 自动选择本机 Inkscape 或 Chrome，重出 1:1 PNG；无可用转换工具则报告故障，不能收敛。沙箱包含脚本、符号、catalog 和 schema。驱动器的 `converged` 保留已执行检查零失败的兼容含义；覆盖状态、版本验证和感知签认按 [校验闭环](references/validation.md) 执行，以 `delivery.ready` 判定交付。

**搜索预算与进度**：布局引擎/驱动器共享 `--max-evals`、`--max-steps`、`--max-seconds`、`--polish-steps`，默认 200 次评估 / 50 个改善步 / 30 秒 / 不额外抛光。时间限在两次评估之间检查；每个评估本身不可中断，驱动器另设子进程上限。预算耗尽保留最佳候选并继续全量校核，停止原因不代表通过；仍有缺陷则返回残差，勿反复加大预算盲搜。`convergence-report.json` 记录每阶段耗时和寻优停止原因，stderr 实时显示进度。

驱动器的完整命令行与退出码见上文「入口决策表」；工作目录、`--layout-seed` / `--optimize` 的优先关系、`--keep` 语义见「运行纪律」，此处不再重复。

## 随附资产与单源纪律（#20 定案）

本 skill 自包含四组资产：

| 资产 | 内容 |
|---|---|
| `assets/component-library/` | 描边符号 SVG（kebab-case 规范名）+ component-catalog.json |
| `assets/contracts/` | `l0-input-contract.schema.json`——L0 intent 结构契约（预检器形状层，也可被编辑器/CI 独立消费） |
| `scripts/` | 两链路渲染模板、`preflight.py` L0 输入预检器（含模板门禁）、`validate_sheet.py` 几何校核、`check_library.py` 库结构校验器、`check_symbol.py` 符号入库门禁（6.4 第 1–12 条 + C13 方框基准，#31 归位）、`layout_engine.py` 布局引擎（规则+守门+寻优）、`proto_optimize.py` 寻优层、`validate_driver.py` 校核驱动器、`topology_confirm.py` 拓扑确认单、`test_suction_markers.py` 专项测试范例 |
| `assets/examples/` | SysML 模型范例、L0 intent+layout 范例、校验负例（负例 expected-report 配对；`negative-mixed-violations` 为七类违规混样、`positive-preflight-cleared` 为预检正例，供 preflight 回归） |

依赖提示：L0 需要 `ruamel.yaml`；形状预检需要 `jsonschema`（缺失时披露 WARN）；布局守门需要 `kiwisolver`。PNG 回读需要本机 Inkscape 或 Chrome，像素检查需要 Pillow 与 NumPy。

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
- 逐件入库门禁 `scripts/check_symbol.py` 与 check_library 同款锚定（默认库=catalog=
  skill 自带资产）。当前全量基线**未绿**：旧 `fsov-provisional-stroke.svg`（端口与
  catalog `main_upper/main_lower` 双向失配，待工程处置）与接通位
  `quick-disconnect-coupling.svg`（无端口组/无类型标注/尺寸带 mm 单位，B-2 挂账
  [#22](https://github.com/sbhorshy/hydraulic-schematics/issues/22)）两件 ERROR、
  退出码 1；「22 只存量符号全量绿跑」仍是 [#31](https://github.com/sbhorshy/hydraulic-schematics/issues/31)
  未完成验收项，不得以跳过、白名单或 WARN 冒充通过（WARN 只披露，不构成工程签认）。
- 改动符号/catalog 后先跑 `check_library.py`（库结构校验器），再跑 selftest
  （见下）。**pre-push 钩子**（`.git/hooks/pre-push`，不入库）接的是
  check_library.py，#31 未改钩子；check_symbol.py 的全量扫描不在 pre-push
  内，维持既有披露口径手动/CI 运行。库结构不过即拒绝推送；确需强行越过用
  `git push --no-verify`（不建议，须披露）。

改动符号、catalog 或模板脚本后，跑一条命令的基准图回归确认出图能力未被打破（详细覆盖面见 `scripts/selftest.py` 头注）：

```bash
python .agents/skills/hydraulic-schematic/scripts/selftest.py    # 0 过 / 1 断 / 2 用法或输出路径预检失败
# 可选：--jobs N(1..4) 逐套件有界并行；--suite-timeout 秒 单套件测试进程挂起保护上限
# （不是构图/寻优预算——寻优预算见 Phase 2.5 的 --max-evals/--max-seconds）；
# --log-dir 新目录 逐套件实时日志；--report 新 JSON 完整机器报告；
# --list-suites 纯 JSON 列 F 组全部套件（以 selftest.py 的 L0_SUITES 注册表为准）；
# --update-golden 重录金样；
# HYDRAULIC_SELFTEST_UNIT_LOG=/新路径 另存 F 组独占合并完整日志。
```

F 组固定执行完整 L0_SUITES 清单（由 `scripts/selftest_runner.py` 逐套件独立进程调度；套件数以注册表为准，不在文档写死绝对数），任何套件未过即整体失败，没有缩小范围却宣称完整通过的旁路。逐套件调度器的专项测试（`tests/scheduler/`）与仓库 editor/project 集成测试（`tests/repository/`）都不在本自检内，各自单独命令运行。
