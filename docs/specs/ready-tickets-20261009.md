# 可直接推进的后续工单 · 2026-10-09

用户授权：检查后续可直接实施的工单并立即开工，沿 implement-spec 执行至本批验收与发布。

本批依据真实正文依赖与现有资料选择 #23、#39、#42、#44、#46、#49、#62。当前前沿为 #23/#39/#44/#62；为避免同一走线接口同时改动，调度上先合 #62，再做 #23。#42 等 #39；#46/#49 等 #44。

代码起点为前批 `f93bd98`，工作区输入捕获基线为 `f3a00952fd5d13fffe85db4740c00fd064d60918`。原工作区保留；移植仅在各自隔离工作树。历史脚本和输出不代表当前通过。

验收边界沿用已批准的公开 preflight、布局器、renderer、validator、driver、SVG/PNG、报告、追溯清单；迁移入口/原型 HTTP 属这些票必要的用户边界。TDD 在上述可观察行为处逐例红绿，不再重复请求已有验收范围的许可。

## 依赖及当前阻塞

- #31：归位工程可做，但全库22件中2 ERROR，不能把active18绿替代整票全量绿；暂保留为缺口，不改变端口语义或静默豁免。
- #45：check_valve_refuel已登记；其余类型缺catalog/端口资产事实，先在#44归因，不能只补尺寸。#47/#48/#50/#51/#52/#53按正文依赖暂不进入本批。
- #24/#36/#40/#61/#63仍有真人签认或工程定义；本轮不代签，不改mirror禁令，不提高maturity。
- #60有局部原型但功能/真人手感尚未到站；只随#23/#62修必要契约/门禁兼容，不声称GUI工程化交付。#41仍受#40阻塞。

各原票验收如下；技术落点可按现有规范源调整，但不能放宽闸门、预算、已声明端口或编造拓扑。

## #23

https://github.com/sbhorshy/hydraulic-schematics/issues/23

> 父票：沉淀批（#14 定案：随沉淀批一并做，不阻塞到站）

## Question

canvas_shift_x=30 双坐标系税：左侧本有隐式边距、真正紧的右侧反被吃 30px（#18 USERR 裁切根源）；guard 的 −SHIFT 兼任右缘裕量守门，直接归零会让母线贴 viewBox 边。正解是契约显式化：layout 自声明 drawable 矩形，guard/validate/renderer 只读不推，右缘裕量拆成显式 EDGE_MARGIN 参数，删 canvas_shift_x。迁移面：validate_sheet 15 处 / layout_engine 6 处 / proto_render 5 处。放 T3 之后动接口，避免冻结侧与 skill 侧漂移。

## 验收

- [ ] layout 契约字段落定（drawable / EDGE_MARGIN），三文件迁移完成，canvas_shift_x 删除
- [ ] 到站链全量回归：fail 0、B 面板不劣于到站水平（B3 ≤1.447、B4/B5 不压线）
- [ ] 右缘裕量由显式参数守门（母线不贴 viewBox 边）

Blocked-by: #22

## #39

https://github.com/sbhorshy/hydraulic-schematics/issues/39

Parent: #33
Blocked by: #35 #38

## Question

按原型定稿把装配语义落规范源：preflight（schema/语义层装配检查：成员已声明、装配端口不悬空）；validate_sheet 新 V 规则（enclosure 完整围合成员、管线越框界只在成员端口、enclosure 与图例/图签栏重叠预算）；selftest 正反例扩充；若模型表达决议影响布局引擎/寻优/驱动器，同步挂钩。规范源改动遵循运行纪律：check_library + selftest 双闸确认。




## #42

https://github.com/sbhorshy/hydraulic-schematics/issues/42

Parent: #33
Blocked by: #39

## Question

装配展开图的间距自适应目前由原型层 `auto_space.py`（CDF 工作区）承载，规则已实证：
符号足迹/端口偏移从符号 SVG 实读（rot 感知，符号换版重跑即对齐主路——v4.2 教训的机制化）；
盒距 = max(B5 下限， 标签净空所需)，净空所需超软上限（80）则后一节点标签翻 above + B5 下限；
边界 extern 按引出段长度挂链两端。布局引擎本身承接不了：R1 硬性要求油箱，
对无母线装配图 `StopIteration`（2026-09-06 实测）。

本票把该规则上移进规范源：引擎增装配单行图分支（或 R15+ 规则），或裁决为
独立轻解析器随渲染链分发；`assemblies` 段感知、selftest 正例（CDF 图）、
knob 表进参数化口径。与 #39 规范源批同期或随后，落裁决。


## #44

https://github.com/sbhorshy/hydraulic-schematics/issues/44

Parent: #43

## Question

