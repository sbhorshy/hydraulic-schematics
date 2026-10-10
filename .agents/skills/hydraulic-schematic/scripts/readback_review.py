"""Version-bound local PNG readback. Cropping never records perceptual signoff."""
import argparse
from datetime import datetime, timezone
import base64
import hashlib
import html
import io
import json
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from PIL import Image
from proofreading_evidence import digest_json, file_digest, verify_report, validation_fingerprint, enrich_report, write_report

MANIFEST='readback-manifest.json'
INDEX='readback.html'
LEDGER='readback-items-review.json'


def write_json(path,value):
    value['integrity']=digest_json({k:v for k,v in value.items() if k!='integrity'})
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)


def source(workdir):
    verification=verify_report(workdir)
    if verification['status']!='current' or verification.get('png',{}).get('status')!='pass':
        raise ValueError('Current verified validation report and PNG required: '+json.dumps(verification,ensure_ascii=False))
    report=json.loads((workdir/'validation-report.json').read_text())
    if report.get('geometry',{}).get('coordinate_system')!='root_svg_user_units':
        raise ValueError('Normalized root SVG geometry is required for local readback')
    path=workdir/'browser-evidence.json'
    browser=json.loads(path.read_text()) if path.exists() else {}
    if not browser.get('viewbox'):
        root=ET.parse(workdir/'1#系统原理图.svg').getroot()
        browser['viewbox']=[float(v) for v in root.get('viewBox','').replace(',',' ').split()]
    if len(browser['viewbox'])!=4 or any(not math.isfinite(v) for v in browser['viewbox']) or min(browser['viewbox'][2:])<=0:
        raise ValueError('A finite SVG viewBox is required for PNG localization')
    return report,browser


def binding_payload(manifest):
    return {**{k:manifest[k] for k in ('schema','artifact_fingerprint','validation_fingerprint','png_sha256','png_size','viewbox','scale')},
            'objects':[{k:v for k,v in item.items() if k!='review'} for item in manifest['objects']],
            'regions':[{k:v for k,v in region.items() if k!='file'} for region in manifest['regions']]}


def point_box(point,pad=24):
    x,y=point
    return [x-pad,y-pad,x+pad,y+pad]


def expand(box,pad=12):
    return [box[0]-pad,box[1]-pad,box[2]+pad,box[3]+pad]


