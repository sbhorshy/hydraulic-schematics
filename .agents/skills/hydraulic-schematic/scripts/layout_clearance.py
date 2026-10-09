"""Composition budgets from final root-SVG geometry, never layout rectangles.

measure_runs joins storage-only collinear cuts within each logical input edge.
Ports, branches, real bends/reversals and bridge boundaries remain semantic ends.
"""
from collections import defaultdict
import math

from endpoint_checks import ENDPOINT_TOLERANCE


def measure_runs(geometry, topology):
    vertices=topology.get('vertices',[])
    segments=topology.get('segments',[])
    positions=[v['position'] for v in vertices]
    protected={i for i,v in enumerate(vertices) if v['terminals'] or v['degree'] != 2}
    # A retraced segment has one physical neighbour but two ordered incidences.
    # Preserve the actual reversal vertices before normalizing duplicate ink.
    visible_ids={segment['svg_id'] for segment in segments}
    for pipe in geometry['pipes']:
        if pipe['svg_id'] not in visible_ids: continue
        for a,b,c in zip(pipe['points'],pipe['points'][1:],pipe['points'][2:]):
            u=(b[0]-a[0],b[1]-a[1]); v=(c[0]-b[0],c[1]-b[1])
            if u[0]*v[0]+u[1]*v[1] < 0:
                protected.update(i for i,p in enumerate(positions) if math.dist(p,b) <= ENDPOINT_TOLERANCE)
    groups=defaultdict(dict)
    for segment in segments:
        if segment['bridge']:
            protected.update((segment['a'],segment['b']))
            continue
        key=tuple(sorted((segment['a'],segment['b'])))
        groups[segment['anchor']].setdefault(key,set()).add(segment['svg_id'])
    runs=[]
    for anchor,edges in groups.items():
        neighbours=defaultdict(set)
        for a,b in edges:
            neighbours[a].add(b); neighbours[b].add(a)
        stops=set(protected)
        for vertex,adjacent in neighbours.items():
            if len(adjacent) != 2:
                stops.add(vertex); continue
            a,c=[positions[n] for n in adjacent]; b=positions[vertex]
            u=(a[0]-b[0],a[1]-b[1]); v=(c[0]-b[0],c[1]-b[1])
            length=max(math.hypot(*u),math.hypot(*v))
            if (u[0]*v[0]+u[1]*v[1] >= 0 or
                abs(u[0]*v[1]-u[1]*v[0]) > ENDPOINT_TOLERANCE*length):
                stops.add(vertex)
        used=set()
        for start in sorted(stops & neighbours.keys()) + sorted(neighbours.keys()-stops):
            for nxt in sorted(neighbours[start]):
                key=tuple(sorted((start,nxt)))
                if key in used: continue
                path=[start,nxt]; ids=set(edges[key]); used.add(key)
                while path[-1] not in stops:
                    following=neighbours[path[-1]]-{path[-2]}
                    if len(following) != 1: break
                    end=next(iter(following)); key=tuple(sorted((path[-1],end)))
                    if key in used: break
                    path.append(end); used.add(key); ids.update(edges[key])
                points=[positions[i] for i in path]
                runs.append({'anchor':anchor,'start':points[0],'end':points[-1],
                             'length':sum(math.dist(a,b) for a,b in zip(points,points[1:])),
                             'svg_ids':sorted(i for i in ids if i), 'vertices':path})
    return runs


def box_gap(first, second):
    """Shortest Euclidean gap and witness points for two axis-aligned footprints."""
    a,b=[],[]
    for axis in (0,1):
        if first[axis+2] < second[axis]:
            a.append(first[axis+2]);b.append(second[axis])
        elif second[axis+2] < first[axis]:
            a.append(first[axis]);b.append(second[axis+2])
        else:
            value=max(first[axis],second[axis]);a.append(value);b.append(value)
    return math.dist(a,b),[a,b]


def nearest_components(geometry):
    nodes=sorted(geometry['nodes'].items())
    measured=[]
    for i,(name,a) in enumerate(nodes):
        for other,b in nodes[i+1:]:
            distance,positions=box_gap(a['footprint'],b['footprint'])
            measured.append({'components':[name,other],'distance':distance,
                             'positions':positions,'footprints':[a['footprint'],b['footprint']]})
    return min(measured,key=lambda pair:pair['distance']) if measured else None


