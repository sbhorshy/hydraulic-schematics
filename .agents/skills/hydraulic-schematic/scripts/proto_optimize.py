# -*- coding: utf-8 -*-
"""#19 布局寻优层：以 B1–B7 为能量函数的叠加微调（#22 沉淀进 skill）。

票面问题（#19 实验）：正式布局器（layout_engine.py，方案乙）输出上叠一层
小规模邻域搜索（挪位/换行/母线微调，cost=B1–B7 加权），看 B3 能否从 2.373
压进预算 1.5、其余指标是否劣化。结论：能（2.373→1.447），已并入布局器
第三阶段（--optimize）；负对照证明纯预算能量不可用（run A：把 WARN 换成
FAIL），必须带硬缺陷项 V2/V13 + 不劣化下限。

B1 使用拆桥前的输入/走线非连通交点，与最终零交叉预算一致。
其余候选几何指标保持轻量近似，最终全量 validate_sheet 校核为权威。
几何真值来自进程内复刻出图管线（place→wire→wire_taps→find_crossings→
split_h），与落盘 SVG 同源，不经文本往返——#22 起复刻对象为 skill 渲染器
render_l0_sheet（与 frozen proto_render 同源，方法级兼容）。

能量取字典序三元组（违限项数, B3 超预算量, 走线总长）：
B1 交叉、B2 折返超限、B3 非豁免超 1.5、B4<8、B5<40 各记一项违限；
B3 预算边界豁免（边界端子走廊 ≤4）与 validate 同判，豁免线不驱动寻优。
边界端子判点：布局 json 可给 "boundary_terminals": [[x,y],...] 覆写；
缺省值为 1# 系统实测知识（披露：新系统接入时应在布局中显式给出）。

用法:
  python proto_optimize.py <种子.layout.json> [--intent INTENT.yaml]
      [--catalog CAT.json] [-o 前缀] [--kick N] [--pure-budget]
输出: <前缀>.layout.json / <前缀>-opt-log.json
"""
import argparse
import copy
import math
import io
import json
import os
import random
import sys
import time

import render_l0_sheet as R

HERE = os.path.dirname(os.path.abspath(__file__))

# 寻优循环内 place() 反复读符号文件,缓存之(返回值只被读取,不被改写)。
_read_symbol_orig = R.read_symbol
_read_symbol_cache = {}


def _cached_read_symbol(path):
    if path not in _read_symbol_cache:
        _read_symbol_cache[path] = _read_symbol_orig(path)
    return _read_symbol_cache[path]


R.read_symbol = _cached_read_symbol

# B3 走廊豁免只读取布局声明的根坐标 boundary_terminals；缺省无豁免。
B3_BUDGET, B3_BOUNDARY = 1.5, 4.0
B4_BUDGET, B5_BUDGET = 8.0, 40.0
B2_SINGLE, B2_TOTAL = 3, 40
from layout_contract import drawable_bounds, pipe_half_width


def canvas_geom(L):
    return drawable_bounds(L)


def boundary_terminals(L):
    return [tuple(t) for t in (L.get('boundary_terminals')
                               or [])]


# ---------- 评估器：与 validate_sheet 构图预算面板同口径 ----------

def turns_of(pts):
    dirs = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if abs(x1 - x0) >= abs(y1 - y0):
            dirs.append('H' if x1 >= x0 else 'h')
        else:
            dirs.append('V' if y1 >= y0 else 'v')
    return sum(1 for i in range(1, len(dirs))
               if dirs[i] != dirs[i - 1] or dirs[i][0] != dirs[i - 1][0])


def near_terminal(p, bt):
    return any(abs(p[0] - t[0]) < 3 and abs(p[1] - t[1]) < 3
               for t in bt)


