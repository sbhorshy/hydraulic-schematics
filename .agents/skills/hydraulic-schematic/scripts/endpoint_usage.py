"""One input-defined port inventory for rendering and V5 disclosure.

Bare path instances use the catalog main_path.in when preceded and main_path.out
when followed by another token. Taps use both declared endpoints regardless of
gas/measurement/body_tap semantics.
Unknowns describe uncertainty; they neither create nor consume ports.
"""
from collections import Counter
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def resolve_symbol(ref, workdir, catalog_dir):
    candidates = [Path(workdir) / ref,
                  Path(catalog_dir) / Path(ref.replace('\\', '/')).name]
    return next((p for p in candidates if p.is_file()), candidates[0]).resolve()


def endpoint_usage(intent, types, nodes):
    used = set()
    for path in intent.get('paths') or []:
        for index, token in enumerate(path):
            inst, dot, pid = token.partition('.')
            if inst not in intent['parts']:
                continue
            if dot:
                used.add(token)
            else:
                main = types[intent['parts'][inst]].get('main_path') or {}
                if index > 0 and 'in' in main:
                    used.add(inst + '.' + main['in'])
                if index < len(path) - 1 and 'out' in main:
                    used.add(inst + '.' + main['out'])
    for tap in intent.get('taps') or []:
        used.update(tap[k] for k in ('sensor', 'at'))
    declared = {inst + '.' + port['id']
                for inst, typ in intent['parts'].items() if inst in nodes
                for port in types[typ]['ports']}
    return {'used': sorted(used), 'declared': sorted(declared),
            'dangling': sorted(declared - used)}


def symbol_contract(intent, types, nodes, workdir, catalog_dir):
    """Audit the selected local symbol, never a catalog default replacing it.

    Port identity/coordinate metadata is structural. Catalog role overrides for
    shared symbols (e.g. return filters) remain authoritative and are permitted.
    """
    issues = []
    for inst, node in nodes.items():
        if inst not in intent['parts']:
            continue
        source = resolve_symbol(node['symbol'], workdir, catalog_dir)
        typ = types[intent['parts'][inst]]
        declared = {p['id'] for p in typ['ports']}

        def add(kind, detail, pid=None):
            issues.append({'kind': kind, 'component': inst,
                           'endpoint': inst + '.' + pid if pid else None,
                           'symbol': str(source), 'detail': '%s 符号端口契约: %s' % (inst, detail)})

        try:
            root = ET.parse(source).getroot()
        except (OSError, ET.ParseError) as exc:
            add('unreadable_symbol', str(exc))
            continue
        groups = [g for g in root.iter() if g.get('id') == 'connection-points']
        if len(groups) != 1:
            add('port_group', 'connection-points 组数量 %d，预期 1' % len(groups))
        markers = [p for g in groups for p in g]
        counts = Counter(p.get('data-port-id') for p in markers)
        actual = {pid for pid in counts if pid}
        for pid in sorted(declared - actual):
            add('missing_symbol_port', '目录声明的 %s 缺于实际符号' % pid, pid)
        for pid in sorted(actual - declared):
            add('undeclared_symbol_port', '实际符号的 %s 未在目录声明' % pid, pid)
        for pid, count in counts.items():
            if not pid or count != 1:
                add('invalid_port_id', 'data-port-id=%s 数量 %d' % (pid, count), pid)
        for marker in markers:
            try:
                xy = [float(marker.get(k)) for k in ('cx', 'cy')]
                valid = all(math.isfinite(v) for v in xy)
            except (TypeError, ValueError):
                valid = False
            if not valid or marker.get('data-anchor-direction') not in ('up', 'down', 'left', 'right'):
                add('invalid_port_geometry', '端口 %s 坐标/锚向无效' % marker.get('data-port-id'),
                    marker.get('data-port-id'))
    return issues


