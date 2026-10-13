# 输入追溯清单

来源使用可解析的 intent 锚点；不推测 YAML 物理行号。母线共享主干不增加逻辑边，跨线桥与折线拆段保留原输入连接。

## 连接(边)映射

| 输入锚点 | intent 连接 | 图上逻辑边 | 逻辑实例数 | SVG 片段 |
| --- | --- | --- | --- | --- |
| `paths[0][0->1]` | `TANK-001.suction_out ↔ EDP-001.suction` | `paths[0][0->1]` | 1 | wire-0-0 |
| `paths[1][0->1]` | `EDP-001.pressure_out ↔ PF-001.inlet` | `paths[1][0->1]` | 1 | wire-1-0 |
| `paths[1][1->2]` | `PF-001.outlet ↔ USR-001` | `paths[1][1->2]` | 1 | wire-2-0 |

## 节点(part)映射

| 输入锚点 | part 声明 | 图上元件 | 符号形式 |
| --- | --- | --- | --- |
| `parts.EDP-001` | `EDP-001: engine_driven_pump` | inst-EDP-001 | `symbols/edp-provisional-stroke.svg` |
| `parts.PF-001` | `PF-001: pressure_filter` | inst-PF-001 | `symbols/filter-line-shutoff-stroke.svg` |
| `parts.TANK-001` | `TANK-001: bootstrap_reservoir` | inst-TANK-001 | `symbols/bootstrap-type-reservoir.svg` |

## 端口 / 母线 / 边界辅助映射

| 输入锚点 | 对象 | SVG 图元 |
| --- | --- | --- |
| `parts.EDP-001.ports.suction` | `EDP-001.suction` | port-EDP-001-suction |
| `parts.EDP-001.ports.pressure_out` | `EDP-001.pressure_out` | port-EDP-001-pressure_out |
| `parts.EDP-001.ports.case_drain` | `EDP-001.case_drain` | port-EDP-001-case_drain |
| `parts.EDP-001.ports.drive_shaft` | `EDP-001.drive_shaft` | port-EDP-001-drive_shaft |
| `parts.PF-001.ports.inlet` | `PF-001.inlet` | port-PF-001-inlet |
| `parts.PF-001.ports.outlet` | `PF-001.outlet` | port-PF-001-outlet |
| `parts.TANK-001.ports.bootstrap_pressure_in` | `TANK-001.bootstrap_pressure_in` | port-TANK-001-bootstrap_pressure_in |
| `parts.TANK-001.ports.suction_out` | `TANK-001.suction_out` | port-TANK-001-suction_out |
| `parts.TANK-001.ports.return_in` | `TANK-001.return_in` | port-TANK-001-return_in |
| `parts.TANK-001.ports.body_sense_tap` | `TANK-001.body_sense_tap` | port-TANK-001-body_sense_tap |
| `extern.USR-001` | `USR-001` | extern-USR-001 |

## 简化说明 / 未知项

以下未知项只披露，不生成连接；逻辑实例数不按 SVG 片段数累加。

- supply-only-regression-return-circuit-not-modeled
- TANK-001.bootstrap_pressure_in-not-modeled
- EDP-001.case_drain-not-modeled
- EDP-001.drive_shaft-not-modeled
