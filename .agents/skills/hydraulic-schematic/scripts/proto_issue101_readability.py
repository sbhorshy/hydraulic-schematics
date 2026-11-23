# -*- coding: utf-8 -*-
"""#101 一次性原型：B1–B7 之外的图面可读性候选指标（不进 main）。

票面问题：哪些读图任务能说明 B1–B7 之外还有改进空间，哪些指标值得进入布局评价。

输入是 validation-report.json 里已核对的 topology / geometry / text_geometry，
不读 DOM、不渲染、不启动浏览器。全部是纯函数：同一份模型既喂挖掘脚本，
也喂单文件决策页；日后若采纳，可原样抬进 layout_clearance / 快速评估器。

候选指标（票面六项）：
  M1 主线折点        沿一条读图主线（跨元件、跨母线）累计的真实转角数
  M2 方向一致性      主线上逆主导方向的走线长度占比、折返事件数
  M3 标签距离        标签墨迹框到所属元件足迹的净距；到最近非所属元件的净距
  M4 走廊穿插        不同网络的平行走线在阅读带内并行的次数与长度
  M5 端口末段        从端口沿画线直走到第一个转角的长度
  M6 枢纽/三通/桥    三通点间距、三通点到转角的距离、跨线桥到最近节点的距离

用法:
  python proto_issue101_readability.py <workdir> [--json]
"""
from __future__ import print_function

import argparse
import io
import json
import os

TOL = 0.6

# 阈值是待验证的提案，不是预算。决策页可调，用来看排序是否随阈值翻转。
PARAMS = dict(
    corridor_w=16.0,     # M4 并行阅读带（px）
    corridor_min=24.0,   # M4 计一次穿插所需的最短并行长度（px）
    label_far=40.0,      # M3 标签离所属元件超过此距离算“远离”（px）
    stub_short=16.0,     # M5 端口末段短于此值算“短桩”（px）
    junction_min=30.0,   # M6 两个三通点小于此间距算“贴脸”（px）
)

# 读图主线：每一跳在同一管网内沿实际画线走；相邻两跳之间穿过一个元件符号。
MAIN_LINES = [
    ('吸油 油箱→EDP', [('TANK-001.suction_out', 'FSOV-001.main_upper'),
                   ('FSOV-001.main_lower', 'EDP-001.suction')]),
    ('吸油 油箱→EMP', [('TANK-001.suction_out', 'EMP-001.suction')]),
    ('压力 EDP→USER-005', [('EDP-001.pressure_out', 'PF-001.inlet'),
                      ('PF-001.outlet', 'PRV-001.inlet'),
                      ('PRV-001.outlet', 'USER-005.pressure_in')]),
    ('压力 EMP→USER-001', [('EMP-001.pressure_out', 'PF-001.inlet'),
                      ('PF-001.outlet', 'PRV-001.inlet'),
                      ('PRV-001.outlet', 'USER-001.pressure_in')]),
    ('回油 USER-003→油箱', [('USER-003.return_out', 'RF-001.inlet'),
                      ('RF-001.outlet', 'TANK-001.return_in')]),
    ('壳体回油 EDP→油箱', [('EDP-001.case_drain', 'CDF-001.inlet'),
                      ('CDF-001.outlet', 'TANK-001.return_in')]),
    ('自增压 @PRESS→油箱', [('EDP-001.pressure_out', 'PRV-002.inlet'),
                      ('PRV-002.outlet', 'TANK-001.bootstrap_pressure_in')]),
    ('蓄压 @PRESS→ACC', [('EDP-001.pressure_out', 'PRV-002.inlet'),
                     ('PRV-002.outlet', 'ACC-001.hydraulic_port')]),
]


# ---------- 几何小工具 ----------

def orient(a, b):
    return 'H' if abs(b[1] - a[1]) < TOL else 'V'


