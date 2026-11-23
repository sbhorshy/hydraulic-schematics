"""Throwaway core for issue #99: focused vs budgeted layout optimization."""
import importlib.util, inspect, json, math, random, re, shutil, subprocess, sys, time
from pathlib import Path

ROOT = Path('/root/orca/workspaces/组件库/issue-99')
SCRIPTS = ROOT / '.agents/skills/hydraulic-schematic/scripts'
sys.path.insert(0, str(SCRIPTS))
import proto_optimize as P  # noqa: E402

COORD = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)')
TARGET_LIMIT = {'b1': 1.0, 'v2': 0.0, 'v13': 0.0, 'b3': 1.5, 'b4': 8.0, 'b5': 40.0,
                'b2tot': 40.0, 'b2max': 3.0}


PROJECT_SYMBOLS = None


def use_project_symbols(symbols_dir):
    global PROJECT_SYMBOLS
    PROJECT_SYMBOLS = str(symbols_dir)
    """The fast evaluator hardcodes the skill's bundled symbol library; the 1#
    workdir has its own (registered) copies. Rebind only that path in the
    throwaway harness so both strategies evaluate the same sheet as the CLI."""
    src = inspect.getsource(P.bpanel)
    old = "cat_dir=os.path.join(HERE, '..', 'assets', 'component-library')"
    assert old in src
    src = src.replace(old, "cat_dir=_PROJECT_SYMBOLS")
    old_boxes = """boxes = {inst: (nd['x'], nd['y'], nd['x'] + nd['w'], nd['y'] + nd['h'])
             for inst, nd in L['nodes'].items()}"""
    assert old_boxes in src, 'box geometry changed in proto_optimize'
    src = src.replace(old_boxes, "boxes = _rotated_boxes(L)")
    ns = dict(P.__dict__)
    ns['_PROJECT_SYMBOLS'] = str(symbols_dir)

    def _rotated_boxes(layout):
        boxes = {}
        for inst, nd in layout['nodes'].items():
            w, h = nd.get('w', 0), nd.get('h', 0)
            if int(nd.get('rot', 0) or 0) % 180 == 90:
                w, h = h, w
            boxes[inst] = (nd['x'], nd['y'], nd['x'] + w, nd['y'] + h)
        return boxes

    ns['_rotated_boxes'] = _rotated_boxes
    exec(src, ns)
    P.bpanel = ns['bpanel']


def crossing_centers(layout, intent, catalog):
    """B1 findings carry no coordinates in validation-report; recover the
    crossing points from the same in-process geometry the evaluator uses."""
    s = P.R.Sheet(intent, layout, catalog, cat_dir=PROJECT_SYMBOLS)
    s.place()
    s.build_textboxes()
    _segs, junc, _bus, _polys = s.wire()
    s.wire_taps()
    cross = s.find_crossings(junc, s.polys)
    return [(float(x), float(y)) for x, y, *_ in cross]


def finding_targets(report):
    targets, centers = [], []
    for c in report.get('checks', []):
        if c.get('result') != 'fail':
            continue
        code = c.get('id')
        detail = c.get('detail', '')
        if code == 'V13':
            targets.append('v13')
        elif code == 'V2':
            targets.append('v2')
        elif code == 'V19' and 'B1' in detail:
            targets.append('b1')
        elif code == 'V19' and 'B3' in detail:
            targets.append('b3')
        elif code in ('V12', 'V19') and c.get('budget_id') == 'B7':
            targets.append('text')
        else:
            targets.append('other:' + code)
        for x, y in COORD.findall(detail):
            centers.append((float(x), float(y)))
        for key in ('position', 'bbox'):
            val = c.get(key)
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                if isinstance(val[0], (int, float)):
                    centers.append((float(val[0]), float(val[1])))
    return sorted(set(targets)), centers


