# -*- coding: utf-8 -*-
"""P3 提速评估补充（#14 并入议题证据）：首改进不限时跑到局部最优。
双种子（13/7）实测：平台 159s/304s，终态 len 9162.7/9102.7、b3 均 1.447；
生产版丁（最陡 ~900s）len 9102.7、b3 1.447——seed7 与丁逐位相同。"""
import copy
import io
import json
import os
import random
import time

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
import layout_engine as LE
import proto_optimize as PO

CAP_S = 600.0


def load_yaml(p):
    from ruamel.yaml import YAML
    with io.open(p, encoding='utf-8') as f:
        return YAML(typ='safe', pure=True).load(f)


intent = load_yaml(os.path.join(HERE, '1#系统.intent.yaml'))
with io.open(os.path.join(HERE, 'component-catalog.json'), encoding='utf-8') as f:
    cat = json.load(f)
with io.open(os.path.join(HERE, '1#系统.layout.json'), encoding='utf-8') as f:
    ref = json.load(f)

layout, structure = LE.rules(intent, cat, dict(LE.P), ref)
layout, guard_rep = LE.guard(layout, structure, dict(LE.P))
bp0 = PO.bpanel(copy.deepcopy(layout), intent, cat)
PO.NO_REGRESSION.update(b1=bp0['b1'], b2tot=bp0['b2tot'], b2max=bp0['b2max'],
                        b4=bp0['b4'], b5=bp0['b5'])


def fi_full(L0, seed):
    rng = random.Random(seed)
    bp = PO.bpanel(L0, intent, cat)
    cur, e = L0, PO.energy(bp)
    t0 = time.perf_counter()
    evals = steps = 0
    last_imp_t = 0.0
    milestones = []
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
        if improved is None:
            break
        cur, bp, e = improved
        steps += 1
        last_imp_t = time.perf_counter() - t0
        if not milestones or milestones[-1][1] != e[2]:
            milestones.append((round(last_imp_t, 1), e))
        if last_imp_t > CAP_S:
            break
    return dict(seed=seed, steps=steps, evals=evals,
                plateau_s=round(last_imp_t, 1), final=e,
                b3=bp['b3'], len=bp['length'], milestones=milestones[-6:])


for seed in (13, 7):
    r = fi_full(layout, seed)
    print('[seed %d] 步=%d 评估=%d 平台=%.1fs 终能量=%s b3=%.3f len=%d'
          % (r['seed'], r['steps'], r['evals'], r['plateau_s'],
             r['final'], r['b3'], r['len']))
    print('   收尾里程碑:', r['milestones'])
