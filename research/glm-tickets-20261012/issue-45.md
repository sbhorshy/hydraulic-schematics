# GitHub #45 · FOOTPRINT 新类型登记与引擎补齐 —— GLM 执行报告（二审修订）

- 执行者模型：bigmodel-api/GLM-5.3（ZCode 会话）
- 工单：sbhorshy/hydraulic-schematics#45（Parent #43，Blocked by #44）
- 基线：799b80a（独立 issue-45 worktree）
- 日期：2026-10-12（二审修订：纳入审核端实跑 probe 事实，统一复现命令口径）
- **结论：#45 仅部分完成，原票面正例未满足。** check_valve_refuel 核对通过（原登记正确）；check_valve_spring 完成三处登记（FOOTPRINT + 双册 catalog，事实全部取自符号实读）；eco_bottle 与接通位 quick_disconnect_coupling 经查证确属事实缺口，按工单指令不伪造登记（NEED-CLARIFICATION 见 §4），并阻塞 #47 后续对账。**当前项目 intent 的引擎 probe 为 exit 1**（§1.3，#46 气侧残差，正确 fail-closed）；本报告不承诺当前项目输入 engine exit 0。

## 0. 未实跑限制（诚实边界）

本会话 Bash 权限层未配置（仅放行只读文件命令；python/wsl/git 及子代理执行全被同一错误拦截），**整改后的测试与脚本 ZCode 未实际运行**。一审时 Codex 已实跑第一版 `FootprintRegistration45` 6 用例全部通过（日志 `../45-first-review-tests.log`，相对 worktree 根）；整改后为 4 用例，红/绿须由 Codex 按 §5 复跑取真证据。本报告引用的**项目引擎 probe 结果为审核端 2026-10-12 实跑事实**（§1.3），非推导。

## 1. 事实

### 1.1 四类型的资产/端口事实（全部静态实读，可复核）

- **check_valve_refuel**：check-valve.svg（与 check_valve 共用，viewBox `0 0 80 80`）；connection-points inlet(80,40) anchor=right / outlet(0,40) anchor=left；双册均已登记（role=return 为 2026-09-07 用户签认变体口径）。**核对通过，无需改动。**
- **check_valve_spring**：check-valve-spring.svg，viewBox `-48 0 96 142`（96×142）；connection-points inlet(0,142) anchor=down / outlet(0,0) anchor=up，role=pressure，status=provisional，源自 Drawing2.dxf。三处原先均未登记。**可登记（本次完成）。**
- **quick_disconnect_coupling（接通位）**：quick-disconnect-coupling.svg **无 connection-points**（B-2 挂账，check_library WHITELIST 在案）；双册未登记。**事实缺口，不登记。**
- **eco_bottle**：全库 22 个 SVG 无对应符号；双册未登记；sysml part def 仅单口 `inlet`。**事实缺口，不登记。**

### 1.2 引擎门禁链路（为何"登记"必须是三处）

`layout_engine.py` 入口门禁 `port_roles()`（layout_engine.py:136-148）要求类型**同时**登记于 catalog（端口事实）与 FOOTPRINT（足迹事实），否则 `SystemExit('规则引擎: 不支持的元件类型…')`。布点由 R1–R16 按 FOOTPRINT 尺寸做、不认实例名（串联中间件由 R2 类型无关逐件放置，layout_engine.py:273-281），故登记后 check_valve_spring 作为串联件即可被布点。覆盖外形态走"未布元件"fail-closed（layout_engine.py:586-589），口径未动。

### 1.3 当前项目输入的引擎实跑结果（审核端，2026-10-12）

从 worktree 根实跑（与 §5 D 同命令）：`python .agents/skills/hydraulic-schematic/scripts/layout_engine.py '1#系统原理图/1#系统.intent.yaml' '1#系统原理图/component-catalog.json' - -o ../45-project-probe.layout.json` → **exit 1**，stderr 逐字：`规则引擎: 未布元件 ['ACC-001', 'ACV-001', 'PG-001']——intent 形态超出 R1–R16 覆盖`（日志 `../45-project-probe.log`、布局 `../45-project-probe.layout.json`）。