def measure_corridors(geometry, topology, runs, budget, browser=None):
    declared={edge['anchor']:set(edge['endpoints']) for edge in topology['expected_edges']}
    measured,exemptions,unchecked=[],[],[]
    browser_rows={row['id']:row for row in (browser or {}).get('elements',[]) if row['id']}
    for bridge in topology.get('bridges',[]):
        row=browser_rows.get(bridge['svg_id'])
        if not row or not row['visible']:
            unchecked.append({'anchor':bridge['anchor'],'svg_id':bridge['svg_id'],
                              'detail':'Missing measured bridge geometry'})
            continue
        for inst,node in geometry['nodes'].items():
            try:
                distance,positions=bridge_gap(bridge,row,node['footprint'])
            except ValueError as error:
                unchecked.append({'anchor':bridge['anchor'],'svg_id':bridge['svg_id'],'detail':str(error)})
                break
            measured.append({'component':inst,'anchor':bridge['anchor'],'segment':bridge['endpoints'],
                             'positions':positions,'distance':distance,'deficit':max(0,budget-distance),
                             'svg_ids':[bridge['svg_id']],'geometry':'semicircular_bridge'})
    for run in runs:
        a,b=run['start'],run['end']
        if abs(a[0]-b[0]) > ENDPOINT_TOLERANCE and abs(a[1]-b[1]) > ENDPOINT_TOLERANCE:
            unchecked.append(dict(run,detail='Nonorthogonal straight-run clearance unsupported'))
            continue
        line_box=[min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])]
        for inst,node in geometry['nodes'].items():
            exempt=None
            for pid,port in node['ports'].items():
                if inst+'.'+pid not in declared.get(run['anchor'],set()): continue
                for end,other in ((a,b),(b,a)):
                    if math.dist(end,port['position']) > ENDPOINT_TOLERANCE: continue
                    dx,dy=other[0]-end[0],other[1]-end[1]; ux,uy=port['direction']
                    if dx*ux+dy*uy > ENDPOINT_TOLERANCE and abs(dx*uy-dy*ux) <= ENDPOINT_TOLERANCE:
                        exempt=pid
            if exempt:
                exemptions.append({'component':inst,'port':exempt,'anchor':run['anchor'],
                                   'segment':[a,b],'reason':'Declared terminal run leaves its own port along the outward anchor.'})
                continue
            distance,positions=box_gap(line_box,node['footprint'])
            measured.append({'component':inst,'anchor':run['anchor'],'segment':[a,b],
                             'positions':positions,'distance':distance,'deficit':max(0,budget-distance),
                             'svg_ids':run['svg_ids']})
    nearest=min(measured,key=lambda p:p['distance']) if measured else None
    return {'nearest':nearest,'violations':[p for p in measured if p['distance'] < budget],
            'measured_pairs':len(measured),'terminal_exemptions':exemptions,'unchecked':unchecked,
            'coverage_status':('not_checked' if unchecked or geometry['issues'] or topology['coverage_status']=='not_checked'
                               else 'warn' if any(p['distance'] < budget for p in measured)
                               else 'pass' if measured else 'not_applicable')}


def measure_groups(geometry, intent, browser, budget):
    groups=intent.get('groups') or []
    rows=browser.get('elements',[]) if browser.get('status')=='pass' else []
    measured,unchecked=[],[]
    for group in groups:
        frames=[row for row in rows if row['attrs'].get('data-group')==group['id'] and row['tag']=='rect']
        if len(frames)!=1 or not frames[0]['visible']:
            unchecked.append({'group':group['id'],'detail':'Missing/duplicate/hidden measured group frame'})
            continue
        try:
            frame=display_rectangle(frames[0],browser)
        except ValueError as error:
            unchecked.append({'group':group['id'],'detail':str(error)})
            continue
        for member in group['members']:
            node=geometry['nodes'].get(member)
            if not node:
                unchecked.append({'group':group['id'],'component':member,'detail':'Missing normalized member footprint'})
                continue
            box=node['footprint']
            gaps=[box[0]-frame[0],box[1]-frame[1],frame[2]-box[2],frame[3]-box[3]]
            witnesses=[[[frame[0],box[1]],[box[0],box[1]]],
                       [[box[0],frame[1]],[box[0],box[1]]],
                       [[frame[2],box[1]],[box[2],box[1]]],
                       [[box[0],frame[3]],[box[0],box[3]]]]
            side=min(range(4),key=lambda i:gaps[i]); distance=gaps[side]
            measured.append({'group':group['id'],'component':member,'distance':distance,
                             'deficit':max(0,budget-distance),'positions':witnesses[side],
                             'side':('left','top','right','bottom')[side], 'frame':frame,'footprint':box})
    nearest=min(measured,key=lambda p:p['distance']) if measured else None
    return {'nearest':nearest,'measurements':measured,'unchecked':unchecked,
            'status':('not_applicable' if not groups else 'not_checked' if unchecked
                      else 'warn' if nearest and nearest['distance']<budget else 'pass')}


