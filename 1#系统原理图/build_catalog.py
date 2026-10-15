# -*- coding: utf-8 -*-
"""以 skill 快照 catalog(0.2-draft)为基础,生成 1#系统原理图 工作目录的
扩展目录 0.3-draft:补 8 个新类型 + 5 个既有类型指向本目录已标注符号副本。
"""
import json
import io

# This legacy generator writes a hard-coded Windows worktree. Keep it
# fail-closed until #48 supplies the supported catalog generation entry.
raise SystemExit("旧项目目录生成器已停用（#49 防回退）；请使用现有目录和规范源 validate_driver.py。生成器重构见 #48。")

BASE = r'D:/File/COMAC/组件库/.agents/skills/hydraulic-schematic/assets/component-library/component-catalog.json'
WORK = r'D:/File/COMAC/组件库/1#系统原理图/component-catalog.json'
SYMDIR = 'symbols/'

with io.open(BASE, encoding='utf-8') as f:
    cat = json.load(f)

cat['catalog_revision'] = '0.3-draft'
types = {c['component_type']: c for c in cat['components']}

updates = {
    'engine_driven_pump': ('edp-provisional-stroke.svg', 'provisional',
                           '本工作目录副本已带 connection-points(描边 provisional,无标准页)。'),
    'electric_motor_driven_pump': ('emp-provisional-stroke.svg', 'provisional',
                                   '本工作目录副本已带 connection-points(描边 provisional)。'),
    'firewall_shutoff_valve': ('firewall-shutoff-valve.svg', 'annotated',
                               'CAD 转换(Drawing2.dxf)v1.4 副本,2026-09-07 替换 provisional 描边;'
                               '两口 main_upper/main_lower 双向,ports/main_path 继承规范源。'),
    'hydro_pneumatic_accumulator': ('accumulator.svg', 'annotated',
                                    '重描绘边件,端口标注齐全;旧"两处 port-pressure-in 重 id"缺陷已随重绘消除。'),
    'bootstrap_reservoir': ('bootstrap-type-reservoir.svg', 'draft',
                            '规范源描边油箱受管副本;见 symbols/README.md;不得回写退役资产。'),
    # skill 更新后快照收录 hydraulic_user(0.1-draft);资产路径改指本目录副本。
    'hydraulic_user': ('hydraulic-user.svg', 'provisional',
                       '通用用户名框(data-name-slot),实例名由渲染器写入名槽;'
                       '门禁 C11/C12:provisional 无标准页,引用它的 L0 文件须在 unknown 登记。'),
}
for t, (asset, st, note) in updates.items():
    types[t]['symbol'] = {'asset': SYMDIR + asset, 'symbol_status': st, 'note': note}


def port(pid, seid, medium, role, flow, anchor, note=None):
    d = {'id': pid, 'svg_element_id': seid, 'medium': medium, 'role': role,
         'flow_capability': flow, 'anchor_direction': anchor}
    if note:
        d['role_note'] = note
    return d


