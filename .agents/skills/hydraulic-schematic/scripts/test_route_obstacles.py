"""Real renderer CLI regressions; final SVG checks do not call router predicates."""
import copy,json,subprocess,sys,tempfile,unittest,xml.etree.ElementTree as ET
from pathlib import Path
from test_entrypoints import make_render_workspace,SKILL

class HardRouting(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='route-obstacles-');self.addCleanup(self.temp.cleanup)
        self.work=make_render_workspace(Path(self.temp.name),SKILL/'assets/fixtures/l0-small-seed')
        self.layout=json.loads((self.work/'1#系统.layout.json').read_text())
        self.intent=dict(catalog='comac-hydraulic-components@0.7-draft',l0_version='1.1',system='HARD-ROUTING',maturity='concept',extern={},parts={n:'pressure_filter' for n in ('A','B','BLOCK')},paths=[['A','B']],unknown=[])
        self.layout.update(nodes={n:self.node(x,300) for n,x in [('A',400),('B',1000),('BLOCK',700)]},externs={},buses={},labels={n:n for n in self.intent['parts']},label_pos={n:'above' for n in self.intent['parts']},lanes=[180,750],vlanes=[350,1200],boundary_terminals=[])
    def node(self,x,y):return dict(x=x,y=y,w=80,h=80,symbol='symbols/filter-line-shutoff-stroke.svg')
    def run_renderer(self):
        (self.work/'1#系统.intent.yaml').write_text(json.dumps(self.intent))
        (self.work/'1#系统.layout.json').write_text(json.dumps(self.layout))
        return subprocess.run([sys.executable,'-B',str(self.work/'render_l0_sheet.py'),str(self.work)],capture_output=True,text=True,timeout=60)
    def lines(self):
        return [e for e in ET.parse(self.work/'1#系统原理图.svg').iter() if e.get('class','').startswith('ln-')]
    def clear_of(self,rect):
        for wire in self.lines():
            pts=[tuple(map(float,p.split(','))) for p in wire.get('points','').split()]
            for a,b in zip(pts,pts[1:]):
                if a[0]==b[0]:hit=rect[0]+.01<a[0]<rect[2]-.01 and max(min(a[1],b[1]),rect[1])<min(max(a[1],b[1]),rect[3])-.01
                else:
                    self.assertEqual(a[1],b[1]);hit=rect[1]+.01<a[1]<rect[3]-.01 and max(min(a[0],b[0]),rect[0])<min(max(a[0],b[0]),rect[2])-.01
                self.assertFalse(hit,(wire.attrib,a,b,rect))
    def test_path_detours_before_scoring_and_is_deterministic(self):
        p=self.run_renderer();self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.clear_of((685.3,285.3,794.7,394.7))
        one=(self.work/'1#系统原理图.svg').read_bytes();p=self.run_renderer();self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(one,(self.work/'1#系统原理图.svg').read_bytes())
    def test_blocked_terminal_does_not_exempt_neighbor_or_leave_stale_output(self):
        self.layout['nodes']['BLOCK']=self.node(475,300)
        stale=('1#系统原理图.svg','1#系统原理图-topology.json','1#系统原理图-topology.md','sheet-readback.png','sheet-readback.png.evidence.json','validation-report.json','readback-manifest.json','readback.html')
        for f in stale:(self.work/f).write_text('stale')
        p=self.run_renderer();self.assertNotEqual(p.returncode,0)
        error=json.loads((self.work/'routing-error.json').read_text());self.assertEqual(error['anchor'],'paths[0][0->1]')
        self.assertIn('BLOCK',[o['obstacle'] for o in error['obstacles']])
        for f in stale:self.assertFalse((self.work/f).exists(),f)
        self.assertEqual(json.loads((self.work/'1#系统.layout.json').read_text()),self.layout)
    def test_bus_trunk_cannot_cut_through_body(self):
        self.intent['paths']=[['A','@P'],['B','@P']];self.layout['buses']={'P':{'kind':'v','x':700}}
        self.layout['nodes'].update(B=self.node(400,600),BLOCK=self.node(660,430))
        p=self.run_renderer()
        if p.returncode:
            e=json.loads((self.work/'routing-error.json').read_text());self.assertIn('buses.P',e['anchor']);self.assertIn('BLOCK',[o['obstacle'] for o in e['obstacles']])
        else:self.clear_of((645.3,415.3,754.7,524.7))
    def test_bus_branch_cannot_exempt_first_segment(self):
        self.intent['paths']=[['A','@P']];self.layout['buses']={'P':{'kind':'v','x':1100}}
        self.layout['nodes']['BLOCK']=self.node(475,300)
        p=self.run_renderer();self.assertNotEqual(p.returncode,0)
        self.assertIn('BLOCK',(self.work/'routing-error.json').read_text())
    def test_label_is_hard_even_when_body_does_not_block_port(self):
        self.layout['nodes']['BLOCK']=self.node(490,200)
        self.layout['label_pos']['BLOCK']='below';self.layout['labels']['BLOCK']='BLOCKING LABEL'
        # Label lies just below A's port; put its text baseline on the exit ray.
        self.layout['label_drop']={'BLOCK':44}
        p=self.run_renderer();self.assertNotEqual(p.returncode,0)
        e=json.loads((self.work/'routing-error.json').read_text())
        self.assertTrue(any(o['kind']=='label' and o['obstacle']=='label.BLOCK' for o in e['obstacles']))
    def test_rotated_scaled_nonsquare_symbol_is_an_obstacle(self):
        self.intent['parts']['BLOCK']='firewall_shutoff_valve'
        self.layout['nodes']['BLOCK']=dict(x=690,y=280,w=362.304,h=204.003,rot=90,symbol='symbols/firewall-shutoff-valve.svg')
        p=self.run_renderer();self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.clear_of((675.3,265.3,908.703,657.004))
    def test_nonzero_viewbox_origin_and_scale_keep_terminal_connection(self):
        # The reservoir source viewBox is nonzero; actual port metadata stays
        # aligned with the final route after uniform down-scaling.
        from ruamel.yaml import YAML
        self.intent=YAML(typ='safe').load((SKILL/'assets/fixtures/l0-small-seed/1#系统.intent.yaml').read_text())
        self.layout=json.loads((SKILL/'assets/fixtures/l0-small-seed/1#系统.layout.json').read_text())
        self.layout['nodes']['TANK-001'].update(w=109,h=282)
        p=self.run_renderer();self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        from sheet_geometry import load_geometry
        root=ET.parse(self.work/'1#系统原理图.svg').getroot()
        geo=load_geometry(root,self.layout,lambda ref:self.work/ref)
        self.assertEqual(geo['issues'],[])
        expected=tuple(geo['nodes']['TANK-001']['ports']['suction_out']['position'])
        wire=next(e for e in self.lines() if e.get('data-edge')=='paths[0][0->1]')
        actual=tuple(map(float,wire.get('points').split()[0].split(',')))
        self.assertAlmostEqual(actual[0],expected[0],places=1);self.assertAlmostEqual(actual[1],expected[1],places=1)
    def test_tap_source_stub_cannot_cut_neighbor(self):
        self.intent['parts'].update(A='pressure_gauge',B='air_charging_valve',D='pressure_filter',E='pressure_filter')
        self.intent['paths']=[['D','E']]
        self.intent['taps']=[{'sensor':'A.pressure_sense','at':'B.accumulator_gas'}]
        self.layout['nodes']['A']['symbol']='symbols/pressure-gauge.svg'
        self.layout['nodes']['B']['symbol']='symbols/air-charging-valve.svg'
        self.layout['nodes'].update(D=self.node(400,850),E=self.node(1000,850),BLOCK=self.node(420,382))
        p=self.run_renderer();self.assertNotEqual(p.returncode,0)
        e=json.loads((self.work/'routing-error.json').read_text())
        self.assertEqual(e['anchor'],'taps[0]')
        self.assertIn('BLOCK',[o['obstacle'] for o in e['obstacles']])

    def test_optimizer_marks_no_route_infeasible(self):
        import proto_optimize as O
        self.layout['nodes']['BLOCK']=self.node(475,300)
        for n in self.layout['nodes'].values():n['symbol']=str(SKILL/'assets/component-library'/Path(n['symbol']).name)
        panel=O.bpanel(self.layout,self.intent,json.loads((SKILL/'assets/component-library/component-catalog.json').read_text()))
        self.assertIn('routing_error',panel);self.assertGreater(O.violations(panel),0)

if __name__=='__main__':unittest.main()
