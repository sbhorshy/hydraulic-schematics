> 审核补注：这是 GLM 首轮执行报告；后续修正、实际测试与状态以 [review-31.md](review-31.md) 为准。

# #31 符号入库门禁规范源归位 —— 执行记录（GLM，2026-10-12）

工作区：独立 issue-31 worktree（`D:\file\comac\组件库\.scratch\glm-work-20261012\issue-31`）。
执行环境限制：ZCode edit CLI 无 Bash 执行权限（只读 `ls`/`grep` 可用），**Python/WSL/git
一律未运行**——本文所有"预期输出/退出码"均为代码走查推演，附既有实测佐证，**未执行**，
待 Codex 审核端实际运行核验（命令见 §5）。未改 `.git`、未推送、未评论 GitHub、未动其他
worktree、未删除任何历史资产、未重绘符号、未捏造端口、未调整成熟度、未跑整套 selftest。

## 1. 变更清单（本票实际修改）

| 文件 | 变更 |
|---|---|
| `.agents/skills/hydraulic-schematic/scripts/check_symbol.py` | **新增（规范源）**。以工作区副本为底本迁入；校核规则 `check()`（C1–C13）逐行未动；CLI 重写为 argparse（`files` / `--all` / `--lib` / `--catalog`），目录与 catalog 锚定改为脚本自身位置解析（`<skill>/assets/component-library/`），并补 fail-closed（见 §3） |
| `1#系统原理图/check_symbol.py` | **退役为薄兼容入口**。照 `validate_sheet.py`/`render.py` 同款形式（runpy 透传 skill 脚本）；无默认参数注入——无位置参数时由规范源全量扫 skill 自带库（旧"扫脚本所在工作区目录"语义随副本一并退役）。历史全文仍在 git（`f3a00952` 捕获）与 `proto/frozen/check_symbol.py` 冻结件中 |
| `.agents/skills/hydraulic-schematic/scripts/test_symbol_gate.py` | **新增**。skill 便携 CLI 回归（6 用例），已注册 selftest F 组 |
| `.agents/skills/hydraulic-schematic/scripts/selftest.py` | `L0_SUITES` 增加 `test_symbol_gate`；F 组标签与头注补"符号入库门禁 CLI"及红基线钉扎说明 |
| `tests/repository/test_symbol_gate_entry.py` | **新增**。项目兼容入口集成回归（4 用例：任意 cwd 指定件 / 无参全量红基线 / WARN 不签认 / 假仓库相对布局解析） |
| `.agents/skills/hydraulic-schematic/SKILL.md` | ① Phase 1 门禁引用改指 `scripts/check_symbol.py` 并**撤销"脚本暂随工作区携带、归位挂账 #31"注记**；② scripts 资产表补登 `check_symbol.py`；③ 单源纪律节新增"全量基线未绿（2 件已知 ERROR、退出码 1），全量绿跑仍是 #31 未完成验收项，不得以跳过/白名单/WARN 冒充" |
| `.agents/skills/hydraulic-schematic/references/symbol-library.md` | ① C13 门禁段撤销挂账句，改归位口径（锚定/`--all`/退出码/fail-closed）并保留全量未绿事实；② 「标注新符号的步骤」补第 6 步：入库前过门禁 |
| `1#系统原理图/README.md` | 复制纪律口径更新：`check_symbol.py` 列入本目录规范源薄入口清单，"没有第二份渲染/校核/**门禁**实现" |
| `docs/规格与需求.md`（§工具表后现状句） | 现状句由"暂随工作区携带，归位挂账 #31"改为"已随 #31 归位 skill scripts……全量绿跑基线因两件已知缺陷仍未建立"（该文档为快照非规范源，仅改此现状句；§迁移叙事与 R3 需求行保留原文） |

未动：`1#系统原理图/proto/frozen/check_symbol.py`（冻结证据）、
`1#系统原理图/component-catalog.json` 与 skill catalog、全部符号 SVG、
`1#系统原理图/check_proportions.py`、`1#系统原理图/preflight.py`（不属本票）。

## 2. 规范源迁移要点

- **锚定**：`HERE=脚本目录`、`SKILL=HERE/..`、`LIB=SKILL/assets/component-library`、
  catalog 缺省 `<lib>/component-catalog.json`——与 `check_library.py` 同款；任意 cwd
  调用解析结果一致（测试用任意临时 cwd 验证）。
- **--all / 无位置参数**：全量扫默认库，跳过非组件件（`_*`、`test-*`、`negative-*`、
  `*preview*`、整图类——沿用归档 `sync_snapshot.py` 的排除口径）。当前默认库 23 只
  SVG 中 `_template.svg` 被排除，**扫描数=22**。
