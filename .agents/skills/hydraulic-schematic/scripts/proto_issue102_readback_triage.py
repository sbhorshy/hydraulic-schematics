"""Throwaway core for issue #102: turn readback findings into ordered, fixable problems.

PROTOTYPE — not wired into the skill. Pure functions over the official validation
report (plus the browser-evidence rows, which carry element ownership). No IO and
no DOM, so the module can be lifted into ``readback_review`` once the decisions hold.

    ctx    = set_viewbox(context(report, browser, reference, reference_browser), viewbox)
    result = build(locate(report, ctx), ctx)       # problems, rows, resolved, summary
    queue  = repair_order(result['problems'], rule)

The unit of the readback page is a *problem*: findings that sit at one place, or
blame the same wire or label, merged — one layout edit usually explains several
rows, and the fix round is capped at two.
"""
import math
import re

CLASS_ORDER = ('connection', 'occlusion', 'label', 'layout', 'disclosure', 'unchecked')
CLASS_LABEL = {
    'connection': '连接语义', 'occlusion': '遮挡', 'label': '标签重叠', 'layout': '版式与预算',
    'disclosure': '输入事实', 'unchecked': '连带未校核',
}
CLASS_WHY = {
    'connection': '读起来会连错线，先修；它还挡着图像差分和 V4/V14',
    'occlusion': '有内容被盖住，可能藏着连错线',
    'label': '字压字，认不出归属',
    'layout': '能读，但绕、挤、贴',
    'disclosure': '输入事实，布局改不了，不进修图单',
    'unchecked': '不是独立问题：上游有未决项，修好后自动恢复校核',
}
CHECK_CLASS = {
    'V3': 'connection', 'V4': 'connection', 'V10': 'connection', 'V13': 'connection',
    'V14': 'connection', 'V17': 'connection',
    'V2': 'occlusion', 'V6': 'occlusion', 'V7': 'occlusion', 'V8': 'occlusion',
    'V12': 'label', 'V11': 'layout',
    'V5': 'disclosure', 'V9': 'disclosure',
}
SEVERITY = {'fail': 0, 'warn': 1, 'not_checked': 2}
SEVERITY_LABEL = {'fail': '失败', 'warn': '提示', 'not_checked': '未校核'}
STATE_LABEL = {'new': '新增', 'persisting': '仍在', 'moved': '仍在（随对象移动）', 'unknown': '未比对'}
# Inside one problem the most specific finding leads: it names the fix.
KIND_RANK = ('collinear_overlap', 'text_overlap', 'text_clearance', 'crossing', 'unexpected_cycle', 'topology',
             'node_gap', 'short_segment', 'corridor', 'group_padding', 'foldback', 'detour')
OBSTACLE = {'suction_marker': '吸油标记', 'graphic': '图元', 'symbol_body': '符号本体', 'symbol_outline': '符号轮廓',
             'text': '文字', 'path': '线条', 'line': '线', 'polyline': '走线', 'circle': '圆', 'rect': '方框'}
# Fix paths carry over from #99 (targeted optimisation) and #100 (local auto-fix).
FIX_PATH = {
    'local': '定向邻域可修',
    'route': '交走线 / 规则层',
    'agent': '交 agent，每次走官方链',
    'disclose': '不修图 · 披露',
    'recheck': '随上游恢复',
}
RULES = ('class', 'location', 'line', 'impact')
RULE_LABEL = {
    'class': '先类别，后位置',
    'location': '按位置：从上到下、从左到右',
    'line': '沿主线：同一条线的排在一起',
    'impact': '先修一条动作消掉最多条目的',
}
# 主线折返 is a read-back hint only (图面可读性评分, #101): it sorts last inside its rule.
# The low-signal tail is for the main-line foldback hint (ticket 101, M2), which is not yet in the
# official report. B2's own `foldback` check is a budget item and sorts in its normal place.
LOW_SIGNAL = ()
PERSISTING = ('inline', 'after')
NOTES = ('inline', 'tail')
MERGE_PAD = 48.0      # two findings this close are treated as one problem
ROUTE_REACH = 170.0   # how much neighbouring wire the widest crop keeps
MAX_CROP = (560.0, 440.0)
MIN_CROP = (150.0, 110.0)
BAND = 230.0          # reading order: top-to-bottom in bands this tall, left-to-right inside

PAIR = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)\s*->\s*'
                  r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)')
POINT = re.compile(r'\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)')
INSTANCES = re.compile(r'[A-Z][A-Z0-9]*-\d{3}')
BUDGET_ID = re.compile(r'构图预算 (B\d)')
ANCHOR = re.compile(r'(?:paths|taps)\[\d+\]\[\d+->\d+\]|buses\.[A-Z]+')
# Rows whose own wording says what is wrong: name, action, fix path.
KIND_TEXT = {
    'missing_junction': ('接点缺失', 'add_junction', 'route'),
    'edge_anchor': ('跳线没有归属的管线', 'inspect', 'route'),
    'additional_or_wrong_connection': ('端点与输入不符', 'inspect', 'route'),
    'wrong_network_join': ('不同管网接到了一起', 'inspect', 'route'),
    'bridge_gap': ('跳线两端不连续', 'inspect', 'route'),
    'false_connection': ('假接点', 'inspect', 'route'),
    'unexpected_cycle': ('管网多出闭环', 'inspect', 'route'),
    'drawable_overflow': ('出了可绘制范围', 'move', 'local'),
}


# ---------- geometry ----------

def union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def grow(box, pad):
    return [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad]


def clip(box, window):
    return [max(box[0], window[0]), max(box[1], window[1]), min(box[2], window[2]), min(box[3], window[3])]


def overlaps(a, b, pad=0.0):
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


def points_box(points, pad=0.0):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return grow([min(xs), min(ys), max(xs), max(ys)], pad)


def frame(boxes, view, min_size=MIN_CROP, max_size=MAX_CROP):
    """Crop box for these boxes: not smaller than min, not larger than max, kept on the sheet."""
    box = union(boxes)
    if box is None:
        return None
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    w, h = max(box[2] - box[0], min_size[0]), max(box[3] - box[1], min_size[1])
    w, h = min(w, max_size[0]), min(h, max_size[1])
    x0 = min(max(cx - w / 2, view[0]), view[2] - w)
    y0 = min(max(cy - h / 2, view[1]), view[3] - h)
    return [x0, y0, x0 + w, y0 + h]


def turns_of(points):
    """Same count as the validator's B2: direction changes along one polyline."""
    dirs = []
    for a, b in zip(points, points[1:]):
        if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
            dirs.append('H' if b[0] >= a[0] else 'h')
        else:
            dirs.append('V' if b[1] >= a[1] else 'v')
    return sum(1 for i in range(1, len(dirs)) if dirs[i] != dirs[i - 1])


def detour_of(points):
    man = abs(points[-1][0] - points[0][0]) + abs(points[-1][1] - points[0][1])
    length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(points, points[1:]))
    return length / man if man else None


def zone(box, view):
    """Coarse place name on a 3×3 grid, for people who do not think in coordinates."""
    if not box or not view:
        return '全图'
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    col, row = '左中右'[min(2, int(3 * cx / view[2]))], '上中下'[min(2, int(3 * cy / view[3]))]
    return '中部' if (col, row) == ('中', '中') else col + row


def _segments(item):
    """Where the finding is on the sheet: its own lines and points when it has them, else its box."""
    segs = [(line[i], line[i + 1]) for line in item.get('lines') or [] for i in range(len(line) - 1)]
    if segs or item.get('points'):
        return segs + [(p, p) for p in item.get('points') or []]
    if item.get('box'):
        b = item['box']
        c = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]]
        return [(c[i], c[(i + 1) % 4]) for i in range(4)]
    return []


