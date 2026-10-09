# 绘图后校对增强 · 实施验收

已完成[十票规格](schematic-proofreading.md)。集成分支：`integration/schematic-proofreading-20261009`；最终经验证的运行时提交：`a903a04b8a86530c505f7de6108eeb46f09c4fa3`。审查基线 `e9b6be85` 是本批开始前的工作区快照，保留了当时既有修改。

| 工单 | 完成行为 | 主要公共 CLI 回归 |
|---|---|---|
| [#64](https://github.com/sbhorshy/hydraulic-schematics/issues/64) | 变换后的端口接入、方向和接管避体 | `test_port_geometry` |
| [#65](https://github.com/sbhorshy/hydraulic-schematics/issues/65) | 可见几何逐边对账及规范追溯清单 | `test_topology_reconciliation` |
| [#66](https://github.com/sbhorshy/hydraulic-schematics/issues/66) | 真实汇流点、交叉和连续跨线桥 | `test_junction_semantics` |
| [#67](https://github.com/sbhorshy/hydraulic-schematics/issues/67) | taps、悬空清单、实际红圈与图签一致 | `test_dangling_ports` |
| [#68](https://github.com/sbhorshy/hydraulic-schematics/issues/68) | 液压/气侧引线与本体的实际描画、线宽和连续性 | `test_display_widths / test_paint_evidence` |
| [#69](https://github.com/sbhorshy/hydraulic-schematics/issues/69) | 实际字形范围、压字、裁切、净空和缺失标签 | `test_text_display` |
| [#70](https://github.com/sbhorshy/hydraulic-schematics/issues/70) | 实际足迹、避让走廊和真实折点预算 | `test_layout_clearance` |
| [#71](https://github.com/sbhorshy/hydraulic-schematics/issues/71) | 覆盖清单、所用资产/工具指纹和版本绑定签认 | `test_proofreading_evidence` |
| [#72](https://github.com/sbhorshy/hydraulic-schematics/issues/72) | 批量局部图、对象覆盖与逐项审阅门禁 | `test_readback_review` |
| [#73](https://github.com/sbhorshy/hydraulic-schematics/issues/73) | 声明范围内语义/像素差分和不可比说明 | `test_sheet_diff` |

## 最终验证

完整自测 **6/6 通过，包含 226 个 unittest 用例**；专项部分 809.065 秒，总耗时 810.524 秒。源码提交未在测试期间变化。[完整日志](schematic-proofreading-evidence/final-selftest.log)。

[双轴评审及整改](schematic-proofreading-review.md)分别保留 Standards 和 Spec 的发现、规范依据与修复结果。公共绘图、独立校核、驱动器、实际 Chrome/Pillow 图像及故意损坏负例共同验证；测试通过不自动写入感知签认。

- 最小样例：驱动器与独立校核结果一致，自动检查零失败。根代理实际查看完整 PNG 和全部 8 张局部图后，显式确认 17 项及整图；重跑 `--keep` 保留同版结论，驱动器退出 **0**、`delivery.ready=true`。[图像](schematic-proofreading-evidence/accepted-small.png)。
- 当前 23 部件旧种子：两入口结果一致，保留 **13 条失败**，涉及 V2/V3/V10/V13/V14/V19。根代理实际查看整图和 9 张重点局部图；11 项已确认、4 项存疑、119 项未查看，整图记录为存疑，仍阻断交付。没有为绿色结果修改输入或放宽预算。
- 差分实际示例：局部引线修复定位 42 个变化像素、0 个越域像素，拓扑不变；误改其他节点出现 370 个越域像素；目标范围内错口即使 0 个越域像素也因语义变化失败。[前后图与差分](schematic-proofreading-evidence/diff-example.png)。

[结构化验收摘要](schematic-proofreading-evidence/acceptance.json)区分初次出图状态与实际回读后的状态。最小样例原有概念级净空提示及 draft/provisional/unknown 披露保留。

## 单次运行实测

使用已提供布局、独立临时工作目录、本机 Chrome、1:1 的 1680×1390 PNG；未启动布局寻优。以下是本环境单次实测，不是跨设备的保证值。

| 测项 | 最小样例 | 当前 23 部件样例 |
|---|---:|---:|
| 完整驱动链（含校核和局部图） | 4.144s | 7.232s |
| 局部对象 / 裁图数量 | 17 / 8 | 134 / 62 |
| 批量局部图耗时 | 0.445s | 1.207s |

局部图从同一最终 PNG 一次解码后裁取，不逐端口启动转换器。显示测量按 SVG、字体和工具版本复用；候选寻优不启动浏览器。真实局部差分约 2.36–2.58 秒，固定两次范围描画；显式整体字体差分约 1.04 秒、不额外栅格化原图。

完整开发回归包含大量真实浏览器正负例，耗时与上表的单次出图分别记录。

## 使用

```bash
python .agents/skills/hydraulic-schematic/scripts/validate_driver.py \
  --intent <intent.yaml> --layout-seed <layout.json> --workdir <独立目录>
```

工作目录新增 `readback.html`、`readback-manifest.json` 和局部图。先核实版本，再实际查看整图与局部图；逐项使用 `readback_review.py record-item <目录> <对象ID...> --decision confirmed|questioned --reviewer <姓名> --note <实际检查内容>`。整图使用 `proofreading_evidence.py record-review` 记录，随后重新校核；未查看或存疑项保留阻断。

```bash
python .agents/skills/hydraulic-schematic/scripts/sheet_diff.py freeze <旧目录> --output <冻结目录>
python .agents/skills/hydraulic-schematic/scripts/sheet_diff.py compare <冻结目录> <新目录> \
  --scope <变更范围.json> --output <新差分目录>
```

范围示例：`{"nodes":["PF-001"],"include_adjacent_edges":true,"note":"修复该滤器外接引线"}`。节点/邻边的视觉范围不会自动授权逻辑换口。驱动器也可用成对的 `--compare-against` / `--change-scope` 生成差分。

## 边界与状态

- `converged` 保留已执行检查零失败的兼容含义；完整交付以 `delivery.ready` 为准。缺必检证据或签认时驱动器退出 4；独立校核保留原字段。
- 当前旧种子的压力/泄油接触、气侧走线和零交叉预算缺陷作为诊断回归保留；它不因工具实现完成而变成合格图纸。
- 不支持的描画、单位、变换或缺少测量能力按对象明确未校核；无法对齐的画布不作“无差异”结论。局部字体范围重绘要求可复核的字体环境。
- 端口输入语义、0.1 单位舍入容差及既有 B1/B4/B5/B6/B7 阈值保留。正确跨线桥仍计入零交叉预算。
- 原工作区同步以起始内容哈希为保护，只应用本批差异；历史自定义出图目录与其他既有修改不纳入本批同步。
