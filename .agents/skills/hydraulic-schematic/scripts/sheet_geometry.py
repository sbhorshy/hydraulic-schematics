"""Read final SVG geometry in root SVG user units.

Public boundary: load_geometry(root, layout, resolve_symbol). Nodes expose the
actual instance matrix, transformed symbol viewBox footprint, and asset ports;
pipes expose transformed points. No routing or layout coordinate reconstruction.
Unsupported geometry is returned in issues, never silently certified.
"""
import math
import re
import xml.etree.ElementTree as ET

IDENTITY = (1., 0., 0., 1., 0., 0.)
DIRECTIONS = {'left': (-1., 0.), 'right': (1., 0.),
              'up': (0., -1.), 'down': (0., 1.)}
NUMBER = r'[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?'
# Pose comparisons run on source-viewBox control points transformed into root
# SVG user units, never on raw matrix coefficients: a coefficient tuple mixes
# the dimensionless scale with translations, so an absolute per-coefficient
# epsilon accepts a doubled scale whenever k is small (0.001 vs 0.002 both sit
# inside 0.01). Each coordinate's budget = POSE_TOLERANCE (absolute floor for
# %g rounding at ordinary coordinate magnitudes) plus POSE_RELATIVE_TOLERANCE
# times the transformed point's own magnitude, capped at POSE_TOLERANCE_CAP.
# The budget deliberately never scales with the source-viewBox terms that
# produce a coordinate (|a*x| + |e| can individually reach 1e9 while the point
# lands at ordinary sheet coordinates, because the terms cancel): a huge
# cancellable viewBox origin would then buy a huge tolerance and swallow a
# whole-symbol misplacement (audit counterexample: viewBox x=1e9 with a 100px
# translation error passed). %g rounding acts on the renderer's final-chain
# parameters, whose effect shows up at the transformed point's own size; a
# declaration so large that %g cannot express it inside the cap is rejected
# as unrepresentable precision rather than accepted misaligned.
POSE_TOLERANCE = 0.01
POSE_RELATIVE_TOLERANCE = 1e-4
POSE_TOLERANCE_CAP = 1.0


def multiply(a, b):
    """SVG affine composition a * b, in (a,b,c,d,e,f) storage order."""
    return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
            a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
            a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])


def point(matrix, xy):
    a, b, c, d, e, f = matrix
    x, y = xy
    return (a*x+c*y+e, b*x+d*y+f)


def transform(value):
    result = IDENTITY
    rest = value or ''
    while rest.strip(' ,\t\r\n'):
        match = re.match(r'\s*,?\s*([A-Za-z]+)\s*\(([^)]*)\)', rest)
        if not match:
            raise ValueError('unsupported transform: ' + value)
        name, args = match.groups()
        numbers = [float(v) for v in re.findall(NUMBER, args)]
        if re.sub(NUMBER, '', args).strip(' ,\t\r\n'):
            raise ValueError('invalid transform: ' + value)
        if name == 'translate' and len(numbers) in (1, 2):
            m = (1., 0., 0., 1., numbers[0], numbers[1] if len(numbers) == 2 else 0.)
        elif name == 'scale' and len(numbers) in (1, 2):
            m = (numbers[0], 0., 0., numbers[-1], 0., 0.)
        elif name == 'rotate' and len(numbers) in (1, 3):
            angle = math.radians(numbers[0])
            c, s = math.cos(angle), math.sin(angle)
            m = (c, s, -s, c, 0., 0.)
            if len(numbers) == 3:
                x, y = numbers[1:]
                m = multiply(multiply((1., 0., 0., 1., x, y), m),
                             (1., 0., 0., 1., -x, -y))
        elif name == 'matrix' and len(numbers) == 6:
            m = tuple(numbers)
        else:
            raise ValueError('unsupported transform: ' + value)
        result = multiply(result, m)
        rest = rest[match.end():]
    return result