- **--lib DIR [--catalog PATH]**：沙箱/测试入口（承接 baseline-44 摸底时"独立复制脚本+
  catalog"的做法，正式化为参数）。

## 3. CLI 行为差异（相对工作区旧副本，需 Codex 知悉）

| 场景 | 旧工作区副本 | 归位后规范源 | 依据 |
|---|---|---|---|
| 无参/`--all` 扫描目录 | 脚本所在工作区目录 | skill 自带库 | 票面"默认库锚定 skill 自带资产" |
| 默认 catalog | 工作区 `component-catalog.json` | `<lib>/component-catalog.json` | 同上 |
| 显式文件不存在 | `io.open` 抛异常（traceback，退出码 1） | 干净 `[ERROR] 文件不存在`，退出码 1 | fail-closed 且可读 |
| 库目录缺失/扫 0 件 | `0 个文件, 0 ERROR` 退出码 0（空转过） | `[ERROR] 库目录不存在/无可检 SVG` 退出码 1 | 票面"缺失/无效目录 fail-closed" |
| catalog 缺失 | 静默 `{}`，C4/C5 对账悄悄失效 | `[ERROR] catalog 不存在` 退出码 1 | 单源锚定的完整性 |
| 未知选项 | 被静默丢弃（可能静默少检文件） | argparse 退出码 2 | fail-closed |
| C1–C13 校核规则 | — | **逐行未动** | 不重写无关规则 |

## 4. 全库门禁基线（预期，未执行）

**命令**：`/usr/bin/python3 .agents/skills/hydraulic-schematic/scripts/check_symbol.py --all`
**预期**：`---- 22 个文件, 2 个有 ERROR, 2 个可正式出图 ----`，**退出码 1**。

佐证：本预期为对现行库与 catalog 0.7-draft 的逐文件代码走查，与
`research/ready-work-20261009/baseline-44/symbol-gate.log`（2026-10-10 用独立复制脚本 +
canonical catalog 实测，exit 1，22 件/2 ERROR/2 可正式出图）**逐项一致**；其间库与
catalog 仅 #45 增 `check_valve_spring` 目录条目（不改任何扫描文件的判定路径）。

### 4.1 两件 ERROR 逐项定位与工程事实归属

**fsov-provisional-stroke.svg**（旧 FSOV 临时件，已被 `firewall-shutoff-valve.svg` v1.8 取代）：

- `C4 目录声明的端口在 SVG 中缺失: main_lower`、`…: main_upper`（catalog
  `firewall_shutoff_valve` 现登记 `main_upper/main_lower`）
- `C5 SVG 存在目录未声明的端口: command / inlet / outlet`（旧件端口命名）
- W：`C11 非正式出图件(provisional)`、`C4 目录 svg_element_id=port-main-upper/-lower
  在 SVG 中不存在`
- **需工程事实**：其注释自载"失电位未知（unknown: FSOV-001.fail_position）、不得用于
  正式出图"。消除此 ERROR 的两条路都要工程/授权输入——按新目录口径重绘（需失电位等
  工程事实），或作为历史资产移出活动库（需授权，本票明确不动）。**不得**靠改 catalog
  去迁就旧件端口。

**quick-disconnect-coupling.svg**（接通位 QD）：

- `C9 width/height 带单位 "mm"`（`27.297mm`——DXF 转换遗留）
- `C3 缺 data-component-type`、`C8 data-symbol-form=None`、`C4 缺 connection-points 组`
- W：`C11 非正式出图件(status=None)`
- **需工程事实**：B-2 挂账（#22，`unknown: quick-disconnect-port-redraw-pending`）——
  断开位侧别语义已工程确认（2026-09-07 右=机侧/左=地面），接通位重绘须以断开位坐标系
  同名同位补齐端口组；这是重绘工作，非本票范围。

其余 18 件全为 WARN（C11 成熟度披露 + C12 未确认项 + 三件 `C3 不在目录中`
WARN：`filter-line-shutoff-stroke.svg`/`pressure-transducer.svg`/断开位 QD 的类型名与
目录条目名不同步——WARN 不计错、不构成工程签认）；2 件 PASS：
`accumulator.svg`、`firewall-shutoff-valve.svg`。**WARN/PASS 明细以 baseline-44 的
symbol-gate.log 为准（第 2–92 行），本票未改任何符号，预期逐字节同判。**

### 4.2 与票面验收的关系

#31 验收第三条"对库内 22 只存量符号全量绿跑一次作基线（退出码 0）"**未达成且本票
不虚构达成**：全量跑如实为退出码 1（上述 2 件）。`test_symbol_gate.py` 把该红基线钉扎
为断言（22/2/2、退出码 1、逐条错误报文）——两件缺陷转正时更新期望即是全量绿基线的
验收动作；期间任何以跳过、白名单、WARN 充当通过的做法都会与测试/文档披露冲突。