def focus_elements(layout, centers, radius=190.0):
    focus = {'nodes': set(), 'buses': set(), 'lanes': set(), 'vlanes': set()}
    if not centers:
        return focus
    nodes = layout['nodes']
    for cx, cy in centers:
        for name, nd in nodes.items():
            x0, y0 = nd['x'], nd['y']
            w, h = nd.get('w', 0), nd.get('h', 0)
            if int(nd.get('rot', 0) or 0) % 180 == 90:
                w, h = h, w
            x1, y1 = x0 + w, y0 + h
            d = math.hypot(max(x0 - cx, cx - x1, 0.0), max(y0 - cy, cy - y1, 0.0))
            if d <= radius:
                focus['nodes'].add(name)
        for name, bd in layout.get('buses', {}).items():
            if abs(cx - bd['x']) <= radius:
                focus['buses'].add(name)
        for i, y in enumerate(layout.get('lanes') or []):
            if abs(cy - y) <= radius:
                focus['lanes'].add(i)
        for i, x in enumerate(layout.get('vlanes') or []):
            if abs(cx - x) <= radius:
                focus['vlanes'].add(i)
    return focus


def focused_neighbors(layout, focus):
    moves = P.neighbors(layout)
    if not any(focus.values()):
        return moves, False
    kept = []
    for m in moves:
        op = m[0]
        if op == 'bus_move' and m[1] in focus['buses']:
            kept.append(m)
        elif op == 'node_move' and m[1] in focus['nodes']:
            kept.append(m)
        elif op in ('lane_move', 'lane_del') and m[1] in focus['lanes']:
            kept.append(m)
        elif op in ('vlane_move', 'vlane_del') and m[1] in focus['vlanes']:
            kept.append(m)
    # If the finding geometry names no movable element, keep the full neighborhood
    # (recorded as fallback in the result) instead of pretending to be focused.
    return (kept or moves), not kept


def target_ok(bp, targets, seed_bp, seed_e):
    if not targets:
        return False
    for t in targets:
        if t == 'text' or t.startswith('other:'):
            return False  # not represented in the fast B-panel
        if t in ('b1', 'b3'):
            if bp[t] > TARGET_LIMIT[t] + 1e-9:
                return False
        elif t in ('v2', 'v13'):
            if bp[t] >= seed_bp[t]:
                return False
        elif bp[t] < seed_bp[t] - 1e-9:
            return False
    return P.violations(bp) < seed_e[0]


def focused_climb(L0, intent, catalog, log, *, targets, focus, seed_bp, seed_e,
                  seed=19, max_evals=200, max_steps=50, max_seconds=30.0,
                  polish_steps=0, initial_bp=None, progress=None):
    started = time.monotonic()
    rng = random.Random(seed)
    bp = initial_bp if initial_bp is not None else P.bpanel(L0, intent, catalog)
    cur, e = L0, P.energy(bp)
    evals, steps, polished = 1, 0, 0
    budgets = dict(max_evals=max_evals, max_steps=max_steps,
                   max_seconds=max_seconds, polish_steps=polish_steps)
    emit = progress or (lambda event: None)

    def event(kind, **extra):
        return dict(tag='focused', event=kind, step=steps, steps=steps, evals=evals,
                    elapsed_s=round(time.monotonic() - started, 6), energy=e,
                    bp=bp, targets=targets, focus={k: sorted(map(str, v)) for k, v in focus.items()}, **extra)

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
    while True:
        if target_ok(bp, targets, seed_bp, seed_e) and polished >= polish_steps:
            reason = 'target_cleared'
            break
        reason = budget_stop()
        if reason:
            break
        moves, fallback = focused_neighbors(cur, focus)
        rng.shuffle(moves)
        found = None
        for move in moves:
            reason = budget_stop()
            if reason:
                break
            cand = P.apply_move(cur, move)
            if cand is None:
                continue
            cbp = P.bpanel(cand, intent, catalog)
            evals += 1
            ce = P.energy(cbp)
            if ce < e:
                found = (cand, cbp, ce, move)
                break
        if found is None:
            reason = reason or budget_stop() or 'local_minimum'
            break
        cur, bp, e, move = found
        steps += 1
        log.append(event('accepted', move=repr(move)))
        emit(log[-1])
    log.append(event('stop', stop_reason=reason, budgets=budgets, move=None))
    emit(log[-1])
    return cur, bp, e