def _seg_gap(a, b):
    """Distance between two segments; 0 when they cross."""
    def point_seg(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2))
        return ((p[0] - a[0] - t * dx) ** 2 + (p[1] - a[1] - t * dy) ** 2) ** 0.5

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    a1, a2, b1, b2 = a[0], a[1], b[0], b[1]
    d1, d2, d3, d4 = cross(b1, b2, a1), cross(b1, b2, a2), cross(a1, a2, b1), cross(a1, a2, b2)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)):
        return 0.0
    return min(point_seg(a1, b1, b2), point_seg(a2, b1, b2), point_seg(b1, a1, a2), point_seg(b2, a1, a2))


def _is_point(p):
    return isinstance(p, (list, tuple)) and len(p) == 2 and all(isinstance(v, (int, float)) for v in p)


def _is_box(p):
    return isinstance(p, (list, tuple)) and len(p) == 4 and all(isinstance(v, (int, float)) for v in p)


def _matrices(report):
    return {inst: [float(v) for v in node['matrix']] for inst, node in (report or {}).get('geometry', {}).get('nodes', {}).items()
            if node.get('matrix') and node.get('footprint')}


# ---------- lookup tables ----------

def context(report, browser=None, reference=None, reference_browser=None):
    """Everything the steps need about one sheet, built once."""
    topo = report.get('topology', {})
    footprints = {inst: list(node['footprint']) for inst, node in report.get('geometry', {}).get('nodes', {}).items()
                  if node.get('footprint')}
    ports_of = {}
    for group in (topo.get('expected_edges', []), topo.get('actual_edges', [])):
        for edge in group:
            if edge.get('anchor'):
                known = ports_of.setdefault(edge['anchor'], [])
                known.extend(p for p in edge.get('endpoints', []) if p not in known)
    anchors_of_svg = {}
    for seg in topo.get('segments', []):
        if seg.get('svg_id'):
            anchors_of_svg.setdefault(seg['svg_id'], []).append(seg.get('anchor'))
    texts = report.get('text_geometry', {}).get('texts', [])
    return {
        'footprints': footprints, 'ports_of': ports_of, 'segments': topo.get('segments', []),
        'anchors_of_svg': anchors_of_svg, 'buses': topo.get('buses', []), 'bridges': topo.get('bridges', []) or [],
        'elements': {row.get('key'): row for row in (browser or {}).get('elements', [])},
        'pipes': report.get('geometry', {}).get('pipes', []), 'texts': texts,
        'text_by_element': {t.get('element'): t for t in texts},
        'budget': {item['id']: item for item in report.get('composition_budget', {}).get('items', [])},
        'coverage': {row['id']: row.get('status') for row in report.get('coverage', [])},
        'viewbox': None, 'reference': reference, 'reference_browser': reference_browser,
        'before': {inst: list(node['footprint']) for inst, node in (reference or {}).get('geometry', {}).get('nodes', {}).items()
                   if node.get('footprint')},
        'bus_boxes': _bus_boxes(browser), 'before_buses': _bus_boxes(reference_browser),
        'matrices': _matrices(report), 'before_matrices': _matrices(reference),
        'rerouted': _rerouted(browser, reference_browser),
    }


def _wire_boxes(browser):
    boxes = {}
    for row in (browser or {}).get('elements', []):
        anchor = (row.get('attrs') or {}).get('data-input-anchor') or ''
        if anchor.startswith(('paths[', 'taps[')) and _is_box(row.get('bbox')):
            boxes[anchor] = list(row['bbox'])
    return boxes


def _rerouted(browser, before):
    """Input edges whose drawn line differs between the two versions. A symptom can sit far from
    the edited object when the router sends another wire elsewhere; this is how that link shows."""
    now, was = _wire_boxes(browser), _wire_boxes(before)
    return {anchor: {'was': was[anchor], 'now': box} for anchor, box in now.items()
            if anchor in was and any(abs(x - y) > 0.5 for x, y in zip(was[anchor], box))}


def _bus_boxes(browser):
    boxes = {}
    for row in (browser or {}).get('elements', []):
        bus = (row.get('attrs') or {}).get('data-bus')
        if bus and _is_box(row.get('bbox')):
            boxes[bus] = union([boxes.get(bus), list(row['bbox'])])
    return boxes


def set_viewbox(ctx, viewbox):
    ctx['viewbox'] = [float(v) for v in viewbox]
    return ctx


def nodes_of_ports(ctx, ports):
    return sorted({p.split('.')[0] for p in ports if p.split('.')[0] in ctx['footprints']})


def nodes_of_anchors(ctx, anchors):
    nodes = []
    for anchor in anchors:
        nodes.extend(nodes_of_ports(ctx, ctx['ports_of'].get(anchor, [])))
    return sorted(set(nodes))


def owner_of_element(ctx, key):
    """Element ownership, attributed the same way sheet_diff does."""
    row = ctx['elements'].get(key)
    if not row:
        return None
    if row.get('instance'):
        return 'node:' + row['instance']
    attrs = row.get('attrs') or {}
    label = attrs.get('data-label-for') or next(
        (a.get('attrs', {}).get('data-label-for') for a in row.get('ancestors', [])
         if (a.get('attrs') or {}).get('data-label-for')), None)
    if label:
        return 'extern:' + label[1:] if label.startswith('@') else 'node:' + label
    if attrs.get('data-port'):
        return 'node:' + attrs['data-port'].split('.')[0]
    anchor = attrs.get('data-input-anchor', '')
    if anchor.startswith(('paths[', 'taps[', 'buses.')):
        return 'edge:' + anchor
    if attrs.get('data-edges'):
        return 'junction:' + attrs['data-edges']
    if attrs.get('data-extern'):
        return 'extern:' + attrs['data-extern']
    return None


def crossings_of(report):
    return [event for evidence in report.get('evidence', []) if evidence.get('id') == 'V14'
            for event in evidence.get('events', []) if event.get('kind') == 'crossing']


# ---------- locate: one item per finding ----------

def _item(check, index, kind, cls, box=None, points=(), nodes=(), edges=(), labels=(), subjects=(), **extra):
    """One located finding. ``subjects`` are what a fix would touch (``node:`` / ``edge:`` / ``label:``);
    ``nodes`` also lists the neighbours a crop should keep."""
    points = [list(p) for p in points if p]
    item = {
        'id': '%s:%04d' % (check['id'], index), 'check': check['id'], 'result': check['result'],
        'kind': kind, 'class': cls, 'detail': check.get('detail', ''), 'box': box,
        'points': points, 'nodes': sorted(set(nodes)), 'edges': sorted(e for e in set(edges) if e),
        'labels': sorted(set(labels)), 'subjects': sorted(set(subjects)), 'whole_sheet': box is None,
    }
    item.update(extra)
    return item


