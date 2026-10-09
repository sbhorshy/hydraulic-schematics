"""Independent displayed-width checks against source ports and lead boundaries."""
import math
import re
import xml.etree.ElementTree as ET
from browser_evidence import collect
from lead_geometry import segments, source_leads, perpendicular_scale
from sheet_geometry import point, walk
from svg_paint import color_rgba, has_dash_gaps, computed_length

POSITION_TOLERANCE = .1  # the existing SVG coordinate serialization allowance
WIDTH_TOLERANCE = .02  # SVG units; no tolerance is added for a visible gap
RATIOS = {'pressure':3., 'return':1., 'suction':1., 'case_drain':1., 'sense':1.}


def _class(row, prefix):
    for entry in [row['attrs']] + [a['attrs'] for a in row.get('ancestors', [])]:
        found = next((c[len(prefix):] for c in entry.get('class','').split() if c.startswith(prefix)), None)
        if found:
            return found
    return None


def _visible_stroke(row):
    if not row.get('visible') or float(row['style'].get('stroke-opacity','1')) <= 0:
        return False
    if computed_length(row['style'].get('stroke-width'))==0:return False
    color=color_rgba(row['style']['stroke'])
    if color is None:return None
    return color[3]>0 and color[:3]!=(255.,255.,255.)


def _overlap(a,b,c,d):
    """Projected overlap on AB, only for a coincident straight segment CD."""
    length = math.dist(a,b)
    ux,uy = (b[0]-a[0])/length,(b[1]-a[1])/length
    if any(abs((p[0]-a[0])*uy-(p[1]-a[1])*ux)>POSITION_TOLERANCE for p in (c,d)):
        return None
    lo,hi = sorted((sum((p[i]-a[i])*v for i,v in enumerate((ux,uy))) for p in (c,d)))
    lo,hi = max(0.,lo), min(length,hi)
    return (lo,hi) if hi-lo > POSITION_TOLERANCE else None


def _on_segment(p,a,b):
    length = math.dist(a,b)
    ux,uy = (b[0]-a[0])/length,(b[1]-a[1])/length
    along = (p[0]-a[0])*ux + (p[1]-a[1])*uy
    normal = abs((p[0]-a[0])*uy - (p[1]-a[1])*ux)
    return normal <= POSITION_TOLERANCE and -POSITION_TOLERANCE <= along <= length+POSITION_TOLERANCE