def orthogonal_similarity(m):
    a, b, c, d, _, _ = m
    return (a*d-b*c > 0 and abs(a*c+b*d) < 1e-6
            and abs(math.hypot(a, b)-math.hypot(c, d)) < 1e-6
            and (abs(a) < 1e-6 or abs(b) < 1e-6))


def determinant(m):
    return m[0]*m[3] - m[1]*m[2]


def reflected_orthogonal_similarity(m):
    """Axis-aligned orthogonal similarity with a negative determinant."""
    a, b, c, d, _, _ = m
    return (a*d-b*c < 0 and abs(a*c+b*d) < 1e-6
            and abs(math.hypot(a, b)-math.hypot(c, d)) < 1e-6
            and (abs(a) < 1e-6 or abs(b) < 1e-6))


def declared_mirror_axis(node):
    """Layout node mirror value -> None/'x'/'y'; anything else is rejected.

    0 is deliberately not treated as False, matching mirror_policy's domain.
    """
    value = node.get('mirror')
    if value is None or value is False or value == 'none':
        return None
    if isinstance(value, str) and value in ('x', 'y'):
        return value
    raise ValueError('unsupported mirror declaration %r '
                     '(allowed: absent/None/False/none/x/y)' % (value,))


def _translate(x, y):
    return (1., 0., 0., 1., float(x), float(y))


def _uniform_scale(s):
    return (float(s), 0., 0., float(s), 0., 0.)


def _rotation(degrees):
    angle = math.radians(degrees)
    cos, sin = math.cos(angle), math.sin(angle)
    return (cos, sin, -sin, cos, 0., 0.)


def _reflection(width, height, axis):
    # Same geometry as mirror_policy.mirror_svg_transform, kept local so this
    # module stays dependency-free: 'x' -> translate(W,0) scale(-1,1).
    if axis == 'x':
        return (-1., 0., 0., 1., float(width), 0.)
    return (1., 0., 0., -1., 0., float(height))


def declared_instance_matrix(node, vb, axis):
    """Expected instance matrix for the declared pose, matching the renderer
    chain place -> rotate -> optional mirror -> uniform viewBox scale ->
    viewBox origin shift. Requires a finite non-degenerate viewBox and
    rot in 0/90/180/270."""
    vx, vy, vw, vh = vb
    if not all(math.isfinite(v) for v in vb) or vw <= 0 or vh <= 0:
        raise ValueError('symbol viewBox must be finite with positive size: %r'
                         % (vb,))
    k = min(float(node['w'])/vw, float(node['h'])/vh)
    W, H = vw*k, vh*k
    rot = int(node.get('rot', 0)) % 360
    if rot not in (0, 90, 180, 270):
        raise ValueError('declared rot %r outside 0/90/180/270'
                         % (node.get('rot'),))
    comp = {0: (0., 0.), 90: (H, 0.), 180: (W, H), 270: (0., W)}[rot]
    m = multiply(multiply(_translate(node['x'], node['y']),
                          _translate(*comp)), _rotation(rot))
    if axis:
        m = multiply(m, _reflection(W, H, axis))
    return multiply(m, multiply(_uniform_scale(k), _translate(-vx, -vy)))


def _pose_control_points(vb):
    """The four source viewBox corners, in source user units."""
    vx, vy, vw, vh = vb
    return ((vx, vy), (vx + vw, vy), (vx + vw, vy + vh), (vx, vy + vh))


def _pose_matches(expected, actual, control_points):
    """Match two instance poses by their effect on the control points.

    Both matrices transform the same source viewBox corners; agreement is
    required in root SVG user units within a budget tied to each transformed
    point's own magnitude on the sheet (the size %g rounding actually acts
    on), floored at POSE_TOLERANCE and capped at POSE_TOLERANCE_CAP. The
    budget must not scale with the cancellable source-coordinate terms
    feeding the point: a viewBox origin of 1e9 with a ~100px translation
    error must stay a rejection, not ride a 1e9-sized tolerance.
    """
    for xy in control_points:
        for want, got in zip(point(expected, xy), point(actual, xy)):
            budget = min(POSE_RELATIVE_TOLERANCE * max(abs(want), abs(got)),
                         POSE_TOLERANCE_CAP)
            if abs(want - got) > max(POSE_TOLERANCE, budget):
                return False
    return True