def _text_item(check, index, ctx):
    text = ctx['text_by_element'].get(check.get('element'), {})
    owner = (text.get('owner') or '').split(':')
    labels, nodes, edges, obstacle = [], [], [], check.get('obstacle_component')
    if len(owner) == 2 and owner[0] in ('label', 'symbol') and owner[1] in ctx['footprints']:
        nodes.append(owner[1])
        if owner[0] == 'label':
            labels.append(owner[1])
    named = str(check.get('obstacle', ''))
    if '__' in named and named.split('__')[0] in ctx['footprints']:
        obstacle = named.split('__')[0]
    if obstacle is None and isinstance(check.get('obstacle'), int):
        held = owner_of_element(ctx, check['obstacle'])
        if held and held.startswith('node:'):
            obstacle = held[5:]
        elif held and held.startswith('edge:'):
            edges.append(held[5:])
            nodes.extend(nodes_of_ports(ctx, ctx['ports_of'].get(held[5:], [])))
    other = ctx['text_by_element'].get(check.get('obstacle'), {})
    other_owner = (other.get('owner') or '').split(':')
    if other_owner[0] == 'label' and other_owner[-1] in ctx['footprints']:
        if other_owner[-1] not in labels:
            labels.append(other_owner[-1])
        nodes.append(other_owner[-1])
        obstacle = obstacle or other_owner[-1]
    if obstacle in ctx['footprints']:
        nodes.append(obstacle)
    if isinstance(obstacle, int) or (obstacle is None and isinstance(check.get('obstacle'), int)):
        obstacle = OBSTACLE.get(check.get('obstacle_kind'), '图元')
    for key in ('component', 'label_owner'):
        if check.get(key) in ctx['footprints']:
            nodes.append(check[key])
            if key == 'label_owner':
                labels.append(check[key])
    subjects = ['label:' + n for n in labels]
    if owner and owner[0] == 'symbol' and owner[1] in ctx['footprints'] and 'node:' + owner[1] not in subjects:
        subjects.append('node:' + owner[1])
    box = list(check['bbox']) if isinstance(check.get('bbox'), list) and len(check['bbox']) == 4 else None
    kind = check.get('kind') or 'text_clearance'
    return _item(check, index, kind, 'label', box, nodes=nodes, edges=edges, labels=labels, subjects=subjects,
                 text=check.get('text') or text.get('text', ''), obstacle=obstacle or named or None,
                 distance=check.get('distance'), required=check.get('required_clearance', 6.0))


def _overlap_item(check, index, ctx):
    pairs = [((float(m.group(1)), float(m.group(2))), (float(m.group(3)), float(m.group(4))))
             for m in PAIR.finditer(check.get('detail', ''))]
    points, edges = [], []
    for a, b in pairs:
        points += [a, b]
        horizontal = abs(a[1] - b[1]) < 0.6
        axis = 0 if horizontal else 1
        line = a[1] if horizontal else a[0]
        for seg in ctx['segments']:
            s, e = seg.get('start'), seg.get('end')
            if not s or not e or abs(s[1 - axis] - line) >= 0.6 or abs(e[1 - axis] - line) >= 0.6:
                continue
            lo, hi = min(a[axis], b[axis]), max(a[axis], b[axis])
            if min(max(s[axis], e[axis]), hi) - max(min(s[axis], e[axis]), lo) > 0.5:
                edges.append(seg.get('anchor'))
    edges = sorted(set(e for e in edges if e))
    length = re.search(r'重叠 (\d+) 单位', check.get('detail', ''))
    return _item(check, index, 'collinear_overlap', 'connection', points_box(points, 8) if points else None, points,
                 nodes_of_anchors(ctx, edges), edges, subjects=['edge:' + e for e in edges],
                 lines=[[list(a), list(b)] for a, b in pairs],
                 overlap=int(length.group(1)) if length else None,
                 segments=[[list(a), list(b)] for a, b in pairs])


def _crossing_item(check, index, ctx, report):
    """B1 carries no coordinates in its row; the V14 crossing events do."""
    detail = check.get('detail', '')
    events = [{'position': list(e['position']), 'anchors': sorted(e.get('input_anchors', [])),
               'networks': sorted(e.get('networks', []))} for e in crossings_of(report)]
    before = set()
    if ctx.get('reference'):
        before = {(round(e['position'][0]), round(e['position'][1])) for e in crossings_of(ctx['reference'])}
    fresh = [e for e in events if (round(e['position'][0]), round(e['position'][1])) not in before]
    shown = fresh or events
    for e in shown:
        # The event names both halves of the bridged path; the other line is only given as a network.
        own = {b['id'] for b in ctx['buses'] if set(e['anchors']) & set(b.get('input_anchors', []))}
        e['bus'] = next((b['anchor'] for b in ctx['buses'] if b['id'] in e['networks'] and b['id'] not in own), None)
        paths = [a for a in e['anchors'] if not a.startswith('buses.')]
        buses = [a for a in e['anchors'] if a.startswith('buses.')] + [e['bus'] for e in [e] if e['bus']]
        e['label'] = ' × '.join([paths[0].split('[')[0] if paths else '母线'] + (buses[:1] or e['networks'][:1]))
    anchors = sorted({a for e in shown for a in e['anchors']} | {e['bus'] for e in shown if e['bus']})
    held = '证据不完整不予放行' in detail
    count = re.search(r'交叉 (\d+) 处', detail)
    return _item(check, index, 'crossing', 'unchecked' if held else 'connection',
                 points_box([e['position'] for e in shown], 28) if shown else None,
                 [e['position'] for e in shown], nodes_of_anchors(ctx, anchors), anchors,
                 subjects=[] if held else ['edge:' + a for a in anchors],
                 crossings=events, new_crossings=fresh, total=int(count.group(1)) if count else len(events),
                 allowance=ctx['budget'].get('B1', {}).get('allowance'), reason='evidence' if held else 'count')


def _budget_item(check, index, ctx, report):
    """Budget rows carry no coordinates of their own; recover them from the panel and topology."""
    detail = check.get('detail', '')
    found = BUDGET_ID.search(detail)
    bid = found.group(1) if found else 'B?'
    panel = ctx['budget'].get(bid, {})
    if bid == 'B1':
        return _crossing_item(check, index, ctx, report)
    if bid == 'B7':
        return None      # summary row; every violation already has its own text row
    if bid in ('B2', 'B3'):
        if bid == 'B2':
            single = re.search(r'单条折返 (\d+) > 3', detail) or re.search(r'折返单条 (\d+) > 3', detail)
            rated = sorted(((turns_of(p['points']), p) for p in ctx['pipes']), key=lambda t: -t[0])
            worst = int(single.group(1)) if single else 0
            limit, kind = 3, 'foldback'
        else:
            ratio = re.search(r'绕行比 ([\d.]+) > 1.5', detail)
            worst = float(ratio.group(1)) if ratio else 0.0
            rated = sorted(((detour_of(p['points']) or 0.0, p) for p in ctx['pipes']), key=lambda t: -t[0])
            limit, kind = 1.5, 'detour'
        if worst:
            picked = sorted(rated, key=lambda t: abs(t[0] - worst))[:2]
            if bid == 'B3':
                picked = [t for t in picked if abs(t[0] - worst) < 0.01] or [t for t in rated if t[0] > limit][:2]
        else:
            picked = rated[:3]
        edges = sorted({a for _, p in picked for a in ctx['anchors_of_svg'].get(p['svg_id'], []) if a})
        return _item(check, index, kind, 'layout',
                     union([points_box(p['points'], 16) for _, p in picked]), [pt for _, p in picked for pt in p['points']],
                     nodes_of_anchors(ctx, edges), edges, subjects=['edge:' + e for e in edges],
                     lines=[[list(pt) for pt in p['points']] for _, p in picked],
                     worst=worst, limit=limit, exempt='豁免' in detail)
    if bid == 'B4':
        runs = panel.get('runs') or []
        run = panel.get('nearest_run') or (min(runs, key=lambda r: r.get('length', 1e9)) if runs else {})
        return _item(check, index, 'short_segment', 'layout', points_box([run['start'], run['end']], 26) if run else None,
                     [run.get('start'), run.get('end')], nodes_of_anchors(ctx, [run.get('anchor')]), [run.get('anchor')],
                     subjects=['edge:' + run['anchor']] if run.get('anchor') else [],
                     length=run.get('length'), limit=8.0, anchor=run.get('anchor'))
    if bid == 'B5':
        near = panel.get('nearest') or {}
        return _item(check, index, 'node_gap', 'layout', points_box(near.get('positions') or [], 24) or None,
                     near.get('positions') or [], near.get('components') or [],
                     subjects=['node:' + n for n in near.get('components') or []],
                     distance=near.get('distance'), limit=40.0, deficit=near.get('deficit'))
    if bid == 'B6':
        if '分组' in detail:
            near = panel.get('nearest_group') or {}
            return _item(check, index, 'group_padding', 'layout', points_box(near.get('positions') or [], 24) or None,
                         near.get('positions') or [], [near.get('component')],
                         subjects=['node:' + near['component']] if near.get('component') else [],
                         group=near.get('group'), distance=near.get('distance'), limit=14.0)
        near = panel.get('nearest_corridor') or {}
        return _item(check, index, 'corridor', 'layout', points_box(near.get('positions') or [], 24) or None,
                     near.get('positions') or [], [near.get('component')], [near.get('anchor')],
                     subjects=['edge:' + near['anchor']] if near.get('anchor') else [],
                     distance=near.get('distance'), limit=12.0, deficit=near.get('deficit'), anchor=near.get('anchor'))
    return _item(check, index, 'budget', 'layout')