def bridge_gap(bridge, row, box):
    """Exact circular half-arc distance to a rectangular footprint.

    Topology has independently parsed the semicircle. Browser bounds determine
    its actual bulge after the final orthogonal transform, without reconstructing
    transforms from layout or treating the arc's empty chord as visible pipe.
    """
    a,b=bridge['endpoints']; center=[(a[k]+b[k])/2 for k in (0,1)]
    radius=math.dist(a,b)/2; bounds=row['bbox']
    if radius <= 0: raise ValueError('Degenerate bridge arc')
    if abs(a[1]-b[1]) <= ENDPOINT_TOLERANCE:
        direction=[0,-1 if center[1]-bounds[1] > bounds[3]-center[1] else 1]
        sizes=(bounds[2]-bounds[0],bounds[3]-bounds[1]); expected=(2*radius,radius)
    elif abs(a[0]-b[0]) <= ENDPOINT_TOLERANCE:
        direction=[-1 if center[0]-bounds[0] > bounds[2]-center[0] else 1,0]
        sizes=(bounds[2]-bounds[0],bounds[3]-bounds[1]); expected=(radius,2*radius)
    else: raise ValueError('Nonorthogonal bridge chord unsupported')
    if any(abs(x-y)>ENDPOINT_TOLERANCE for x,y in zip(sizes,expected)):
        raise ValueError('Bridge display is not an orthogonal circular half-arc')
    candidates=[a,b]
    candidates.extend([center[0]+dx*radius,center[1]+dy*radius] for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)))
    for x in (box[0],box[2]):
        for y in (box[1],box[3]):
            vx,vy=x-center[0],y-center[1]; length=math.hypot(vx,vy)
            if length: candidates.append([center[0]+radius*vx/length,center[1]+radius*vy/length])
    # Rect-edge intersections, including corner/tangent contact, are exact zero.
    for axis in (0,1):
        other=1-axis
        for value in (box[axis],box[axis+2]):
            delta=value-center[axis]
            if abs(delta)>radius: continue
            offset=math.sqrt(max(0,radius*radius-delta*delta))
            for sign in (-1,1):
                p=list(center);p[axis]=value;p[other]+=sign*offset
                if box[other] <= p[other] <= box[other+2]: candidates.append(p)
    measured=[]
    for p in candidates:
        if sum((p[k]-center[k])*direction[k] for k in (0,1)) < -1e-7: continue
        q=[min(max(p[k],box[k]),box[k+2]) for k in (0,1)]
        measured.append((math.dist(p,q),[p,q]))
    return min(measured,key=lambda item:item[0])


def canvas_bounds(geometry, topology, browser):
    """V6 component footprints and visible pipe bounds in root SVG coordinates."""
    rows={row['id']:row for row in browser.get('elements',[]) if row['id']}
    canvas=browser.get('viewbox')
    if not canvas:
        return [],{'id':'V6','coverage_status':'not_checked','coverage_detail':'Actual SVG canvas/display bounds unavailable.'}
    x,y,w,h=canvas; limit=[x,y,x+w,y+h]
    objects=[]
    for inst,node in geometry['nodes'].items():
        if rows.get('inst-'+inst,{}).get('visible',True):
            objects.append({'component':inst,'box':node['footprint']})
    pipes={s['svg_id']:s['anchor'] for s in topology.get('segments',[])}
    for sid,anchor in pipes.items():
        row=rows.get(sid)
        if row and row['visible']:
            objects.append({'svg_id':sid,'anchor':anchor,'box':row['bbox']})
    findings=[]
    for item in objects:
        box=item['box']
        overflow=dict(zip(('left','top','right','bottom'),(max(0,x-box[0]),max(0,y-box[1]),max(0,box[2]-limit[2]),max(0,box[3]-limit[3]))))
        if any(overflow.values()):
            name=item.get('component') or item.get('svg_id')
            findings.append({'id':'V6','result':'fail','kind':'canvas_overflow',**item,'overflow':overflow,
                             'detail':'%s 实际根 SVG 范围 %s 越出画布 %s，超出 %s' % (name,box,limit,overflow)})
    unchecked=geometry['issues'] or topology.get('display_evidence',{}).get('unchecked')
    return findings,{'id':'V6','canvas':[w,h],'canvas_bounds':limit,'coordinate_system':'root_svg_user_units',
                     'coverage_status':'not_checked' if unchecked else 'pass',
                     'coverage_detail':'Final component footprints and browser-visible pipe bounds checked against the actual SVG viewBox.',
                     'content_x':[min(o['box'][0] for o in objects),max(o['box'][2] for o in objects)] if objects else None,
                     'content_y':[min(o['box'][1] for o in objects),max(o['box'][3] for o in objects)] if objects else None,
                     'objects':objects}


