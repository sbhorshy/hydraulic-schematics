# -*- coding: utf-8 -*-
"""布局引擎（#18 方案乙正式实现）：规则定行位 + 约束守门微调。

两段式，替代"人工给坐标"这一步（接 preflight 后、place() 前）：

  Stage 1  rules()    母线驱动的规则式分层。从 intent paths 推导链/单边/母线，
                      按端口 role 与连接形态分类（不认实例名），R1–R14 定出全部
                      坐标。布局语言的全部自由度收在参数表 P——改参只改这张表。
  Stage 2  guard()    kiwi 约束守门。把 REQUIRED 不变量（画布/图例回避、B5 盒距、
                      元件禁骑母线、母线次序、跨带净距）作用在规则解上：
                      规则解已满足则零漂移；个别违例由求解器在锚点拉力下微调并出
                      结构化报告；不可满足则报错退出（绝不静默出图）。

隐式惯例显式化（#17 定案随票沉淀）：
  · 母线净距 ≈ 40 = 18 引出桩 + 8 预算最短段 + 5 桥半径 + 裕量（BUS_PUMP_CLEAR）；
  · 元件禁骑母线：盒缘离母线 ≥ BUS_NO_RIDE=20；
  · 符号足迹(w/h)与挂装角(rot)是符号库/流路事实，不是布局决策。

用法：
  python layout_engine.py INTENT CATALOG REF_LAYOUT -o OUT.layout.json
      [--guard-report OUT.json] [--param KEY=VAL ...]

REF_LAYOUT 仅取 labels/label_pos/label_drop 等展示文案（标签文字不是坐标决策），
坐标一概不从参照布局读取。--param 供改参传播实验（如 ROW_PITCH=420）。
"""
import io
import json
import os
import sys

from kiwisolver import Solver, Variable, UnsatisfiableConstraint
from kiwisolver import strength as _st
strong = _st.strong
from ruamel.yaml import YAML

# ---------- 规则参数表 P：布局语言的全部自由度 ----------
P = dict(
    TANK_X=60,                 # R1 油箱置左
    COL_GAP=90,                # R2 列间距(吸油阀列与泵列)
    BUS_GAP=262,               # R3 压力汇流母线离泵列右缘——取值使 @PRESS≈880:
                               # 右侧要给用户场+收集链留画布,汇流母线不外飘
    BUS_PUMP_CLEAR=40,         # R3 壳体回油母线离泵列右缘(=18桩+8最短段+5桥+裕量)
    BUS_INLINE_GAP_A=120,      # R4 母线→串联件(汇流母线出线)
    DIST_INLINE_GAP_A=140,     # R4 母线→串联件(分配母线出线余量更大,人工同款)
    BUS_INLINE_GAP_B=80,       # R4 串联件→下一条母线
    USR_BUS_GAP=30,            # R4' 链尾母线挂用户场时改用紧凑尾距(用户列贴它成场)
    RET_CLEAR=60,              # R7 回油母线与压力汇流母线净距
    ROW_MAIN=290,              # R5 主行
    ROW_WIRE_DY=40,            # R5 主行走线高度(主行+40,即 80x80 符号端口中线)
    ROW_PITCH=320,             # R5 行距(主行→辅行)
    ROW_RETURN=700,            # R7 回油行(extern 类回油滤)
    ROW_QDR=900,               # R7 地面接头行
    ROW_CASE=100,              # R8 壳体回油行(顶)
    RET_OFFSET=260,            # R7 回油行/接头行元件离回油母线
    TANK_TOP_PAD=14,           # R1 油箱顶缘高出主行
    BOOST_DROP=130,            # R9 自增压支路在辅行下的落差(留 >B5 余量)
    BOOST_X_OFF=160,           # R9 自增压阀离油箱右缘
    QDP_DROP=270,              # R6 地面压力接头在主行下的落差
    QDP_X_OFF=28,              # R6 地面接头离母线(=18引出桩+10最短段,≥预算8)
    GAS_GAP=73,                # R10 气侧纵向堆叠间距
    GAS_STACK_GAP=43,          # R10 气侧横向堆叠净距(≥B5 40)
    ACC_BUS_OFF=20,            # R6/R10 蓄压器离母线(=禁骑下限,不小于它)
    GAS_STACK_X0=0,            # R10 首个气侧件与蓄压器左对齐(腾出横堆宽度,
                               # 供压母线禁骑钳位就不再压缩 B5 净距)
    GAS_RISE=30,               # R10 首个气侧件相对蓄压器顶的抬升修正
    USER_BUS_PAD=28,           # R13 @USR→用户列(12px尾+10px尾+裕量)
    USER_RETURN_PAD=28,        # R13 用户列→@USERR
    USER_PITCH_GAP=45,         # R13 列内净距(≥B5 40)
    USER_GAS_CLEAR=43,         # R13 气侧堆叠底缘→用户列顶(≥B5 40)
    USER_FALLBACK_TOP=160,     # R13 无气侧堆叠时的列顶
    RF_DROP=44,                # R14 收集链滤离地面接头行底(≥B5 40)
    USR_OFF=40,                # R12 extern 边界离最右元件
    LANE_TOP=100,              # R11 顶部走廊
    VLANE_WEST=20,             # R11 西缘竖廊
    EDGE_PAD=12,               # R11 竖廊离列缘
    BUS_NO_RIDE=20,            # 守门: 盒缘离母线最小距离(禁骑母线)
    BOX_GAP=40,                # 守门: B5 盒距
    CANVAS_W=1680, CANVAS_H=1390, SHIFT=30,
    LEGEND=dict(x=380, y=1020, w=540, h=290),   # 让位回油收集走廊
    TITLE=dict(x=40, y=1330, w=1600, h=56),
)

