# -*- coding: utf-8 -*-
"""#19 布局寻优层实验：以 B1–B7 为能量函数的叠加微调。

票面问题：正式布局器（layout_engine.py，方案乙）输出上叠一层小规模邻域搜索
（挪位/换行/母线微调，cost=B1–B7 加权），看 B3 能否从 2.373 压进预算 1.5、
其余指标是否劣化。能→走廊规则沉淀回规则层；不能→披露"属走廊结构问题"。

评估器与 proto_validate.py 的构图预算面板同口径（B2/B3/B4 折线统计、
B1 桥接后残余交叉、B5 盒净距），并在种子处对齐官方报告数值后才参与搜索。
几何真值来自进程内复刻 proto_render 的出图管线（place→wire→wire_taps→
find_crossings→split_h），与落盘 SVG 同源，不经文本往返。

能量取字典序三元组（违限项数, B3 超预算量, 走线总长）：
B1 交叉、B2 折返超限、B3 非豁免超 1.5、B4<8、B5<40 各记一项违限；
B3 预算边界豁免（边界端子走廊 ≤4）与 validate 同判，豁免线不驱动寻优。

用法:
  python proto_optimize.py [种子.layout.json] [-o 前缀] [--kick N]
输出: <前缀>.layout.json / <前缀>-opt-log.json
"""
import copy
import io
import json
import os
import random
import sys
import time

import proto_render as R

HERE = os.path.dirname(os.path.abspath(__file__))

# 寻优循环内 place() 反复读符号文件,缓存之(返回值只被读取,不被改写)。
_read_symbol_orig = R.read_symbol
_read_symbol_cache = {}


def _cached_read_symbol(path):
    if path not in _read_symbol_cache:
        _read_symbol_cache[path] = _read_symbol_orig(path)
    return _read_symbol_cache[path]


R.read_symbol = _cached_read_symbol

BOUNDARY_TERMINALS = [(1480.0, 300.0), (1480.0, 700.0), (60.0, 514.4)]
B3_BUDGET, B3_BOUNDARY = 1.5, 4.0
B4_BUDGET, B5_BUDGET = 8.0, 40.0
B2_SINGLE, B2_TOTAL = 3, 40
CANVAS_W, CANVAS_H, SHIFT = 1680, 1390, 30


# ---------- 评估器：与 proto_validate 构图预算面板同口径 ----------

def turns_of(pts):
    dirs = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x1 - x0) >= abs(y1 - y0):
            dirs.append('H' if x1 >= x0 else 'h')
        else:
            dirs.append('V' if y1 >= y0 else 'v')
    return sum(1 for i in range(1, len(dirs))
               if dirs[i] != dirs[i - 1] or dirs[i][0] != dirs[i - 1][0])


def near_terminal(p):
    return any(abs(p[0] - t[0]) < 3 and abs(p[1] - t[1]) < 3
               for t in BOUNDARY_TERMINALS)


def seg_rect_hit(p0, p1, rect, tol=2.0):
    """线段是否穿越矩形内部(仅正交段)。返回穿越长度。同 proto_validate。"""
    x0, y0 = p0
    x1, y1 = p1
    rx0, ry0, rx1, ry1 = rect
    rx0, ry0, rx1, ry1 = rx0 + tol, ry0 + tol, rx1 - tol, ry1 - tol
    if rx1 <= rx0 or ry1 <= ry0:
        return 0.0
    if abs(y1 - y0) < 0.5:
        if not (ry0 < y0 < ry1):
            return 0.0
        a, b = sorted((x0, x1))
        return max(0.0, min(b, rx1) - max(a, rx0))
    if abs(x1 - x0) < 0.5:
        if not (rx0 < x0 < rx1):
            return 0.0
        a, b = sorted((y0, y1))
        return max(0.0, min(b, ry1) - max(a, ry0))
    return 0.0