def _located_item(check, index, ctx, cls):
    """Any row that carries its own position, anchors, ports or element."""
    detail = check.get('detail', '')
    points, lines, anchors = [], [], []
    for key in ('positions', 'endpoints', 'expected_endpoints', 'actual_endpoints'):
        points += [[float(p[0]), float(p[1])] for p in (check.get(key) or []) if _is_point(p)]
    if _is_point(check.get('position')):
        points.append([float(v) for v in check['position']])
    points += [[float(m.group(1)), float(m.group(2))] for m in POINT.finditer(detail)]
    box = next(([float(v) for v in check[key]] for key in ('bbox', 'box')
                if isinstance(check.get(key), (list, tuple)) and len(check[key]) == 4), None)
    ports = [p for key in ('endpoints', 'expected_endpoints', 'actual_endpoints', 'networks')
             for p in (check.get(key) or []) if isinstance(p, str) and p.split('.')[0] in ctx['footprints']]
    anchors += [a for a in (check.get('input_anchors') or []) if a]
    if check.get('anchor'):
        anchors.append(check['anchor'])
    own = nodes_of_ports(ctx, ports)
    if check.get('component') in ctx['footprints']:
        own.append(check['component'])
    held = owner_of_element(ctx, check.get('element')) if check.get('element') is not None else None
    if held and held.startswith('node:') and held[5:] in ctx['footprints']:
        own.append(held[5:])
    bridge = next((b for b in ctx['bridges'] if b.get('svg_id') and b['svg_id'] == check.get('svg_id')), None)
    if bridge:
        points.append([float(v) for v in bridge['position']])
        lines.append([[float(v) for v in p] for p in bridge.get('endpoints') or []])
        if bridge.get('anchor'):
            anchors.append(bridge['anchor'])
    for pipe in ctx['pipes']:
        if set(ctx['anchors_of_svg'].get(pipe['svg_id'], [])) & set(anchors):
            lines.append([list(pt) for pt in pipe['points']])
    if lines and not points:
        points = [pt for line in lines for pt in line]
    box = box or (points_box(points, 16) if points else None)
    nodes = sorted(set(own + nodes_of_anchors(ctx, anchors)))
    if box:
        reach = grow(box, 30)

        def gap(n):
            fp = ctx['footprints'][n]
            return max(box[0] - fp[2], fp[0] - box[2], 0) ** 2 + max(box[1] - fp[3], fp[1] - box[3], 0) ** 2
        nodes = sorted(set(nodes + sorted((n for n in ctx['footprints'] if overlaps(ctx['footprints'][n], reach)), key=gap)[:2]))
    subjects = ['node:' + n for n in sorted(set(own))] or ['edge:' + a for a in sorted(set(anchors))]
    return _item(check, index, check.get('kind') or 'other', cls, box, points, nodes, anchors, subjects=subjects,
                 lines=lines, ports=sorted(set(ports)), bridge=check.get('svg_id'),
                 cycles=check.get('actual_cycle_rank'),
                 overflow=max([v for v in (check.get('overflow') or {}).values()] or [0]))


def _disclosure_item(check, index, ctx):
    detail = check.get('detail', '')
    count = re.search(r'(\d+) 个', detail)
    return _item(check, index, 'dangling' if check['id'] == 'V5' else 'unannotated', 'disclosure', None, (),
                 sorted(set(INSTANCES.findall(detail)) & set(ctx['footprints'])),
                 ports=re.findall(r'[A-Z][A-Z0-9]*-\d{3}\.\w+', detail), count=int(count.group(1)) if count else None)


def _generic_item(check, index, ctx):
    """Everything with a position in the row or in its wording."""
    detail = check.get('detail', '')
    points = [[float(m.group(1)), float(m.group(2))] for m in POINT.finditer(detail)]
    box = list(check['bbox']) if isinstance(check.get('bbox'), list) and len(check['bbox']) == 4 else (
        points_box(points, 20) if points else None)
    nodes = [c for c in (check.get('component'), check.get('instance'), check.get('label_owner')) if c in ctx['footprints']]
    anchors = list(check.get('input_anchors') or []) + ([check['anchor']] if check.get('anchor') else [])
    anchors += ANCHOR.findall(detail)[:6]
    nodes += nodes_of_anchors(ctx, anchors)
    held = owner_of_element(ctx, check.get('element')) if check.get('element') is not None else None
    if held and held.startswith('node:'):
        nodes.append(held[5:])
    subjects = ['node:' + n for n in nodes[:1]] or ['edge:' + a for a in anchors if a]
    if box:
        reach = grow(box, 30)

        def gap(n):
            fp = ctx['footprints'][n]
            return max(box[0] - fp[2], fp[0] - box[2], 0) ** 2 + max(box[1] - fp[3], fp[1] - box[3], 0) ** 2
        near = sorted((n for n in ctx['footprints'] if overlaps(ctx['footprints'][n], reach)), key=gap)[:3]
        nodes = sorted(set(nodes + near))
    return _item(check, index, check.get('kind') or 'other', CHECK_CLASS.get(check['id'], 'layout'), box, points, nodes,
                 anchors, subjects=subjects)


def locate(report, ctx=None):
    """Every fail/warn row plus every unchecked evidence block, located on the sheet."""
    ctx = ctx or context(report)
    items = []
    for index, check in enumerate(report.get('checks', [])):
        if check.get('result') not in ('fail', 'warn'):
            continue
        kind = check.get('kind') or ''
        if check['id'] == 'V12' or kind.startswith('text') or (check['id'] == 'V19' and check.get('bbox')):
            item = _text_item(check, index, ctx)
        elif check['id'] == 'V13':
            item = _overlap_item(check, index, ctx)
        elif check['id'] == 'V19' and BUDGET_ID.search(check.get('detail', '')):
            item = _budget_item(check, index, ctx, report)
        elif check['id'] in ('V5', 'V9'):
            item = _disclosure_item(check, index, ctx)
        else:
            item = _located_item(check, index, ctx, CHECK_CLASS.get(check['id'], 'layout'))
        if item:
            items.append(item)
    for evidence in report.get('evidence', []):
        if ctx['coverage'].get(evidence.get('id')) == 'not_checked':
            items.append({
                'id': 'unchecked:%s' % evidence['id'], 'check': evidence['id'], 'result': 'not_checked', 'kind': 'unchecked',
                'class': 'unchecked', 'detail': '；'.join(str(u.get('detail') if isinstance(u, dict) else u)
                                                         for u in (evidence.get('unchecked') or []) if u)[:160],
                'box': None, 'points': [], 'nodes': [], 'edges': [], 'labels': [], 'subjects': [], 'whole_sheet': True,
            })
    return items