def inventory(report):
    nodes=report['geometry']['nodes'];points={};objects=[]
    edges=report.get('topology',{}).get('expected_edges',[])
    def add(oid,kind,label,targets,**fields):
        objects.append({'id':oid,'kind':kind,'label':label,'targets':targets,**fields})
    for evidence in report.get('evidence',[]):
        if evidence['id']!='V20': continue
        for assembly in evidence.get('assemblies',[]):
            aid=assembly['assembly']
            add('assembly:'+aid,'assembly',aid+' 装配围框',
                [expand(assembly['frame'])] if assembly.get('frame') else [],
                input_anchors=[assembly['anchor']],members=assembly['members'])
            for index,crossing in enumerate(assembly.get('crossings',[])):
                add('assembly-crossing:'+aid+':'+str(index),'assembly_crossing',aid+' 越框端口',
                    [point_box(crossing['position'])],position=crossing['position'],
                    input_anchors=[assembly['anchor'],crossing['input_anchor']],member_port=crossing['member_port'])
    lead_bounds={}
    for evidence in report.get('evidence',[]):
        if evidence['id']=='V16':
            for row in evidence.get('measurements',[]):
                lead_bounds[(row.get('component'),row.get('port'))]=row.get('boundary',[])
    for inst,node in nodes.items():
        add('component:'+inst,'component',inst+' 元件全貌',[expand(node['footprint'])],component=inst)
        for pid,port in node['ports'].items():
            endpoint=inst+'.'+pid;points[endpoint]=port['position'];target=point_box(port['position'])
            for boundary in lead_bounds.get((inst,pid),[]):
                box=point_box(boundary,12);target=[min(target[0],box[0]),min(target[1],box[1]),max(target[2],box[2]),max(target[3],box[3])]
            add('port:'+endpoint,'port',endpoint,[target],component=inst,port=pid,position=port['position'],
                input_anchors=[e['anchor'] for e in edges if endpoint in e['endpoints']])
    for node in report.get('topology',{}).get('nodes',[]):
        if node['id'] not in nodes:
            add('component:'+node['id'],'component',node['id']+' 元件全貌',[],component=node['id'],unavailable_reason='组件实际足迹未取得')
    # Preserve declared endpoints even when their geometry could not be measured.
    for evidence in report.get('evidence',[]):
        if evidence['id']=='V5':
            for endpoint in evidence.get('declared',[]):
                if endpoint not in points:
                    inst,pid=endpoint.split('.',1)
                    add('port:'+endpoint,'port',endpoint,[],component=inst,port=pid,unavailable_reason='端口几何未取得')
    for external in report.get('topology',{}).get('externs',[]):
        vertex=next((v for v in report['topology'].get('vertices',[]) if external['id'] in v['terminals']),None)
        if vertex:
            points[external['id']]=vertex['position']
            add('external:'+external['id'],'external',external['id'],[point_box(vertex['position'])],position=vertex['position'])
    seen=set()
    for evidence in report.get('evidence',[]):
        if evidence['id'] not in ('V4','V14'):continue
        for event in evidence.get('events',[]):
            key=digest_json([event['position'],event['input_anchors']])[:12]
            if key in seen:continue
            seen.add(key)
            add('intersection:'+key,'intersection','接点 / 交叉 '+str(event['position']),[point_box(event['position'],32)],
                position=event['position'],input_anchors=event['input_anchors'],intersection_kind=event['kind'])
    for bridge in report.get('topology',{}).get('bridges',[]):
        add('bridge:'+str(bridge['svg_id']),'bridge','桥弧 '+str(bridge['svg_id']),[point_box(bridge['position'],32)],
            position=bridge['position'],input_anchors=[bridge.get('anchor')])
    def targets(finding):
        result=[]
        for key in ('position','actual_position'):
            point=finding.get(key)
            if isinstance(point,(list,tuple)) and len(point)==2 and all(isinstance(v,(int,float)) for v in point):result.append(point_box(point,28))
        for value in finding.get('positions') or []:
            if isinstance(value,(list,tuple)) and len(value) in (2,4) and all(isinstance(v,(int,float)) for v in value):
                result.append(point_box(value,28) if len(value)==2 else expand(value))
        for key in ('box','bbox','text_bbox','footprint'):
            value=finding.get(key)
            if isinstance(value,(list,tuple)) and len(value)==4 and all(isinstance(v,(int,float)) for v in value):result.append(expand(value))
        if not result and finding.get('endpoint') in points:
            result.append(point_box(points[finding['endpoint']],28))
        if not result:
            for endpoint in finding.get('endpoints') or []:
                if isinstance(endpoint,str) and endpoint in points:result.append(point_box(points[endpoint],28))
        if not result:
            for inst,node in nodes.items():
                if inst in (finding.get('component'),finding.get('obstacle')) or inst in finding.get('components',[]) or inst in finding.get('detail',''):
                    result.append(expand(node['footprint']))
        return result
    for index,finding in enumerate(report.get('checks',[])):
        if finding.get('result') not in ('fail','warn'):continue
        boxes=targets(finding)
        if finding['id']=='V19' and 'B1' in finding['detail']:
            boxes=[point_box(e['position'],32) for evidence in report.get('evidence',[]) if evidence['id']=='V14' for e in evidence.get('events',[]) if e['kind']=='crossing']
        add('finding:%s:%04d'%(finding['id'],index),'finding',finding['id']+' '+finding['detail'],boxes,
            check_id=finding['id'],finding_kind=finding.get('kind'),position=finding.get('position'),
            severity=finding['result'],full_sheet_context=not boxes)
    for evidence in report.get('evidence',[]):
        unmeasured=list(evidence.get('unchecked') or [])+list(evidence.get('marker_display',{}).get('unchecked') or [])
        for index,finding in enumerate(unmeasured):
            boxes=targets(finding)
            add('unchecked:%s:%04d'%(evidence['id'],index),'finding',evidence['id']+' 未校核：'+str(finding.get('detail') or finding.get('reason') or '需回读确认'),
                boxes,check_id=evidence['id'],severity='not_checked',full_sheet_context=not boxes)
    for budget in report.get('composition_budget',{}).get('items',[]):
        if budget['status'] not in ('over','fail'):continue
        candidates=[]
        if budget.get('nearest_run'):
            run=budget['nearest_run'];candidates.append({**run,'positions':[run['start'],run['end']]})
        if budget.get('nearest'):candidates.append(budget['nearest'])
        candidates.extend(budget.get('corridors',{}).get('violations',[]))
        for index,candidate in enumerate(candidates):
            add('budget:%s:%04d'%(budget['id'],index),'finding',budget['id']+' 净距 / 管段疑点',targets(candidate),check_id=budget['id'],severity='warn')
    return objects


