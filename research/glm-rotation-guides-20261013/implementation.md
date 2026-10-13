# glm-rotation-guides-20261013 · 旋转几何缺口实现记录

对应 GitHub sbhorshy/hydraulic-schematics#60 的一个子项：编辑器原型的参考线、
吸附与选中框仍使用未交换的 `nd.w/h`，非方形组件 rot 90/270 时与已修好的
`drawableSize`（drawable 夹取）占位不一致。本记录只覆盖该子项，**不声称 #60
整体完成，也不涉及 #61 定位的签认**。

## 变更文件

- `editor-proto/index.html`（生产，4 处最小修改，全部复用既有 `drawableSize`）
- `tests/repository/test_editor_rotated_guides.py`（新增，Node vm 行为测试）
- 未改动：`tests/repository/test_editor_drag_frontend.py`（原 35 项口径保持原样）、
  命中层 `buildHitLayer`（屏幕空间几何，无失败证据，不动）、服务端与资产。

## 生产修改（editor-proto/index.html）

1. `guideCands`：吸附目标候选改为按 `drawableSize(o)` 的交换后宽高取
   左/中/右、上/中/下（此前直接 `o.x + o.w` 等）。
2. `drawHints`：被拖组件三条候选边/中心改为 `drawableSize(d.nd)`。
3. `onUp` 落点吸附：同式改用 `drawableSize(d.nd)`。
4. `drawSel`：选中框 `width/height` 改为 `drawableSize(nd)`；
   `x/y` 仍为旋转后框左上 `nd.x/nd.y`，不因旋转/镜像二次偏移；
   mirror 不参与尺寸计算（不二次翻转）。

不变式保持：吸附次序仍是 对齐 → 栅格 → drawable 夹取；0/180 不交换；
`drawableDeltaClamp`（本就正确）未动；busy / 权威布局保护（`layoutIndex=null`
禁拖、`holdForUnknownState` 等）未动。

## 测试（TDD：先红后绿）

新增 `tests/repository/test_editor_rotated_guides.py`：从 index.html 提取
`<script>` 在 Node vm 原样执行，只 mock DOM/fetch，断言生产
`startDrag/onMove/onUp/select/drawSel` 的真实行为（提交给 POST /api/delta 的
请求体 + SVG 元素实际属性），无源码字符串断言、无实现复制。五个场景：

| 场景 | 断言要点 |
| --- | --- |
| hints_snap_rot90_dragged | 被拖 200×80 rot90（占位 80×200）：拖动中提示线画在目标左缘 400 / 中线 450；松手提交 dx=220/310（按未交换宽高时无吸附、dx=225/315）；定格线与吸附结果一致 |
| snap_target_rot90 | 吸附目标自身 rot90：候选=400/440/480 与 100/200/300（未交换时 400/500/600、100/140/180 → dx=395/dy=105）；提示线与提交 dx=380/dy=100 |
| drawsel_rects | drawSel 实际 rect 属性：rot0/180 → 200×80，rot90/270 → 80×200，rot90+mirror=x / rot270+mirror=y 不二次翻转；x/y 恒为 100/100 |
| rot0_rot180_no_swap | 0/180 对照：左缘/中心吸附与 drawable 夹取余量（dx≤700/dy≤620）均按未交换 200×80 |
| snap_overrun_clamped | 吸附 930/610 + 栅格 20 推越界后，drawable 夹取按 80×200 兜底回 dx=820/dy=500（右/下缘贴 xmax/ymax） |

### 实测（Windows 主机；node v22.23.1、Python 3.12.2）

```text
# 基线（改实现前，原 35 项）
python -m unittest discover -s tests/repository -p "test_editor_*.py" -v
→ Ran 35 tests ... OK

# 红灯（只跑新文件，实现未改）
python -m unittest tests.repository.test_editor_rotated_guides -v
→ Ran 5 tests, FAILED (failures=3)
  FAIL drawsel_rect / rot90_dragged_snap / rot90_target_candidates
  ok   rot0_rot180_no_swap / snap_overrun_clamped（对照与守卫，符合设计）
（中途一次失败为 harness 快照自身 class/cls 双键瑕疵，属测试侧修正，
 生产行为断言本身已按预期暴露缺口。）

# 补丁后
python -m unittest tests.repository.test_editor_rotated_guides -v
→ Ran 5 tests ... OK

# 全套（控制器口径 discover，含原 35 项 + 新 5 项）
python -m unittest discover -s tests/repository -p "test_editor_*.py" -v
→ Ran 40 tests in 142.514s ... OK
```

执行器通过其默认 WSL 调用环境观察到 Node 不在 PATH；该环境不等同于
Codex 控制端。Codex 后续在固定候选及独立集成版本上实跑 WSL 测试，
均为 40 项通过、无跳过。最终验收以 [控制端记录](acceptance.md) 及其
绑定提交的报告为准，执行器自测不替代独立验证。

## 剩余范围（不在本次声称完成）

- #60 其余子项与整体验收由工程侧独立进行；本补丁只覆盖旋转占位一致性。
- #61（定位）未触碰、未签认。
- 未 push / 未 merge / 未更新 GitHub 状态。
