# -*- coding: utf-8 -*-
"""原型 A：kiwisolver 声明式约束布局（#17 路线 A）。

与原型 B 共用同一张约定参数表（proto_b_rules.P + FOOTPRINT，符号足迹为库事实），
差别只在"坐标怎么来"：本文件**不计算任何坐标**，只向 Cassowary/Kiwi 求解器声明——
  REQUIRED：画布/图例回避、B5 盒距、母线次序与净距、行列对齐、支路挂接几何；
  弱约束：各行/列的偏好锚点（约定表 P 的值）。
坐标是求解器的输出。改参数只改声明，一致性由求解器保证（这是与规则式的本质差异）。
"""
import io
import json
import os
import sys

from kiwisolver import Solver, Variable
from kiwisolver import strength as _st
strong, weak = _st.strong, _st.weak

import proto_b_rules as conv

HERE = os.path.dirname(os.path.abspath(__file__))
FZ = os.path.join(HERE, 'frozen')
P, FOOTPRINT = conv.P, conv.FOOTPRINT


def main():
    intent = conv.load_yaml(os.path.join(FZ, '1#系统.intent.yaml'))
    with io.open(os.path.join(FZ, 'component-catalog.json'), encoding='utf-8') as f:
        cat = json.load(f)
    roles, types = conv.port_roles(cat, intent['parts'])
    chains, single, buses = conv.analyze(intent, roles)

    parts = intent['parts']
    V = {inst: (Variable(inst + '.x'), Variable(inst + '.y'))
         for inst in parts}
    B = {b: Variable('bus.' + b + '.x') for b in buses}
    s = Solver()

    def w(inst):
        return FOOTPRINT[parts[inst]][0]

    def h(inst):
        return FOOTPRINT[parts[inst]][1]

    def add(c):
        s.addConstraint(c)

    def at(inst, x=None, y=None, strength=weak):
        """偏好锚点：声明"这一维想在哪"。"""
        if x is not None:
            add((V[inst][0] == x) | strength)
        if y is not None:
            add((V[inst][1] == y) | strength)

    # ---------- 识别（与 B 同一分类器）----------
    tank = next(i for i, r in roles.items() if 'suction_out' in r and 'return_in' in r)
    pumps = sorted(i for i, r in roles.items()
                   if 'suction' in r and 'pressure_out' in r and 'case_drain' in r)
    chain_mids = {m for _s, ms, _e in chains for m in ms}
    pumps.sort(key=lambda i: (i not in {e.split('.')[0] for _s, ms, e in chains
                                        if ms and e.split('.')[0] == i}, i))
    succ_valves = sorted(m for m in chain_mids
                         if parts[m] == 'firewall_shutoff_valve')
    edp, emp = pumps[0], pumps[1]
    fsov = succ_valves[0]
    pf = next(m for _s, ms, _e in chains
              if _s == '@PRESS' and _e == '@MANIFOLD' for m in ms)
    prv1 = next(m for _s, ms, _e in chains
                if _s == '@MANIFOLD' and ms and not _e.startswith('@') for m in ms)
    prv2 = next(m for _s, ms, _e in chains
                if _s.startswith('@') and ms and _e.split('.')[0] == tank for m in ms)
    rf = next(m for _s, ms, _e in chains
              if not _s.startswith('@') and ms and _e == '@RET' for m in ms)
    cdf = next(m for _s, ms, _e in chains
               if _s.startswith('@') and conv.classify_bus(buses[_s[1:]]) == 'case'
               for m in ms)
    def leaf_on(bus_name, exclude=()):
        """单边支路：某母线上挂着、且带显式端口的叶子元件（排除油箱）。"""
        for a, b in single:
            bus_tok, other = (a, b) if a.startswith('@') else (b, a)
            if not bus_tok.startswith('@') or bus_tok[1:] != bus_name:
                continue
            if other.startswith('@') or '.' not in other:
                continue
            inst = other.split('.')[0]
            if inst not in exclude:
                return inst
        return None

    acc = next(i for i in [leaf_on('MANIFOLD', exclude=(tank,))]
               if i and 'gas_port' in roles[i])
    qdp = leaf_on('MANIFOLD', exclude=(tank, acc))
    qdr = leaf_on('RET', exclude=(tank,))

    # ---------- REQUIRED：画布与图例回避 ----------
    for inst in parts:
        x, y = V[inst]
        add(x >= 60)
        add(x + w(inst) <= P['CANVAS_W'] - 30)
        add(y >= 60)
        add(y + h(inst) <= P['LEGEND']['y'] - 10)   # 图例上缘净空

    # ---------- REQUIRED：主行/辅行对齐与次序 ----------
    add(V[fsov][0] == V[edp][0] * 0 + V[fsov][0])          # 占位无关式，保持可读
    add(V[fsov][1] == V[edp][1])
    add(V[pf][1] == V[edp][1] - (h(pf) - 80) / 2)
    add(V[prv1][1] == V[edp][1])
    add(V[emp][0] == V[edp][0])
    add(V[edp][1] + h(edp) + 40 <= V[emp][1])              # B5 纵向
    add(V[tank][0] + w(tank) + 40 <= V[fsov][0])
    add(V[fsov][0] + w(fsov) + 40 <= V[edp][0])
    add(V[tank][1] + P['TANK_TOP_PAD'] <= V[edp][1])       # 油箱罩住主行

    # ---------- REQUIRED：母线次序与挂接净距 ----------
    add(V[edp][0] + w(edp) + 40 <= B['CASE'])  # 40=18引出桩+8最短段+5桥半径+裕量
    add(B['CASE'] + 120 <= B['PRESS'])
    add(V[edp][0] + w(edp) + 100 <= B['PRESS'])
    add(B['PRESS'] + P['BUS_INLINE_GAP_A'] <= V[pf][0])
    add(V[pf][0] + w(pf) + P['BUS_INLINE_GAP_B'] <= B['MANIFOLD'])
    add(B['PRESS'] + P['RET_CLEAR'] <= B['RET'])
    add(B['MANIFOLD'] + 60 <= V[prv1][0])
    add(V[prv1][0] + w(prv1) + 20 <= 1480)                  # 用户缘
    add(V[acc][1] + h(acc) <= V[edp][1])                    # 蓄压器在主行上方
    add(B['MANIFOLD'] - 60 <= V[acc][0] + w(acc) / 2)
    add(V[acc][0] + w(acc) / 2 <= B['MANIFOLD'] + 60)
    add(V[acc][1] >= 60)
    # 气侧堆叠：ACV 在 ACC 上方，PG 在 ACV 右侧同行
    acv = next(t['sensor'].split('.')[0] for t in intent['taps']
               if t['at'].split('.')[0] == acc)
    pg = next(t['sensor'].split('.')[0] for t in intent['taps']
              if t['at'].split('.')[0] == acv)
    add(V[acv][1] + h(acv) + 20 <= V[acc][1])
    add(B['MANIFOLD'] - 120 <= V[acv][0] + w(acv) / 2)
    add(V[acv][0] + w(acv) / 2 <= B['MANIFOLD'] + 120)
    add(V[pg][1] == V[acv][1])
    add(V[acv][0] + w(acv) + 20 <= V[pg][0])
    add(V[pg][0] + w(pg) <= P['CANVAS_W'] - 30)
    # 地面接头：QDP 骑 MANIFOLD、在两行之间；QDR 对 RET、在回油行下方
    add(V[edp][1] + h(edp) + 60 <= V[qdp][1])
    add(V[qdp][1] + h(qdp) + 40 <= V[emp][1])
    add(B['MANIFOLD'] + 30 <= V[qdp][0])   # 左缘净距=18px引出桩+8px预算最短段+裕量
    add((V[qdp][0] + w(qdp) / 2 <= B['MANIFOLD'] + 80) | strong)  # 偏好：紧贴母线右侧
    add(V[rf][1] + h(rf) + 40 <= V[qdr][1])
    add(B['RET'] + 20 <= V[qdr][0])
    # 回油滤在 RET 与用户缘之间；壳体回油滤在顶行
    add(B['RET'] + 100 <= V[rf][0])
    add(V[rf][0] + w(rf) + 40 <= 1480)
    add(V[cdf][1] + h(cdf) + 60 <= V[edp][1])
    add(V[tank][0] + w(tank) + 60 <= V[cdf][0])
    add(V[cdf][0] + w(cdf) <= B['PRESS'] - 20)
    # 自增压优先阀：油箱与泵列之间、辅行下方
    add(V[tank][0] + w(tank) + 40 <= V[prv2][0])
    add(V[prv2][0] + w(prv2) <= B['PRESS'] - 40)
    add(V[emp][1] + h(emp) + 40 <= V[prv2][1])

    # ---------- 弱约束：约定表偏好锚点 ----------
    at(tank, x=P['TANK_X'], y=P['ROW_MAIN'] - P['TANK_TOP_PAD'])
    at(fsov, x=P['TANK_X'] + w(tank) + P['COL_GAP'])
    at(edp, x=P['TANK_X'] + w(tank) + P['COL_GAP'] + 80 + P['COL_GAP'],
       y=P['ROW_MAIN'], strength=strong)
    at(emp, y=P['ROW_MAIN'] + P['ROW_PITCH'], strength=strong)
    at(pf, x=880 + P['BUS_INLINE_GAP_A'], y=P['ROW_MAIN'] - (h(pf) - 80) // 2,
       strength=strong)
    at(prv1, x=1300)
    at(prv2, x=P['TANK_X'] + w(tank) + 160,
       y=P['ROW_MAIN'] + P['ROW_PITCH'] + P['BOOST_DROP'], strength=strong)
    at(rf, x=1200, y=P['ROW_RETURN'], strength=strong)
    at(cdf, x=P['TANK_X'] + 360, y=P['ROW_CASE'], strength=strong)
    at(acc, x=1180, y=P['ROW_MAIN'] - h(acc), strength=strong)
    at(acv, x=1240, y=60, strength=strong)
    at(pg, x=1414, y=50, strength=strong)
    at(qdp, x=1186, y=P['ROW_MAIN'] + P['QDP_DROP'], strength=strong)
    at(qdr, x=1200, y=P['ROW_QDR'], strength=strong)
    for b, pref in (('PRESS', 880), ('MANIFOLD', 1160), ('RET', 940), ('CASE', 620)):
        add((B[b] == pref) | strong)

    s.updateVariables()
    nodes = {}
    for inst in parts:
        x, y = V[inst]
        nodes[inst] = dict(x=round(x.value()), y=round(y.value()),
                           w=w(inst), h=h(inst), rot=0,
                           symbol=FOOTPRINT[parts[inst]][2])
    # 挂装角（流路方向规则，A/B 同表）：回油滤右→左、自增压阀右→左、壳体滤顶装
    nodes[rf]['rot'] = 180
    nodes[prv2]['rot'] = 180
    nodes[cdf]['rot'] = 270

    with io.open(os.path.join(FZ, '1#系统.layout.json'), encoding='utf-8') as f:
        v23 = json.load(f)
    layout = dict(
        layout_version='protoA-1.0',
        source_l0='1#系统.intent.yaml',
        note='原型 A：kiwisolver 声明式约束——坐标为求解器输出，声明见 proto_a_kiwi.py（#17）。',
        canvas=dict(width=P['CANVAS_W'], height=P['CANVAS_H']),
        canvas_shift_x=P['SHIFT'],
        style=dict(base_line_width_T=1.2, symbol_stroke_width=2, suction_marker_S=8),
        externs=dict(v23['externs']),
        nodes=nodes,
        buses={b: dict(kind='v', x=round(bb.value())) for b, bb in B.items()},
        lanes=[P['LANE_TOP']],
        vlanes=[P['VLANE_WEST'],
                conv_nlane(nodes, tank)],
        group_padding=20, group_label_gap=10,
        legend=P['LEGEND'], title_block=P['TITLE'],
        labels={k: v for k, v in v23.get('labels', {}).items() if k in nodes},
        label_pos={k: v for k, v in v23.get('label_pos', {}).items() if k in nodes},
        label_drop=dict(v23.get('label_drop', {})),
    )
    with io.open(os.path.join(FZ, '1#系统A.layout.json'), 'w', encoding='utf-8') as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)
    print('layoutA.json:', len(nodes), 'nodes,', len(B), 'buses')
    return 0


def conv_nlane(nodes, tank):
    """吸油上行竖廊：油箱右缘与首列左缘之间（规则同 B 的 R11）。"""
    tr = nodes[tank]['x'] + nodes[tank]['w']
    lefts = sorted(n['x'] for n in nodes.values() if n['x'] > tr)
    return tr + conv.P['EDGE_PAD'] if not lefts else (tr + lefts[0]) // 2


if __name__ == '__main__':
    sys.exit(main())