# 符号足迹表(符号库事实,非布局决策;rot 由挂装规则输出)。
# 第 4 位 port_dy = 主端口在布局单位下的纵向偏移(None=80x80 系,中线即走线高度)。
# 这是符号库事实:滤的进出口在 84/112、优先阀在 63x(140/324)≈27.2,
# 串联件须按端口对齐走线高度,按中心对齐会产出台阶(第 6 轮目视验收教训)。
FOOTPRINT = {
    'bootstrap_reservoir': (218, 564, 'symbols/reservoir-bootstrap-annotated.svg', None),
    'firewall_shutoff_valve': (80, 80, 'symbols/fsov-provisional-stroke.svg', None),
    'engine_driven_pump': (80, 80, 'symbols/edp-provisional-stroke.svg', None),
    'electric_motor_driven_pump': (80, 80, 'symbols/emp-provisional-stroke.svg', None),
    'filter_line_shutoff_dp': (80, 112, 'symbols/filter-line-shutoff-dp.svg', 84.0),
    'filter_line_shutoff_dp_case_drain': (60, 80, 'symbols/filter-line-shutoff-dp.svg', None),
    'filter_line_shutoff_dp_return': (80, 112, 'symbols/filter-line-shutoff-dp.svg', None),
    'priority_valve': (140, 78, 'symbols/priority-valve.svg', 27.2),
    'hydro_pneumatic_accumulator': (60, 100, 'symbols/accumulator.svg', None),
    'air_charging_valve': (134, 57, 'symbols/air-charging-valve.svg', None),
    'pressure_gauge': (63, 67, 'symbols/pressure-gauge.svg', None),
    'quick_disconnect_coupling_disconnected': (160, 68, 'symbols/quick-disconnect-coupling-disconnected.svg', None),
    'quick_disconnect_coupling_disconnected_return': (160, 68, 'symbols/quick-disconnect-coupling-disconnected.svg', None),
    'hydraulic_user': (120, 60, 'symbols/hydraulic-user.svg', None),
}


# ---------- 输入 ----------
def load_yaml(p):
    y = YAML(typ='safe', pure=True)
    y.version = (1, 2)
    with io.open(p, encoding='utf-8') as f:
        return y.load(f)


def port_roles(cat, parts):
    types = {c['component_type']: c for c in cat['components']}
    out = {}
    for inst, t in parts.items():
        out[inst] = {p['id']: p['role'] for p in types[t]['ports']}
    return out, types


# ---------- 拓扑归约 ----------
def analyze(intent, roles):
    """paths -> (chains, single, buses)。

    chains: (首 token, [中间件...], 尾 token);single: 二元路径;
    buses: 母线名 -> 挂接端口 role 集(线型与母线类别的依据)。
    """
    chains, single, buses = [], [], {}
    for toks in intent['paths']:
        if len(toks) == 2:
            single.append((toks[0], toks[1]))
        else:
            chains.append((toks[0], list(toks[1:-1]), toks[-1]))
        for t in toks:
            if t.startswith('@'):
                buses.setdefault(t[1:], set())
        for k in range(len(toks) - 1):
            a, b = toks[k], toks[k + 1]
            for bus, other in ((a, b), (b, a)):
                if not bus.startswith('@') or other.startswith('@'):
                    continue
                inst, _, pid = other.partition('.')
                if not pid:
                    continue        # main_path 解析留给渲染器
                buses[bus[1:]].add(roles[inst].get(pid, 'pressure'))
    return chains, single, buses


