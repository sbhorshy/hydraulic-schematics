#!/usr/bin/env python3
"""一次性原型（issue 102）：把分诊结果和真实回读页打包成单文件决策页。

输入是 make_cases.py 写在被忽略目录里的 `.artifacts/issue102/cases/<名字>/`
（官方链产物：validation-report、browser-evidence、PNG、readback.html）。
本脚本对每张图跑一遍分诊模块，连同「现状」用的真实回读页一起嵌进
readback-triage-prototype.html。页面无服务端、无持久化，双击即可打开。

用法（仓库根目录）：先 python3 research/issue102/make_cases.py，再
python3 research/issue102/build_prototype.py
"""
import base64
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / '.agents' / 'skills' / 'hydraulic-schematic' / 'scripts'))
sys.path.insert(0, str(HERE))

import make_cases                                                            # noqa: E402
import proto_issue102_readback_triage as t                                    # noqa: E402
import sheet_diff                                                             # noqa: E402

CASES = ROOT / '.artifacts' / 'issue102' / 'cases'
OUT = HERE / 'readback-triage-prototype.html'
VIEW = (0, 0, 1710, 1390)
REACH = {'tight': 90.0, 'normal': 170.0, 'wide': 260.0}
FINDING_ROW = re.compile(r'^(V\d+|B\d) ')
FIXED = {
    'local': '定向邻域可修（结构化）', 'route': '交走线 / 规则层（结构化）', 'agent': '交 agent，每次走官方链',
    'disclose': '不修图 · 披露', 'recheck': '随上游恢复',
}


def load(name, file):
    return json.loads((CASES / name / file).read_text(encoding='utf-8'))


def run(report, browser, reference, reference_browser):
    """One triage pass; problems also carry their crops at the three context widths."""
    ctx = t.set_viewbox(t.context(report, browser, reference, reference_browser), VIEW)
    result = t.build(t.locate(report, ctx), ctx)
    for problem in result['problems']:
        problem['context_reach'] = {key: t.crops(problem, ctx, px) for key, px in REACH.items()}
    for item in result['items']:
        item.pop('rows', None)
    # Enough for the page to re-derive a path when a kind's destination is tried another way: failures
    # outrank hints, and a node_gap cause outranks the label symptoms it produced — regardless of when
    # the row first appeared. symptom_kinds lets the page turn cause-first off for comparison.
    items = {i['id']: i for i in result['items']}
    for problem in result['problems']:
        aim = items[problem['suggestion']['aim']]
        group = [items[i] for i in problem['items']]
        fails = [i for i in group if i['result'] == 'fail']
        cause = aim['kind'] == 'node_gap' and any(i['class'] == 'label' for i in group)
        pool = ([aim] + [i for i in fails if i['class'] != 'label']) if cause else (fails or group)
        again = max((_own(t, i) for i in pool), key=WEIGHT.get)
        assert again == problem['suggestion']['fix_path'], (problem['title'], again, problem['suggestion']['fix_path'])
        problem['suggestion'].update({
            'aim_kind': [aim['class'], aim['kind'], aim['result']],
            'fresh_kinds': sorted({(i['class'], i['kind'], i['result']) for i in pool}),
            'symptom_kinds': sorted({(i['class'], i['kind'], i['result']) for i in group if cause and i['class'] == 'label'}),
            'cause': cause})
    return ctx, result


WEIGHT = {'agent': 4, 'route': 3, 'local': 2, 'recheck': 1, 'disclose': 0}


def _own(module, item):
    """Fix path of one finding taken by itself."""
    return module._suggest(item, [item], sorted(item['nodes']), sorted(item['edges']))[2]


def page_facts(page):
    """What the current page shows: where the findings sit in the object list."""
    stripped = re.sub(r'data:image/png;base64,[A-Za-z0-9+/=]+', '', page)
    rows = re.findall(r'<tr>(.*?)</tr>', stripped, flags=re.S)[1:]
    found = [i for i, row in enumerate(rows) if FINDING_ROW.match(re.sub(r'<[^>]+>', '', row))]
    only_sheet = sum(1 for i in found if 'href="#overview"' in rows[i] and 'href="#region-' not in rows[i])
    return {'rows': len(rows), 'findings': len(found), 'first': found[0] + 1 if found else None,
            'last': found[-1] + 1 if found else None, 'overview_only': only_sheet, 'regions': stripped.count('<section id="region-')}


