# -*- coding: utf-8 -*-
"""#101 一次性挖掘：同一 1# 输入的布局变体 -> 官方出图链 -> 六项候选指标（不进 main）。

从人工认可的 1# 布局出发，各施加一步可解释的改动（挪元件 / 母线 / 走廊，或挪标签），
每个变体走官方 render -> validate，读取 validation-report.json，再取 B1–B7 面板与
proto_issue101_readability 的六项指标。运行产物只写被忽略的 .artifacts/issue101/mine/。

用法（仓库根目录）:
  python3 research/issue101/mine_variants.py [--workers 4] [--limit N] [--only labels|moves]
"""
import argparse
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/hydraulic-schematic/scripts'
PROJECT = ROOT / '1#系统原理图'
OUT = ROOT / '.artifacts/issue101/mine'
sys.path.insert(0, str(SCRIPTS))
import proto_optimize as P  # noqa: E402
import proto_issue101_readability as R  # noqa: E402

DROPS = (0, 20, 60, 80, 120, 160)
LIFTS = (0, 20, 40, 100, 140)
SLOTS = ('below', 'above', 'right')
KEEP_FAIL = False  # True 时连有 fail 的变体也保留工作目录（第二轮要拿坏图做演示）


def label_variant(base, inst, slot, offset):
    """把 inst 的标签放到 slot 槽，偏移取 offset（below 用 drop，above 用 lift）。"""
    L = copy.deepcopy(base)
    L.setdefault('label_pos', {})[inst] = slot
    L.setdefault('label_drop', {}).pop(inst, None)
    L.setdefault('label_lift', {}).pop(inst, None)
    if slot == 'below' and offset:
        L['label_drop'][inst] = offset
    elif slot == 'above' and offset:
        L['label_lift'][inst] = offset
    return L


def candidates(base, only=None):
    out = []
    if only in (None, 'moves'):
        for m in P.neighbors(base):
            L = P.apply_move(base, m)
            if L is not None:
                out.append(('-'.join(str(x) for x in m), L, [repr(m)]))
    if only in (None, 'labels'):
        for inst in base['labels']:
            node = base['nodes'][inst]
            if 'hydraulic-user' in node['symbol']:
                continue  # 用户框名字在框内名槽，没有框外标签
            slot = base.get('label_pos', {}).get(inst, 'below')
            cur = (base.get('label_drop', {}) if slot == 'below' else base.get('label_lift', {})).get(inst, 0)
            plan = [(slot, o) for o in (DROPS if slot == 'below' else LIFTS) if o != cur]
            plan += [(s, 0) for s in SLOTS if s != slot]
            for s, o in plan:
                out.append(('label_%s_%s_%d' % (s, inst, o), label_variant(base, inst, s, o),
                            ['%s.%s -> %s%s' % (inst, slot, s, '' if not o else ' %+d' % o)]))
    return out


def official(layout, dest):
    """官方链：render -> validate；返回 (report 或 None, 错误文本)。"""
    dest.mkdir(parents=True, exist_ok=True)
    (dest / '1#系统.layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding='utf-8')
    for name in ('1#系统.intent.yaml', '1#系统组件.json', 'component-catalog.json'):
        shutil.copy(PROJECT / name, dest / name)
    shutil.copytree(PROJECT / 'symbols', dest / 'symbols', dirs_exist_ok=True)
    r = subprocess.run([sys.executable, str(SCRIPTS / 'render_l0_sheet.py'), '.'],
                       cwd=dest, capture_output=True, text=True)
    if r.returncode:
        tail = (r.stderr.strip() or r.stdout.strip()).splitlines()[-1:]
        err = dest / 'routing-error.json'
        detail = tail[0][:300] if tail else 'render exit %d' % r.returncode
        if err.is_file():
            try:
                detail += ' | ' + json.loads(err.read_text(encoding='utf-8')).get('anchor', '')[:80]
            except ValueError:
                pass
        return None, detail
    subprocess.run([sys.executable, str(SCRIPTS / 'validate_sheet.py'), '.'],
                   cwd=dest, capture_output=True, text=True)
    return json.loads((dest / 'validation-report.json').read_text(encoding='utf-8')), None


def describe(report):
    fails = [c.get('id') for c in report['checks'] if c.get('result') == 'fail']
    return dict(fail=report['fail_count'], warn=report['warn_count'], fails=fails)


def run(item):
    cid, layout, moves = item
    dest = OUT / 'var' / cid
    started = time.monotonic()
    try:
        report, err = official(layout, dest)
    except Exception as error:  # 原型：把异常记成数据，不中断整批
        report, err = None, '%s: %s' % (type(error).__name__, error)
    row = dict(id=cid, moves=moves, seconds=round(time.monotonic() - started, 1))
    if report is None:
        row.update(ok=False, error=err)
        shutil.rmtree(dest / 'symbols', ignore_errors=True)
        return row
    res, _ev, panel = R.summarize(report)
    row.update(ok=True, **describe(report), budget=panel, metrics=res)
    (dest / 'browser-evidence.json').unlink(missing_ok=True)
    if report['fail_count'] and not KEEP_FAIL:
        shutil.rmtree(dest, ignore_errors=True)  # 有 fail 的变体只留摘要
    return row


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--only', choices=('labels', 'moves'))
    args = ap.parse_args()
    base = json.loads((PROJECT / '1#系统.layout.json').read_text(encoding='utf-8'))
    items = candidates(base, args.only)
    if args.limit:
        items = items[:args.limit]
    (OUT / 'var').mkdir(parents=True, exist_ok=True)
    print('candidates: %d' % len(items), flush=True)
    started = time.monotonic()
    rows = []
    if args.workers > 1:
        import multiprocessing
        with multiprocessing.Pool(args.workers) as pool:
            for row in pool.imap_unordered(run, items):
                rows.append(row)
                print('[%3d/%3d] %-34s %s' % (len(rows), len(items), row['id'],
                                             'ERR ' + row['error'] if not row['ok'] else
                                             'fail %d warn %d' % (row['fail'], row['warn'])), flush=True)
    else:
        for item in items:
            row = run(item)
            rows.append(row)
    rows.sort(key=lambda r: r['id'])
    summary = dict(candidates=len(items), seconds=round(time.monotonic() - started, 1),
                  params=R.PARAMS, rows=rows)
    (OUT / 'variants.json').write_text(json.dumps(summary, ensure_ascii=False), encoding='utf-8')
    ok = [r for r in rows if r['ok']]
    print('done %d in %.0fs: render-fail %d, official fail0 %d, fail>0 %d' % (
        len(rows), time.monotonic() - started, len(rows) - len(ok),
        sum(1 for r in ok if not r['fail']), sum(1 for r in ok if r['fail'])))


if __name__ == '__main__':
    main()