- ACC-001/ACV-001/PG-001 为**前批 #46 气侧链带入**当前项目 intent 的实例，超出 R1–R16 覆盖，引擎按既定口径 fail-closed——**行为正确，本票不改引擎绕过此残差**。
- #44 时代"项目 probe exit 0"是当时输入下的历史事实，**不适用于当前项目输入**，本报告不以之作验收依据。
- 因此用例 3 的绿仅限 skill 自带 L0 fixture（§3），不外推到项目输入。

## 2. 改动清单（4 个文件）

| 文件 | 改动 |
|---|---|
| `.agents/skills/hydraulic-schematic/scripts/layout_engine.py` | FOOTPRINT 追加 `'check_valve_spring': (96, 142, 'symbols/check-valve-spring.svg', 142.0)`（port_dy=142.0 = 主端口 inlet 实读 y，竖直变体下缘；对照 relief_valve 竖直件先例）。含 4 行注释：来源实读 + QD/ECO 缺口指引。**规则、参数、B1–B7 守门零改动** |
| `.agents/skills/hydraulic-schematic/assets/component-library/component-catalog.json`（skill 册 0.7-draft） | 手工追加 check_valve_spring 条目：inline / main_path inlet→outlet / 两端口 hydraulic·pressure·in·down、out·up / rotations [0,90,180,270] / allow_mirror=false，字段全部与符号 connection-points 实读一致；description 仅保留 SVG 实测事实 |
| `1#系统原理图/component-catalog.json`（项目册 0.3-draft） | 追加同一条目（手工登记，符合项目册现状；**未触碰 build_catalog.py**） |
| `.agents/skills/hydraulic-schematic/scripts/test_entrypoints.py` | 新增 `FootprintRegistration45` 用例组（一审 6 → 整改后 4）；随 test_entrypoints 自动进入 selftest F 组 L0_SUITES，**selftest.py 零改动** |

两个有意的保守决定：① **catalog_revision 不递增**（skill 册保持 0.7-draft、项目册 0.3-draft：工单以 0.7-draft 为对齐基准，递增会触发既有 intent 的 preflight E-CAT-ID WARN；版本收编归 #48）；② 端口 role 登记 **pressure**（符号实读如此；回油变体角色若要成立须走 check_valve_refuel 式用户签认——一审擅写的"装配语境线型差异由 unknown 披露"先例规则已删）。

一审整改其余项：测试接缝改真实 CLI（删除对 `engine.FOOTPRINT` 内部表的全部直接断言）；双册 description 类型名笔误改正 `filter_line_shutoff_dp_return_bypass`（catalog 实有类型，component-catalog.json:867）；layout_engine.py 注释去 research/ 硬引用。

未改动：任何符号 SVG、既有 catalog 条目、preflight/render/validate、引擎规则与守门、.git（Windows git 不识别 Linux worktree gitdir 指针，提交留 Codex）。

## 3. 测试口径与状态

- 接缝 = `layout_engine.py` CLI 公开接口（真实 intent/catalog 文件进出、退出码、失败清单、guard 随 CLI 执行后的输出 layout 节点），**不断言引擎内部表**。
- 事实源 = 符号 SVG 实读 + skill 册 catalog，期望值不来自被测代码（无同义反复）；便携套件只用 skill 自带资产（fixtures/l0-current + 自带库），不引用 worktree 外文件；项目册对齐由 §5 E 手工命令覆盖。
- fail-closed 口径 = ECO/QD 实例加入后必须按类型逐条点名失败（不 KeyError、不 Traceback、不猜拓扑）。

4 用例（红绿预期见 §5 命令注释）：