def plan_regions(objects,size,viewbox):
    vx,vy,vw,vh=viewbox;sx,sy=size[0]/vw,size[1]/vh
    regions=[]
    for item in objects:
        item['region_ids']=[]
        for target in item['targets']:
            box=[max(0,min(size[0],math.floor((target[0]-vx)*sx))),max(0,min(size[1],math.floor((target[1]-vy)*sy))),
                 max(0,min(size[0],math.ceil((target[2]-vx)*sx))),max(0,min(size[1],math.ceil((target[3]-vy)*sy)))]
            if box[2]<=box[0] or box[3]<=box[1]:continue
            merged=False
            for region in regions:
                old=region['pixel_box'];union=[min(old[0],box[0]),min(old[1],box[1]),max(old[2],box[2]),max(old[3],box[3])]
                if (old==box or (not (old[2]+8<box[0] or box[2]+8<old[0] or old[3]+8<box[1] or box[3]+8<old[1])
                    and union[2]-union[0]<=160*sx and union[3]-union[1]<=160*sy)):
                    region['pixel_box']=union
                    if item['id'] not in region['object_ids']:region['object_ids'].append(item['id'])
                    merged=True;break
            if not merged:regions.append({'pixel_box':box,'object_ids':[item['id']]})
    for index,region in enumerate(regions):
        region['id']='region-%04d'%index
        for item in objects:
            if item['id'] in region['object_ids']:item['region_ids'].append(region['id'])
    components={o['component']:o for o in objects if o['kind']=='component'}
    for item in objects:
        if item['kind']=='port' and item['component'] in components:
            item['context_region_ids']=list(components[item['component']]['region_ids'])
        if not item['region_ids']:
            if item.get('full_sheet_context'):item['region_ids']=['full']
            else:item['unavailable_reason']=item.get('unavailable_reason','目标在当前图像范围之外')
        item['review']={'status':'unviewed'}
    return regions


