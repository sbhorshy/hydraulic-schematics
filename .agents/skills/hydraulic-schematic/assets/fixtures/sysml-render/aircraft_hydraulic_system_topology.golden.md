# aircraft_hydraulic_system 整机原理图追溯清单
本清单把 SVG 中的每个节点/边映射到 SysML 模型的唯一输入定义(行号),遵循仓库核心原则"任一组件/端口/连接/图元可追溯到唯一输入定义"。
## 连接(边)映射
| 来源 connect 行 | SysML 语句 | 图上的边 | 实例数 |
|---|---|---|---|
| 197 | `connect mechanicalInput to enginePump.mechanicalInput` | enginePump 驱动轴(机械) | 绿+黄(×2) |
| 198 | `connect enginePumpCommand to enginePump.command` | 发动机泵指令(在电路边界 enginePumpCommand 聚合, 图上未单独画到 EDP) | 绿+黄(×2) |
| 199 | `connect electricPumpCommand to electricPump.command` | 电动泵指令(同上, 边界口聚合) | 绿+黄(×2) |
| 200 | `connect reservoir.service to enginePump.hydraulicOutput` | 油箱供油→EDP | 绿+黄(×2) |
| 201 | `connect reservoir.service to electricPump.hydraulicOutput` | 油箱供油→EMP | 绿+黄(×2) |
| 202 | `connect enginePump.hydraulicOutput to filterUnit.inlet` | EDP 压力→压力滤 | 绿+黄(×2) |
| 203 | `connect electricPump.hydraulicOutput to filterUnit.inlet` | EMP 压力→压力滤 | 绿+黄(×2) |
| 204 | `connect filterUnit.outlet to pressureControl.inlet` | 压力滤→压力控制阀 | 绿+黄(×2) |
| 205 | `connect pressureControl.outlet to isolationValve.inlet` | 压力控制阀→隔离阀 | 绿+黄(×2) |
| 206 | `connect isolationValve.outlet to accumulator.service` | 隔离阀→蓄压器(并联支路) | 绿+黄(×2) |
| 207 | `connect isolationValve.outlet to systemOutput` | 隔离阀→系统输出 | 绿+黄(×2) |
| 222 | `connect greenCircuit.systemOutput to powerTransferUnit.greenInput` | 绿→PTU 绿侧 | ×1 |
| 223 | `connect yellowCircuit.systemOutput to powerTransferUnit.yellowInput` | 黄→PTU 黄侧 | ×1 |
| 224 | `connect greenCircuit.systemOutput to landingGear.hydraulicInput` | 绿→起落架 | ×1 |
| 225 | `connect yellowCircuit.systemOutput to flightControls.hydraulicInput` | 黄→飞控 | ×1 |
| 227 | `connect controller.greenPumpCommand to greenCircuit.enginePumpCommand` | 控制器→绿泵指令 | ×1 |
| 228 | `connect controller.yellowPumpCommand to yellowCircuit.enginePumpCommand` | 控制器→黄泵指令 | ×1 |
| 229 | `connect controller.ptuCommand to powerTransferUnit.command` | 控制器→PTU 指令 | ×1 |
| 230 | `connect controller.landingGearCommand to landingGear.command` | 控制器→起落架指令 | ×1 |
| 231 | `connect controller.flightControlCommand to flightControls.command` | 控制器→飞控指令 | ×1 |

## 节点(part)映射
| 来源行 | part | 图上元件 | 符号 |
|---|---|---|---|
| 151 | `noseGearActuator:LinearActuator` | noseGearActuator | 总成/框图 |
| 152 | `leftMainGearActuator:LinearActuator` | leftMainGearActuator | 总成/框图 |
| 153 | `rightMainGearActuator:LinearActuator` | rightMainGearActuator | 总成/框图 |
| 160 | `leftAileronActuator:LinearActuator` | leftAileronActuator | 总成/框图 |
| 161 | `rightAileronActuator:LinearActuator` | rightAileronActuator | 总成/框图 |
| 162 | `elevatorActuator:LinearActuator` | elevatorActuator | 总成/框图 |
| 163 | `rudderActuator:LinearActuator` | rudderActuator | 总成/框图 |
| 183 | `reservoir:Reservoir` | reservoir | 油箱(描边) |
| 184 | `enginePump:EngineDrivenPump` | enginePump | EDP(临时几何) |
| 185 | `electricPump:ElectricMotorPump` | electricPump | EMP(临时几何) |
| 186 | `accumulator:Accumulator` | accumulator | 蓄压器(描边) |
| 187 | `filterUnit:Filter` | filterUnit | 压力滤(描边) |
| 188 | `pressureControl:PressureControlValve` | pressureControl | 压力控制阀(绘制框图) |
| 189 | `isolationValve:IsolationValve` | isolationValve | 隔离阀(绘制框图) |
| 215 | `greenCircuit:HydraulicCircuit` | greenCircuit | 总成/框图 |
| 216 | `yellowCircuit:HydraulicCircuit` | yellowCircuit | 总成/框图 |
| 217 | `powerTransferUnit:PowerTransferUnit` | powerTransferUnit | 总成/框图 |
| 218 | `landingGear:LandingGearActuationSystem` | landingGear | 总成/框图 |
| 219 | `flightControls:FlightControlActuationSystem` | flightControls | 总成/框图 |
| 220 | `controller:HydraulicSystemController` | controller | 总成/框图 |
| 235 | `aircraftHydraulics:AircraftHydraulicSystem` | aircraftHydraulics | 总成/框图 |

## 概念模型简化说明
- 各作动器(起落架/飞控)的**回油**在模型中未建模,图上未画。
- `status` 端口存在但整机层无连线(概念级),图上仅以端口点示意,未接出。
- 回路内部指令(198/199: enginePumpCommand→enginePump.command 等)在电路边界 `enginePumpCommand` 端口聚合,图上未单独画到泵。
- 泵与油箱的 `reservoir.service↔pump.hydraulicOutput` 经 HydraulicPowerPort 同时绑定供油与回油;图上只画供油(正方向),回油半边在概念层抽象,未单独绘制。
- 黄系统为绿系统的水平镜像布局,两者内部拓扑相同。
- PTU 传递功率不传递液体(模型注释),图上 PTU 两侧只画供压入口,无流体连通线。
