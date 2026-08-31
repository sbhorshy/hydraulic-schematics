# -*- coding: utf-8 -*-
"""P3 提速评估（#14 并入议题证据，2026-08-31 实测）：邻域解剖 + 单评估剖析 + 有界 A/B。

三个实验：
  E1 邻域解剖：动作类型构成与规模（决定每步最陡下降的评估次数）。
  E2 单次评估剖析：cProfile 看单评耗时花在哪（路由/交叉/指标各占多少）。
  E3 有界 A/B：同一阶段 2 起点，最陡下降 vs 首改进各 150s，
     记能量-时间曲线、步数、评估次数。
实测要点：邻域 267 候选（走廊网格新增占 50%）；单评 48ms 中 wire() 路由占
68%；150s 内首改进 45 步/终长 9222.7 vs 最陡 6 步/10062.7。
全收敛与丁对照见 eval-p3-speedup-full.py。
"""
import copy
import cProfile
import io
import json
import os
import pstats
import random
import time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
import layout_engine as LE
import proto_optimize as PO

BUDGET_S = 150.0


def load_yaml(p):
    from ruamel.yaml import YAML
    with io.open(p, encoding='utf-8') as f:
        return YAML(typ='safe', pure=True).load(f)


intent = load_yaml(os.path.join(HERE, '1#系统.intent.yaml'))
with io.open(os.path.join(HERE, 'component-catalog.json'), encoding='utf-8') as f:
    cat = json.load(f)
with io.open(os.path.join(HERE, '1#系统.layout.json'), encoding='utf-8') as f:
    ref = json.load(f)

# ---- 阶段 2 起点（与引擎 stage-3 同口径：规则 + 守门，不加寻优）----
layout, structure = LE.rules(intent, cat, dict(LE.P), ref)
layout, guard_rep = LE.guard(layout, structure, dict(LE.P))
bp0 = PO.bpanel(copy.deepcopy(layout), intent, cat)
PO.NO_REGRESSION.update(b1=bp0['b1'], b2tot=bp0['b2tot'], b2max=bp0['b2max'],
                        b4=bp0['b4'], b5=bp0['b5'])
print('== E0 起点（阶段 2 输出）==')
print('面板:', {k: bp0[k] for k in ('b1', 'b2tot', 'b2max', 'b3',
                                   'b4', 'b5', 'v2', 'v13', 'length')})
print('能量:', PO.energy(bp0))

# ---- E1 邻域解剖 ----
ms = PO.neighbors(layout)
cnt = Counter(m[0] for m in ms)
print('\n== E1 邻域 ==')
print('规模:', len(ms), ' 构成:', dict(cnt))

# ---- E2 单次评估剖析 ----
pr = cProfile.Profile()
pr.enable()
bp1 = PO.bpanel(copy.deepcopy(layout), intent, cat)
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats('cumulative').print_stats(16)
print('\n== E2 单次 bpanel 剖析 ==')
print(s.getvalue())

# ---- E3 A/B ----
t0 = time.perf_counter()
bp = PO.bpanel(layout, intent, cat)
print('首评计时: %.1f ms' % ((time.perf_counter() - t0) * 1000))


def climb_steepest(L0, budget_s):
    bp = PO.bpanel(L0, intent, cat)
    cur, e = L0, PO.energy(bp)
    t0 = time.perf_counter()
    evals = steps = 0
    trace = [(0.0, e)]
    stop = False
    while not stop:
        best, bestm, bestbp, bestL = e, None, bp, cur
        for m in PO.neighbors(cur):
            cand = PO.apply_move(cur, m)
            if cand is None:
                continue
            evals += 1
            cbp = PO.bpanel(cand, intent, cat)
            ce = PO.energy(cbp)
            if ce < best:
                best, bestm, bestbp, bestL = ce, m, cbp, cand
            if time.perf_counter() - t0 > budget_s:
                stop = True
                break
        if stop:
            break
        if bestm is None:
            break
        cur, bp, e = bestL, bestbp, best
        steps += 1
        trace.append((round(time.perf_counter() - t0, 1), e))
    return dict(tag='steepest', trace=trace, evals=evals, steps=steps,
                final=e, final_bp=bp)


def climb_first_improvement(L0, budget_s, seed=13):
    rng = random.Random(seed)
    bp = PO.bpanel(L0, intent, cat)
    cur, e = L0, PO.energy(bp)
    t0 = time.perf_counter()
    evals = steps = 0
    trace = [(0.0, e)]
    while True:
        msl = PO.neighbors(cur)
        rng.shuffle(msl)
        improved = None
        for m in msl:
            cand = PO.apply_move(cur, m)
            if cand is None:
                continue
            evals += 1
            cbp = PO.bpanel(cand, intent, cat)
            ce = PO.energy(cbp)
            if ce < e:
                improved = (cand, cbp, ce)
                break
            if time.perf_counter() - t0 > budget_s:
                break
        if improved is None:
            break                      # 整邻域无改进 = 局部最优（全扫确认）
        if time.perf_counter() - t0 > budget_s:
            break
        cur, bp, e = improved
        steps += 1
        trace.append((round(time.perf_counter() - t0, 1), e))
    return dict(tag='first-improve', trace=trace, evals=evals, steps=steps,
                final=e, final_bp=bp)


print('\n== E3 A/B（各 %.0fs）==' % BUDGET_S)
res = {}
for fn in (climb_steepest, climb_first_improvement):
    r = fn(layout, BUDGET_S)
    res[r['tag']] = r
    print('[%s] 步=%d 评估=%d 终能量=%s' % (r['tag'], r['steps'], r['evals'],
                                          r['final']))
    print('   终面板: b3=%.3f len=%d v=%d b3over=%s'
          % (r['final_bp']['b3'], r['final_bp']['length'], r['final'][0],
             r['final'][1]))
    print('   轨迹:', ' '.join('%ds:%s' % (t, e) for t, e in r['trace'][:14]))

st, fi = res['steepest'], res['first-improve']
print('\n== 对比 ==')
print('150s 内评估次数: steepest %d vs first-improve %d'
      % (st['evals'], fi['evals']))
print('150s 时能量:     steepest %s vs first-improve %s'
      % (st['final'], fi['final']))