def classify_bus(role_set):
    """母线类别:由挂接 role 集推导(case > return > pressure)。"""
    s = set(role_set)
    if 'case_drain' in s:
        return 'case'
    if s <= {'return', 'pressure'} and 'return' in s:
        return 'return'
    return 'pressure'


# ---------- Stage 1: 规则引擎 ----------
def rules(intent, cat, params, ref=None):
    """intent -> (layout, structure)。structure 供守门层生成 REQUIRED。"""
    P = params
    roles, _types = port_roles(cat, intent['parts'])
    chains, single, buses = analyze(intent, roles)
    parts = intent['parts']
    structure = dict(rows={}, stacks={})

    # ---- 识别(按连接形态与端口 role,不认实例名)----
    tank = next(i for i, r in roles.items()
                if 'suction_out' in r and 'return_in' in r)
    pumps = [i for i, r in roles.items()
             if 'suction' in r and 'pressure_out' in r and 'case_drain' in r]
    # 主泵 = 串联链(油箱→阀→泵)的链尾;其余泵落辅行。确定性排序兜底。
    pumps.sort(key=lambda i: (i not in {e.split('.')[0] for _s, ms, e in chains
                                        if ms and e.split('.')[0] == i}, i))
    # 吸油串联阀 = 油箱起步链上的中间件
    succ_valves = sorted(m for s_tok, ms, _e in chains
                         if s_tok.split('.')[0] == tank for m in ms)

    # ---- 用户场识别(双挂叶:两条单边各接一条母线,一压一回)----
    bus_attachments = {}
    for a, b in single:
        pair = ((a, b) if a.startswith('@') else
                ((b, a) if b.startswith('@') else (None, None)))
        bus_tok, other = pair
        if bus_tok is None or other.startswith('@'):
            continue
        bus_attachments.setdefault(other.split('.')[0], set()).add(bus_tok[1:])
    users = sorted(i for i, bs in bus_attachments.items()
                   if len(bs) == 2 and i != tank
                   and sorted(classify_bus(buses[b]) for b in bs)
                   == ['pressure', 'return'])
    user_buses = set().union(*[bus_attachments[i] for i in users]) if users else set()
    usr_bus = next((b for b in user_buses
                    if classify_bus(buses[b]) == 'pressure'), None)
    userr_bus = next((b for b in user_buses
                      if classify_bus(buses[b]) == 'return'), None)

    # ---- 压力汇流母线 = 泵压力出口共同接入的那条 ----
    press_bus = None
    for a, b in single:
        for bus, other in ((a, b), (b, a)):
            if bus.startswith('@') and not other.startswith('@'):
                inst, _, pid = other.partition('.')
                if inst in pumps and roles[inst].get(pid) == 'pressure_out':
                    press_bus = bus[1:]
    if press_bus is None:
        press_bus = next(b for b, rs in buses.items()
                         if classify_bus(rs) == 'pressure')

    nodes, buses_out, externs = {}, {}, {}

    def put(inst, x, y, rot=0, row=None, stack=None):
        w, h = FOOTPRINT[parts[inst]][:2]
        nodes[inst] = dict(x=int(x), y=int(y), w=w, h=h, rot=rot)
        # 重放置(如 R8 覆盖 R9 误点)须从旧行带除名,行带结构才与坐标一致。
        for members in structure['rows'].values():
            if inst in members and members != structure['rows'].get(row):
                members.remove(inst)
        for members in structure['stacks'].values():
            if inst in members and members != structure['stacks'].get(stack):
                members.remove(inst)
        if row:
            structure['rows'].setdefault(row, []).append(inst)
        if stack:
            structure['stacks'].setdefault(stack, []).append(inst)

    # ---- R1 油箱首位(左缘,顶对主行上方 TANK_TOP_PAD)----
    tank_w, tank_h = FOOTPRINT[parts[tank]][:2]
    tank_right = P['TANK_X'] + tank_w
    put(tank, P['TANK_X'], P['ROW_MAIN'] - P['TANK_TOP_PAD'], row='main')

    # ---- R2 吸油阀列 + 泵列 ----
    x = tank_right + P['COL_GAP']
    for v in succ_valves:
        put(v, x, P['ROW_MAIN'], row='main')
        x += FOOTPRINT[parts[v]][0] + P['COL_GAP']
    pump_x = x
    for k, pm in enumerate(pumps):
        put(pm, pump_x, P['ROW_MAIN'] + (0 if k == 0 else P['ROW_PITCH']),
            row=('main' if k == 0 else 'aux'))
    pump_right = pump_x + FOOTPRINT[parts[pumps[0]]][0]

    # ---- R3 母线初位(壳体/汇流/回油;分配与用户场母线由 R4/R13 回填)----
    for b, rs in buses.items():
        kind = classify_bus(rs)
        if kind == 'case':
            buses_out[b] = dict(kind='v', x=pump_right + P['BUS_PUMP_CLEAR'])
        elif b == press_bus:
            buses_out[b] = dict(kind='v', x=pump_right + P['BUS_GAP'])
        elif kind == 'return' and b not in user_buses:
            buses_out[b] = dict(kind='v',
                                x=buses_out[press_bus]['x'] + P['RET_CLEAR'])
        else:
            buses_out.setdefault(b, dict(kind='v', x=0))    # 占位,后续回填
    # 分配母线 = 压力链自汇流母线出发的链尾(兜底:下一条压力类母线)
    dist = next((e_tok[1:] for s_tok, ms, e_tok in chains
                 if s_tok == '@' + press_bus and ms and e_tok.startswith('@')),
                None)
    if dist is None:
        dist = next(b for b, rs in buses.items()
                    if classify_bus(rs) == 'pressure' and b != press_bus)

    # ---- R4 压力链:双母线夹串联件(不动点;回油收集链归 R14)----
    def bus_kind(tok):
        return classify_bus(buses.get(tok[1:], set())) if tok.startswith('@') else None

    pending = [c for c in chains
               if c[0].startswith('@') and c[2].startswith('@')
               and bus_kind(c[0]) == 'pressure']
    while pending:
        progressed = False
        rest = []
        for s_tok, mids, e_tok in pending:
            if buses_out[s_tok[1:]]['x'] == 0:
                rest.append((s_tok, mids, e_tok))
                continue
            bx = buses_out[s_tok[1:]]['x']
            # 分配母线出线余量更大(串联件前后都要给桩+最短段留足)
            gap_a = (P['DIST_INLINE_GAP_A'] if s_tok[1:] == dist
                     else P['BUS_INLINE_GAP_A'])
            for m in mids:
                w, h = FOOTPRINT[parts[m]][:2]
                mx = bx + gap_a
                # 端口对齐走线高度:按中心摆放时,滤(端口在84/112)与优先阀
                # (63x140/324)的接口会偏离泵出油口线,主压路出现台阶
                # (目视验收缺陷)。port_dy 是符号库事实,见 FOOTPRINT 注。
                pdy = FOOTPRINT[parts[m]][3]
                put(m, mx,
                    P['ROW_MAIN'] + P['ROW_WIRE_DY']
                    - (pdy if pdy is not None else P['ROW_WIRE_DY']),
                    row='main')
                bx = mx + w + P['BUS_INLINE_GAP_B']
            # 链尾母线挂用户场 → 紧凑尾距(R4'),用户列要贴它成场
            tail_gap = (P['USR_BUS_GAP'] if e_tok[1:] in user_buses
                        else P['BUS_INLINE_GAP_B'])
            buses_out[e_tok[1:]]['x'] = bx - P['BUS_INLINE_GAP_B'] + tail_gap
            progressed = True
        pending = rest
        if pending and not progressed:
            raise SystemExit('规则引擎: 压力链不可定位(起点母线无坐标): %s'
                             % [c[0] for c in pending])

    # ---- R13 用户场:双母线夹一列(列顶先按回退值,R10 后平移修正)----
    if users:
        col_x = buses_out[usr_bus]['x'] + P['USER_BUS_PAD']
        y = P['USER_FALLBACK_TOP']
        for u in users:
            put(u, col_x, y, stack='user_col')
            y += FOOTPRINT[parts[u]][1] + P['USER_PITCH_GAP']
        buses_out[userr_bus]['x'] = (col_x + FOOTPRINT[parts[users[0]]][0]
                                     + P['USER_RETURN_PAD'])

    # ---- R5/R6/R9 分配母线支路 ----
    dx = buses_out[dist]['x']
    for s_tok, mids, e_tok in chains:
        if s_tok[1:] != dist:
            continue
        if mids and not e_tok.startswith('@'):
            m = mids[0]
            w, h = FOOTPRINT[parts[m]][:2]
            pdy = FOOTPRINT[parts[m]][3]
            put(m, dx + P['BUS_INLINE_GAP_A'],
                P['ROW_MAIN'] + P['ROW_WIRE_DY']
                - (pdy if pdy is not None else P['ROW_WIRE_DY']),
                row='main')
            if e_tok in intent.get('extern', {}):
                externs[e_tok] = dict(x=dx + P['BUS_INLINE_GAP_A'] + w + P['USR_OFF'],
                                      y=P['ROW_MAIN'] + 110, anchor='left',
                                      label=e_tok)
        elif not mids and not e_tok.startswith('@'):
            inst = e_tok.split('.')[0]
            if inst in nodes or inst in users or inst in intent.get('extern', {}):
                continue
            if 'gas_port' in roles.get(inst, {}):
                put(inst, dx + P['ACC_BUS_OFF'],
                    P['ROW_MAIN'] - FOOTPRINT[parts[inst]][1], stack='gas_low')
            else:
                put(inst, dx + P['QDP_X_OFF'],
                    P['ROW_MAIN'] + P['QDP_DROP'], row='aux1')
    # R9 自增压支路:压力母线 → 阀 → 油箱(增压口),置于油箱前方辅行下。
    # 必须门控"压力母线起步":壳体回油链(@CASE→滤→油箱)链尾同为油箱,
    # 不门控会误点进 aux2 行带,行带序随之判反(第 2 轮教训)。
    for s_tok, mids, e_tok in chains:
        if (s_tok.startswith('@') and bus_kind(s_tok) == 'pressure'
                and mids and e_tok.split('.')[0] == tank):
            m = mids[0]
            put(m, tank_right + P['BOOST_X_OFF'],
                P['ROW_MAIN'] + P['ROW_PITCH'] + P['BOOST_DROP'], rot=180,
                row='aux2')

    # ---- 单边母线支路:气侧骑母线顶 / 地面接头落辅助行 / 回油接头落接头行 ----
    for a, b in single:
        bus_tok, other = (a, b) if a.startswith('@') else \
            ((b, a) if b.startswith('@') else (None, None))
        if bus_tok is None or other.startswith('@'):
            continue
        inst = other.split('.')[0]
        if inst in nodes or inst in users or inst == tank \
                or inst in intent.get('extern', {}):
            continue
        bname = bus_tok[1:]
        if classify_bus(buses[bname]) == 'return':
            put(inst, buses_out[bname]['x'] + P['RET_OFFSET'], P['ROW_QDR'],
                row='qdr')
        elif 'gas_port' in roles.get(inst, {}):
            put(inst, buses_out[bname]['x'] + P['ACC_BUS_OFF'],
                P['ROW_MAIN'] - FOOTPRINT[parts[inst]][1], stack='gas_low')
        else:
            put(inst, buses_out[bname]['x'] + P['QDP_X_OFF'],
                P['ROW_MAIN'] + P['QDP_DROP'], row='aux1')

    # ---- R7 回油行(extern 起步的回油链;收集链归 R14)----
    ret_buses = [b for b, rs in buses.items()
                 if classify_bus(rs) == 'return' and b not in user_buses]
    for s_tok, mids, e_tok in chains:
        end_bus = e_tok[1:] if e_tok.startswith('@') else None
        if end_bus in ret_buses and mids and not s_tok.startswith('@'):
            m = mids[0]
            put(m, buses_out[end_bus]['x'] + P['RET_OFFSET'], P['ROW_RETURN'],
                rot=180, row='return')
            if s_tok in intent.get('extern', {}):
                rightmost = max(n['x'] + n['w'] for n in nodes.values())
                externs[s_tok] = dict(x=rightmost + P['USR_OFF'],
                                      y=P['ROW_RETURN'], anchor='left',
                                      label=s_tok)

    # ---- R14 回油收集链:母线→滤→母线;滤对齐接头列、落收集行 ----
    for s_tok, mids, e_tok in chains:
        if not (s_tok.startswith('@') and e_tok.startswith('@')):
            continue
        if (bus_kind(s_tok) == 'return' and bus_kind(e_tok) == 'return'):
            if not mids:
                continue
            m = mids[0]
            qdr = next((i for i, nd in nodes.items()
                        if 'qdr' in structure['rows']
                        and i in structure['rows']['qdr']), None)
            base_y = (nodes[qdr]['y'] + nodes[qdr]['h'] if qdr
                      else P['ROW_QDR'] + 68)
            put(m, nodes[qdr]['x'] if qdr else buses_out[s_tok[1:]]['x'],
                base_y + P['RF_DROP'], rot=180, row='collect')

    # ---- R8 壳体回油族:母线→滤(顶装)→油箱 ----
    for s_tok, mids, e_tok in chains:
        if (s_tok.startswith('@') and mids and bus_kind(s_tok) == 'case'):
            m = mids[0]
            put(m, P['TANK_X'] + 360, P['ROW_CASE'], rot=270, row='case')

    # ---- R10 气侧 taps:传感链自蓄压器向上/向右堆叠 ----
    if intent.get('taps'):
        acc_inst = next((i for i in nodes
                         if 'gas_port' in roles.get(i, {})
                         and nodes[i]['y'] < P['ROW_MAIN']), None)
        if acc_inst:
            # 供压用户场母线的禁骑上限(气侧横堆不得越过它)
            usr_limit = (buses_out[usr_bus]['x'] - P['BUS_NO_RIDE']
                         if usr_bus else P['CANVAS_W'])
            prev = acc_inst
            for t in intent['taps']:
                sinst = t['sensor'].split('.')[0]
                if sinst in nodes or sinst in users:
                    continue
                w, h = FOOTPRINT[parts[sinst]][:2]
                if prev == acc_inst:        # 首件:蓄压器正上方
                    nx = nodes[prev]['x'] + P['GAS_STACK_X0']
                    ny = nodes[prev]['y'] - h - P['GAS_GAP'] + P['GAS_RISE']
                else:                       # 后续:右侧横堆,不得骑上供压母线
                    nx = min(nodes[prev]['x'] + nodes[prev]['w'] + P['GAS_STACK_GAP'],
                             usr_limit - w)
                    ny = nodes[prev]['y']
                nodes[sinst] = dict(x=int(nx), y=int(ny), w=w, h=h, rot=0)
                structure['stacks'].setdefault('gas_stack', []).append(sinst)
                prev = sinst
            # R13 列顶修正:与用户列 x-重叠的气侧件底缘 + 净距
            if users:
                ux0 = nodes[users[0]]['x']
                ux1 = ux0 + nodes[users[0]]['w']
                overl = [i for i in structure['stacks']['gas_stack']
                         if nodes[i]['x'] < ux1 and nodes[i]['x'] + nodes[i]['w'] > ux0]
                if overl:
                    gas_bottom = max(nodes[i]['y'] + nodes[i]['h'] for i in overl)
                    shift = gas_bottom + P['USER_GAS_CLEAR'] - nodes[users[0]]['y']
                    if shift:
                        for u in users:
                            nodes[u]['y'] += shift

    # ---- R11 走廊 ----
    vlanes = [P['VLANE_WEST'],
              tank_right + P['EDGE_PAD']]           # 西缘竖廊 + 吸油上行竖廊

    # ---- extern 兜底(extern 类 intent;用户名框类 intent 的 extern 为空)----
    for e, kind in intent.get('extern', {}).items():
        if e not in externs:
            externs[e] = dict(x=1480, anchor='left', label=e,
                              y=(P['ROW_RETURN'] if kind == 'return'
                                 else P['ROW_MAIN'] + 110))

    layout = dict(
        layout_version='layout-engine-1.0',
        source_l0=os.path.basename(intent['source'] if 'source' in intent else '')
        or '',
        note='方案乙:R1–R14 规则定行位 + kiwi 守门微调(#18);全部坐标由'
             '参数表+intent 拓扑推导,零手工坐标。',
        canvas=dict(width=P['CANVAS_W'], height=P['CANVAS_H']),
        canvas_shift_x=P['SHIFT'],
        style=dict(base_line_width_T=1.2, symbol_stroke_width=2, suction_marker_S=8),
        externs=externs, nodes=nodes, buses=buses_out,
        lanes=[P['LANE_TOP']], vlanes=vlanes,
        group_padding=20, group_label_gap=10,
        legend=P['LEGEND'], title_block=P['TITLE'],
    )
    for inst, nd in nodes.items():
        fp = FOOTPRINT.get(parts[inst])
        if fp is None:
            raise SystemExit('规则引擎: 类型无足迹登记: %s (%s)' % (inst, parts[inst]))
        nd['symbol'] = fp[2]

    # 展示文案(标签/图例文字)取自参照布局——文案不是坐标决策。
    if ref:
        for key in ('labels', 'label_pos', 'label_drop'):
            if key in ref:
                layout[key] = {k: v for k, v in ref[key].items() if k in nodes}
        for k in externs:
            if k in ref.get('externs', {}):
                externs[k]['label'] = ref['externs'][k]['label']

    missing = set(parts) - set(nodes)
    if missing:
        raise SystemExit('规则引擎: 未布元件 %s——intent 形态超出 R1–R14 覆盖'
                         % sorted(missing))
    return layout, structure


