"""Input anchors and independently measured SVG connectivity.

Coordinates exposed here are root SVG user units (canvas shift already applied).
Logical input edges use stable paths[i][k->k+1] / taps[i] anchors. Shared bus
trunks and bridge-split runs are representation, never extra logical edges.
"""
import json
from pathlib import Path
from svg_paint import color_rgba, has_dash_gaps, computed_length


def declared_topology(intent, catalog):
    types = {c['component_type']: c for c in catalog['components']}
    def endpoint(token, want):
        inst, dot, _ = token.partition('.')
        if inst in intent['parts'] and not dot:
            return inst + '.' + types[intent['parts'][inst]]['main_path'][want]
        return token
    edges = []
    for pi, path in enumerate(intent.get('paths') or []):
        for k, (a, b) in enumerate(zip(path, path[1:])):
            edges.append({'anchor': 'paths[%d][%d->%d]' % (pi, k, k + 1),
                          'endpoints': [endpoint(a, 'out'), endpoint(b, 'in')],
                          'kind': 'path'})
    for i, tap in enumerate(intent.get('taps') or []):
        edges.append({'anchor': 'taps[%d]' % i, 'endpoints': [tap['sensor'], tap['at']], 'kind': 'tap'})
    nodes = [{'id': inst, 'anchor': 'parts.' + inst, 'type': typ}
             for inst, typ in intent['parts'].items()]
    ports = [{'id': n['id'] + '.' + p['id'], 'component': n['id'],
              'anchor': n['anchor'] + '.ports.' + p['id'],
              'catalog_anchor': n['type'] + '.ports.' + p['id']}
             for n in nodes for p in types[n['type']]['ports']]
    buses = [{'id': bus, 'anchor': 'buses.' + bus[1:],
              'input_anchors': [e['anchor'] for e in edges if bus in e['endpoints']]}
             for bus in sorted({v for e in edges for v in e['endpoints'] if v.startswith('@')})]
    externs = [{'id': name, 'anchor': 'extern.' + name} for name in intent.get('extern', {})]
    return {'schema_version': 1, 'nodes': nodes, 'ports': ports, 'edges': edges,
            'buses': buses, 'externs': externs,
            'assemblies': [{'id':aid,'anchor':'assemblies.'+aid,'label':assembly['label'],
                            'members':assembly['members'],'svg_ids':['assembly-'+aid,'assembly-label-'+aid]}
                           for aid,assembly in (intent.get('assemblies') or {}).items()], 'unknown': intent.get('unknown') or []}


