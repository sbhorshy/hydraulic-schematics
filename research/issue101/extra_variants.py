# -*- coding: utf-8 -*-
"""#101 一次性：给决策页的“反例演示”补几张真实出过的图（不进 main）。

反例要成立，图池里得有“标签更靠近主人、但为此多违了标签净空”的真图。
第二轮的候选都是单步改动，凑不出这种组合，这里直接给几串标签改动走官方链。

用法（仓库根目录）: python3 research/issue101/extra_variants.py [--workers 5]
产物: .artifacts/issue101/mine2/var/<id>/ 与 .artifacts/issue101/mine2/extra.json
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/issue101'))
import mine_round2 as M2  # noqa: E402
import mine_variants as V1  # noqa: E402

L = 'label'
EXTRAS = [
    [('node_move', 'PRV-001', 0, 20), ('node_move', 'CV-002', 0, 20)],
    [(L, 'TANK-001', 'below', 0), (L, 'EMP-001', 'below', 0)],
    [(L, 'TANK-001', 'below', 0), (L, 'EMP-001', 'below', 0), (L, 'EDP-001', 'above', 0)],
    [(L, 'TANK-001', 'below', 0), (L, 'EMP-001', 'below', 0), (L, 'EDP-001', 'above', 0), (L, 'CDF-001', 'below', 0)],
    [(L, 'TANK-001', 'below', 0), (L, 'EMP-001', 'below', 0), (L, 'EDP-001', 'above', 0), (L, 'CDF-001', 'below', 0),
     (L, 'ACC-001', 'above', 0)],
]


def one(ops):
    layout = M2.apply(M2.BASE, [list(o) for o in ops])
    if layout is None:
        return dict(id=M2.op_id(ops), ok=False, error='out of canvas')
    return V1.run((M2.op_id(ops), layout, [list(o) for o in ops]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workers', type=int, default=5)
    args = ap.parse_args()
    import multiprocessing
    with multiprocessing.Pool(args.workers, initializer=M2._setup_v1) as pool:
        rows = list(pool.imap_unordered(one, EXTRAS))
    rows.sort(key=lambda r: r['id'])
    (M2.OUT / 'extra.json').write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    for r in rows:
        print('%-90s %s' % (r['id'][:90], 'ERR ' + r['error'] if not r['ok'] else
                            'fail %d warn %d amb %s far %s' % (r['fail'], r['warn'], r['metrics']['m3']['ambiguous'],
                                                              r['metrics']['m3']['far'])))


if __name__ == '__main__':
    main()
