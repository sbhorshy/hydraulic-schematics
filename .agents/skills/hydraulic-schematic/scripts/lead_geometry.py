"""Linear SVG segments and source-defined external lead spans.

Supports line, polyline and paths using M/L/H/V (absolute/relative, repeated
arguments, multiple subpaths). Curves and closed paths are deliberately not
external-lead candidates unless annotated, in which case they are unchecked.
"""
import math
import re
from sheet_geometry import NUMBER, walk, point


def segments(tag, attrs):
    tag = tag.rsplit('}', 1)[-1]
    if tag == 'line':
        a = (float(attrs.get('x1', 0)), float(attrs.get('y1', 0)))
        b = (float(attrs.get('x2', 0)), float(attrs.get('y2', 0)))
        return [(a,b)] if math.dist(a,b)>1e-8 else []
    if tag == 'polyline':
        numbers = list(map(float, re.findall(NUMBER, attrs.get('points', ''))))
        if len(numbers) < 4 or len(numbers) % 2:
            raise ValueError('invalid polyline')
        points = list(zip(numbers[::2], numbers[1::2]))
        return [(a,b) for a,b in zip(points,points[1:]) if math.dist(a,b)>1e-8]
    if tag != 'path':
        return []
    value = attrs.get('d', '')
    tokens = re.findall(r'[A-Za-z]|'+NUMBER, value)
    if re.sub(r'[MmLlHhVv]|'+NUMBER, '', value).strip(' ,\t\n\r'):
        raise ValueError('unsupported non-linear/closed path')
    out, i, command, current = [], 0, None, (0., 0.)
    while i < len(tokens):
        if tokens[i].isalpha():
            command, i = tokens[i], i+1
        if command is None:
            raise ValueError('missing path command')
        count = 1 if command.lower() in ('h','v') else 2
        args = list(map(float, tokens[i:i+count]))
        if len(args) != count:
            raise ValueError('incomplete path command')
        i += count
        x,y = current
        if command.lower() == 'h':
            target = (args[0]+(x if command.islower() else 0), y)
        elif command.lower() == 'v':
            target = (x, args[0]+(y if command.islower() else 0))
        else:
            target = (args[0]+(x if command.islower() else 0), args[1]+(y if command.islower() else 0))
        if command.lower() != 'm':
            out.append((current,target))
        else:
            command = 'l' if command == 'm' else 'L'
        current = target
    return [(a,b) for a,b in out if math.dist(a,b)>1e-8]


def source_leads(root, ports):
    """Return actual source element, matrix, segment list and matching port ID.

    Port matching is geometric, not a renderer-supplied pl-* class claim.
    """
    result, unchecked = [], []
    for el, matrix in walk(root):
        try:
            local = segments(el.tag, el.attrib)
        except (ValueError, TypeError) as error:
            if el.get('data-interface-port'):
                unchecked.append({'port':el.get('data-interface-port'), 'element':el.get('id'), 'reason':str(error)})
            continue
        if not local:
            if el.get('data-interface-port'):
                unchecked.append({'port':el.get('data-interface-port'), 'element':el.get('id'), 'reason':'Empty or unsupported external lead geometry'})
            continue
        mapped = [(point(matrix,a),point(matrix,b)) for a,b in local]
        matching = [pid for pid,p in ports.items()
                    if any(math.dist(p[:2],q)<.1 for seg in mapped for q in seg)]
        if len(matching) == 1:
            result.append({'element':el, 'matrix':matrix, 'segments':mapped,
                           'local_segments':local, 'port':matching[0]})
    return result, unchecked


def perpendicular_scale(matrix, vector):
    length = math.hypot(*vector)
    if length < 1e-9:
        raise ValueError('zero tangent')
    x,y = vector[0]/length, vector[1]/length
    a,b,c,d = matrix[:4]
    transformed = math.hypot(a*x+c*y,b*x+d*y)
    if transformed < 1e-9:
        raise ValueError('singular stroke transform')
    return abs(a*d-b*c)/transformed
