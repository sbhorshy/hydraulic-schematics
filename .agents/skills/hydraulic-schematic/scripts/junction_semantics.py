"""Input-network and actual crossing semantics, independent of marker claims."""
from collections import defaultdict
import math
import re

TOLERANCE=.1


def input_networks(declarations):
    parent={}
    def find(p):
        parent.setdefault(p,p)
        while parent[p]!=p:
            p=parent[p]
        return p
    for edge in declarations.get('expected_edges',declarations.get('edges',[])):
        a,b=map(find,edge['endpoints'])
        parent[max(a,b)]=min(a,b)
    result={e['anchor']:find(e['endpoints'][0]) for e in declarations.get('expected_edges',declarations.get('edges',[]))}
    result.update({b['anchor']:find(b['id']) for b in declarations.get('buses',[])})
    return result


def on(p,a,b):
    length=math.dist(a,b)
    return length>TOLERANCE and abs((p[0]-a[0])*(b[1]-a[1])-(p[1]-a[1])*(b[0]-a[0]))/length<=TOLERANCE and all(min(a[k],b[k])-TOLERANCE<=p[k]<=max(a[k],b[k])+TOLERANCE for k in (0,1))


def axis(segment):
    a,b=segment['start'],segment['end']
    if math.dist(a,b)<=TOLERANCE:return None
    if abs(a[1]-b[1])<=TOLERANCE:return 'h'
    if abs(a[0]-b[0])<=TOLERANCE:return 'v'
    return None


def intersection_events(segments, networks):
    horizontal=[s for s in segments if axis(s)=='h']
    vertical=[s for s in segments if axis(s)=='v']
    candidates=[]
    for h in horizontal:
        for v in vertical:
            p=[v['start'][0],h['start'][1]]
            if on(p,h['start'],h['end']) and on(p,v['start'],v['end']) and not any(math.dist(p,q)<=TOLERANCE for q in candidates):
                candidates.append(p)
    events=[]
    for p in candidates:
        incident=[s for s in segments if axis(s) and on(p,s['start'],s['end'])]
        directions=set()
        for s in incident:
            for end in (s['start'],s['end']):
                if math.dist(p,end)<=TOLERANCE:continue
                directions.add(('right' if end[0]>p[0] else 'left') if axis(s)=='h' else ('down' if end[1]>p[1] else 'up'))
        if len(directions)<3:continue
        anchors=sorted({s['anchor'] for s in incident if s.get('anchor')})
        known={networks[a] for a in anchors if a in networks}
        kind=('unchecked' if not anchors or any(s.get('anchor') not in networks for s in incident) else
              'junction' if len(known)==1 else 'crossing' if len(directions)==4 else 'false_connection')
        events.append({'position':p,'kind':kind,'input_anchors':anchors,'networks':sorted(known),
                       'directions':sorted(directions),'horizontal_anchors':sorted({s['anchor'] for s in incident if axis(s)=='h' and s.get('anchor')})})
    return sorted(events,key=lambda e:tuple(e['position']))


def renderer_events(polys, anchors, declarations):
    segments=[{'start':a,'end':b,'anchor':anchor} for (_,pts),anchor in zip(polys,anchors) for a,b in zip(pts,pts[1:])]
    return intersection_events(segments,input_networks(declarations))


def merge_collinear(points):
    result=[]
    for p in points:
        while len(result)>1:
            a,b=result[-2:];u=(b[0]-a[0],b[1]-a[1]);v=(p[0]-b[0],p[1]-b[1])
            if abs(u[0]*v[1]-u[1]*v[0])<1e-6 and u[0]*v[0]+u[1]*v[1]>0:result.pop()
            else:break
        result.append(p)
    return result


def painted(row, kind='fill'):
    value=row['style'].get(kind,'none')
    if value=='none':return False
    match=re.fullmatch(r'rgba?\(([-+0-9., /]+)\)',value)
    if not match:return None
    values=[float(v) for v in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)',match[1])]
    if len(values) not in (3,4):return None
    return values[:3]!=[255.,255.,255.] and (len(values)==3 or values[3]>0) and float(row['style'].get(kind+'-opacity','1'))>0


def effects(row):
    return any(style.get(k,'none')!='none' for style in [row['style']]+[a.get('effects',{}) for a in row.get('ancestors',[])] for k in ('clip-path','mask','filter'))


