# 输入追溯清单

来源使用可解析的 intent 锚点；不推测 YAML 物理行号。母线共享主干不增加逻辑边，跨线桥与折线拆段保留原输入连接。

## 连接(边)映射

| 输入锚点 | intent 连接 | 图上逻辑边 | 逻辑实例数 | SVG 片段 |
| --- | --- | --- | --- | --- |
| `paths[0][0->1]` | `TANK-001.suction_out ↔ EMP-001.suction` | `paths[0][0->1]` | 1 | wire-0-0 |
| `paths[1][0->1]` | `TANK-001.suction_out ↔ FSOV-001.main_upper` | `paths[1][0->1]` | 1 | wire-1-0 |
| `paths[1][1->2]` | `FSOV-001.main_lower ↔ EDP-001.suction` | `paths[1][1->2]` | 1 | wire-2-0 |
| `paths[2][0->1]` | `EDP-001.pressure_out ↔ @PRESS` | `paths[2][0->1]` | 1 | wire-3-0 |
| `paths[3][0->1]` | `EMP-001.pressure_out ↔ @PRESS` | `paths[3][0->1]` | 1 | wire-4-0 |
| `paths[4][0->1]` | `@PRESS ↔ PF-001.inlet` | `paths[4][0->1]` | 1 | wire-5-0, wire-5-1, bridge-0 |
| `paths[4][1->2]` | `PF-001.outlet ↔ @MANIFOLD` | `paths[4][1->2]` | 1 | wire-6-0 |
| `paths[5][0->1]` | `@MANIFOLD ↔ PRV-001.inlet` | `paths[5][0->1]` | 1 | wire-7-0 |
| `paths[5][1->2]` | `PRV-001.outlet ↔ @USR` | `paths[5][1->2]` | 1 | wire-8-0 |
| `paths[6][0->1]` | `@USR ↔ USER-001.pressure_in` | `paths[6][0->1]` | 1 | wire-9-0 |
| `paths[7][0->1]` | `@USR ↔ USER-002.pressure_in` | `paths[7][0->1]` | 1 | wire-10-0 |
| `paths[8][0->1]` | `@USR ↔ USER-003.pressure_in` | `paths[8][0->1]` | 1 | wire-11-0 |
| `paths[9][0->1]` | `@USR ↔ USER-004.pressure_in` | `paths[9][0->1]` | 1 | wire-12-0 |
| `paths[10][0->1]` | `@USR ↔ USER-005.pressure_in` | `paths[10][0->1]` | 1 | wire-13-0 |
| `paths[11][0->1]` | `@USR ↔ USER-006.pressure_in` | `paths[11][0->1]` | 1 | wire-14-0 |
| `paths[12][0->1]` | `@USR ↔ USER-007.pressure_in` | `paths[12][0->1]` | 1 | wire-15-0 |
| `paths[13][0->1]` | `@USR ↔ USER-008.pressure_in` | `paths[13][0->1]` | 1 | wire-16-0 |
| `paths[14][0->1]` | `PRV-002.outlet ↔ ACC-001.hydraulic_port` | `paths[14][0->1]` | 1 | wire-17-0 |
| `paths[15][0->1]` | `@PRESS ↔ PRV-002.inlet` | `paths[15][0->1]` | 1 | wire-18-0 |
| `paths[15][1->2]` | `PRV-002.outlet ↔ TANK-001.bootstrap_pressure_in` | `paths[15][1->2]` | 1 | wire-19-0 |
| `paths[16][0->1]` | `@MANIFOLD ↔ QDP-001.aircraft_side` | `paths[16][0->1]` | 1 | wire-20-0 |
| `paths[17][0->1]` | `USER-001.return_out ↔ @USERR` | `paths[17][0->1]` | 1 | wire-21-0 |
| `paths[18][0->1]` | `USER-002.return_out ↔ @USERR` | `paths[18][0->1]` | 1 | wire-22-0 |
| `paths[19][0->1]` | `USER-003.return_out ↔ @USERR` | `paths[19][0->1]` | 1 | wire-23-0 |
| `paths[20][0->1]` | `USER-004.return_out ↔ @USERR` | `paths[20][0->1]` | 1 | wire-24-0 |
| `paths[21][0->1]` | `USER-005.return_out ↔ @USERR` | `paths[21][0->1]` | 1 | wire-25-0 |
| `paths[22][0->1]` | `USER-006.return_out ↔ @USERR` | `paths[22][0->1]` | 1 | wire-26-0 |
| `paths[23][0->1]` | `USER-007.return_out ↔ @USERR` | `paths[23][0->1]` | 1 | wire-27-0 |
| `paths[24][0->1]` | `USER-008.return_out ↔ @USERR` | `paths[24][0->1]` | 1 | wire-28-0 |
| `paths[25][0->1]` | `@USERR ↔ RF-001.inlet` | `paths[25][0->1]` | 1 | wire-29-0 |
| `paths[25][1->2]` | `RF-001.outlet ↔ @RET` | `paths[25][1->2]` | 1 | wire-30-0 |
| `paths[26][0->1]` | `CV-002.outlet ↔ @USERR` | `paths[26][0->1]` | 1 | wire-31-0 |
| `paths[27][0->1]` | `@RET ↔ TANK-001.return_in` | `paths[27][0->1]` | 1 | wire-32-0 |
| `paths[28][0->1]` | `@RET ↔ QDR-001.aircraft_side` | `paths[28][0->1]` | 1 | wire-33-0 |
| `paths[29][0->1]` | `EDP-001.case_drain ↔ @CASE` | `paths[29][0->1]` | 1 | wire-34-0 |
| `paths[30][0->1]` | `EMP-001.case_drain ↔ @CASE` | `paths[30][0->1]` | 1 | wire-35-0 |
| `paths[31][0->1]` | `@CASE ↔ CDF-001.inlet` | `paths[31][0->1]` | 1 | wire-36-0 |
| `paths[31][1->2]` | `CDF-001.outlet ↔ @RET` | `paths[31][1->2]` | 1 | wire-37-0 |
| `taps[0]` | `PG-001.pressure_sense ↔ ACC-001.gas_port` | `taps[0]` | 1 | wire-44-0 |
| `taps[1]` | `ACV-001.accumulator_gas ↔ PG-001.pressure_sense` | `taps[1]` | 1 | wire-45-0 |

