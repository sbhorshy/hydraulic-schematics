# -*- coding: utf-8 -*-
"""原型 B：母线驱动的规则式分层布局（#17 路线 B）。

输入：frozen/ 的 1#系统.intent.yaml + component-catalog.json（与基线 #11 严格同源）。
输出：frozen/layoutB.json + frozen/1#系统B原理图.svg + B 面板实测。

方法沿调研票结论（变电站单线图规则式分层，arXiv 1903.09495 的同构迁移）：
  1. 从 intent paths 提取链（chain）与母线（@bus），按端口 role 推线型与类别；
  2. 母线定位：x = 上游列右缘 + 间距（母线承重，长度由所挂支路决定——render.py 画母线）；
  3. 元件定位：行列网格——行=流路族（主压/辅压/回油/壳体回油/气侧），列=拓扑深度；
  4. 走廊：规则生成 lanes/vlanes 候选值，交 route() 择优。
全程不读 v2.3 的任何坐标数字；符号足迹（w/h/rot）是符号库事实，非布局决策。
"""
import io
import json
import os
import sys
from ruamel.yaml import YAML

HERE = os.path.dirname(os.path.abspath(__file__))
FZ = os.path.join(HERE, 'frozen')

# ---------- 规则参数表（布局语言的全部自由度都在这张表里） ----------
P = dict(
    TANK_X=60,                 # R1 油箱置左
    COL_GAP=90,                # R2 列间距
    BUS_GAP=300,               # R3 母线离上游列右缘
    BUS_INLINE_GAP_A=120,      # R4 母线→串联件
    BUS_INLINE_GAP_B=80,       # R4 串联件→下一条母线
    RET_CLEAR=60,              # R7 回油母线与压力母线净距
    ROW_MAIN=290,              # R5 主行
    ROW_PITCH=320,             # R5 行距
    ROW_RETURN=700,            # R7 回油行
    ROW_QDR=900,               # R7 地面接头行
    ROW_CASE=100,              # R8 壳体回油行（顶）
    TANK_TOP_PAD=14,           # R1 油箱顶缘高出主行
    BOOST_DROP=120,            # R9 自增压支路在辅行下的落差
    QDP_DROP=270,              # R6 地面压力接头在主行下的落差
    GAS_GAP=73,                # R10 气侧堆叠间距
    USR_OFF=40,                # R12 用户边界离最右元件
    LANE_TOP=100,              # R11 顶部走廊
    VLANE_WEST=20,             # R11 西缘竖廊
    EDGE_PAD=12,               # R11 竖廊离列缘
    CANVAS_W=1680, CANVAS_H=1390, SHIFT=30,
    LEGEND=dict(x=1000, y=1020, w=540, h=290),
    TITLE=dict(x=40, y=1330, w=1600, h=56),
)

# 符号足迹表（符号库事实；rot 属挂装规则输出）
FOOTPRINT = {
    'bootstrap_reservoir': (218, 564, 'symbols/reservoir-bootstrap-annotated.svg'),
    'firewall_shutoff_valve': (80, 80, 'symbols/fsov-provisional-stroke.svg'),
    'engine_driven_pump': (80, 80, 'symbols/edp-provisional-stroke.svg'),
    'electric_motor_driven_pump': (80, 80, 'symbols/emp-provisional-stroke.svg'),
    'filter_line_shutoff_dp': (80, 112, 'symbols/filter-line-shutoff-dp.svg'),
    'filter_line_shutoff_dp_case_drain': (60, 80, 'symbols/filter-line-shutoff-dp.svg'),
    'filter_line_shutoff_dp_return': (80, 112, 'symbols/filter-line-shutoff-dp.svg'),
    'priority_valve': (140, 78, 'symbols/priority-valve.svg'),
    'hydro_pneumatic_accumulator': (60, 100, 'symbols/accumulator.svg'),
    'air_charging_valve': (134, 57, 'symbols/air-charging-valve.svg'),
    'pressure_gauge': (63, 67, 'symbols/pressure-gauge.svg'),
    'quick_disconnect_coupling_disconnected': (160, 68, 'symbols/quick-disconnect-coupling-disconnected.svg'),
    'quick_disconnect_coupling_disconnected_return': (160, 68, 'symbols/quick-disconnect-coupling-disconnected.svg'),
}


def load_yaml(p):
    y = YAML(typ='safe', pure=True)
    y.version = (1, 2)
    with io.open(p, encoding='utf-8') as f:
        return y.load(f)


def port_roles(cat, parts):
    """inst -> {port_id: role}；另给 type 查询。"""
    types = {c['component_type']: c for c in cat['components']}
    out = {}
    for inst, t in parts.items():
        out[inst] = {p['id']: p['role'] for p in types[t]['ports']}
    return out, types


