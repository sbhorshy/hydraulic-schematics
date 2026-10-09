"""Freeze verified sheet versions and compare declared changes without signing review."""
import argparse
import json
import math
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET

from sheet_version import freeze_version, read_version
from proofreading_evidence import digest_json, file_digest


def _model(version):
    report = version['report']
    topology = report.get('topology', {})
    if topology.get('coverage_status') != 'pass' or report.get('geometry', {}).get('issues'):
        raise ValueError('Complete measured topology and normalized geometry are required for comparison')
    browser_path = version['files'].get('browser_evidence')
    browser = json.loads(browser_path.read_text(encoding='utf-8')) if browser_path else {}
    if browser.get('status') != 'pass':
        raise ValueError('Current browser measurements are required for object attribution')
    return {'version': version, 'topology': topology, 'geometry': report['geometry'], 'browser': browser}


def _relations(topology):
    def edges(key):
        grouped = {}
        for edge in topology[key]:
            grouped.setdefault(edge['anchor'], []).append(sorted(edge['endpoints']))
        return {k: sorted(v) for k, v in grouped.items()}
    return {'declared': edges('expected_edges'), 'actual': edges('actual_edges'),
            'networks': sorted(sorted(n['terminals']) for n in topology['networks']),
            'nodes': sorted((n['id'], n['type']) for n in topology['nodes']),
            'ports': sorted((p['id'], p['catalog_anchor']) for p in topology['ports']),
            'unknown': topology['unknown']}


def _scope(scope, models):
    allowed_keys = {'nodes', 'edges', 'include_adjacent_edges', 'global', 'note', 'topology_changes'}
    if not isinstance(scope, dict) or set(scope) - allowed_keys:
        raise ValueError('Scope has unsupported fields; declare nodes/edges/global and optional exact topology_changes, never masks')
    if not isinstance(scope.get('note'), str) or not scope['note'].strip():
        raise ValueError('Scope requires a concrete note describing the intended change')
    nodes = scope.get('nodes', [])
    edges = scope.get('edges', [])
    if any(not isinstance(v, list) or any(not isinstance(i, str) for i in v) for v in (nodes, edges)):
        raise ValueError('Scope nodes and edges must be identifier lists')
    for key in ('global', 'include_adjacent_edges'):
        if key in scope and not isinstance(scope[key], bool):
            raise ValueError(key + ' must be boolean')
    known_nodes = {n['id'] for m in models for n in m['topology']['nodes']}
    declared = [e for m in models for e in m['topology']['expected_edges']]
    known_edges = {e['anchor'] for e in declared} | {b['anchor'] for m in models for b in m['topology']['buses']}
    if set(nodes) - known_nodes or set(edges) - known_edges:
        raise ValueError('Scope references unknown node or input edge identifiers')
    transitions = scope.get('topology_changes', {})
    if not isinstance(transitions, dict) or set(transitions) - set(edges):
        raise ValueError('Exact topology changes require individually declared edge targets')
    for transition in transitions.values():
        if (not isinstance(transition, dict) or set(transition) != {'before', 'after'} or
                any(not isinstance(v, list) or len(v) != 2 or any(not isinstance(p, str) for p in v)
                    for v in transition.values())):
            raise ValueError('Each topology transition must name exactly two before and two after endpoints')
    adjacent = set()
    if scope.get('include_adjacent_edges', False):
        adjacent = {e['anchor'] for e in declared if any(p.split('.')[0] in nodes for p in e['endpoints'])}
    if not nodes and not edges and not scope.get('global'):
        raise ValueError('Declare at least one target node/edge or an explicit global change')
    return {**scope, 'nodes': sorted(set(nodes)), 'edges': sorted(set(edges)),
            'global': scope.get('global', False), 'adjacent_edges': sorted(adjacent),
            'allowed_edges': sorted(set(edges) | adjacent), 'topology_changes': transitions}


def _declared_networks(edges):
    parent = {}
    def find(p):
        parent.setdefault(p, p)
        while parent[p] != p:
            p = parent[p]
        return p
    for relations in edges.values():
        for a, b in relations:
            parent[find(a)] = find(b)
    groups = {}
    for endpoint in parent:
        groups.setdefault(find(endpoint), []).append(endpoint)
    return sorted(sorted(v) for v in groups.values())


