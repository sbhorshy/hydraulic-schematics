# RESERVOIR-TEMP-SENSING 追溯清单

来源: `reservoir-temp-sensing.intent.yaml`(L0 v1.1,目录 comac-hydraulic-components@0.1-draft,成熟度 concept)。
图面: `reservoir-temp-sensing.svg`,布局 `reservoir-temp-sensing.layout.json`。

## 节点(part)映射

| intent 行 | 实例 | 类型 | 图上元件 | 符号文件 |
|---|---|---|---|---|
| 21 | TANK-001 | bootstrap_reservoir | inst-TANK-001 | bootstrap-type-reservoir.svg |
| 22 | TT-001 | temperature_transducer | inst-TT-001 | temperature-transducer.svg |
| 23 | TSW-001 | temperature_switch | inst-TSW-001 | temperature-switch.svg |
| 18 | RET-001 | extern:return | 边界标记 (120,490) | — |

## 连接(边)映射

| intent 行 | 语句 | 图上折线(端点) | 线型 | 实例数 |
|---|---|---|---|---|
| 27 | `RET-001 -> TANK-001.return_in` | (120,490)->(300,490) | return | 1 |

## 测量支路(taps,规范 11.1)

| intent 行 | 语句 | 图上支路(端点) | 接入三通 |
|---|---|---|---|
| 33 | `{"sensor": "TT-001", "at": "TANK-001.return_in", "position": "upstream"}` | (280,723)->(260,490) | (260,490) |
| 34 | `{"sensor": "TSW-001", "at": "TANK-001.return_in", "position": "upstream"}` | (150,924)->(130,490) | (130,490) |

## 简化说明(概念级抽象,逐条披露)

1. 油箱用目录内唯一油箱类型 bootstrap_reservoir(带液位计自增压油箱,符号 draft 状态,图签栏已披露)。目录没有开放式常压油箱类型。
2. 目录的 bootstrap_reservoir 没有"油箱本体感温口";两只感温件的测点按 taps 规则挂在 TANK-001.return_in 所在回油网络(安装点取网络最近接入点),油箱内油温整体分布未建模(unknown: TANK-001.bulk_temp_sense_port_not_in_catalog)。
3. 感温件的电输出口(TT-001/TSW-001.elec_out)去向未声明,按悬空端口标红,不代为接线;冻结契约不含 signal 节,远传指示未建模(unknown: *.elec_out_destination)。
4. 油箱自增压气源(TANK-001.bootstrap_pressure_in)与吸油去向(TANK-001.suction_out,泵未声明)未建模,端口悬空标红。
5. 悬空端口 4 个: TANK-001.bootstrap_pressure_in TANK-001.suction_out TSW-001.elec_out TT-001.elec_out。
