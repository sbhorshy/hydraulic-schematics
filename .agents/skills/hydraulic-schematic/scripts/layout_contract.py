"""One root-SVG coordinate contract for current L0 layouts.

Drawable is the content rectangle. The explicit right edge margin is outside
that rectangle, inside the canvas; consumers must not subtract it a second time.
"""
import math

EDGE_MARGIN = 30.0


def number(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError('layout %s must be a finite number' % name)
    return float(value)


def make_contract(width, height, margin=EDGE_MARGIN):
    return {'coordinate_system':'root_svg_user_units',
            'drawable':{'x':0, 'y':0, 'width':width-margin, 'height':height},
            'edge_margin':margin}


def drawable_bounds(layout):
    if 'canvas_shift_x' in layout:
        raise ValueError('Legacy canvas_shift_x layout: run migrate_layout.py INPUT -o OUTPUT first')
    try:
        canvas = layout['canvas']; drawable = layout['drawable']
        cw, ch = (number(canvas[k], 'canvas.'+k) for k in ('width','height'))
        x, y, w, h = (number(drawable[k], 'drawable.'+k) for k in ('x','y','width','height'))
        margin = number(layout['edge_margin'], 'edge_margin')
    except (KeyError, TypeError) as error:
        raise ValueError('Layout requires explicit drawable and edge_margin; use migrate_layout.py') from error
    if margin < EDGE_MARGIN:
        raise ValueError('edge_margin must be at least %g SVG units' % EDGE_MARGIN)
    if (min(cw,ch,w,h)<=0 or min(x,y)<0 or x+w+margin>cw+1e-6 or y+h>ch+1e-6):
        raise ValueError('drawable must fit canvas with its declared right edge_margin')
    if layout.get('coordinate_system') != 'root_svg_user_units':
        raise ValueError(
            "Layout requires explicit coordinate_system='root_svg_user_units'; "
            'for an undeclared layout with verified root coordinates run migrate_layout.py --declare-root INPUT -o OUTPUT; '
            'for legacy canvas_shift_x use migrate_layout.py INPUT -o OUTPUT')
    return x, y, x+w, y+h


def pipe_half_width(layout):
    """Largest standard pipe radius, used by layout guards before paint exists."""
    return 1.5 * float((layout.get('style') or {}).get('base_line_width_T',1.2))
