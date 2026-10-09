/*
 * HYD-SYS-1 拓扑模型(SysML v2,仅拓扑关系)
 *
 * 来源: 1#系统.intent.yaml(L0 v1.1,目录 comac-hydraulic-components@0.3-draft,成熟度 concept)
 *       与 1#系统_topology.md / 1#系统原理图.svg 同源,逐边对应。
 * 范围: parts + ports + connections,不含参数、行为与属性。端口不标方向(意图层未声明)。
 * 母线: @PRESS/@MANIFOLD/@USR/@USERR/@RET/@CASE 是原理图的绘图抽象(非部件)。
 *       不建 n 元 connection(SysIDE 文法只支持二元 connect),改为星形编码:
 *       以母线上真实存在的枢纽端口/部件为中心做二元连接,同一枢纽的连接共节点,
 *       汇流语义不变。枢纽取:@PRESS=PF-001.inlet、@MANIFOLD=PF-001.outlet、
 *       @USR=PRV-001、@USERR=RF-001.inlet、@RET=RF-001.outlet、@CASE=CDF-001.inlet。
 * 边数核对: 40 条二元 connect。构成 = 清单拓扑 41 边(39 液压 + 2 taps)- 7 条汇流边
 *       并入枢纽 + 2026-09-07 新增:EMP 溢流→生态瓶 +1、刹车支路净 +2(替代 1 直连)、
 *       EDP 三线泵侧串快卸拆边净 +3、集中加油支路 +1(CV-002 出口接回油滤前枢纽)、
 *       蓄压器液端改挂自增压支路 ±0(@MANIFOLD 换 PRV-002 下游)。
 * 油滤装配(与 filter-line-shutoff-dp.svg 一一对应,用户口径:只记拓扑):
 *       油滤本体 = 滤芯 + 压差传感器(传感器两感压口跨接滤芯上游/下游,对应符号两根竖管);
 *       目录三类型各自内联本体结构,与 SVG 符号一一对应(SysIDE 文法不接受
 *       "定义名带引号或下划线 + 特化冒号",空特化写法过不了门禁,故不复用基型);
 *       PF 实例直用本体类型;回油滤为组件 return_filter
 *       = 本体(filter_line_shutoff_dp_return 基型)+ 弹簧单向阀旁通(2026-09-07 用户口径,
 *       滤芯堵塞压差顶开旁通,流向判断待工程确认;intent/原理图已于同日同步,
 *       目录类型 filter_line_shutoff_dp_return_bypass,符号 100x194);
 *       壳体回油滤为组件 case_drain_filter = 本体(filter_line_shutoff_dp 基型)+ 单向阀串联
 *       (两个组件层类型目录均无对应符号)。
 *       内部连接:本体结构 4 条 ×3 + case_drain_filter 3 条 + return_filter 4 条 = 19 条。
 * 未入图 3 项(类型/拓扑未声明,不编造拓扑,见 intent unknown):
 *       能源转换装置选择阀、能源转换装置(疑似 PTU)、集中加油组件
 *       (其隔离单向阀 CV-002 已按 2026-09-07 口径落位:回油滤前支路)。
 */

