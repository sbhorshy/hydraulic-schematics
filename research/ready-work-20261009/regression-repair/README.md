# 最终全量失败后的测试坐标迁移

首轮全量在 `c215799` 失败：A–E 通过；F 为 260 tests / 1374.902 秒，17 FAIL、5 ERROR。仓库独立集成 6 项通过。该轮失败原件保留在 `.scratch/ready-work/final-evidence/`，哈希列于 [evidence.json](evidence.json)，没有改记为通过。

只读分组诊断与修复后的定向运行对齐了全部失败数量：

| 模块 | 原 FAIL / ERROR | 原因与修复 |
|---|---|---|
| junction_semantics | 7 / 5 | 管线、桥弧、圆点、extern 和选择器仍用旧局部 x；把注入恢复到原来的最终根坐标 |
| readback_review | 2 / 0 | 折返、6 px 防火墙尾线仍注入旧 x；恢复根坐标，保留同一位置与裁图墨迹断言 |
| port_geometry | 5 / 0 | 2 px 断口变成 28 px、旧线未接真实端口、嵌套变换重复加 30；只改注入，保留端口身份/位置/距离断言 |
| topology_reconciliation | 1 / 0 | 拆线/桥片段使用旧端点导致 PF 实际未接；同时迁移该模块其他通过但错位的注入，恢复原反例语义 |
| display_widths | 1 / 0 | current viewBox 已为 1710×1390，测试却强制 1680×1390；改从真实 viewBox 推导 SVG viewport 与 Chrome 窗口，保持 1×/2× 及全部墨迹比值门槛 |
| text_display | 1 / 0 | 额外变换仅 translate(200)，注入仍额外计算旧隐含 30；保持原文字/吸油标记碰撞断言 |

另修正 `sheet_diff` 一条原本仍通过的换口反例：原点串未真正接到当前目标 outlet，现在恢复原根坐标端点，既有“预期范围内也不能换拓扑”的断言不变。

七个受改测试模块的全部断言表达式与 `c215799` 做 AST 对比完全一致，计数逐文件记录在 evidence.json。端口、本体穿越、六像素尾线、实际 PNG、网络身份等原验收条件未放宽；没有修改 renderer/validator、拓扑、端口资产或任何预算。

定向结果：junction + 两项回读 22 项通过（146.615 秒）；port/topology + display/text 32 项通过（146.682 秒）；sheet_diff 换口单例通过（9.664 秒）。完整日志持久保存在 `.scratch/ready-work/` 的对应文件；**这不是新的完整 selftest 通过证明**，最终冻结后仍须重跑完整 skill 和独立仓库测试。

`selftest.py` 新增可选 `HYDRAULIC_SELFTEST_UNIT_LOG`：调用者提供一个可写、尚不存在的日志路径时，F 组以 `-v` 逐用例运行，stdout/stderr 直接流式写入该文件；控制台仍显示简短摘要。已有文件不会被覆盖，超时/中断前已写输出保留。1800 秒进程保护和功能预算不变。不指定时保留原行为。此日志模式待下一轮正式全量实际使用；本轮没有为验证日志而额外启动完整 selftest。

#23 的到站零交叉约束阻断仍按 [arrival-23](../arrival-23/README.md) 保持开放；测试迁移通过不等于该真实图纸验收通过。