# ---------- Stage 2: 约束守门 ----------
def guard(layout, structure, params):
    """REQUIRED 作用在规则解上;返回 (微调后 layout, 报告)。

    每条 REQUIRED 由 req() 同步登记一份"规则点数值检查"——既喂给求解器,
    又能在规则点回答"哪条、违了多少"。规则解已一致时漂移为零(零漂移性质);
    有违例时求解器在强锚点拉力下做最小位移微调,报告列出挪了谁。
    """
    P = params
    nodes = layout['nodes']
    bx = {b: float(v['x']) for b, v in layout['buses'].items()}
    s = Solver()
    checks = []       # (tag, 规则点是否已满足)

    V = {inst: (Variable(inst + '.x'), Variable(inst + '.y'))
         for inst in nodes}
    B = {b: Variable('bus.' + b + '.x') for b in bx}

    def req(tag, constraint, ok_at_rule):
        s.addConstraint(constraint)
        checks.append((tag, ok_at_rule))

    # 锚点:规则解(strong 拉力;守门只在该动时才动)
    for inst, (vx, vy) in V.items():
        s.addConstraint((vx == nodes[inst]['x']) | strong)
        s.addConstraint((vy == nodes[inst]['y']) | strong)
    for b, v in B.items():
        s.addConstraint((v == bx[b]) | strong)

    def w(i):
        return nodes[i]['w']

    def h(i):
        return nodes[i]['h']

    def x0(i):
        return nodes[i]['x']

    def y0(i):
        return nodes[i]['y']

    def x1(i):
        return nodes[i]['x'] + nodes[i]['w']

    def y1(i):
        return nodes[i]['y'] + nodes[i]['h']

    def x_overlap(a, b):
        return x0(a) < x1(b) and x0(b) < x1(a)

    GAP = P['BOX_GAP']
    EPS = 1e-6

    # -- REQUIRED 1: 画布与图例回避(净空只对 x-压住图例的盒声明)--
    LG0, LG1 = P['LEGEND']['x'], P['LEGEND']['x'] + P['LEGEND']['w']
    for inst in nodes:
        vx, vy = V[inst]
        req('canvas.left[%s]' % inst, vx >= 60, x0(inst) >= 60 - EPS)
        req('canvas.right[%s]' % inst, vx + w(inst) <= P['CANVAS_W'] - 30,
            x1(inst) <= P['CANVAS_W'] - 30 + EPS)
        req('canvas.top[%s]' % inst, vy >= 60, y0(inst) >= 60 - EPS)
        if x0(inst) < LG1 and LG0 < x1(inst):
            req('legend.clear[%s]' % inst,
                vy + h(inst) <= P['LEGEND']['y'] - 10,
                y1(inst) <= P['LEGEND']['y'] - 10 + EPS)

    # -- REQUIRED 2: 元件禁骑母线(侧别取规则解观察侧;近邻 300 内才声明)--
    for inst in nodes:
        for b in B:
            if abs((x0(inst) + x1(inst)) / 2.0 - bx[b]) > 300:
                continue
            if x1(inst) <= bx[b]:
                req('no-ride[%s|%s<W]' % (inst, b),
                    V[inst][0] + w(inst) + P['BUS_NO_RIDE'] <= B[b],
                    x1(inst) + P['BUS_NO_RIDE'] <= bx[b] + EPS)
            else:
                req('no-ride[%s|%s>W]' % (inst, b),
                    B[b] + P['BUS_NO_RIDE'] <= V[inst][0],
                    bx[b] + P['BUS_NO_RIDE'] <= x0(inst) + EPS)

    # -- REQUIRED 3: 同行相邻盒距 / 同列相邻盒距 ≥ B5 --
    for row, members in structure['rows'].items():
        ms = sorted(members, key=lambda i: x0(i))
        for a, b in zip(ms, ms[1:]):
            req('row[%s]:%s->%s' % (row, a, b),
                V[a][0] + w(a) + GAP <= V[b][0],
                x1(a) + GAP <= x0(b) + EPS)
    for stack, members in structure['stacks'].items():
        ms = sorted(members, key=lambda i: y0(i))
        for a, b in zip(ms, ms[1:]):
            if x_overlap(a, b):
                req('stack[%s]:%s->%s' % (stack, a, b),
                    V[a][1] + h(a) + GAP <= V[b][1],
                    y1(a) + GAP <= y0(b) + EPS)
        # 同带水平相邻(如气侧横堆):同 y 起点者按 x 链声明 B5
        bands = {}
        for i in members:
            bands.setdefault(round(y0(i) / 10.0), []).append(i)
        for band in bands.values():
            hb = sorted(band, key=lambda i: x0(i))
            for a, b in zip(hb, hb[1:]):
                req('hband[%s]:%s->%s' % (stack, a, b),
                    V[a][0] + w(a) + GAP <= V[b][0],
                    x1(a) + GAP <= x0(b) + EPS)

    # -- REQUIRED 4: 跨行带净距(仅对 x-重叠的对声明;上带底+GAP ≤ 下带顶)--
    row_tops = {r: min(y0(i) for i in ms)
                for r, ms in structure['rows'].items() if ms}
    for ra, ma in structure['rows'].items():
        for rb, mb in structure['rows'].items():
            if ra == rb or row_tops[ra] >= row_tops[rb]:
                continue
            for i in mb:
                for j in ma:
                    if x_overlap(i, j):
                        req('band[%s->%s]:%s-under-%s' % (ra, rb, i, j),
                            V[j][1] + h(j) + GAP <= V[i][1],
                            y1(j) + GAP <= y0(i) + EPS)
    # 用户列与气侧横堆:x-重叠的对,气侧底 + GAP ≤ 列顶
    for u in structure['stacks'].get('user_col', []):
        for g in structure['stacks'].get('gas_stack', []):
            if x_overlap(u, g):
                req('cross[user_col]:%s-under-%s' % (u, g),
                    V[g][1] + h(g) + GAP <= V[u][1],
                    y1(g) + GAP <= y0(u) + EPS)

    # -- REQUIRED 5: 母线次序(规则解观察序,保序不倒置)--
    seq = sorted(bx, key=lambda b: bx[b])
    for a, b in zip(seq, seq[1:]):
        req('bus-order[%s<%s]' % (a, b), B[a] + P['BUS_NO_RIDE'] <= B[b],
            bx[a] + P['BUS_NO_RIDE'] <= bx[b] + EPS)

    # -- REQUIRED 6: 母线画布界。viewBox 固定 canvas 宽而内容整体 +SHIFT,
    # 母线可用右缘 = CANVAS_W - SHIFT;越界即被裁出图面(目视验收缺陷)。
    for b in B:
        req('canvas.right[bus:%s]' % b,
            B[b] <= P['CANVAS_W'] - P['SHIFT'],
            bx[b] <= P['CANVAS_W'] - P['SHIFT'] + EPS)
        req('canvas.left[bus:%s]' % b, B[b] >= 60, bx[b] >= 60 - EPS)

    # ---- 规则点违例评估 → 求解 → 漂移报告 ----
    violations_at_rule = [tag for tag, ok in checks if not ok]
    try:
        s.updateVariables()
    except UnsatisfiableConstraint as e:
        raise SystemExit('守门层: REQUIRED 不可满足,拒绝出图。规则点违例 %d 条:'
                         '\n  %s\n求解器: %s'
                         % (len(violations_at_rule),
                            '\n  '.join(violations_at_rule[:10]), e))
    drift = {}
    for inst, (vx, vy) in V.items():
        dx, dy = vx.value() - nodes[inst]['x'], vy.value() - nodes[inst]['y']
        if abs(dx) > 0.5 or abs(dy) > 0.5:
            drift[inst] = dict(dx=round(dx, 1), dy=round(dy, 1))
            nodes[inst]['x'] = int(round(vx.value()))
            nodes[inst]['y'] = int(round(vy.value()))
    for b, v in B.items():
        if abs(v.value() - layout['buses'][b]['x']) > 0.5:
            drift['bus:' + b] = dict(dx=round(v.value() - layout['buses'][b]['x'], 1))
            layout['buses'][b]['x'] = int(round(v.value()))
    report = dict(
        guard='kiwi REQUIRED on rule solution (#18 方案乙)',
        constraints=len(checks),
        violations_at_rule=violations_at_rule,
        drifted=drift,
        zero_drift=not drift,
    )
    return layout, report