工作树压着 2026-09-07 全链交付的大批未提交改动（回油滤旁通全链、QD 侧别 skill 侧、油箱 body_tap、v4.2 压差油滤 80×80 等，skill+项目双侧文件均动），且 selftest D 已知红。地图其余票要在干净基线上开，先摸底再收口：

1. 跑全量摸底：selftest 全量 + skill-chain-e2e + 项目侧整链（preflight→引擎→渲染→校核），产出**红/绿面清单**；
2. 红项逐条归因（QD 侧别兑现红 / v4.2 未重跑 / 其他），归入本图对应票（[FOOTPRINT 新类型登记与引擎补齐]、[selftest D 红修复与 skill-chain-e2e 冻结态重钉] 等）；
3. 已到站部分收口提交为基线 commit（红项文件是否随批提交，按归因结论定并披露——不带病通过，也不静默截断）。

收口后其余票的开票基线 = 本票产出的基线 commit。


## #46

https://github.com/sbhorshy/hydraulic-schematics/issues/46

Parent: #43
Blocked by: #44

## Question

蓄压器移挂与气侧链串接是 2026-09-07 用户口径，SysML 侧已改、intent 侧未落（老账），三层不同步：

1. **液端移挂**：`1#系统.intent.yaml` 中 ACC-001 液端现仍挂 `@MANIFOLD`（行 78，注释已声称移出）——按口径改挂自增压支路 PRV-002 下游，与 `1#系统.sysml` 行 294 对齐；
2. **气侧链串接**：现两条 taps（ACV@ACC 气口、PG@ACV 充气口）改 ACC→PG→ACV 串接口径（SysML 行 329-330 已是串接），写法票内定（taps 链式 vs paths 支路，对齐 preflight E-TAP 口径）；
3. **出图随行**：气侧链布局挪到 PRV-002 附近（引擎 R10 气侧堆叠或布局覆写），preflight/几何校核/回读三层过。

验收：intent↔SysML↔图三层对账一致，差异逐条披露。


## #49

https://github.com/sbhorshy/hydraulic-schematics/issues/49

Parent: #43
Blocked by: #44

## Question

油箱已统一用 skill 单源 `bootstrap-type-reservoir.svg`（2026-09-07 指令），旧 `reservoir-bootstrap-annotated.svg` 退役出库：

1. 全仓清点引用（catalog symbol.asset、FOOTPRINT、rendering-rules/symbol-library 文档、项目侧 symbols/ 拷贝、历史夹具）；
2. 退役（删文件+引用清理），check_library 与 selftest 过；
3. 符号重绘 campaign 早期符号待办 -1（其余 3 只不在本图范围，见地图 Out of scope）。


## #62

https://github.com/sbhorshy/hydraulic-schematics/issues/62

Parent: #54

## Question

**需求（用户 2026-09-29 签认）：旋转换装位后，出线不应干涉自身本体——管线适配装位，而非要求人转回。**

现状（[最小原型：拖拽写回闭环](https://github.com/sbhorshy/hydraulic-schematics/issues/60) v0.5 实证）：走线为规则式解（§13 R1），端口出桩沿锚方向后直奔目标，**不避让自身本体墨迹**。非对称复合符号换装位时折返段穿越本体：RF-001（viewBox 100×194，原生 outlet 右缘锚朝右）从签认 rot=180 转到 0 后，outlet 折返段 `1264.1,1137→1282.1,1137→940,1137` 横穿本体 → V2 fail。90°/270° 因端口转竖直、走廊不同而不撞（但读图错位）。

要解的问题：`render.py` wire() 对「出桩后直连目标会穿越自身本体」的连接做**规则式避让**，候选：

- **母线接入点伸缩**：目标是母线时，接入 y 沿母线延伸避让本体（@RET「底端延伸接 RF-001」先例已在）；窄版首选；
- 绕行 detour：出桩后下/上绕本体再回接——通用但折返多，B2/B3 预算压力。

硬约束：保持规则式（不做寻路求解器，§13 R1 不重开）；B1–B7 预算口径不劣化；V2 语义不变（避让后 V2 应自然转绿，不是放行）。

验收：

- [ ] RF-001 转 rot=0 后全链出图无 V2（旋转即净，或一键收敛），四旋转角扫描全过；
- [ ] selftest 金样重钉全绿；规范 6.3.3/走线规则文档随版；
- [ ] 编辑器侧（[最小原型：拖拽写回闭环](https://github.com/sbhorshy/hydraulic-schematics/issues/60)）旋转提示相应放宽（不再警告「转回原方位」）。

关联：雾区「保手调局部重推」是走廊级大版图，本票只做「自身本体避让」窄版；引擎重推弃种子的老路不复用。