def write_manifest(workdir, intent, catalog, fragments):
    manifest = declared_topology(intent, catalog)
    manifest['fragments'] = fragments
    for item in manifest['nodes']:
        item['svg_ids'] = ['inst-' + item['id']]
    for item in manifest['ports']:
        item['svg_ids'] = ['port-' + item['component'] + '-' + item['id'].split('.',1)[1]]
    for item in manifest['externs']:
        item['svg_ids'] = ['extern-' + item['id']]
    for item in manifest['edges'] + manifest['buses']:
        item['svg_ids'] = [f['id'] for f in fragments if f['anchor'] == item['anchor']]
    target = Path(workdir) / '1#系统原理图-topology'
    target.with_suffix('.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    layout_path=Path(workdir)/'1#系统.layout.json'
    selected=json.loads(layout_path.read_text(encoding='utf-8')).get('nodes',{}) if layout_path.is_file() else {}
    types={c['component_type']:c for c in catalog['components']}
    lines = ['# 输入追溯清单', '',
             '来源使用可解析的 intent 锚点；不推测 YAML 物理行号。母线共享主干不增加逻辑边，跨线桥与折线拆段保留原输入连接。', '',
             '## 连接(边)映射', '',
             '| 输入锚点 | intent 连接 | 图上逻辑边 | 逻辑实例数 | SVG 片段 |',
             '| --- | --- | --- | --- | --- |']
    for item in manifest['edges']:
        lines.append('| `%s` | `%s` | `%s` | 1 | %s |' %
                     (item['anchor'],' ↔ '.join(item['endpoints']),item['anchor'],', '.join(item['svg_ids'])))
    lines += ['', '## 节点(part)映射', '',
              '| 输入锚点 | part 声明 | 图上元件 | 符号形式 |', '| --- | --- | --- | --- |']
    for item in manifest['nodes']:
        symbol=selected.get(item['id'],{}).get('symbol') or types[item['type']].get('symbol',{}).get('asset','未提供')
        lines.append('| `%s` | `%s: %s` | %s | `%s` |' %
                     (item['anchor'],item['id'],item['type'],', '.join(item['svg_ids']),symbol))
    lines += ['', '## 端口 / 母线 / 边界辅助映射', '',
              '| 输入锚点 | 对象 | SVG 图元 |', '| --- | --- | --- |']
    for item in manifest['ports'] + manifest['buses'] + manifest['externs'] + manifest['assemblies']:
        lines.append('| `%s` | `%s` | %s |' % (item['anchor'],item['id'],', '.join(item.get('svg_ids',[]))))
    lines += ['', '## 简化说明 / 未知项', '', '以下未知项只披露，不生成连接；逻辑实例数不按 SVG 片段数累加。', '']
    lines += ['- ' + str(value) for value in manifest['unknown']] or ['- 无声明的未知项。']
    target.with_suffix('.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return manifest


def reconcile_topology(root, geometry, intent, catalog, layout, browser_evidence=None):
    """Rebuild terminal-to-terminal edges from geometry, then compare to input.

    Proper interior crossings stay separate; endpoint incidence creates a T.
    Valid visible bridge arcs join only their own two endpoints. Catalog ports
    stop a trace (we never traverse a component). Bus trunks collapse to @ID.
    data-edge is audited as provenance only, never used to create adjacency.
    """
    from collections import Counter, defaultdict
    import math
    import re
    from sheet_geometry import walk, point, NUMBER, IDENTITY

    expected = declared_topology(intent, catalog)
    findings = []
    def fail(kind, anchor, detail, **context):
        findings.append({'id': 'V10', 'result': 'fail', 'kind': kind,
                         'anchor': anchor, 'detail': detail, **context})
    try:
        elements = list(walk(root))
    except ValueError as error:
        fail('unsupported_geometry', None, str(error))
        return {**expected, 'expected_edges': expected['edges'], 'actual_edges': [],
                'findings': findings, 'coverage_status': 'not_checked'}
    browser_evidence = browser_evidence or {'status':'not_checked','reason':'Browser display evidence unavailable'}
    measured = browser_evidence.get('status') == 'pass'
    browser_rows = {row['key']:row for row in browser_evidence.get('elements',[])}
    element_keys = {el:index for index,(el,_) in enumerate(elements)}
    unchecked = []
    parent = {c: e for e in root.iter() for c in e}
    def check_effects(el, row):
        effects = [row['style']] + [a.get('effects', {}) for a in row.get('ancestors', [])]
        if any(style.get(k, 'none') != 'none' for style in effects
               for k in ('clip-path', 'mask', 'filter')):
            unchecked.append({'svg_id': el.get('id'),
                              'detail': 'Unsupported clipping/mask/filter affects visibility'})
    def visible(el):
        if measured:
            row = browser_rows.get(element_keys[el])
            if row is None:
                unchecked.append({'svg_id':el.get('id'),'detail':'Missing browser element measurement'})
                return False
            style = row['style']
            check_effects(el, row)
            if has_dash_gaps(style.get('stroke-dasharray')) is not False:
                unchecked.append({'svg_id':el.get('id'),'position':row['bbox'],'detail':'Dashed/unresolved stroke cannot certify continuous painted connectivity'})
            width=computed_length(style.get('stroke-width','1'))
            if not row['visible'] or float(style.get('stroke-opacity','1'))<=0 or width==0:
                return False
            if width is None:
                unchecked.append({'svg_id':el.get('id'),'position':row['bbox'],'detail':'Unresolved computed stroke width '+style.get('stroke-width','')})
                return True
            color=color_rgba(style.get('stroke'))
            if color is None:
                unchecked.append({'svg_id':el.get('id'),'detail':'Unsupported stroke paint '+str(style.get('stroke'))})
                return True  # provisional geometry is disclosed as not_checked below
            return (row['visible'] and color[3]>0 and color[:3]!=(255.,255.,255.)
                    and float(style.get('stroke-opacity','1')) > 0 and width > 0)
        while el is not None:
            style = dict(re.findall(r'([\w-]+)\s*:\s*([^;]+)', el.get('style', '')))
            if (style.get('display', el.get('display')) == 'none' or
                style.get('visibility', el.get('visibility')) in ('hidden', 'collapse') or
                style.get('opacity', el.get('opacity', '1')).strip() in ('0', '0.0') or
                style.get('stroke-opacity', el.get('stroke-opacity', '1')).strip() in ('0', '0.0')):
                return False
            el = parent.get(el)
        return True
    by_id = {el.get('id'): el for el, _ in elements if el.get('id')}
    sheet_matrix = next((m for e, m in elements if e.get('id') == 'sheet'), IDENTITY)
    for issue in geometry['issues']:
        fail('unsupported_geometry', None, 'Cannot reconcile: ' + issue['detail'], **{k:v for k,v in issue.items() if k != 'detail'})

    # Identity anchors are checked independently from measured terminal positions.
    for node in expected['nodes']:
        matches = [e for e, _ in elements if e.get('id') == 'inst-' + node['id']]
        if len(matches) != 1 or matches[0].get('data-node') != node['id'] or matches[0].get('data-input-anchor') != node['anchor']:
            fail('node_anchor', node['anchor'], 'Missing/duplicate/invalid node anchor ' + node['id'], component=node['id'])
    for port in expected['ports']:
        inst, pid = port['component'], port['id'].split('.',1)[1]
        matches = [(e,m) for e,m in elements if e.tag.rsplit('}',1)[-1] == 'metadata' and e.get('data-port') == port['id']]
        source = geometry['nodes'].get(inst,{}).get('ports',{}).get(pid)
        valid = len(matches) == 1 and source is not None
        if valid:
            el, matrix = matches[0]
            try:
                position = point(matrix,(float(el.get('data-x')),float(el.get('data-y'))))
                valid = (el.get('data-node') == inst and el.get('data-port-id') == pid and
                         el.get('data-input-anchor') == port['anchor'] and
                         el.get('id') == 'port-' + inst + '-' + pid and
                         parent.get(el) is by_id.get('inst-' + inst) and
                         math.dist(position,source['position']) <= .1)
            except (ValueError,TypeError):
                valid = False
        if not valid:
            fail('port_anchor', port['anchor'], 'Missing/duplicate/invalid port anchor ' + port['id'], component=inst,port=pid)
    node_ids = {n['id'] for n in expected['nodes']}
    port_ids = {p['id'] for p in expected['ports']}
    for el,_ in elements:
        if el.get('data-node') and el.get('data-node') not in node_ids:
            fail('unresolved_node_anchor',el.get('data-input-anchor'),'Node anchor refers to no input: ' + el.get('data-node'))
        if el.tag.rsplit('}',1)[-1] == 'metadata' and el.get('data-port') is not None and el.get('data-port') not in port_ids:
            fail('unresolved_port_anchor',el.get('data-input-anchor'),'Port anchor refers to no input: ' + str(el.get('data-port')))
    valid_anchors = {e['anchor'] for e in expected['edges'] + expected['buses']}
    seen_ids = Counter(e.get('id') for e, _ in elements if e.get('id'))
    segments, positions = [], []
    def vertex(xy):
        xy = tuple(xy)
        for i, old in enumerate(positions):
            if math.dist(old, xy) <= .1:
                return i
        positions.append(xy)
        return len(positions) - 1
    def add_segment(a, b, sid, anchor=None, bridge=False):
        va, vb = vertex(a), vertex(b)
        if va != vb:
            segments.append({'a': va, 'b': vb, 'svg_id': sid, 'anchor': anchor, 'bridge': bridge})
    pipes = list(geometry['pipes'])
    for el,matrix in elements:
        ancestor=parent.get(el); in_lines=False
        while ancestor is not None:
            if ancestor.get('id') == 'lines': in_lines=True; break
            ancestor=parent.get(ancestor)
        if not in_lines or any(c.startswith('ln-') for c in el.get('class','').split()):
            continue
        tag=el.tag.rsplit('}',1)[-1]
        if tag not in ('line','polyline','path','polygon','rect','circle','ellipse','use') or not visible(el):
            continue
        try:
            if tag == 'line':
                pts=[(float(el.get('x'+n)),float(el.get('y'+n))) for n in ('1','2')]
            elif tag == 'polyline':
                nums=[float(v) for v in re.findall(NUMBER,el.get('points',''))]
                pts=list(zip(nums[::2],nums[1::2]))
            else:
                raise ValueError('Unsupported additional pipe element ' + tag)
            pipes.append({'svg_id':el.get('id'),'class':el.get('class',''),
                          'points':[point(matrix,p) for p in pts]})
        except (TypeError,ValueError) as error:
            fail('unsupported_geometry',el.get('data-input-anchor'),str(error),svg_id=el.get('id'))
            unchecked.append({'svg_id':el.get('id'),'detail':str(error)})
    for pipe in pipes:
        sid = pipe['svg_id']
        el = by_id.get(sid)
        # Anonymous pipes remain actual geometry; absent IDs must not hide additions.
        if el is None:
            el = next((e for e, _ in elements if e.get('class') == pipe['class'] and not e.get('id')), None)
        if el is not None and not visible(el):
            continue
        anchor = el.get('data-input-anchor') if el is not None else None
        claim = el.get('data-edge') if el is not None else None
        if (anchor not in valid_anchors or (not anchor.startswith('buses.') and claim != anchor)
                or (anchor.startswith('buses.') and el.get('data-bus') != '@' + anchor[6:])):
            fail('edge_anchor', anchor, 'Missing or unresolved input anchor for pipe ' + str(sid), svg_id=sid)
        if not sid or seen_ids[sid] != 1:
            fail('duplicate_or_missing_anchor', anchor, 'Pipe SVG ID is missing or duplicated: ' + str(sid), svg_id=sid)
        pts = pipe['points']
        row = browser_rows.get(element_keys.get(el)) if el is not None else None
        if row:
            attrs = row['attrs']
            if row['tag'] == 'polyline':
                values=[float(v) for v in re.findall(NUMBER,attrs.get('points',''))]
                pts=[point(row['matrix'],xy) for xy in zip(values[::2],values[1::2])]
            elif row['tag'] == 'line':
                pts=[point(row['matrix'],(float(attrs['x'+n]),float(attrs['y'+n]))) for n in ('1','2')]
        for a, b in zip(pts, pts[1:]):
            add_segment(a, b, sid, anchor)
    bridge_records = []
    for el, matrix in elements:
        ancestors = []; ancestor = el
        while ancestor is not None:
            ancestors.append(ancestor.get('id')); ancestor = parent.get(ancestor)
        if 'legend' in ancestors or 'symbols' in ancestors:
            continue
        if not any(c.startswith('brg-') for c in el.get('class', '').split()) or not visible(el):
            continue
        # The renderer's single circular half-arc is an independently parsed path.
        if el.get('data-edge') not in valid_anchors or el.get('data-input-anchor') != el.get('data-edge') or not el.get('id') or seen_ids[el.get('id')] != 1:
            fail('edge_anchor',el.get('data-edge'),'Missing/duplicate/unresolved bridge anchor',svg_id=el.get('id'))
        match = re.fullmatch(r'\s*M\s*(' + NUMBER + r')[ ,]+(' + NUMBER + r')\s*A\s*(' + NUMBER + r')[ ,]+(' + NUMBER + r')[ ,]+0[ ,]+0[ ,]+[01][ ,]+(' + NUMBER + r')[ ,]+(' + NUMBER + r')\s*', el.get('d', ''))
        if not match:
            fail('unsupported_bridge', el.get('data-edge'), 'Unsupported visible bridge geometry', svg_id=el.get('id'))
            continue
        x1, y1, rx, ry, x2, y2 = map(float, match.groups())
        if abs(y1-y2) > .1 or abs(abs(x2-x1)-2*rx) > .1 or abs(rx-ry) > .1:
            fail('unsupported_bridge', el.get('data-edge'), 'Bridge is not a continuous semicircle', svg_id=el.get('id'))
            continue
        matrix = browser_rows.get(element_keys[el],{}).get('matrix',matrix)
        a, b = point(matrix, (x1, y1)), point(matrix, (x2, y2))
        add_segment(a, b, el.get('id'), el.get('data-edge'), True)
        bridge_records.append({'svg_id': el.get('id'), 'position': point(matrix, ((x1+x2)/2, y1)),
                               'endpoints': [a,b], 'anchor': el.get('data-edge')})

    # A real same-network crossing is a semantic branch even when it occurs
    # inside two stored straight segments. Marker circles never create vertices.
    from junction_semantics import input_networks, intersection_events
    crossings = intersection_events([
        {'start':positions[s['a']],'end':positions[s['b']],'anchor':s['anchor']}
        for s in segments if not s['bridge']], input_networks(expected))
    for event in crossings:
        if event['kind']=='junction':
            vertex(event['position'])

    labels = defaultdict(set)
    for inst, node in geometry['nodes'].items():
        instance=by_id.get('inst-' + inst)
        row=browser_rows.get(element_keys.get(instance),{})
        if row and not row['visible']:
            fail('hidden_node','parts.' + inst,'Component is not visible: ' + inst,component=inst)
            continue
        if row:
            check_effects(instance, row)
            # Chrome stores SVG matrices at float32 precision. Compare actual
            # terminal displacement in the same 0.1-unit rounding tolerance,
            # not raw coefficient equality (which misflags valid rotations).
            a,b,c,d,e,f = node['matrix']
            det=a*d-b*c
            inverse=(d/det,-b/det,-c/det,a/det,(c*f-d*e)/det,(b*e-a*f)/det)
            if any(math.dist(point(row['matrix'],point(inverse,port['position'])),port['position']) > .1
                   for port in node['ports'].values()):
                unchecked.append({'component':inst,'detail':'CSS instance transform is outside normalized port geometry'})
        for pid, port in node['ports'].items():
            labels[vertex(port['position'])].add(inst + '.' + pid)
    for ext in expected['externs']:
        markers = [(e,m) for e,m in elements if e.get('data-extern') == ext['id'] and visible(e)]
        if len(markers) != 1:
            fail('extern_anchor', ext['anchor'], 'Missing/duplicate external terminal ' + ext['id'])
            continue
        el, matrix = markers[0]
        nums = [float(v) for v in re.findall(NUMBER, el.get('d',''))]
        if len(nums) != 6:
            fail('extern_geometry', ext['anchor'], 'Unsupported external marker ' + ext['id'])
            continue
        matrix = browser_rows.get(element_keys[el],{}).get('matrix',matrix)
        labels[vertex(point(matrix, nums[2:4]))].add(ext['id'])

    def on_segment(p, a, b):
        length = math.dist(a,b)
        return length > 0 and abs((p[0]-a[0])*(b[1]-a[1])-(p[1]-a[1])*(b[0]-a[0])) / length <= .1 and all(min(a[k],b[k])-.1 <= p[k] <= max(a[k],b[k])+.1 for k in (0,1))
    # Bus identity comes from the declared corridor transformed with the sheet,
    # then from visible collinear trunk geometry, never from data-bus alone.
    bus_vertices = defaultdict(set)
    for bus in expected['buses']:
        name = bus['id'][1:]
        if name not in layout.get('buses', {}):
            fail('missing_bus', bus['anchor'], 'Missing declared bus corridor ' + bus['id'])
            continue
        x = layout['buses'][name]['x']
        a, b = point(sheet_matrix,(x,0)), point(sheet_matrix,(x,layout['canvas']['height']))
        trunks = [s for s in segments if s['anchor'] == bus['anchor'] and not s['bridge'] and
                  on_segment(positions[s['a']],a,b) and on_segment(positions[s['b']],a,b)]
        for s in trunks:
            for v, pos in enumerate(positions):
                if on_segment(pos, positions[s['a']], positions[s['b']]):
                    bus_vertices[bus['id']].add(v)
        # A one-branch bus has a degenerate (zero-length) trunk. Its actual
        # branch endpoint must still meet the declared corridor.
        if not trunks and len(bus['input_anchors']) == 1:
            for s in segments:
                for v in (s['a'],s['b']):
                    if on_segment(positions[v],a,b):
                        bus_vertices[bus['id']].add(v)
        if not bus_vertices[bus['id']]:
            fail('missing_bus', bus['anchor'], 'No visible bus geometry for ' + bus['id'])
        for v in bus_vertices[bus['id']]:
            labels[v].add(bus['id'])

    # Split straight segments at all actual endpoints/ports (including T joins),
    # not at an unmarked proper crossing. Bridge chords are never split.
    graph = defaultdict(list)
    atomic = []
    for s in segments:
        a, b = positions[s['a']], positions[s['b']]
        vs = [s['a'],s['b']] if s['bridge'] else sorted(
            [i for i,p in enumerate(positions) if on_segment(p,a,b)], key=lambda i: math.dist(a,positions[i]))
        for u,v in zip(vs,vs[1:]):
            idx=len(atomic)
            atomic.append({**s,'a':u,'b':v})
            graph[u].append((v,idx)); graph[v].append((u,idx))
    for bus in expected['buses']:
        edges = [s for s in atomic if s['anchor'] == bus['anchor']]
        adjacency = defaultdict(set)
        for seg in edges:
            adjacency[seg['a']].add(seg['b']); adjacency[seg['b']].add(seg['a'])
        pending = set(adjacency); count = 0
        while pending:
            count += 1; todo = [pending.pop()]; component = set(todo)
            while todo:
                for n in adjacency[todo.pop()] - component:
                    component.add(n); pending.discard(n); todo.append(n)
        if count > 1:
            fail('disconnected_bus',bus['anchor'],'Visible bus trunk is disconnected: ' + bus['id'])
    # Reconstruct each claimed fragment group geometrically. An anchor associates
    # fragments with an input definition; its alleged endpoints are never trusted.
    # Every group's actual terminal contacts and continuity must prove that claim.
    actual = []
    groups = defaultdict(list)
    for i, segment in enumerate(atomic):
        groups[segment['anchor']].append(i)
    for edge in expected['edges']:
        anchor = edge['anchor']
        indexes = groups.get(anchor, [])
        if not indexes:
            fail('missing_connection', anchor, 'Missing actual connection ' + ' ↔ '.join(edge['endpoints']), endpoints=edge['endpoints'])
            continue
        adjacency = defaultdict(set)
        duplicates = Counter()
        for i in indexes:
            seg = atomic[i]; u,v = seg['a'],seg['b']
            adjacency[u].add(v); adjacency[v].add(u)
            duplicates[tuple(sorted((u,v)))]+=1
        pending = set(adjacency); components = []
        while pending:
            todo = [pending.pop()]; component=set(todo)
            while todo:
                for n in adjacency[todo.pop()] - component:
                    component.add(n); pending.discard(n); todo.append(n)
            components.append(component)
        for component in components:
            contacts = sorted({terminal for v in component for terminal in labels[v]})
            ends = [v for v in component if len(adjacency[v]) == 1]
            unattached = [positions[v] for v in ends if not labels[v]]
            record = {'anchor':anchor, 'endpoints':contacts,
                      'svg_ids':sorted({atomic[i]['svg_id'] or '' for i in indexes}),
                      'positions':[positions[v] for v in ends],
                      'segments':[i for i in indexes if atomic[i]['a'] in component]}
            actual.append(record)
            if set(contacts) != set(edge['endpoints']) or unattached or len(components) != 1:
                fail('additional_or_wrong_connection', anchor,
                     'Actual endpoints disagree with input %s: %s (unattached %s)' % (anchor, contacts, unattached),
                     expected_endpoints=edge['endpoints'], actual_endpoints=contacts,
                     positions=record['positions'], svg_ids=record['svg_ids'])
        if any(count > 1 for count in duplicates.values()):
            fail('duplicate_connection_geometry', anchor, 'Repeated visible segment within ' + anchor,
                 svg_ids=sorted({atomic[i]['svg_id'] or '' for i in indexes}))

    # Whole-sheet adjacency independently detects accidental joins between groups.
    # A shared trunk may represent several edges; connectivity is compared after
    # merging input edges into terminal nets, without adding component internals.
    expected_parent = {}
    def leader(item):
        expected_parent.setdefault(item,item)
        while expected_parent[item] != item:
            item = expected_parent[item]
        return item
    for edge in expected['edges']:
        a,b = edge['endpoints']; expected_parent[leader(a)]=leader(b)
    pending = set(graph)
    networks = []
    while pending:
        todo=[pending.pop()]; component=set(todo)
        while todo:
            for n,_ in graph[todo.pop()]:
                if n not in component:
                    component.add(n);pending.discard(n);todo.append(n)
        contacts=sorted({terminal for v in component for terminal in labels[v]})
        indexes=sorted({i for v in component for _,i in graph[v]})
        anchors=sorted({atomic[i]['anchor'] for i in indexes if atomic[i]['anchor']})
        networks.append({'terminals':contacts,'anchors':anchors,'segments':indexes})
        if len({leader(p) for p in contacts}) > 1:
            fail('wrong_network_join', next((a for a in anchors if not a.startswith('buses.')), None),
                 'Visible geometry joins separate input networks: ' + ', '.join(contacts),
                 endpoints=contacts, input_anchors=anchors)
        if not contacts or not anchors:
            fail('unaccounted_geometry', anchors[0] if anchors else None,
                 'Visible geometry has no declared terminal connection',
                 position=positions[min(component)],svg_ids=sorted({atomic[i]['svg_id'] or '' for i in indexes}))
    return {**expected, 'coordinate_system':'root_svg_user_units', 'endpoint_tolerance':.1,
            'expected_edges':expected['edges'], 'actual_edges':actual,
            'segments':[{**s,'start':positions[s['a']],'end':positions[s['b']]} for s in atomic],
            'vertices':[{'position':p,'terminals':sorted(labels[i]),'degree':len({n for n,_ in graph[i]})} for i,p in enumerate(positions)],
            'bridges':bridge_records,'networks':networks,'findings':findings,
            'display_evidence':{'status':browser_evidence['status'],'reason':browser_evidence.get('reason'),'unchecked':unchecked},
            'coverage_status':'pass' if measured and not geometry['issues'] and not unchecked else 'not_checked'}
