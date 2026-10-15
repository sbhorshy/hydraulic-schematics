"""Independent endpoint checks using final SVG geometry and input declarations."""
import math

# Renderer rounds each coordinate to 0.1; Euclidean error is at most sqrt(2)*0.05.
ENDPOINT_TOLERANCE = 0.1


def declared_terminals(intent, catalog):
    types = {c['component_type']: c for c in catalog['components']}
    terminals = []

    def add(token, want, anchor):
        inst, _, pid = token.partition('.')
        if inst not in intent['parts']:
            return
        if not pid:
            pid = types[intent['parts'][inst]]['main_path'][want]
        terminals.append({'component': inst, 'port': pid, 'anchor': anchor})

    for pi, path in enumerate(intent.get('paths') or []):
        for k, (a, b) in enumerate(zip(path, path[1:])):
            anchor = 'paths[%d][%d->%d]' % (pi, k, k+1)
            add(a, 'out', anchor)
            add(b, 'in', anchor)
    for i, tap in enumerate(intent.get('taps') or []):
        add(tap['sensor'], None, 'taps[%d]' % i)
        add(tap['at'], None, 'taps[%d]' % i)
    return terminals


def check_endpoints(geometry, intent, catalog):
    findings, evidence = [], []
    ends = [(pipe, endpoint, neighbour) for pipe in geometry['pipes']
            for endpoint, neighbour in ((pipe['points'][0], pipe['points'][1]),
                                        (pipe['points'][-1], pipe['points'][-2]))]
    for issue in geometry['issues']:
        findings.append(dict(issue, id='V3', result='fail', kind='unsupported_geometry'))
    for terminal in declared_terminals(intent, catalog):
        port = geometry['nodes'].get(terminal['component'], {}).get('ports', {}).get(terminal['port'])
        if port is None:
            findings.append(dict(terminal, id='V3', result='fail', kind='missing_port',
                                 position=None, detail='声明端口无可校核几何'))
            continue
        pos = port['position']
        candidates = sorted(ends, key=lambda e: math.dist(e[1], pos))
        nearest = candidates[0] if candidates else None
        distance = math.dist(nearest[1], pos) if nearest else None
        item = dict(terminal, position=pos, direction=port['direction'], distance=distance)
        evidence.append(item)
        if nearest is None or distance > ENDPOINT_TOLERANCE:
            findings.append(dict(item, id='V3', result='fail', kind='endpoint_gap',
                                 actual_position=nearest[1] if nearest else None,
                                 detail='接管未抵达声明端口 %s.%s，端点距离 %s'
                                 % (terminal['component'], terminal['port'], distance)))
            continue
        for pipe, endpoint, neighbour in candidates:
            if math.dist(endpoint, pos) > ENDPOINT_TOLERANCE:
                break
            dx, dy = neighbour[0]-endpoint[0], neighbour[1]-endpoint[1]
            ax, ay = port['direction']
            forward = dx*ax+dy*ay
            sideways = abs(dx*ay-dy*ax)
            if forward <= ENDPOINT_TOLERANCE or sideways > ENDPOINT_TOLERANCE:
                findings.append(dict(item, id='V3', result='fail', kind='anchor_direction',
                                     actual_position=endpoint, neighbour=neighbour,
                                     pipe_index=pipe['index'],
                                     detail='接管方向违背旋转后端口锚向 %s.%s (%s): %s -> %s'
                                     % (terminal['component'], terminal['port'],
                                        port['anchor_direction'], endpoint, neighbour)))
    for pipe in geometry['pipes']:
        pts = pipe['points']
        context = next((t for t in evidence if any(math.dist(t['position'], e) <= ENDPOINT_TOLERANCE
                        for e in (pts[0], pts[-1]))), {})
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            ux, uy, vx, vy = b[0]-a[0], b[1]-a[1], c[0]-b[0], c[1]-b[1]
            if abs(ux*vy-uy*vx) < 1e-6 and ux*vx+uy*vy < -1e-6:
                findings.append(dict(context, id='V3', result='fail', kind='foldback',
                                     pipe_index=pipe['index'], position=b, segment=(a, b, c),
                                     detail='管线折返形成越界线头: %s %s -> %s -> %s'
                                     % (pipe['class'], a, b, c)))
    return findings, {'id': 'V3', 'coordinate_system': geometry['coordinate_system'],
                      'coverage_status': ('not_checked' if geometry['issues'] else
                                          'pass' if evidence else 'not_applicable'),
                      'detail': ('Declared terminals checked against final SVG pipe endpoints'
                                 if evidence else 'No declared component connections'),
                      'endpoint_tolerance': ENDPOINT_TOLERANCE,
                      'tolerance_reason': 'SVG 0.1 unit coordinate rounding only',
                      'terminals': evidence}


def segment_body_length(a, b, box):
    """Clip the complete straight segment to a footprint's open interior."""
    t0, t1 = 0., 1.
    for axis in (0, 1):
        lo, hi = box[axis]+ENDPOINT_TOLERANCE, box[axis+2]-ENDPOINT_TOLERANCE
        delta = b[axis]-a[axis]
        if abs(delta) < 1e-9:
            if not lo < a[axis] < hi:
                return 0.
        else:
            enter, leave = sorted(((lo-a[axis])/delta, (hi-a[axis])/delta))
            t0, t1 = max(t0, enter), min(t1, leave)
    return max(0., t1-t0)*math.dist(a, b)


def check_bodies(geometry, terminal_evidence):
    findings = []
    for pipe in geometry['pipes']:
        pts = pipe['points']
        connected = [t for t in terminal_evidence if any(
            math.dist(t['position'], end) <= ENDPOINT_TOLERANCE for end in (pts[0], pts[-1]))]
        for index, (a, b) in enumerate(zip(pts, pts[1:])):
            for inst, node in geometry['nodes'].items():
                hit = segment_body_length(a, b, node['footprint'])
                if hit <= ENDPOINT_TOLERANCE:
                    continue
                # Only an actual terminal segment may leave its own port's
                # footprint, along its outward anchor. Intermediate points,
                # another body's boundary, and wrong-side incidence never exempt.
                allowed = False
                for end, neighbour in ((a, b), (b, a)):
                    if not ((index == 0 and end == pts[0]) or
                            (index == len(pts)-2 and end == pts[-1])):
                        continue
                    for terminal in connected:
                        if terminal['component'] != inst or math.dist(end, terminal['position']) > ENDPOINT_TOLERANCE:
                            continue
                        dx, dy = neighbour[0]-end[0], neighbour[1]-end[1]
                        ax, ay = terminal['direction']
                        if dx*ax+dy*ay > ENDPOINT_TOLERANCE and abs(dx*ay-dy*ax) <= ENDPOINT_TOLERANCE:
                            allowed = True
                if allowed:
                    continue
                context = connected[0] if connected else {}
                findings.append({**context, 'id': 'V2', 'result': 'fail', 'kind': 'body_crossing',
                                 'component': context.get('component'), 'port': context.get('port'),
                                 'anchor': context.get('anchor'), 'obstacle': inst,
                                 'pipe_index': pipe['index'], 'segment': (a, b),
                                 'position': ((a[0]+b[0])/2, (a[1]+b[1])/2),
                                 'penetration': hit,
                                 'detail': '管线穿越 %s 本体 %.2f 单位,段 %s->%s' % (inst, hit, a, b)})
    return findings