def index_html(workdir,manifest):
    esc=lambda value:html.escape(str(value))
    encode=lambda path:base64.b64encode((workdir/path).read_bytes()).decode()
    labels={'unviewed':'未查看','confirmed':'已确认','questioned':'存疑'}
    counts={state:sum(o['review']['status']==state for o in manifest['objects']) for state in labels}
    whole={'confirmed':'已确认','questioned':'存疑','pending':'待回读','invalidated':'已失效'}.get(manifest.get('whole_sheet_review'),'待回读')
    width,height=manifest['png_size']
    out=['<!doctype html><meta charset="utf-8"><title>原理图局部回读</title>',
         '<style>body{font:15px sans-serif;margin:24px;max-width:1200px;color:#222}img{max-width:100%;image-rendering:pixelated}section{border:1px solid #bbb;padding:16px;margin:20px 0;max-width:960px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px;text-align:left}svg{width:100%;height:auto}.roi{fill:transparent;stroke:transparent;pointer-events:none}.roi:target{fill:#ef44441a;stroke:#ef4444;stroke-width:3}small{color:#555}</style>',
         '<h1>原理图局部回读</h1><p>绑定版本 '+esc(manifest['review_binding'][:12])+'。局部生成不代表已确认；整图签认与逐项结论分别记录。</p>',
         '<p>'+esc(' · '.join(labels[k]+' '+str(v) for k,v in counts.items()))+'；整图签认：'+esc(whole)+'</p>',
         '<p>%d 个对象 · %d 张局部图 · %d× PNG像素</p>'%(len(manifest['objects']),len(manifest['regions']),manifest['scale']),
         '<p><small>图像以绑定版本的像素嵌入本页。当前文件有效性请使用回读验证命令核实。</small></p>',
         '<h2 id="overview">完整图</h2><svg role="img" viewBox="0 0 %d %d"><image width="%d" height="%d" href="data:image/png;base64,%s"/>'%(width,height,width,height,encode(manifest['full_png']))]
    for region in manifest['regions']:
        x,y,right,bottom=region['pixel_box']
        out.append('<rect id="loc-%s" class="roi" x="%s" y="%s" width="%s" height="%s"/>'%(esc(region['id']),x,y,right-x,bottom-y))
    out+=['</svg>','<h2>对象清单</h2><table><tr><th>对象</th><th>状态</th><th>局部与备注</th></tr>']
    for item in manifest['objects']:
        links=' '.join('<a href="#'+('overview' if r=='full' else esc(r))+'">'+('全图' if r=='full' else esc(r))+'</a>' for r in item['region_ids'])
        links += ' '.join(' <a href="#'+esc(r)+'">元件全貌</a>' for r in item.get('context_region_ids',[]) if r not in item['region_ids'])
        note=item.get('unavailable_reason') or item['review'].get('note','')
        out.append('<tr><td>'+esc(item['label'])+'</td><td>'+labels[item['review']['status']]+'</td><td>'+links+'<br>'+esc(note)+'</td></tr>')
    out.append('</table>')
    for region in manifest['regions']:
        out.append('<section id="'+esc(region['id'])+'"><h2>'+esc(', '.join(region['object_ids']))+'</h2><p><a href="#loc-'+esc(region['id'])+'">在全图定位</a> · '+esc(manifest['scale'])+'× PNG像素</p><img alt="'+esc(region['id'])+'" src="data:image/png;base64,'+encode(region['file'])+'"></section>')
    return '\n'.join(out)+'\n'


def generate(workdir,scale=4):
    workdir=Path(workdir).resolve();started=time.monotonic()
    if not 1<=scale<=8:raise ValueError('Scale must be between 1 and 8')
    report,browser=source(workdir)
    png=(workdir/'sheet-readback.png').read_bytes()
    png_sha=hashlib.sha256(png).hexdigest()
    if png_sha!=report['artifacts']['files']['png']['sha256']:raise ValueError('PNG changed during generation')
    with Image.open(io.BytesIO(png)) as loaded:
        loaded.load();image=loaded.copy()
    objects=inventory(report);regions=plan_regions(objects,image.size,browser['viewbox']);images={}
    for region in regions:
        box=region['pixel_box']
        crop=image.crop(box).resize(((box[2]-box[0])*scale,(box[3]-box[1])*scale),Image.Resampling.NEAREST)
        payload=io.BytesIO();crop.save(payload,format='PNG');images[region['id']]=payload.getvalue()
        region.update(sha256=hashlib.sha256(images[region['id']]).hexdigest(),size=[crop.width,crop.height])
    manifest={'schema':'sheet-local-readback-v1','artifact_fingerprint':report['artifacts']['fingerprint'],
              'validation_fingerprint':validation_fingerprint(report),'png_sha256':png_sha,'png_size':list(image.size),
              'viewbox':browser['viewbox'],'scale':scale,'objects':objects,'regions':regions,
              'rasterizations':0,'png_decode_count':1,
              'coverage':{'total':len(objects),'covered':sum(bool(o['region_ids']) for o in objects),
                          'unavailable':[o['id'] for o in objects if not o['region_ids']]}}
    manifest['review_binding']=digest_json(binding_payload(manifest))
    folder=Path('readback')/manifest['review_binding']
    if workdir not in (workdir/folder).resolve().parents:raise ValueError('Readback folder escapes workspace')
    (workdir/folder).mkdir(parents=True,exist_ok=True)
    manifest['full_png']=str(folder/'full.png');(workdir/manifest['full_png']).write_bytes(png)
    for region in regions:
        region['file']=str(folder/(region['id']+'.png'));(workdir/region['file']).write_bytes(images[region['id']])
    if verify_report(workdir)['status']!='current':raise ValueError('Source artifacts changed during generation')
    apply_reviews(workdir,manifest)
    manifest['elapsed_s']=round(time.monotonic()-started,6)
    publish(workdir,manifest)
    refresh_reviews(workdir)
    manifest['elapsed_s']=round(time.monotonic()-started,6)
    write_json(workdir/MANIFEST,manifest)
    return manifest