1. `test_refuel_catalog_entry_matches_symbol_facts` — check_valve_refuel 条目（asset 名/端口对/main_path/allow_mirror）与 check-valve.svg 实读一致。
2. `test_spring_valve_catalog_entry_matches_symbol_port_group` — check_valve_spring 条目两端口 6 字段（element_id/medium/role/flow/anchor）逐一等于符号 connection-points。
3. `test_cli_places_spring_valve_and_reports_nodes_matching_symbol_facts` — 冻结 l0-current intent 插入弹簧阀 X-001 走 CLI：exit 0、guard 随 CLI 实际执行，输出节点 w/h/symbol 与符号 viewBox 实读逐一对账（CV-002 一并复账）。
4. `test_cli_reports_unregistered_types_fail_closed_with_actionable_list` — ECO-001/QD-001..003 加入后 exit 1、逐实例逐类型点名、无 KeyError/Traceback。

配套：`check_library.py` 预期 exit 0（新条目 asset 可解析、声明端口均在符号端口组内，L3 硬档）。

运行状态：一审 6 用例 Codex 实跑全过（0.421s，日志 `../45-first-review-tests.log`）；**整改后 4 用例未实跑**（§0）。

## 4. 未满足条件（原票正例对账 + NEED-CLARIFICATION）

**原票面正例未满足：**

- "项目 intent 过引擎不再 KeyError/正常布点"：**未满足**——当前项目 probe exit 1（§1.3：#46 气侧残差 ACC/ACV/PG 超 R1–R16 覆盖）。即使 ECO/QD 缺口解决，此残差仍需后续规则覆盖或工程决定，本票不绕过。
- "含 CV-002/ECO/QD 实例的项目 intent 过引擎"：**未满足**——ECO/QD 无法登记（下述缺口）；sysml→intent 落地属 #51/#52，本票不吞并。用例 4 只验证 fail-closed 行为正确（无 KeyError/Traceback），**不构成等价验收**。
- check_valve_refuel 的 KeyError 崩塌类已消除：三处登记齐备，用例 1+3 在 L0 fixture 上钉住 catalog/符号一致与 CLI 布点（不外推项目输入）。
- "R1–R16 覆盖外形态仍 fail-closed（'未布元件'清单口径不变）"：layout_engine.py:586-589 未动；既有 `test_unsupported_refuel_connection_is_not_guessed`（test_entrypoints.py:94-99）与用例 4 共同覆盖。

**NEED-CLARIFICATION（需工程口径，阻塞 #47 后续对账）：**

1. **eco_bottle（ECO-001）**：无符号、无双册条目、无尺寸事实；sysml 定义仅单口 `inlet`（"溢流收集口,接 EMP 溢流口"），对端 `EMP-001.overflow` 端口在 catalog/SVG 中不存在（现行 EMP 只有 elec_power=electrical/signal_in；改义属工程端口变更，#44 亦裁定"EMP overflow 不能猜"）。需工程确认：符号/尺寸方案、EMP 溢流口是否为 elec_power 改义。
2. **quick_disconnect_coupling（QD-001..003 接通位）**：符号无 connection-points（B-2 重绘挂账）；端口命名两口径冲突——sysml 用 `inlet/outlet`（1#系统.sysml:199-204 等）vs catalog B-2 规定连接位重绘沿用断开位侧别名 `aircraft_side/ground_side`（component-catalog.json drawing_blockers B-2）；符号为 CAD mm 原尺度（viewBox 27.297×11），入库还需出图缩放口径。需工程确认命名口径 + 补端口组；在此之前登记任何足迹/端口行都属伪造。
3. （次要披露）skill 册 0.7-draft 实有 24 类型条目（工单写作"23 类型"；不含 hydraulic_user 通用名框则恰 23）；本次登记后 25（不含则 24）。

## 5. 精确复现命令（Codex 复跑取真证据）

统一约定：**全部命令从 worktree 根运行、脚本用全相对路径**；仅单元测试因 `-m unittest` 模块发现需要**显式 cd** 进 scripts 目录。基线环境 WSL `/usr/bin/python3`。