def sheet(name):
    edits, stratum, note = make_cases.CASES[name]
    edited = sorted({key[1] for key in edits})
    report, browser = load(name, 'validation-report.json'), load(name, 'browser-evidence.json')
    raw = base64.b64encode((CASES / name / 'sheet-readback.png').read_bytes()).decode('ascii')
    png = 'data:image/png;base64,' + raw
    page = (CASES / name / 'readback.html').read_text(encoding='utf-8')
    assert page.count(png) == 1, 'the full-sheet image should be embedded once'
    page = page.replace(png, '__PNG__')
    base_report, base_browser = load('base', 'validation-report.json'), load('base', 'browser-evidence.json')

    # The default view compares against the frozen base; the base itself has nothing before it.
    _, now = run(report, browser, None if name == 'base' else base_report, None if name == 'base' else base_browser)
    _, blind = run(report, browser, None, None)
    problems = now['problems']
    now['orders'] = {'%s|%s|%s' % (rule, stay, notes): [p['id'] for p in t.order(problems, rule, stay, notes)]
                     for rule in t.RULES for stay in t.PERSISTING for notes in t.NOTES}
    model = {'topology': report['topology']}
    now['repair'] = {}
    for rule in t.RULES:
        order = t.repair_order(problems, rule)
        try:
            sheet_diff._scope(dict(order['diff_scope']), [model, model])
            order['scope_ok'] = True
        except ValueError as error:
            order['scope_ok'] = False
            order['scope_error'] = str(error)
        now['repair'][rule] = order
    now['diff_ready'] = bool(report.get('topology', {}).get('coverage_status') == 'pass'
                             and not report.get('geometry', {}).get('issues') and browser.get('status') == 'pass')

    def names(problem):
        return bool(set(problem['scope']['nodes']) & set(edited)
                    or {s['id'] for s in problem['suspects'] if s['level'] == 2} & set(edited))

    ranked = [p for p in problems if p['class'] not in ('disclosure', 'unchecked')]
    flat = t.flat(now['items'])
    by_id = {p['id']: p for p in problems}
    check = {}
    for rule in t.RULES:
        top = next((p for p in t.order(problems, rule) if p['class'] not in ('disclosure', 'unchecked')), None)
        check[rule] = {'ok': names(top) if top and edited else None, 'title': top['title'] if top else '', 'id': top['id'] if top else None}
    check['flat'] = ({'ok': names(by_id[flat[0]['problem']]), 'detail': flat[0]['detail'][:60]} if flat else None) if edited else None
    new_rows = sum(i['state'] == 'new' and i['class'] not in ('disclosure', 'unchecked') for i in now['items'])
    check['fanout'] = {'rows': new_rows, 'problems': sum(p['state'] == 'new' for p in ranked)}
    return {
        'name': name, 'stratum': stratum, 'note': note, 'edit': '；'.join('%s.%s' % (k[1], k[2]) for k in edits) or '无',
        'trial': name in make_cases.TRIALS, 'fail': report['fail_count'], 'warn': report['warn_count'],
        'coverage': report.get('topology', {}).get('coverage_status'), 'png': png,
        'page': page, 'facts': page_facts(page), 'check': check,
        'triage': now, 'blind': {'problems': blind['problems'], 'summary': blind['summary'], 'resolved': []},
    }


def resolved_views():
    """The base seen from each broken sheet: what the broken rows become once the edit is undone."""
    report, browser = load('base', 'validation-report.json'), load('base', 'browser-evidence.json')
    out = {}
    for name in make_cases.CASES:
        if name == 'base':
            continue
        _, result = run(report, browser, load(name, 'validation-report.json'), load(name, 'browser-evidence.json'))
        out[name] = {'problems': result['problems'], 'resolved': result['resolved'], 'summary': result['summary']}
    return out


