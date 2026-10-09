"""Version-bound local PNG readback. Cropping never records perceptual signoff."""
import argparse
import base64
import hashlib
import html
import io
import json
import math
from pathlib import Path
import time

from PIL import Image
from proofreading_evidence import digest_json, file_digest, verify_report, validation_fingerprint

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
    browser=json.loads((workdir/'browser-evidence.json').read_text())
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
        for value in finding.get('positions',[]):
            if isinstance(value,(list,tuple)) and len(value) in (2,4) and all(isinstance(v,(int,float)) for v in value):
                result.append(point_box(value,28) if len(value)==2 else expand(value))
        for key in ('box','bbox','text_bbox','footprint'):
            value=finding.get(key)
            if isinstance(value,(list,tuple)) and len(value)==4 and all(isinstance(v,(int,float)) for v in value):result.append(expand(value))
        if not result:
            for endpoint in finding.get('endpoints',[]):
                if isinstance(endpoint,str) and endpoint in points:result.append(point_box(points[endpoint],28))
        if not result:
            for inst,node in nodes.items():
                if inst in (finding.get('component'),finding.get('obstacle')) or inst in finding.get('components',[]) or inst in finding.get('detail',''):
                    result.append(expand(node['footprint']))
        return result
    for index,finding in enumerate(report.get('checks',[])):
        if finding.get('result') not in ('fail','warn'):continue
        boxes=targets(finding)
        add('finding:%s:%04d'%(finding['id'],index),'finding',finding['id']+' '+finding['detail'],boxes,
            check_id=finding['id'],finding_kind=finding.get('kind'),position=finding.get('position'),
            severity=finding['result'],full_sheet_context=not boxes)
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
    for item in objects:
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
    width,height=manifest['png_size']
    out=['<!doctype html><meta charset="utf-8"><title>原理图局部回读</title>',
         '<style>body{font:15px sans-serif;margin:24px;max-width:1200px;color:#222}img{max-width:100%;image-rendering:pixelated}section{border:1px solid #bbb;padding:16px;margin:20px 0;max-width:960px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:6px;text-align:left}svg{width:100%;height:auto}.roi{fill:transparent;stroke:transparent;pointer-events:none}.roi:target{fill:#ef44441a;stroke:#ef4444;stroke-width:3}small{color:#555}</style>',
         '<h1>原理图局部回读</h1><p>绑定版本 '+esc(manifest['review_binding'][:12])+'。局部生成不代表已确认；整图签认与逐项结论分别记录。</p>',
         '<p>'+esc(' · '.join(labels[k]+' '+str(v) for k,v in counts.items()))+'</p>',
         '<p><small>图像以绑定版本的像素嵌入本页。当前文件有效性请使用回读验证命令核实。</small></p>',
         '<h2 id="overview">完整图</h2><svg role="img" viewBox="0 0 %d %d"><image width="%d" height="%d" href="data:image/png;base64,%s"/>'%(width,height,width,height,encode(manifest['full_png']))]
    for region in manifest['regions']:
        x,y,right,bottom=region['pixel_box']
        out.append('<rect id="loc-%s" class="roi" x="%s" y="%s" width="%s" height="%s"/>'%(esc(region['id']),x,y,right-x,bottom-y))
    out+=['</svg>','<h2>对象清单</h2><table><tr><th>对象</th><th>状态</th><th>局部与备注</th></tr>']
    for item in manifest['objects']:
        links=' '.join('<a href="#'+('overview' if r=='full' else esc(r))+'">'+('全图' if r=='full' else esc(r))+'</a>' for r in item['region_ids'])
        note=item.get('unavailable_reason') or item['review'].get('note','')
        out.append('<tr><td>'+esc(item['label'])+'</td><td>'+labels[item['review']['status']]+'</td><td>'+links+'<br>'+esc(note)+'</td></tr>')
    out.append('</table>')
    for region in manifest['regions']:
        out.append('<section id="'+esc(region['id'])+'"><h2>'+esc(', '.join(region['object_ids']))+'</h2><p><a href="#loc-'+esc(region['id'])+'">在全图定位</a> · '+esc(manifest['scale'])+'× PNG像素</p><img alt="'+esc(region['id'])+'" src="data:image/png;base64,'+encode(region['file'])+'"></section>')
    return '\n'.join(out)+'\n'


def generate(workdir,scale=4):
    workdir=Path(workdir).resolve();started=time.monotonic()
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
    folder=Path('readback')/manifest['review_binding'];(workdir/folder).mkdir(parents=True,exist_ok=True)
    manifest['full_png']=str(folder/'full.png');(workdir/manifest['full_png']).write_bytes(png)
    for region in regions:
        region['file']=str(folder/(region['id']+'.png'));(workdir/region['file']).write_bytes(images[region['id']])
    if verify_report(workdir)['status']!='current':raise ValueError('Source artifacts changed during generation')
    page=index_html(workdir,manifest);(workdir/INDEX).write_text(page,encoding='utf-8')
    manifest['html_sha256']=hashlib.sha256(page.encode()).hexdigest()
    manifest['elapsed_s']=round(time.monotonic()-started,6)
    write_json(workdir/MANIFEST,manifest)
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    gen=commands.add_parser('generate');gen.add_argument('workdir');gen.add_argument('--scale',type=int,default=4)
    args=parser.parse_args()
    try:
        if not 1<=args.scale<=8:raise ValueError('Scale must be between 1 and 8')
        result=generate(args.workdir,args.scale)
        print(json.dumps({'status':'current','manifest':str(Path(args.workdir)/MANIFEST),'html':str(Path(args.workdir)/INDEX),
                          'object_count':len(result['objects']),'crop_count':len(result['regions']),'elapsed_s':result['elapsed_s']},ensure_ascii=False))
        return 0
    except (OSError,ValueError,KeyError) as error:
        print(json.dumps({'status':'invalidated','detail':str(error)},ensure_ascii=False));return 1


if __name__=='__main__':
    raise SystemExit(main())