## 节点(part)映射

| 输入锚点 | part 声明 | 图上元件 | 符号形式 |
| --- | --- | --- | --- |
| `parts.TANK-001` | `TANK-001: bootstrap_reservoir` | inst-TANK-001 | `symbols/seed-516f64ccba53407af46ce7ba537fbbc60a243bb3d9e03c636126cc331dd9b444/bootstrap-type-reservoir.svg` |
| `parts.FSOV-001` | `FSOV-001: firewall_shutoff_valve` | inst-FSOV-001 | `symbols/seed-4ee96f91a5fe87354577f40813577f50abe2d7e62d5620e4475760f692f3cb5f/firewall-shutoff-valve.svg` |
| `parts.EDP-001` | `EDP-001: engine_driven_pump` | inst-EDP-001 | `symbols/seed-134414e3efa5adfc73e55ed39c30bae9433c1e7767b502e9b789860f5512c07b/edp-provisional-stroke.svg` |
| `parts.EMP-001` | `EMP-001: electric_motor_driven_pump` | inst-EMP-001 | `symbols/seed-e12e5fb728ce2763ab1071c80639d155460e858b70b5ed674c1e7d8e61670e34/emp-provisional-stroke.svg` |
| `parts.PF-001` | `PF-001: filter_line_shutoff_dp` | inst-PF-001 | `symbols/seed-ff35d7db0b17f99fcd509b32f103aee158ea0eb2d5099d883492f22a6da0f9ea/filter-line-shutoff-dp.svg` |
| `parts.CDF-001` | `CDF-001: filter_line_shutoff_dp_case_drain` | inst-CDF-001 | `symbols/seed-ff35d7db0b17f99fcd509b32f103aee158ea0eb2d5099d883492f22a6da0f9ea/filter-line-shutoff-dp.svg` |
| `parts.RF-001` | `RF-001: filter_line_shutoff_dp_return_bypass` | inst-RF-001 | `symbols/seed-45797c08114c86d65c5e345002cbf97c98e65f57969b77e27bfdfdc26cf9d491/filter-line-shutoff-dp-return-bypass.svg` |
| `parts.PRV-001` | `PRV-001: priority_valve` | inst-PRV-001 | `symbols/seed-57a6ff501b52f71ccbc48188bff91f69769051d6ccb25f1d4123bec623ecb3d7/priority-valve.svg` |
| `parts.PRV-002` | `PRV-002: priority_valve` | inst-PRV-002 | `symbols/seed-57a6ff501b52f71ccbc48188bff91f69769051d6ccb25f1d4123bec623ecb3d7/priority-valve.svg` |
| `parts.ACC-001` | `ACC-001: hydro_pneumatic_accumulator` | inst-ACC-001 | `symbols/seed-79f752fc217400b9d3e65dbdf3979aab2c2944f2ca76d57309754026e3c843e6/accumulator.svg` |
| `parts.ACV-001` | `ACV-001: air_charging_valve` | inst-ACV-001 | `symbols/seed-6e4189e69c08123b2ccde13ceaaec958eeb906f8a28c493cae3420e4a0f80b9b/air-charging-valve.svg` |
| `parts.PG-001` | `PG-001: pressure_gauge` | inst-PG-001 | `symbols/seed-8ead439d3a7b18805467832ab0ad4dfa32827ffae65ac27b5f094a77d642919d/pressure-gauge.svg` |
| `parts.QDP-001` | `QDP-001: quick_disconnect_coupling_disconnected` | inst-QDP-001 | `symbols/seed-f7e42b835a79fa6ab826557e9703e998d744126fd72addceba37e9a5ef9848f1/quick-disconnect-coupling-disconnected.svg` |
| `parts.QDR-001` | `QDR-001: quick_disconnect_coupling_disconnected_return` | inst-QDR-001 | `symbols/seed-f7e42b835a79fa6ab826557e9703e998d744126fd72addceba37e9a5ef9848f1/quick-disconnect-coupling-disconnected.svg` |
| `parts.CV-002` | `CV-002: check_valve_refuel` | inst-CV-002 | `symbols/seed-25eaf4c6b5170429872b9310b465111750f0de6e33793b8bfd524488f240c92b/check-valve.svg` |
| `parts.USER-001` | `USER-001: hydraulic_user` | inst-USER-001 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |
| `parts.USER-002` | `USER-002: hydraulic_user` | inst-USER-002 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |
| `parts.USER-003` | `USER-003: hydraulic_user` | inst-USER-003 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |
| `parts.USER-004` | `USER-004: hydraulic_user` | inst-USER-004 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |
| `parts.USER-005` | `USER-005: hydraulic_user` | inst-USER-005 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |
| `parts.USER-006` | `USER-006: hydraulic_user` | inst-USER-006 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |
| `parts.USER-007` | `USER-007: hydraulic_user` | inst-USER-007 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |
| `parts.USER-008` | `USER-008: hydraulic_user` | inst-USER-008 | `symbols/seed-ec3a9ca2d0a915546915e547738c6daa5526a5658b261dfd016e402d4ff54481/hydraulic-user.svg` |

