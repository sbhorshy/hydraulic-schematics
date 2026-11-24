# Issue 110：未入样缺陷的可渲染样本与去向回填

一次性研究分支 `research/issue110-unseen-defects`，**不合并、不开 PR**。回答 [#110](https://github.com/sbhorshy/hydraulic-schematics/issues/110) 的 Question：#102 原型 21 张图只出现 V4/V5/V6/V9/V10/V12/V13/V14/V19，未入样的 V2/V3/V7/V8/V11/V15/V16/V17/V20 能否补出可渲染注入样本，并按 [#102 决议三](https://github.com/sbhorshy/hydraulic-schematics/issues/102#issuecomment-7108887937) 的四门槛归一档。

门槛原文：「**目标对象 / 锚点稳定、偏差可度量、范围能被 `sheet_diff._scope` 接受、成败由官方链判定**。满足门槛才谈结构化；『local』的含义是结构化，不等于已证明能修。」去向定义沿用决议三：local / route / agent（只有文字）/ disclose / recheck。决议三同时把样本边界说清：「未入样的缺陷一律交 agent；21 张只出现 9 个检查号、22 种缺陷」（同一决议评论也把「21 张改过的图」更正为 20 张改动图 + 1 张基线）。[#98](https://github.com/sbhorshy/hydraulic-schematics/issues/98) Notes 要求同一输入、种子、环境；本实验全部从当前 1# 输入派生，基线 intent 逐字节复制，官方脚本不改。[#99 决议](https://github.com/sbhorshy/hydraulic-schematics/issues/99#issuecomment-7092488334) 的「V2 穿本体：没有可渲染的注入样本，待补样本再归类」由下文的手工 SVG 样本补上。

## 1. 未入样检查号：代码位置与精确触发

位置均相对仓库根目录，行号对应本分支 HEAD（391200a）。

| ID | 规范源位置 | 触发条件（代码口径） |
|---|---|---|
| V2 | `.agents/skills/hydraulic-schematic/scripts/endpoint_checks.py:106-142`（`check_bodies`，由 `validate_sheet.py:183` 调用） | 对最终 SVG 每条管段的**全部**线段与变换后符号足迹求交；`segment_body_length > 0.1` 且不属于「真实首/末端口沿自身外向锚向离开本体」时，`fail kind=body_crossing`，报 `penetration`。仅允许真实首末端和该端口锚向豁免，路线中段不豁免。 |
| V3 | `endpoint_checks.py:31-88`（`check_endpoints`） | 声明端口与最终 SVG 管段端点最近距离 `> 0.1`（`endpoint_gap`）；或首末段不满足端口旋转后锚向（`forward<=0.1` 或 `sideways>0.1`，`anchor_direction`）；或同管线严格共线反向折返（`foldback`）。 |
| V7 | `layout_clearance.py:423-485`（`frame_checks`，`validate_sheet.py:562`） | 浏览器实测 `rect.lg`/`rect.tb` 与彼此、元件实际足迹重叠；管线压框 `>8` 单位；或桥弧整段被框覆盖 `>8`。重叠判据 `not (a[2]<b[0] or …)`，故相接也算。 |
| V8 | `layout_clearance.py:428-441,471-477`（`frame_checks`）；`assembly_checks.py:146-158`（装配模式，`validate_sheet.py:829`） | 声明 `groups` 的可见 `rect.grp[data-group]` 圈进非成员足迹；或声明装配的框与成员足迹/字形内距 `<14`、与非成员足迹相交、框缺失/无有效描画。 |
| V11 | `validate_sheet.py:491-513` | 最终根 SVG 管段同时满足 `abs(dx)>1e-7` 与 `abs(dy)>1e-7` 即 `fail kind=nonorthogonal_pipe`；0.1 接管舍入容差不适用于斜线。 |
| V15 | `stroke_checks.py:51-119,254,328`（`check_widths`，`validate_sheet.py:313`） | 浏览器实测线宽：管网 `ln-pressure=3T`、其余 `1T`；本体/内部机构 `1.5T`；外引线须落在 `[3T,1T,1.5T]`。有效宽度偏差 `>0.02`，虚线管网、零描画、`non-scaling-stroke` 均触发。 |
| V16 | `stroke_checks.py:171-287`（`check_widths`） | 每条声明端口的外引线须从端口到本体边界连续可见、与相接管网同宽（容差 0.02），并有独立本体接触；`body_tap` 需真实描边/填充命中。红圈或 connection-point 不算引线；缺测进 `unchecked`。 |
| V17 | `validate_sheet.py:317-475`；语义推导 `topology_reconciliation.py:510-554` | ①吸油网络到达不兼容非透明压力/回油/泄油端（`suction_semantics`）；②声明吸油链被画成非 `ln-suction` 或宽度 ≠ `1T`；③缺 `.ln-suction` 样式/出现 `stroke-dasharray`；④每组斜杠必须 5 根、高 `2S`、角 60°、组内距 `1.25S`、不得压组件/文字/框；⑤图例 `S` 必须与 `layout.style.suction_marker_S` 一致。渲染器在 `render_l0_sheet.py:204-205` 对语义错误直接抛 `ValueError`（**出图前**）。 |
| V20 | `assembly_checks.py:92-211`（`validate_sheet.py:829`）；框生成 `assembly_checks.py:44-74`；输入门禁 `preflight.py:144-184` | 声明 `assemblies` 后：装配框宽须 `1.5T` 长虚线 `8 5`、无填充；成员足迹/字形内距 ≥14；框不得圈非成员或压图例/图签；标签左对齐于框上；任何跨框管段必须恰为该成员声明外向端口的直接引线，否则 `assembly_boundary_crossing`。 |

V2 的出图前硬路由门禁在 `render_l0_sheet.py:522-556`：所有候选正交走线经 `route_obstacles.collisions` 判定失败时 `raise RO.failure(anchor, rejected)`，写 `routing-error.json` 并清掉旧 SVG（`render_l0_sheet.py:1454` 附近）。因此「让路由器主动画出穿本体线」不可达，只能走手工 SVG 路线。

## 2. 注入样本与官方链结果

全部由 `research/issue110/make_unseen_cases.py` 生成（复用 `prototype/issue-102-readback-triage:research/issue102/make_cases.py` 的 render→rasterize→validate 链）。`base` 为 fail 0 / warn 6；每案例只改一处。下表的「证明」列指向 `research/issue110/evidence/<case>/`：`summary.json`（严格注入前后值、三条命令的 rc/stdout、`fails`/`warns`、`coverage`、`topology_coverage`、产物指纹）与 `validation-report-compact.json`（报告 checks/coverage/拓扑标识）。

| case | 如何产生 | 官方链出图 | 官方 fail / warn | 注入前后几何 | 证明 |
|---|---|---|---|---|---|
| `v2-through-body` | 基线先渲染，再手工改 SVG：`v2-through-body` | render 0 / raster 0 / validate 1（出图成功；注入发生在渲染后） | fail 9：V2×4、V3、V14×2、V19；warn 8。V2 原文如「管线穿越 PRV-001 本体 69.90 单位」 | `wire-3-0`（`paths[2][0->1]`）`[(690,330),(910,330)]` → `[(690,330),(690,320),(1400,320),(1400,330),(910,330)]`；横段穿 PF-001 99.80、PRV-001 69.90 单位 | `evidence/v2-through-body/summary.json` |
| `v3-endpoint-gap` | 基线渲染后改 SVG 末点：`v3-endpoint-gap` | 0/0/1 | fail 5：V3、V2、V11、V10、V19；warn 6。V3「端点距离 2.8284271247461903」 | `wire-0-0` 末点 `(610,646)` → `(612,648)`，EMP-001.suction 端口不动 | `evidence/v3-endpoint-gap/summary.json` |
| `v7-legend-title` | 输入侧 layout：`legend.y` 1020 → 1060 | 0/0/1 | fail 2：V7、V12；warn 8。V7「图例 [380,1060,920,1350] ↔ 图签 [40,1330,1640,1386]」 | 图例下移 40，与图签重叠 20 单位；V12 为伴生文字净空 -0.6 | `evidence/v7-legend-title/summary.json` |
| `v8-foreign-member` | 输入侧 intent 增 `groups.ZONE{members:[ACC-001,PG-001]}` | 0/0/1 | fail 2：V8、V19（V19 见 caveat）；warn 8 | 自动生成框 `[706,812,943,960]` 圈进非成员 ACV-001 足迹 `(830,939,964,996)` | `evidence/v8-foreign-member/summary.json` |
| `v11-diagonal` | 基线渲染后改 SVG 中间拐点：`v11-diagonal` | 0/0/1 | fail 6：V11×2、V3×2、V4、V19；warn 5。V11 `axis deltas=(293,7)` | `wire-0-0` 拐点 `(590,686)` → `(601,693)`，两端端口不动 | `evidence/v11-diagonal/summary.json` |
| `v15-single-width` | 基线渲染后给 `wire-3-0` 加 `style="stroke-width:4.8"` | 0/0/1 | fail 1：仅 V15「effective width 4.800 != 3.600」；warn 6 | 单管 `paths[2][0->1]` 线宽 CSS 3.60 → inline 4.80；坐标不变 | `evidence/v15-single-width/summary.json` |
| `v16-single-lead` | 基线渲染后给 `USER-001__port-stub-left` 加 `style="stroke-width:1.8"` | 0/0/1 | fail 1：仅 V16「lead 1.800 != network 3.600」；warn 6 | 单端口 `USER-001.pressure_in` 外引线 3.60 → 1.80（1.8 本身是允许的 symbol 宽，故 V15 不误报）；坐标不变 | `evidence/v16-single-lead/summary.json` |
| `v17-missing-slash` | 基线渲染后删掉首个 `suc-mark-group` 的一根斜杠 | 0/0/1 | fail 1：仅 V17「吸油斜杠组 0 含 4 根，标准要求完整 5 根」；warn 6 | 组 0：5 根 → 4 根；删 `(320,632.8)->(336,642.1)`，其余几何不变 | `evidence/v17-missing-slash/summary.json` |
| `v20-assembly-crossing` | 输入侧 intent 增 `assemblies.PUMPZONE{members:[EDP-001,EMP-001]}` | 0/0/1 | fail 5：V20×3、V8、V19（V19 caveat）；warn 6 | 自动生成装配框后，3 条非成员外向管段越框；V20 只接受成员声明端口的直接引出段 | `evidence/v20-assembly-crossing/summary.json` |

`base` 的完整链是 `python3 <skill>/scripts/render_l0_sheet.py <workdir>` → `rasterize_sheet.py <svg> -o <png>` → `validate_sheet.py <workdir>`；所有案例 `svg_written=true`、拓扑 `coverage_status=pass`、`geometry.issues=[]`。差分范围用官方 `sheet_diff._scope` 直接校验，九个 scope 全部 accepted：`research/issue110/scopes/*.json` 与 `evidence/scope-check.json`。注意 accepted 只证明范围标识合法；未声称 `sheet_diff compare` 已通过（差异报告仍受 `_model` 的 PNG/浏览器/字体一致性和 `delivery.ready` 约束）。

## 3. 四门槛逐项归一档

下表每格按「①目标/锚点稳定 ②偏差可度量 ③`_scope` 接受 ④官方链判定」顺序回答；证据均为本节对应 case 目录。

| ID | ① | ② | ③ | ④ | 档 | 证据 |
|---|---|---|---|---|---|---|
| V2 | 是：障碍件 PF-001/PRV-001 足迹与 `paths[2][0->1]` 锚点均稳定 | 是：穿体 99.80 / 69.90 单位（`penetration`） | 是：nodes `PF-001,PRV-001` + edge `paths[2][0->1]`（accepted） | 是：validate fail V2 四条 | **structured·local** | `scopes/v2-through-body.json`、`evidence/v2-through-body/summary.json` |
| V3 | 是：`EMP-001.suction` 与 `paths[0][0->1]` 稳定 | 是：端点距离 2.828 > 0.1 | 是：node `EMP-001` + edge `paths[0][0->1]`（accepted） | 是：validate fail V3 | **structured·route**（端点与输入不符属走线/规则层；不冒充可自动执行的 local） | `scopes/v3-endpoint-gap.json` |
| V7 | 是：`rect.lg`/`rect.tb` 根坐标框稳定 | 是：相交 20 单位、框重叠 | 是：`global:true` + 具体 note（accepted；框不是 scope 节点） | 是：validate fail V7 | **structured·local**（伴生 V12 文字净空仍按 agent） | `scopes/v7-legend-title.json` |
| V8 | 是：`groups.ZONE` 框 + 非成员 ACV-001 足迹稳定 | 是：框与足迹相交坐标准确给出 | 是：nodes `ACC-001,PG-001,ACV-001`（accepted；`groups.ZONE` 不是 scope 节点，故以成员表达） | 是：validate fail V8 | **structured·local** | `scopes/v8-foreign-member.json` |
| V11 | 是：`wire-0-0`/`paths[0][0->1]` 稳定 | 是：`axis deltas=(293,7)`、`(11,47)` vs ε=1e-7 | 是：node `TANK-001,EMP-001` + edge（accepted） | 是：validate fail V11 | **structured·route**（正交约束是规则层） | `scopes/v11-diagonal.json` |
| V15 | 是：单管 `wire-3-0` + `paths[2][0->1]` 稳定 | 是：4.800 vs 3.600，差 1.2 | 是：node `EDP-001` + edge（accepted） | 是：validate fail V15（唯一 fail） | **structured·local** | `scopes/v15-single-width.json` |
| V16 | 是：`USER-001.pressure_in` 与引线 id 稳定 | 是：1.800 vs 3.600，差 1.8 | 是：node `USER-001` + edge `paths[6][0->1]`（accepted） | 是：validate fail V16（唯一 fail） | **structured·route**（引线宽度随管网规则，action=inspect） | `scopes/v16-single-lead.json` |
| V17 | 是：吸油链锚点 `paths[0][0->1]` 等、斜杠组序 0 稳定 | 是：4 根 vs 5 根 | 是：三条吸油边 + `TANK-001`（accepted） | 是：validate fail V17（唯一 fail） | **structured·local**（可渲染的是标记几何；语义变异见例外，仍交 agent） | `scopes/v17-missing-slash.json` |
| V20 | 是：`assemblies.PUMPZONE`、成员与其端口、越框点稳定 | 是：3 处越框点/归属由 V20 报告给出 | 是：nodes `EDP-001,EMP-001` + 邻接边（accepted；装配锚点不是 scope 节点） | 是：validate fail V20×3 | **structured·route**（规则层越框交接，非自动修法） | `scopes/v20-assembly-crossing.json` |

无一项落入 disclose 或 recheck：九个样本都由官方链给出确定 fail，不是提示或证据不全。V4/V14 的 `not_checked` 伴生项才属于 recheck，但那是已入样的 ID，不在本票回填范围。

## 4. 例外与 caveat

1. **V2 只能手工改 SVG**：九组单点布局探针（`research/issue110/probe_route_gate.py`，证据 `evidence/route-gate-probe.json`）中 ACC-001 `y+170`、PRV-002 `y-60`、PG-001 `x+60`、ACV-001 `y+60`、EDP-001 `x+60`、EMP-001 `y-60`、CDF-001 `x+60` 全在渲染前被硬门禁挡住：`rc=1`、`routing-error.json.status=blocked`、无 SVG；如 PG-001 探针的障碍就是 PG-001 本体，clearance 12。故 #99 的「 intent/布局侧没有可渲染样本」仍成立；本票补的是**渲染后手工编辑最终 SVG** 的样本（官方 rasterize+validate 仍判定），不是可经官方渲染器复现的输入注入。手工样本同时带出 V3 锚向、V14 缺桥、V19 预算失败，并非单一缺陷样本。
2. **V17 语义变异仍不可渲染**：`probe_v17_semantics.py` 向 intent 追加 `['TANK-001.suction_out','USER-001.pressure_in']` 后，`render_l0_sheet.py:204-205` 抛 `ValueError: Suction network reaches an incompatible nontransparent terminal …`，`rc=1`、无 SVG；证据 `evidence/v17-semantics-blocked.json`。该变异按要求**留 agent**，理由：出图前语义门禁阻断，不能由官方链给出几何判定。可渲染的 V17 样本仅覆盖标记几何（缺一根斜杠）。
3. **intent 侧样本带 V19 伴生失败**：V8/V20 需改 intent；`bridge_policy` 按 intent 字节 SHA-256 绑定（`bridge_allowance.py:38-48,83-119`），重 dump 后旧登记失效，fail-closed 报 V19。这是注入副作用，不是目标缺陷；各 case 的 `edits` 日志与 scope note 中已记录。若未来要为实验开登记，应按新 intent 单独登记，不得改生产表。
4. **样本单一性**：全部基于 1# 一份输入、同一 Chrome/字体/脚本环境（产物指纹见各 summary）；失败计数与原型 #102 的 21 图不可直接比较（本分支 HEAD 已含 #97 合并后的检查项）。
5. **可提出的后续工单（仅建议，本票不建）**：①让 V2 的手工 SVG 注入成为受控实验入口，或提供不触发硬门禁的合法目标位；②为 intent 侧实验提供按字节绑定的临时跳线登记流程；③给 V17 吸油语义阻断补一个可渲染诊断路径或明确披露口径。

## 5. 精确复现

分支基于 391200a；在独立 worktree 中（不要改 main / 当前 checkout）：

```bash
cd /root/orca/workspaces/组件库/v2-v7-v8
git worktree add -b research/issue110-unseen-defects .scratch/issue110/wt HEAD
cd .scratch/issue110/wt

python3 research/issue110/make_unseen_cases.py          # 10 张：base + 9 个注入案例
python3 research/issue110/probe_route_gate.py           # V2 出图前硬门禁探针
python3 research/issue110/probe_v17_semantics.py        # V17 语义变异阻断
python3 research/issue110/check_scopes.py               # sheet_diff._scope 九个范围
```

单案复现示例：`python3 research/issue110/make_unseen_cases.py v15-single-width`。生成图只在被忽略的 `.artifacts/issue110/`；文本证据在 `research/issue110/evidence/`。查看官方报告原文可用各 `.artifacts/issue110/cases/<case>/validation-report.json`（不入分支）。所有 official 命令在本分支脚本中使用 `sys.executable` 和 skill 规范源 `.agents/skills/hydraulic-schematic/scripts/`，cwd 固定 `/tmp`，与原型 make_cases.py 一致。

## 6. 回填 #102 去向表的一句话结论

V2 local、V3 route、V7 local、V8 local、V11 route、V15 local、V16 route、V17 local（语义变异 agent）、V20 route；九个 ID 均可产出受官方链判定的样本并过四门槛，V2 的手工 SVG 例外与 V17 语义门禁例外按第 4 节保留。
