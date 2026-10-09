"""Read final SVG geometry in root SVG user units (including canvas shift).

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


def walk(root, matrix=IDENTITY):
    """Yield (element, actual cumulative matrix), including the root."""
    matrix = multiply(matrix, transform(root.get('transform')))
    yield root, matrix
    for child in root:
        yield from walk(child, matrix)


def load_geometry(root, layout, resolve_symbol):
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
            if not orthogonal_similarity(matrix):
                raise ValueError('unsupported mirrored/nonuniform/nonorthogonal instance transform')
            source = ET.parse(resolve_symbol(node['symbol'])).getroot()
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
