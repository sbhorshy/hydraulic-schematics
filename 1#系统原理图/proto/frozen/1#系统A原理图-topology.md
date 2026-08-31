# HYD-SYS-1 追溯清单

来源: `1#系统.intent.yaml`(L0 v1.1,目录 comac-hydraulic-components@0.3-draft,成熟度 concept),由工程师手写组件清单 `1#系统组件.json` 落成。
图面: `1#系统原理图.svg`,布局 `1#系统.layout.json`。

## 节点(part)映射

| intent 行 | 实例 | 类型 | 清单项 | 图上元件 | 符号文件 |
|---|---|---|---|---|---|
| 28 | TANK-001 | bootstrap_reservoir | 清单17 bootstrap-type-reservoir(油箱) | inst-TANK-001 | reservoir-bootstrap-annotated.svg |
| 29 | FSOV-001 | firewall_shutoff_valve | 清单3 firewall-shutoff-valve(FWSOV) | inst-FSOV-001 | fsov-provisional-stroke.svg |
| 30 | EDP-001 | engine_driven_pump | 清单1 EDP | inst-EDP-001 | edp-provisional-stroke.svg |
| 31 | EMP-001 | electric_motor_driven_pump | 清单2 EMP | inst-EMP-001 | emp-provisional-stroke.svg |
| 32 | PF-001 | filter_line_shutoff_dp | 清单5 filter-line-shutoff-dp(压力油滤) | inst-PF-001 | filter-line-shutoff-dp.svg |
| 33 | CDF-001 | filter_line_shutoff_dp_case_drain | 清单6 filter-line-shutoff-dp(壳体回油滤) | inst-CDF-001 | filter-line-shutoff-dp.svg |
| 34 | RF-001 | filter_line_shutoff_dp_return | 清单7 filter-line-shutoff-dp(回油滤) | inst-RF-001 | filter-line-shutoff-dp.svg |
| 35 | PRV-001 | priority_valve | 清单9 priority-valve(优先阀) | inst-PRV-001 | priority-valve.svg |
| 36 | PRV-002 | priority_valve | 清单14 priority-valve(自增压优先阀) | inst-PRV-002 | priority-valve.svg |
| 37 | ACC-001 | hydro_pneumatic_accumulator | 清单15 accumulator(系统蓄压器) | inst-ACC-001 | accumulator.svg |
| 38 | ACV-001 | air_charging_valve | 清单16 air-charging-valve(充气活门) | inst-ACV-001 | air-charging-valve.svg |
| 39 | PG-001 | pressure_gauge | 清单16 pressure-gauge(充气压力表) | inst-PG-001 | pressure-gauge.svg |
| 40 | QDP-001 | quick_disconnect_coupling_disconnected | 清单8 quick-disconnect(地面压力快卸接头) | inst-QDP-001 | quick-disconnect-coupling-disconnected.svg |
| 41 | QDR-001 | quick_disconnect_coupling_disconnected_return | 清单4 quick-disconnect(地面回油快卸接头) | inst-QDR-001 | quick-disconnect-coupling-disconnected.svg |
| 24 | USR-001 | extern:outlet | 清单18 用户(未建模为组件) | 边界标记 (1480,400) | — |
| 25 | USR-002 | extern:return | 清单18 用户(未建模为组件) | 边界标记 (1480,700) | — |

## 连接(边)映射

