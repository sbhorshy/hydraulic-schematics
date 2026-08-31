# HYD-SYS-1 追溯清单

来源: `1#系统.intent.yaml`(L0 v1.1,目录 comac-hydraulic-components@0.3-draft,成熟度 concept),由工程师手写组件清单 `1#系统组件.json` 落成。
图面: `1#系统原理图.svg`,布局 `1#系统.layout.json`。

## 节点(part)映射

| intent 行 | 实例 | 类型 | 清单项 | 图上元件 | 符号文件 |
|---|---|---|---|---|---|
| 27 | TANK-001 | bootstrap_reservoir | 清单17 bootstrap-type-reservoir(油箱) | inst-TANK-001 | reservoir-bootstrap-annotated.svg |
| 28 | FSOV-001 | firewall_shutoff_valve | 清单3 firewall-shutoff-valve(FWSOV) | inst-FSOV-001 | fsov-provisional-stroke.svg |
| 29 | EDP-001 | engine_driven_pump | 清单1 EDP | inst-EDP-001 | edp-provisional-stroke.svg |
| 30 | EMP-001 | electric_motor_driven_pump | 清单2 EMP | inst-EMP-001 | emp-provisional-stroke.svg |
| 31 | PF-001 | filter_line_shutoff_dp | 清单5 filter-line-shutoff-dp(压力油滤) | inst-PF-001 | filter-line-shutoff-dp.svg |
| 32 | CDF-001 | filter_line_shutoff_dp_case_drain | 清单6 filter-line-shutoff-dp(壳体回油滤) | inst-CDF-001 | filter-line-shutoff-dp.svg |
| 33 | RF-001 | filter_line_shutoff_dp_return | 清单7 filter-line-shutoff-dp(回油滤) | inst-RF-001 | filter-line-shutoff-dp.svg |
| 34 | PRV-001 | priority_valve | 清单9 priority-valve(优先阀) | inst-PRV-001 | priority-valve.svg |
| 35 | PRV-002 | priority_valve | 清单14 priority-valve(自增压优先阀) | inst-PRV-002 | priority-valve.svg |
| 36 | ACC-001 | hydro_pneumatic_accumulator | 清单15 accumulator(系统蓄压器) | inst-ACC-001 | accumulator.svg |
| 37 | ACV-001 | air_charging_valve | 清单16 air-charging-valve(充气活门) | inst-ACV-001 | air-charging-valve.svg |
| 38 | PG-001 | pressure_gauge | 清单16 pressure-gauge(充气压力表) | inst-PG-001 | pressure-gauge.svg |
| 39 | QDP-001 | quick_disconnect_coupling_disconnected | 清单8 quick-disconnect(地面压力快卸接头) | inst-QDP-001 | quick-disconnect-coupling-disconnected.svg |
| 40 | QDR-001 | quick_disconnect_coupling_disconnected_return | 清单4 quick-disconnect(地面回油快卸接头) | inst-QDR-001 | quick-disconnect-coupling-disconnected.svg |
| 41 | USER-001 | hydraulic_user |  | inst-USER-001 | hydraulic-user.svg |
| 42 | USER-002 | hydraulic_user |  | inst-USER-002 | hydraulic-user.svg |
| 43 | USER-003 | hydraulic_user |  | inst-USER-003 | hydraulic-user.svg |
| 44 | USER-004 | hydraulic_user |  | inst-USER-004 | hydraulic-user.svg |
| 45 | USER-005 | hydraulic_user |  | inst-USER-005 | hydraulic-user.svg |
| 46 | USER-006 | hydraulic_user |  | inst-USER-006 | hydraulic-user.svg |
| 47 | USER-007 | hydraulic_user |  | inst-USER-007 | hydraulic-user.svg |
| 48 | USER-008 | hydraulic_user |  | inst-USER-008 | hydraulic-user.svg |

## 连接(边)映射