def _topology_delta(before, after, scope):
    changed = {key: sorted(k for k in before[key].keys() | after[key].keys()
                           if before[key].get(k) != after[key].get(k)) for key in ('declared', 'actual')}
    unexpected, authorized = [], []
    candidates = set(changed['declared']) | set(changed['actual']) | set(scope['topology_changes'])
    for anchor in sorted(candidates):
        claim = scope['topology_changes'].get(anchor)
        exact = claim and all(relations[key].get(anchor) == [sorted(claim[version])]
                              for version, relations in (('before', before), ('after', after))
                              for key in ('declared', 'actual'))
        if exact:
            authorized.append(anchor)
        else:
            unexpected.append({'kind': 'unexpected_topology', 'anchor': anchor,
                               'before': {k: before[k].get(anchor) for k in ('declared', 'actual')},
                               'after': {k: after[k].get(anchor) for k in ('declared', 'actual')},
                               'detail': 'Node/adjacent-edge visual scope does not authorize changed port connections'})
    if before['networks'] != after['networks']:
        if not authorized or after['networks'] != _declared_networks(after['declared']):
            unexpected.append({'kind': 'unexpected_topology', 'detail': 'Actual network joins changed beyond an exact authorized input transition'})
    for key in ('nodes', 'ports', 'unknown'):
        if before[key] != after[key]:
            unexpected.append({'kind': 'unexpected_topology', 'detail': key + ' contract/disclosure changed',
                               'before': before[key], 'after': after[key]})
    return {'unchanged': before == after, 'declared_changed_edges': changed['declared'],
            'actual_changed_edges': changed['actual'], 'network_changed': before['networks'] != after['networks'],
            'authorized_changes': authorized, 'unexpected_changes': unexpected,
            'before': before, 'after': after}


def _owner(row):
    if row.get('instance'):
        return 'node:' + row['instance']
    attrs = row['attrs']
    if attrs.get('data-label-for'):
        target = attrs['data-label-for']
        return ('extern:' + target[1:]) if target.startswith('@') else 'node:' + target
    if attrs.get('data-port'):
        return 'node:' + attrs['data-port'].split('.')[0]
    if attrs.get('data-input-anchor', '').startswith(('paths[', 'taps[', 'buses.')):
        return 'edge:' + attrs['data-input-anchor']
    if attrs.get('data-edges'):
        return 'junction:' + '|'.join(sorted(attrs['data-edges'].split()))
    if attrs.get('data-extern'):
        return 'extern:' + attrs['data-extern']
    return 'other'


def _rows(model):
    return [r for r in model['browser']['elements']
            if r['tag'] not in ('g', 'svg', 'tspan')
            and not any(a['tag'] in ('defs', 'clipPath', 'mask', 'symbol') for a in r.get('ancestors', []))]


def _objects(model):
    objects = {}
    for row in _rows(model):
        # DOM indexes are renderer bookkeeping, not source identities.
        record = {k: row.get(k) for k in ('tag', 'attrs', 'matrix', 'bbox', 'style', 'visible', 'opacity', 'text')}
        objects.setdefault(_owner(row), []).append(record)
    for node, geometry in model['geometry']['nodes'].items():
        # The driver relocates identical selected assets into content-addressed
        # directories. Paths are provenance; actual ports/footprints are geometry.
        objects.setdefault('node:' + node, []).append({'source_geometry': {
            k: v for k, v in geometry.items() if k != 'symbol'}})
    return objects


def _allowed(owner, scope):
    if scope['global']:
        return True
    if owner.startswith('node:'):
        return owner[5:] in scope['nodes']
    if owner.startswith('edge:'):
        return owner[5:] in scope['allowed_edges']
    if owner.startswith('junction:'):
        return bool(set(owner[9:].split('|')) & set(scope['allowed_edges']))
    return False


def _paint_alpha(value):
    if value == 'none':
        return 0
    match = re.fullmatch(r'rgba?\(([^)]+)\)', value)
    if not match:
        raise ValueError('Scoped paint servers or unsupported colors cannot produce a reliable ink mask')
    values = [float(v.strip()) for v in match[1].split(',')]
    if len(values) not in (3, 4):
        raise ValueError('Unsupported scoped color syntax')
    return values[3] if len(values) == 4 else 1