```bash
cd "/mnt/d/file/comac/组件库/.scratch/glm-work-20261012/issue-45"

# A. 红：基线对照在 799b80a 的独立临时副本中进行（复制目录或由 Codex 另建 worktree 均可），
#    只应用 test_entrypoints.py 改动；不使用 git stash，不影响当前 worktree。
#    在该副本的根目录执行：
cd .agents/skills/hydraulic-schematic/scripts
/usr/bin/python3 -m unittest test_entrypoints.FootprintRegistration45 -v
#    预期：用例 2 ERROR(StopIteration)（双册无 check_valve_spring 条目）、
#          用例 3 FAIL(CLI exit 1，stderr 点名 X-001 check_valve_spring 未登记)；用例 1/4 PASS

# B. 绿：当前 worktree（全部整改改动就位），同命令
cd "/mnt/d/file/comac/组件库/.scratch/glm-work-20261012/issue-45/.agents/skills/hydraulic-schematic/scripts"
/usr/bin/python3 -m unittest test_entrypoints.FootprintRegistration45 -v   # 预期 4 用例全 PASS
/usr/bin/python3 -m unittest test_entrypoints -v                          # 含既有 LayoutEntrypoints 回归

# C. 库门禁（L1–L3 硬档）；以下命令回到 worktree 根执行
cd "/mnt/d/file/comac/组件库/.scratch/glm-work-20261012/issue-45"
/usr/bin/python3 .agents/skills/hydraulic-schematic/scripts/check_library.py
#    预期 exit 0；INFO 仅既有 QD 连接位 WHITELIST 豁免一行

# D. 项目真实输入引擎 probe（审核端 2026-10-12 已实跑：exit 1，证据见 §1.3）
/usr/bin/python3 .agents/skills/hydraulic-schematic/scripts/layout_engine.py \
    "1#系统原理图/1#系统.intent.yaml" "1#系统原理图/component-catalog.json" \
    - -o ../45-project-probe.layout.json
#    预期 exit 1：规则引擎: 未布元件 ['ACC-001', 'ACV-001', 'PG-001']——intent 形态超出 R1–R16 覆盖
#    （#46 气侧残差，正确 fail-closed；本票不改引擎绕过）

# E. 双册对齐（skill 册 vs 项目册 check_valve_spring 条目逐字段相等）
/usr/bin/python3 - <<'EOF'
import json
skill = json.load(open(".agents/skills/hydraulic-schematic/assets/component-library/component-catalog.json", encoding="utf-8"))
proj  = json.load(open("1#系统原理图/component-catalog.json", encoding="utf-8"))
a = {c["component_type"]: c for c in skill["components"]}["check_valve_spring"]
b = {c["component_type"]: c for c in proj["components"]}["check_valve_spring"]
assert a == b, "dual-catalog check_valve_spring mismatch"
print("dual-catalog check_valve_spring aligned:", a["display_name"])
EOF

# F. 全量回归（主审核端统一执行，本票未跑）
/usr/bin/python3 .agents/skills/hydraulic-schematic/scripts/selftest.py
```

## 6. 边界遵守声明

未推送、未评论 GitHub、未关票、未合并、未跑全量 selftest、未改主工作区或其他 worktree、未改 .git（Windows git 不识别 Linux worktree 指针，提交留 Codex）、未重跑 build_catalog.py、未改任何符号 SVG/既有 catalog 条目/工程角色、未放宽 B1–B7、未解禁镜像、未删除任何 unknown 挂账、未吞并 #47/#51/#52、未改任何既有 CDF 图、未替用户做 #36 选型、**未改引擎规则以绕过 #46 气侧残差**。整改轮 ZCode 未运行任何测试（会话无 Bash 权限层，仅 Read/Edit/Write 改文件），不声称实跑红绿；项目 probe 事实引自审核端实跑日志。