def kinds(sheets):
    """Every finding kind in the sample (class x kind x level): the fix path one such finding gets on
    its own, how many lead a problem, how many ride in a problem led by something else, and samples."""
    EXTRA = {
        'unchecked': '未校核（上游有未决项）',     # the module has no display name for the bare row
    }
    table = {}
    for name, data in sheets.items():
        tri = data['triage']
        items = {i['id']: i for i in tri['items']}
        for item in tri['items']:
            key = (item['class'], item['kind'], item['result'])
            action, text, path = t._suggest(item, [item], sorted(item['nodes']), sorted(item['edges']))
            row = table.setdefault(key, {
                'class': key[0], 'kind': key[1], 'name': EXTRA.get(key[1]) or (t.KIND_TEXT.get(key[1]) or (t.SHORT.get(key[1], key[1]),))[0],
                'result': key[2], 'path': path, 'action': action, 'items': 0, 'led': 0, 'led_items': 0,
                'sample': None, 'joined': None})
            row['items'] += 1
            if row['sample'] is None:
                row['sample'] = {'sheet': name, 'title': t._title([item], sorted(item['nodes']), sorted(item['edges'])),
                                 'text': text, 'objects': sorted(item['nodes'])[:4] + sorted(item['edges'])[:4]}
        for problem in tri['problems']:
            lead = items[problem['lead']]
            key = (lead['class'], lead['kind'], lead['result'])
            row = table[key]
            row['led'] += 1
            row['led_items'] += sum((items[i]['class'], items[i]['kind'], items[i]['result']) == key for i in problem['items'])
            if row['joined'] is None and problem['suggestion']['fix_path'] != row['path']:
                row['joined'] = {'sheet': name, 'title': problem['title'], 'action': problem['suggestion']['action'],
                                 'path': problem['suggestion']['fix_path'], 'text': problem['suggestion']['text']}
    for row in table.values():
        row['rides'] = row['items'] - row['led_items']
    return sorted(table.values(), key=lambda r: (t.CLASS_ORDER.index(r['class']), t.SEVERITY[r['result']], r['kind']))


def main():
    started = time.time()
    base = sheet('base')
    sheets = {'base': base}
    for name in make_cases.CASES:
        if name != 'base':
            sheets[name] = sheet(name)
    base['behind'] = resolved_views()
    data = {
        'view': list(VIEW), 'reach': REACH,
        'labels': {'class': t.CLASS_LABEL, 'why': t.CLASS_WHY, 'rule': t.RULE_LABEL, 'state': t.STATE_LABEL,
                   'severity': t.SEVERITY_LABEL, 'path': t.FIX_PATH},
        'trials': list(make_cases.TRIALS), 'sheets': sheets, 'kinds': kinds(sheets),
    }
    # "<" is escaped so no embedded page can close the data element; JSON.parse turns it back.
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    payload = payload.replace('<', '\\u003c').replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    html = HEAD + CSS + MID + payload + TAIL + JS + END
    OUT.write_text(html, encoding='utf-8')
    print('%s  %.1f MB  %d 张图  %d 种缺陷  %.1f s' % (OUT.name, OUT.stat().st_size / 1e6, len(sheets), len(data['kinds']),
                                                     time.time() - started))
    for name, one in sheets.items():
        print('  %-15s fail=%-2d warn=%-2d rows=%d findings=%d first=%s overview_only=%d regions=%d named=%s' % (
            name, one['fail'], one['warn'], one['facts']['rows'], one['facts']['findings'], one['facts']['first'],
            one['facts']['overview_only'], one['facts']['regions'],
            ''.join('✓' if one['check'][r]['ok'] else '✗' if one['check'][r]['ok'] is False else '·' for r in t.RULES)
            + ('/B✓' if (one['check']['flat'] or {}).get('ok') else '/B✗' if one['check']['flat'] else '')))


CSS = (HERE / 'prototype.css').read_text(encoding='utf-8')
JS = (HERE / 'prototype.js').read_text(encoding='utf-8')
HEAD = """<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>回读分诊原型</title>
<style>
"""
MID = """</style>
<script type="application/json" id="data">"""
TAIL = """</script>
<body>
<div id="app"></div>
<script>
"""
END = "</script>\n</body>\n</html>\n"

if __name__ == '__main__':
    main()
