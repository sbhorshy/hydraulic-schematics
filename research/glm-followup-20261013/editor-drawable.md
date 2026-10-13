# #60 原型缺口 · 前端 drawable 夹取（GLM 实现范围记录）

日期：2026-10-13 · 实现：GLM（ZCode bridge，仅 Read/Edit/Write）· 审核：Codex · 测试：由控制端执行

## 范围（仅此三文件，未动历史资产/基线/图纸）

- `editor-proto/index.html`：拖拽夹取依据从 canvas 猜测切换为服务端 drawable 契约。
- `tests/repository/test_editor_drag_frontend.py`：新增 Node 行为测试。
- 本文件。

依赖前提（已集成，未改动）：服务端 #60 server-bounds 已完成，`GET /api/layout` 披露
`drawable_bounds=[xmin,ymin,xmax,ymax]`；服务端 `apply_delta` 以
`layout_contract.drawable_bounds` + 旋转占位宽高交换（`ew,eh = rot%180 ? (h,w) : (w,h)`）
做权威夹取，坏契约/放不下时写盘前整事务拒绝。

## 实现要点（index.html）

- `parseDrawableBounds`：只认四个有限数且 `xmin<xmax`、`ymin<ymax`；不满足返回 null。
  GET /api/layout 只核验 drawable 矩形/margin 声明本身，不核验节点占位；占位放不下由
  服务端 `apply_delta` 写盘前另行拒绝。前端只核对传输面最小形态。
- `refreshLayout`：发起即与 `layoutIndex` 一同置空 `drawableBounds`；读到合法契约才恢复。
  契约无效 ≠ 布局刷新失败：`nodes` 有效时 `refreshLayout` 仍返回 true（busy 正常放行，
  镜像/旋转不受影响），仅拖拽被禁；读取失败仍返回 false 走既有停用分支。全程不猜
  canvas 宽高做夹取依据（原 `clampDelta` 的 `(W.width||1e6)` 兜底已删除）。
- `startDrag`：新增 `!drawableBounds` 守卫，无有效契约不接受拖拽；busy/权威节点守卫原样保留。
- `drawableDeltaClamp`：位移域夹取 `dx∈[xmin−x, xmax−ew−x]`、`dy∈[ymin−y, ymax−eh−y]`，
  旋转占位经 `drawableSize` 交换；拖动中 `clampDelta` 与松手提交共用同一公式（与服务端
  `apply_delta` 同式，右缘 margin 已在契约内不二次扣）。
- `onUp` 提交顺序：对齐吸附 → 栅格取整 → 位移取整 0.1 → **再夹取一次** → 提交。
  边界非栅格倍数（或对齐/取整把右/下缘推出 drawable）时边界优先于栅格，不提交越界位移。
- 未动：busy/镜像/旋转保护、postDelta 闭环与未知态处理、参考线/选中框绘制。

## 测试（控制端尚未执行，本记录不声称通过）

`tests/repository/test_editor_drag_frontend.py`：从 index.html 提取 `<script>` 在 Node vm
上下文原样执行（最小 DOM stub + fetch stub：`/api/sheet` 挂起、`/api/delta` 只记录请求体
并回 stage=delta），驱动生产 `startDrag/onMove/onUp/refreshLayout`，断言实际提交的
dx/dy、拖动中夹取值与预览 transform、各契约形态下 refreshLayout 后的拖拽状态。
node 不在 PATH 时整类 skip。4 场景：

1. `nonzero_start` 非零起点：提交位移相对节点坐标（防把指针绝对值当位移）；
2. `grid_bottom_right` 非整栅格右/下边：drawable 1010×810 + 栅格 20，吸附推至
   960/780（右/下缘越界）必须在 onUp 再夹回 850/670，拖动中同为 850/670；
3. `nonsquare_rot` 非方形 90/270：200×80 旋转占位 80×200，右/下余量按交换后宽高
   （820/500 而非 700/620），含反向夹到左/上缘与 rot 270 对照；
4. `unknown_bounds` 未知边界禁写：缺 `drawable_bounds`/非有限元素/边缘倒置/读取失败
   四态均 `drawableBounds=null` 且拖拽不启动、不产生提交；合法契约对照组放行并夹取提交。

控制端待执行命令：`python3 -m unittest discover -s tests/repository -p "test_editor_*.py" -v`

## 已知边界 / 未做

- 测试由控制端执行后才算数；本记录与实现说明不构成"已通过"。
- 真实 Chrome 拖动手感回归由 root 负责（未做）。
- 对齐参考线/吸附候选/选中框仍按未交换的 w/h 绘制（既有行为，不在本轮口径）。
- 提交位移取整 0.1 后再夹取：整数/定点坐标下精确；极端非定点边界值会失去栅格对齐
  （边界优先，不越界），与服务端权威夹取一致。
- 契约无效但节点有效时镜像/旋转仍可用（服务端仍是权威兜底）；这是有意取舍而非遗漏。
- 未关闭 #60/#61，未代签手感。

## 修订记录

- 2026-10-13（控制端首轮后）：修复 harness 语法错误——`/api/sheet` 挂起分支
  `new Promise(() {})` 缺 `=>`，致四个前端场景在 Node 加载期即 SyntaxError
  （控制端日志：35 测试中服务端侧 drag_bounds/mirror/rotation 全过，仅此前端
  harness 失败）；断言未削弱/删除/跳过。同轮修正注释口径：GET /api/layout 只
  核验 drawable 矩形/margin 声明，节点占位可放下由 apply_delta 写盘前另行拒绝。
  前端场景逻辑在本轮修复前从未实际执行，通过与否待控制端重跑。
