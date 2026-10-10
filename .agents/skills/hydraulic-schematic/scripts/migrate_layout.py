"""Explicitly migrate a legacy L0 layout to root-SVG units without moving content.

Only drawing-local x coordinates gain the old translation. Panels remain in
root units. If required, extend the canvas rightward in 10-unit increments to
provide the new margin; never shrink the margin or reposition a component.
"""
import argparse
import copy
import json
import math
from pathlib import Path
from layout_contract import EDGE_MARGIN, drawable_bounds, make_contract, number, pipe_half_width

LEGACY_BOUNDARY_TERMINALS = [[1480.0,300.0],[1480.0,700.0],[60.0,514.4]]


def migrate(layout, margin=EDGE_MARGIN, declare_root=False):
    result = copy.deepcopy(layout)
    if declare_root:
        if ('canvas_shift_x' in result or 'drawable' not in result
                or result.get('coordinate_system') not in (None, 'root_svg_user_units')):
            raise ValueError('--declare-root requires an undeclared drawable layout with verified root coordinates; '
                             'it cannot override an unknown coordinate_system or a legacy canvas_shift_x')
        result['coordinate_system'] = 'root_svg_user_units'
    if 'canvas_shift_x' not in result and 'drawable' in result:
        drawable_bounds(result)
        return result
    shift = number(result.pop('canvas_shift_x',0), 'legacy shift')
    for section in ('nodes','externs','buses'):
        for obj in (result.get(section) or {}).values():
            obj['x'] += shift
    result['vlanes'] = [x+shift for x in result.get('vlanes',[])]
    result['boundary_terminals'] = [[x+shift,y] for x,y in result.get('boundary_terminals',LEGACY_BOUNDARY_TERMINALS)]
    assembly = result.get('assembly_layout') or {}
    for decision in assembly.get('decisions',[]):
        if 'x' in decision: decision['x'] += shift
    if 'ASSEMBLY_START_X' in assembly.get('params',{}):
        assembly['params']['ASSEMBLY_START_X'] += shift
    width, height = result['canvas']['width'], result['canvas']['height']
    radius = pipe_half_width(result)
    right = 0
    for node in (result.get('nodes') or {}).values():
        extent = node['h'] if int(node.get('rot',0)) % 180 else node['w']
        right = max(right, node['x']+extent+18+radius)
    for section in ('buses','externs'):
        for obj in (result.get(section) or {}).values():
            right = max(right, obj['x']+radius)
    if right+margin > width:
        width = math.ceil((right+margin)/10)*10
        result['canvas']['width'] = width
    result.update(make_contract(width,height,margin))
    drawable_bounds(result)
    result.setdefault('revision_log',[]).append(
        'root-coordinate migration: content x %+g; panels unchanged; canvas right %g→%g; edge_margin=%g'
        % (shift, layout['canvas']['width'], width, margin))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input');parser.add_argument('-o','--output',required=True)
    parser.add_argument('--edge-margin',type=float,default=EDGE_MARGIN)
    parser.add_argument('--declare-root',action='store_true',
                        help='explicitly confirm an undeclared drawable layout already uses root SVG units; preserve geometry')
    args=parser.parse_args()
    try:
        output=migrate(json.loads(Path(args.input).read_text(encoding='utf-8')),args.edge_margin,declare_root=args.declare_root)
        Path(args.output).write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    except (OSError,ValueError,KeyError,TypeError) as error:
        parser.exit(1,str(error)+'\n')


if __name__=='__main__':main()
