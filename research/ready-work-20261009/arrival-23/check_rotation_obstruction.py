"""Reproduce the fixed-port rotation obstruction from current project inputs.

This is a read-only combinatorial certificate, not a new rendering rule or a
license to mirror a symbol. NetworkX supplies an optional independent check.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET
from ruamel.yaml import YAML

ROOT=Path(__file__).resolve().parents[3]
PUMPS=('EDP-001','EMP-001')
PORTS={'suction':'SUCTION','pressure_out':'PRESSURE','case_drain':'CASE'}


def cyclic_order(points, angle):
    # All allowed rotations preserve orientation. Sort the actual port rays in
    # SVG's y-down coordinates; the starting ray is immaterial.
    cosine,sine=math.cos(math.radians(angle)),math.sin(math.radians(angle))
    rotated={name:(x*cosine-y*sine,x*sine+y*cosine) for name,(x,y) in points.items()}
    order=tuple(sorted(rotated,key=lambda key:math.atan2(rotated[key][1],rotated[key][0])%(2*math.pi)))
    return min(order[i:]+order[:i] for i in range(len(order)))


def faces(orders):
    sigma={(pump,edge):(pump,order[(i+1)%3]) for pump,order in orders.items() for i,edge in enumerate(order)}
    alpha={(pump,edge):(PUMPS[1-i],edge) for i,pump in enumerate(PUMPS) for edge in orders[pump]}
    unseen=set(sigma);result=[]
    while unseen:
        start=min(unseen);dart=start;walk=[]
        while dart not in walk:
            walk.append(dart);unseen.remove(dart);dart=sigma[alpha[dart]]
        assert dart==start
        result.append(['%s:%s'%d for d in walk])
    return result


def independent_check(orders):
    try:
        import networkx as nx
    except ImportError:
        return {'status':'not_executed','reason':'optional NetworkX unavailable; six-dart certificate remains above'}
    data={pump:list(orders[pump]) for pump in PUMPS}
    data.update({network:list(PUMPS) for network in PORTS.values()})
    embedding=nx.PlanarEmbedding();embedding.set_data(data)
    abstract_planar=nx.check_planarity(nx.Graph(embedding))[0]
    try:
        embedding.check_structure()
        return {'version':nx.__version__,'abstract_graph_planar':abstract_planar,'fixed_rotation_planar':True}
    except nx.NetworkXException as error:
        return {'version':nx.__version__,'abstract_graph_planar':abstract_planar,'fixed_rotation_planar':False,'error':str(error)}


def certificate():
    project=ROOT/'1#系统原理图'
    intent=YAML(typ='safe').load(project/'1#系统.intent.yaml')
    layout=json.loads((project/'1#系统.layout.json').read_text())
    catalog=json.loads((project/'component-catalog.json').read_text())
    types={c['component_type']:c for c in catalog['components']}
    required=[['TANK-001.suction_out','EMP-001.suction'],
              ['TANK-001.suction_out','FSOV-001','EDP-001.suction'],
              ['EDP-001.pressure_out','@PRESS'],['EMP-001.pressure_out','@PRESS'],
              ['EDP-001.case_drain','@CASE'],['EMP-001.case_drain','@CASE']]
    input_paths=[]
    for path in required:
        assert path in intent['paths'],('Signed obstruction paths changed; re-evaluate certificate',path)
        input_paths.append({'anchor':'paths[%d]'%intent['paths'].index(path),'path':path})
    points={};symbols={}
    hash_file=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    for pump in PUMPS:
        entry=types[intent['parts'][pump]]
        assert layout['nodes'][pump]['symbol']==entry['symbol']['asset']
        symbol=project/entry['symbol']['asset'];svg=ET.parse(symbol).getroot()
        x,y,w,h=map(float,svg.attrib['viewBox'].replace(',',' ').split())
        ports={e.attrib['data-port-id']:e.attrib for e in svg.iter() if e.get('data-port-id') in PORTS}
        assert set(ports)==set(PORTS)
        points[pump]={PORTS[p]:(float(e['cx'])-x-w/2,float(e['cy'])-y-h/2) for p,e in ports.items()}
        symbols[pump]={'asset':str(symbol.relative_to(ROOT)),'sha256':hash_file(symbol),'viewBox':[x,y,w,h],
                       'ports':{p:{k:e[k] for k in ('cx','cy','data-anchor-direction')} for p,e in ports.items()},
                       'clockwise_network_order':cyclic_order(points[pump],0)}
    combinations=[]
    for a in (0,90,180,270):
        for b in (0,90,180,270):
            orders={p:cyclic_order(points[p],angle) for p,angle in zip(PUMPS,(a,b))}
            walk=faces(orders);chi=2-3+len(walk)
            combinations.append({'rotations':dict(zip(PUMPS,(a,b))),'cyclic_orders':orders,'face_walks':walk,
                                 'vertices':2,'edges':3,'faces':len(walk),'euler_characteristic':chi,'planar_required_faces':3})
            assert len(walk)==1 and chi==0
    orders={p:cyclic_order(points[p],0) for p in PUMPS}
    opposite={PUMPS[0]:orders[PUMPS[0]],PUMPS[1]:tuple(reversed(orders[PUMPS[1]]))}
    control=faces(opposite);assert len(control)==3
    return {'claim':'No planar routing realizes these same cyclic port orders and three internally disjoint common-network paths.',
            'scope':'Current 23-part project; abstract K2,3 is planar, its signed fixed rotation system is not.',
            'input_sha256':{f:hash_file(project/f) for f in ['1#系统.intent.yaml','1#系统.layout.json','component-catalog.json']},
            'input_paths':input_paths,'degree_two_suction_component':{'instance':'FSOV-001','main_path':types[intent['parts']['FSOV-001']]['main_path']},
            'symbols':symbols,'allowed_rotation_combinations':combinations,'independent_networkx':independent_check(orders),
            'orientation_reversal_control':{'allowed':False,'reason':'Counterfactual only; mirror/port identity changes are forbidden.',
                'faces':len(control),'euler_characteristic':2-3+len(control),'independent_networkx':independent_check(opposite)}}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('-o','--output',type=Path);args=parser.parse_args()
    text=json.dumps(certificate(),ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(text)
    else:print(text,end='')
