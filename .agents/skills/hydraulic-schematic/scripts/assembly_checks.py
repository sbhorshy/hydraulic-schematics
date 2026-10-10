"""Assembly enclosures measured in root SVG units, with actual glyph evidence.

Assembly membership is semantic; a frame never creates a component or endpoint.
The rendering pass measures the member SVG before inserting frames underneath
its pipe layer. Validation measures the resulting SVG independently.
"""
import math
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
import xml.etree.ElementTree as ET

from browser_evidence import collect
from sheet_geometry import load_geometry, point
from text_checks import glyph_paint, display_effects

PADDING = 14.


def member_boxes(assembly, geometry, browser):
    boxes, unchecked = [], []
    rows=browser.get('elements',[]) if browser.get('status')=='pass' else []
    if browser.get('status')!='pass':
        unchecked.append({'reason':browser.get('reason','Browser glyph evidence unavailable')})
    for member in assembly['members']:
        node=geometry['nodes'].get(member)
        if node:
            boxes.append({'component':member,'kind':'footprint','bbox':list(node['footprint'])})
        else:
            unchecked.append({'component':member,'reason':'Member footprint unavailable'})
        labels=[r for r in rows if r['tag']=='text' and
                (r['attrs'].get('data-label-for')==member or r.get('instance')==member)]
        if not labels:
            unchecked.append({'component':member,'reason':'Member text evidence unavailable'})
        for row in labels:
            if not row.get('visible') or glyph_paint(row) is False:
                unchecked.append({'component':member,'reason':'Member text hidden or unpainted'})
            elif glyph_paint(row) is None or row.get('ink_status')!='pass' or not row.get('ink_bbox') or display_effects(row):
                unchecked.append({'component':member,'reason':'Member glyph ink cannot be measured'})
            else:
                boxes.append({'component':member,'kind':'text','element':row['id'] or row['key'],'bbox':row['ink_bbox']})
    return boxes,unchecked


def render_enclosures(svg_path, intent, layout, resolve_symbol):
    if not intent.get('assemblies'): return
    path=Path(svg_path);raw=path.read_text(encoding='utf-8')
    browser=collect(path)
    geometry=load_geometry(ET.fromstring(raw),layout,resolve_symbol)
    frames=[]
    padding=max(PADDING,float(layout.get('group_padding',PADDING)))
    gap=max(8.,float(layout.get('group_label_gap',8)))
    for aid,assembly in intent['assemblies'].items():
        boxes,unchecked=member_boxes(assembly,geometry,browser)
        attrs='data-assembly=%s data-input-anchor=%s' % (quoteattr(aid),quoteattr('assemblies.'+aid))
        if unchecked:
            frames.append('<g %s data-measurement="not_checked"/>' % attrs)
            continue
        # Include half the 1.5T frame ink, so the clear space is at least 14.
        margin=padding+.75*float(layout.get('style',{}).get('base_line_width_T',1.2))
        x=min(b['bbox'][0] for b in boxes)-margin
        y=min(b['bbox'][1] for b in boxes)-margin
        right=max(b['bbox'][2] for b in boxes)+margin
        bottom=max(b['bbox'][3] for b in boxes)+margin
        frames.append('<rect id=%s class="enc" %s x="%.6f" y="%.6f" width="%.6f" height="%.6f"/>' %
                      (quoteattr('assembly-'+aid),attrs,x,y,right-x,bottom-y))
        frames.append('<text id=%s class="enc-lbl" %s x="%.6f" y="%.6f">%s</text>' %
                      (quoteattr('assembly-label-'+aid),attrs,x,y-gap,escape(assembly['label'])))
    # Root-coordinate frames precede the shifted drawing; source transforms are
    # already accounted for by load_geometry / browser evidence.
    raw=raw.replace('<g id="sheet"','<g id="assemblies">'+''.join(frames)+'</g>\n<g id="sheet"',1)
    path.write_text(raw,encoding='utf-8')