| intent 行 | 语句 | 图上折线(端点) | 线型 | 实例数 |
|---|---|---|---|---|
| 48 | `TANK-001.suction_out -> EMP-001.suction` | (278,686)->(538,650) | suction | 1 |
| 49 | `TANK-001.suction_out -> FSOV-001` | (278,686)->(368,330) | suction | 1 |
| 49 | `FSOV-001 -> EDP-001.suction` | (448,330)->(538,330) | suction | 1 |
| 53 | `EDP-001.pressure_out -> @PRESS` | (618,330)->(880,0) | pressure | 1 |
| 54 | `EMP-001.pressure_out -> @PRESS` | (618,650)->(880,0) | pressure | 1 |
| 55 | `@PRESS -> PF-001` | (880,0)->(1000,358) | pressure | 1 |
| 55 | `PF-001 -> @MANIFOLD` | (1080,358)->(1160,0) | pressure | 1 |
| 59 | `@MANIFOLD -> PRV-001` | (1160,0)->(1300,317) | pressure | 1 |
| 59 | `PRV-001 -> USR-001` | (1440,317)->(1480,400) | pressure | 1 |
| 60 | `@MANIFOLD -> ACC-001.hydraulic_port` | (1160,0)->(1210,290) | pressure | 1 |
| 61 | `@PRESS -> PRV-002` | (880,0)->(578,781) | pressure | 1 |
| 61 | `PRV-002 -> TANK-001.bootstrap_pressure_in` | (438,781)->(232,840) | pressure | 1 |
| 62 | `@MANIFOLD -> QDP-001.inlet` | (1160,0)->(1190,536) | pressure | 1 |
| 65 | `USR-002 -> RF-001` | (1480,700)->(1280,728) | return | 1 |
| 65 | `RF-001 -> @RET` | (1200,728)->(940,0) | return | 1 |
| 66 | `@RET -> TANK-001.return_in` | (940,0)->(60,686) | return | 1 |
| 67 | `@RET -> QDR-001.inlet` | (940,0)->(1200,934) | return | 1 |
| 71 | `EDP-001.case_drain -> @CASE` | (578,370)->(658,0) | case_drain | 1 |
| 72 | `EMP-001.case_drain -> @CASE` | (578,690)->(658,0) | case_drain | 1 |
| 73 | `@CASE -> CDF-001` | (658,0)->(480,157) | case_drain | 1 |
| 73 | `CDF-001 -> TANK-001.return_in` | (480,100)->(60,686) | case_drain | 1 |

## 气侧支路(taps,规范 11.1)

| intent 行 | 语句 | 图上支路(端点) |
|---|---|---|
| 77 | `{"sensor": "ACV-001.accumulator_gas", "at": "ACC-001.gas_port"}` | (1213,90)->(1210,190) |
| 78 | `{"sensor": "PG-001.pressure_sense", "at": "ACV-001.charge_port"}` | (1446,127)->(1347,90) |

## 简化说明(概念级抽象,逐条披露)

1. 清单 18 项中 4 项未入图:能源转换装置选择阀、能源转换装置(判读疑似 PTU)、集中加油组件——类型与符号均未登记;地面加油单向阀——类型受控(check_valve)但加油口拓扑未声明。对应 unknown: ETP-selector-valve-not-in-catalog / ETP-unit-not-in-catalog / ground-refuel-assembly-not-in-catalog / ground-refuel-check-valve-connection-unknown。
2. 壳体回油滤清单只声明 1 只,双泵壳体回油经 @CASE 母线合流入滤(unknown: TANK-001-return-port-count-unconfirmed 同源问题:主回油+壳体回油共用油箱 return_in 端口)。
3. FWSOV 装吸油侧沿 system-1 审查卡 D-1 判断;若实际在压力侧须重接(unknown: FSOV-001-suction-side-placement-assumed)。
4. 气侧件(充气活门/充气压力表)按预检处方走 taps 专线,不入液压 paths;充气源去向未声明,charge_port 由压力表接入即为末端(unknown: accumulator-charge-source-not-declared)。
5. 两只地面快卸接头画为断开位:机侧接入母线支路,地面侧开放,悬空端口红圈是断开位语义而非缺线(unknown: QD-open-ends-are-disconnected-position)。
6. 悬空端口 5 个: EDP-001.drive_shaft EMP-001.elec_power FSOV-001.command QDP-001.outlet QDR-001.outlet。其中 EDP.drive_shaft、EMP.elec_power、FSOV.command 为动力源/命令端去向未声明。
7. 目录为本工作目录扩展副本(0.3-draft):基于 skill 快照 0.2-draft 新增 8 个类型(油滤三变体/快卸接头两变体/优先阀/充气活门/充气压力表),详见 build_catalog.py;这些类型尚未回登记规范源 已标注/component-catalog.json,冻结前须补。
8. 构图预算披露(validation-report.json):B1 交叉 0、B2 折返/单条 3、B4/B5/B6 达标;B3 油箱回油线(@RET->TANK.return_in,顶绕走廊 y=100)绕行比 2.373 > 1.5 走 WARN 通道——根因是油箱单一 return_in 端口(unknown: TANK-001-return-port-count-unconfirmed),确认多回油口后本线可拆直。V4 的"三通点不在母线"为图例示例点,非实体三通;V5 计 9 个悬空端口系校核器未计 taps 连通,图面实际标红 5 个(EDP-001.drive_shaft、EMP-001.elec_power、FSOV-001.command、QDP-001.outlet、QDR-001.outlet,后两者为断开位语义)。