# ---------- signature: the same finding in another version? ----------

def signature(item):
    """Version-stable identity: DOM indexes and raw wording are renderer bookkeeping."""
    check, result, kind = item['check'], item['result'], item['kind']
    spot = tuple(round(v) for v in item['box']) if item.get('box') else None
    if kind.startswith('text'):
        other = item.get('obstacle') if item.get('obstacle') in item['nodes'] else None
        return (check, result, kind, item.get('text'), other, spot)
    if kind == 'collinear_overlap':
        return (check, result, tuple(sorted(tuple(sorted((tuple(round(v) for v in a), tuple(round(v) for v in b))))
                                            for a, b in item['segments'])))
    if kind == 'crossing':
        return (check, 'B1', result, tuple(sorted(tuple(round(v) for v in p) for p in item['points'])))
    if kind in ('foldback', 'detour'):
        return (check, kind, result, tuple(item['edges']))
    if kind in ('short_segment', 'corridor', 'group_padding'):
        return (check, kind, result, tuple(item['edges']), tuple(item['nodes']))
    if kind == 'node_gap':
        return (check, kind, result, tuple(item['nodes']))
    if item['class'] in ('disclosure', 'unchecked'):
        return (check, result)
    return (check, result, kind, tuple(tuple(round(v) for v in p) for p in item['points']), spot)


# ---------- problems ----------

def _wires(item):
    return {s for s in item['subjects'] if not s.startswith('node:')}


def _moved_with(item, before):
    """The same finding on the same wire or label at another place: it followed its object."""
    return bool(_wires(item)) and any(
        i['check'] == item['check'] and i['kind'] == item['kind'] and i['result'] == item['result']
        and _wires(item) == _wires(i) for i in before)


def _related(a, b):
    """Two findings are one problem when they share a wire or label, or sit at one place."""
    wires = _wires(a) & _wires(b)
    if wires:
        return True
    same_node = {s for s in a['subjects'] if s.startswith('node:')} & {s for s in b['subjects'] if s.startswith('node:')}
    both = bool(a['box'] and b['box'])
    near = both and overlaps(a['box'], b['box'], MERGE_PAD) and \
        min(_seg_gap(s, t) for s in _segments(a) for t in _segments(b)) <= MERGE_PAD
    return near or (bool(same_node) and (not both or overlaps(a['box'], b['box'], 2 * MERGE_PAD)))


def _merge(items):
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i, a in enumerate(items):
        for j in range(i):
            if _related(a, items[j]):
                parent[find(i)] = find(j)
    groups = {}
    for i, item in enumerate(items):
        groups.setdefault(find(i), []).append(item)
    return [groups[key] for key in sorted(groups)]


def _rank(item):
    return KIND_RANK.index(item['kind']) if item['kind'] in KIND_RANK else len(KIND_RANK)


def _primary(group):
    return sorted(group, key=lambda i: (SEVERITY[i['result']], i.get('state') != 'new', CLASS_ORDER.index(i['class']),
                                         _rank(i), i['id']))[0]


def _fix_lead(group):
    """The finding a fix should aim at: a layout cause beats the label symptoms it produces."""
    fresh = [i for i in group if i.get('state') == 'new'] or group
    texts = [i for i in fresh if i['class'] == 'label']
    causes = [i for i in fresh if i['kind'] == 'node_gap' and texts
              and set(i['nodes']) <= {n for t in texts for n in t['nodes']}]
    return causes[0] if causes else _primary(fresh)


def _suggest(item, group, nodes, edges):
    """(action, prose, fix path) for the finding the fix should aim at."""
    kind = item['kind']
    anchors = '、'.join(edges[:3]) + ('…' if len(edges) > 3 else '')
    names = '、'.join(nodes[:3]) + ('…' if len(nodes) > 3 else '')
    wire, part = anchors or '相关走线', names or '相关元件'
    if item['class'] == 'unchecked':
        if kind == 'crossing':
            return 'recheck', '交叉 %s 处在放行预算 %s 内，但 V4/V14 证据不完整：先修连接语义的其它项，这一条随上游恢复。' % (
                item.get('total'), item.get('allowance')), 'recheck'
        return 'recheck', '上游拓扑还有未决项；修好连接语义的失败后，%s 自动恢复校核。' % item['check'], 'recheck'
    symptoms = ''
    if len(group) > 1 and kind == 'node_gap':
        covered = sorted({i.get('text') for i in group if i['class'] == 'label' and i.get('text')})
        fails = sum(i['result'] == 'fail' for i in group if i['class'] == 'label')
        symptoms = '；预计 %s 的 %d 个标签（%s）压在上面（%d 条失败）会消除，修后由官方链复核' % (
            part, len(covered), '、'.join(covered[:2]), fails)
    if kind == 'crossing':
        spot = (item.get('new_crossings') or item.get('crossings') or [{}])[0].get('label', '走线')
        return 'reroute', '交叉 %s 处，放行 %s 处；新增的是 %s。让其中一条线在交叉点附近绕开，或把引起交叉的元件 / 母线挪回原位。' % (
            item.get('total'), item.get('allowance'), spot), 'local'
    if kind == 'collinear_overlap':
        if item['result'] == 'warn':
            return 'note', '共线重叠但汇于同一端口，按连通处理：只是提示，不必修。', 'disclose'
        return 'separate', '两条线共线重叠 %s 单位，读起来像接在一起（%s）：改折返点把两条线分开，或恢复 %s 的朝向。' % (
            item.get('overlap'), wire, part), 'route'
    if kind == 'text_overlap':
        return 'move_label', '标签「%s」压在 %s 上（净空 %s，要求 ≥ %s）：把标签挪到净空位，或挪开 %s。' % (
            item.get('text'), item.get('obstacle'), item.get('distance'), item.get('required'), part), 'agent'
    if kind.startswith('text'):
        return 'move_label', '标签「%s」离 %s 只有 %s（要求 ≥ %s）：把标签挪到净空位（距线 6–8 px，与所指示件对齐）。' % (
            item.get('text'), item.get('obstacle'), item.get('distance'), item.get('required')), 'agent'
    if kind == 'node_gap':
        return 'separate', '%s 贴在一起（净距 %s，要求 ≥ %s）：二者拉开至少 %s px%s。' % (
            ' 与 '.join(nodes[:2]), round(item.get('distance') or 0.0, 1), item.get('limit'),
            round(item.get('deficit') or 0.0), symptoms), 'local'
    if kind == 'short_segment':
        return 'straighten', '%s 上有一段 %s px 的短线（要求 ≥ %s）：去掉这个折点，或把两端拉开。' % (
            item.get('anchor'), item.get('length'), item.get('limit')), 'local'
    if kind == 'detour':
        return 'shorten', '%s 绕行比 %s（上限 %s）：减少这条线的绕行折点。' % (wire, item.get('worst'), item.get('limit')), 'local'
    if kind == 'foldback':
        return 'straighten', '%s 折返 %s 次（上限 %s）：减少这条线的折返。' % (wire, item.get('worst'), item.get('limit')), 'local'
    if kind in ('corridor', 'group_padding'):
        return 'separate', '%s 贴着 %s 走，净距 %s（要求 ≥ %s）：把走线或元件挪开。' % (
            wire, part, item.get('distance'), item.get('limit')), 'local'
    at = '（%s, %s）' % (round(item['points'][0][0]), round(item['points'][0][1])) if item.get('points') else ''
    name, action, path = KIND_TEXT.get(kind, (kind, 'inspect', 'route'))
    if kind == 'missing_junction':
        return action, '%s 的分支处%s没有实心接点：接点应随走线生成，先查这条线的折点为何没落在汇合处。' % (wire, at), path
    if kind == 'edge_anchor':
        return action, '跳线 %s 没有可归属的管线%s：多半是 %s 附近的管线断开，先恢复该处走线。' % (
            item.get('bridge'), at, part), path
    if kind == 'additional_or_wrong_connection':
        return action, '%s 的端点与输入不符%s：恢复 %s 的朝向或位置，让管线接到声明端口。' % (wire, at, part), path
    if kind == 'wrong_network_join':
        return action, '不同管网的线接到了一起（%s）：把 %s 挪回原位，让这些线分开。' % (wire, part), path
    if kind == 'bridge_gap':
        return action, '跳线 %s 与两端管线不连续%s：恢复 %s 的朝向或位置，让管线连续通过交叉点。' % (
            item.get('bridge'), at, part), path
    if kind == 'false_connection':
        return action, '两条不同管网的线在%s相接（%s）：把 %s 挪开，使两条线分开。' % (at, wire, part), path
    if kind == 'unexpected_cycle':
        return action, '管网多出 %s 个闭环（%s）：把 %s 挪回原位，消除多出来的连通。' % (item.get('cycles'), wire, part), path
    if kind == 'drawable_overflow':
        return action, '%s 出了可绘制范围 %s px：向图内挪回。' % (part or wire, round(item.get('overflow') or 0, 1)), path
    if item['class'] == 'occlusion':
        return 'move', '内容被盖住或出了可绘制范围（%s）：挪开遮挡物，或把出界的部分挪回图内。' % (part or wire), 'local'
    if item['class'] == 'connection':
        return 'inspect', '连接关系与输入不符（%s）：先查这些连接是否被画到了一起，再改走线或母线位置。' % (
            wire if wire != '相关走线' else item['detail'][:60]), 'route'
    if item['class'] == 'disclosure':
        return 'disclose', '输入事实：%s。布局改不了，不进修图单。' % item['detail'].split(':')[0], 'disclose'
    return 'inspect', item['detail'], 'agent'


