# CDF 活动输入与版本边界

`case_drain_filter.intent.yaml` 与 `case_drain_filter.layout.json` 为活动输入。#23 只把布局转换为根 SVG 坐标，保持实际内容位置和既有 w/h；不暗改旧种子的装配间距/尺寸或工程含义。当前规范源 R17 可从真实 SVG 端口、足迹和实际字形重新生成布局；它不沿用参照中的旧尺寸。普通单向阀仍是工作默认，不代表弹簧/流向已签认。

```bash
python .agents/skills/hydraulic-schematic/scripts/validate_driver.py \
  --intent '1#系统原理图/CDF-001装配图/case_drain_filter.intent.yaml' \
  --ref '1#系统原理图/CDF-001装配图/case_drain_filter.layout.json' \
  --workdir /tmp/cdf-current-run
```

如需保持旧布局，改用 `--layout-seed` 明确传入本目录布局，实际校核红项须披露，不能拿旧 PNG 代替新证据。本目录 render_l0_sheet.py、validate_sheet.py、auto_space.py 已在文件 I/O 前 fail-closed，避免以旧双坐标算法读写迁移后的输入。

已有 SVG/PNG/topology/report 是 f3a00952 捕获的历史实证，未重写、未升格。历史脚本实现在该提交中保留；复现实验应导出整套历史输入、脚本与资产到独立目录，不混用活动 seed。