def _ink_mask(model, scope, output, name):
    """One batch rasterization for every allowed object; no rectangular masks."""
    import numpy as np
    from PIL import Image
    from rasterize_sheet import export

    version = model['version']
    root = ET.parse(version['files']['svg']).getroot()
    elements = list(root.iter())
    for row in _rows(model):
        element = elements[row['key']]
        if row['tag'] != element.tag.rsplit('}', 1)[-1]:
            raise ValueError('Browser/SVG element identity mismatch while attributing changed pixels')
        style = element.get('style', '') + ';'
        if not _allowed(_owner(row), scope) or not row['visible']:
            element.set('style', style + 'display:none!important;')
            continue
        effects = [row['style']] + [a.get('effects', {}) for a in row.get('ancestors', [])]
        if row['tag'] in ('use', 'image') or any(s.get(k, 'none') != 'none' for s in effects for k in ('clip-path', 'mask', 'filter')):
            raise ValueError('Scoped image/use/clipping/mask/filter ink cannot be attributed reliably')
        for paint in ('stroke', 'fill'):
            alpha = _paint_alpha(row['style'].get(paint, 'none'))
            style += '%s:%s!important;' % (paint, 'rgba(0,0,0,%g)' % alpha if alpha else 'none')
        element.set('style', style)
    svg = output / (name + '-scope.svg')
    ET.register_namespace('', 'http://www.w3.org/2000/svg')
    svg.write_text(ET.tostring(root, encoding='unicode'), encoding='utf-8')
    receipt = version['verification']['png']['receipt']['renderer']
    result = export(svg, output / (name + '-scope.png'), backend=receipt['backend'])
    derived = json.loads((output / (name + '-scope.png.evidence.json')).read_text())
    if derived['renderer']['version'] != receipt['version']:
        raise ValueError('Historical rasterizer is unavailable; derived ink masks would use a different renderer version')
    pixels = np.asarray(Image.open(output / (name + '-scope.png')).convert('RGB'))
    return np.any(pixels < 255, axis=2), result


def _regions(mask):
    """Connected changed-pixel runs, for localization only (never an ignore mask)."""
    import numpy as np
    parent, boxes, counts = [], [], []
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    previous = []
    for y, row in enumerate(mask):
        edges = np.flatnonzero(np.diff(np.r_[False, row, False]))
        current = []
        for start, stop in zip(edges[::2], edges[1::2]):
            ident = len(parent); parent.append(ident)
            boxes.append([int(start), y, int(stop), y + 1]); counts.append(int(stop - start))
            current.append((int(start), int(stop), ident))
            for lo, hi, old in previous:
                if lo > stop:
                    break
                if hi >= start:
                    a, b = find(ident), find(old)
                    if a != b:
                        parent[b] = a
                        boxes[a] = [min(boxes[a][0], boxes[b][0]), min(boxes[a][1], boxes[b][1]),
                                    max(boxes[a][2], boxes[b][2]), max(boxes[a][3], boxes[b][3])]
                        counts[a] += counts[b]
        previous = current
    return [{'bbox': box, 'pixels': counts[i]} for i, box in enumerate(boxes) if find(i) == i]


