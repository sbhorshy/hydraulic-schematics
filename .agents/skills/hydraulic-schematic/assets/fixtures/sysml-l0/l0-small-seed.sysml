/*
 * L0-SMALL-SEED —— #52 validate_sysml 独立正例模型（与 1# 系统无关的具名测试模型）。
 *
 * 拓扑对应 assets/fixtures/l0-small-seed/1#系统.intent.yaml 的最小供油链
 * （油箱吸油 → 发动机驱动泵 → 压力滤 → 用户边界），布局 seed 直接复用该
 * 夹具的 1#系统.layout.json（坐标显式给定）。回油、自增压与壳体回油未建模，
 * 转换器按未连接目录端口自动披露进 unknown。
 *
 * extern 边界采用本仓库原生边界写法（窄约定见 references/sysml-l0.md §6）：
 * 系统 part 内 port 'USR-001'; 是 SysML 实体声明，connect 直接引用该端口；
 * 下面这行注释只补充 L0 边界角色，不替代实体声明（仅注释而无端口声明会被
 * 转换器拒绝）：
 *   extern: USR-001=outlet
 */

package 'L0-SMALL-SEED' {

    part def 'bootstrap_reservoir' {
        port 'suction_out';
        port 'return_in';
        port 'bootstrap_pressure_in';
    }

    part def 'engine_driven_pump' {
        port 'suction';
        port 'pressure_out';
        port 'case_drain';
    }

    part def 'pressure_filter' {
        port 'inlet';
        port 'outlet';
    }

    part 'HYD-SUPPLY-FIXTURE' {
        port 'USR-001';
        part 'TANK-001' : 'bootstrap_reservoir';
        part 'EDP-001' : 'engine_driven_pump';
        part 'PF-001' : 'pressure_filter';

        // 吸油段：全显式端口
        connect 'TANK-001'.'suction_out' to 'EDP-001'.'suction';

        // 压力段：泵出口 → 压力滤入口
        connect 'EDP-001'.'pressure_out' to 'PF-001'.'inlet';

        // 边界段：压力滤出口 → 系统边界端口（L0 角色 outlet 由注释声明）
        connect 'PF-001'.'outlet' to 'USR-001';
    }
}