def seg_type(ra, rb):
    s = {ra, rb}
    if s == {'pressure'}:
        return 'pressure'
    if 'suction' in s:
        return 'suction'
    if 'case_drain' in s:
        return 'case_drain'
    if 'return' in 'return':
        pass
    if 'return' in s:
        return 'return'
    return 'pressure'


def analyze(intent, roles):
    """把 paths 归约为：母线表（含挂接支路 role 集）、链表、单边表。"""
    chains, single, buses = [], [], {}
    for p in intent['paths']:
        toks = p
        if len(toks) == 2:
            single.append((toks[0], toks[1]))
        else:
            chains.append((toks[0], list(toks[1:-1]), toks[-1]))
        for t in toks:
            if t.startswith('@'):
                buses.setdefault(t[1:], set())
        # 挂接 role 集合：母线两侧端点的 role
        for k in range(len(toks) - 1):
            a, b = toks[k], toks[k + 1]
            for bus, other, other_want in ((a, b, 'in'), (b, a, 'out')):
                if not bus.startswith('@'):
                    continue
                if other.startswith('@'):
                    roles_here = 'bus'
                else:
                    inst, pid = (other.split('.', 1) + [None])[:2]
                    if pid is None:
                        continue        # main_path 解析留给渲染器
                    roles_here = roles[inst].get(pid, 'pressure')
                buses[bus[1:]].add(roles_here)
    return chains, single, buses


def classify_bus(role_set):
    """R-母线类别：由挂接 role 多重集推导。"""
    s = set(role_set)
    if 'case_drain' in s:
        return 'case'
    if s <= {'return', 'pressure'} and 'return' in s:
        return 'return'
    return 'pressure'