def read_signed(path):
    value=json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value,dict):raise ValueError('Readback file must contain an object: '+path.name)
    if value.get('integrity')!=digest_json({k:v for k,v in value.items() if k!='integrity'}):
        raise ValueError('Readback file integrity mismatch: '+path.name)
    return value


def ledger(workdir):
    path=workdir/LEDGER
    return read_signed(path) if path.exists() else {'schema':'sheet-item-review-v1','versions':{}}


def apply_reviews(workdir,manifest):
    records=ledger(workdir)['versions'].get(manifest['review_binding'],{}).get('items',{})
    for item in manifest['objects']:
        item['review']=records.get(item['id'],{'status':'unviewed'})
        review=item['review']
        if review['status'] not in ('confirmed','questioned','unviewed'):
            raise ValueError('Invalid item review status')
        if review['status']!='unviewed' and (not review.get('reviewer','').strip() or not review.get('note','').strip()):
            raise ValueError('Explicit item reviewer and note required')


def publish(workdir,manifest):
    manifest['whole_sheet_review']=verify_report(workdir).get('perceptual_review',{}).get('status','pending')
    page=index_html(workdir,manifest)
    temporary=workdir/(INDEX+'.tmp');temporary.write_text(page,encoding='utf-8');temporary.replace(workdir/INDEX)
    manifest['html_sha256']=hashlib.sha256(page.encode()).hexdigest()
    write_json(workdir/MANIFEST,manifest)
    return manifest


def assess_manifest(workdir,report):
    """Assess derived files/reviews against an already verified/current report.

    This never calls verify_report, so validation can use it without a cycle.
    """
    workdir=Path(workdir);manifest=None
    try:
        manifest=read_signed(workdir/MANIFEST)
        if manifest.get('schema')!='sheet-local-readback-v1':raise ValueError('Unknown readback schema')
        if manifest['artifact_fingerprint']!=report['artifacts']['fingerprint'] or manifest['validation_fingerprint']!=validation_fingerprint(report):
            raise ValueError('Readback belongs to a different artifact/automatic-validation version')
        if manifest['png_sha256']!=report['artifacts']['files']['png']['sha256']:raise ValueError('Readback PNG binding mismatch')
        if digest_json(binding_payload(manifest))!=manifest['review_binding']:raise ValueError('Readback binding mismatch')
        folder=(workdir/'readback'/manifest['review_binding']).resolve()
        if workdir.resolve() not in folder.parents:raise ValueError('Readback folder escapes the workspace')
        files=[(manifest['full_png'],manifest['png_sha256'])]+[(r['file'],r['sha256']) for r in manifest['regions']]
        for name,expected in files:
            path=(workdir/name).resolve()
            if path.parent!=folder or file_digest(path)!=expected:raise ValueError('Readback image changed or missing: '+name)
        if file_digest(workdir/INDEX)!=manifest['html_sha256']:raise ValueError('Static readback report changed or missing')
        decisions=ledger(workdir)['versions'].get(manifest['review_binding'],{}).get('items',{})
        for item in manifest['objects']:
            if item['review']!=decisions.get(item['id'],{'status':'unviewed'}):raise ValueError('Review view differs from recorded explicit decisions')
        counts={state:sum(o['review']['status']==state for o in manifest['objects']) for state in ('confirmed','questioned','unviewed')}
        unavailable=[o['id'] for o in manifest['objects'] if not o['region_ids']]
        complete=not unavailable and counts['confirmed']==len(manifest['objects'])
        return {'status':'current','complete':complete,'review_status':'complete' if complete else 'questioned' if counts['questioned'] else 'pending',
                'review_binding':manifest['review_binding'],'review_counts':counts,'object_count':len(manifest['objects']),
                'crop_count':len(manifest['regions']),'unavailable':unavailable,'manifest':MANIFEST,'html':INDEX}
    except (OSError,ValueError,KeyError,TypeError) as error:
        return {'status':'invalidated','complete':False,'review_status':'invalidated','detail':str(error),
                'review_counts':{'confirmed':0,'questioned':0,'unviewed':len(manifest.get('objects',[])) if manifest else 0}}


