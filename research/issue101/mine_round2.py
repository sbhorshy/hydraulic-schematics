# -*- coding: utf-8 -*-
"""#101 一次性挖掘（第二轮）：进程内快速筛 -> 官方出图链确认（不进 main）。

第一轮只走了单步邻域（mine_variants.py）：259 张与基线 B1–B7 状态相同的图里，
走线类指标几乎不动。这一轮用寻优器同一口径的进程内评估
（proto_issue101_readability.summarize_in_process，约 0.1 s/张）扫更大的改动
（元件挪位网格、母线/走廊平移、标签槽与偏移、多步组合），按候选指标挑极值，
再送官方 render -> validate 确认。进程内只量 B1–B5 与 V2/V13；B6/B7 与 fail 数以官方链为准。

运行产物只写被忽略的 .artifacts/issue101/mine2/。
用法（仓库根目录）:
  python3 research/issue101/mine_round2.py screen  [--random N] [--workers 10]
  python3 research/issue101/mine_round2.py confirm [--pick picks.json] [--workers 4]
"""
import argparse
import copy
import inspect
import io
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/hydraulic-schematic/scripts'
PROJECT = ROOT / '1#系统原理图'
OUT = ROOT / '.artifacts/issue101/mine2'
sys.path.insert(0, str(SCRIPTS))
import render_l0_sheet as RS  # noqa: E402
import proto_optimize as P  # noqa: E402
import proto_issue101_readability as R  # noqa: E402
import mine_variants as V1  # noqa: E402

INTENT = CATALOG = BASE = BPANEL = None


# ---------- 进程内面板：与寻优器同源，但符号取 1# 工作目录（同 #99 原型的做法） ----------

def project_bpanel(project_dir):
    """proto_optimize.bpanel 硬编码 skill 自带符号库；1# 布局的 EMP 镜像登记只对
    工作目录符号有效。只把库路径与元件盒（旋转后按实际缩放尺寸）换掉。"""
    src = inspect.getsource(P.bpanel)
    old = "cat_dir=os.path.join(HERE, '..', 'assets', 'component-library')"
    assert old in src
    src = src.replace(old, "cat_dir=_PROJECT, workdir=_PROJECT")
    old_boxes = """boxes = {inst: (nd['x'], nd['y'], nd['x'] + nd['w'], nd['y'] + nd['h'])
             for inst, nd in L['nodes'].items()}"""
    assert old_boxes in src, 'box geometry changed in proto_optimize'
    src = src.replace(old_boxes, "boxes = _rotated_boxes(L)")
    ns = dict(P.__dict__)
    ns['_PROJECT'] = str(project_dir)

    def _rotated_boxes(L):
        return {i: (nd['x'], nd['y'],
                    nd['x'] + (nd['_H'] if nd['_rot'] % 180 else nd['_W']),
                    nd['y'] + (nd['_W'] if nd['_rot'] % 180 else nd['_H']))
                for i, nd in L['nodes'].items()}
    ns['_rotated_boxes'] = _rotated_boxes
    exec(src, ns)
    return ns['bpanel']


def setup():
    global INTENT, CATALOG, BASE, BPANEL
    INTENT = RS.load_yaml(str(PROJECT / '1#系统.intent.yaml'))
    CATALOG = json.loads((PROJECT / 'component-catalog.json').read_text(encoding='utf-8'))
    BASE = json.loads((PROJECT / '1#系统.layout.json').read_text(encoding='utf-8'))
    BPANEL = project_bpanel(PROJECT)


# ---------- 改动词表：每个候选 = 一串原子改动，作用于人工认可的基线布局 ----------

def apply(base, ops):
    """原子改动依次作用；返回新布局或 None（越出画布）。

    走线类改动直接用寻优器的邻域动作（proto_optimize.apply_move 的 move 元组），
    标签改动用 mine_variants.label_variant。
    """
    L = copy.deepcopy(base)
    for op in ops:
        if op[0] == 'label':
            L = V1.label_variant(L, op[1], op[2], op[3])
            continue
        L = P.apply_move(L, op)
        if L is None:
            return None
    return L


def op_id(ops):
    parts = []
    for o in ops:
        if o[0] == 'label':
            parts.append('lab_%s_%s_%d' % (o[1], o[2], o[3]))
        else:
            parts.append('-'.join(str(x) for x in o))
    return '__'.join(parts)