package 'HYD-SYS-1' {

    // ===================== 组件类型(本图用到的 15 类) =====================
    // 端口只列拓扑证据到的;去向未声明的悬空端口同样声明、保持不连接。

    part def 'bootstrap_reservoir' {
        port 'suction_out';             // 吸油出
        port 'return_in';               // 回油入(主回油与壳体回油共用,unknown: TANK-001-return-port-count-unconfirmed)
        port 'bootstrap_pressure_in';   // 自增压入(PRV-002)
    }

    part def 'firewall_shutoff_valve' {
        port 'command';                 // 关断命令,悬空(unknown: FSOV-001-command-destination)
        // 流道两侧均按整件连接,无命名口证据
    }

    part def 'engine_driven_pump' {
        port 'suction';
        port 'pressure_out';
        port 'case_drain';
    }

    part def 'electric_motor_driven_pump' {
        port 'suction';
        port 'pressure_out';
        port 'case_drain';
        port 'overflow';                // 溢流口(2026-09-07 用户口径,原 elec_power 口位),接生态瓶
    }

    // ---- 油滤装配件(与 filter-line-shutoff-dp.svg 一一对应,用户口径:只记拓扑)----
    // 符号画法:压差传感器圆叉在上,两根竖管分落到菱形(滤芯)上游/下游两条斜边上
    // (x=30.5/49.5,解得 y=70.36),故传感器两感压口跨接滤芯进出油侧。

    part def 'filter_element' {
        port 'inlet';                   // 滤芯上游(脏侧)
        port 'outlet';                  // 滤芯下游(净侧)
    }

    part def 'dp_sensor' {
        port 'sense_a';                 // 上游感压口(左竖管)
        port 'sense_b';                 // 下游感压口(右竖管)
        // 符号注释:就地目视无电输出,指示器/传感器待定(unknown DPS-001_indicator_or_sensor),故无电气端口
    }

    part def 'check_valve' {
        port 'inlet';
        port 'outlet';                  // 单向阀(允许单向流通;流向语义见各使用处注释)
    }

    part def 'check_valve_refuel' {
        // 集中加油单向阀:与 check_valve 同符号(check-valve.svg),role=return——回油路,线型走回油细线
        port 'inlet';                   // 加油源侧,接集中加油组件(未建模,悬空)
        port 'outlet';                  // 出油侧,接回油滤前母线
    }

    part def 'filter_line_shutoff_dp' {
        // 压力油滤本体(role=pressure,PF-001 直用)= 滤芯 + 压差传感器
        port 'inlet';                   // 目录已登记:in,左侧
        port 'outlet';                  // 目录已登记:out,右侧

        part 'element' : 'filter_element';
        part 'sensor' : 'dp_sensor';

        // 主流路:入 -> 滤芯 -> 出;压差传感器跨滤芯感压(对应符号两根竖管)
        connect 'inlet' to 'element'.'inlet';
        connect 'element'.'outlet' to 'outlet';
        connect 'sensor'.'sense_a' to 'element'.'inlet';
        connect 'sensor'.'sense_b' to 'element'.'outlet';
    }

    part def 'check_valve_spring' {
        // 弹簧单向阀(弹簧加载常闭,压差超弹簧设定值即开;符号资产 check-valve-spring.svg,
        // 两册目录均未登记类型,绘制组件符号时补登记)
        port 'inlet';
        port 'outlet';
    }

    part def 'filter_line_shutoff_dp_return' {
        // 回油滤本体(role=return;目录登记保留,回油滤组件装配用基型),结构与压力油滤本体一致
        port 'inlet';
        port 'outlet';

        part 'element' : 'filter_element';
        part 'sensor' : 'dp_sensor';

        connect 'inlet' to 'element'.'inlet';
        connect 'element'.'outlet' to 'outlet';
        connect 'sensor'.'sense_a' to 'element'.'inlet';
        connect 'sensor'.'sense_b' to 'element'.'outlet';
    }

    part def 'return_filter' {
        // 回油滤组件 RF-001(2026-09-07 用户口径):本体 + 弹簧单向阀,旁通(组件层,
        // 目录无对应符号,绘制组件符号时补登记)。滤芯堵塞压差顶开旁通阀,继续回油;
        // 单向阀允许 inlet->outlet(与主路同向),设定值/流向为判断,待工程确认。
        port 'inlet';
        port 'outlet';

        part 'body' : 'filter_line_shutoff_dp_return';
        part 'cv' : 'check_valve_spring';

        // 旁通:入口分两路,滤芯主路与弹簧单向阀并联回合于出口
        connect 'inlet' to 'body'.'inlet';
        connect 'inlet' to 'cv'.'inlet';
        connect 'body'.'outlet' to 'outlet';
        connect 'cv'.'outlet' to 'outlet';
    }

    part def 'filter_line_shutoff_dp_case_drain' {
        // 壳体回油滤本体(role=case_drain;目录登记保留,组件装配用基型),结构与上同
        port 'inlet';
        port 'outlet';

        part 'element' : 'filter_element';
        part 'sensor' : 'dp_sensor';

        connect 'inlet' to 'element'.'inlet';
        connect 'element'.'outlet' to 'outlet';
        connect 'sensor'.'sense_a' to 'element'.'inlet';
        connect 'sensor'.'sense_b' to 'element'.'outlet';
    }

    part def 'case_drain_filter' {
        // 壳体回油滤组件 CDF-001:本体 + 单向阀,串联(组件层,目录无对应符号)
        port 'inlet';
        port 'outlet';

        part 'body' : 'filter_line_shutoff_dp';
        part 'cv' : 'check_valve';

        connect 'inlet' to 'body'.'inlet';
        connect 'body'.'outlet' to 'cv'.'inlet';
        connect 'cv'.'outlet' to 'outlet';
    }

    part def 'priority_valve';                     // PRV-001 用户供压 / PRV-002 油箱自增压,两侧整件连接

    part def 'hydro_pneumatic_accumulator' {
        port 'hydraulic_port';          // 液压口,液端,接液压管路(ACC-001 现挂自增压支路 PRV-002 下游)
        port 'gas_port';                // 气口,气端,接充气链(ACC-001 接 PG->ACV;ACC-002 充气去向未声明)
    }

    part def 'air_charging_valve' {
        port 'accumulator_gas';         // 气侧/蓄压器侧(2026-09-07 用户口径:符号右侧;现目录/SVG 记在左,待同步)
        port 'charge_port';             // 地面充气侧(2026-09-07 用户口径:符号左侧;现目录/SVG 记在右,待同步),
                                        // 链末端悬空,充气源去向未声明(unknown: accumulator-charge-source-not-declared)
    }

    part def 'pressure_gauge' {
        port 'pressure_sense';          // 测压口,气侧,串接于蓄压器与充气活门之间
    }

    part def 'eco_bottle' {
        // 生态瓶(2026-09-07 用户口径新增的独立设备,清单外,目录未登记类型/符号)
        port 'inlet';                   // 溢流收集口,接 EMP 溢流口
    }

    part def 'quick_disconnect_coupling_disconnected' {
        port 'aircraft_side';           // 机侧座端(自封常通),接母线支路(v1.3 侧别口径,原 inlet)
        port 'ground_side';             // 地面接口(分离半端),断开位悬空是预期语义(unknown: QD-open-ends-are-disconnected-position)
    }

    part def 'quick_disconnect_coupling_disconnected_return' {
        port 'aircraft_side';
        port 'ground_side';             // 断开位悬空
    }

    part def 'quick_disconnect_coupling' {
        // 快卸接头,接通位直通(2026-09-07 用户口径:EDP 三条管线泵侧各串一只,便于拆泵;
        // 目录现有两变体均为断开位地面快卸,本类型清单外/目录未登记)
        port 'inlet';
        port 'outlet';
    }

    part def 'hydraulic_user' {
        port 'pressure_in';
        port 'return_out';
    }

    // ===================== 系统实例 =====================
    // 母线(@PRESS/@MANIFOLD/@USR/@USERR/@RET/@CASE)不建连接定义,以星形枢纽表达,见各组注释。

    part 'HYD-SYS-1' {

        // 28 个实例 = 清单 18 项落成的 22 个受控实例(含 8 只用户名框)
        //            + 7 个新增设备(生态瓶、刹车单向阀 CV-001、刹车蓄压器 ACC-002、
        //              EDP 三线泵侧快卸 QD-001..003、集中加油单向阀 CV-002)
        part 'TANK-001' : 'bootstrap_reservoir';                                        // 清单17 油箱
        part 'FSOV-001' : 'firewall_shutoff_valve';                                     // 清单3 FWSOV(装吸油侧,审查卡 D-1 判断)
        part 'EDP-001'  : 'engine_driven_pump';                                         // 清单1 EDP
        part 'EMP-001'  : 'electric_motor_driven_pump';                                 // 清单2 EMP
        part 'PF-001'   : 'filter_line_shutoff_dp';                                     // 清单5 压力油滤(本体直用)
        part 'CDF-001'  : 'case_drain_filter';                                          // 清单6 壳体回油滤组件(本体+单向阀)
        part 'RF-001'   : 'return_filter';                                              // 清单7 回油滤组件(本体+弹簧单向阀旁通,2026-09-07 用户口径)
        part 'PRV-001'  : 'priority_valve';                                             // 清单9 优先阀(用户供压)
        part 'PRV-002'  : 'priority_valve';                                             // 清单14 自增压优先阀
        part 'ACC-001'  : 'hydro_pneumatic_accumulator';                                // 清单15 系统蓄压器(液端挂自增压支路 PRV-002 下游,2026-09-07 用户口径)
        part 'ACV-001'  : 'air_charging_valve';                                         // 清单16 充气活门
        part 'PG-001'   : 'pressure_gauge';                                             // 清单16 充气压力表
        part 'ECO-001'  : 'eco_bottle';                                                 // 生态瓶(2026-09-07 新增,清单外,目录未登记)
        part 'CV-001'   : 'check_valve';                                                // 刹车供压单向阀(2026-09-07 新增,清单外)
        part 'CV-002'   : 'check_valve_refuel';                                         // 集中加油单向阀(清单"地面加油单向阀",2026-09-07 落位:回油滤前支路;role=return)
        part 'ACC-002'  : 'hydro_pneumatic_accumulator';                                // 刹车蓄压器(2026-09-07 新增,清单外,挂在支路)
        part 'QD-001'   : 'quick_disconnect_coupling';                                  // EDP 吸油线泵侧快卸(2026-09-07 新增,清单外)
        part 'QD-002'   : 'quick_disconnect_coupling';                                  // EDP 压力线泵侧快卸(同上)
        part 'QD-003'   : 'quick_disconnect_coupling';                                  // EDP 壳体回油线泵侧快卸(同上)
        part 'QDP-001'  : 'quick_disconnect_coupling_disconnected';                     // 清单8 地面压力快卸(断开位)
        part 'QDR-001'  : 'quick_disconnect_coupling_disconnected_return';              // 清单4 地面回油快卸(断开位)
        part 'USER-001' : 'hydraulic_user';                                             // 清单18 MF扰流板
        part 'USER-002' : 'hydraulic_user';                                             // 清单18 襟翼
        part 'USER-003' : 'hydraulic_user';                                             // 清单18 缝翼
        part 'USER-004' : 'hydraulic_user';                                             // 清单18 副翼
        part 'USER-005' : 'hydraulic_user';                                             // 清单18 升降舵
        part 'USER-006' : 'hydraulic_user';                                             // 清单18 方向舵
        part 'USER-007' : 'hydraulic_user';                                             // 清单18 反推
        part 'USER-008' : 'hydraulic_user';                                             // 清单18 正常刹车

        // ---- 吸油(intent 行 55-56):EDP 泵侧串快卸 QD-001 ----
        connect 'TANK-001'.'suction_out' to 'EMP-001'.'suction';
        connect 'TANK-001'.'suction_out' to 'FSOV-001';
        connect 'FSOV-001' to 'QD-001'.'inlet';
        connect 'QD-001'.'outlet' to 'EDP-001'.'suction';

        // ---- 压力汇合 @PRESS(intent 行 60,61,62,76):双泵直接并联,无隔离单向阀;
        //      以压力油滤入口为枢纽,四端共节点;EDP 压力线泵侧串快卸 QD-002 ----
        connect 'EDP-001'.'pressure_out' to 'QD-002'.'inlet';
        connect 'QD-002'.'outlet' to 'PF-001'.'inlet';
        connect 'EMP-001'.'pressure_out' to 'PF-001'.'inlet';
        connect 'PRV-002' to 'PF-001'.'inlet';

        // ---- 分配母线 @MANIFOLD(intent 行 62,66,75,77):以压力油滤出口为枢纽;
        //      ACC-001 液端已移出(2026-09-07 用户口径,改挂自增压支路,见下组) ----
        connect 'PF-001'.'outlet' to 'PRV-001';
        connect 'PF-001'.'outlet' to 'QDP-001'.'aircraft_side';

        // ---- 用户供压母线 @USR(intent 行 66-74):以 PRV-001 为枢纽;USER-008(正常刹车)
        //      改经刹车支路供压,见下组 ----
        connect 'PRV-001' to 'USER-001'.'pressure_in';
        connect 'PRV-001' to 'USER-002'.'pressure_in';
        connect 'PRV-001' to 'USER-003'.'pressure_in';
        connect 'PRV-001' to 'USER-004'.'pressure_in';
        connect 'PRV-001' to 'USER-005'.'pressure_in';
        connect 'PRV-001' to 'USER-006'.'pressure_in';
        connect 'PRV-001' to 'USER-007'.'pressure_in';

        // ---- 刹车支路(2026-09-07 用户口径,清单外新增):正常刹车前串单向阀 CV-001,
        //      刹车蓄压器 ACC-002 挂在单向阀下游节点(支路,不串在主线上);
        //      单向阀防蓄压器向供压线倒灌,流向为判断,待工程确认 ----
        connect 'PRV-001' to 'CV-001'.'inlet';
        connect 'CV-001'.'outlet' to 'USER-008'.'pressure_in';
        connect 'ACC-002'.'hydraulic_port' to 'CV-001'.'outlet';

        // ---- 集中加油支路(2026-09-07 落位,原 intent unknown ground-refuel-check-valve-connection-unknown):
        //      单向阀出口接回油滤前节点(@USERR 枢纽),允许加油流进入、防倒灌(流向为判断);
        //      阀入口接集中加油组件(类型未登记,未建模,悬空) ----
        connect 'CV-002'.'outlet' to 'RF-001'.'inlet';

        // ---- 油箱自增压支路(intent 行 76)----
        connect 'PRV-002' to 'TANK-001'.'bootstrap_pressure_in';

        // ---- 蓄压器液端挂自增压支路(2026-09-07 用户口径:蓄压器两端,液端接液压管路,
        //      自 @MANIFOLD 移到 PRV-002 下游;气端充气链见文末气侧链组)----
        connect 'PRV-002' to 'ACC-001'.'hydraulic_port';

        // ---- 用户回油收集母线 @USERR(intent 行 82-90):以回油滤入口为枢纽 ----
        connect 'USER-001'.'return_out' to 'RF-001'.'inlet';
        connect 'USER-002'.'return_out' to 'RF-001'.'inlet';
        connect 'USER-003'.'return_out' to 'RF-001'.'inlet';
        connect 'USER-004'.'return_out' to 'RF-001'.'inlet';
        connect 'USER-005'.'return_out' to 'RF-001'.'inlet';
        connect 'USER-006'.'return_out' to 'RF-001'.'inlet';
        connect 'USER-007'.'return_out' to 'RF-001'.'inlet';
        connect 'USER-008'.'return_out' to 'RF-001'.'inlet';

        // ---- 回油母线 @RET(intent 行 90-92):以回油滤出口为枢纽 ----
        connect 'RF-001'.'outlet' to 'TANK-001'.'return_in';
        connect 'RF-001'.'outlet' to 'QDR-001'.'aircraft_side';

        // ---- 壳体回油母线 @CASE(intent 行 96-98):以壳体回油滤入口为枢纽,双泵合流;
        //      EDP 壳体回油线泵侧串快卸 QD-003 ----
        connect 'EDP-001'.'case_drain' to 'QD-003'.'inlet';
        connect 'QD-003'.'outlet' to 'CDF-001'.'inlet';
        connect 'EMP-001'.'case_drain' to 'CDF-001'.'inlet';

        // ---- 壳体回油滤出油并入回油母线 @RET(2026-09-07 用户口径:
        //      与回油滤出口合流为一条回油路,同赴油箱回油口与地面回油快卸;
        //      原"CDF 出油直回油箱"改接 @RET 枢纽)----
        connect 'CDF-001'.'outlet' to 'RF-001'.'outlet';

        // ---- EMP 溢流口接生态瓶(2026-09-07 用户口径;原 elec_power 悬空口改溢流口;
        //      生态瓶为清单外新增设备)----
        connect 'EMP-001'.'overflow' to 'ECO-001'.'inlet';

        // ---- 气侧链(用户 2026-09-07 口径:蓄压器气端 -> 压力表 -> 充气活门,串接,
        //      挂在自增压支路 PRV-002 下游的蓄压器气端上;与 intent 行 107-108 的
        //      taps 写法不一致,intent/原理图侧待同步;ACV 左右端口侧别也待同步:
        //      用户口径 左=地面充气侧/右=气侧,现目录与 SVG 记法相反)----
        connect 'ACC-001'.'gas_port' to 'PG-001'.'pressure_sense';
        connect 'PG-001'.'pressure_sense' to 'ACV-001'.'accumulator_gas';
    }
}