def bpanel(L, intent, catalog):
    """进程内渲染并量 B1–B5（B6/B7 与 validate 同批不测）+ 硬缺陷 V2/V13。

    只有 B 面板的能量会把 WARN 级指标换成 FAIL 级缺陷（run A 实测：
    删顶走廊使 B3 达标,代价是回油线横穿油箱/泵本体——V2 两处 fail）。
    V2（穿符号本体段数）与 V13（非豁免共线重叠对数）以硬违限进能量;
    V16 依赖 PNG 像素回读,不复刻,由官方链仲裁。
    """
    s = R.Sheet(intent, L, catalog)
    s.place()
    s.build_textboxes()
    _segs, junc, _bus, _polys = s.wire()
    s.wire_taps()
    cross = s.find_crossings(junc, s.polys)
    polys = []
    for lt, pts in s.polys:
        for run in s.split_h(pts, cross):
            polys.append((lt, run))
    portxy = {}
    for (inst, _pid), (px, py, _a) in s.abs.items():
        portxy.setdefault(inst, []).append((px, py))
    ports_flat = [q for lst in portxy.values() for q in lst]
    boxes = {inst: (nd['x'], nd['y'], nd['x'] + nd['w'], nd['y'] + nd['h'])
             for inst, nd in L['nodes'].items()}

    turn_total = turn_max = 0
    ratios = []            # (ratio, pts, exempt)
    min_seg = 9e9
    length_all = 0.0
    for _c, pts in polys:
        t = turns_of(pts)
        turn_total += t
        turn_max = max(turn_max, t)
        man = abs(pts[-1][0] - pts[0][0]) + abs(pts[-1][1] - pts[0][1])
        ln = sum(abs(a[0] - b[0]) + abs(a[1] - b[1])
                 for a, b in zip(pts, pts[1:]))
        length_all += ln
        if man > 0:
            exempt = (ln / man > B3_BUDGET and
                      (near_terminal(pts[0]) or near_terminal(pts[-1])))
            ratios.append((ln / man, pts, exempt))
        for a, b in zip(pts, pts[1:]):
            min_seg = min(min_seg, abs(a[0] - b[0]) + abs(a[1] - b[1]))

    segs_all = [(c, pts[k], pts[k + 1])
                for c, pts in polys for k in range(len(pts) - 1)]

    # B1 桥接后残余非连通交叉(端点相接的 T 型汇入不算)。
    b1 = 0
    for i in range(len(segs_all)):
        _c1, a1, b1p = segs_all[i]
        h1 = abs(b1p[1] - a1[1]) < 0.6
        for j in range(i + 1, len(segs_all)):
            _c2, a2, b2 = segs_all[j]
            h2 = abs(b2[1] - a2[1]) < 0.6
            if h1 == h2:
                continue
            x, y = (a2[0], a1[1]) if h1 else (a1[0], a2[1])

            def on(p, s0, e0):
                return (min(s0[0], e0[0]) - 0.5 <= x <= max(s0[0], e0[0]) + 0.5
                        and min(s0[1], e0[1]) - 0.5 <= y <= max(s0[1], e0[1]) + 0.5)
            if not (on((x, y), a1, b1p) and on((x, y), a2, b2)):
                continue
            ends = {(round(q[0], 1), round(q[1], 1))
                    for q in (segs_all[i][1], segs_all[i][2],
                              segs_all[j][1], segs_all[j][2])}
            if (round(x, 1), round(y, 1)) in ends:
                continue
            b1 += 1

    # V2 走线穿越符号本体:段端点落在框缘(±3)或该框端口上的是接线,豁免。
    v2 = 0
    for _c, pts in polys:
        for k in range(len(pts) - 1):
            for inst, bx in boxes.items():
                on_a = (abs(pts[k][0] - bx[0]) < 3 or abs(pts[k][0] - bx[2]) < 3
                        or abs(pts[k][1] - bx[1]) < 3 or abs(pts[k][1] - bx[3]) < 3)
                on_b = (abs(pts[k + 1][0] - bx[0]) < 3
                        or abs(pts[k + 1][0] - bx[2]) < 3
                        or abs(pts[k + 1][1] - bx[1]) < 3
                        or abs(pts[k + 1][1] - bx[3]) < 3)
                port_at = any(abs(pts[q][0] - px) < 3 and abs(pts[q][1] - py) < 3
                              for q in (k, k + 1)
                              for px, py in portxy.get(inst, ()))
                if on_a or on_b or port_at:
                    continue
                if seg_rect_hit(pts[k], pts[k + 1], bx, tol=3.0) > 6.0:
                    v2 += 1

    # V13 共线重叠(>6 且非"≤25 并汇于同一端口"豁免)。
    v13 = 0
    for i in range(len(segs_all)):
        _c1, a1, b1p = segs_all[i]
        h1 = abs(b1p[1] - a1[1]) < 0.6
        for j in range(i + 1, len(segs_all)):
            _c2, a2, b2 = segs_all[j]
            h2 = abs(b2[1] - a2[1]) < 0.6
            if h1 != h2:
                continue
            if h1:
                if abs(a1[1] - a2[1]) > 1.2:
                    continue
                lo1, hi1 = sorted((a1[0], b1p[0]))
                lo2, hi2 = sorted((a2[0], b2[0]))
            else:
                if abs(a1[0] - a2[0]) > 1.2:
                    continue
                lo1, hi1 = sorted((a1[1], b1p[1]))
                lo2, hi2 = sorted((a2[1], b2[1]))
            ov = min(hi1, hi2) - max(lo1, lo2)
            if ov <= 6:
                continue
            shared = False
            if ov <= 25:
                for (qx, qy) in (a1, b1p, a2, b2):
                    if any(abs(qx - px) < 3 and abs(qy - py) < 3
                           for px, py in ports_flat):
                        shared = True
                        break
            if not shared:
                v13 += 1

    boxes_list = list(boxes.values())
    b5 = None
    for i in range(len(boxes_list)):
        for j in range(i + 1, len(boxes_list)):
            r1, r2 = boxes_list[i], boxes_list[j]
            dx = max(r1[0] - r2[2], r2[0] - r1[2], 0.0)
            dy = max(r1[1] - r2[3], r2[1] - r1[3], 0.0)
            g = (dx * dx + dy * dy) ** 0.5
            if b5 is None or g < b5:
                b5 = g

    live = [r for r, _p, ex in ratios if not ex]
    exempt = ['%.3f' % r for r, _p, ex in ratios
              if ex and r <= B3_BOUNDARY]
    return dict(
        b1=b1,
        b2tot=turn_total, b2max=turn_max,
        b3=round(max(live), 3) if live else 0.0,
        b3_exempt=exempt,
        b4=round(min_seg, 1),
        b5=round(b5, 1) if b5 is not None else None,
        v2=v2, v13=v13,
        length=round(length_all, 1),
    )