def check_junctions(topology, browser):
    """Check actual system markers/bridges against input and visible geometry."""
    findings=[]; unchecked=[]
    def fail(check,kind,detail,**context):
        findings.append({'id':check,'result':'fail','kind':kind,'detail':detail,**context})
    if browser.get('status')!='pass':
        return [],[{'id':check,'coverage_status':'not_checked','coverage_detail':browser.get('reason','No actual display evidence')} for check in ('V4','V14')]
    rows=browser['elements']; by_id={r['id']:r for r in rows if r['id']}
    straight=[s for s in topology.get('segments',[]) if not s['bridge']]
    networks=input_networks(topology)
    unchecked.extend({'check':'both','svg_id':s['svg_id'],'input_anchors':[s.get('anchor')],
                      'detail':'Nonorthogonal system pipe is unsupported by junction classification'}
                     for s in straight if axis(s) is None and math.dist(s['start'],s['end'])>TOLERANCE)
    if topology.get('findings'):
        unchecked.append({'check':'both','detail':'Topology reconciliation has unresolved findings; marker evidence cannot certify those input connections.'})
    markers=[]
    for row in rows:
        ancestors={a['id'] for a in row.get('ancestors',[])}
        if 'legend' in ancestors or 'symbols' in ancestors or row.get('instance'):continue
        if 'jn' not in row['attrs'].get('class','').split() and 'junctions' not in ancestors:continue
        if row['tag']=='g':continue
        box=row['bbox'];position=[(box[0]+box[2])/2,(box[1]+box[3])/2]
        paint=painted(row)
        unsupported=effects(row) or paint is None or row['tag'] not in ('circle','ellipse')
        marker={'svg_id':row['id'],'position':position,'visible':row['visible'],'fill':row['style'].get('fill'),
                'fill_opacity':row['style'].get('fill-opacity'),'opacity':row['opacity'],'bbox':box,
                'painted':bool(row['visible'] and paint and box[2]>box[0] and box[3]>box[1]),'unchecked':unsupported}
        if unsupported:unchecked.append({'check':'V4','position':position,'svg_id':row['id'],'detail':'Filled marker paint/shape/effects need additional display evidence'})
        markers.append(marker)
    # The real arc is joined to the adjacent straight geometry first. Its own
    # data-edge claim cannot assign it to a different pipe/network.
    bridges=[]; virtual=[]
    for bridge in topology.get('bridges',[]):
        row=by_id.get(bridge['svg_id']);a,b=bridge['endpoints']
        stroke=painted(row,'stroke') if row else None
        if row and (not row['visible'] or stroke is False or float(row['style'].get('stroke-width','0').replace('px',''))<=0):
            fail('V14','unpainted_bridge','Bridge has no effective visible stroke',position=bridge['position'],input_anchors=[bridge['anchor']],svg_id=bridge['svg_id'])
            continue
        endpoints=[]
        for endpoint in (a,b):
            endpoints.append({s['anchor'] for s in straight if any(math.dist(endpoint,p)<=TOLERANCE for p in (s['start'],s['end']))})
        owners=set.intersection(*endpoints)
        valid_owner=bridge['anchor'] in owners
        unknown=bool(row and effects(row)) or stroke is None
        record={**bridge,'owners':sorted(o for o in owners if o),'continuous':bool(owners),
                'valid_owner':valid_owner,'unchecked':unknown}
        bridges.append(record)
        if row and row['style'].get('stroke-dasharray','none')!='none' and any(float(v)>0 for v in re.findall(r'[-+]?[0-9.]+',row['style']['stroke-dasharray'])):
            fail('V14','dashed_bridge','Bridge stroke is discontinuous',position=bridge['position'],input_anchors=[bridge['anchor']],svg_id=bridge['svg_id'])
        if unknown:unchecked.append({'check':'V14','svg_id':bridge['svg_id'],'position':bridge['position'],'detail':'Bridge clipping/masking/filtering unsupported'})
        elif not valid_owner:
            fail('V14','bridge_gap','Bridge does not continuously join its claimed pipe at both ends',position=bridge['position'],
                 input_anchors=sorted({a for a in [bridge.get('anchor'),*owners] if a}),svg_id=bridge['svg_id'],endpoints=bridge['endpoints'])
        for owner in owners or {bridge['anchor']}:
            virtual.append({'start':a,'end':b,'anchor':owner,'svg_id':bridge['svg_id'],'virtual':'bridge'})
    # Missing arcs leave facing loose ends. Reconstruct a candidate gap only for
    # diagnosis; this does not create an actual connection or repair V10's graph.
    loose=defaultdict(list)
    for anchor in networks:
        adjacency=defaultdict(set)
        for s in straight:
            if s['anchor']!=anchor:continue
            adjacency[s['a']].add(s['b']);adjacency[s['b']].add(s['a'])
        for vertex,near in adjacency.items():
            data=topology['vertices'][vertex]
            if len(near)!=1 or data['terminals']:continue
            p=data['position'];q=topology['vertices'][next(iter(near))]['position']
            if abs(p[1]-q[1])<=TOLERANCE:loose[anchor].append((p,1 if q[0]>p[0] else -1))
    for anchor,ends in loose.items():
        for a,direction in ends:
            if direction!=-1:continue
            candidates=[b for b,d in ends if d==1 and b[0]>a[0]+TOLERANCE and abs(b[1]-a[1])<=TOLERANCE]
            if candidates:
                b=min(candidates,key=lambda p:p[0])
                virtual.append({'start':a,'end':b,'anchor':anchor,'svg_id':None,'virtual':'gap'})
    segments=straight+virtual
    events=intersection_events(segments,networks)
    for event in events:
        position=event['position'];context={'position':position,'input_anchors':event['input_anchors'],'networks':event['networks']}
        local=[m for m in markers if math.dist(m['position'],position)<=TOLERANCE]
        dots=[m for m in local if m['painted'] and not m['unchecked']]
        arcs=[b for b in bridges if math.dist(b['position'],position)<=TOLERANCE]
        suspect=[s for s in segments if s.get('svg_id') in by_id and on(position,s['start'],s['end']) and effects(by_id[s['svg_id']])]
        if event['kind']=='unchecked' or suspect:
            unchecked.append({'check':'both',**context,'detail':'Incident pipe identity or display effects are unsupported'})
            continue
        if event['kind']=='junction':
            if not dots and not any(m['unchecked'] for m in local):
                fail('V4','missing_junction','Real connected branch has no visible filled junction dot',**context)
            if len(dots)>1:fail('V4','duplicate_junction','Real branch has duplicate junction dots',**context)
            if arcs and not any(b['unchecked'] for b in arcs):
                fail('V14','bridge_breaks_connection','Bridge cuts across a junction belonging to one input network',**context)
        else:
            if dots:fail('V4','false_junction','Junction dot falsely joins distinct input networks',**context)
            if event['kind']=='false_connection':
                fail('V14','false_connection','Distinct input networks touch at a terminal/T; a marker cannot legalize this connection',**context)
            elif not arcs:
                fail('V14','missing_bridge','Unconnected crossing lacks its actual continuous bridge',**context)
            else:
                for bridge in arcs:
                    if bridge['unchecked']:continue
                    if abs(bridge['endpoints'][0][1]-bridge['endpoints'][1][1])>TOLERANCE:
                        fail('V14','bridge_orientation','Required horizontal-over-vertical bridge has the wrong orientation',svg_id=bridge['svg_id'],**context)
                    if any(axis(s)=='h' and on(position,s['start'],s['end']) for s in straight):
                        fail('V14','bridge_not_split','Straight pipe remains under the bridge at the crossing',svg_id=bridge['svg_id'],**context)
    junctions=[e for e in events if e['kind']=='junction']
    for marker in markers:
        if not marker['painted'] or marker['unchecked']:continue
        if any(math.dist(marker['position'],e['position'])<=TOLERANCE for e in events):continue
        incident=[s for s in straight if on(marker['position'],s['start'],s['end'])]
        anchors=sorted({s['anchor'] for s in incident if s.get('anchor')})
        fail('V4','unexpected_junction','Filled dot is offset from a real branch or lies on an ordinary corner/straight run',
             position=marker['position'],input_anchors=anchors,svg_id=marker['svg_id'])
    for bridge in bridges:
        if bridge['unchecked']:continue
        if not any(math.dist(bridge['position'],e['position'])<=TOLERANCE for e in events):
            fail('V14','orphan_bridge','Bridge is not centered on an actual crossing',position=bridge['position'],input_anchors=[bridge['anchor']],svg_id=bridge['svg_id'])
    evidence=[]
    for check in ('V4','V14'):
        issues=[u for u in unchecked if u['check'] in (check,'both')]
        incomplete=topology.get('coverage_status')=='not_checked' or issues
        evidence.append({'id':check,'coverage_status':'not_checked' if incomplete else 'pass',
                         'coverage_detail':'Input networks reconciled against actual visible system junctions and continuous bridges.' if not incomplete else 'Junction/crossing display or topology measurement incomplete.',
                         'coordinate_system':'root_svg_user_units','position_tolerance':TOLERANCE,
                         'junctions':len([m for m in markers if m['painted']]),'expected_junctions':junctions,
                         'crossings':len([e for e in events if e['kind']=='crossing']),
                         'bridged':len(bridges),'unbridged':sum(f['kind']=='missing_bridge' for f in findings),
                         'events':events,'markers':markers,'bridges':bridges,'unchecked':issues})
    return findings,evidence
