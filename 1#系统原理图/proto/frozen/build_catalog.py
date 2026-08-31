# -*- coding: utf-8 -*-
"""以 skill 快照 catalog(0.2-draft)为基础,生成 1#系统原理图 工作目录的
扩展目录 0.3-draft:补 8 个新类型 + 5 个既有类型指向本目录已标注符号副本。
"""
import json
import io

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
    'firewall_shutoff_valve': ('fsov-provisional-stroke.svg', 'provisional',
                               '本工作目录副本已带 connection-points(描边 provisional,无标准页)。'),
    'hydro_pneumatic_accumulator': ('accumulator.svg', 'annotated',
                                    '重描绘边件,端口标注齐全;旧"两处 port-pressure-in 重 id"缺陷已随重绘消除。'),
    'bootstrap_reservoir': ('reservoir-bootstrap-annotated.svg', 'annotated',
                            'draft 级描边(数据源 USER_ANNOTATED);门禁 C8 报 data-symbol-form=traced_outline,'
                            '属符号重绘运动待办早期符号。本图按 CONCEPT 档使用并在图签披露。'),
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
     'description': '1#系统组件清单"filter-line-shutoff-dp(压力油滤)"。压差指示器占符号上半,布局占位须按 80x112。',
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
]

have = {c['component_type'] for c in cat['components']}
added = 0
for e in new_entries:
    if e['component_type'] in have:
        raise SystemExit('类型已存在: ' + e['component_type'])
    cat['components'].append(e)
    added += 1

with io.open(WORK, 'w', encoding='utf-8') as f:
    json.dump(cat, f, ensure_ascii=False, indent=2)
    f.write('\n')
print('catalog 0.3-draft: 新增 %d 类型,共 %d' % (added, len(cat['components'])))