def _title(group, nodes, edges):
    lead = _primary(group)
    kind, item = lead['kind'], lead
    first_wire = edges[0] if edges else '走线'
    one = None
    if kind == 'crossing':
        one = '新增交叉' if item.get('reason') == 'count' else '交叉未放行'
    elif kind == 'collinear_overlap':
        one = '两条线共线重叠' if item['result'] == 'fail' else '共线重叠（汇于同一端口）'
    elif kind == 'text_overlap':
        one = '标签「%s」压在 %s 上' % (item.get('text'), item.get('obstacle'))
    elif kind.startswith('text'):
        one = '标签「%s」离 %s 太近' % (item.get('text'), item.get('obstacle'))
    elif kind == 'node_gap':
        one = '%s 贴在一起' % ' 与 '.join(nodes[:2])
    elif kind == 'short_segment':
        one = '%s 有短线' % item.get('anchor')
    elif kind == 'detour':
        one = '%s 绕行' % first_wire
    elif kind == 'foldback':
        one = '%s 折返过多' % first_wire
    elif kind in ('corridor', 'group_padding'):
        one = '%s 贴着 %s 走' % (first_wire, nodes[0] if nodes else '元件')
    elif kind == 'dangling':
        one = '%s 个悬空端口' % item.get('count')
    elif kind == 'unannotated':
        one = '%s 个符号未标注' % item.get('count')
    elif kind == 'unchecked':
        one = '%s 未校核' % item['check']
    elif kind in KIND_TEXT:
        what = item.get('cycles') if kind == 'unexpected_cycle' else None
        one = '%s%s：%s' % (KIND_TEXT[kind][0], ' ×%s' % what if what else '', nodes[0] if nodes else (first_wire if first_wire != '走线' else item.get('bridge') or item['check']))
    elif nodes:
        one = '%s 处 %s' % (nodes[0], item['detail'].split(':')[0][:28])
    if len(group) == 1:
        return one or item['check']
    if all(i['kind'] == kind and i['check'] == item['check'] for i in group):
        return '%s ×%d' % (one, len(group))
    overlapped = sum(i['kind'] == 'collinear_overlap' and i['result'] == 'fail' for i in group)
    cycles = sorted((i.get('cycles') or 0) for i in group if i.get('cycles'))
    if overlapped > 1:
        return '%d 条共线重叠%s' % (overlapped, '，管网多出 %d 个闭环' % cycles[0] if cycles else '')
    if kind == 'crossing' and len(item.get('new_crossings') or item.get('crossings') or []) > 1:
        one = '%s ×%d' % (one, len(item.get('new_crossings') or item.get('crossings') or []))
    others = [i for i in group if i is not lead]
    rest = sorted({'%s ×%d' % (c, sum(x['check'] == c for x in others)) for c in {x['check'] for x in others}})
    return '%s（同处 %s）' % (one or item['check'], '、'.join(rest))


def _changed(ctx):
    """Objects whose footprint or bus line moved since the reference version."""
    out = {}
    for inst, was in ctx['before'].items():
        now = ctx['footprints'].get(inst)
        was_m, now_m = ctx['before_matrices'].get(inst), ctx['matrices'].get(inst)
        moved = now and any(abs(a - b) > 0.5 for a, b in zip(was, now))
        turned = was_m and now_m and any(abs(a - b) > 1e-6 for a, b in zip(was_m[:4], now_m[:4]))
        if moved or turned:
            angle = 0
            if turned:
                angle = round((_degrees(now_m) - _degrees(was_m)) % 360)
            out['node:' + inst] = {'id': inst, 'label': inst, 'kind': 'node', 'was': was, 'now': now or was, 'angle': angle,
                                   'delta': [round((now[0] + now[2] - was[0] - was[2]) / 2), round((now[1] + now[3] - was[1] - was[3]) / 2)]}
    for bus, was in ctx['before_buses'].items():
        now = ctx['bus_boxes'].get(bus)
        if not now:
            continue
        # A bus line only has one meaningful coordinate; its drawn length follows the taps.
        axis = 0 if was[0] == was[2] and now[0] == now[2] else 1
        shift = now[axis] - was[axis]
        if abs(shift) > 0.5:
            out['bus:' + bus] = {'id': bus.lstrip('@'), 'label': '%s 母线' % bus.lstrip('@'), 'kind': 'bus', 'was': was, 'now': now,
                                 'anchor': 'buses.' + bus.lstrip('@'), 'delta': [round(shift), 0]}
    return out


def _degrees(matrix):
    return math.degrees(math.atan2(matrix[1], matrix[0]))


def _suspects(box, named, wired_to, edges, ctx, changed):
    """What moved that could explain the problem, strongest evidence first: the object the leading
    finding names (2); anything wired into the problem, or any edited object when the problem sits on a
    wire that was drawn differently last time (1); something nearby (0)."""
    reach = grow(box, ROUTE_REACH) if box else None
    ends = {p for e in edges for p in nodes_of_ports(ctx, ctx['ports_of'].get(e, []))}
    # A wire redrawn when none of its own endpoints moved was sent elsewhere by the router: a side effect.
    moved = set(edges) & set(ctx.get('rerouted') or {})
    ends_moved = {p for e in moved for p in nodes_of_ports(ctx, ctx['ports_of'].get(e, []))}
    rewire = bool(moved) and not any(c['kind'] == 'node' and c['id'] in ends_moved for c in changed.values())
    found = []
    for key, c in changed.items():
        mine = c['id'] in named or c.get('anchor') in edges
        wired = c['kind'] == 'node' and (c['id'] in wired_to or c['id'] in ends)
        near = bool(reach) and (overlaps(c['now'], reach) or overlaps(c['was'], reach))
        level, why = (2, 'named') if mine else (1, 'wired') if wired else (1, 'rerouted') if rewire else (0, 'near') if near else (-1, '')
        if level >= 0:
            found.append(dict(c, level=level, why=why))
    return sorted(found, key=lambda c: -c['level'])