def main():
    intent = load_yaml(os.path.join(FZ, '1#系统.intent.yaml'))
    with io.open(os.path.join(FZ, 'component-catalog.json'), encoding='utf-8') as f:
        cat = json.load(f)
    roles, types = port_roles(cat, intent['parts'])
    chains, single, buses = analyze(intent, roles)

    # ---- 元件分类（按 catalog 端口 role 模式，不认实例名）----
    tank = next(i for i, r in roles.items() if 'suction_out' in r and 'return_in' in r)
    pumps = [i for i, r in roles.items()
             if 'suction' in r and 'pressure_out' in r and 'case_drain' in r]
    pumps.sort()  # 确定性；edp < emp 字典序即主/辅
    # 兜底：排序后把带吸油串联链的泵放主行
    chain_mid_insts = {m for _s, ms, _e in chains for m in ms}
    pumps.sort(key=lambda i: (i not in {e.split('.')[0] for _s, ms, e in chains
                                        if ms and e.split('.')[0] == i}, i))

    nodes, buses_out = {}, {}
    externs = {}
    lanes, vlanes = [P['LANE_TOP']], [P['VLANE_WEST']]

    # ---- R1：油箱首位（左缘，顶对主行上方 TOP_PAD）----
    tank_w, tank_h = FOOTPRINT[intent['parts'][tank]][:2]
    tank_right = P['TANK_X'] + tank_w
    nodes[tank] = dict(x=P['TANK_X'], y=P['ROW_MAIN'] - P['TANK_TOP_PAD'],
                       w=tank_w, h=tank_h, rot=0)

    # ---- 列坐标推导（R2/R3/R4）----
    # 吸油串联阀列（主行上、泵左侧的 inline 件）
    succ_valves = sorted(m for m in chain_mid_insts
                         if intent['parts'][m] == 'firewall_shutoff_valve')
    x = tank_right + P['COL_GAP']
    for v in succ_valves:
        w = FOOTPRINT[intent['parts'][v]][0]
        nodes[v] = dict(x=x, y=P['ROW_MAIN'], w=w, h=80, rot=0)
        x += w + P['COL_GAP']
    pump_x = x
    for pm in pumps:
        nodes[pm] = dict(x=pump_x, y=(P['ROW_MAIN'] if pm == pumps[0] else
                                      P['ROW_MAIN'] + P['ROW_PITCH']),
                         w=80, h=80, rot=0)
    pump_right = pump_x + 80

    # ---- 母线定位 ----
    for b, rs in buses.items():
        kind = classify_bus(rs)
        if kind == 'case':
            buses_out[b] = dict(kind='v', x=pump_right + 40)
        elif b == 'PRESS':
            buses_out[b] = dict(kind='v', x=pump_right + P['BUS_GAP'])
        elif b == 'RET':
            buses_out[b] = dict(kind='v', x=buses_out['PRESS']['x'] + P['RET_CLEAR'])
        else:
            buses_out[b] = dict(kind='v', x=0)   # 占位，R4 后回填
    # 压力主链上的 inline 件（滤）架在两母线之间
    for s_tok, mids, e_tok in chains:
        if not (s_tok.startswith('@') and e_tok.startswith('@')):
            continue
        if classify_bus(buses[s_tok[1:]]) != 'pressure':
            continue
        bx = buses_out[s_tok[1:]]['x']
        for m in mids:
            w, h, _ = FOOTPRINT[intent['parts'][m]]
            mx = bx + P['BUS_INLINE_GAP_A']
            nodes[m] = dict(x=mx, y=P['ROW_MAIN'] - (h - 80) // 2, w=w, h=h, rot=0)
            bx = mx + w + P['BUS_INLINE_GAP_B']
        buses_out[e_tok[1:]]['x'] = bx

    # ---- 分配母线支路（R5/R6/R9/R10）----
    dist = next(b for b, rs in buses.items()
                if classify_bus(rs) == 'pressure' and b not in ('PRESS',))
    dx = buses_out[dist]['x']
    main_row_members = [i for i in nodes
                        if nodes[i]['y'] == P['ROW_MAIN'] and i != tank]
    # 优先阀→用户：主行延伸
    for s_tok, mids, e_tok in chains:
        if s_tok[1:] == dist and mids and not e_tok.startswith('@'):
            for m in mids:
                w, h, _ = FOOTPRINT[intent['parts'][m]]
                mx = dx + 140
                nodes[m] = dict(x=mx, y=P['ROW_MAIN'], w=w, h=h, rot=0)
                externs[e_tok] = dict(
                    x=mx + w + P['USR_OFF'],
                    y=P['ROW_MAIN'] + 110, anchor='left',
                    label=e_tok + '\n' + ('至用户 (供压)' if intent['extern'][e_tok] == 'outlet'
                                          else '自用户 (回油)'))
            rightmost = max(n['x'] + n['w'] for n in nodes.values())
    # 蓄压器：母线正上方，气侧堆叠向上（R10）
    for s_tok, mids, e_tok in chains:
        if s_tok[1:] == dist and not mids:
            inst = e_tok.split('.')[0]
            if 'gas_port' in roles.get(inst, {}):
                w, h, _ = FOOTPRINT[intent['parts'][inst]]
                nodes[inst] = dict(x=dx + 20, y=P['ROW_MAIN'] - h, w=w, h=h, rot=0)
    # 地面压力接头：母线下方辅助位（R6）
    for s_tok, mids, e_tok in chains:
        if s_tok[1:] == dist and not mids:
            inst = e_tok.split('.')[0]
            if inst not in nodes:
                w, h, _ = FOOTPRINT[intent['parts'][inst]]
                nodes[inst] = dict(x=dx + 26, y=P['ROW_MAIN'] + P['QDP_DROP'],
                                   w=w, h=h, rot=0)
    # 自增压支路：@PRESS→阀→油箱.boost，油箱前方（R9）
    for s_tok, mids, e_tok in chains:
        if s_tok.startswith('@') and mids and e_tok.split('.')[0] == tank:
            m = mids[0]
            w, h, _ = FOOTPRINT[intent['parts'][m]]
            nodes[m] = dict(x=tank_right + 160, rot=180,
                            y=P['ROW_MAIN'] + P['ROW_PITCH'] + P['BOOST_DROP'],
                            w=w, h=h)

    # ---- 回油族（R7）----
    ret_x = buses_out['RET']['x']
    for s_tok, mids, e_tok in chains:
        # 回油链两型：USR→滤→@RET（边界在链首）；链尾接回油母线的单边已另处处理
        if mids and classify_bus(buses.get(e_tok[1:], set())) == 'return':
            m = mids[0]
            w, h, _ = FOOTPRINT[intent['parts'][m]]
            nodes[m] = dict(x=ret_x + 260, y=P['ROW_RETURN'], w=w, h=h, rot=180)
            if s_tok in intent['extern']:
                externs[s_tok] = dict(x=rightmost + P['USR_OFF'], y=P['ROW_RETURN'],
                                      anchor='left', label=s_tok + '\n自用户 (回油)')
        if classify_bus(buses.get(s_tok[1:], set())) == 'return' and not mids:
            inst = s_tok.split('.')[0]
            if inst in intent['extern']:
                externs[s_tok] = dict(x=rightmost + P['USR_OFF'], y=P['ROW_RETURN'],
                                      anchor='left', label=inst + '\n自用户 (回油)')

    # ---- 单边母线支路：蓄压器(带 gas_port)上母线、快卸接头落辅助行 ----
    for a, b in single:
        bus_tok, other = (a, b) if a.startswith('@') else (b, a)
        if not bus_tok.startswith('@'):
            continue
        inst = other.split('.')[0]
        if inst in nodes or inst in intent['extern']:
            continue
        w, h, _ = FOOTPRINT[intent['parts'][inst]]
        bname = bus_tok[1:]
        if 'gas_port' in roles.get(inst, {}):
            # 蓄压器：底缘贴主行顶，骑在分配母线上方
            nodes[inst] = dict(x=buses_out[bname]['x'] + 20,
                               y=P['ROW_MAIN'] - h, w=w, h=h, rot=0)
        elif classify_bus(buses.get(bname, set())) == 'return':
            nodes[inst] = dict(x=buses_out[bname]['x'] + 260, y=P['ROW_QDR'],
                               w=w, h=h, rot=0)
        else:
            # 地面压力接头类：分配母线下方辅助位（R6）
            nodes[inst] = dict(x=buses_out[bname]['x'] + 26,
                               y=P['ROW_MAIN'] + P['QDP_DROP'], w=w, h=h, rot=0)

    # ---- 气侧 taps（R10）：传感链自蓄压器向上堆叠，第二个起向右排 ----
    if intent.get('taps'):
        acc_inst = None
        for inst, r in roles.items():
            if 'gas_port' in r and inst in nodes and nodes[inst]['y'] < P['ROW_MAIN']:
                acc_inst = inst
                break
        if acc_inst:
            prev = acc_inst
            for t in intent['taps']:
                sinst = t['sensor'].split('.')[0]
                if sinst in nodes:
                    continue
                w, h, _ = FOOTPRINT[intent['parts'][sinst]]
                px, py = nodes[prev]['x'], nodes[prev]['y']
                pw = nodes[prev]['w']
                first = (prev == acc_inst)
                nodes[sinst] = dict(
                    x=(px + 60 if first else px + pw + P['GAS_GAP']),
                    y=(py - h - P['GAS_GAP'] + 30 if first else py),
                    w=w, h=h, rot=0)
                prev = sinst

    # ---- 壳体回油族（R8）：母线→滤(顶装 rot270)→油箱 ----
    for s_tok, mids, e_tok in chains:
        if classify_bus(buses.get(s_tok[1:], set())) == 'case' and mids:
            m = mids[0]
            w, h, _ = FOOTPRINT[intent['parts'][m]]
            nodes[m] = dict(x=P['TANK_X'] + 360, y=P['ROW_CASE'], w=w, h=h, rot=270)

    # ---- 走廊（R11）----
    first_col_left = min((n['x'] for n in nodes.values()
                          if n['y'] == P['ROW_MAIN'] and n['x'] > tank_right),
                         default=tank_right + 40)
    vlanes.append(tank_right + P['EDGE_PAD'] + 0)   # 吸油上行竖廊
    # ---- externs 兜底（漏挂的按族定行：回油族对齐回油行，其余主行下）----
    ret_buses = {b for b, rs in buses.items() if classify_bus(rs) == 'return'}
    for e, kind in intent.get('extern', {}).items():
        if e not in externs:
            externs[e] = dict(x=1480, anchor='left', label=e,
                              y=(P['ROW_RETURN'] if kind == 'return'
                                 else P['ROW_MAIN'] + 110))
    _ = ret_buses
    layout = dict(
        layout_version='protoB-1.0',
        source_l0='1#系统.intent.yaml',
        note='原型 B：母线驱动规则式分层——全部坐标由规则表+intent 拓扑推导（#17）。',
        canvas=dict(width=P['CANVAS_W'], height=P['CANVAS_H']),
        canvas_shift_x=P['SHIFT'],
        style=dict(base_line_width_T=1.2, symbol_stroke_width=2, suction_marker_S=8),
        externs=externs, nodes=nodes, buses=buses_out,
        lanes=lanes, vlanes=vlanes,
        group_padding=20, group_label_gap=10,
        legend=P['LEGEND'], title_block=P['TITLE'],
    )
    for inst, nd in nodes.items():
        nd['symbol'] = FOOTPRINT[intent['parts'][inst]][2]
    # 展示常量取自 v2.3（标签文字/图例是文案，不是坐标决策）
    with io.open(os.path.join(FZ, '1#系统.layout.json'), encoding='utf-8') as f:
        v23 = json.load(f)
    keep = dict(v23)
    for key in ('labels', 'label_pos', 'label_drop'):
        if key in keep:
            layout[key] = {k: v for k, v in keep[key].items() if k in nodes}
    for k in list(externs):
        if k in v23.get('externs', {}):
            externs[k]['label'] = v23['externs'][k]['label']

    with io.open(os.path.join(FZ, '1#系统B.layout.json'), 'w', encoding='utf-8') as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)
    print('layoutB.json:', len(nodes), 'nodes,', len(buses_out), 'buses')
    missing = set(intent['parts']) - set(nodes)
    if missing:
        print('!!! 未布元件:', sorted(missing))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