## 端口 / 母线 / 边界辅助映射

| 输入锚点 | 对象 | SVG 图元 |
| --- | --- | --- |
| `parts.TANK-001.ports.bootstrap_pressure_in` | `TANK-001.bootstrap_pressure_in` | port-TANK-001-bootstrap_pressure_in |
| `parts.TANK-001.ports.suction_out` | `TANK-001.suction_out` | port-TANK-001-suction_out |
| `parts.TANK-001.ports.return_in` | `TANK-001.return_in` | port-TANK-001-return_in |
| `parts.TANK-001.ports.body_sense_tap` | `TANK-001.body_sense_tap` | port-TANK-001-body_sense_tap |
| `parts.FSOV-001.ports.main_upper` | `FSOV-001.main_upper` | port-FSOV-001-main_upper |
| `parts.FSOV-001.ports.main_lower` | `FSOV-001.main_lower` | port-FSOV-001-main_lower |
| `parts.EDP-001.ports.suction` | `EDP-001.suction` | port-EDP-001-suction |
| `parts.EDP-001.ports.pressure_out` | `EDP-001.pressure_out` | port-EDP-001-pressure_out |
| `parts.EDP-001.ports.case_drain` | `EDP-001.case_drain` | port-EDP-001-case_drain |
| `parts.EDP-001.ports.drive_shaft` | `EDP-001.drive_shaft` | port-EDP-001-drive_shaft |
| `parts.EMP-001.ports.suction` | `EMP-001.suction` | port-EMP-001-suction |
| `parts.EMP-001.ports.pressure_out` | `EMP-001.pressure_out` | port-EMP-001-pressure_out |
| `parts.EMP-001.ports.case_drain` | `EMP-001.case_drain` | port-EMP-001-case_drain |
| `parts.EMP-001.ports.elec_power` | `EMP-001.elec_power` | port-EMP-001-elec_power |
| `parts.PF-001.ports.inlet` | `PF-001.inlet` | port-PF-001-inlet |
| `parts.PF-001.ports.outlet` | `PF-001.outlet` | port-PF-001-outlet |
| `parts.CDF-001.ports.inlet` | `CDF-001.inlet` | port-CDF-001-inlet |
| `parts.CDF-001.ports.outlet` | `CDF-001.outlet` | port-CDF-001-outlet |
| `parts.RF-001.ports.inlet` | `RF-001.inlet` | port-RF-001-inlet |
| `parts.RF-001.ports.outlet` | `RF-001.outlet` | port-RF-001-outlet |
| `parts.PRV-001.ports.inlet` | `PRV-001.inlet` | port-PRV-001-inlet |
| `parts.PRV-001.ports.outlet` | `PRV-001.outlet` | port-PRV-001-outlet |
| `parts.PRV-002.ports.inlet` | `PRV-002.inlet` | port-PRV-002-inlet |
| `parts.PRV-002.ports.outlet` | `PRV-002.outlet` | port-PRV-002-outlet |
| `parts.ACC-001.ports.hydraulic_port` | `ACC-001.hydraulic_port` | port-ACC-001-hydraulic_port |
| `parts.ACC-001.ports.gas_port` | `ACC-001.gas_port` | port-ACC-001-gas_port |
| `parts.ACV-001.ports.accumulator_gas` | `ACV-001.accumulator_gas` | port-ACV-001-accumulator_gas |
| `parts.ACV-001.ports.charge_port` | `ACV-001.charge_port` | port-ACV-001-charge_port |
| `parts.PG-001.ports.pressure_sense` | `PG-001.pressure_sense` | port-PG-001-pressure_sense |
| `parts.QDP-001.ports.ground_side` | `QDP-001.ground_side` | port-QDP-001-ground_side |
| `parts.QDP-001.ports.aircraft_side` | `QDP-001.aircraft_side` | port-QDP-001-aircraft_side |
| `parts.QDR-001.ports.ground_side` | `QDR-001.ground_side` | port-QDR-001-ground_side |
| `parts.QDR-001.ports.aircraft_side` | `QDR-001.aircraft_side` | port-QDR-001-aircraft_side |
| `parts.CV-002.ports.inlet` | `CV-002.inlet` | port-CV-002-inlet |
| `parts.CV-002.ports.outlet` | `CV-002.outlet` | port-CV-002-outlet |
| `parts.USER-001.ports.pressure_in` | `USER-001.pressure_in` | port-USER-001-pressure_in |
| `parts.USER-001.ports.return_out` | `USER-001.return_out` | port-USER-001-return_out |
| `parts.USER-002.ports.pressure_in` | `USER-002.pressure_in` | port-USER-002-pressure_in |
| `parts.USER-002.ports.return_out` | `USER-002.return_out` | port-USER-002-return_out |
| `parts.USER-003.ports.pressure_in` | `USER-003.pressure_in` | port-USER-003-pressure_in |
| `parts.USER-003.ports.return_out` | `USER-003.return_out` | port-USER-003-return_out |
| `parts.USER-004.ports.pressure_in` | `USER-004.pressure_in` | port-USER-004-pressure_in |
| `parts.USER-004.ports.return_out` | `USER-004.return_out` | port-USER-004-return_out |
| `parts.USER-005.ports.pressure_in` | `USER-005.pressure_in` | port-USER-005-pressure_in |
| `parts.USER-005.ports.return_out` | `USER-005.return_out` | port-USER-005-return_out |
| `parts.USER-006.ports.pressure_in` | `USER-006.pressure_in` | port-USER-006-pressure_in |
| `parts.USER-006.ports.return_out` | `USER-006.return_out` | port-USER-006-return_out |
| `parts.USER-007.ports.pressure_in` | `USER-007.pressure_in` | port-USER-007-pressure_in |
| `parts.USER-007.ports.return_out` | `USER-007.return_out` | port-USER-007-return_out |
| `parts.USER-008.ports.pressure_in` | `USER-008.pressure_in` | port-USER-008-pressure_in |
| `parts.USER-008.ports.return_out` | `USER-008.return_out` | port-USER-008-return_out |
| `buses.CASE` | `@CASE` | wire-43-0 |
| `buses.MANIFOLD` | `@MANIFOLD` | wire-39-0 |
| `buses.PRESS` | `@PRESS` | wire-38-0 |
| `buses.RET` | `@RET` | wire-42-0 |
| `buses.USERR` | `@USERR` | wire-41-0 |
| `buses.USR` | `@USR` | wire-40-0 |