def _how(c):
    label, dx, dy, angle = c['label'], *c['delta'], c.get('angle', 0)
    if c['kind'] == 'bus':
        return '%s（%s %d px）' % (label, '左移' if dx < 0 else '右移' if dx > 0 else '上下' + '移', abs(dx) or abs(dy))
    if angle:
        return '%s（转了 %d°）' % (label, angle)
    if abs(dy) >= 1 and abs(dy) >= abs(dx):
        return '%s（%s %d px）' % (label, '上移' if dy < 0 else '下移', abs(dy))
    if abs(dx) >= 1:
        return '%s（%s %d px）' % (label, '左移' if dx < 0 else '右移', abs(dx))
    return '%s（尺寸变了）' % label


SHORT = {'collinear_overlap': '共线重叠', 'text_overlap': '标签压字', 'text_clearance': '标签净空不足', 'crossing': '交叉',
         'node_gap': '元件贴在一起', 'short_segment': '短线段', 'foldback': '折返过多', 'detour': '绕行',
         'corridor': '贴体走线', 'group_padding': '分组内边距不足', 'dangling': '悬空端口', 'unannotated': '符号未标注'}


def _symptoms(group):
    """What the problem looks like on the sheet, worst first: [(name, check, result, count)]."""
    tally = {}
    for i in group:
        name = KIND_TEXT.get(i['kind'], (SHORT.get(i['kind'], i['check']),))[0]
        key = (name, i['check'], i['result'])
        tally[key] = tally.get(key, 0) + 1
    return [{'name': k[0], 'check': k[1], 'result': k[2], 'count': n}
            for k, n in sorted(tally.items(), key=lambda kv: (SEVERITY[kv[0][2]], kv[0][0]))]


def _problem(group, ctx, seen, changed):
    lead = _primary(group)
    aim = _fix_lead(group)
    nodes = sorted({n for i in group for n in i['nodes']})
    edges = sorted({e for i in group for e in i['edges']})
    box = union([i['box'] for i in group if i['box']])
    action, prose, path = _suggest(aim, group, nodes, edges)
    states = [i.get('state', 'unknown') for i in group]
    state = ('unknown' if seen is None else 'persisting' if all(s == 'persisting' for s in states)
             else 'moved' if all(s in ('persisting', 'moved') for s in states) else 'new')
    suspects = _suspects(box, lead['nodes'], nodes, edges, ctx, changed) if state == 'new' else []
    # Where a problem goes is a property of its findings, not of when they were first seen: a row
    # still present in round two must keep its tier. Failures outrank hints; a node_gap cause outranks
    # the label symptoms it produced.
    fails = [i for i in group if i['result'] == 'fail']
    if aim['kind'] == 'node_gap' and any(i['class'] == 'label' for i in group):
        pool = [aim] + [i for i in fails if i['class'] != 'label']
    else:
        pool = fails or group
    weight = {'agent': 4, 'route': 3, 'local': 2, 'recheck': 1, 'disclose': 0}
    path = max((_suggest(i, [i], sorted(i['nodes']), sorted(i['edges']))[2] for i in pool), key=weight.get)
    lead_in = ''
    strong = [c for c in suspects if c['level'] == 2]
    rewire = [c for c in suspects if c['why'] == 'rerouted']
    if strong:
        lead_in = '上一版之后动过：%s。先恢复它，或按下面的办法处理。' % '、'.join(_how(c) for c in strong)
    elif rewire:
        lead_in = '上一版之后动过 %s，这里的 %s 跟着改了走向，多半是它引起的。先恢复它，或按下面的办法处理。' % (
            '、'.join(_how(c) for c in rewire), '、'.join(sorted(set(edges) & set(ctx.get('rerouted') or {}))[:2]))
    elif suspects:
        lead_in = '上一版之后相连或附近动过：%s，可能是起因。' % '、'.join(_how(c) for c in suspects[:3])
    symptoms = _symptoms(group)
    return {
        'class': lead['class'], 'severity': lead['result'], 'state': state,
        'title': _title(group, nodes, edges), 'lead': lead['id'], 'kind': lead['kind'],
        'zone': zone(box, ctx.get('viewbox')),
        'items': [i['id'] for i in group], 'rows': [i['detail'] for i in group],
        'counts': {c: sum(i['check'] == c for i in group) for c in sorted({i['check'] for i in group})},
        'box': box, 'center': [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2] if box else None,
        'nodes': nodes, 'edges': edges, 'labels': sorted({n for i in group for n in i['labels']}),
        'buses': sorted({e.split('.', 1)[1] for e in edges if e.startswith('buses.')}),
        'suspects': [{'id': c['id'], 'label': c['label'], 'kind': c['kind'], 'how': _how(c), 'level': c['level'], 'why': c['why']}
                     for c in suspects],
        'symptoms': symptoms,
        'suggestion': {'action': action, 'text': prose, 'lead_in': lead_in, 'aim': aim['id'], 'fix_path': path,
                       'fix_path_label': FIX_PATH[path], 'structured': path in ('local', 'route') and bool(nodes or edges)},
        # The fix aims at the cause when one is known, else at the objects the findings name.
        'scope': {'nodes': sorted(c['id'] for c in suspects if c['kind'] == 'node' and c['level'] >= 1) or nodes,
                  'edges': sorted(set(edges) | {c['anchor'] for c in suspects if c['level'] == 2 and c['kind'] == 'bus'}),
                  'buses': sorted(c['id'] for c in suspects if c['level'] == 2 and c['kind'] == 'bus'),
                  'include_adjacent_edges': True, 'note': ''},
    }


EMPTY_CROPS = {'finding': None, 'objects': None, 'route': None, 'footprints': {}, 'labels': [], 'wires': []}


def crops(problem, ctx, reach_px=ROUTE_REACH):
    """Three crops of increasing context: the finding, the finding with its owner, with the route."""
    view, box = ctx.get('viewbox'), problem['box']
    if box is None or not view:
        return dict(EMPTY_CROPS)
    core = grow(box, 24)
    reach = grow(core, reach_px)
    own = {n: fp for n, fp in ctx['footprints'].items() if n in problem['nodes'] and overlaps(fp, reach)}
    labels = [t['bbox'] for t in ctx['texts']
              if (t.get('owner') or '').split(':')[-1] in problem['labels'] and overlaps(t['bbox'], reach)]
    objects = frame([core] + list(own.values()) + labels, view)
    window = grow(objects, reach_px)
    wires = [clip(points_box(p['points']), window) for p in ctx['pipes'] if overlaps(points_box(p['points']), window)]
    route = frame([objects] + wires, view, min_size=(0, 0)) if wires else None
    if route and (route[2] - route[0] <= objects[2] - objects[0] + 4 or route[2] - route[0] >= MAX_CROP[0] - 1):
        route = None
    return {
        'finding': frame([core], view), 'objects': objects, 'route': route,
        'footprints': own, 'labels': labels,
        'wires': [[list(pt) for pt in p['points']] for p in ctx['pipes']
                  if route and overlaps(points_box(p['points']), route)],
    }


