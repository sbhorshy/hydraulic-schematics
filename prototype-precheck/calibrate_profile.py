# -*- coding: utf-8 -*-
"""#3 校准基准：从两张成品图实测构图指标。

对「构图预算定档」提供实测打底：阈值不能拍脑袋，先看两张已人工验证的图长什么样。
输出逐图汇总表（折返/绕行比/交叉/间距/最短段），供盘问会话逐项拍板。

用法: python calibrate_profile.py
"""
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHEETS = [
    ('整机/SysML', os.path.join(HERE, '..', 'aircraft_hydraulic_system_schematic.svg')),
    ('1#系统/L0', os.path.join(HERE, '..', '已标注', '1#系统原理图', '1#系统原理图.svg')),
]
LINE_CLS_A = {'hi', 'med', 'lo', 'sig', 'mech'}          # SysML 链路线类
LINE_CLS_B = {'ln-suction', 'ln-pressure', 'ln-return', 'ln-case_drain'}


def load(path):
    with open(path, encoding='utf-8') as f:
        return f.read()


def polylines_sysml(s):
    """只取真走线：带 data-sysml-line 属性的 path（阀件内部笔画、图例样线不算）。"""
    out = []
    for m in re.finditer(r'<path[^>]*\bclass="(%s)"[^>]*data-sysml-line="[^"]+"[^>]*\bd="([^"]+)"'
                         % '|'.join(LINE_CLS_A), s):
        cls, d = m.groups()
        pts, cur = [], None
        for tok in re.finditer(r'([MHVL])\s*(-?[\d.]+)(?:\s+(-?[\d.]+))?', d):
            k, a, b = tok.group(1), float(tok.group(2)), tok.group(3)
            if k == 'M':
                cur = (a, float(b)); pts.append(cur)
            elif k == 'L':
                cur = (a, float(b)); pts.append(cur)
            elif k == 'H':
                cur = (a, cur[1]); pts.append(cur)
            elif k == 'V':
                cur = (cur[0], a); pts.append(cur)
        if len(pts) >= 2:
            out.append((cls, pts))
    return out


def polylines_l0(s):
    out = []
    for m in re.finditer(r'<polyline[^>]*class="(%s)"[^>]*points="([^"]+)"' % '|'.join(LINE_CLS_B), s):
        cls, raw = m.groups()
        pts = [tuple(float(v) for v in p.split(',')) for p in raw.split()]
        if len(pts) >= 2:
            out.append((cls.split('-', 1)[1], pts))
    return out


def turns(pts):
    """方向变化次数；U 形回折(180°)也算一次折返。"""
    dirs = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x1 - x0) >= abs(y1 - y0):
            dirs.append('H' if x1 >= x0 else 'h')
        else:
            dirs.append('V' if y1 >= y0 else 'v')
    return sum(1 for i in range(1, len(dirs))
               if dirs[i] != dirs[i - 1] or dirs[i][0] != dirs[i - 1][0]), dirs


def seg_len(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) if (
        a[0] == b[0] or a[1] == b[1]) else math.hypot(a[0] - b[0], a[1] - b[1])


def measure(tag, pls, s):
    n_seg = n_turn = 0
    t_lens, ratios, per_pl_turns = [], [], []
    min_seg, max_turns = 9e9, 0
    segs_all = []
    for _, pts in pls:
        n_seg += len(pts) - 1
        t, _dirs = turns(pts)
        n_turn += t
        max_turns = max(max_turns, t)
        per_pl_turns.append(t)
        manhattan = abs(pts[-1][0] - pts[0][0]) + abs(pts[-1][1] - pts[0][1])
        length = sum(seg_len(a, b) for a, b in zip(pts, pts[1:]))
        if manhattan > 0:
            ratios.append(length / manhattan)
        for a, b in zip(pts, pts[1:]):
            L = seg_len(a, b)
            min_seg = min(min_seg, L)
            t_lens.append(L)
            segs_all.append((a, b))
    # 交叉计数：正交线段交点，端点重合不算，粗略去重
    crossings = 0
    def on_seg(p, a, b):
        return (min(a[0], b[0]) <= p[0] <= max(a[0], b[0])
                and min(a[1], b[1]) <= p[1] <= max(a[1], b[1]))
    for i in range(len(segs_all)):
        (ax0, ay0), (ax1, ay1) = segs_all[i]
        ha = ay0 == ay1
        for j in range(i + 1, len(segs_all)):
            (bx0, by0), (bx1, by1) = segs_all[j]
            hb = by0 == by1
            try:
                if ha and not hb:   # 水平 × 垂直
                    x, y = bx0, ay0
                elif hb and not ha:
                    x, y = ax0, by0
                else:
                    continue
                ix, iy = segs_all[i][0], None
                if on_seg((x, y), segs_all[i][0], segs_all[i][1]) and \
                   on_seg((x, y), segs_all[j][0], segs_all[j][1]):
                    # 端点相接(T型汇入)不算交叉
                    ends = set()
                    for sg in (segs_all[i], segs_all[j]):
                        ends.add((round(sg[0][0], 1), round(sg[0][1], 1)))
                        ends.add((round(sg[1][0], 1), round(sg[1][1], 1)))
                    if (round(x, 1), round(y, 1)) in ends:
                        continue
                    crossings += 1
            except ZeroDivisionError:
                pass
    bridges = len(re.findall(r'class="(bridge|br-arc)', s))
    junctions = len(re.findall(r'class="(junction|jn)"', s))
    # 节点框最小间隙（data-node 元素的 image/g 内 rect 近似）
    boxes = []
    for m in re.finditer(r'data-node="([^"]+)"', s):
        pass
    texts = len(re.findall(r'<text[ >]', s))
    return dict(
        tag=tag, polylines=len(pls), segments=n_seg,
        turns_total=n_turn, turns_max_single=max_turns,
        turn_dist=sorted(per_pl_turns, reverse=True)[:6],
        detour_max=round(max(ratios), 3) if ratios else None,
        detour_p90=round(sorted(ratios)[int(.9 * (len(ratios) - 1))], 3) if ratios else None,
        min_segment=round(min_seg, 1),
        crossings_raw=crossings, bridge_arcs=bridges, junctions=junctions, texts=texts)


for tag, path in SHEETS:
    s = load(path)
    pls = polylines_sysml(s) + polylines_l0(s)
    r = measure(tag, pls, s)
    print('== %s == (%s)' % (tag, os.path.relpath(path, HERE)))
    for k, v in r.items():
        print('  %-16s %s' % (k, v))
