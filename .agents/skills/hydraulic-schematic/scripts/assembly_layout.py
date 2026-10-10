"""R17: deterministic single-row assembly layout using source ports and glyph ink.

No tank/bus inference or path solver. Unsupported graphs/orientations fail closed.
Coordinates never come from the reference; only labels, symbol choice and rot do.
"""
import copy
import math
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
from browser_evidence import collect
from endpoint_usage import resolve_symbol
from sheet_geometry import load_geometry
from layout_contract import make_contract, drawable_bounds, pipe_half_width
from text_checks import glyph_paint, display_effects


def reject(detail):
    raise SystemExit('装配单行布局 R17: '+detail+'；请提供显式布局。')


def source_node(inst,typ,reference,source_dir,catalog_dir):
    selected=reference.get('nodes',{}).get(inst,{})
    asset=selected.get('symbol') or typ.get('symbol',{}).get('asset')
    if not asset: reject(inst+' 无符号资产')
    path=resolve_symbol(asset,source_dir,catalog_dir)
    try:
        source=ET.parse(path).getroot()
        vx,vy,w,h=map(float,source.get('viewBox','').replace(',',' ').split())
        if min(w,h)<=0 or not all(math.isfinite(v) for v in (vx,vy,w,h)): raise ValueError('invalid viewBox')
    except (OSError,ValueError,ET.ParseError) as error:
        reject(inst+' 符号无法读取: '+str(error))
    main=typ.get('main_path') or {}
    if set(main)!= {'in','out'}: reject(inst+' 缺少二端主路')
    rotations=[selected['rot']] if 'rot' in selected else [0,90,180,270]
    for rotation in rotations:
        if rotation not in (0,90,180,270): reject(inst+' 挂装角必须为 0/90/180/270')
        dx,dy={0:(0,0),90:(h,0),180:(w,h),270:(0,w)}[rotation]
        root=ET.fromstring('<svg><g id="inst-%s" transform="translate(%s,%s) rotate(%s) translate(%s,%s)"/></svg>' % (inst,dx,dy,rotation,-vx,-vy))
        node={'x':0.,'y':0.,'w':w,'h':h,'rot':rotation,'symbol':str(path)}
        measured=load_geometry(root,{'nodes':{inst:node}},lambda _:path)
        if measured['issues']: reject(inst+' 端口几何未校核: '+str(measured['issues']))
        geometry=measured['nodes'][inst]
        incoming=geometry['ports'].get(main['in']);outgoing=geometry['ports'].get(main['out'])
        if (incoming and outgoing and math.dist(incoming['direction'],(-1,0))<.001 and
                math.dist(outgoing['direction'],(1,0))<.001 and
                abs(incoming['position'][1]-outgoing['position'][1])<.001 and
                incoming['position'][0]<outgoing['position'][0]):
            return node,geometry,main
    reject(inst+' 现有挂装不支持左入右出水平主路（不自动换端口或镜像）')


def measure_labels(intent,catalog,layout,source_dir,catalog_dir):
    from render_l0_sheet import Sheet,css
    sheet=Sheet(intent,copy.deepcopy(layout),catalog,cat_dir=str(catalog_dir),workdir=str(source_dir))
    sheet.place()
    fragments=['<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2000 2000"><style>'+css(1.2)+'</style>']
    fragments+=sheet.symbols()
    for placement in ('below','above'):
        sheet.L['label_pos']={inst:placement for inst in layout['nodes']}
        fragments+=['<g id="measure-'+placement+'">']+sheet.texts()+['</g>']
    fragments.append('</svg>')
    with tempfile.TemporaryDirectory(prefix='assembly-labels-') as directory:
        path=Path(directory)/'labels.svg';path.write_text('\n'.join(fragments))
        browser=collect(path)
    if browser.get('status')!='pass': reject('文字测量 not_checked: '+browser.get('reason','browser unavailable'))
    result={inst:{'below':[],'above':[]} for inst in layout['nodes']}
    for row in browser['elements']:
        inst=row['attrs'].get('data-label-for')
        if inst not in result or row['tag']!='text':continue
        placement=next((a['id'][8:] for a in row['ancestors'] if a.get('id') in ('measure-below','measure-above')),None)
        if not placement: continue
        if (not row['visible'] or glyph_paint(row) is not True or row.get('ink_status')!='pass' or
                not row.get('ink_bbox') or display_effects(row)): reject(inst+' 字形测量 not_checked')
        result[inst][placement].append(row['ink_bbox'])
    if any(not boxes for labels in result.values() for boxes in labels.values()): reject('缺少成员标签实际字形')
    return result,{'renderer':browser['renderer'],'font_environment':browser['font_environment'],
                   'measurement_svg_sha256':browser['svg_sha256']}


