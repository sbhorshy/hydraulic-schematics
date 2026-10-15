"""Independent final-SVG/CLI regressions for strict orthogonality."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_entrypoints import make_render_workspace, SKILL

class NearAxisCLI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='near-axis-')
        self.addCleanup(self.temp.cleanup)
        self.work=make_render_workspace(Path(self.temp.name),SKILL/'assets/fixtures/l0-small-seed')
        run=subprocess.run([sys.executable,str(self.work/'render_l0_sheet.py'),str(self.work)],capture_output=True,text=True)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr)
        self.svg=self.work/'1#系统原理图.svg'
        self.original=self.svg.read_text()

    def validate_points(self,points=None):
        root=ET.fromstring(self.original)
        line=next(e for e in root.iter() if e.get('data-edge')=='paths[1][0->1]')
        if points is not None:line.set('points',points)
        ET.register_namespace('','http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root,encoding='unicode'))
        run=subprocess.run([sys.executable,str(self.work/'validate_sheet.py'),str(self.work)],capture_output=True,text=True,timeout=60)
        self.assertIn(run.returncode,(0,1),run.stdout+run.stderr)
        report=json.loads((self.work/'validation-report.json').read_text())
        return report,[c for c in report['checks'] if c['id']=='V11' and c['result']=='fail']

    def test_subpixel_diagonal_is_a_located_failure(self):
        for delta in (.1,.3,.5):
            with self.subTest(delta=delta):
                report,failures=self.validate_points('650,530 680,%s 850,530'%(530+delta))
                self.assertTrue(failures)
                self.assertEqual(failures[0]['anchor'],'paths[1][0->1]')
                self.assertAlmostEqual(failures[0]['axis_deltas'][1],delta)
                self.assertIn('segment',failures[0])
                self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V11'),'fail')

    def test_true_horizontal_and_vertical_segments_pass(self):
        for points in (None,'650,530 670,530 670,490 830,490 830,530 850,530'):
            with self.subTest(points=points):
                report,failures=self.validate_points(points)
                self.assertEqual(failures,[])
                self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V11'),'pass')

    def test_duplicate_and_collinear_storage_points_are_not_diagonals(self):
        _,failures=self.validate_points('650,530 650,530 670,530 720,530 850,530')
        self.assertEqual(failures,[])


    def test_renderer_keeps_real_near_axis_ports_and_emits_only_hv(self):
        layout=self.work/'1#系统.layout.json'
        original=json.loads(layout.read_text())
        for delta in (.1,.3,.5):
            with self.subTest(delta=delta):
                data=json.loads(json.dumps(original))
                data['nodes']['EDP-001']['y']+=delta
                layout.write_text(json.dumps(data))
                run=subprocess.run([sys.executable,str(self.work/'render_l0_sheet.py'),str(self.work)],capture_output=True,text=True)
                self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                self.original=self.svg.read_text()
                root=ET.fromstring(self.original)
                for wire in root.iter():
                    if not wire.get('class','').startswith('ln-'):continue
                    points=[tuple(map(float,p.split(','))) for p in wire.get('points','').split()]
                    for a,b in zip(points,points[1:]):
                        self.assertTrue(abs(a[0]-b[0])<1e-7 or abs(a[1]-b[1])<1e-7,(a,b))
                report,failures=self.validate_points()
                self.assertEqual(failures,[])
                self.assertFalse([c for c in report['checks'] if c['id']=='V3' and c['result']=='fail'])

    def test_taps_preserve_small_real_offset_without_diagonal_or_lost_end(self):
        from render_l0_sheet import Sheet
        for delta in (.1,.3,.5):
            with self.subTest(delta=delta):
                intent={'parts':{},'taps':[{'sensor':'A.p','at':'B.p'}]}
                layout={'nodes':{},'buses':{},'externs':{},'canvas':{'width':200,'height':200}}
                sheet=Sheet(intent,layout,{'components':[]})
                sheet.abs={('A','p'):(0.,50.,'right'),('B','p'):(100.,50.+delta,'left')}
                sheet.wire_taps()
                points=sheet.polys[0][1]
                self.assertEqual(points[0],(0.,50.))
                self.assertEqual(points[-1],(100.,50.+delta))
                for a,b in zip(points,points[1:]):
                    self.assertTrue(abs(a[0]-b[0])<1e-7 or abs(a[1]-b[1])<1e-7,(a,b))

if __name__=='__main__':unittest.main()