def seg_rect_hit(p0, p1, rect, tol=2.0):
    """线段是否穿越矩形内部(仅正交段)。返回穿越长度。同 validate_sheet。"""
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
    bt = boundary_terminals(L)
    s = R.Sheet(intent, L, catalog,
                cat_dir=os.path.join(HERE, '..', 'assets', 'component-library'))
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
                      (near_terminal(pts[0], bt) or near_terminal(pts[-1], bt)))
            ratios.append((ln / man, pts, exempt))
        for a, b in zip(pts, pts[1:]):
            min_seg = min(min_seg, abs(a[0] - b[0]) + abs(a[1] - b[1]))

    segs_all = [(c, pts[k], pts[k + 1])
                for c, pts in polys for k in range(len(pts) - 1)]

    # B1 counts planned nonconnected crossings before bridge gaps, exactly as
    # the final zero-crossing budget requires. A correct bridge is no exemption.
    # This uses input/route geometry and launches no browser for candidates.
    b1 = len({(round(x,1),round(y,1)) for x,y,_ in cross})

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
    left, top, right, bottom = canvas_geom(L)
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
    for y in range(max(140, int(top)), int(bottom) - 89, LANE_GRID):
        if all(abs(y - ly) >= 15 for ly in lanes):
            ms.append(('lane_add', y))
    for x in range(max(60, int(left)), int(right) - 60, VLANE_GRID):
        if all(abs(x - cx) >= 15 for cx in vlanes) and x not in (20,):
            ms.append(('vlane_add', x))
    for b, bd in L['buses'].items():
        for dx in (-20, -10, 10, 20):
            ms.append(('bus_move', b, dx))
    for inst, nd in L['nodes'].items():
        for dx, dy in ((-20, 0), (20, 0), (0, -20), (0, 20)):
            ms.append(('node_move', inst, dx, dy))
    return ms


def _fast_copy(L):
    """两级浅拷贝替代 deepcopy（#14）。布局各键至多嵌套两层——
    nodes/buses/externs 的值是标量 dict，lanes/vlanes 是标量 list，
    legend/title_block/canvas/style 是标量 dict——两级拷贝即隔离
    apply_move 与管线管线写入的全部路径，候选对象新鲜度契约不变，
    省掉 deepcopy 的备忘录机制（实测约占爬坡墙钟一半）。"""
    c = dict(L)
    for k in ('canvas', 'drawable', 'style', 'legend', 'title_block'):
        if isinstance(L.get(k), dict):
            c[k] = dict(L[k])
    for k in ('externs', 'nodes', 'buses'):
        c[k] = {n: dict(v) for n, v in (L.get(k) or {}).items()}
    for k in ('lanes', 'vlanes'):
        c[k] = list(L.get(k) or [])
    return c


def apply_move(L, m):
    L = _fast_copy(L)
    left, top, right, bottom = canvas_geom(L)
    radius = pipe_half_width(L)
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
    L['lanes'] = [ly for ly in L.get('lanes', []) if max(top, 60) <= ly <= bottom - 60]
    L['vlanes'] = [cx for cx in L.get('vlanes', []) if max(left + radius, 20) <= cx <= right - radius]
    for bd in L['buses'].values():
        if not (max(left + radius, 60) <= bd['x'] <= right - radius):
            return None
    for nd in L['nodes'].values():
        if not (max(left + radius, 60) <= nd['x'] and nd['x'] + nd['w'] <= right - radius):
            return None
        if not (max(top + radius, 60) <= nd['y'] and nd['y'] + nd['h'] <= bottom - 60):
            return None
    if len(set(L.get('lanes', []))) != len(L.get('lanes', [])):
        return None
    return L


# ---------- 搜索：固定种子首改进下降 + 随机踢散重启（#14 换策略）----------

# 预算覆盖种子面板及每个实际评估候选。时间预算在评估间检查，单次评估
# 不会被中断；max_evals/max_steps 是可复现的首要界限。
MAX_EVALS, MAX_STEPS, MAX_SECONDS, POLISH_STEPS = 200, 50, 30.0, 0


def validate_budgets(max_evals, max_steps, max_seconds, polish_steps):
    for name, value, minimum in (('max_evals', max_evals, 1),
                                  ('max_steps', max_steps, 0),
                                  ('polish_steps', polish_steps, 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError('%s 必须为 >= %d 的整数' % (name, minimum))
    if (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float))
            or not math.isfinite(max_seconds) or max_seconds < 0):
        raise ValueError('max_seconds 必须为有限非负数')


