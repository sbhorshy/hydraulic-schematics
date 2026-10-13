# CDF-001 壳体回油滤组件 装配展开图 · 拓扑追溯清单

- **唯一输入定义**: `1#系统原理图/1#系统.sysml`（SysML v2，仅拓扑）
- **图品**: `case_drain_filter装配图.svg`（L0 链路: `case_drain_filter.intent.yaml` + `case_drain_filter.layout.json`）
- **校核**: preflight ERROR 0；`validate_sheet.py` fail 0 / warn 2（披露见文末）；构图预算 B1–B6 全过；Inkscape 1:1 回读 PNG 感知验收
- **成熟度**: concept，不可用于工程放行

## 装配语义（SysML 行 118–129）

```
case_drain_filter (CDF-001)
  inlet ──> body (filter_line_shutoff_dp 基型) ──> cv (check_valve) ──> outlet
```

本体内部结构（行 75–88：滤芯 + 压差传感器，内部连接 4 条）由受控符号
`filter-line-shutoff-dp.svg` 内联表达，不拆节点——与 SysML 头注行 14–19
"油滤装配件与 filter-line-shutoff-dp.svg 一一对应；目录三类型各自内联本体结构"一致。

## 连接（边）映射

| # | 图上边 | intent token 对 | SysML 依据（行号） | 说明 |
|---|---|---|---|---|
| E1 | `CASE-IN` → `CDF-001-BODY.inlet` | paths[0][0..1] | 126 `connect 'inlet' to 'body'.'inlet'`；边界语义 235–236（@CASE 母线，双泵合流） | 左边界三角→本体进口 |
| E2 | `CDF-001-BODY.outlet` → `CDF-001-CV.inlet` | paths[0][1..2] | 127 `connect 'body'.'outlet' to 'cv'.'inlet'` | 本体出口→单向阀 |
| E3 | `CDF-001-CV.outlet` → `CASE-OUT` | paths[0][2..3] | 128 `connect 'cv'.'outlet' to 'outlet'`；边界语义 239（直回油箱） | 单向阀出口→右边界三角 |

## 节点（part）映射

| 图上实例 | 类型（catalog 0.4-draft） | SysML 依据 | 实例数 | 符号 |
|---|---|---|---|---|
| `CDF-001-BODY` | `filter_line_shutoff_dp_case_drain` | SysML 行 123 `part 'body' : 'filter_line_shutoff_dp'` + 行 104–116 壳体回油滤本体（role=case_drain） | 1 | `filter-line-shutoff-dp.svg`（目录 status=draft，图签栏已披露） |
| `CDF-001-CV` | `check_valve` | SysML 行 124 `part 'cv' : 'check_valve'` | 1 | `check-valve.svg`（rot=180 使进口朝左；`allow_mirror=false`，镜像会反转通流方向） |

本体内部（符号内联，不落节点）：`element` (filter_element) + `sensor` (dp_sensor)，
对应 SysML 行 80–87 四条内部 connect；符号上半压差指示圆叉的两根竖管落到菱形
（滤芯）上/下游斜边，即传感器两感压口跨接滤芯进出油侧。

## 本体符号内部图形 ↔ SysML 内部连接对照

| SysML connect（行号） | 符号图形 |
|---|---|
| `connect 'inlet' to 'element'.'inlet'`（84） | 进口引线 (0,84)→菱形左顶点 |
| `connect 'element'.'outlet' to 'outlet'`（85） | 菱形右顶点→出口引线 (80,84) |
| `connect 'sensor'.'sense_a' to 'element'.'inlet'`（86） | 左竖管落到菱形上游斜边 (x=30.5) |
| `connect 'sensor'.'sense_b' to 'element'.'outlet'`（87） | 右竖管落到菱形下游斜边 (x=49.5) |

## 概念级简化与口径披露

0. **装配围框（#38 原型新增）**：intent `assemblies` 段声明 CDF-001（label + members，
   对应 SysML 行 118 `part def 'case_drain_filter'` 整体）；围框 rect
   `data-assembly="CDF-001"`（286,172 348×219，1.5T 长虚线）由渲染器按成员画出足迹
   （节点盒∪标签）+内距 14 推导；越框点在 BODY.inlet / CV.outlet 两成员端口。
   条文见 rendering-rules「装配围框（Assembly Enclosure）」节（#37 定档）。
1. **单向阀端口 role 为目录缺省 `pressure`**：装配语境实为壳体回油介质。线宽两级制
   （高压 3.0T / 低压 1.0T，全部实线）下 E3 段线型类名推导为 `return`，与 case_drain
   边同为 1.0T 实线，视觉无差异；catalog 约束"case_drain 端口不得与 role=pressure
   的网络连通"指不得接入压力供压网络，本装配内部串联不构成该违反。已同时登记
   intent `unknown: CDF-001-CV.port-role-catalog-default`。
2. **边界按 `return` 建模**：L0 契约 extern 枚举（inlet/outlet/return）无 case_drain；
   两边界三角为绘图抽象（SysML 头注行 7：母线是绘图抽象，非部件）。
3. **本体类型取 role=case_drain 变体**：SysML 装配引用基型 `filter_line_shutoff_dp`
   （行 123，SysIDE 文法限制不复用特化写法）；目录变体 `filter_line_shutoff_dp_case_drain`
   结构相同、端口 role=case_drain，与 `1#系统.intent.yaml` 对 CDF-001 的口径一致。
4. **管线无流向箭头**：V18 闸门明令禁止渲染器属管线箭头（组件符号内部运动箭头除外），
   与已交付的 `1#系统原理图.svg` 口径一致；`rendering-rules.md` 视觉常量段"流体边带
   marker-end 箭头"为旧口径残留，与 V18 冲突，以闸门为准。
5. **流向待确认**：单向阀"允许流向油箱、防倒灌"为判断，SysML 行 72 已注明待工程确认，
   登记为 `unknown: CDF-001-CV.flow-direction-tbd`；符号朝向（左进右出，阀座楔尖朝上游）
   表达意图方向，不构成放行依据。

## 校核披露（warn 2，与 1# 基线同类）

- **V4** 三通点 (329,708) 不在任何母线 x 上——此为**图例栏内"三通"教学演示点**，
  非图面三通；本图无母线。
- **V9** 符号 2 个非 annotated（`data-symbol-status` 属性缺失）——库级已知缺口，
  `1#系统原理图` 基线同样存在（22 个同报）；本体符号目录 status=draft 已在图签栏披露。
- **校验器副本差异**（相对 skill 规范源，均已在副本内注明）：
  ① 输入/输出文件名常量改为 `case_drain_filter.*`；② 库路径常量改为仓库根相对；
  ③ V17 门控改为"仅当图上确有 `ln-suction` 折线时要求五斜杠组"（装配图无吸油网络，
  原判定对无吸油图误报）。规范源侧是否采纳 ③ 建议挂账。

## 复现命令

```bash
cd "1#系统原理图/CDF-001装配图"
python auto_space.py .               # 自适应间距解析(符号足迹/标签净空实读推导,写回 layout)
python render_l0_sheet.py .          # preflight 门禁 + 渲染 -> case_drain_filter装配图.svg
"/d/Program Files/Inkscape/bin/inkscape" -o sheet-readback.png -w 1000 "case_drain_filter装配图.svg"
python validate_sheet.py .           # -> validation-report.json（fail 0 / warn 2）
```

间距不手调：改 intent/标签/符号后重跑 `auto_space.py` 即得新坐标（规则与 knob
见脚本头注；引擎级承接挂[布局引擎承接装配单行图](https://github.com/sbhorshy/hydraulic-schematics/issues/42)）。