def run_search(layout_path, intent, catalog, strategy, report=None, budget=None):
    budget = budget or {}
    L = json.loads(layout_path.read_text())
    seed_bp = P.bpanel(L, intent, catalog)
    P.NO_REGRESSION.clear()
    P.NO_REGRESSION.update({k: seed_bp[k] for k in ('b1', 'b2tot', 'b2max', 'b4', 'b5')
                            if seed_bp.get(k) is not None})
    seed_e = P.energy(seed_bp)
    log, started = [], time.monotonic()
    targets, focus, fallback = [], {}, False
    if strategy == 'focused' and (report is None or
                                  not any(c.get('result') == 'fail'
                                          for c in report.get('checks', []))):
        # No findings: a targeted strategy has nothing to target. The first
        # usable sheet is the seed itself, with one measurement and zero moves.
        out, bp, e = L, seed_bp, seed_e
        stop = {'stop_reason': 'no_findings', 'evals': 1, 'steps': 0}
        moves = P.neighbors(L)
    elif strategy == 'focused':
        assert report is not None
        targets, centers = finding_targets(report)
        if 'b1' in targets:
            centers += crossing_centers(L, intent, catalog)
        focus = focus_elements(L, centers)
        moves, fallback = focused_neighbors(L, focus)
        out, bp, e = focused_climb(
            L, intent, catalog, log, targets=targets, focus=focus,
            seed_bp=seed_bp, seed_e=seed_e, initial_bp=seed_bp,
            **{k: v for k, v in budget.items() if k in
               ('seed', 'max_evals', 'max_steps', 'max_seconds', 'polish_steps')})
    else:
        out, bp, e = P.climb(L, intent, catalog, log, 'budgeted',
                             initial_bp=seed_bp, progress=lambda _e: None,
                             **{k: v for k, v in budget.items() if k in
                                ('seed', 'max_evals', 'max_steps', 'max_seconds', 'polish_steps')})
    stop = next((x for x in reversed(log) if x['event'] == 'stop'), {})
    reason = stop.get('stop_reason') or (
        'no_findings' if strategy == 'focused' and not targets else None)
    return dict(strategy=strategy, layout=out, seed_bp=seed_bp, final_bp=bp,
                seed_e=seed_e, energy=e, targets=targets,
                focus={k: sorted(map(str, v)) for k, v in focus.items()},
                fallback=fallback, focus_move_count=len(moves) if strategy == 'focused' else None,
                global_move_count=len(P.neighbors(L)), stop_reason=reason,
                evals=stop.get('evals', 1), steps=stop.get('steps', 0),
                elapsed_s=round(time.monotonic() - started, 3), log=log)


def render_and_validate(layout, dest, intent_path, catalog_path):
    dest.mkdir(parents=True, exist_ok=True)
    (dest / '1#系统.layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2))
    shutil.copy(intent_path, dest / '1#系统.intent.yaml')
    shutil.copy(catalog_path, dest / 'component-catalog.json')
    shutil.copy(ROOT / '1#系统原理图/1#系统组件.json', dest / '1#系统组件.json')
    shutil.copytree(ROOT / '1#系统原理图/symbols', dest / 'symbols', dirs_exist_ok=True)
    timings = {}
    t0 = time.perf_counter()
    r = subprocess.run(['python3', str(SCRIPTS / 'render_l0_sheet.py'), '.'],
                       cwd=dest, capture_output=True, text=True)
    timings['render_s'] = round(time.perf_counter() - t0, 3)
    if r.returncode:
        return {'render_error': r.stderr.strip()[-400:], 'timings': timings}
    t0 = time.perf_counter()
    subprocess.run(['python3', str(SCRIPTS / 'rasterize_sheet.py'), '1#系统原理图.svg',
                    '-o', 'sheet-readback.png'], cwd=dest, check=True, capture_output=True)
    timings['rasterize_s'] = round(time.perf_counter() - t0, 3)
    t0 = time.perf_counter()
    subprocess.run(['python3', str(SCRIPTS / 'validate_sheet.py'), '.'], cwd=dest, capture_output=True)
    timings['validate_s'] = round(time.perf_counter() - t0, 3)
    report = json.loads((dest / 'validation-report.json').read_text())
    return {'fail_count': report['fail_count'], 'warn_count': report['warn_count'],
            'fails': [c.get('id') for c in report['checks'] if c.get('result') == 'fail'],
            'b3': next((i['measured'].get('max') for i in report['composition_budget']['items']
                        if i['id'] == 'B3'), None),
            'timings': timings}