def candidates(random_count):
    out = []

    def add(ops):
        out.append((op_id(ops), ops))

    steps = [-80, -60, -40, -20, 20, 40, 60, 80]
    for inst, nd in BASE['nodes'].items():
        if 'hydraulic-user' in nd['symbol']:
            continue
        for dx in steps:
            for dy in steps:
                add([('node_move', inst, dx, dy)])
    for name in BASE['buses']:
        for dx in (-120, -100, -80, -60, -40, -20, 20, 40, 60, 80, 100, 120):
            add([('bus_move', name, dx)])
    for i, y in enumerate(BASE.get('lanes') or []):
        for dy in (-100, -80, -60, -40, -20, 20, 40, 60, 80, 100):
            add([('lane_move', i, dy)])
    for i, x in enumerate(BASE.get('vlanes') or []):
        for dx in (-120, -100, -80, -60, -40, -20, 20, 40, 60, 80, 100, 120):
            add([('vlane_move', i, dx)])
    for inst in BASE['labels']:
        if 'hydraulic-user' in BASE['nodes'][inst]['symbol']:
            continue
        for drop in range(0, 201, 20):
            add([('label', inst, 'below', drop)])
        for lift in range(0, 161, 20):
            add([('label', inst, 'above', lift)])
        add([('label', inst, 'right', 0)])
    for seed in range(random_count):
        r = random.Random(seed)
        L, ops = BASE, []
        for _ in range(r.choice((2, 2, 3, 3, 4))):
            pool = P.neighbors(L)
            kind = r.choice(('node', 'node', 'node', 'bus', 'lane', 'vlane'))
            pool = [m for m in pool if m[0] in (
                ('node_move',) if kind == 'node' else ('bus_move',) if kind == 'bus'
                else ('lane_move', 'lane_add') if kind == 'lane' else ('vlane_move', 'vlane_add'))]
            if not pool:
                continue
            m = r.choice(pool)
            if m[0] == 'node_move' and 'hydraulic-user' in L['nodes'][m[1]]['symbol']:
                continue
            L2 = P.apply_move(L, m)
            if L2 is None:
                continue
            L, _ = L2, ops.append(tuple(m))
        if ops:
            add(ops)
    seen, uniq = set(), []
    for cid, ops in out:
        if cid not in seen:
            seen.add(cid)
            uniq.append((cid, ops))
    return uniq


# ---------- 进程内筛选 ----------

def screen(item):
    cid, ops = item
    started = time.monotonic()
    row = dict(id=cid, ops=ops)
    L = apply(BASE, ops)
    if L is None:
        row.update(ok=False, error='out of canvas')
        return row
    try:
        bp = BPANEL(L, INTENT, CATALOG)
        if bp.get('routing_error'):
            anchor = bp['routing_error'].get('anchor') if isinstance(bp['routing_error'], dict) else str(bp['routing_error'])
            row.update(ok=False, error='routing blocked: %s' % anchor)
            return row
        res, _ev = R.summarize_in_process(L, INTENT, CATALOG, PROJECT)
    except Exception as error:  # 原型：把异常记成数据，不中断整批
        row.update(ok=False, error='%s: %s' % (type(error).__name__, error))
        return row
    row.update(ok=True, panel={k: v for k, v in bp.items() if k != 'b3_exempt'},
               metrics=res, seconds=round(time.monotonic() - started, 2))
    return row


def do_screen(args):
    setup()
    items = candidates(args.random)
    (OUT / 'var').mkdir(parents=True, exist_ok=True)
    print('candidates: %d' % len(items), flush=True)
    started = time.monotonic()
    rows = []
    import multiprocessing
    with multiprocessing.Pool(args.workers, initializer=setup) as pool:
        for row in pool.imap_unordered(_screen_item, items, chunksize=8):
            rows.append(row)
    rows.sort(key=lambda r: r['id'])
    base_bp = BPANEL(BASE, INTENT, CATALOG)
    summary = dict(candidates=len(items), seconds=round(time.monotonic() - started, 1),
                   base_panel={k: v for k, v in base_bp.items() if k != 'b3_exempt'},
                   params=R.PARAMS, rows=rows)
    (OUT / 'screen.json').write_text(json.dumps(summary, ensure_ascii=False), encoding='utf-8')
    print('done %d in %.0fs: ok %d' % (len(rows), time.monotonic() - started,
                                       sum(1 for r in rows if r['ok'])))


def _screen_item(item):
    return screen(item)


# ---------- 官方链确认 ----------

def do_confirm(args):
    setup()
    data = json.loads((OUT / 'screen.json').read_text(encoding='utf-8'))
    rows = {r['id']: r for r in data['rows']}
    ids = json.loads(Path(args.pick).read_text(encoding='utf-8')) if args.pick else list(rows)
    items = [(cid, rows[cid]['ops']) for cid in ids if cid in rows]
    V1.OUT = OUT  # 官方链产物落到 mine2/var/<id>/
    import multiprocessing
    done = []
    with multiprocessing.Pool(args.workers, initializer=_setup_v1) as pool:
        for row in pool.imap_unordered(_confirm_item, items):
            done.append(row)
            print('[%3d/%3d] %-60s %s' % (len(done), len(items), row['id'],
                                          'ERR ' + row['error'] if not row['ok'] else
                                          'fail %d warn %d' % (row['fail'], row['warn'])), flush=True)
    done.sort(key=lambda r: r['id'])
    (OUT / 'confirm.json').write_text(json.dumps(done, ensure_ascii=False), encoding='utf-8')
    print('done %d: render-fail %d, fail0 %d' % (len(done), sum(1 for r in done if not r['ok']),
                                                 sum(1 for r in done if r['ok'] and not r['fail'])))


def _setup_v1():
    setup()
    V1.OUT = OUT
    V1.KEEP_FAIL = True


def _confirm_item(item):
    cid, ops = item
    return V1.run((cid, apply(BASE, ops), [list(o) for o in ops]))


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('phase', choices=('screen', 'confirm'))
    ap.add_argument('--workers', type=int, default=10)
    ap.add_argument('--random', type=int, default=4000)
    ap.add_argument('--pick', help='只确认这些候选 id（JSON 列表）')
    args = ap.parse_args()
    (do_screen if args.phase == 'screen' else do_confirm)(args)