# ---------- CLI ----------
def main(argv):
    def take(i):
        return argv[i + 1]

    intent_p, cat_p, ref_p = argv[1], argv[2], argv[3]
    out_p, guard_p = None, None
    params = dict(P)
    ref = None
    i = 4
    while i < len(argv):
        if argv[i] == '-o':
            out_p = take(i)
            i += 2
        elif argv[i] == '--guard-report':
            guard_p = take(i)
            i += 2
        elif argv[i] == '--param':
            k, _, v = take(i).partition('=')
            params[k] = (json.loads(v) if v.startswith('{')
                         else int(v) if v.lstrip('-').isdigit() else float(v))
            i += 2
        else:
            raise SystemExit('未知参数: %s' % argv[i])
    if ref_p != '-':
        with io.open(ref_p, encoding='utf-8') as f:
            ref = json.load(f)
    intent = load_yaml(intent_p)
    with io.open(cat_p, encoding='utf-8') as f:
        cat = json.load(f)
    layout, structure = rules(intent, cat, params, ref)
    layout, report = guard(layout, structure, params)
    with io.open(out_p, 'w', encoding='utf-8') as f:
        json.dump(layout, f, ensure_ascii=False, indent=2)
    if guard_p:
        with io.open(guard_p, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print('layout-engine:', len(layout['nodes']), 'nodes,',
          len(layout['buses']), 'buses;',
          'guard 零漂移(%d 条 REQUIRED 全部规则点自洽)'
          % report['constraints'] if report['zero_drift']
          else 'guard 微调: %s' % sorted(report['drifted']))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