def _check_mirror_trace(inst, element, axis):
    """#63 traceability: the instance group's data-mirror records must agree
    with the layout declaration. The renderer emits data-mirror and
    data-mirror-input-anchor only for authorized mirrors, so a declared mirror
    without its record, a record without a declaration, a wrong recorded axis,
    or an input anchor pointing anywhere but this node's own mirror field is a
    broken trace and an issue — never a silent pass."""
    reported = element.get('data-mirror')
    anchor = element.get('data-mirror-input-anchor')
    if axis is None:
        if reported is not None:
            raise ValueError('instance %s records data-mirror=%r but the '
                             'layout declares no mirror' % (inst, reported))
        if anchor is not None:
            raise ValueError('instance %s carries data-mirror-input-anchor=%r '
                             'without a declared mirror' % (inst, anchor))
        return
    if reported != axis:
        raise ValueError('declared mirror=%r but instance %s records '
                         'data-mirror=%r' % (axis, inst, reported))
    if anchor != 'nodes.%s.mirror' % inst:
        raise ValueError('declared mirror=%r but instance %s records '
                         'data-mirror-input-anchor=%r (expected nodes.%s.mirror)'
                         % (axis, inst, anchor, inst))


def walk(root, matrix=IDENTITY):
    """Yield (element, actual cumulative matrix), including the root."""
    matrix = multiply(matrix, transform(root.get('transform')))
    yield root, matrix
    for child in root:
        yield from walk(child, matrix)