def check_widths(svg_path, layout, geometry, resolve_symbol, browser=None):
    browser = browser if browser is not None else collect(svg_path)
    ev15 = {'id':'V15', 'base_T':float(layout.get('style',{}).get('base_line_width_T',1)),
            'allowed_T':{'high':3.,'low':1.,'symbol':1.5}, 'measurements':[]}
    ev16 = {'id':'V16', 'scheme':'A: body/internal mechanisms retain 1.5T; external leads follow network',
            'measurements':[], 'unchecked':[], 'position_tolerance':POSITION_TOLERANCE,
            'width_tolerance':WIDTH_TOLERANCE, 'browser_evidence':'browser-evidence.json'}
    failures = []
    if browser.get('status') != 'pass':
        reason = browser.get('reason','Browser evidence unavailable')
        for ev in (ev15,ev16):
            ev.update(coverage_status='not_checked',coverage_detail=reason)
        return failures,[ev15,ev16]
    rows = browser['elements']
    ev15['browser_evidence'] = ev16['browser_evidence']
    ev16['svg_sha256'] = browser['svg_sha256']
    ev16['unchecked'].extend({'component':inst,'reason':'Normalized source ports unavailable'}
                             for inst in layout['nodes'] if inst not in geometry['nodes'])
    actual, pipes = [], []
    external_keys = set()
    for row in rows:
        cls = _class(row,'ln-')
        if not row.get('instance') and not cls:
            continue
        if row.get('visible') and row['attrs'].get('data-interface-port') and row['tag'] not in ('line','path','polyline'):
            ev16['unchecked'].append({'component':row.get('instance'),'port':row['attrs']['data-interface-port'],
                                      'element':row['id'] or row['key'],'position':row['bbox'],
                                      'reason':'Unsupported external lead element '+row['tag']})
            continue
        paint = _visible_stroke(row)
        if paint is None:
            if cls or row['attrs'].get('data-interface-port') or _class(row,'pl-'):
                ev16['unchecked'].append({'component':row.get('instance'),'port':row['attrs'].get('data-interface-port'),
                                          'element':row.get('id') or row['key'],'reason':'Unsupported stroke paint '+row['style']['stroke'],
                                          'position':row['bbox']})
            continue
        if not paint:
            if cls or row['attrs'].get('data-interface-port') or _class(row,'pl-'):
                failures.append(('V15','%s %s has no visible stroke @%s' %
                                 (row.get('instance') or '',row.get('id') or row['key'],row['bbox'])))
            continue
        if row['style'].get('vector-effect') == 'non-scaling-stroke':
            failures.append(('V15','%s non-scaling-stroke keeps device width when the sheet is enlarged @%s' %
                             (row.get('id') or row['key'],row['bbox'])))
        try:
            parts = segments(row['tag'],row['attrs'])
            width=computed_length(row['style']['stroke-width'])
            if width is None:raise ValueError('Unresolved computed stroke width '+row['style']['stroke-width'])
            for a,b in parts:
                effective = width * perpendicular_scale(row['matrix'],(b[0]-a[0],b[1]-a[1]))
                if row['style'].get('vector-effect') == 'non-scaling-stroke':
                    effective = width
                item = {'row':row,'a':point(row['matrix'],a),'b':point(row['matrix'],b),'width':effective}
                actual.append(item)
                if cls in RATIOS:
                    item['class'] = cls
                    pipes.append(item)
                    dashed=has_dash_gaps(row['style'].get('stroke-dasharray'))
                    if dashed:
                        failures.append(('V15','%s %s pipe uses a dashed stroke where continuous ink is required @%s' % (row.get('id') or row['key'],cls,item['a'])))
                    elif dashed is None:
                        ev16['unchecked'].append({'element':row.get('id') or row['key'],'position':item['a'],'reason':'Unresolved network dash lengths'})
                    expected = RATIOS[cls]*ev15['base_T']
                    measurement = {'element':row.get('id') or row['key'], 'class':cls,'position':item['a'],
                                   'effective_width':effective, 'expected_width':expected}
                    ev15['measurements'].append(measurement)
                    if abs(effective-expected)>WIDTH_TOLERANCE:
                        failures.append(('V15','%s %s pipe effective width %.3f != %.3f @%s' %
                                         (measurement['element'],cls,effective,expected,item['a'])))
        except (ValueError,TypeError) as error:
            ports = geometry['nodes'].get(row.get('instance'),{}).get('ports',{})
            matched = [pid for pid,p in ports.items() if
                       any(math.dist(p['position'],q)<=POSITION_TOLERANCE for q in row.get('endpoints',[]))]
            pid = row['attrs'].get('data-interface-port')
            if cls or pid or _class(row,'pl-') or matched:
                for port in matched or [pid]:
                    ev16['unchecked'].append({'component':row.get('instance'),'port':port,
                                              'element':row.get('id') or row['key'], 'reason':str(error),
                                              'position':row['bbox']})
    for inst,node in geometry['nodes'].items():
        source = ET.parse(resolve_symbol(node['symbol'])).getroot()
        source_ports = {}
        for el,matrix in walk(source):
            if el.get('data-port-id'):
                source_ports[el.get('data-port-id')] = point(matrix,(float(el.get('cx')),float(el.get('cy'))))
        leads,unsupported = source_leads(source,source_ports)
        ev16['unchecked'].extend(dict(component=inst,position=node['ports'].get(u.get('port'),{}).get('position'),**u)
                                 for u in unsupported)
        for lead in leads:
            pid = lead['port']
            port = node['ports'].get(pid)
            if not port:
                continue
            position = port['position']
            permitted = [(point(node['matrix'],a),point(node['matrix'],b)) for a,b in lead['segments']]
            # Source geometry owns this role even if the attached network's paint
            # or width is unavailable; such a lead must not become a body stroke.
            external_keys.update(item['row']['key'] for item in actual if item['row'].get('instance')==inst
                                 and any(_overlap(a,b,item['a'],item['b']) for a,b in permitted))
            if any(u.get('component') == inst and u.get('port') == pid for u in ev16['unchecked']):
                continue
            touching = [p for p in pipes if any(math.dist(q,position)<=POSITION_TOLERANCE for q in (p['a'],p['b']))]
            if not touching:
                continue  # an unconnected port has no network-width requirement (V3 owns missing connections)
            classes = {p['class'] for p in touching}
            if len({RATIOS[c] for c in classes}) != 1:
                failures.append(('V16','%s.%s incompatible network widths at %s' % (inst,pid,position)))
                continue
            expected = RATIOS[next(iter(classes))]*ev15['base_T']
            measurement = {'component':inst,'port':pid,'position':position,'class':sorted(classes),
                           'boundary':[], 'expected_width':expected,'effective_width':None,'segments':[]}
            unchecked = False
            used_keys = set()
            for local_a,local_b in lead['segments']:
                a,b = point(node['matrix'],local_a),point(node['matrix'],local_b)
                matches = []
                for item in actual:
                    if item['row'].get('instance') != inst:
                        continue
                    span = _overlap(a,b,item['a'],item['b'])
                    if span:
                        matches.append((span,item))
                        used_keys.add(item['row']['key'])
                        external_keys.add(item['row']['key'])
                        for endpoint in (item['a'],item['b']):
                            if not any(_on_segment(endpoint,pa,pb) for pa,pb in permitted):
                                failures.append(('V16','%s.%s lead extends beyond the defined port/body boundary @%s' %
                                                 (inst,pid,endpoint)))
                length = math.dist(a,b)
                cuts = sorted({0.,length,*[v for span,_item in matches for v in span]})
                for lo,hi in zip(cuts,cuts[1:]):
                    if hi-lo<=POSITION_TOLERANCE:
                        continue
                    middle = (lo+hi)/2
                    seen = [item for span,item in matches if span[0]<=middle<=span[1]]
                    location = [a[i]+(b[i]-a[i])*middle/length for i in range(2)]
                    if not seen:
                        failures.append(('V16','%s.%s missing external lead between port and defined body boundary @%s' % (inst,pid,location)))
                        continue
                    for item in seen:
                        row = item['row']
                        dashed=has_dash_gaps(row['style'].get('stroke-dasharray'))
                        if dashed:
                            failures.append(('V16','%s.%s dashed external lead cannot provide continuous ink to the body boundary @%s' % (inst,pid,location)))
                        elif dashed is None:
                            ev16['unchecked'].append({'component':inst,'port':pid,'position':location,'reason':'Unresolved external lead dash lengths'})
                            unchecked=True
                        if any(effects.get(k,'none') != 'none' for effects in
                               [row['style']] + [a.get('effects',{}) for a in row.get('ancestors',[])]
                               for k in ('clip-path','mask','filter')):
                            ev16['unchecked'].append({'component':inst,'port':pid,'element':row['id'] or row['key'],
                                                      'position':location,'reason':'clipped/masked/filtered lead requires pixel measurement'})
                            unchecked = True
                        segment = {'element':row['id'] or row['key'],'position':location,
                                   'effective_width':item['width'],'expected_width':expected}
                        measurement['segments'].append(segment)
                        ev15['measurements'].append(dict(segment,component=inst,port=pid,kind='external_lead'))
                        standards=[value*ev15['base_T'] for value in ev15['allowed_T'].values()]
                        if not any(abs(item['width']-value)<=WIDTH_TOLERANCE for value in standards):
                            failures.append(('V15','%s.%s effective external lead width %.3f is outside standard widths %s @%s' %
                                             (inst,pid,item['width'],[round(v,4) for v in standards],location)))
                        if abs(item['width']-expected)>WIDTH_TOLERANCE:
                            failures.append(('V16','%s.%s %s effective lead width %.3f != network %.3f @%s; width may change only at the defined body boundary' %
                                             (inst,pid,segment['element'],item['width'],expected,location)))
            if measurement['segments']:
                measurement['effective_width'] = measurement['segments'][0]['effective_width']
            # Only source-defined terminal points can be transitions to the body.
            terminals = []
            for seg in lead['segments']:
                for p in seg:
                    count = sum(math.dist(p,q)<POSITION_TOLERANCE for s in lead['segments'] for q in s)
                    if count==1 and math.dist(point(node['matrix'],p),position)>POSITION_TOLERANCE:
                        terminals.append(point(node['matrix'],p))
            measurement['boundary'] = terminals
            for terminal in terminals:
                contacts = []
                for row in rows:
                    if row.get('instance') != inst or row['key'] not in used_keys:
                        continue
                    for endpoint, hits in zip(row.get('endpoints',[]),row.get('endpoint_contacts',[])):
                        if math.dist(endpoint,terminal)<=POSITION_TOLERANCE:
                            contacts.extend(k for k in hits if k not in used_keys)
                if not contacts:
                    # Multi-subpath paths may terminate at their first subpath's start;
                    # browser endpoints are first/last, so lack of evidence stays explicit.
                    ev16['unchecked'].append({'component':inst,'port':pid,'position':terminal,
                                              'reason':'No independent browser body contact at the source-defined transition'})
                    unchecked = True
            measurement['status'] = 'not_checked' if unchecked else 'measured'
            ev16['measurements'].append(measurement)
    # Painted bodies/internal mechanisms are a separate role from external leads.
    # Solid fills (arrows, hatching) do not create a stroke-width requirement.
    for row in rows:
        if (not row.get('instance') or row['tag'] not in ('line','path','polyline','polygon','rect','circle','ellipse')
                or row['key'] in external_keys):
            continue
        pid=row['attrs'].get('data-interface-port')
        if pid and any(u.get('component')==row['instance'] and u.get('port')==pid for u in ev16['unchecked']):
            continue  # An explicitly unmeasured interface is not relabeled as body.
        paint=_visible_stroke(row)
        if paint is False:continue
        width=computed_length(row['style']['stroke-width'])
        effects=any(style.get(k,'none')!='none' for style in
                    [row['style']]+[a.get('effects',{}) for a in row.get('ancestors',[])] for k in ('clip-path','mask','filter'))
        reason=None
        if paint is None or width is None or effects:
            reason='Body stroke paint/width/display effect needs additional measurement'
        else:
            try:
                parts=segments(row['tag'],row['attrs'])
                factors=[perpendicular_scale(row['matrix'],(b[0]-a[0],b[1]-a[1])) for a,b in parts]
            except ValueError:
                a,b,c,d,_,_=row['matrix']
                if abs(a*a+b*b-c*c-d*d)<1e-7 and abs(a*c+b*d)<1e-7:
                    factors=[math.hypot(a,b)]
                elif row['tag'] in ('circle','ellipse','rect'):
                    trace=a*a+b*b+c*c+d*d;disc=math.sqrt(max(0.,trace*trace-4*(a*d-b*c)**2))
                    factors=[math.sqrt(max(0.,(trace-disc)/2)),math.sqrt((trace+disc)/2)]
                else:
                    reason='Curved body under nonuniform transform requires additional directional width evidence'
            if not reason:
                widths=[width*f for f in factors]
                expected=1.5*ev15['base_T']
                ev15['measurements'].append({'component':row['instance'],'element':row['id'] or row['key'],
                                             'kind':'symbol_body','position':row['bbox'],'effective_widths':widths,'expected_width':expected})
                if any(abs(value-expected)>WIDTH_TOLERANCE for value in widths):
                    failures.append(('V15','%s %s body/internal effective widths %s != prescribed %.3f @%s' %
                                     (row['instance'],row['id'] or row['key'],[round(v,4) for v in widths],expected,row['bbox'])))
        if reason:
            ev16['unchecked'].append({'component':row['instance'],'element':row['id'] or row['key'],
                                      'position':row['bbox'],'reason':reason})
    ev15.update(coverage_status='not_checked' if ev16['unchecked'] else 'pass',
                coverage_detail='Computed network/lead widths in root SVG units; symbol body styling is preserved.')
    ev16.update(coverage_status='not_checked' if ev16['unchecked'] else 'pass',
                coverage_detail='Browser-computed strokes across complete source-defined external leads and body contacts.'
                if not ev16['unchecked'] else '%d displayed lead measurements lack complete evidence.' % len(ev16['unchecked']))
    return list(dict.fromkeys(failures)),[ev15,ev16]
