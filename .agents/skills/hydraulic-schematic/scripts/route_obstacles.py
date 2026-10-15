"""Hard routing envelopes in root SVG units; no scoring can waive a hit.

Node envelopes conservatively use the uniformly scaled, rotated symbol viewBox
footprint plus stroke allowance, not a claim of measured body ink. Label boxes
come from the renderer's text reservation; final browser V12 remains mandatory.
"""

EPS = 1e-8
BODY_CLEARANCE = 12.0
TEXT_CLEARANCE = 6.0
DIRECTIONS = {'left': (-1, 0), 'right': (1, 0), 'up': (0, -1), 'down': (0, 1)}


class RoutingError(ValueError):
    def __init__(self, anchor, findings, reason='no legal orthogonal candidate'):
        self.report = dict(schema='routing-error/1', status='blocked', anchor=anchor,
                           reason=reason, obstacles=findings)
        names = ', '.join(dict.fromkeys(str(f.get('obstacle')) for f in findings))
        super().__init__('Routing blocked %s: %s; obstacles=%s' % (anchor, reason, names))


def half_width(sheet, line_type):
    return float(sheet.L.get('style', {}).get('base_line_width_T', 1.2)) * (1.5 if line_type == 'pressure' else .5)


def envelopes(sheet, line_type):
    half = half_width(sheet, line_type)
    # Source body stroke is 1.5T; viewport-boundary ink can extend beyond it.
    body_pad = BODY_CLEARANCE + half + .75 * float(sheet.L.get('style', {}).get('base_line_width_T', 1.2))
    result = []
    for name, n in sheet.L.get('nodes', {}).items():
        w, h = n.get('_W', n['w']), n.get('_H', n['h'])
        if int(n.get('_rot', n.get('rot', 0))) % 180:
            w, h = h, w
        raw = (n['x'], n['y'], n['x'] + w, n['y'] + h)
        result.append(dict(obstacle=name, kind='body', raw=raw, clearance=BODY_CLEARANCE,
                           bounds=expand(raw, body_pad)))
    ids = getattr(sheet, 'textbox_ids', [])
    for index, box in enumerate(sheet.textboxes):
        result.append(dict(obstacle=ids[index] if index < len(ids) else 'label[%d]' % index,
                           kind='label', raw=box, clearance=TEXT_CLEARANCE,
                           bounds=expand(box, TEXT_CLEARANCE + half)))
    return result


def expand(box, pad):
    return (box[0]-pad, box[1]-pad, box[2]+pad, box[3]+pad)


def segment_hit(a, b, box):
    """Positive-length intersection with the OPEN envelope; tangent is legal."""
    if abs(a[0]-b[0]) < EPS:
        return box[0]+EPS < a[0] < box[2]-EPS and max(min(a[1], b[1]), box[1]) < min(max(a[1], b[1]), box[3])-EPS
    if abs(a[1]-b[1]) < EPS:
        return box[1]+EPS < a[1] < box[3]-EPS and max(min(a[0], b[0]), box[0]) < min(max(a[0], b[0]), box[2])-EPS
    return True


def terminals_for(sheet, start, end=None):
    """Only placed, exact endpoint ports can exempt their own outward corridor."""
    result = []
    for position, endpoint in (('start', start), ('end', end)):
        if endpoint is None:
            continue
        matches = [(inst, pid) for (inst, pid), p in getattr(sheet, 'abs', {}).items()
                   if all(abs(p[i]-endpoint[i]) < EPS for i in (0, 1)) and p[2] == endpoint[2]]
        if len(matches) == 1:
            inst, pid = matches[0]
            result.append(dict(position=position, node=inst, port=pid, point=endpoint[:2], direction=endpoint[2]))
    return result


def corridor_segments(points, terminal):
    reverse = terminal['position'] == 'end'
    pts = list(reversed(points)) if reverse else points
    if not pts or any(abs(pts[0][i]-terminal['point'][i]) > EPS for i in (0, 1)):
        return set()
    dx, dy = DIRECTIONS[terminal['direction']]
    found = set()
    for index, (a, b) in enumerate(zip(pts, pts[1:])):
        vx, vy = b[0]-a[0], b[1]-a[1]
        if abs(vx*dy-vy*dx) > EPS or vx*dx+vy*dy < -EPS:
            break
        found.add(len(points)-2-index if reverse else index)
    return found


def collisions(sheet, points, line_type='pressure', terminals=()):
    # Test the actual one-decimal geometry that polyline() emits.
    points = [(round(x,1),round(y,1)) for x,y in points]
    terminals = [dict(t,point=tuple(round(v,1) for v in t['point'])) for t in terminals]
    exceptions = {}
    for terminal in terminals:
        exceptions.setdefault(terminal['node'], set()).update(corridor_segments(points, terminal))
    hits = []
    for obstacle in envelopes(sheet, line_type):
        for index, (a, b) in enumerate(zip(points, points[1:])):
            if obstacle['kind'] == 'body' and index in exceptions.get(obstacle['obstacle'], ()):
                continue
            if segment_hit(a, b, obstacle['bounds']):
                hits.append(dict(obstacle=obstacle['obstacle'], kind=obstacle['kind'],
                                 bounds=obstacle['bounds'], clearance=obstacle['clearance'],
                                 segment=[a, b], position=[(a[0]+b[0])/2, (a[1]+b[1])/2]))
    return hits


def assert_legal(sheet, points, anchor, line_type='pressure', terminals=()):
    hits = collisions(sheet, points, line_type, terminals)
    if hits:
        raise RoutingError(anchor, hits)


def escape_point(sheet, endpoint, line_type='pressure', length=20.0):
    x, y, direction = endpoint
    dx, dy = DIRECTIONS[direction]
    terms = terminals_for(sheet, endpoint)
    if terms:
        own = next((o for o in envelopes(sheet, line_type) if o['kind']=='body' and o['obstacle']==terms[0]['node']), None)
        if own:
            box = own['bounds']
            distance = {'left': x-box[0], 'right': box[2]-x, 'up': y-box[1], 'down': box[3]-y}[direction]
            length = max(length, distance+.2)
    return (x+dx*length, y+dy*length)


def edge_lanes(sheet, line_type='pressure'):
    """Finite obstacle-edge fallback; 0.2 protects one-decimal SVG rounding."""
    boxes = [o['bounds'] for o in envelopes(sheet, line_type)]
    xs = sorted(set(round(x, 4) for b in boxes for x in (b[0]-.2, b[2]+.2)))
    ys = sorted(set(round(y, 4) for b in boxes for y in (b[1]-.2, b[3]+.2)))
    d = sheet.L.get('drawable')
    if d:
        h = half_width(sheet, line_type)
        xs = [x for x in xs if d['x']+h <= x <= d['x']+d['width']-h]
        ys = [y for y in ys if d['y']+h <= y <= d['y']+d['height']-h]
    return xs, ys


def failure(anchor, findings):
    unique = {}
    for hit in findings:
        unique.setdefault((hit['kind'], hit['obstacle']), hit)
    return RoutingError(anchor, list(unique.values()))
