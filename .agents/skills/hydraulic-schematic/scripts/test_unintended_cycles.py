"""Extra loops are detected through the final SVG topology CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from ruamel.yaml import YAML
from test_entrypoints import make_render_workspace,SKILL
NS='{http://www.w3.org/2000/svg}'

class UnintendedCyclesCLI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='extra-cycle-');self.addCleanup(self.temp.cleanup)
        self.work=make_render_workspace(Path(self.temp.name),SKILL/'assets/fixtures/l0-small-seed')
        self.yaml=YAML()
        path=self.work/'1#系统.intent.yaml';self.intent=self.yaml.load(path)
        self.intent['parts'].update({n:'pressure_gauge' for n in ('GA-001','GB-001','GC-001')})
        self.intent['taps']=[{'sensor':'GA-001.pressure_sense','at':'GB-001.pressure_sense'},
                             {'sensor':'GA-001.pressure_sense','at':'GC-001.pressure_sense'}]
        path=self.work/'1#系统.layout.json';layout=json.loads(path.read_text());layout.setdefault('label_pos',{}).update({'GA-001':'right','GB-001':'right','GC-001':'below'})
        layout['canvas'].update(width=2000,height=1500)
        layout['drawable'].update(width=1970,height=1500)
        for name,x,y,rot in [('GA-001',1300,200,0),('GB-001',1501,500,180),('GC-001',1732,235,90)]:
            layout['nodes'][name]={'x':x,'y':y,'w':63,'h':67,'rot':rot,'symbol':'symbols/pressure-gauge.svg'}
            layout['labels'][name]=name
        path.write_text(json.dumps(layout))

    def drawing(self,damaged=False,ring=False,split=False):
        if ring:self.intent['taps'].append({'sensor':'GB-001.pressure_sense','at':'GC-001.pressure_sense'})
        with (self.work/'1#系统.intent.yaml').open('w') as f:self.yaml.dump(self.intent,f)
        p=subprocess.run([sys.executable,str(self.work/'render_l0_sheet.py'),str(self.work)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        if ring:
            routes=['1332,267 1332,450 1532,450 1532,500',
                    '1332,267 1332,287 1250,287 1250,170 1712,170 1712,267 1732,267',
                    '1532,500 1532,480 1700,480 1700,267 1732,267']
            junctions=[(1332,287),(1532,480),(1712,267)]
        elif damaged:
            routes=['1332,267 1332,287 1532,287 1532,500',
                    '1332,267 1332,327 1712,327 1712,267 1732,267']
            junctions=[(1332,287),(1532,327)]
        else:
            routes=['1332,267 1332,327 1532,327 1532,500',
                    '1332,267 1332,287 1712,287 1712,267 1732,267']
            junctions=[(1332,287)]
        for i,points in enumerate(routes):
            wire=next(e for e in root.iter() if e.tag==NS+'polyline' and e.get('data-edge')=='taps[%d]'%i)
            wire.set('points',points)
            if split and i==0:
                wire.set('points','1332,267 1332,287 1332,307')
                group=next(e for e in root.iter() if e.get('id')=='lines')
                ET.SubElement(group,NS+'polyline',{**wire.attrib,'id':'split-tap-tail','points':'1332,307 1332,327 1532,327 1532,500'})
        group=next(e for e in root.iter() if e.get('id')=='junctions')
        for e in list(group):
            if float(e.get('cx','0'))>1250:group.remove(e)
        for i,(x,y) in enumerate(junctions):
            ET.SubElement(group,NS+'circle',{'id':'gas-join-%d'%i,'class':'jn','cx':str(x),'cy':str(y),'r':'3'})
        ET.register_namespace('',NS[1:-1]);svg.write_text(ET.tostring(root,encoding='unicode'))
        p=subprocess.run([sys.executable,str(self.work/'validate_sheet.py'),str(self.work)],capture_output=True,text=True,timeout=90)
        self.assertIn(p.returncode,(0,1),p.stdout+p.stderr)
        return json.loads((self.work/'validation-report.json').read_text())

    def loops(self,r):return [f for f in r['checks'] if f.get('kind')=='unexpected_cycle']

    def test_taps_rectangle_is_not_accepted_as_the_same_connected_net(self):
        r=self.drawing(damaged=True);hits=self.loops(r)
        self.assertTrue(hits)
        self.assertEqual(hits[0]['actual_cycle_rank'],1)
        self.assertEqual(hits[0]['expected_cycle_rank'],0)
        self.assertTrue(hits[0]['positions']);self.assertIn('taps[0]',hits[0]['input_anchors'])
        self.assertEqual(next(c['status'] for c in r['coverage'] if c['id']=='V10'),'fail')

    def test_single_t_branch_and_shared_stub_do_not_add_cycles(self):
        self.assertEqual(self.loops(self.drawing()),[])

    def test_collinear_storage_fragments_do_not_add_cycles(self):
        self.assertEqual(self.loops(self.drawing(split=True)),[])

    def test_explicit_source_ring_is_not_banned(self):
        r=self.drawing(ring=True)
        self.assertEqual(self.loops(r),[])
        net=next(n for n in r['topology']['networks'] if 'GA-001.pressure_sense' in n['terminals'])
        self.assertEqual(net['cycle_evidence']['expected_rank'],1)
        self.assertEqual(net['cycle_evidence']['actual_rank'],1)

    def test_missing_display_evidence_does_not_assert_a_measured_cycle(self):
        self.drawing(damaged=True)
        from sheet_geometry import load_geometry
        from topology_reconciliation import reconcile_topology
        root=ET.parse(self.work/'1#系统原理图.svg').getroot()
        layout=json.loads((self.work/'1#系统.layout.json').read_text())
        catalog=json.loads((self.work/'component-catalog.json').read_text())
        geometry=load_geometry(root,layout,lambda ref:self.work/ref)
        result=reconcile_topology(root,geometry,self.intent,catalog,layout,{'status':'not_checked','reason':'Missing display evidence'})
        self.assertEqual(result['coverage_status'],'not_checked')
        self.assertFalse([f for f in result['findings'] if f.get('kind')=='unexpected_cycle'])
        self.assertTrue(any(n['cycle_evidence']['status']=='not_checked' for n in result['networks']))

if __name__=='__main__':unittest.main()
