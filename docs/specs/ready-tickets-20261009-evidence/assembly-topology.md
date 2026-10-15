# 输入追溯清单

来源使用可解析的 intent 锚点；不推测 YAML 物理行号。母线共享主干不增加逻辑边，跨线桥与折线拆段保留原输入连接。

## 连接(边)映射

| 输入锚点 | intent 连接 | 图上逻辑边 | 逻辑实例数 | SVG 片段 |
| --- | --- | --- | --- | --- |
| `paths[0][0->1]` | `CASE-IN ↔ CDF-001-BODY.inlet` | `paths[0][0->1]` | 1 | wire-0-0 |
| `paths[0][1->2]` | `CDF-001-BODY.outlet ↔ CDF-001-CV.inlet` | `paths[0][1->2]` | 1 | wire-1-0 |
| `paths[0][2->3]` | `CDF-001-CV.outlet ↔ CASE-OUT` | `paths[0][2->3]` | 1 | wire-2-0 |

## 节点(part)映射

| 输入锚点 | part 声明 | 图上元件 | 符号形式 |
| --- | --- | --- | --- |
| `parts.CDF-001-BODY` | `CDF-001-BODY: filter_line_shutoff_dp_case_drain` | inst-CDF-001-BODY | `/mnt/d/file/comac/组件库/.scratch/ready-work/final-evidence/assembly/filter-line-shutoff-dp.svg` |
| `parts.CDF-001-CV` | `CDF-001-CV: check_valve` | inst-CDF-001-CV | `/mnt/d/file/comac/组件库/.scratch/ready-work/final-evidence/assembly/check-valve.svg` |

## 端口 / 母线 / 边界辅助映射

| 输入锚点 | 对象 | SVG 图元 |
| --- | --- | --- |
| `parts.CDF-001-BODY.ports.inlet` | `CDF-001-BODY.inlet` | port-CDF-001-BODY-inlet |
| `parts.CDF-001-BODY.ports.outlet` | `CDF-001-BODY.outlet` | port-CDF-001-BODY-outlet |
| `parts.CDF-001-CV.ports.inlet` | `CDF-001-CV.inlet` | port-CDF-001-CV-inlet |
| `parts.CDF-001-CV.ports.outlet` | `CDF-001-CV.outlet` | port-CDF-001-CV-outlet |
| `extern.CASE-IN` | `CASE-IN` | extern-CASE-IN |
| `extern.CASE-OUT` | `CASE-OUT` | extern-CASE-OUT |
| `assemblies.CDF-001` | `CDF-001` | assembly-CDF-001, assembly-label-CDF-001 |

## 简化说明 / 未知项

以下未知项只披露，不生成连接；逻辑实例数不按 SVG 片段数累加。

- CDF-001-CV.flow-direction-tbd
- CDF-001-CV.port-role-catalog-default
- CDF-001-BODY.dp-indicator-or-sensor
- CDF-001.filtration-rating