def load_geometry(root, layout, resolve_symbol, mirror_axes=None):
    """Read final SVG geometry, optionally honouring validated mirrors (#63).

    mirror_axes maps instance -> 'x'/'y' for mirrors whose catalog permission
    the caller already validated (mirror_policy.check_mirror). Without a
    permission every reflected (det<0) instance matrix is rejected; with one,
    the declared axis, rotation, uniform scale and translation must match the
    actual SVG matrix (including non-zero viewBox origins, compared through
    the transformed source viewBox corners so scale errors are judged at their
    real geometric size). The instance group's data-mirror /
    data-mirror-input-anchor traceability attributes must agree with the
    declaration in both directions. A missing mirror, a wrong axis/rotation,
    an undeclared negative matrix and an inconsistent mirror trace are issues,
    never silent passes. Apart from an authorized reflection, nonuniform,
    non-orthogonal and degenerate transforms stay rejected.
    """
    result = {'coordinate_system': 'root_svg_user_units', 'nodes': {},
              'pipes': [], 'issues': []}
    try:
        elements = list(walk(root))
    except ValueError as error:
        result['issues'].append({'detail': str(error)})
        return result
    instances = {el.get('id', '')[5:]: (el, matrix) for el, matrix in elements
                 if el.get('id', '').startswith('inst-')}
    for inst, node in layout['nodes'].items():
        try:
            if inst not in instances:
                raise ValueError('missing final SVG instance ' + inst)
            element, matrix = instances[inst]
            source = ET.parse(resolve_symbol(node['symbol'])).getroot()
            axis = declared_mirror_axis(node)
            permission = (mirror_axes or {}).get(inst)
            if axis is None:
                if determinant(matrix) < 0:
                    raise ValueError('reflected instance transform without a declared mirror')
                if not orthogonal_similarity(matrix):
                    raise ValueError('unsupported mirrored/nonuniform/nonorthogonal instance transform')
                _check_mirror_trace(inst, element, axis)
            else:
                if permission is None:
                    raise ValueError("declared mirror=%r has no validated catalog permission" % axis)
                if permission != axis:
                    raise ValueError('declared mirror=%r differs from the validated permission axis %r'
                                     % (axis, permission))
                _check_mirror_trace(inst, element, axis)
                if determinant(matrix) > 0:
                    raise ValueError('declared mirror=%r but the instance transform has no reflection' % axis)
                if not reflected_orthogonal_similarity(matrix):
                    raise ValueError('mirrored instance transform is nonuniform/nonorthogonal/degenerate')
                vb = tuple(map(float,
                               source.get('viewBox').replace(',', ' ').split()))
                control = _pose_control_points(vb)
                expected = declared_instance_matrix(node, vb, axis)
                if not _pose_matches(expected, matrix, control):
                    other = 'y' if axis == 'x' else 'x'
                    if _pose_matches(declared_instance_matrix(node, vb, other),
                                     matrix, control):
                        raise ValueError('declared mirror=%r but the instance transform reflects the %s axis'
                                         % (axis, other))
                    raise ValueError('mirrored instance pose (rotation/scale/translation) does not '
                                     'match the declared layout: expected %s actual %s'
                                     % (tuple(round(v, 6) for v in expected),
                                        tuple(round(v, 6) for v in matrix)))
            vx, vy, w, h = map(float, source.get('viewBox').replace(',', ' ').split())
            corners = [point(matrix, p) for p in ((vx, vy), (vx+w, vy),
                                                (vx+w, vy+h), (vx, vy+h))]
            footprint = (min(p[0] for p in corners), min(p[1] for p in corners),
                         max(p[0] for p in corners), max(p[1] for p in corners))
            ports = {}
            for el, local in walk(source):
                pid = el.get('data-port-id')
                if not pid:
                    continue
                if pid in ports:
                    raise ValueError('duplicate symbol port ' + pid)
                pm = multiply(matrix, local)
                xy = point(pm, (float(el.get('cx')), float(el.get('cy'))))
                vector = DIRECTIONS[el.get('data-anchor-direction')]
                dx, dy = pm[0]*vector[0]+pm[2]*vector[1], pm[1]*vector[0]+pm[3]*vector[1]
                length = math.hypot(dx, dy)
                direction = (dx/length, dy/length)
                ports[pid] = {'position': xy, 'direction': direction,
                              'anchor_direction': min(DIRECTIONS, key=lambda k:
                                  math.dist(DIRECTIONS[k], direction)),
                              'role': el.get('data-port-role'), 'medium': el.get('data-medium')}
            if not ports:
                raise ValueError('missing symbol connection-points')
            result['nodes'][inst] = {'matrix': matrix, 'footprint': footprint,
                                    'ports': ports, 'symbol': node['symbol']}
        except (ValueError, KeyError, TypeError, OSError, ET.ParseError) as error:
            result['issues'].append({'component': inst, 'detail': str(error)})
    for el, matrix in elements:
        classes = el.get('class', '').split()
        cls = next((v for v in classes if v.startswith('ln-')), None)
        if not cls:
            continue
        tag = el.tag.rsplit('}', 1)[-1]
        try:
            if tag == 'polyline':
                numbers = [float(v) for v in re.findall(NUMBER, el.get('points', ''))]
                if len(numbers) % 2:
                    raise ValueError('odd polyline coordinate count')
                pts = list(zip(numbers[::2], numbers[1::2]))
            elif tag == 'line':
                pts = [(float(el.get('x1')), float(el.get('y1'))),
                       (float(el.get('x2')), float(el.get('y2')))]
            else:
                raise ValueError('unsupported pipe element ' + tag)
            if len(pts) < 2:
                raise ValueError('pipe has fewer than two points')
            result['pipes'].append({'class': cls, 'points': [point(matrix, p) for p in pts],
                                    'svg_id': el.get('id'), 'index': len(result['pipes'])})
        except (ValueError, TypeError) as error:
            result['issues'].append({'svg_id': el.get('id'), 'detail': str(error)})
    return result