def boundary_hits(a,b,box):
    """Intersections with the frame centerline, including a bend on the frame."""
    hits=[]
    for axis in (0,1):
        other=1-axis
        delta=b[axis]-a[axis]
        if abs(delta)<1e-8: continue
        for side in (box[axis],box[axis+2]):
            t=(side-a[axis])/delta
            p=[a[i]+t*(b[i]-a[i]) for i in (0,1)]
            if -1e-8<=t<=1+1e-8 and box[other]-1e-8<=p[other]<=box[other+2]+1e-8:
                if not any(math.dist(p,q)<.01 for q in hits): hits.append(p)
    return hits


def check_assemblies(intent, layout, geometry, browser, topology, runs):
    from layout_clearance import display_rectangle, InvisibleFrameError
    from svg_paint import computed_length, color_rgba
    from text_checks import point_segment
    findings=[]
    evidence={'id':'V20','coordinate_system':'root_svg_user_units','assemblies':[],
              'unchecked':[],'browser_evidence':'browser-evidence.json','svg_sha256':browser.get('svg_sha256')}
    declarations=intent.get('assemblies') or {}
    if not declarations:
        evidence['coverage_status']='not_applicable'
        return findings,[evidence]
    rows=browser.get('elements',[]) if browser.get('status')=='pass' else []
    def fail(aid,kind,detail,check='V20',**extra):
        findings.append({'id':check,'result':'fail','kind':kind,'assembly':aid,
                         'anchor':'assemblies.'+aid,'detail':aid+': '+detail,**extra})
    for aid,assembly in declarations.items():
        record={'assembly':aid,'anchor':'assemblies.'+aid,'members':assembly['members'],'crossings':[]}
        evidence['assemblies'].append(record)
        frames=[r for r in rows if r['tag']=='rect' and r['attrs'].get('data-assembly')==aid]
        if browser.get('status')!='pass':
            evidence['unchecked'].append({'assembly':aid,'reason':browser.get('reason','Browser evidence unavailable')})
            continue
        if len(frames)!=1:
            deferred=any(r['attrs'].get('data-assembly')==aid and r['attrs'].get('data-measurement')=='not_checked' for r in rows)
            if not deferred:
                fail(aid,'assembly_frame','Missing or duplicate enclosure')
            evidence['unchecked'].append({'assembly':aid,'reason':'Enclosure measurement unavailable'})
            continue
        row=frames[0]
        try:
            frame=display_rectangle(row,browser,require_outline=True)
        except InvisibleFrameError as error:
            fail(aid,'assembly_frame',str(error));continue
        except ValueError as error:
            evidence['unchecked'].append({'assembly':aid,'reason':str(error)});continue
        record.update(frame=frame,svg_id=row['id'])
        width=computed_length(row['style']['stroke-width'])
        a,b,c,d,_,_=row['matrix']
        scales=(math.hypot(a,b),math.hypot(c,d))
        if width is None or row['style'].get('vector-effect','none')!='none':
            evidence['unchecked'].append({'assembly':aid,'reason':'Enclosure displayed width cannot be measured'})
            half=0
        else:
            actual=[width*s for s in scales];half=max(actual)/2
            record['stroke_widths']=actual
            expected=1.5*float(layout.get('style',{}).get('base_line_width_T',1.2))
            dash=[computed_length(v) for v in row['style'].get('stroke-dasharray','').replace(',',' ').split()]
            fill=color_rgba(row['style'].get('fill','none'))
            fill_visible=(fill is not None and fill[3]>0 and float(row['style'].get('fill-opacity',1))>0)
            if any(abs(v-expected)>.02 for v in actual) or dash!=[8.,5.] or fill_visible:
                fail(aid,'assembly_style','Enclosure requires unfilled 1.5T long dashes (8 5)',bbox=frame,measured_widths=actual)
        boxes,unchecked=member_boxes(assembly,geometry,browser)
        evidence['unchecked'].extend(dict(assembly=aid,**u) for u in unchecked)
        record['member_boxes']=boxes
        for item in boxes:
            box=item['bbox']
            padding=min(box[0]-frame[0],box[1]-frame[1],frame[2]-box[2],frame[3]-box[3])-half
            item['padding']=padding
            if padding<PADDING-.001:
                fail(aid,'assembly_member_containment','Member footprint/text needs at least 14 units of clear padding',
                     check='V8',component=item['component'],bbox=item['bbox'],member_kind=item['kind'],padding=padding,frame=frame)
        for member,node in geometry['nodes'].items():
            box=node['footprint']
            if (member not in assembly['members'] and box[0]<frame[2] and frame[0]<box[2]
                    and box[1]<frame[3] and frame[1]<box[3]):
                fail(aid,'assembly_nonmember','Enclosure intersects a nonmember footprint',
                     check='V8',component=member,bbox=box,frame=frame)
        labels=[r for r in rows if r['tag']=='text' and r['attrs'].get('data-assembly')==aid]
        if len(labels)!=1 or labels[0].get('text')!=assembly['label'] or not labels[0]['visible'] or glyph_paint(labels[0]) is False:
            fail(aid,'assembly_label','Missing, hidden or incorrect assembly label',bbox=frame)
        elif glyph_paint(labels[0]) is None or labels[0].get('ink_status')!='pass' or display_effects(labels[0]):
            evidence['unchecked'].append({'assembly':aid,'reason':'Assembly label glyphs unavailable'})
        else:
            box=labels[0]['ink_bbox'];record['label_bbox']=box
            try:
                origin=point(labels[0]['matrix'],[float(labels[0]['attrs']['x']),float(labels[0]['attrs']['y'])])
                aligned=abs(origin[0]-frame[0])<=.1 and labels[0]['style']['text-anchor']=='start'
            except (KeyError,ValueError,TypeError):
                aligned=False
            if box[3]>=frame[1]-half or not aligned:
                fail(aid,'assembly_label','Assembly label must be left aligned above enclosure',bbox=box)
        for panel in [r for r in rows if r['tag']=='rect' and any(x.get('id') in ('title','legend') for x in r.get('ancestors',[]))]:
            try: pb=display_rectangle(panel,browser)
            except ValueError as error:
                evidence['unchecked'].append({'assembly':aid,'reason':str(error)});continue
            if frame[0]<pb[2] and pb[0]<frame[2] and frame[1]<pb[3] and pb[1]<frame[3]:
                fail(aid,'assembly_panel_overlap','Enclosure overlaps legend/title (zero overlap budget)',check='V7',bbox=frame,panel_bbox=pb)
        expected={e['anchor']:e['endpoints'] for e in topology.get('expected_edges',[])}
        seen=set()
        for segment in topology.get('segments',[]):
            a=topology['vertices'][segment['a']]['position'];b=topology['vertices'][segment['b']]['position']
            for position in boundary_hits(a,b,frame):
                key=(segment['anchor'],round(position[0],4),round(position[1],4))
                if key in seen: continue
                seen.add(key)
                endpoints=expected.get(segment['anchor'],[])
                members=[p for p in endpoints if p.split('.')[0] in assembly['members']]
                port_endpoint=None
                if len(members)==1:
                    inst,pid=members[0].split('.',1)
                    port=geometry['nodes'].get(inst,{}).get('ports',{}).get(pid)
                    if port:
                        for run in runs:
                            if run['anchor']!=segment['anchor']:continue
                            p=port['position'];u=port['direction'];delta=[position[i]-p[i] for i in (0,1)]
                            if (min(math.dist(p,run['start']),math.dist(p,run['end']))<=.1 and
                                point_segment(position,run['start'],run['end'])<=.1 and
                                delta[0]*u[0]+delta[1]*u[1]>0 and abs(delta[0]*u[1]-delta[1]*u[0])<=.1):
                                port_endpoint=members[0];break
                crossing={'position':position,'input_anchor':segment['anchor'],'svg_id':segment['svg_id'],
                          'member_port':port_endpoint,'status':'pass' if port_endpoint else 'fail'}
                record['crossings'].append(crossing)
                if not port_endpoint:
                    fail(aid,'assembly_boundary_crossing','Only a declared outward member-port lead may cross enclosure',**crossing)
        if topology.get('coverage_status')=='not_checked' or geometry['issues']:
            evidence['unchecked'].append({'assembly':aid,'reason':'Some final pipe/footprint geometry is unchecked'})
    evidence['coverage_status']='not_checked' if evidence['unchecked'] else 'fail' if findings else 'pass'
    containment={'id':'V8','coverage_status':'not_checked' if evidence['unchecked'] else 'pass',
                 'coverage_detail':'Assembly members include transformed footprints and actual glyph ink with 14 units clear padding.'}
    return findings,[evidence,containment]