def build(items, ctx):
    """Cluster located items into problems, then classify, date, suggest and scope them."""
    fixable = [i for i in items if i['class'] not in ('disclosure', 'unchecked')]
    rest = [i for i in items if i['class'] in ('disclosure', 'unchecked')]
    seen, resolved, changed = None, [], {}
    if ctx.get('reference'):
        before_items = locate(ctx['reference'], context(ctx['reference'], ctx.get('reference_browser')))
        seen = {signature(i) for i in before_items}
        now = {signature(i) for i in items}
        for group in _merge([i for i in before_items if i['class'] not in ('disclosure', 'unchecked')]):
            if any(signature(i) in now or _moved_with(i, items) for i in group):
                continue
            if any(_related(old, new) for old in group for new in fixable):
                continue          # got worse or moved: not resolved
            old = _problem(group, ctx, None, {})
            resolved.append({'title': old['title'], 'class': old['class'], 'severity': old['severity'], 'rows': len(group)})
        changed = _changed(ctx)
    for item in items:
        item['state'] = ('unknown' if seen is None else 'persisting' if signature(item) in seen
                         else 'moved' if _moved_with(item, before_items) else 'new')
    groups = _merge(fixable) + [[i] for i in rest]
    problems = [_problem(group, ctx, seen, changed) for group in groups]
    for index, problem in enumerate(order(problems, 'class')):
        problem['id'] = 'p%d' % (index + 1)
        problem['context'] = crops(problem, ctx)
    by_item = {i['id']: problem for group, problem in zip(groups, problems) for i in group}
    for item in items:
        item['problem'] = by_item[item['id']]['id']
        item['context'] = crops(_problem([item], ctx, None, {}), ctx) if item['class'] not in ('disclosure', 'unchecked') \
            else dict(EMPTY_CROPS)
    return {'problems': problems, 'resolved': resolved, 'summary': summarize(problems, resolved, items),
            'changed': changed, 'items': items}


def _line(problem):
    """The wire a problem reads along: the first declared path it touches, else its bus."""
    keys = [(0, int(m.group(2))) if (m := re.match(r'(paths|taps)\[(\d+)\]', e)) else (1, e) for e in problem['edges']]
    return min(keys) if keys else (2, '')


def order(problems, rule='class', persisting='inline', notes='inline'):
    """Fix queue first: worst finding, then the rule; disclosures and not-checked rows last.

    ``persisting='after'`` puts what is new in a level before what was already there;
    ``notes='tail'`` drops hint-only warnings (nothing to fix) next to the disclosures.
    """
    def key(problem):
        cx, cy = problem['center'] or (0, 0)
        place = (int(cy // BAND), cx)
        cls = CLASS_ORDER.index(problem['class'])
        if problem['class'] in ('disclosure', 'unchecked'):
            return (9, cls, 0, 0.0, 0)
        tail = 8 if notes == 'tail' and problem['severity'] == 'warn' and problem['suggestion']['fix_path'] == 'disclose' else 0
        moved = problem['state'] in ('persisting', 'moved')   # 'moved' is a persisting subcase
        head = (SEVERITY[problem['severity']], 1 if persisting == 'after' and moved else 0)
        low = problem['kind'] in LOW_SIGNAL
        if rule == 'location':
            return (tail,) + head + place + (low,)
        if rule == 'impact':
            return (tail,) + head + (-len(problem['items']), low) + place
        if rule == 'line':
            return (tail,) + head + _line(problem) + (low,) + place
        return (tail,) + head + (cls, low) + place
    return sorted(problems, key=key)


def flat(items):
    """Variant B: no merging; worst rows first, report order inside a level."""
    return sorted((i for i in items if i['class'] not in ('disclosure', 'unchecked')),
                  key=lambda i: (SEVERITY[i['result']], i['id']))


def repair_order(problems, rule='class', round_number=1, max_rounds=2, diff_ready=True, persisting='inline', notes='inline'):
    """What the next fix round consumes: ordered fixable problems plus one diff scope.

    ``diff_scope`` follows the keys ``sheet_diff`` accepts (nodes, edges, include_adjacent_edges,
    note); bus anchors ride inside ``edges`` because that is where sheet_diff knows them.

    A row only becomes a work item when its finding has a fix. Hints that say "no change needed",
    rows that recover with their upstream, input facts and not-checked rows are reported but never
    enter the repair queue, and they do not inflate the diff scope.
    """
    ranked = order(problems, rule, persisting, notes)
    def no_fix(p):
        return (p['class'] in ('disclosure', 'unchecked')
                or p['suggestion']['fix_path'] in ('disclose', 'recheck'))
    queue = [p for p in ranked if not no_fix(p)]
    held = [p for p in ranked if no_fix(p)]
    return {
        'round': round_number, 'max_rounds': max_rounds, 'rule': rule, 'diff_ready': diff_ready,
        'problems': [{'order': i + 1, 'id': p['id'], 'class': p['class'], 'severity': p['severity'], 'state': p['state'],
                      'title': p['title'], 'findings': p['items'], 'context': {k: p['context'][k] for k in ('finding', 'objects', 'route')},
                      'suggestion': p['suggestion'], 'suspects': p['suspects'],
                      # Only structured items carry a machine-executable scope. Agent rows take the prose.
                      'scope': dict(p['scope'], note='第 %d 轮 · 第 %d 项：%s（%s）' % (
                          round_number, i + 1, p['title'], CLASS_LABEL[p['class']])) if p['suggestion']['structured'] else None}
                     for i, p in enumerate(queue)],
        'not_in_queue': [{'id': p['id'], 'class': p['class'], 'title': p['title'],
                          'path': p['suggestion']['fix_path'],
                          'reason': ('输入事实，布局改不了' if p['class'] == 'disclosure'
                                     else '上游有未决项，修好后自动恢复校核' if p['class'] == 'unchecked'
                                     else FIX_PATH[p['suggestion']['fix_path']])}
                         for p in held],
        'diff_scope': {'nodes': sorted({n for p in queue for n in (p['scope'] or {}).get('nodes', [])}),
                       'edges': sorted({e for p in queue for e in (p['scope'] or {}).get('edges', [])} |
                                       {'buses.' + b for p in queue for b in (p['scope'] or {}).get('buses', [])}),
                       'include_adjacent_edges': any((p['scope'] or {}).get('include_adjacent_edges') for p in queue),
                       'note': '第 %d 轮：修复回读问题 %s；核对相邻管线的关联变化，保持端口连通关系不变。' % (
                           round_number, '、'.join(p['id'] for p in queue) or '无')},
    }


def summarize(problems, resolved, items):
    fixable = [p for p in problems if p['class'] not in ('disclosure', 'unchecked')]
    counted = [i for i in items if i['class'] not in ('disclosure', 'unchecked')]
    return {
        'problems': len(fixable), 'findings': len(counted),
        'fail': sum(i['result'] == 'fail' for i in counted), 'warn': sum(i['result'] == 'warn' for i in counted),
        'fail_problems': sum(p['severity'] == 'fail' for p in fixable),
        'new': sum(p['state'] == 'new' for p in fixable), 'persisting': sum(p['state'] == 'persisting' for p in fixable),
        'unknown': sum(p['state'] == 'unknown' for p in fixable), 'resolved': len(resolved),
        'disclosures': sum(p['class'] == 'disclosure' for p in problems),
        'unchecked': sum(p['class'] == 'unchecked' for p in problems),
        'by_class': {cls: sum(p['class'] == cls for p in fixable) for cls in CLASS_ORDER[:4]},
    }


def triage(report, browser=None, reference=None, reference_browser=None, viewbox=(0, 0, 1710, 1390)):
    """Convenience entry point for callers that have the files in hand."""
    ctx = set_viewbox(context(report, browser, reference, reference_browser), viewbox)
    return build(locate(report, ctx), ctx)
