# B 组只读诊断

起始 HEAD：`c215799dd606ca2c4c55663c1c6c79eb5d22e95a`。

执行命令（skill/scripts 中）：`python -m unittest -v test_display_widths test_paint_evidence test_text_display test_proofreading_evidence test_sheet_diff`。完整输出 `diagnose-full-b.log`；68 tests / 511.971 s / exit 1 / 2 FAIL / 0 ERROR。未修改源码，也未运行全量 selftest。

1. `test_display_widths.DisplayWidths.test_actual_png_width_ratios_at_normal_and_double_scale`：第200行断言 `lead/pipe` 实测1.2215686274509805，超出1±0.12。第182–189行把SVG viewport及Chrome窗口硬设1680×1390，但当前 `l0-current/1#系统.layout.json` 已迁移为1710×1390，根viewBox随之为1710；按SVG默认等比适配会缩放墨迹并在纵向留白，而第198行仍按根用户单位固定坐标采样。因此这个失败不能证明生产线宽异常。建议从本次SVG viewBox取得viewport/window尺寸，保证1×/2×采样仍是根坐标一一映射；保留原比例阈值和实际PNG验证。

2. `test_text_display.TextDisplay.test_v17_and_v12_share_root_coordinates_for_suction_marks`：第196行未找到预期V17“文字 H”碰撞。第187行给sheet额外加translate(200,0)，第190行读取的是已迁移后的mark根坐标；第194行却仍把probe放在`x+230-4`，多计已经移除的旧30单位平移。应从最终累积变换求mark根位置，或本用例使用实际额外平移200；保留第一次不碰撞、第二次V17/V12都定位同一碰撞的双重断言。

`test_paint_evidence`、`test_proofreading_evidence`、`test_sheet_diff`全部通过，其他显示线宽/文字专项均通过。本轮没有出现生产实现异常证据；两项归因为源码与当前夹具之间可定位的坐标假设失配，但修复后仍须原断言实跑通过才可关闭，不应只更新期望数字或弱化阈值。

补充：`test_sheet_diff.py:121` 尚有旧绝对坐标注入，但本轮用例通过；它改变到了无效连线仍会触发unexpected_topology，因此不把该处额外计作本轮失败。可由统一实现者后续让该负例从实际端口取点，确保仍精确测试“目标范围内换口”。
