# #63 编辑器镜像操作面（editor-proto）· 实现说明

日期：2026-10-12。状态：代码与测试已写完，**待 Codex 实跑验收**（本文所引自检结果以实跑日志为准）。

## 定位

原型定位不变（#58 手调即真源、#59 编辑器无导出、校验权威=validate_sheet 零重实现）。
本轮只把 #63 已落地的镜像许可链（mirror_policy 三道闸 → render place →
sheet_geometry 姿态校验）接入编辑器的操作面：**编辑器不新增裁决，只复用单源**。

## 服务端（editor-proto/server.py）

- `apply_delta` 增加绝对 `mirror` 请求：`'none'/'x'/'y'`；**缺省（键不在）=保持当前姿态**。
  0/True/数字/其他字符串在请求层（HTTP 400，stage=request）与 `apply_delta` 入口
  （stage=delta）双重拒绝——不把 0/true 默认成 none。
- 授权：`_mirror_permission_issues` 复用 `endpoint_usage.mirror_contract`（与 render
  place / validate_sheet contract 阶段同一许可单源），按 workdir 实际 catalog（本地
  覆盖优先，回落 skill 规范源库）、实际符号资产字节、intent 实例类型逐实例过三道闸。
  时机在 `write_layout_atomic` **之前**：未登记 / 登记 hash 过期 / 非法轴 →
  整次事务拒绝（stage=permission），`layout_version`/`revision_log`/文件字节不变；
  同请求携带的移动一并拒绝，绝不部分落盘。已有合法镜像的实例仅移动（键缺省）也重过
  许可——资产/端口契约漂移会令旧登记失效。
- `mirror:'none'` = 移除镜像（允许）；mirror-only 轴变更**不算零位移**；重申同轴且无
  移动/旋转仍是零位移。
- 日志：revision_log 条目记节点 ID、坐标、`mirror before→after`（none 也显式记）、
  `rot before→after`；本路径只写 `x/y/rot/mirror` 四键，端口 id/角色永不在此触碰。

## UI（editor-proto/index.html）

- 选中框新增「左右镜像 (x) / 上下镜像 (y) / 还原 (none)」按钮与当前轴显示。
- `M` 键循环 none→x→y→none（文案注明）；焦点在文本输入/下拉框或按着
  Alt/Ctrl/Meta 时不触发。`R`/Esc 行为不变；端口连线提示文案保持。
- 服务器拒绝时 banner 如实反馈（"镜像被服务器拒绝（未落盘）"），画布保持上一帧，
  不暗改本地成功态。无导出端点、无绕过闸门的路径（#59 口径未动）。

## 回归（tests/repository/test_editor_mirror.py）

- 快速用例直调真实 `apply_delta`：授权/写入/日志全真；仅渲染-校核子进程链替换为
  记账执行器（setUpClass 真实渲染一次提供链产物快照）。
  覆盖：授权落盘+日志 before/after；未登记组件带移动整事务拒绝且文件字节不变；
  登记过期（资产字节变更）拒绝；非法值拒绝；`none` 移除；镜像+移动+旋转同请求保留；
  已带镜像实例移动重验；同轴重申=零位移；HTTP 层 0/true/'z' 拒绝。
- 全链正例（真实执行器 + HTTP，`EditorMirrorFullChain`）由 Codex 实跑。
- 不宣称 #60/#61 人机产品签认完成：`passed` 仍要求感知签认，编辑器用例一律断言
  `passed=False`（无签认冒充）。

## 同轮修复（非编辑器）

1. **sheet_geometry 姿态容差（审核反例）**：`_pose_matches` 旧预算把
   `|a*x|+|e|` 的可抵消大数当容差基数——viewBox 原点 1e9 时容差 ~2e5，
   整符号平移 100px 仍判匹配。现改为按**变换后控制点自身的图上幅度**给预算
   （`POSE_TOLERANCE` 底 + `POSE_RELATIVE_TOLERANCE`×点幅度，封顶
   `POSE_TOLERANCE_CAP=1.0` SVG 单位）：%g 舍入余量保留（1/3 缩放正例），
   无法在该容差内表达的精度直接拒绝而不是接受错位。之前"大 viewBox 倍缩放"
   修复解决了小 k 系数盲区，本轮修掉源坐标抵消盲区；其余姿态检查未放宽。
   公开 `load_geometry` 反例（test_mirror_render.py）：viewBox=(1e9,0,80,80)、
   node=(100,200,80,80,mirror x)、actual e+100 → 必须拒绝。
2. **validate_sheet B1 披露**：`covered` 已要求 V4 与 V14 覆盖均 pass
   （junction_semantics 的 unsupported marker 只记 V4 not_checked，单查 V14 会
   放过带未知 marker 的跳线）；`verified_bridges` 现在**仅在该条件成立时**计入
   逐点核实数，否则整组按 0 披露——虚线桥/假接点存在时不再"一边 fail 一边报
   verified=1"。`measured` 始终是真实交叉数。
   真实负例（test_bridge_allowance.py，参照 ../probe-bridge-gate.py 复现）：
   linearGradient 填充的 circle.jn marker（V4 not_checked）与 stroke-dasharray
   虚线桥（V14 dashed_bridge）都要求 B1 fail 且 verified_bridges=0、measured 不减。
3. **候选布局落盘**（1#系统.layout.json 2.3）：EMP-001 mirror=y、CDF-001
   (730,430) rot270、@CASE x=700、EMP 标签 right / CDF below+drop20，
   bridge_policy 维持已登记 id。来源：../tasks/layout-single-bridge.txt 的
   Codex 已验证候选（仅旧 B1=0 失败，../layout-probe-summary.json）。skill 示例
   seed 与生产不同构（EMP x=530、含 CDF-002），按"仅同构同步"口径未动。
4. **许可 1 下第二处桥拒绝**（tests/repository/test_bridge_single_allowance.py）：
   真实 1# 原料临时副本，原候选 B1 raw1/pass/allowance1/verified1 且 fail0；
   仅 PF-001.y 254→354 时 raw2/fail/verified2 且 V4/V14 无失败、唯一失败族 V19。
   不 mock registry/validator。
5. **two_crossings 夹具**：吸油线去程 y=400、回程 y=450，消除自身共线重叠
   （旧路线 V10/V13/missing_junction 先炸，测不到 B1 本身）；保留
   "V4/V14 无失败"断言。

## Codex 实跑清单（本轮验收）

```
python -m unittest -v tests.repository.test_editor_mirror tests.repository.test_bridge_single_allowance
python -m unittest -v tests.repository.test_editor_rotation        # 既有回归不破
python .agents/skills/hydraulic-schematic/scripts/test_mirror_render.py
python .agents/skills/hydraulic-schematic/scripts/test_bridge_allowance.py
python .agents/skills/hydraulic-schematic/scripts/selftest.py      # F 组全套
python .agents/skills/hydraulic-schematic/scripts/check_library.py
# 1# 候选完整验收（冻结来源前）：
python .agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py "1#系统原理图"
python .agents/skills/hydraulic-schematic/scripts/validate_sheet.py "1#系统原理图"
```
