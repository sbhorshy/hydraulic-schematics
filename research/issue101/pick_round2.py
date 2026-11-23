# -*- coding: utf-8 -*-
"""#101 一次性：从进程内筛选结果里挑送官方链确认的候选（不进 main）。

分组：A 读图主线折点/折返有变化；C 并行走廊；D 三通/桥间距两极；E 随机对照；
F 标签归属；G 带硬缺陷但可读性数字更好的图（给能量排序模拟器演示“排错层会选坏图”）。
用法: python3 research/issue101/pick_round2.py > .artifacts/issue101/mine2/picks.json
"""
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/issue101'))
import flat_metrics as F  # noqa: E402

MINE = ROOT / '.artifacts/issue101/mine2'
BASE_LINES = {'吸油 油箱→EDP': 4, '吸油 油箱→EMP': 2, '压力 EDP→USER-005': 6, '压力 EMP→USER-001': 6,
              '回油 USER-003→油箱': 6, '壳体回油 EDP→油箱': 9, '自增压 @PRESS→油箱': 5, '蓄压 @PRESS→ACC': 5}
BASE_REV = {'吸油 油箱→EDP': 0, '吸油 油箱→EMP': 0, '压力 EDP→USER-005': 2, '压力 EMP→USER-001': 0,
            '回油 USER-003→油箱': 3, '壳体回油 EDP→油箱': 5, '自增压 @PRESS→油箱': 2, '蓄压 @PRESS→ACC': 3}


def main():
    d = json.loads((MINE / 'screen.json').read_text(encoding='utf-8'))
    b = d['base_panel']
    ok = [r for r in d['rows'] if r['ok']]
    for r in ok:
        r['_f'] = F.flat(r['metrics'])

    def legal(r, tight=False):
        p = r['panel']
        good = (p['b1'] <= b['b1'] and p['v2'] == 0 and p['v13'] == 0 and p['b2max'] <= 3
                and p['b2tot'] <= 40 and p['b3'] <= 1.5 and p['b4'] >= 8 and p['b5'] >= 40)
        if tight:
            good = good and p['b2tot'] <= b['b2tot'] and p['b4'] >= b['b4'] and p['b5'] >= b['b5']
        return good

    picks = []

    def add(tag, rows, cap=10 ** 6):
        for r in rows[:cap]:
            picks.append(r['id'])

    wide = [r for r in ok if legal(r)]
    tight = [r for r in ok if legal(r, True)]
    # A：单步改动就让某条读图主线的折点或折返数变化（宽合法）
    a = [r for r in wide if len(r['ops']) == 1 and (
        any(r['metrics']['m1']['per_line'][n] != v for n, v in BASE_LINES.items())
        or any(r['metrics']['m2']['per_line'][n][0] != v for n, v in BASE_REV.items()))]
    add('A', a)
    # C：出现并行阅读带事件
    add('C', [r for r in wide if r['metrics']['m4']['count'] > 0])
    # D：三通间距 / 三通到转角 / 桥到节点 的两极（紧合法，最多两步改动）
    small = [r for r in tight if len(r['ops']) <= 2]
    for key in ('m6_jg', 'm6_jb', 'm6_br'):
        val = [r for r in small if r['_f'][key] is not None]
        add('D', sorted(val, key=lambda r: r['_f'][key]), 12)
        add('D', sorted(val, key=lambda r: -r['_f'][key]), 12)
    # E：紧合法随机对照
    rng = random.Random(7)
    add('E', rng.sample(tight, 40))
    # F：标签归属歧义数 0 / 3 的图
    add('F', [r for r in tight if r['_f']['m3_amb'] == 0][:6])
    add('F', [r for r in tight if r['_f']['m3_amb'] >= 3][:6])
    # G：带硬缺陷（V2/V13/多一处交叉）但某项可读性数字比原图好
    def better(r):
        f = r['_f']
        return (f['m2_rev'] < 15 or f['m3_amb'] < 2 or (f['m6_jg'] or 99) > 30
                or (f['m6_jb'] or 99) > 30 or f['m3_far'] < 4)
    g = [r for r in ok if not legal(r) and r['panel']['b1'] + r['panel']['v2'] + r['panel']['v13'] > b['b1']
         and r['panel']['b1'] <= 2 and r['panel']['v2'] <= 2 and r['panel']['v13'] <= 3 and better(r)
         and len(r['ops']) == 1]
    add('G', sorted(g, key=lambda r: r['id']), 14)
    seen, uniq = set(), []
    for cid in picks:
        if cid not in seen:
            seen.add(cid)
            uniq.append(cid)
    json.dump(uniq, sys.stdout, ensure_ascii=False)
    print(file=sys.stderr)


if __name__ == '__main__':
    main()