def seg_len(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def pt_dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


def rect_dist(a, b):
    """两个 [x0,y0,x1,y1] 矩形的欧氏净距（相交或相贴为 0）。"""
    dx = max(b[0] - a[2], a[0] - b[2], 0.0)
    dy = max(b[1] - a[3], a[1] - b[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


def dir_of(p, q):
    """有向直线段的方向：R / L / D / U。"""
    return (('R' if q[0] > p[0] else 'L') if orient(p, q) == 'H'
            else ('D' if q[1] > p[1] else 'U'))


def runs_of(pts):
    """折线拆成最长直线段 [(p0, p1)]；共线存储切分不算折点。"""
    out = []
    for a, b in zip(pts, pts[1:]):
        if seg_len(a, b) < 1e-9:
            continue
        if out and pt_dist(out[-1][1], a) < TOL and orient(out[-1][0], out[-1][1]) == orient(a, b):
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def bends_of(pts):
    """真实转角坐标：相邻直线段方向改变处。"""
    r = runs_of(pts)
    return [list(r[i][1]) for i in range(len(r) - 1)]


def _other(segs, s, cur):
    """线段 s 不在顶点 cur 的另一端顶点。"""
    return segs[s]['a'] if segs[s]['b'] == cur else segs[s]['b']


# ---------- 从官方报告建模型 ----------

def _walk(segs, verts, idx, start=None):
    """把一组首尾相接的线段还原成一条折线。start 给定时从靠近它的端点出发。"""
    adj = {}
    for s in idx:
        adj.setdefault(segs[s]['a'], []).append(s)
        adj.setdefault(segs[s]['b'], []).append(s)
    ends = [v for v in adj if len(adj[v]) == 1]
    if start is not None:
        ends.sort(key=lambda v: pt_dist(verts[v]['position'], start))
    if len(ends) != 2:
        raise ValueError('线段组不是一条简单折线（端点 %d 个）' % len(ends))
    pts, used, cur = [verts[ends[0]]['position']], set(), ends[0]
    while True:
        nxt = [s for s in adj[cur] if s not in used]
        if not nxt:
            break
        s = nxt[0]
        used.add(s)
        cur = _other(segs, s, cur)
        pts.append(verts[cur]['position'])
    if len(used) != len(idx):
        raise ValueError('线段组有分叉')
    return [[p[0], p[1]] for p in pts]


def build_model(report):
    """官方报告 -> 规范化模型。坐标全部是根 SVG 用户单位。"""
    geo = report['geometry']['nodes']
    top = report['topology']
    segs, verts = top['segments'], top['vertices']
    net_of = {}
    for ni, net in enumerate(top['networks']):
        for s in net['segments']:
            net_of[s] = ni

    def net(idx):
        nets = sorted({net_of[s] for s in idx if s in net_of})
        return nets[0] if len(nets) == 1 else None

    nodes = {inst: dict(footprint=list(nd['footprint']),
                        ports={pid: dict(p) for pid, p in nd['ports'].items()})
             for inst, nd in geo.items()}
    edges = [dict(anchor=e['anchor'], endpoints=list(e['endpoints']),
                  pts=_walk(segs, verts, e['segments'], e['positions'][0]),
                  network=net(e['segments']),
                  bridge=any(segs[s]['bridge'] for s in e['segments']))
             for e in top['actual_edges']]
    buses = []
    for b in top['buses']:
        idx = [s for s, sg in enumerate(segs) if sg['anchor'] == b['anchor']]
        if idx:
            buses.append(dict(anchor=b['anchor'], name=b['id'], pts=_walk(segs, verts, idx),
                              network=net(idx)))

    boxes = {}
    for tx in report['text_geometry']['texts']:
        own = tx.get('owner') or ''
        if not own.startswith('label:'):
            continue
        bb = tx['bbox']
        o = boxes.setdefault(own.split(':', 1)[1], list(bb))
        o[0], o[1] = min(o[0], bb[0]), min(o[1], bb[1])
        o[2], o[3] = max(o[2], bb[2]), max(o[3], bb[3])
    labels = [dict(owner=k, bbox=v) for k, v in sorted(boxes.items())]

    vad = {}
    for si, sg in enumerate(segs):
        vad.setdefault(sg['a'], []).append(si)
        vad.setdefault(sg['b'], []).append(si)
    return dict(nodes=nodes, edges=edges, buses=buses, labels=labels, segs=segs,
                verts=verts, vad=vad, bridges=list(top.get('bridges') or []))


def classify_vertices(model):
    """三通点 = 度≥3 的顶点；转角 = 度 2 且两段方向不同的顶点。"""
    segs, verts, vad = model['segs'], model['verts'], model['vad']
    junction, bend = [], []
    for vi, v in enumerate(verts):
        inc = vad.get(vi, [])
        if v['degree'] >= 3:
            junction.append(list(v['position']))
        elif len(inc) == 2:
            dirs = [orient(v['position'], segs[s]['start'] if segs[s]['b'] == vi else segs[s]['end'])
                    for s in inc]
            if dirs[0] != dirs[1]:
                bend.append(list(v['position']))
    model['junction'], model['bend'] = junction, bend


def straight_run(model, v0):
    """从顶点沿共线线段直走，返回经过的点（到转角、断头或不共线的分叉为止）。

    同一端口引出两条边时，开头会有一段重叠的存储切分；它们同向，任取其一。
    """
    segs, verts, vad = model['segs'], model['verts'], model['vad']
    pts, used, cur = [verts[v0]['position']], set(), v0
    while True:
        cands = [s for s in vad.get(cur, []) if s not in used]
        want = (dir_of(pts[-2], pts[-1]) if len(pts) >= 2
                else dir_of(pts[-1], verts[_other(segs, cands[0], cur)]['position']) if cands else None)
        cands = [s for s in cands
                 if dir_of(pts[-1], verts[_other(segs, s, cur)]['position']) == want]
        if not cands:
            break
        s = cands[0]
        used.add(s)
        cur = _other(segs, s, cur)
        pts.append(verts[cur]['position'])
    return pts


def hop_path(model, a, b):
    """同一管网内从端子 a 走到端子 b 的折线（管网是树，路径唯一）。"""
    verts, segs, vad = model['verts'], model['segs'], model['vad']

    def vertex(terminal):
        hits = [i for i, v in enumerate(verts) if terminal in v['terminals']]
        if len(hits) != 1:
            raise ValueError('端子不唯一: %s (%d)' % (terminal, len(hits)))
        return hits[0]

    va, vb = vertex(a), vertex(b)
    prev, queue = {va: None}, [va]
    while queue and vb not in prev:
        cur = queue.pop(0)
        for s in vad.get(cur, []):
            nxt = _other(segs, s, cur)
            if nxt not in prev:
                prev[nxt] = (cur, s)
                queue.append(nxt)
    if vb not in prev:
        raise ValueError('同一管网内不可达: %s -> %s' % (a, b))
    steps, cur = [], vb
    while prev[cur] is not None:
        cur, s = prev[cur]
        steps.append(s)
    steps.reverse()
    pts, cur = [list(verts[va]['position'])], va
    for s in steps:
        cur = _other(segs, s, cur)
        pts.append(list(verts[cur]['position']))
    return pts, [segs[s]['anchor'] for s in steps]


# ---------- 六项候选指标 ----------

def metric_main_lines(model):
    """M1 主线折点 + M2 方向一致性。

    相邻两跳之间隔着元件符号，不连线：各跳的直线段直接首尾相接成列表，
    不跨元件合并，避免把穿元件的虚线段算成走线。
    """
    out = []
    for name, hops in MAIN_LINES:
        runs, anchors, pts_all = [], [], []
        for a, b in hops:
            pts, anc = hop_path(model, a, b)
            anchors += anc
            runs += runs_of(pts)
            pts_all.append(pts)
        length = sum(seg_len(p, q) for p, q in runs)
        fwd = {'R': 0.0, 'L': 0.0, 'D': 0.0, 'U': 0.0}
        dirs = []
        for p, q in runs:
            d = dir_of(p, q)
            fwd[d] += seg_len(p, q)
            dirs.append(d)
        # 折返：同一轴上先后两段方向相反（正交走线里两段之间必隔着垂直段）。
        same_axis = [[d for d in dirs if d in axis] for axis in ('RL', 'DU')]
        reversals = sum(1 for seq in same_axis for x, y in zip(seq, seq[1:]) if x != y)
        backward = min(fwd['R'], fwd['L']) + min(fwd['D'], fwd['U'])
        out.append(dict(name=name, bends=sum(len(runs_of(p)) - 1 for p in pts_all),
                        bend_pts=[p for pts in pts_all for p in bends_of(pts)],
                        length=round(length, 1), backward=round(backward, 1),
                        consistency=None if not length else round(1.0 - backward / length, 3),
                        reversals=reversals, pts=pts_all, anchors=sorted(set(anchors))))
    return out


def metric_labels(model):
    """M3 标签距离：到所属元件的净距、到最近非所属元件的净距。"""
    nodes, out = model['nodes'], []
    for lab in model['labels']:
        own = lab['owner']
        if own not in nodes:
            continue
        rivals = sorted((rect_dist(lab['bbox'], nd['footprint']), inst)
                        for inst, nd in nodes.items() if inst != own)
        out.append(dict(owner=own, bbox=lab['bbox'], gap=round(rect_dist(lab['bbox'], nodes[own]['footprint']), 1),
                        rival=rivals[0][1] if rivals else None,
                        rival_gap=round(rivals[0][0], 1) if rivals else None,
                        footprint=nodes[own]['footprint']))
    return out


def metric_corridor(model, w, min_len, main_anchors):
    """M4 不同网络的平行走线在阅读带内的并行。"""
    runs = [dict(anchor=e['anchor'], network=e['network'], run=r, main=e['anchor'] in main_anchors)
            for e in model['edges'] for r in runs_of(e['pts'])]
    runs += [dict(anchor=b['anchor'], network=b['network'], run=r,
                  main=b['anchor'] in main_anchors or b['name'] in main_anchors)
             for b in model['buses'] for r in runs_of(b['pts'])]
    events = []
    for i, a in enumerate(runs):
        for b in runs[i + 1:]:
            if a['network'] is None or a['network'] == b['network']:
                continue
            (a0, a1), (b0, b1) = a['run'], b['run']
            o = orient(a0, a1)
            if o != orient(b0, b1):
                continue
            axis, cross = (0, 1) if o == 'H' else (1, 0)
            d = abs(a0[cross] - b0[cross])
            if d > w + 1e-9:
                continue
            lo1, hi1 = sorted((a0[axis], a1[axis]))
            lo2, hi2 = sorted((b0[axis], b1[axis]))
            overlap = min(hi1, hi2) - max(lo1, lo2)
            if overlap < min_len - 1e-9:
                continue
            events.append(dict(a=a['anchor'], b=b['anchor'], d=round(d, 1),
                               overlap=round(overlap, 1), main=bool(a['main'] or b['main']),
                               ra=[list(a0), list(a1)], rb=[list(b0), list(b1)]))
    return events


def metric_stubs(model):
    """M5 端口末段：从端口沿画线直走到第一个转角的长度，以及是否沿锚向离开。"""
    out = []
    for vi, v in enumerate(model['verts']):
        port = next((t for t in v['terminals'] if '.' in t), None)
        if port is None or not model['vad'].get(vi):
            continue  # 未接线的悬空端口没有末段
        pts = straight_run(model, vi)
        inst, pid = port.split('.', 1)
        direction = model['nodes'][inst]['ports'][pid]['direction']
        dot = sum((pts[1][k] - pts[0][k]) * direction[k] for k in (0, 1))
        out.append(dict(port=port, run=[list(p) for p in pts],
                        length=round(seg_len(pts[0], pts[-1]), 1), aligned=dot > 0))
    return out


def metric_junctions(model):
    """M6 三通点间距、三通点到转角、跨线桥到最近节点。"""
    jun, bend = model['junction'], model['bend']

    def closest(points_a, points_b, same_set=False):
        """两组点之间最近的一对；same_set 时只比较不同下标的点。"""
        best = None
        for i, p in enumerate(points_a):
            for k, q in enumerate(points_b):
                if same_set and k <= i:
                    continue
                if best is None or pt_dist(p, q) < best[0]:
                    best = (pt_dist(p, q), p, q)
        return None if best is None else dict(d=round(best[0], 1), a=list(best[1]), b=list(best[2]))

    bridges = []
    for b in model['bridges']:
        own = next((e for e in model['edges'] if b['anchor'] and e['anchor'] == b['anchor']), None)
        own_corners = bends_of(own['pts']) if own else []
        others = [p for p in jun + bend if all(pt_dist(p, q) > TOL for q in own_corners)]
        pos = b['position']

        def nearest(pts):
            return None if not pts else round(min(pt_dist(pos, p) for p in pts), 1)
        bridges.append(dict(pos=list(pos), anchor=b['anchor'],
                            own_gap=nearest(own_corners), other_gap=nearest(others)))
    return dict(junction_gap=closest(jun, jun, same_set=True),
                junction_bend=closest(jun, bend), bridges=bridges)


def metrics_from_model(model, params=None):
    """规范化模型 -> (六项指标摘要, 叠加层证据)。官方报告与进程内两条路共用。"""
    pr = dict(PARAMS, **(params or {}))
    lines = metric_main_lines(model)
    main_anchors = set()
    for ln in lines:
        main_anchors.update(ln['anchors'])
    labels = metric_labels(model)
    events = metric_corridor(model, pr['corridor_w'], pr['corridor_min'], main_anchors)
    stubs = metric_stubs(model)
    j = metric_junctions(model)
    result = dict(
        m1=dict(max=max(l['bends'] for l in lines), sum=sum(l['bends'] for l in lines),
                per_line={l['name']: l['bends'] for l in lines}),
        m2=dict(reversals=sum(l['reversals'] for l in lines),
                backward_frac_max=round(max(1.0 - l['consistency'] for l in lines), 3),
                per_line={l['name']: [l['reversals'], l['backward'], l['length']] for l in lines}),
        m3=dict(gap_max=max(l['gap'] for l in labels),
                gap_mean=round(sum(l['gap'] for l in labels) / len(labels), 1),
                far=[l['owner'] for l in labels if l['gap'] > pr['label_far']],
                ambiguous=[l['owner'] for l in labels
                           if l['rival_gap'] is not None and l['rival_gap'] < l['gap']],
                per_label={l['owner']: [l['gap'], l['rival'], l['rival_gap']] for l in labels}),
        m4=dict(count=len(events), length=round(sum(e['overlap'] for e in events), 1),
                min_gap=None if not events else min(e['d'] for e in events),
                main_count=sum(1 for e in events if e['main']),
                events=[[e['a'], e['b'], e['d'], e['overlap'], e['main']] for e in events]),
        m5=dict(min=min(s['length'] for s in stubs),
                short=[s['port'] for s in stubs if s['length'] < pr['stub_short']],
                misaligned=[s['port'] for s in stubs if not s['aligned']],
                per_port={s['port']: s['length'] for s in stubs}),
        m6=dict(junction_gap=j['junction_gap'], junction_bend=j['junction_bend'],
                bridges=j['bridges'], junctions=len(model['junction'])),
    )
    evidence = dict(
        main_lines=[dict(name=l['name'], hops=l['pts'], bends=l['bend_pts']) for l in lines],
        labels=labels, corridor=events, stubs=stubs,
        junctions=model['junction'], bends=model['bend'],
        bridges=[dict(pos=list(b['position']), anchor=b['anchor']) for b in model['bridges']],
        nodes={k: v['footprint'] for k, v in model['nodes'].items()},
    )
    return result, evidence


def summarize(report, params=None):
    """官方报告 -> (六项指标摘要, 叠加层证据, B1–B7 面板)。"""
    model = build_model(report)
    classify_vertices(model)
    result, evidence = metrics_from_model(model, params)
    panel = {it['id']: dict(status=it['status'], measured=it['measured'])
             for it in report.get('composition_budget', {}).get('items', [])}
    return result, evidence, panel


def _cut_segment(a, b, cut):
    """轴对齐线段 ab 在 cut 中落于其内部的点处切开，返回小线段 [(p, q)]。"""
    horiz = orient(a, b) == 'H'
    axis, cross_ax = (0, 1) if horiz else (1, 0)
    lo, hi = sorted((a[axis], b[axis]))
    inside = sorted(q[axis] for q in cut
                    if abs(q[cross_ax] - a[cross_ax]) < TOL and lo + TOL < q[axis] < hi - TOL)
    chain = [a] + [(t, a[1]) if horiz else (a[0], t) for t in inside] + [b]
    return list(zip(chain, chain[1:]))


def summarize_in_process(layout, intent, catalog, project_dir, params=None):
    """寻优器口径：不起浏览器，直接用渲染器进程内对象算同一组指标。

    走线、端口、三通点取自渲染器自己的对象（与 proto_optimize.bpanel 同源）；
    标签框是布局估计框而不是浏览器墨迹，所以 M3 在进程内只是近似。
    project_dir 是工作目录（内含 symbols/ 与 component-catalog.json）。
    """
    import copy
    import render_l0_sheet as R
    layout = copy.deepcopy(layout)  # place() 会往节点里写派生字段
    s = R.Sheet(intent, layout, catalog, cat_dir=str(project_dir), workdir=str(project_dir))
    s.place()
    s.build_textboxes()
    _segs, junc, _bus, _polys = s.wire()
    s.wire_taps()
    cross = s.find_crossings(junc, s.polys)

    def rnd(p):
        return (round(p[0], 1), round(p[1], 1))

    # ---- 网络身份：沿输入声明做并查集，裸实例按目录 main_path 补出端口 ----
    parent, net_of_anchor = {}, {}
    for name in layout['buses']:
        net_of_anchor['buses.' + name] = '@' + name

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            x = parent[x]
        return x

    def key(token, want):
        return token if token.startswith('@') else '%s.%s' % s.resolve(token, want)

    for pi, p in enumerate(intent['paths']):
        for k, (a, b) in enumerate(zip(p, p[1:])):
            net_of_anchor['paths[%d][%d->%d]' % (pi, k, k + 1)] = key(a, 'out')
            parent[find(key(a, 'out'))] = find(key(b, 'in'))
    for ti, t in enumerate(intent.get('taps') or []):
        net_of_anchor['taps[%d]' % ti] = key(t['sensor'], 'out')
        parent[find(key(t['sensor'], 'out'))] = find(key(t['at'], 'in'))
    net_ids = {}

    def net(anchor):
        root = find(net_of_anchor[anchor])
        net_ids.setdefault(root, len(net_ids))
        return net_ids[root]

    # ---- 顶点与线段：折线在自身顶点、其他折线端点和三通点处切分 ----
    cut = {rnd(pts[k]) for _lt, pts in s.polys for k in (0, -1)}
    cut |= {rnd((x, y)) for x, y in junc}
    verts, vids, segs, edges, buses = [], {}, [], [], []

    def vid(p):
        k = rnd(p)
        if k not in vids:
            vids[k] = len(verts)
            verts.append(dict(position=list(k), terminals=[], degree=0))
        return vids[k]

    for anchor, (_lt, pts) in zip(s.poly_anchors, s.polys):
        rec = dict(anchor=anchor, endpoints=[], pts=[list(p) for p in pts],
                   network=net(anchor), bridge=False)
        if anchor.startswith('buses.'):
            rec['name'] = '@' + anchor.split('.', 1)[1]
            buses.append(rec)
        else:
            edges.append(rec)
        for a, b in zip(pts, pts[1:]):
            for p, q in _cut_segment(a, b, cut):
                segs.append(dict(a=vid(p), b=vid(q), anchor=anchor, bridge=False,
                                 start=list(rnd(p)), end=list(rnd(q))))
    vad = {}
    for si, sg in enumerate(segs):
        vad.setdefault(sg['a'], []).append(si)
        vad.setdefault(sg['b'], []).append(si)
    for vi, v in enumerate(verts):
        v['degree'] = len({segs[sg]['b'] if segs[sg]['a'] == vi else segs[sg]['a']
                           for sg in vad.get(vi, [])})
    for (inst, pid), (x, y, _a) in s.abs.items():
        if rnd((x, y)) in vids:
            verts[vids[rnd((x, y))]]['terminals'].append('%s.%s' % (inst, pid))

    # ---- 元件足迹、端口方向、标签估计框 ----
    anchor_dir = {'right': (1.0, 0.0), 'left': (-1.0, 0.0), 'up': (0.0, -1.0), 'down': (0.0, 1.0)}
    nodes = {}
    for inst, nd in layout['nodes'].items():
        w, h = (nd['_H'], nd['_W']) if nd['_rot'] % 180 else (nd['_W'], nd['_H'])
        nodes[inst] = dict(footprint=[nd['x'], nd['y'], nd['x'] + w, nd['y'] + h],
                           ports={pid: dict(position=[x, y], direction=anchor_dir[a])
                                  for (i, pid), (x, y, a) in s.abs.items() if i == inst})
    labels = [dict(owner=i.split('.', 1)[1], bbox=list(box))
              for i, box in zip(s.textbox_ids, s.textboxes) if i.startswith('label.')]

    model = dict(nodes=nodes, edges=edges, buses=buses, labels=labels, segs=segs, verts=verts,
                 vad=vad, junction=[], bend=[],
                 bridges=[dict(position=[x, y], anchor=None) for x, y, _lt in cross])
    classify_vertices(model)
    return metrics_from_model(model, params)


def load_report(workdir):
    with io.open(os.path.join(workdir, 'validation-report.json'), encoding='utf-8') as f:
        return json.load(f)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('workdir')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()
    rep = load_report(args.workdir)
    res, _ev, panel = summarize(rep)
    print(json.dumps(dict(result=res, params=PARAMS, budget=panel,
                          fail=rep['fail_count'], warn=rep['warn_count']),
                     ensure_ascii=False, indent=1 if args.json else None))