def rules(intent,catalog,params,ref=None,source_dir=None,catalog_dir=None):
    from preflight import preflight
    contract=preflight(intent,catalog)
    if not contract['ok']:
        reject('预检未通过: '+ '; '.join(f['message'] for f in contract['findings'] if f['level']=='ERROR'))
    ref=ref or {};P=params
    source_dir=Path(source_dir or Path.cwd())
    catalog_dir=Path(catalog_dir or Path(__file__).resolve().parent.parent/'assets/component-library')
    assemblies=intent.get('assemblies') or {};paths=intent.get('paths') or []
    if len(assemblies)!=1 or len(paths)!=1 or intent.get('taps') or intent.get('groups'):
        reject('仅支持一个装配、一条 extern→成员链→extern，无 taps/groups 分支')
    path=paths[0];chain=path[1:-1];assembly=next(iter(assemblies.values()))
    if (len(chain)<2 or len(set(chain))!=len(chain) or set(chain)!=set(intent['parts']) or
            set(chain)!=set(assembly['members']) or path[0]==path[-1] or
            set((path[0],path[-1]))!=set(intent.get('extern',{}))):
        reject('路径必须恰好遍历所有成员一次，两端为已声明 extern，禁止母线/重复/额外成员')
    for key in ('ASSEMBLY_START_X','ASSEMBLY_RUN_Y','ASSEMBLY_STUB_IN','ASSEMBLY_STUB_OUT','ASSEMBLY_GAP_CAP','BOX_GAP','ASSEMBLY_TEXT_CLEAR'):
        if not math.isfinite(P[key]) or P[key]<0: reject('无效参数 '+key)
    if P['BOX_GAP']<40 or P['ASSEMBLY_TEXT_CLEAR']<6 or P['ASSEMBLY_GAP_CAP']<P['BOX_GAP']:
        reject('B5≥40、B7≥6 且软上限≥盒距下限不可放宽')
    types={c['component_type']:c for c in catalog['components']};nodes={};geometries={};mains={}
    for inst in chain:
        if intent['parts'][inst] not in types: reject(inst+' 类型未登记')
        node,geometry,main=source_node(inst,types[intent['parts'][inst]],ref,source_dir,catalog_dir)
        node['y']=P['ASSEMBLY_RUN_Y']-geometry['ports'][main['in']]['position'][1]
        nodes[inst]=node;geometries[inst]=geometry;mains[inst]=main
    layout=dict(layout_version='layout-engine-assembly-1',source_l0='',note='R17 单行装配；实际 SVG 足迹/端口与浏览器字形；禁止拓扑猜测。',
                canvas={'width':P['CANVAS_W'],'height':P['CANVAS_H']},
                **make_contract(P['CANVAS_W'], P['CANVAS_H'], P['EDGE_MARGIN']),
                style={'base_line_width_T':1.2,'symbol_stroke_width':2,'suction_marker_S':8},nodes=nodes,buses={},externs={},
                labels={inst:ref.get('labels',{}).get(inst,inst) for inst in chain},label_pos={},
                group_padding=14,group_label_gap=10,legend=copy.deepcopy(P['LEGEND']),title_block=copy.deepcopy(P['TITLE']))
    labels,provenance=measure_labels(intent,catalog,layout,source_dir,catalog_dir)
    placed=[];decisions=[];all_boxes=[]
    def boxes(inst,placement):
        node=nodes[inst];box=geometries[inst]['footprint']
        return [('footprint',[box[0],box[1]+node['y'],box[2],box[3]+node['y']])]+[('text',b) for b in labels[inst][placement]]
    for inst in chain:
        placement='below';current=boxes(inst,placement)
        base=P['ASSEMBLY_START_X'] if not placed else nodes[placed[-1]]['x']+geometries[placed[-1]]['footprint'][2]+P['BOX_GAP']
        def required(items):
            x=base
            for kind,b in items:
                for other_kind,other in all_boxes:
                    if kind==other_kind=='footprint':continue
                    vertical=max(b[1]-other[3],other[1]-b[3],0)
                    if vertical<P['ASSEMBLY_TEXT_CLEAR']:
                        horizontal=math.sqrt(P['ASSEMBLY_TEXT_CLEAR']**2-vertical**2)
                        x=max(x,other[2]+horizontal-b[0])
            return x
        x=required(current)
        gap=(x-nodes[placed[-1]]['x']-geometries[placed[-1]]['footprint'][2]) if placed else 0
        if placed and gap>P['ASSEMBLY_GAP_CAP']:
            placement='above';current=boxes(inst,placement);x=base
            if required(current)>base+.001: reject(inst+' above 标签仍不足净空，单行软上限不能满足')
        # Renderer text anchors are serialized to 0.1 units. Round outward so
        # a measured 6-unit clearance cannot become 5.95 in the final SVG.
        x=math.ceil(x*10-1e-8)/10
        nodes[inst]['x']=x;layout['label_pos'][inst]=placement
        all_boxes.extend((kind,[b[0]+x,b[1],b[2]+x,b[3]]) for kind,b in current)
        decisions.append({'component':inst,'label_pos':placement,'x':x,'gap':(x-nodes[placed[-1]]['x']-geometries[placed[-1]]['footprint'][2]) if placed else None})
        placed.append(inst)
    for endpoint,inst,want,stub,anchor in ((path[0],chain[0],'in',-P['ASSEMBLY_STUB_IN'],'right'),
                                          (path[-1],chain[-1],'out',P['ASSEMBLY_STUB_OUT'],'left')):
        port=geometries[inst]['ports'][mains[inst][want]]['position']
        layout['externs'][endpoint]={'x':nodes[inst]['x']+port[0]+stub,'y':P['ASSEMBLY_RUN_Y'],'anchor':anchor,
                                    'label':ref.get('externs',{}).get(endpoint,{}).get('label',endpoint)}
    # Keep the legend below the enclosure; title remains at its declared canvas band.
    layout['legend']['y']=max(b[3] for _,b in all_boxes)+100
    layout['legend']['h']=max(310,layout['legend']['h'])
    layout['boundary_terminals']=[[e['x'],e['y']] for e in layout['externs'].values()]
    layout['assembly_layout']={'rule':'R17','decisions':decisions,'text_measurement':provenance,
                               'params':{k:P[k] for k in P if k.startswith('ASSEMBLY_') or k=='BOX_GAP'}}
    return layout,{'assembly_row':chain,'boxes':all_boxes,'rows':{'assembly':chain},'stacks':{}}


