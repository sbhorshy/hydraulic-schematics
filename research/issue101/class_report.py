# -*- coding: utf-8 -*-
"""#101 一次性：汇总两轮官方链结果，列出 B1–B7 等价类与类外图（不进 main）。"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/issue101'))
sys.path.insert(0, str(ROOT / '.agents/skills/hydraulic-schematic/scripts'))
import flat_metrics as F  # noqa: E402
import proto_issue101_readability as R  # noqa: E402

A = ROOT / '.artifacts/issue101'


def main():
    b = R.load_report(A / 'base')
    bres, _bev, bpanel = R.summarize(b)
    bs = F.status_sig(bpanel)
    bd = {k: v['status'] for k, v in bpanel.items()}
    bf = F.flat(bres)
    r1 = json.loads((A / 'mine/variants.json').read_text(encoding='utf-8'))['rows']
    r2 = json.loads((A / 'mine2/confirm.json').read_text(encoding='utf-8'))
    for name, rows in (('第一轮 单步邻域', r1), ('第二轮 定向筛选', r2)):
        ok = [r for r in rows if r['ok']]
        cls = [r for r in ok if r['fail'] == 0 and F.status_sig(r['budget']) == bs]
        print('%s: %d 张，出图失败 %d，fail0 %d，B1–B7 等价类 %d' % (name, len(rows), len(rows) - len(ok),
                                                                 sum(1 for r in ok if not r['fail']), len(cls)))
        print('   fail>0 的校核项:', collections.Counter(f for r in ok if r['fail'] for f in r['fails']).most_common())
        out = [r for r in ok if r['fail'] == 0 and F.status_sig(r['budget']) != bs]
        print('   fail0 但 B1–B7 状态不同: %d 张' % len(out))
        cnt = collections.Counter()
        for r in out:
            d = {k: (v['status'], v['measured']) for k, v in r['budget'].items()}
            cnt[tuple((k, d[k][0], bd[k][0]) for k in sorted(d) if d[k][0] != bd[k][0]
                      or (k == 'B7' and (d[k][1] or {}).get('violations') != (bd[k][1] or {}).get('violations')))] += 1
        for k, n in cnt.most_common(8):
            print('     %3d %s' % (n, k))
        for r in cls:
            r['_f'] = F.flat(r['metrics'])
        print('   等价类内指标范围:')
        for k in bf:
            vals = [r['_f'][k] for r in cls if r['_f'][k] is not None]
            print('     %-9s 原图 %-6s 最小 %-6s 最大 %-6s 取值 %d 种' % (k, bf[k], min(vals), max(vals), len(set(vals))))


if __name__ == '__main__':
    main()