def violations(bp):
    v = (bp['b1'] + bp['v2'] + bp['v13'])
    if bp['b2max'] > B2_SINGLE or bp['b2tot'] > B2_TOTAL:
        v += 1
    if bp['b3'] > B3_BUDGET + 1e-9:
        v += 1
    if bp['b4'] < B4_BUDGET - 1e-9:
        v += 1
    if bp['b5'] is not None and bp['b5'] < B5_BUDGET - 1e-9:
        v += 1
    # 不劣化约束（run B）：其余指标不得比种子差——纯预算能量会把
    # B4/B5 裕量吃到地板（run A 实测 10.0→8.0、43.0→40.0）。
    for k, better in (('b1', min), ('b2tot', min), ('b2max', min),
                      ('b4', max), ('b5', max)):
        if NO_REGRESSION.get(k) is None:
            continue
        s, c = NO_REGRESSION[k], bp[k]
        if better is min and c > s + 1e-9:
            v += 1
        if better is max and c < s - 1e-9:
            v += 1
    return v


def energy(bp):
    return (violations(bp), round(max(0.0, bp['b3'] - B3_BUDGET), 3),
            bp['length'])


# ---------- 邻域动作集：换行（lanes/vlanes）、母线微调、元件挪位 ----------

LANE_GRID, VLANE_GRID = 20, 20

# 不劣化下限（run B 生效）：main() 用种子面板填充；置空则退回纯预算能量。
NO_REGRESSION = {}


def neighbors(L):
    ms = []
    lanes = L.get('lanes') or []
    vlanes = L.get('vlanes') or []
    for i in range(len(lanes)):
        for dy in (-40, -20, -10, 10, 20, 40):
            ms.append(('lane_move', i, dy))
        ms.append(('lane_del', i))
    for i in range(len(vlanes)):
        for dx in (-40, -20, -10, 10, 20, 40):
            ms.append(('vlane_move', i, dx))
        ms.append(('vlane_del', i))
    for y in range(140, 1301, LANE_GRID):
        if all(abs(y - ly) >= 15 for ly in lanes):
            ms.append(('lane_add', y))
    for x in range(60, int(CANVAS_W - SHIFT) - 60, VLANE_GRID):
        if all(abs(x - cx) >= 15 for cx in vlanes) and x not in (20,):
            ms.append(('vlane_add', x))
    for b, bd in L['buses'].items():
        for dx in (-20, -10, 10, 20):
            ms.append(('bus_move', b, dx))
    for inst, nd in L['nodes'].items():
        for dx, dy in ((-20, 0), (20, 0), (0, -20), (0, 20)):
            ms.append(('node_move', inst, dx, dy))
    return ms


