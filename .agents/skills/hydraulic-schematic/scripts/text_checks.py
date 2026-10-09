"""Rendered text measurement, containment and clearance in root SVG units."""
from svg_paint import color_rgba, computed_length
import math
import re
import xml.etree.ElementTree as ET
from layout_clearance import display_rectangle
from lead_geometry import segments, perpendicular_scale
from sheet_geometry import point


def _groups(row):
    return [a['id'] for a in row.get('ancestors',[]) if a.get('id')]


def bbox_gap(a,b):
    return math.hypot(max(a[0]-b[2],b[0]-a[2],0.),max(a[1]-b[3],b[1]-a[3],0.))


def point_segment(p,a,b):
    dx,dy=b[0]-a[0],b[1]-a[1]
    t=max(0.,min(1.,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0.
    return math.dist(p,(a[0]+t*dx,a[1]+t*dy))


def inside(p,poly):
    signs=[(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]) for a,b in zip(poly,poly[1:]+poly[:1])]
    return all(v>=-1e-8 for v in signs) or all(v<=1e-8 for v in signs)


def segment_distance(a,b,c,d):
    def cross(p,q,r): return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    if (max(min(a[0],b[0]),min(c[0],d[0]))<=min(max(a[0],b[0]),max(c[0],d[0]))+1e-8 and
        max(min(a[1],b[1]),min(c[1],d[1]))<=min(max(a[1],b[1]),max(c[1],d[1]))+1e-8 and
        cross(a,b,c)*cross(a,b,d)<=1e-8 and cross(c,d,a)*cross(c,d,b)<=1e-8): return 0.
    return min(point_segment(p,x,y) for p,x,y in ((a,c,d),(b,c,d),(c,a,b),(d,a,b)))


def polygon_segment(poly,a,b):
    if inside(a,poly) or inside(b,poly): return 0.
    return min(segment_distance(c,d,a,b) for c,d in zip(poly,poly[1:]+poly[:1]))


def polygon_distance(a,b):
    if inside(a[0],b) or inside(b[0],a): return 0.
    return min(segment_distance(x,y,p,q) for x,y in zip(a,a[1:]+a[:1]) for p,q in zip(b,b[1:]+b[:1]))


def owner(row):
    if row.get('instance'): return 'symbol:'+row['instance']
    if row['attrs'].get('data-label-for'): return 'label:'+row['attrs']['data-label-for']
    return next((p for p in ('title','legend') if p in _groups(row)),str(row['key']))


def outline_segments(row):
    tag,attrs=row['tag'],row['attrs']
    if tag=='line':
        local=[tuple(row['local_endpoints'])]
    elif tag=='rect' and row.get('linear_outline'):
        x,y,w,h=row['local_bbox']
        points=[(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
        local=list(zip(points,points[1:]))
    elif tag=='polygon':
        values=list(map(float,re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?\d*)',attrs.get('points',''))))
        points=list(zip(values[::2],values[1::2]));points+=points[:1]
        local=list(zip(points,points[1:]))
    else:
        try:
            if tag=='path' and re.search('[zZ]',attrs.get('d','')):
                if len(re.findall('[mM]',attrs['d']))!=1: raise ValueError('multiple closed subpaths')
                local=segments(tag,{**attrs,'d':re.sub('[zZ]','',attrs['d'])})
                if local: local.append((local[-1][1],local[0][0]))
            else: local=segments(tag,attrs)
        except ValueError: local=[]
    if local:
        return [(point(row['matrix'],a),point(row['matrix'],b)) for a,b in local]
    return [(a,b) for a,b in zip(row['outline'],row['outline'][1:])
            if math.dist(a,b)<=max(.26,row['outline_step']*1.1)]


def display_effects(row):
    return any(values.get(k,'none')!='none' for values in [row['style']]+[a.get('effects',{}) for a in row['ancestors']]
               for k in ('clip-path','mask','filter'))


def overlap_finding(text,obstacle,kind,distance,required=6.):
    hard=distance<=0
    return {'id':'V12' if hard else 'V19','result':'fail' if hard else 'warn',
            'kind':'text_overlap' if hard else 'text_clearance','budget_id':'B7','element':text['element'],
            'text':text['text'],'bbox':text['bbox'],'obstacle':obstacle,'obstacle_kind':kind,
            'distance':round(distance,4),'required_clearance':required,'shortfall':round(required-distance,4),
            'detail':'文字 "%s" 与 %s %s：净空 %.3f，要求 %.1f，位置 %s' %
                     (text['text'][:35],kind,obstacle,distance,required,text['bbox'])}


def normalized_text(value):
    return ''.join(str(value or '').split())


def glyph_paint(row):
    style=row['style']
    if not row.get('visible'): return False
    results=[]
    for paint in ('fill','stroke'):
        value=style.get(paint,'none')
        if value=='none' or float(style.get(paint+'-opacity','1'))<=0:
            results.append(False);continue
        color=color_rgba(value)
        if color is None:results.append(None);continue
        alpha=color[3]
        width=computed_length(style.get('stroke-width','0')) if paint=='stroke' else 1
        if width is None:results.append(None);continue
        results.append(alpha>0 and width>0)
    return True if True in results else None if None in results else False


def required_text(rows,layout,intent,resolve_symbol,geometry):
    """Expected text comes from declared labels and the actual selected symbol assets."""
    required,issues,unchecked,used=set(),[],[],set()
    text_rows=[r for r in rows if r['tag']=='text' and not any(a['tag'] in ('defs','symbol','clipPath','mask') for a in r['ancestors'])]
    def missing(text,owner,component=None):
        issues.append({'id':'V12','result':'fail','kind':'missing_required_text','text':text,'label_owner':owner,
                       'component':component,'bbox':None,
                       'component_bbox':geometry['nodes'].get(component,{}).get('footprint'),
                       'detail':'必需文字 "%s" 缺失或内容不符，归属 %s' % (text,owner)})
        unchecked.append({'text':text,'owner':owner,'reason':'Missing required text has no measurable glyph range'})
    def require(text,owner,component=None,element_id=None,scope='labels'):
        candidates=[r for r in text_rows if r['key'] not in used and normalized_text(r['text'])==normalized_text(text)]
        if scope=='instance': candidates=[r for r in candidates if r.get('instance')==component and (not element_id or r['id']==element_id)]
        else:
            candidates=[r for r in candidates if 'labels' in _groups(r) and r['attrs'].get('data-label-for') in (None,owner)]
            candidates.sort(key=lambda r:r['attrs'].get('data-label-for')!=owner)
        if not candidates: missing(text,owner,component);return
        row=candidates[0];required.add(row['key']);used.add(row['key'])
    if layout is not None:
        for inst,node in layout['nodes'].items():
            try: source=ET.parse(resolve_symbol(node['symbol'])).getroot() if resolve_symbol else None
            except (OSError,ET.ParseError) as error:
                unchecked.append({'component':inst,'reason':str(error)});continue
            intrinsic=[e for e in source.iter() if e.tag.rsplit('}',1)[-1]=='text'] if source is not None else []
            name=layout.get('labels',{}).get(inst,inst)
            if not any(e.get('data-name-slot') for e in intrinsic):
                for line in name.split('\n'):
                    if line.strip(): require(line,inst,inst)
            for el in intrinsic:
                label=(''.join(line for line in name.split('\n') if line) if el.get('data-name-slot') else ''.join(el.itertext()).strip()) or ''.join(el.itertext()).strip()
                if label: require(label,inst,inst,inst+'__'+el.get('id') if el.get('id') else None,'instance')
        for name,node in layout.get('externs',{}).items():
            for line in node.get('label',name).split('\n'):
                if line.strip(): require(line,'@'+name)
        for group in ('title','legend'):
            group_rows=[r for r in text_rows if group in _groups(r)]
            required.update(r['key'] for r in group_rows)
            if not group_rows: missing('图签' if group=='title' else '图例',group)
            if group=='title' and intent:
                combined=normalized_text(''.join(r['text'] for r in group_rows))
                for token in ('系统 '+str(intent['system']),'L0 '+str(intent['l0_version']),str(intent['catalog']),
                              '成熟度 '+str(intent['maturity']),'部件','网络','气侧支路','未知项','悬空端口','provisional:','draft:'):
                    if normalized_text(token) not in combined: missing(token,'title')
    blocked=set()
    for row in rows:
        parents=[r for r in text_rows if r['key'] in required and any(a['tag']=='text' and a['attrs']==r['attrs'] for a in row['ancestors'])]
        if row['key'] not in required and not (row['tag']=='tspan' and parents): continue
        paint=glyph_paint(row)
        collapsed=(row.get('ink_status')=='pass' and not row.get('ink_bbox') and bool(row.get('text','').strip()))
        if paint is False or collapsed:
            issues.append({'id':'V12','result':'fail','kind':'text_hidden','element':row['id'] or row['key'],
                           'text':row.get('text'),'bbox':row.get('ink_bbox') or row['bbox'],
                           'detail':'必需文字 "%s" 被隐藏或没有可见字形描画 (%s)' % (row.get('text','')[:40],row['id'] or row['key'])})
            unchecked.append({'element':row['id'] or row['key'],'text':row.get('text'),'reason':'Required text is not displayed'})
            blocked.add(row['key']);blocked.update(r['key'] for r in parents)
        elif paint is None:
            unchecked.append({'element':row['id'] or row['key'],'reason':'Text paint cannot be established'})
            blocked.add(row['key']);blocked.update(r['key'] for r in parents)
    return issues,unchecked,blocked


def check_text(browser, geometry, budget=6., layout=None, intent=None, resolve_symbol=None):
    findings,records,unchecked = [],[],[]
    if browser.get('status')!='pass':
        detail=browser.get('reason','Browser text evidence unavailable')
        return [],[{'id':i,'coverage_status':'not_checked','coverage_detail':detail} for i in ('V12','B7')],{'texts':[],'unchecked':[{'reason':detail}]}
    rows=browser['elements']
    required_findings,required_unchecked,blocked=required_text(rows,layout,intent,resolve_symbol,geometry)
    findings.extend(required_findings);unchecked.extend(required_unchecked)
    vx,vy,vw,vh=browser['viewbox']
    viewport=[vx,vy,vx+vw,vy+vh]
    panels={name:next((r for r in rows if r['tag']=='rect' and name in _groups(r)),None)
            for name in ('title','legend')}
    for row in rows:
        if row['key'] in blocked or row['tag']!='text' or not row.get('visible') or not row.get('text','').strip():
            continue
        paint=glyph_paint(row)
        if paint is False: continue
        if paint is None:
            unchecked.append({'element':row['id'] or row['key'],'text':row.get('text'),'reason':'Text paint cannot be established'})
            continue
        if row.get('ink_status')!='pass' or not row.get('ink_bbox'):
            unchecked.append({'element':row['id'] or row['key'],'text':row.get('text'),
                              'bbox':row['bbox'],'reason':row.get('ink_reason','Glyph ink bounds unavailable')})
            continue
        record={'element':row['id'] or row['key'],'text':row['text'],'bbox':row['ink_bbox'],
                'layout_bbox':row['bbox'],'owner':owner(row),'instance':row.get('instance'),'font':row['style']['font-family'],
                'font_size':row['style']['font-size'],'matrix':row['matrix'],'row':row}
        record['quad_boxes']=[(q,[min(p[0] for p in q),min(p[1] for p in q),max(p[0] for p in q),max(p[1] for p in q)]) for q in row['ink_quads']]
        records.append(record)
        if display_effects(row):
            unchecked.append({'element':record['element'],'text':row['text'],'bbox':record['bbox'],
                              'reason':'Text clipping/masking/filter requires additional rendered evidence'})
        containers=[('viewport',viewport,None)]
        for name,panel in panels.items():
            if name in _groups(row):
                try:
                    if panel is None: raise ValueError('Required text container is missing')
                    box=display_rectangle(panel,browser)
                    containers.append((name,box,panel))
                except ValueError as error:
                    unchecked.append({'element':record['element'],'container':name,'reason':str(error)})
        if row.get('instance'):
            groups=[a['id'] for a in row['ancestors'] if a['tag']=='g' and a['id']]
            candidates=[r for r in rows if r.get('instance')==row['instance'] and r.get('closed')]
            if candidates:
                def rank(shape):
                    shared=next((i for i,g in enumerate(groups) if g in _groups(shape)),len(groups))
                    anchored=0 if row['key'] in shape.get('anchors_inside',[]) else 1
                    b=shape['bbox']
                    return shared,anchored,(b[2]-b[0])*(b[3]-b[1])
                own=min(candidates,key=rank)
                record['container']=own['id'] or own['key']
                record['container_key']=own['key']
                try:
                    box=display_rectangle(own,browser) if own['tag']=='rect' else own['bbox']
                    containers.append((own['id'] or own['key'],box,own))
                except ValueError as error:
                    unchecked.append({'element':record['element'],'container':record['container'],'reason':str(error)})
        for name,box,shape in containers:
            b=record['bbox']
            over={'left':max(0.,box[0]-b[0]),'top':max(0.,box[1]-b[1]),
                  'right':max(0.,b[2]-box[2]),'bottom':max(0.,b[3]-box[3])}
            outside=shape.get('outside_text_points',{}).get(str(row['key']),[]) if shape else []
            if outside and max(over.values())<=.1:
                edges=outline_segments(shape)
                if edges:
                    over['outline']=max(min(point_segment(p,a,b) for a,b in edges) for p in outside)
            if max(over.values())>.1:
                findings.append({'id':'V12','result':'fail','kind':'text_overflow','text':row['text'],
                                 'element':record['element'],'bbox':b,'container':name,'container_bbox':box,
                                 'overflow':over,'detail':'文字 "%s" 越出 %s：%s，实际框 %s' %
                                 (row['text'][:45],name,over,b)})
    clearance=[]
    for row in rows:
        if not row.get('visible') or row['tag'] in ('text','tspan','g','svg'): continue
        style=row['style']
        stroke_color=color_rgba(style['stroke']);fill_color=color_rgba(style['fill'])
        stroke=(stroke_color is None or (stroke_color[3]>0 and stroke_color[:3]!=(255.,255.,255.))) and float(style['stroke-opacity'])>0
        fill=row['tag']!='line' and (fill_color is None or (fill_color[3]>0 and fill_color[:3]!=(255.,255.,255.))) and float(style['fill-opacity'])>0
        if not stroke and not fill: continue
        width=computed_length(style['stroke-width']) if stroke else 0.
        matrix=row['matrix']; max_radius=(width or 0)*math.hypot(*matrix[:4])/2
        nearby=[t for t in records if bbox_gap(t['bbox'],row['bbox'])<=budget+max_radius]
        if not nearby: continue
        if row.get('outline_status')!='pass' or width is None or display_effects(row):
            unchecked.append({'element':row['id'] or row['key'],'bbox':row['bbox'],
                              'reason':'Shape outline or display effect cannot establish text clearance'})
            continue
        classes=row['attrs'].get('class','').split()
        kind=('pipe' if any(c.startswith('ln-') for c in classes) else 'suction_marker' if 'suc-mark' in classes
              else 'symbol_outline' if row.get('instance') else 'graphic')
        shape_segments=[]
        # Keep native subpath jumps out of contour geometry.
        for a,b in outline_segments(row):
            dx,dy=b[0]-a[0],b[1]-a[1]
            if math.hypot(dx,dy)<1e-9: continue
            det=matrix[0]*matrix[3]-matrix[1]*matrix[2]
            if abs(det)<1e-10: continue
            vector=((matrix[3]*dx-matrix[2]*dy)/det,(-matrix[1]*dx+matrix[0]*dy)/det)
            radius=width/2 if style['vector-effect']=='non-scaling-stroke' else width*perpendicular_scale(matrix,vector)/2
            shape_segments.append((a,b,radius,[min(a[0],b[0]),min(a[1],b[1]),max(a[0],b[0]),max(a[1],b[1])]))
        for text in nearby:
            if (row.get('instance') and text.get('instance')!=row['instance'] and
                    text['row']['key'] in row.get('enclosed_text_hits',[])):
                hit=overlap_finding(text,row['id'] or '%s/%s[%d]'%(row['instance'],row['tag'],row['key']),
                                    'symbol_body',0.,budget)
                hit['obstacle_component']=row['instance']
                findings.append(hit)
            nearest=math.inf
            for a,b,radius,box in shape_segments:
                if bbox_gap(text['bbox'],box)>min(budget+radius,nearest+radius): continue
                quads=[q for q,qbox in text['quad_boxes'] if bbox_gap(qbox,box)<=min(budget+radius,nearest+radius)]
                if quads:
                    distance=min(polygon_segment(q,a,b) for q in quads)-radius
                    nearest=min(nearest,distance)
            if fill and text['row']['key'] in row.get('filled_text_hits',[]): nearest=min(nearest,0.)
            if not math.isfinite(nearest): continue
            obstacle=row['id'] or row['key']
            clearance.append({'element':text['element'],'obstacle':obstacle,'obstacle_kind':kind,'distance':nearest})
            if nearest<budget-.001: findings.append(overlap_finding(text,obstacle,kind,nearest,budget))
    for i,text in enumerate(records):
        for other in records[i+1:]:
            gap=bbox_gap(text['bbox'],other['bbox'])
            if gap>budget or (text['owner']==other['owner'] and gap>0): continue
            pairs=[(a,b) for a,abox in text['quad_boxes'] for b,bbox in other['quad_boxes'] if bbox_gap(abox,bbox)<=budget]
            if not pairs: continue
            distance=min(polygon_distance(a,b) for a,b in pairs)
            if text['owner']==other['owner'] and distance>0: continue  # intra-label leading is typography, not B7
            clearance.append({'element':text['element'],'obstacle':other['element'],'obstacle_kind':'text','distance':distance})
            if distance<budget-.001: findings.append(overlap_finding(text,other['element'],'text',distance,budget))
    violations=[f for f in findings if f.get('budget_id')=='B7']
    b7_status='not_checked' if unchecked else 'fail' if any(f['result']=='fail' for f in violations) else 'warn' if violations else 'pass'
    ev=[{'id':'V12','texts':len(records),'coverage_status':'not_checked' if unchecked else 'pass',
         'coverage_detail':'Browser glyph ink bounds and containment checked.','unchecked':unchecked},
        {'id':'B7','coverage_status':b7_status,'coverage_detail':'Actual glyph-to-contour and text-to-text clearance measured.',
         'budget':budget,'violations':len(violations),'unchecked':unchecked,'outline_max_step':.25}]
    return findings,ev,{'texts':records,'clearance':clearance,'budget_status':b7_status,'violations':len(violations),'unchecked':unchecked,'coordinate_system':'root_svg_user_units'}