new_entries = [
    # ---- 油滤三变体,共用 filter-line-shutoff-dp.svg(区别在 port role 与安装位置,
    #      沿用 pressure_filter/return_filter/case_drain_filter 共用 Filter.svg 的既有先例)----
    {'component_type': 'filter_line_shutoff_dp',
     'display_name': '压力油滤(线端关断+压差指示)',
     'description': '1#系统组件清单"filter-line-shutoff-dp(压力油滤)"。压差指示器占符号上半,布局占位须按 80x158。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'filter-line-shutoff-dp.svg', 'symbol_status': 'annotated',
                'note': 'draft;符号注释含未确认项(无标准页 clause-6.1.6 构型),已登记 intent unknown。'},
     'ports': [port('inlet', 'port-inlet', 'hydraulic', 'pressure', 'in', 'left'),
               port('outlet', 'port-outlet', 'hydraulic', 'pressure', 'out', 'right')],
     'main_path': {'in': 'inlet', 'out': 'outlet'},
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    {'component_type': 'filter_line_shutoff_dp_return',
     'display_name': '回油滤(线端关断+压差指示)',
     'description': '1#系统组件清单"filter-line-shutoff-dp(回油滤)"。与压力油滤共用符号,区别在 port role=return(沿用回油滤共用滤符号先例)。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'filter-line-shutoff-dp.svg', 'symbol_status': 'annotated',
                'note': '与 filter_line_shutoff_dp 共用同一符号文件;本类型把端口 role 定为 return。'},
     'ports': [port('inlet', 'port-inlet', 'hydraulic', 'return', 'in', 'left'),
               port('outlet', 'port-outlet', 'hydraulic', 'return', 'out', 'right')],
     'main_path': {'in': 'inlet', 'out': 'outlet'},
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    {'component_type': 'filter_line_shutoff_dp_case_drain',
     'display_name': '壳体回油滤(线端关断+压差指示)',
     'description': '1#系统组件清单"filter-line-shutoff-dp(壳体回油滤)"。与压力油滤共用符号,port role=case_drain。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'filter-line-shutoff-dp.svg', 'symbol_status': 'annotated',
                'note': '与 filter_line_shutoff_dp 共用同一符号文件;本类型把端口 role 定为 case_drain。'},
     'ports': [port('inlet', 'port-inlet', 'hydraulic', 'case_drain', 'in', 'left'),
               port('outlet', 'port-outlet', 'hydraulic', 'case_drain', 'out', 'right')],
     'main_path': {'in': 'inlet', 'out': 'outlet'},
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    # ---- 快卸接头两变体,共用 quick-disconnect-coupling-disconnected.svg ----
    {'component_type': 'quick_disconnect_coupling_disconnected',
     'display_name': '地面压力快卸接头(断开位)',
     'description': '1#系统组件清单"quick-disconnect-coupling-disconnected(地面压力快卸接头)"。断开位:机侧接通、地面侧开放,出图呈悬空端口红圈。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'quick-disconnect-coupling-disconnected.svg', 'symbol_status': 'annotated',
                'note': 'provisional;符号注释"端口语义待工程确认"已登记 intent unknown。'},
     'ports': [port('inlet', 'port-inlet', 'hydraulic', 'pressure', 'in', 'left',
                    '机侧,接压力总管支路。'),
               port('outlet', 'port-outlet', 'hydraulic', 'pressure', 'out', 'right',
                    '地面侧,断开位开放。')],
     'main_path': {'in': 'inlet', 'out': 'outlet'},
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    {'component_type': 'quick_disconnect_coupling_disconnected_return',
     'display_name': '地面回油快卸接头(断开位)',
     'description': '1#系统组件清单"quick-disconnect-coupling-disconnected(地面回油快卸接头)"。与压力快卸接头共用符号,port role=return 使支路线宽归低压级。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'quick-disconnect-coupling-disconnected.svg', 'symbol_status': 'annotated',
                'note': '与 quick_disconnect_coupling_disconnected 共用同一符号文件;本类型端口 role 定为 return。'},
     'ports': [port('inlet', 'port-inlet', 'hydraulic', 'return', 'in', 'left',
                    '机侧,接回油总管支路。'),
               port('outlet', 'port-outlet', 'hydraulic', 'return', 'out', 'right',
                    '地面侧,断开位开放。')],
     'main_path': {'in': 'inlet', 'out': 'outlet'},
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    # ---- 优先阀(两实例共用本类型)----
    {'component_type': 'priority_valve',
     'display_name': '优先阀',
     'description': '1#系统组件清单"priority-valve(优先阀)"与"priority-valve(自增压优先阀)"共用本类型。'
                    '符号内含主路单向阀与下旁路单向阀,两者流向 PENDING_ENGINEER_CONFIRMATION(符号注释),已登记 intent unknown。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'priority-valve.svg', 'symbol_status': 'annotated',
                'note': 'draft;端口标注 v0.3 升级为现行属性约定(id 改语义名 inlet/outlet,引线延至 viewBox 边界)。'},
     'ports': [port('inlet', 'port-inlet-anchor', 'hydraulic', 'pressure', 'in', 'left'),
               port('outlet', 'port-outlet-anchor', 'hydraulic', 'pressure', 'out', 'right')],
     'main_path': {'in': 'inlet', 'out': 'outlet'},
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    # ---- 充气活门 ----
    {'component_type': 'air_charging_valve',
     'display_name': '蓄压器充气活门',
     'description': '1#系统组件清单"air-charging-valve & pressure-gauge(蓄压器充气压力表组件)"的活门件。'
                    '气侧件,medium=pneumatic,不得串入液压 paths,经 taps 挂接蓄压器 gas_port。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'air-charging-valve.svg', 'symbol_status': 'annotated',
                'note': 'draft;端口标注 v0.3 升级为现行属性约定(左端口圆原偏离接口线,已随引线延至边界一并修正)。'},
     'ports': [port('accumulator_gas', 'port-accumulator-gas-anchor', 'pneumatic', 'gas', 'bidirectional', 'left',
                    '按符号形位判读:左侧接蓄压器 gas_port;左右分配未经标准页确认,见 intent unknown。'),
               port('charge_port', 'port-charge-anchor', 'pneumatic', 'gas', 'bidirectional', 'right',
                    '充气源/量表接口侧,断开位开放。')],
     'main_path': None,
     'main_path_note': '气侧件不入液压 paths;挂接关系经 taps 声明(预检处方"气侧走 taps 或专线")。',
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    # ---- 充气压力表 ----
    {'component_type': 'pressure_gauge',
     'display_name': '蓄压器充气压力表',
     'description': '1#系统组件清单"air-charging-valve & pressure-gauge(蓄压器充气压力表组件)"的表件。'
                    'sensing_only,经 taps 挂接;medium=pneumatic 按"测蓄压器气侧压力"用途判定(符号 v1.2 注释)。',
     'connection_role': 'sensing_only',
     'symbol': {'asset': SYMDIR + 'pressure-gauge.svg', 'symbol_status': 'annotated',
                'note': 'draft;v1.2 引线延至 viewBox 下边界并改 medium=pneumatic。'},
     'ports': [port('pressure_sense', 'port-pressure-sense', 'pneumatic', 'measurement', 'none', 'down')],
     'main_path': None,
     'main_path_note': 'sensing_only 禁止入 paths;经 taps 声明。',
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
    # ---- 集中加油单向阀(2026-09-07 落位:回油滤前支路)----
    #      与 check_valve 共用 check-valve.svg,role 按回油路取 return(线型走回油细线),
    #      沿用油滤三变体共用符号先例。
    {'component_type': 'check_valve_refuel',
     'display_name': '集中加油单向阀',
     'description': '集中加油支路隔离单向阀。与 check_valve 共用 check-valve.svg,role=return。',
     'connection_role': 'inline',
     'symbol': {'asset': SYMDIR + 'check-valve.svg', 'symbol_status': 'annotated',
                'note': '与 check_valve 共用同一符号文件;本类型 role 定为 return。'},
     'ports': [port('inlet', 'port-inlet', 'hydraulic', 'return', 'in', 'right'),
               port('outlet', 'port-outlet', 'hydraulic', 'return', 'out', 'left')],
     'main_path': {'in': 'inlet', 'out': 'outlet'},
     'layout': {'allowed_rotations_deg': [0, 90, 180, 270], 'allow_mirror': False}},
]

have = {c['component_type'] for c in cat['components']}
added = 0
skipped = []
for e in new_entries:
    # #21 回登记后规范源已含 22 类型:重复项跳过而非报错,脚本改为可重跑的幂等覆盖。
    if e['component_type'] in have:
        skipped.append(e['component_type'])
        continue
    cat['components'].append(e)
    added += 1

with io.open(WORK, 'w', encoding='utf-8') as f:
    json.dump(cat, f, ensure_ascii=False, indent=2)
    f.write('\n')
print('catalog 0.3-draft: 新增 %d 类型,跳过已存在 %d,共 %d'
      % (added, len(skipped), len(cat['components'])))