def apply_move(L, m):
    L = copy.deepcopy(L)
    op = m[0]
    if op == 'lane_move':
        L['lanes'][m[1]] += m[2]
    elif op == 'lane_del':
        del L['lanes'][m[1]]
    elif op == 'lane_add':
        L['lanes'] = sorted((L.get('lanes') or []) + [m[1]])
    elif op == 'vlane_move':
        L['vlanes'][m[1]] += m[2]
    elif op == 'vlane_del':
        del L['vlanes'][m[1]]
    elif op == 'vlane_add':
        L['vlanes'] = sorted((L.get('vlanes') or []) + [m[1]])
    elif op == 'bus_move':
        L['buses'][m[1]]['x'] += m[2]
    elif op == 'node_move':
        nd = L['nodes'][m[1]]
        nd['x'] += m[2]
        nd['y'] += m[3]
    # 解空间钳位：走廊在图幅内且互不贴脸，母线/元件守住画布可用区。
    L['lanes'] = [ly for ly in L.get('lanes', []) if 60 <= ly <= 1330]
    L['vlanes'] = [cx for cx in L.get('vlanes', []) if 20 <= cx <= CANVAS_W - SHIFT]
    for bd in L['buses'].values():
        if not (60 <= bd['x'] <= CANVAS_W - SHIFT):
            return None
    for nd in L['nodes'].values():
        if not (60 <= nd['x'] and nd['x'] + nd['w'] <= CANVAS_W - SHIFT):
            return None
        if not (60 <= nd['y'] and nd['y'] + nd['h'] <= 1330):
            return None
    if len(set(L.get('lanes', []))) != len(L.get('lanes', [])):
        return None
    return L


# ---------- 搜索：全邻域最陡下降 + 随机踢散重启 ----------

def climb(L0, intent, catalog, log, tag):
    bp = bpanel(L0, intent, catalog)
    cur, e = L0, energy(bp)
    log.append({'tag': tag, 'step': 0, 'move': None, 'energy': e, 'bp': bp})
    step = 0
    while True:
        step += 1
        best, bestm, bestbp, bestL = e, None, bp, cur
        for m in neighbors(cur):
            cand = apply_move(cur, m)
            if cand is None:
                continue
            cbp = bpanel(cand, intent, catalog)
            ce = energy(cbp)
            if ce < best:
                best, bestm, bestbp, bestL = ce, m, cbp, cand
        if bestm is None:
            break
        cur, bp, e = bestL, bestbp, best
        log.append({'tag': tag, 'step': step, 'move': repr(bestm),
                    'energy': e, 'bp': bp})
        print('  [%s] step %d %s -> %s b3=%.3f len=%d'
              % (tag, step, bestm, e[:2], bp['b3'], bp['length']))
    return cur, bp, e


def main():
    argv = sys.argv[1:]
    val_flags = {'-o', '--kick'}
    pos = [a for i, a in enumerate(argv)
           if not a.startswith('-') and (i == 0 or argv[i - 1] not in val_flags)]
    seed_path = os.path.join(HERE, pos[0] if pos else '1#系统乙.layout.json')
    prefix = '1#系统乙-optB'
    kicks = 4
    if '-o' in argv:
        prefix = argv[argv.index('-o') + 1]
    if '--kick' in argv:
        kicks = int(argv[argv.index('--kick') + 1])

    import proto_render  # noqa: F401  (load_yaml 同源)
    intent = R.load_yaml(os.path.join(HERE, '1#系统.intent.yaml'))
    with io.open(os.path.join(HERE, 'component-catalog.json'),
                 encoding='utf-8') as f:
        catalog = json.load(f)
    with io.open(seed_path, encoding='utf-8') as f:
        seed = json.load(f)

    t0 = time.time()
    bp0 = bpanel(copy.deepcopy(seed), intent, catalog)
    print('种子评估 %.2fs: %s' % (time.time() - t0, bp0))
    print('种子能量: %s' % (energy(bp0),))
    if '--pure-budget' not in argv:
        NO_REGRESSION.update(b1=bp0['b1'], b2tot=bp0['b2tot'],
                             b2max=bp0['b2max'], b4=bp0['b4'],
                             b5=bp0['b5'])
        print('不劣化下限(取种子值):', dict(NO_REGRESSION))

    log = []
    bestL, bestbp, beste = climb(seed, intent, catalog, log, 'main')
    rng = random.Random(19)
    for k in range(kicks):
        L = copy.deepcopy(bestL)
        pool = neighbors(L)
        for _ in range(3):
            m = rng.choice(pool)
            L = apply_move(L, m) or L
        L2, bp2, e2 = climb(L, intent, catalog, log, 'kick%d' % k)
        if e2 < beste:
            bestL, bestbp, beste = L2, bp2, e2
        print('kick%d -> %s (best %s)' % (k, e2[:2], beste[:2]))

    with io.open(os.path.join(HERE, prefix + '.layout.json'), 'w',
                 encoding='utf-8') as f:
        json.dump(bestL, f, ensure_ascii=False, indent=2)
    with io.open(os.path.join(HERE, prefix + '-opt-log.json'), 'w',
                 encoding='utf-8') as f:
        json.dump({'seed': os.path.basename(seed_path), 'seed_bp': bp0,
                   'final_bp': bestbp, 'final_energy': beste,
                   'log': log}, f, ensure_ascii=False, indent=1)
    print('最终: %s bp=%s' % (beste, bestbp))
    print('写出 %s.layout.json / -opt-log.json' % prefix)
    return 0


if __name__ == '__main__':
    sys.exit(main())
