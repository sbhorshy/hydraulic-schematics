# 技能链端到端验收（GitHub #21，2026-09-01）

`render_l0_sheet.py + skill catalog 0.4-draft` 对 1# intent 端到端出图不崩、
`validate_sheet` **fail 0**、气侧支路不穿本体。本目录是验收工作目录与证据存档。

## 运行口径（#21 起的技能链工作目录约定）

```bash
# 渲染（就地运行 skill 脚本，传工作目录；无需复制脚本，无需 symbols/ 拷贝——
# 符号经 catalog 锚定到 skill 自带库，单源化）
python .agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py 1#系统原理图/skill-chain-e2e
# 回读（1:1，canvas 1680px）
inkscape <workdir>/1#系统原理图.svg --export-type=png --export-filename=<workdir>/sheet-readback.png -w 1680
# 几何校核
python .agents/skills/hydraulic-schematic/scripts/validate_sheet.py 1#系统原理图/skill-chain-e2e
```

## 输入

- `1#系统.intent.yaml` —— 自 frozen 沙箱原样拷入（22 部件 + 2 taps 气侧支路）。
- `1#系统.layout.json` —— 自 frozen 拷入，唯一改动：TANK-001 符号引用
  `symbols/reservoir-bootstrap-annotated.svg` → `symbols/bootstrap-type-reservoir.svg`
  （skill 库的描边重绘件；frozen 布局保持原样不动）。

## 三处欠账的修通位置

1. **catalog 回登记**：skill catalog 0.1-draft → **0.4-draft**，22 类型齐
   （8 缺失类型自 frozen 迁入；14 存量 symbol 块重写为库内真值；端口锚向按
   符号端口组同步——pressure_switch 的 anchor down→left 即注释点名的漂移）。
2. **TANK-001.suction_out 崩溃**：`bootstrap-type-reservoir.svg` 的方言组
   `port-anchors` 转正为标准 `connection-points`（旧元数据 x=172 与图面引线
   x=155 不一致，统一到图面几何）。
3. **wire_taps 修复移植**：frozen render.py 的锚向出桩 + 障碍全量不豁免实现
   移植进 skill `render_l0_sheet.py`，连同 sense 线型/CSS/图例行、taps 挂账
   （dangling 豁免）、结构自检 taps 口径、main 接线（path_polys/tap_polys）。

## 验收结果

| 项 | 结果 |
|---|---|
| 端到端出图 | `wrote 1#系统原理图.svg`，nets=37 / segments=48 / junctions=20，结构自检放行 |
| validate_sheet | **passed（fail 0, warn 6）**——warn 与现状基线同口径（V13×2 汇同端口、V4 图例示例点、V5 悬空 9、V9 符号成熟度 22、V19/B3 2.373 存量超限） |
| B1–B7 面板 | B1=0、B2 全图 21/单线 3、B4=8.0、B5=40.0、B6 达标；B3 2.373 为手工布局存量（引擎布局已消除至 1.447，见 driver-runs/arrival） |
| 气侧不穿本体 | 几何断言：两条 sense 支路逐段采样，不穿任何节点盒 ✓；`gas-side-branch-zoom.png` 局部回读目视复核 ✓（修复前 V2 穿本体证据见 #18/frozen 历史） |
| check_library | 默认（硬档）通过：22 SVG / 21 端口组 / 白名单 1（quick-disconnect-coupling 连接位变体，挂账 #22） |
| selftest | PASS 3/3（金样回归 / check_library 闸门沙箱拦截 / preflight 负正例） |

## 附带修复（本票内发现）

- 温度/压力开关与传感器 4 只符号：注释声明 elec_out 引线而图面漏画、端口组
  缺 `elec_out`——补齐引线与端口点（"与温度变送器族对齐时一并补"到期兑现）。
- `bootstrap-type-reservoir.svg` 文件内 `separator-lower` id 重复（渲染器按实例
  改名后整图撞 V1）——改名 left/right；check_library L2 增补**全文件 id 重复**检查防复发。
- `selftest.py` 仍引用 #20 已退役的 `sync_snapshot`——B–E 四项改写为
  check_library 闸门沙箱测试（v2）。
