/*
 * DEMO-SYS-1 —— #51 窄版转换器的独立正例模型（与 1# 系统无关的具名测试模型）。
 *
 * 母线枢纽声明（约定见 references/sysml-l0.md；注释中大写名经等号绑定实例/端口即生效）:
 *   枢纽取: @PRESS=PF-001.inlet、@MANIFOLD=PF-001.outlet、@USR=PRV-001.outlet、@RET=TANK-001.return_in
 * @PRESS/@MANIFOLD 为端口枢纽：PF-001两口各绑一条母线且只经母线接线，
 *   转换器按 main_path 补回桥接路径（spoke 补回，等价合并不吞边）。
 * @USR/@RET 为单口端口枢纽：每个已声明枢纽都补回到真实端口的辐条。
 * 元件枢纽口径：只有唯一目录端口的非传感元件才可作枢纽（见文档）；
 *   多端口元件裸挂枢纽会被拒绝（bare 辐条不得绕过元件）。
 * 未知/悬空: TANK-001.bootstrap_pressure_in 未连接（unknown: DEMO-bootstrap-source-not-declared）。
 */

package 'DEMO' {

    part def 'bootstrap_reservoir' {
        port 'suction_out';
        port 'return_in';
        port 'bootstrap_pressure_in';   // 悬空
    }

    part def 'engine_driven_pump' {
        port 'suction';
        port 'pressure_out';
        port 'case_drain';
    }

    part def 'filter_element' {
        port 'inlet';
        port 'outlet';
    }

    part def 'dp_sensor' {
        port 'sense_a';
        port 'sense_b';
    }

    part def 'check_valve' {
        port 'inlet';
        port 'outlet';
    }

    part def 'filter_line_shutoff_dp' {
        port 'inlet';
        port 'outlet';

        part 'element' : 'filter_element';
        part 'sensor' : 'dp_sensor';

        connect 'inlet' to 'element'.'inlet';
        connect 'element'.'outlet' to 'outlet';
        connect 'sensor'.'sense_a' to 'element'.'inlet';
        connect 'sensor'.'sense_b' to 'element'.'outlet';
    }

    part def 'filter_line_shutoff_dp_case_drain' {
        // 与 1# 手写 intent 的 CDF-001 口径一致（带压差指示的本体类型）
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
        // 组件装配形态（本体+串联单向阀）：目录无对应符号，未被引用；
        // 若被实例化，转换器按冻结折叠约定拒绝（结构无法证明的形态不折叠）。
        port 'inlet';
        port 'outlet';

        part 'body' : 'filter_line_shutoff_dp';
        part 'cv' : 'check_valve';

        connect 'inlet' to 'body'.'inlet';
        connect 'body'.'outlet' to 'cv'.'inlet';
        connect 'cv'.'outlet' to 'outlet';
    }

    part def 'priority_valve' {
        port 'inlet';                   // 供流入
        port 'outlet';                  // 出流（@USR 端口枢纽绑此口）
    }

    part def 'pressure_switch' {
        port 'pressure_sense';
    }

    part def 'hydraulic_user' {
        port 'pressure_in';
        port 'return_out';
    }

    part 'DEMO-SYS-1' {

        part 'TANK-001' : 'bootstrap_reservoir';
        part 'EDP-001' : 'engine_driven_pump';
        part 'PF-001' : 'filter_line_shutoff_dp';
        part 'CDF-001' : 'filter_line_shutoff_dp_case_drain';
        part 'PRV-001' : 'priority_valve';
        part 'SW-001' : 'pressure_switch';
        part 'USER-001' : 'hydraulic_user';

        // 吸油: 全显式端口
        connect 'TANK-001'.'suction_out' to 'EDP-001'.'suction';

        // 压力: EDP 出口接 @PRESS 枢纽（端口枢纽）
        connect 'EDP-001'.'pressure_out' to 'PF-001'.'inlet';

        // @MANIFOLD -> PRV-001 供流（端口枢纽接显式端口）；走向待工程确认
        connect 'PF-001'.'outlet' to 'PRV-001'.'inlet';

        // @USR 端口枢纽辐条: 用户挂 PRV-001 出口母线
        connect 'PRV-001'.'outlet' to 'USER-001'.'pressure_in';

        // 回油: 用户回油与壳体回油汇入 @RET（端口枢纽）
        connect 'USER-001'.'return_out' to 'TANK-001'.'return_in';
        connect 'EDP-001'.'case_drain' to 'CDF-001'.'inlet';
        connect 'CDF-001'.'outlet' to 'TANK-001'.'return_in';

        // 传感支路: 压力开关挂壳体回油滤入口（归 taps，不入 paths）
        connect 'SW-001'.'pressure_sense' to 'CDF-001'.'inlet';
    }
}