def display_rectangle(row, browser):
    """Measured orthogonal frame bounds, with unsupported paint effects disclosed."""
    if not row['visible']: raise ValueError('Frame is hidden')
    a,b,c,d,_,_=row['matrix']
    if (abs(a)>1e-6 and abs(b)>1e-6) or (abs(c)>1e-6 and abs(d)>1e-6):
        raise ValueError('Nonorthogonal frame transform is unsupported')
    related=[row]
    for ancestor in row.get('ancestors',[]):
        related.extend(item for item in browser.get('elements',[])
                       if item['tag']==ancestor['tag'] and item['attrs']==ancestor['attrs'])
    if any(item['style'].get(effect,'none')!='none' for item in related for effect in ('clip-path','mask','filter')):
        raise ValueError('Frame clipping/mask/filter is unsupported')
    return row['bbox']


def frame_checks(geometry, topology, browser, intent, layout, runs, clip_length):
    """V7/V8 compare actual displayed frames to normalized footprint/pipe geometry."""
    rows=browser.get('elements',[]) if browser.get('status')=='pass' else []
    frames,unchecked={},[]
    expected=[('legend','lg',None),('title_block','tb',None)]
    expected += [('group:'+g['id'],'grp',g['id']) for g in intent.get('groups') or []]
    for name,cls,gid in expected:
        if gid is None and name not in layout: continue
        matches=[row for row in rows if row['tag']=='rect' and row['attrs'].get('class')==cls
                 and (gid is None or row['attrs'].get('data-group')==gid)]
        try:
            if len(matches)!=1: raise ValueError('Missing or duplicate actual frame')
            frames[name]=display_rectangle(matches[0],browser)
        except ValueError as error:
            unchecked.append({'frame':name,'detail':str(error)})
    def overlap(a,b):
        return not (a[2]<b[0] or a[0]>b[2] or a[3]<b[1] or a[1]>b[3])
    findings=[]
    def add(check,kind,detail,**context):
        findings.append({'id':check,'kind':kind,'result':'fail','detail':detail,**context})
    if 'legend' in frames and 'title_block' in frames and overlap(frames['legend'],frames['title_block']):
        add('V7','frame_overlap','实际图例与图签栏重叠: %s ↔ %s' % (frames['legend'],frames['title_block']),
            frames=['legend','title_block'],positions=[frames['legend'],frames['title_block']])
    for name in ('legend','title_block'):
        box=frames.get(name)
        if box is None: continue
        for inst,node in geometry['nodes'].items():
            if overlap(box,node['footprint']):
                add('V7','frame_component_overlap','%s 实际画框 %s 与元件 %s 实际足迹 %s 重叠' % (name,box,inst,node['footprint']),
                    frame=name,component=inst,positions=[box,node['footprint']])
        for run in runs:
            hit=clip_length(run['start'],run['end'],box,tol=0)
            if hit>8:
                add('V7','frame_pipe_overlap','%s 实际画框压住 %s 管线 %.1f，段 %s → %s' % (name,run['anchor'],hit,run['start'],run['end']),
                    frame=name,anchor=run['anchor'],segment=[run['start'],run['end']],penetration=hit,svg_ids=run['svg_ids'])
        for bridge in topology.get('bridges',[]):
            row=next((r for r in rows if r['id']==bridge['svg_id']),None)
            if not row or not overlap(box,row['bbox']): continue
            if all(box[k]<=row['bbox'][k] and box[k+2]>=row['bbox'][k+2] for k in (0,1)):
                hit=math.pi*math.dist(*bridge['endpoints'])/2
                if hit>8:
                    add('V7','frame_bridge_overlap','%s 实际画框压住完整桥弧 %s (%.1f)' % (name,bridge['svg_id'],hit),
                        frame=name,anchor=bridge['anchor'],svg_id=bridge['svg_id'],penetration=hit)
            else:
                unchecked.append({'frame':name,'svg_id':bridge['svg_id'],'detail':'Partial curved-bridge/frame overlap length is not measured'})
    for group in intent.get('groups') or []:
        box=frames.get('group:'+group['id'])
        if box is None: continue
        for inst,node in geometry['nodes'].items():
            if inst not in group['members'] and overlap(box,node['footprint']):
                add('V8','foreign_component_in_group','分组 %s 实际画框 %s 圈进非成员 %s，实际足迹 %s' % (group['id'],box,inst,node['footprint']),
                    group=group['id'],component=inst,positions=[box,node['footprint']])
    incomplete=geometry['issues'] or topology.get('display_evidence',{}).get('unchecked') or browser.get('status')!='pass'
    evidence=[]
    for check in ('V7','V8'):
        issues=[issue for issue in unchecked if issue['frame'].startswith('group:')==(check=='V8')]
        evidence.append({'id':check,'coverage_status':'not_checked' if incomplete or issues else 'pass',
                         'coverage_detail':'Actual browser frame rectangles checked against normalized component footprints and visible pipe runs.',
                         'coordinate_system':'root_svg_user_units','frames':frames,'unchecked':issues})
    return findings,evidence