def guard(layout,structure,params):
    # Never drift a node away from its measured port-aligned row.
    boxes=[b for _,b in structure['boxes']]
    x0,y0,x1,y1=drawable_bounds(layout)
    padding=layout['group_padding']+.75*layout['style']['base_line_width_T']
    if any(b[0]<x0+padding or b[1]<max(y0+padding,85) or b[2]>x1-padding or b[3]>y1-padding for b in boxes):
        reject('成员/实际字形越出可绘制区域；调整画幅/起点/主路高度')
    ends=list(layout['externs'].values())
    left=min(b[0] for b in boxes)-padding;right=max(b[2] for b in boxes)+padding
    if (ends[0]['x']>=left or ends[-1]['x']<=right or
            any(e['x']<x0+20 or e['x']>x1-20 for e in ends)):
        reject('extern 引出长度必须越过带内距围框并留在画幅内')
    legend=layout['legend'];title=layout['title_block']
    if (legend['y']+legend['h']>title['y']-14 or title['y']+title['h']>layout['canvas']['height'] or
            any(panel['x']<0 or panel['y']<0 or min(panel['w'],panel['h'])<=0 or
                panel['x']+panel['w']>layout['canvas']['width'] for panel in (legend,title))):
        reject('图例/图签画幅不足')
    return layout,{'guard':'R17 measured assembly row (no drift)','constraints':len(boxes)+2,
                   'violations_at_rule':[],'drifted':{},'zero_drift':True,'assembly_layout':layout['assembly_layout']}