## 5. 独立验证命令（Codex 审核端执行；WSL，`/mnt/d/...` 路径）

```bash
cd /mnt/d/file/comac/组件库/.scratch/glm-work-20261012/issue-31
SKILL=.agents/skills/hydraulic-schematic

# (1) 全库门禁基线——预期 exit 1：`22 个文件, 2 个有 ERROR, 2 个可正式出图`
wsl.exe /usr/bin/python3 "$SKILL/scripts/check_symbol.py" --all; echo "exit=$?"

# (2) 便携门禁 CLI 回归（单模块，含红基线钉扎与 fail-closed 用例）
(cd "$SKILL/scripts" && wsl.exe /usr/bin/python3 -m unittest test_symbol_gate -v)

# (3) skill 自包含回归（A–F 全量；F 组新含 test_symbol_gate）——预期 exit 0
wsl.exe /usr/bin/python3 "$SKILL/scripts/selftest.py"; echo "exit=$?"

# (4) 仓库集成回归（含新增 test_symbol_gate_entry 4 用例）——预期 OK
wsl.exe /usr/bin/python3 -m unittest discover -s tests/repository -v

# (5) 兼容入口抽查：指定件（预期 exit 0 + [PASS]）与无参全量（预期 exit 1 + 2 ERROR）
wsl.exe /usr/bin/python3 "1#系统原理图/check_symbol.py" "$SKILL/assets/component-library/accumulator.svg"; echo "exit=$?"
wsl.exe /usr/bin/python3 "1#系统原理图/check_symbol.py"; echo "exit=$?"
```

（如直接在 WSL shell 内，去掉 `wsl.exe ` 前缀即可。）

## 6. TDD 红绿记录（**均未执行**，待 Codex 核验）

- **测试边界（公共接口）**：`check_symbol.py` 真实 CLI（指定 SVG、`--all`、任意 cwd、
  缺失/无效目录 fail-closed）+ 项目兼容入口（真实子进程调用，非 monkeypatch）。
- **红（预判）**：迁移前树上，`test_symbol_gate.py` 因规范源脚本不存在而
  error（subprocess FileNotFoundError）；`test_symbol_gate_entry.py` 的无参全量用例
  期望退出码 1，而旧工作区副本扫本目录 0 个 SVG、空转退出码 0——断言失败。依据：
  旧 `main()` 无参时 `glob(HERE/*.svg)`，`1#系统原理图/` 顶层无 SVG。
- **绿（预判）**：迁移后树上两套测试全过——依据为 §3/§4 的代码走查与 baseline-44
  实测日志；**未经本机运行证实**。若 (2)/(4) 有任何失败，以实际输出为准回改本票，
  不得据本文预期宣称作准。

## 7. 票面验收对照（#31）

| 票面验收项 | 状态 |
|---|---|
| 归位后 SKILL.md Phase 1 与 symbol-library.md 的门禁引用改指 skill 路径，撤掉挂账注记 | **已完成**（本票 §1；docs/规格与需求.md 现状句同步） |
| 工作区副本退役（复制纪律口径更新） | **已完成**（薄兼容入口 + 两处 README 口径；未删除文件） |
| 对库内 22 只存量符号全量绿跑一次作基线（退出码 0） | **未达成/仍开放**：全量如实 exit 1（2 件已知 ERROR，见 §4.1，均需工程事实或授权：fsov 处置、QD 接通位重绘）。红基线已钉扎进 selftest F 组，绿基线留待缺陷转正 |

## 8. 观察到的跨票事项（仅披露，未处理）

1. 本 worktree 内存在 #45 会话（2026-10-12 12:58）未收尾痕迹：
   `component-catalog.json` 已至 **0.7-draft**（新增 `check_valve_spring`，25 类型）、
   `scripts/test_entrypoints.py` 含 `FootprintRegistration45`、`scripts/layout_engine.py`
   同刻改动、`research/glm-tickets-20261012/`（issue-45.md、review-45.md）。本票未触碰
   这些文件；**提交时 Codex 需与 #45 工作分离**。
2. SKILL.md Phase 1 仍写"catalog 0.6-draft 登记 22 个组件类型"，与 0.7-draft/25 类型
   现状不符——属 #45 的文档口径，本票未改。
3. 根 README 徽章仍为 catalog 0.4-draft（历史欠账，非本票范围）。
4. `1#系统原理图/proto/frozen/check_symbol.py` 为冻结证据副本，按冻结纪律保留，不随
   归位清理；`source-snapshot.json`/`runs.json` 中对旧工作区路径的记载是历史实证，
   不改写。