def write_contract_failure(workdir, inventory, issues, unknown):
    """Keep an actionable report even when broken assets prevent rendering."""
    report = {'sheet': '1#系统原理图.svg', 'validation': 'failed',
              'visual_review': 'pending', 'fail_count': len(issues), 'warn_count': 0,
              'checks': [{'id': 'V5', 'result': 'fail', 'detail': q['detail']} for q in issues],
              'evidence': [{'id': 'V5', **inventory, 'contract_issues': issues,
                            'drawing_issues': [], 'drawing_status': 'not_checked',
                            'reason': '符号端口契约失败，未继续几何/披露校核', 'unknown': unknown}]}
    (Path(workdir) / 'validation-report.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in issues:
        print('FAIL V5 ' + item['detail'])
    return 1


def check_disclosure(root, inventory, ports):
    """Compare actual sheet circles and printed title against the input inventory."""
    issues = []
    parents = {child: parent for parent in root.iter() for child in parent}

    def hidden(element):
        while element is not None:
            style = dict(re.findall(r'([\w-]+)\s*:\s*([^;]+)', element.get('style', '')))
            if (style.get('display', element.get('display')) == 'none'
                    or style.get('visibility', element.get('visibility')) in ('hidden', 'collapse')):
                return True
            try:
                if float(style.get('opacity', element.get('opacity', '1'))) <= 0:
                    return True
            except ValueError:
                pass
            element = parents.get(element)
        return False
    rendered = Counter(e.get('data-port') for e in root.iter()
                       if e.tag.rsplit('}', 1)[-1] == 'metadata' and e.get('data-port'))
    declared = set(inventory['declared'])
    for endpoint in sorted(declared | set(rendered)):
        if rendered[endpoint] != int(endpoint in declared):
            issues.append({'kind': 'drawn_port', 'endpoint': endpoint,
                           'detail': '%s 图上端口标记数量 %d，预期 %d（输入使用: %s）'
                           % (endpoint, rendered[endpoint], int(endpoint in declared),
                              endpoint in inventory['used'])})
    group = next((e for e in root.iter() if e.get('id') == 'dangling'), None)
    marks = list(group) if group is not None else []
    counts = Counter(e.get('data-port') for e in marks)
    expected = set(inventory['dangling'])
    for endpoint in sorted(expected | set(counts), key=str):
        count = counts[endpoint]
        if (endpoint not in expected) or count != 1:
            issues.append({'kind': 'dangling_marker', 'endpoint': endpoint,
                           'detail': '%s 悬空红圈数量 %d，预期 %d'
                           % (endpoint, count, int(endpoint in expected))})
    for marker in marks:
        endpoint = marker.get('data-port')
        if endpoint not in expected:
            continue
        inst, pid = endpoint.split('.', 1)
        point = ports.get(inst, {}).get(pid)
        try:
            xy = (float(marker.get('cx')), float(marker.get('cy')))
            visible = (float(marker.get('r', '0')) > 0 and not hidden(marker)
                       and marker.tag.rsplit('}', 1)[-1] == 'circle'
                       and 'dang' in marker.get('class', '').split())
        except (TypeError, ValueError):
            xy, visible = None, False
        if not visible or not point or any(abs(xy[k] - point[k]) > 0.2 for k in (0, 1)):
            issues.append({'kind': 'dangling_marker', 'endpoint': endpoint,
                           'xy': xy, 'detail': '%s 悬空红圈不可见或偏离端口' % endpoint})
    title = next((e for e in root.iter() if e.get('id') == 'title'), None)
    text = ''.join(title.itertext()) if title is not None else ''
    disclosure = re.search(r'悬空端口\s+(\d+)\s*:\s*([^|]*)', text)
    if (hidden(title) or not disclosure or int(disclosure[1]) != len(expected)
            or set(disclosure[2].split()) != (expected or {'无'})):
        issues.append({'kind': 'dangling_title',
                       'detail': '图签悬空端口计数/清单与输入未接端口不一致，预期 %d: %s'
                       % (len(expected), ' '.join(sorted(expected)) or '无')})
    return issues