| intent 行 | 语句 | 图上折线(端点) | 线型 | 实例数 |
|---|---|---|---|---|
| 55 | `TANK-001.suction_out -> EMP-001.suction` | (298,666)->(538,650) | suction | 1 |
| 56 | `TANK-001.suction_out -> FSOV-001` | (298,666)->(368,330) | suction | 1 |
| 56 | `FSOV-001 -> EDP-001.suction` | (448,330)->(538,330) | suction | 1 |
| 60 | `EDP-001.pressure_out -> @PRESS` | (618,330)->(810,0) | pressure | 1 |
| 61 | `EMP-001.pressure_out -> @PRESS` | (618,650)->(810,0) | pressure | 1 |
| 62 | `@PRESS -> PF-001` | (810,0)->(1000,330) | pressure | 1 |
| 62 | `PF-001 -> @MANIFOLD` | (1080,330)->(1170,0) | pressure | 1 |
| 66 | `@MANIFOLD -> PRV-001` | (1170,0)->(1300,329) | pressure | 1 |
| 66 | `PRV-001 -> @USR` | (1440,329)->(1480,0) | pressure | 1 |
| 67 | `@USR -> USER-001.pressure_in` | (1480,0)->(1498,190) | pressure | 1 |
| 68 | `@USR -> USER-002.pressure_in` | (1480,0)->(1498,295) | pressure | 1 |
| 69 | `@USR -> USER-003.pressure_in` | (1480,0)->(1498,400) | pressure | 1 |
| 70 | `@USR -> USER-004.pressure_in` | (1480,0)->(1498,505) | pressure | 1 |
| 71 | `@USR -> USER-005.pressure_in` | (1480,0)->(1498,610) | pressure | 1 |
| 72 | `@USR -> USER-006.pressure_in` | (1480,0)->(1498,715) | pressure | 1 |
| 73 | `@USR -> USER-007.pressure_in` | (1480,0)->(1498,820) | pressure | 1 |
| 74 | `@USR -> USER-008.pressure_in` | (1480,0)->(1498,925) | pressure | 1 |
| 75 | `@MANIFOLD -> ACC-001.hydraulic_port` | (1170,0)->(1190,290) | pressure | 1 |
| 76 | `@PRESS -> PRV-002` | (810,0)->(578,791) | pressure | 1 |
| 76 | `PRV-002 -> TANK-001.bootstrap_pressure_in` | (438,791)->(252,820) | pressure | 1 |
| 77 | `@MANIFOLD -> QDP-001.inlet` | (1170,0)->(1188,574) | pressure | 1 |
| 82 | `USER-001.return_out -> @USERR` | (1618,190)->(1636,0) | return | 1 |
| 83 | `USER-002.return_out -> @USERR` | (1618,295)->(1636,0) | return | 1 |
| 84 | `USER-003.return_out -> @USERR` | (1618,400)->(1636,0) | return | 1 |
| 85 | `USER-004.return_out -> @USERR` | (1618,505)->(1636,0) | return | 1 |
| 86 | `USER-005.return_out -> @USERR` | (1618,610)->(1636,0) | return | 1 |
| 87 | `USER-006.return_out -> @USERR` | (1618,715)->(1636,0) | return | 1 |
| 88 | `USER-007.return_out -> @USERR` | (1618,820)->(1636,0) | return | 1 |
| 89 | `USER-008.return_out -> @USERR` | (1618,925)->(1636,0) | return | 1 |
| 90 | `@USERR -> RF-001` | (1636,0)->(1280,1040) | return | 1 |
| 90 | `RF-001 -> @RET` | (1200,1040)->(960,0) | return | 1 |
| 91 | `@RET -> TANK-001.return_in` | (960,0)->(80,666) | return | 1 |
| 92 | `@RET -> QDR-001.inlet` | (960,0)->(1140,934) | return | 1 |
| 96 | `EDP-001.case_drain -> @CASE` | (578,370)->(658,0) | case_drain | 1 |
| 97 | `EMP-001.case_drain -> @CASE` | (578,690)->(658,0) | case_drain | 1 |
| 98 | `@CASE -> CDF-001` | (658,0)->(480,217) | case_drain | 1 |
| 98 | `CDF-001 -> TANK-001.return_in` | (480,160)->(80,666) | case_drain | 1 |

## 气侧支路(taps,规范 11.1)

| intent 行 | 语句 | 图上支路(端点) |
|---|---|---|
| 102 | `{"sensor": "ACV-001.accumulator_gas", "at": "ACC-001.gas_port"}` | (1180,120)->(1190,190) |
| 103 | `{"sensor": "PG-001.pressure_sense", "at": "ACV-001.charge_port"}` | (1389,137)->(1314,120) |

## 简化说明(概念级抽象,逐条披露)

1. 清单 18 项中 4 项未入图:能源转换装置选择阀、能源转换装置(判读疑似 PTU)、集中加油组件——类型与符号均未登记;地面加油单向阀——类型受控(check_valve)但加油口拓扑未声明。对应 unknown: ETP-selector-valve-not-in-catalog / ETP-unit-not-in-catalog / ground-refuel-assembly-not-in-catalog / ground-refuel-check-valve-connection-unknown。
2. 壳体回油滤清单只声明 1 只,双泵壳体回油经 @CASE 母线合流入滤(unknown: TANK-001-return-port-count-unconfirmed 同源问题:主回油+壳体回油共用油箱 return_in 端口)。
3. FWSOV 装吸油侧沿 system-1 审查卡 D-1 判断;若实际在压力侧须重接(unknown: FSOV-001-suction-side-placement-assumed)。
4. 气侧件(充气活门/充气压力表)按预检处方走 taps 专线,不入液压 paths;充气源去向未声明,charge_port 由压力表接入即为末端(unknown: accumulator-charge-source-not-declared)。
5. 两只地面快卸接头画为断开位:机侧接入母线支路,地面侧开放,悬空端口红圈是断开位语义而非缺线(unknown: QD-open-ends-are-disconnected-position)。
6. 悬空端口 5 个: EDP-001.drive_shaft EMP-001.elec_power FSOV-001.command QDP-001.outlet QDR-001.outlet。其中 EDP.drive_shaft、EMP.elec_power、FSOV.command 为动力源/命令端去向未声明。
7. 目录为本工作目录扩展副本(0.3-draft):基于 skill 快照 0.2-draft 新增 8 个类型(油滤三变体/快卸接头两变体/优先阀/充气活门/充气压力表),详见 build_catalog.py;这些类型尚未回登记规范源 已标注/component-catalog.json,冻结前须补。
8. 构图预算披露(validation-report.json):B1 交叉 0、B2 折返/单条 3、B4/B5/B6 达标;B3 油箱回油线(@RET->TANK.return_in,顶绕走廊 y=100)绕行比 2.373 > 1.5 走 WARN 通道——根因是油箱单一 return_in 端口(unknown: TANK-001-return-port-count-unconfirmed),确认多回油口后本线可拆直。V4 的"三通点不在母线"为图例示例点,非实体三通;V5 计 9 个悬空端口系校核器未计 taps 连通,图面实际标红 5 个(EDP-001.drive_shaft、EMP-001.elec_power、FSOV-001.command、QDP-001.outlet、QDR-001.outlet,后两者为断开位语义)。
