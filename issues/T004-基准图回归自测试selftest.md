# 基准图回归自测试 selftest v1

> **[5 号 Issue 已为 canonical](https://github.com/sbhorshy/hydraulic-schematics/issues/5)** —— 本文件是迁移存档快照，后续更新只在 GitHub 上进行。


<!-- labels: wayfinder:task · AFK -->
<!-- child of MAP-hydraulic-skill-uplift -->

## Question

`scripts/selftest.py` 最小可用集如何裁剪，使"改动符号/catalog/模板后一条命令知道出图能力是否被打破"？

需决断的三点（均已有本次人工验证结论打底，可 fast-path）：

1. **SysML 链路基准图比对语义**：字节级会被 CRLF 干扰（实证：本次内容一致仅换行符不同）——
   建议归一化换行后再比对；基准图放 `assets/fixtures/` 还是首次运行生成？
2. **覆盖面**：v1 只锁 SysML 链路（L0 链路规范源当前断裂，见地图 Out of scope）+ sync_snapshot 闸门自测
   （回退拦截、--force 旁路、prune 计数）够不够作首版？
3. **失败出口**：与渲染器同一退出码约定（0 过 / 1 断），供未来 CI 或 pre-sync 钩子直接调用。

Blocked-by: 无。后续扩展（构图度量进回归、L0 基准图）留在地图迷雾区。

## Resolution

（待认领后填写）

## Assets

-