## 简化说明 / 未知项

以下未知项只披露，不生成连接；逻辑实例数不按 SVG 片段数累加。

- ETP-selector-valve-not-in-catalog
- ETP-unit-not-in-catalog
- ground-refuel-assembly-not-in-catalog
- priority-valve-internal-check-flow-pending
- quick-disconnect-port-semantics-pending
- filter-line-shutoff-dp-standard-page-pending
- return-filter-bypass-assembly-constructed
- return-filter-bypass-cracking-flow-pending
- return-filter-bypass-branch-position-assumed
- air-charging-valve-port-sides-user-confirmed
- pressure-gauge-medium-pneumatic-assumed
- hydraulic-user-symbol-provisional
- FSOV-001-suction-side-placement-assumed
- TANK-001-return-port-count-unconfirmed
- system-relief-valve-not-declared
- pump-isolation-check-valves-not-declared
- EDP-001-drive-shaft-destination
- EMP-001-elec-power-destination
- FSOV-001-command-destination
- QD-open-ends-are-disconnected-position
- accumulator-charge-source-not-declared
- system-pressure-class
- EDP-001-rated-flow
- EMP-001-rated-flow
- ACC-001-precharge-pressure
- ACC-001-volume
- PF-001-filtration-rating
- RF-001-filtration-rating
- CDF-001-filtration-rating
- operating-modes