def compare_versions(before, after, scope, output, pixel_threshold=8):
    """Report local semantic/visual changes without overriding full validation."""
    import numpy as np
    from PIL import Image

    started = time.monotonic()
    target = Path(output).resolve()
    if target.exists():
        raise ValueError('Comparison output already exists: ' + str(target))
    if not 0 <= pixel_threshold <= 16:
        raise ValueError('Per-channel antialias tolerance must be between 0 and 16 of 255')
    versions = [read_version(before), read_version(after)]
    models = [_model(v) for v in versions]
    allowed = _scope(scope, models)
    if models[0]['browser']['viewbox'] != models[1]['browser']['viewbox']:
        raise ValueError('SVG canvases cannot be aligned without resampling; declare the global change but compare pixels separately')
    images = [Image.open(v['files']['png']).convert('RGB') for v in versions]
    if images[0].size != images[1].size:
        raise ValueError('PNG dimensions differ; pixel comparison is not reliable')
    target.mkdir(parents=True)
    # Freeze both inputs before deriving any new evidence, preserving tools and assets.
    frozen = [freeze_version(v['root'], target / label) for v, label in zip(versions, ('before', 'after'))]
    models = [_model(v) for v in frozen]
    allowed = _scope(scope, models)
    images = [Image.open(v['files']['png']).convert('RGB') for v in frozen]
    if models[0]['browser']['viewbox'] != models[1]['browser']['viewbox'] or images[0].size != images[1].size:
        raise ValueError('Frozen canvases cannot be aligned without resampling')
    before_rel, after_rel = [_relations(m['topology']) for m in models]
    topology = _topology_delta(before_rel, after_rel, allowed)
    objects = [_objects(m) for m in models]
    changed = sorted(k for k in objects[0].keys() | objects[1].keys() if objects[0].get(k) != objects[1].get(k))
    unexpected_objects = [k for k in changed if not _allowed(k, allowed)]
    arrays = [np.asarray(image).astype(np.int16) for image in images]
    delta = np.max(np.abs(arrays[0] - arrays[1]), axis=2)
    changed_pixels = delta > pixel_threshold
    rasterizations = []
    if not np.any(changed_pixels):
        expected_pixels = np.zeros(changed_pixels.shape, dtype=bool)
    elif allowed['global']:
        expected_pixels = np.ones(changed_pixels.shape, dtype=bool)
    else:
        masks = []
        for model, label in zip(models, ('before', 'after')):
            mask, timing = _ink_mask(model, allowed, target, label)
            masks.append(mask); rasterizations.append(timing)
        expected_pixels = masks[0] | masks[1]
    unexpected_pixels = changed_pixels & ~expected_pixels
    overlay = np.asarray(images[1]).copy()
    overlay[changed_pixels & expected_pixels] = [255, 180, 0]
    overlay[unexpected_pixels] = [255, 0, 80]
    Image.fromarray(overlay).save(target / 'diff-overlay.png')
    findings = list(topology['unexpected_changes'])
    findings.extend({'kind': 'unexpected_object', 'object': key} for key in unexpected_objects)
    if np.any(unexpected_pixels):
        findings.append({'kind': 'unexpected_pixels', 'detail': 'Changed pixels extend beyond the actual permitted object ink'})
    report = {'schema': 'sheet-change-v1', 'status': 'fail' if findings else 'pass', 'scope': allowed,
              'delivery_certified': False, 'findings': findings,
              'versions': {label: {'artifact_fingerprint': v['verification']['fingerprint'],
                                  'verification': v['verification'], 'frozen': label,
                                  'validation': v['report']['validation'], 'delivery': v['report']['delivery']}
                           for label, v in zip(('before', 'after'), frozen)},
              'topology': topology,
              'objects': {'changed_nodes': [k[5:] for k in changed if k.startswith('node:')],
                          'changed_edges': [k[5:] for k in changed if k.startswith('edge:')],
                          'changed_other': [k for k in changed if not k.startswith(('node:', 'edge:'))],
                          'unexpected': unexpected_objects},
              'pixels': {'changed': int(changed_pixels.sum()), 'unexpected': int(unexpected_pixels.sum()),
                         'below_tolerance': int(((delta > 0) & ~changed_pixels).sum()),
                         'channel_tolerance': pixel_threshold, 'comparison_extent': [0, 0, *images[0].size],
                         'alignment': 'identical root SVG viewBox and PNG dimensions; no resampling or registration',
                         'regions': _regions(changed_pixels), 'unexpected_regions': _regions(unexpected_pixels),
                         'scope_mask': 'union of actual rendered permitted ink in both versions; no rectangular dilation'},
              'timing': {'elapsed_s': round(time.monotonic() - started, 6),
                         'derived_rasterizations': len(rasterizations), 'rasterizations': rasterizations},
              'comparison_tool_sha256': file_digest(__file__)}
    (target / 'change-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    freeze = commands.add_parser('freeze', help='Preserve a current report, SVG/PNG, tools and symbols')
    freeze.add_argument('version')
    freeze.add_argument('--output', required=True)
    verify = commands.add_parser('verify', help='Verify frozen or live evidence before comparison')
    verify.add_argument('version')
    compare = commands.add_parser('compare', help='Compare verified versions against an explicit impact scope')
    compare.add_argument('before')
    compare.add_argument('after')
    compare.add_argument('--scope', required=True)
    compare.add_argument('--output', required=True)
    compare.add_argument('--pixel-threshold', type=int, default=8)
    args = parser.parse_args()
    output_existed = args.command == 'compare' and Path(args.output).exists()
    started = time.monotonic()
    try:
        if args.command == 'compare':
            report = compare_versions(args.before, args.after, json.loads(Path(args.scope).read_text()),
                                      args.output, args.pixel_threshold)
            print(json.dumps({'status': report['status'], 'report': str(Path(args.output) / 'change-report.json')}, ensure_ascii=False))
            return 0 if report['status'] == 'pass' else 1
        result = (freeze_version(args.version, args.output) if args.command == 'freeze'
                  else read_version(args.version))
        print(json.dumps(result['verification'], ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'schema': 'sheet-change-v1', 'status': 'not_comparable', 'reason': str(error),
                  'pixels': None, 'delivery_certified': False,
                  'timing': {'elapsed_s': round(time.monotonic() - started, 6)}}
        if args.command == 'compare' and not output_existed:
            output = Path(args.output)
            output.mkdir(parents=True, exist_ok=True)
            result['sources'] = {'before': args.before, 'after': args.after, 'scope_file': args.scope}
            (output / 'change-report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2


if __name__ == '__main__':
    sys.exit(main())