def verify_bundle(workdir):
    workdir=Path(workdir).resolve()
    try:
        report,_=source(workdir)
        return assess_manifest(workdir,report)
    except (OSError,ValueError,KeyError) as error:
        return {'status':'invalidated','complete':False,'review_status':'invalidated','detail':str(error),
                'review_counts':{'confirmed':0,'questioned':0,'unviewed':0}}


def refresh_reviews(workdir):
    """Refresh only review display/delivery using existing measured evidence."""
    workdir=Path(workdir);verification=verify_report(workdir)
    if verification['status']!='current':raise ValueError('Source report changed during local review')
    report=json.loads((workdir/'validation-report.json').read_text())
    before=validation_fingerprint(report);artifacts=report['artifacts']
    enrich_report(report,workdir,catalog_path=artifacts['catalog_path'],tool_dir=artifacts['tool_dir'])
    if validation_fingerprint(report)!=before:raise ValueError('Review refresh changed automatic evidence fingerprint')
    write_report(report,workdir/'validation-report.json')


def record_items(workdir,object_ids,decision,reviewer,note):
    if decision not in ('confirmed','questioned','unviewed'):raise ValueError('Invalid item decision')
    workdir=Path(workdir).resolve();state=verify_bundle(workdir)
    if state['status']!='current':raise ValueError(state['detail'])
    if not reviewer.strip() or not note.strip():raise ValueError('Explicit reviewer and note are required')
    manifest=read_signed(workdir/MANIFEST);known={o['id'] for o in manifest['objects']}
    if not set(object_ids)<=known:raise ValueError('Unknown readback object: '+str(sorted(set(object_ids)-known)))
    records=ledger(workdir);version=records['versions'].setdefault(manifest['review_binding'],{'items':{},'history':[]})
    at=datetime.now(timezone.utc).isoformat()
    for oid in object_ids:
        value={'status':decision,'reviewer':reviewer,'note':note,'reviewed_at':at}
        version['items'][oid]=value;version['history'].append({'object_id':oid,**value})
    write_json(workdir/LEDGER,records)
    apply_reviews(workdir,manifest);publish(workdir,manifest)
    refresh_reviews(workdir)
    return verify_bundle(workdir)


def main():
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    gen=commands.add_parser('generate');gen.add_argument('workdir');gen.add_argument('--scale',type=int,default=4)
    verify=commands.add_parser('verify');verify.add_argument('workdir')
    review=commands.add_parser('record-item');review.add_argument('workdir');review.add_argument('objects',nargs='+')
    review.add_argument('--decision',choices=('confirmed','questioned','unviewed'),required=True)
    review.add_argument('--reviewer',required=True);review.add_argument('--note',required=True)
    args=parser.parse_args()
    try:
        if args.command=='generate':
            if not 1<=args.scale<=8:raise ValueError('Scale must be between 1 and 8')
            manifest=generate(args.workdir,args.scale)
            result={**verify_bundle(args.workdir),'elapsed_s':manifest['elapsed_s'],'rasterizations':0}
        elif args.command=='verify':result=verify_bundle(args.workdir)
        else:result=record_items(args.workdir,args.objects,args.decision,args.reviewer,args.note)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if result['status']=='current' else 1
    except (OSError,ValueError,KeyError) as error:
        print(json.dumps({'status':'invalidated','complete':False,'detail':str(error)},ensure_ascii=False));return 1


if __name__=='__main__':
    raise SystemExit(main())
