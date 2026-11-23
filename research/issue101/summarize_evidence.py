# -*- coding: utf-8 -*-
"""#101 一次性：把 .artifacts/issue101 的挖掘结果压成可提交的紧凑证据（不进 main）。

每个变体一行：官方出图链的 fail / warn、预算面板是否与原图同类、六项指标的标量摘要。
另算同类图里各指标的取值范围、与总线长的秩相关，以及八条读图主线的折点范围。

用法（仓库根目录）: python3 research/issue101/summarize_evidence.py
产物: research/issue101/evidence/sheets.json、evidence/class-summary.json，并在终端打印摘要
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'research/issue101'))
import build_prototype as B  # noqa: E402

OUT = ROOT / 'research/issue101/evidence'
FIELDS = ('m1_max', 'm1_sum', 'm2_rev', 'm2_back', 'm3_max', 'm3_mean', 'm3_far', 'm3_amb',
          'm4_n', 'm4_len', 'm4_main', 'm5_min', 'm5_short', 'm5_mis', 'm6_jg', 'm6_jb', 'm6_br', 'm6_n')


def _ranks(values):
    """并列取平均名次（0 起；秩相关对整体平移不变）。"""
    order = sorted(range(len(values)), key=lambda i: values[i])
    r = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2.0
        i = j + 1
    return r


def spearman(a, b):
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    da = sum((x - ma) ** 2 for x in ra) ** 0.5
    db = sum((x - mb) ** 2 for x in rb) ** 0.5
    if not da or not db:
        return None
    return round(sum((x - ma) * (y - mb) for x, y in zip(ra, rb)) / (da * db), 2)


def main():
    rows = B.load_rows()
    base_sig = B.status_sig_of(B.BASE_KEY, rows)
    base_flat = B.flat_of(B.BASE_KEY, rows)
    base_report = json.loads((rows[B.BASE_KEY]['wd'] / 'validation-report.json').read_text(encoding='utf-8'))
    details = json.loads(B.DETAILS.read_text(encoding='utf-8'))

    sheets = []
    for key in sorted(rows):
        if key == B.BASE_KEY:
            fail, warn, flat, sig = base_report['fail_count'], base_report['warn_count'], base_flat, base_sig
        else:
            row = rows[key]['row']
            fail, warn = row['fail'], row['warn']
            flat, sig = B.flat_of(key, rows), B.status_sig_of(key, rows)
        sheets.append(dict(key=key, kind=rows[key]['kind'], fail=fail, warn=warn, over=B.over_budget(key, rows),
                           same_class=(not fail and sig == base_sig), length=details[key]['length'],
                           **{f: flat[f] for f in FIELDS}))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'sheets.json').write_text(json.dumps(sheets, ensure_ascii=False, indent=1), encoding='utf-8')

    cls = [s for s in sheets if s['same_class'] and s['key'] != B.BASE_KEY]
    base = next(s for s in sheets if s['key'] == B.BASE_KEY)
    by_key = {s['key']: s for s in sheets}

    summary = dict(
        sheets=len(sheets), same_class=len(cls),
        same_class_by_kind={k: sum(1 for s in cls if s['kind'] == k) for k in sorted({s['kind'] for s in cls})},
        fail0=sum(1 for s in sheets if not s['fail']),
        base={f: base[f] for f in FIELDS},
        base_fail=base['fail'], base_warn=base['warn'], base_over=base['over'], base_length=base['length'],
    )
    summary['class_range'] = {f: [min(s[f] for s in cls), max(s[f] for s in cls)]
                              for f in FIELDS if all(s[f] is not None for s in cls)}
    lengths = [s['length'] for s in cls]
    summary['spearman_with_length'] = {f: spearman([s[f] for s in cls], lengths)
                                       for f in FIELDS if all(s[f] is not None for s in cls)}
    summary['spearman_m1_sum_m2_rev'] = spearman([s['m1_sum'] for s in cls], [s['m2_rev'] for s in cls])

    # 单步邻域里有多少张六项指标与原图完全相同
    summary['r1_class_identical_metrics'] = sum(
        1 for s in cls if s['kind'] == 'r1' and all(s[f] == base[f] for f in FIELDS))

    # 八条读图主线在同类图里的折点 / 折返范围
    lines = {}
    for name in details[B.BASE_KEY]['full']['lines']:
        bends = [details[s['key']]['full']['lines'][name][0] for s in cls if name in details[s['key']]['full']['lines']]
        revs = [details[s['key']]['full']['lines'][name][1] for s in cls if name in details[s['key']]['full']['lines']]
        lines[name] = dict(base_bends=details[B.BASE_KEY]['full']['lines'][name][0],
                           base_reversals=details[B.BASE_KEY]['full']['lines'][name][1],
                           class_bends=[min(bends), max(bends)] if bends else None,
                           class_reversals=[min(revs), max(revs)] if revs else None,
                           class_sheets=len(bends))
    summary['lines'] = lines

    # M1 / M2 是否各自单独变化：按八条主线逐项比（只看折点合计会漏掉「折点换到别的线上」）
    def _bends(k):
        return {n: v[0] for n, v in details[k]['full']['lines'].items()}

    def _revs(k):
        return {n: v[1] for n, v in details[k]['full']['lines'].items()}

    b0, r0 = _bends(B.BASE_KEY), _revs(B.BASE_KEY)
    ind = dict(bends_same_reversals_changed=0, bends_changed_reversals_same=0, both_same=0, both_changed=0,
               reversal_total_changed=0, reversal_total_unchanged_redistributed=0)
    for s in cls:
        b, r = _bends(s['key']), _revs(s['key'])
        sb, sr = b == b0, r == r0
        ind['bends_same_reversals_changed' if sb and not sr else
            'bends_changed_reversals_same' if sr and not sb else
            'both_same' if sb else 'both_changed'] += 1
        if not sr:
            ind['reversal_total_changed'] += int(sum(r.values()) != sum(r0.values()))
            ind['reversal_total_unchanged_redistributed'] += int(sum(r.values()) == sum(r0.values()))
    summary['class_m1_m2_independence'] = ind
    # 全样本（含预算变差的图）里，有没有哪条主线的折点少于原图
    summary['sheets_any_line_fewer_bends'] = sum(
        1 for s in sheets if any(v < b0[n] for n, v in _bends(s['key']).items()))
    summary['lines_fewer_bends_sheets'] = {
        n: sum(1 for s in sheets if _bends(s['key'])[n] < b0[n]) for n in b0}

    # 按定案阈值，各类图的越线条目分布（同类图 + 全样本）。同类图的紧凑数组与完整证据下标相同。
    def _arr(k, name):
        full = details[k].get('full') or {}
        return full[name] if name in full else details[k]['compact'][name]

    def _n_m1(s, t=6):                      # s 是 sheets 里的一行
        return sum(1 for v in _arr(s['key'], 'lines').values() if v[0] > t)

    def _m3_bad(k, t, owners):
        return [o for o, v in _arr(k, 'labels').items()
                if o not in owners and (v[0] > t or (v[2] is not None and v[2] < v[0]))]

    def _n_m6(s, t=30):
        return sum(1 for q in _arr(s['key'], 'jbpairs') if q[0] < t)

    def _dist(items, f):
        out = {}
        for s in items:
            out[f(s)] = out.get(f(s), 0) + 1
        return {str(k): out[k] for k in sorted(out)}

    exempt = set(B.EXEMPT['m3'])
    summary['over_threshold'] = {
        'm1 折点 > 6 的主线条数': dict(base=_n_m1(base), class_sheets=_dist(cls, _n_m1), all_sheets=_dist(sheets, _n_m1)),
        'm3 净距 > 40 px 或离别的元件更近的标签数': dict(
            base=len(_m3_bad(B.BASE_KEY, 40, set())), class_sheets=_dist(cls, lambda s: len(_m3_bad(s['key'], 40, set()))),
            all_sheets=_dist(sheets, lambda s: len(_m3_bad(s['key'], 40, set())))),
        'm3 其中名单外的标签数（名单 = ACC-001、CDF-001、EDP-001、EMP-001、TANK-001）': dict(
            base=len(_m3_bad(B.BASE_KEY, 40, exempt)),
            class_sheets=_dist(cls, lambda s: len(_m3_bad(s['key'], 40, exempt)))),
        'm4 16 px 带内异网并行处数': dict(base=base['m4_n'], class_sheets=_dist(cls, lambda s: s['m4_n']),
                                   all_sheets=_dist(sheets, lambda s: s['m4_n'])),
        'm6 短于 30 px 的三通旁线段条数': dict(base=_n_m6(base), class_sheets=_dist(cls, _n_m6), all_sheets=_dist(sheets, _n_m6)),
    }

    # 原图的预算面板（官方报告）
    summary['base_budget_items'] = [{k: i.get(k) for k in ('id', 'metric', 'measured', 'status')} for i in base_report['composition_budget']['items']]

    screen = json.loads((B.ART / 'mine2/screen.json').read_text(encoding='utf-8'))
    # 标签改动：走通了多少、被走线挡住多少；把每个标签贴回主人各自的代价。
    # 第一轮出了硬缺陷（V12 压字等）的图没有保留报告，只剩 mine/variants.json 里的一行日志，所以单列。
    def _report(k):
        return json.loads((rows[k]['wd'] / 'validation-report.json').read_text(encoding='utf-8'))

    def _panel(k):
        rep = _report(k)
        items = {i['id']: i for i in rep['composition_budget']['items']}
        return dict(fail=rep['fail_count'], b7_violations=rep['text_geometry']['violations'],
                    budgets={i: it.get('measured') for i, it in items.items()})

    b_panel = _panel(B.BASE_KEY)

    def _cost(k):
        """相对原图变了什么：预算实测值、B7 越线条目、硬缺陷数。"""
        p = _panel(k)
        changed = {i: [b_panel['budgets'][i], m] for i, m in p['budgets'].items() if b_panel['budgets'][i] != m}
        if p['b7_violations'] != b_panel['b7_violations']:
            changed['B7 越线条目'] = [b_panel['b7_violations'], p['b7_violations']]
        if p['fail']:
            changed['fail'] = [b_panel['fail'], p['fail']]
        return changed

    R1 = re.compile(r'^label_(above|below|left|right)_(.+?)_(\d+)$')      # 第一轮：label_<槽位>_<元件>_<偏移>
    R2 = re.compile(r'^lab_([^_]+)_(above|below|left|right)_(\d+)$')      # 第二轮：lab_<元件>_<槽位>_<偏移>（只认单步）
    owners = {}

    def _owner(name):
        return owners.setdefault(name, dict(blocked=0, rendered=0, base_px=None, class_ops=[], non_class={}))

    def _note(name, sig):
        o = _owner(name)
        o['non_class'][sig] = o['non_class'].get(sig, 0) + 1

    def _anchor(err):
        return err.split('|')[-1].strip() if '|' in err else err.split(':')[-1].strip()

    v1 = json.loads((B.ART / 'mine/variants.json').read_text(encoding='utf-8'))
    r1 = dict(attempted=0, blocked=0, rendered=0, hard_defect_no_report=0)
    for r in v1['rows']:
        m = R1.match(r['id'])
        if not m:
            continue
        r1['attempted'] += 1
        if not r.get('ok'):
            r1['blocked'] += 1
            _owner(m.group(2))['blocked'] += 1
            _note(m.group(2), '走线被挡（' + _anchor(r.get('error') or '') + '）')
        elif r.get('fail'):
            r1['hard_defect_no_report'] += 1
            _note(m.group(2), '硬缺陷 %d 处（%s；第一轮未保留报告）' % (r['fail'], '/'.join(sorted(set(r.get('fails') or []))) or '?'))
    r2 = dict(candidates=0, blocked=0, walkable_in_process=0, confirmed=0)
    for r in screen['rows']:
        m = R2.match(r['id'])
        if not m:
            continue
        r2['candidates'] += 1
        if r.get('ok'):
            r2['walkable_in_process'] += 1
        else:
            r2['blocked'] += 1
            _owner(m.group(1))['blocked'] += 1
            _note(m.group(1), '走线被挡（' + _anchor(r.get('error') or '') + '）')
    for s in sheets:
        key = s['key']
        if key == B.BASE_KEY:
            continue
        op = key.split(':', 1)[1]
        m = R1.match(op)
        if m:
            slot, owner, n = m.group(1), m.group(2), m.group(3)
            r1['rendered'] += 1
        elif R2.match(op):
            slot, owner, n = R2.match(op).group(2), R2.match(op).group(1), R2.match(op).group(3)
            r2['confirmed'] += 1
        else:
            continue
        o = _owner(owner)
        o['rendered'] += 1
        v = _arr(key, 'labels')[owner]
        if s['same_class']:
            o['class_ops'].append([slot, int(n), v[0], v[2] is not None and v[2] < v[0], key])
        else:
            _note(owner, '；'.join('%s %s→%s' % (i, a, b) for i, (a, b) in sorted(_cost(key).items())))
    base_labels = _arr(B.BASE_KEY, 'labels')
    for name, o in owners.items():
        v = base_labels.get(name)
        o['base_px'] = v[0] if v else None
        o['base_ambiguous'] = bool(v and v[2] is not None and v[2] < v[0]) if v else None
        o['class_ops'].sort(key=lambda t: (t[2], t[0], t[1]))
    r1['same_class'] = sum(1 for s in cls if R1.match(s['key'].split(':', 1)[1]))
    r2['same_class'] = sum(1 for s in cls if R2.match(s['key'].split(':', 1)[1]))
    extras = json.loads((B.ART / 'mine2/extra.json').read_text(encoding='utf-8'))
    summary['label_variants'] = dict(
        round1=r1, round2=r2,
        multi_label_extras=dict(attempted=len(extras), blocked=sum(1 for r in extras if not r['ok'])),
        by_owner=owners)

    # 第二轮进程内筛选：能走通的变体里端口末段是否恒定（进程内口径，只作旁证）
    ok_screen = [r for r in screen['rows'] if r.get('ok')]
    m5_counts = {}
    for r in ok_screen:
        m5_counts[r['metrics']['m5']['min']] = m5_counts.get(r['metrics']['m5']['min'], 0) + 1
    summary['screen'] = dict(candidates=screen['candidates'], ok=len(ok_screen),
                             blocked=sum(1 for r in screen['rows'] if not r.get('ok')),
                             m5_min_counts={str(k): m5_counts[k] for k in sorted(m5_counts)},
                             m5_17_and_b5_under_40=sum(1 for r in ok_screen if r['metrics']['m5']['min'] < 18
                                                       and r['panel'].get('b5') is not None and r['panel']['b5'] < 40))

    # 进程内筛出的候选里折点更少的那些，违反了哪些预算（旁证 M1「合法布局里折点只增不减」；进程内口径）
    sys.path.insert(0, str(ROOT / '.agents/skills/hydraulic-schematic/scripts'))
    import proto_optimize as P  # noqa: E402

    base_bends = {n: v[0] for n, v in details[B.BASE_KEY]['full']['lines'].items()}
    limits = (('B2 单条折点', 'b2max', P.B2_SINGLE, 'le'), ('B2 全图折点', 'b2tot', P.B2_TOTAL, 'le'), ('B3 绕行比', 'b3', P.B3_BUDGET, 'le'),
              ('B4 最短线段', 'b4', P.B4_BUDGET, 'ge'), ('B5 节点净距', 'b5', P.B5_BUDGET, 'ge'))
    fewer = []
    for r in ok_screen:
        less = {n: [base_bends[n], b] for n, b in r['metrics']['m1']['per_line'].items() if b < base_bends.get(n, b)}
        if not less:
            continue
        panel = r['panel']
        bad = [name for name, key, limit, way in limits
               if panel.get(key) is not None and (panel[key] > limit if way == 'le' else panel[key] < limit)]
        if panel['b1'] > screen['base_panel']['b1'] or panel['v2'] or panel['v13']:   # 原图自带 1 处已验证的跨线桥
            bad.append('硬项 b1/v2/v13 = %s/%s/%s' % (panel['b1'], panel['v2'], panel['v13']))
        fewer.append(dict(id=r['id'], fewer=less, panel={k: panel.get(k) for k in ('b1', 'b2tot', 'b2max', 'b3', 'b4', 'b5', 'v2', 'v13')},
                          violates=bad))
    summary['in_process_fewer_bends'] = dict(count=len(fewer), with_violation=sum(1 for f in fewer if f['violates']), rows=fewer)

    # M4：原图较宽的带里最近的三处，以及同类图里出现过的间距
    summary['m4'] = dict(
        base_events_within_64=sorted(q[0] for q in details[B.BASE_KEY]['full']['corridor'] if q[0] <= 64),
        class_gaps=sorted({q[0] for k in (x['key'] for x in cls) for q in _arr(k, 'corridor')}),
        class_gap_counts={str(g): sum(1 for x in cls if any(q[0] == g for q in _arr(x['key'], 'corridor'))) for g in sorted({q[0] for x in cls for q in _arr(x['key'], 'corridor')})})

    # 进程内评估与官方报告对不对账：第二轮走完官方链的 245 张逐项比（决定「只认官方报告」的依据）
    screen_by_id = {r['id']: r for r in screen['rows']}

    def _ip(cid):
        r = screen_by_id.get(cid)
        return r['metrics'] if r and r.get('ok') else None

    def _first(v):
        return v[0] if isinstance(v, list) else v

    pairs = (('m1_max', lambda m: m['m1']['max']), ('m1_sum', lambda m: m['m1']['sum']), ('m2_rev', lambda m: m['m2']['reversals']),
             ('m3_max', lambda m: m['m3']['gap_max']), ('m3_far', lambda m: len(m['m3']['far'])),
             ('m3_amb', lambda m: len(m['m3']['ambiguous'])), ('m4_n', lambda m: m['m4']['count']),
             ('m5_min', lambda m: m['m5']['min']), ('m6_jg', lambda m: m['m6']['junction_gap']['d']),
             ('m6_jb', lambda m: m['m6']['junction_bend']['d']),
             ('m6_br', lambda m: _first([b['other_gap'] for b in m['m6']['bridges']])))
    cmp = {}
    for field, get in pairs:
        same = diff = err = 0
        for x in sheets:
            if not x['key'].startswith('r2:') or x['key'] == B.BASE_KEY:
                continue
            m = _ip(x['key'].split(':', 1)[1])
            try:
                if abs(float(get(m)) - float(x[field])) < 0.05:
                    same += 1
                else:
                    diff += 1
            except (TypeError, ValueError, KeyError, IndexError):
                err += 1
        cmp[field] = dict(same=same, differ=diff, not_comparable=err)
    confirmed = [x for x in sheets if x['key'].startswith('r2:') and not x['key'].startswith('r2x:')]
    summary['official_vs_in_process'] = dict(
        sheets=len(confirmed), by_metric=cmp,
        official_fail_over_0=sum(1 for x in confirmed if x['fail']),
        official_same_class=sum(1 for x in confirmed if x['same_class']))
    summary['attempts'] = dict(
        round1=dict(candidates=len(v1['rows']), blocked=sum(1 for r in v1['rows'] if not r['ok']),
                    rendered=sum(1 for r in v1['rows'] if r['ok']),
                    hard_defect_no_report=sum(1 for r in v1['rows'] if r['ok'] and r.get('fail'))),
        round2=dict(confirmed=len(confirmed)), extras=dict(attempted=len(extras)),
        with_report=len(sheets) - 1)

    # 给反例演示补出的几张：标签贴近主人，但标签净空变差
    extra = []
    for r in json.loads((B.ART / 'mine2/extra.json').read_text(encoding='utf-8')):
        if not r['ok']:
            extra.append(dict(id=r['id'], ok=False, error=r['error']))
            continue
        b7 = (r['budget'].get('B7') or {}).get('measured') or {}
        extra.append(dict(id=r['id'], ok=True, fail=r['fail'], warn=r['warn'],
                          b7_violations=int(b7.get('violations') or 0),
                          non_pass=sorted(k for k, v in r['budget'].items() if v['status'] != 'pass'),
                          m3_far=r['metrics']['m3']['far'], m3_ambiguous=r['metrics']['m3']['ambiguous'],
                          over=B.over_budget('r2x:' + r['id'], rows),
                          same_class=by_key.get('r2x:' + r['id'], {}).get('same_class')))
    summary['extra'] = extra
    (OUT / 'class-summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')

    print('sheets %d, fail0 %d, same class %d %s' % (summary['sheets'], summary['fail0'], summary['same_class'],
                                                     summary['same_class_by_kind']))
    print('base fail %d warn %d over %d length %s' % (base['fail'], base['warn'], base['over'], base['length']))
    for f in FIELDS:
        if f in summary['class_range']:
            print('  %-9s base %-8s class %-18s rho(length) %s' % (
                f, base[f], summary['class_range'][f], summary['spearman_with_length'][f]))
    print('rho(m1_sum, m2_rev) =', summary['spearman_m1_sum_m2_rev'])
    print('class m1/m2 independence:', summary['class_m1_m2_independence'])
    print('sheets with any line having fewer bends than base:', summary['sheets_any_line_fewer_bends'], summary['lines_fewer_bends_sheets'])
    for name, d in summary['over_threshold'].items():
        print('  over %-40s base %s class %s' % (name, d['base'], d['class_sheets']))
    lv = summary['label_variants']
    print('label variants:', {k: lv[k] for k in ('round1', 'round2', 'multi_label_extras')})
    print('official vs in-process:', summary['official_vs_in_process'])
    print('attempts:', summary['attempts'])
    print('in-process fewer bends:', summary['in_process_fewer_bends']['count'], 'with violation', summary['in_process_fewer_bends']['with_violation'])
    print('m4:', summary['m4']['base_events_within_64'], summary['m4']['class_gap_counts'])
    print('r1 class sheets identical in all metrics: %d' % summary['r1_class_identical_metrics'])
    for name, v in lines.items():
        print('  line %-22s bends %d class %s  rev %d class %s  (n=%d)' % (
            name, v['base_bends'], v['class_bends'], v['base_reversals'], v['class_reversals'], v['class_sheets']))
    print('screen:', summary['screen'])
    for e in extra:
        print('  extra', json.dumps(e, ensure_ascii=False))


if __name__ == '__main__':
    main()