def optimizer_progress(event):
    """进度只写 stderr，供驱动器实时透出，保持 stdout 的结构化契约。"""
    print('[optimize:%s] %s evals=%d steps=%d defects=%d elapsed=%.2fs%s'
          % (event['tag'], event['event'], event['evals'], event['steps'],
             event['energy'][0], event['elapsed_s'],
             (' stop=' + event['stop_reason']) if event.get('stop_reason') else ''),
          file=sys.stderr, flush=True)


def climb(L0, intent, catalog, log, tag, seed=19, *,
          max_evals=MAX_EVALS, max_steps=MAX_STEPS, max_seconds=MAX_SECONDS,
          polish_steps=POLISH_STEPS, initial_bp=None, progress=None):
    """固定随机种子的首改进下降；预算耗尽返回目前最优布局，返回三元组不变。

    max_evals 含种子评估；initial_bp 可复用调用方刚测量的种子，仍计一次。
    max_steps 限接受的改善步；0 polish 在种子已达标时不探测任何邻居。
    时间限在评估之间检查，因此可能多花一份评估时间。最终停止记录追加到
    log，包含 stop_reason/evals/steps/elapsed_s，绝不代表完整校验已通过。
    """
    validate_budgets(max_evals, max_steps, max_seconds, polish_steps)
    started = time.monotonic()
    rng = random.Random(seed)
    bp = initial_bp if initial_bp is not None else bpanel(L0, intent, catalog)
    cur, e = L0, energy(bp)
    evals, steps, polished = 1, 0, 0
    budgets = dict(max_evals=max_evals, max_steps=max_steps,
                   max_seconds=max_seconds, polish_steps=polish_steps)
    emit = progress if progress is not None else optimizer_progress

    def event(kind, **extra):
        return dict(tag=tag, event=kind, step=steps, steps=steps, evals=evals,
                    elapsed_s=round(time.monotonic() - started, 6),
                    energy=e, bp=bp, **extra)

    def budget_stop():
        if evals >= max_evals:
            return 'max_evals'
        if steps >= max_steps:
            return 'max_steps'
        if time.monotonic() - started >= max_seconds:
            return 'max_seconds'
        return None

    log.append(event('start', move=None))
    emit(log[-1])
    last_progress = time.monotonic()
    while True:
        at_target = e[0] == 0 and e[1] == 0.0
        if at_target and polished >= polish_steps:
            reason = 'target_reached' if polish_steps == 0 else 'polish_steps'
            break
        reason = budget_stop()
        if reason:
            break
        moves = neighbors(cur)
        rng.shuffle(moves)
        found = None
        for move in moves:
            reason = budget_stop()
            if reason:
                break
            cand = apply_move(cur, move)
            if cand is None:
                continue
            cbp = bpanel(cand, intent, catalog)
            evals += 1
            ce = energy(cbp)
            if ce < e:
                found = (cand, cbp, ce, move)
                break
            if evals % 10 == 0 or time.monotonic() - last_progress >= 1:
                emit(event('progress'))
                last_progress = time.monotonic()
        if found is None:
            reason = reason or budget_stop() or 'local_minimum'
            break
        cur, bp, e, move = found
        steps += 1
        # 达标的那一步不是额外抛光，抛光只计从已达标状态出发的改善。
        if at_target:
            polished += 1
        log.append(event('accepted', move=repr(move)))
        emit(log[-1])
        last_progress = time.monotonic()
    log.append(event('stop', stop_reason=reason, budgets=budgets,
                     polish_steps_used=polished, move=None))
    emit(log[-1])
    return cur, bp, e


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('seed_path')
    ap.add_argument('--intent')
    ap.add_argument('--catalog')
    ap.add_argument('-o', dest='prefix')
    ap.add_argument('--kick', type=int, default=0,
                    help='额外随机重启次数（每次独立应用搜索预算；默认关闭）')
    ap.add_argument('--pure-budget', action='store_true')
    ap.add_argument('--max-evals', type=int, default=MAX_EVALS)
    ap.add_argument('--max-steps', type=int, default=MAX_STEPS)
    ap.add_argument('--max-seconds', type=float, default=MAX_SECONDS)
    ap.add_argument('--polish-steps', type=int, default=POLISH_STEPS)
    args = ap.parse_args()
    try:
        validate_budgets(args.max_evals, args.max_steps, args.max_seconds,
                         args.polish_steps)
        if args.kick < 0:
            raise ValueError('--kick 必须 >= 0')
    except ValueError as exc:
        ap.error(str(exc))
    seed_path = args.seed_path
    seed_dir = os.path.dirname(os.path.abspath(seed_path))
    intent_p = args.intent
    if not intent_p:
        import glob as _glob
        hits = sorted(_glob.glob(os.path.join(seed_dir, '*.intent.yaml')))
        intent_p = hits[0] if len(hits) == 1 else None
    if not intent_p:
        ap.error('未定位 intent：用 --intent 指定，或种子目录下恰有一个 *.intent.yaml')
    cand = os.path.join(seed_dir, 'component-catalog.json')
    cat_p = args.catalog or (cand if os.path.isfile(cand) else os.path.join(
        HERE, '..', 'assets', 'component-library', 'component-catalog.json'))
    prefix = args.prefix or os.path.splitext(seed_path)[0] + '-opt'
    out_prefix = prefix if os.path.dirname(prefix) else os.path.join(seed_dir, prefix)
    budgets = dict(max_evals=args.max_evals, max_steps=args.max_steps,
                   max_seconds=args.max_seconds, polish_steps=args.polish_steps)

    intent = R.load_yaml(intent_p)
    with io.open(cat_p, encoding='utf-8') as f:
        catalog = json.load(f)
    with io.open(seed_path, encoding='utf-8') as f:
        seed = json.load(f)

    t0 = time.time()
    bp0 = bpanel(copy.deepcopy(seed), intent, catalog)
    print('种子评估 %.2fs: %s' % (time.time() - t0, bp0))
    print('种子能量: %s' % (energy(bp0),))
    NO_REGRESSION.clear()
    if not args.pure_budget:
        NO_REGRESSION.update(b1=bp0['b1'], b2tot=bp0['b2tot'],
                             b2max=bp0['b2max'], b4=bp0['b4'],
                             b5=bp0['b5'])
        print('不劣化下限(取种子值):', dict(NO_REGRESSION))

    log = []
    bestL, bestbp, beste = climb(seed, intent, catalog, log, 'main',
                                   initial_bp=bp0, **budgets)
    rng = random.Random(19)
    for k in range(args.kick):
        L = copy.deepcopy(bestL)
        pool = neighbors(L)
        if not pool:
            break
        for _ in range(3):
            m = rng.choice(pool)
            L = apply_move(L, m) or L
        L2, bp2, e2 = climb(L, intent, catalog, log, 'kick%d' % k, **budgets)
        if e2 < beste:
            bestL, bestbp, beste = L2, bp2, e2
        print('kick%d -> %s (best %s)' % (k, e2[:2], beste[:2]))

    with io.open(out_prefix + '.layout.json', 'w',
                 encoding='utf-8') as f:
        json.dump(bestL, f, ensure_ascii=False, indent=2)
    with io.open(out_prefix + '-opt-log.json', 'w',
                 encoding='utf-8') as f:
        json.dump({'seed': os.path.basename(seed_path), 'seed_bp': bp0,
                   'final_bp': bestbp, 'final_energy': beste,
                   'optimization': log[-1], 'budgets_per_search': budgets,
                   'log': log}, f, ensure_ascii=False, indent=1)
    print('最终: %s bp=%s' % (beste, bestbp))
    print('写出 %s.layout.json / -opt-log.json' % out_prefix)
    return 0


if __name__ == '__main__':
    sys.exit(main())
