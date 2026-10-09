"""Exercise real routing with close facing ports: no overshoot/backtracking tails."""
import unittest
from render_l0_sheet import Sheet


def backward_turns(points):
    hits=[]
    for a,b,c in zip(points,points[1:],points[2:]):
        u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1])
        if abs(u[0]*v[1]-u[1]*v[0])<1e-6 and u[0]*v[0]+u[1]*v[1]<-1e-6:
            hits.append((a,b,c))
    return hits


class CloseFacingPorts(unittest.TestCase):
    def sheet(self):
        s=object.__new__(Sheet)
        s.L={'nodes':{},'vlanes':[]}
        s.drawn=[];s.buslines=[];s.textboxes=[]
        return s

    def test_reported_valve_to_pump_route_has_no_tail(self):
        a=(526.003,449.038,'right');b=(560,330,'left')
        pts=self.sheet().route(a,b)
        self.assertEqual(pts[0],a[:2]);self.assertEqual(pts[-1],b[:2])
        self.assertEqual(backward_turns(pts),[])
        self.assertGreater(pts[1][0],a[0])
        self.assertLess(pts[-2][0],b[0])

    def test_short_clearances_in_all_four_orientations(self):
        for gap in (6,14,34,40,80):
            cases=[((0,100,'right'),(gap,0,'left')),
                   ((gap,100,'left'),(0,0,'right')),
                   ((100,0,'down'),(0,gap,'up')),
                   ((100,gap,'up'),(0,0,'down'))]
            for a,b in cases:
                with self.subTest(gap=gap,a=a,b=b):
                    pts=self.sheet().route(a,b)
                    self.assertEqual(pts[0],a[:2]);self.assertEqual(pts[-1],b[:2])
                    self.assertEqual(backward_turns(pts),[])
                    for p,q in zip(pts,pts[1:]):
                        self.assertTrue(abs(p[0]-q[0])<1e-6 or abs(p[1]-q[1])<1e-6)

    def test_facing_collinear_ports_remain_direct(self):
        for gap in (6,14,34,80):
            pts=self.sheet().route((0,0,'right'),(gap,0,'left'))
            self.assertEqual(backward_turns(pts),[])
            self.assertTrue(all(y==0 for x,y in pts))
            self.assertEqual(sum(abs(b[0]-a[0]) for a,b in zip(pts,pts[1:])),gap)


class BacktrackValidation(unittest.TestCase):
    def test_six_pixel_tail_is_rejected_by_sheet_validator(self):
        import json,subprocess,sys,tempfile,xml.etree.ElementTree as ET
        from pathlib import Path
        from test_entrypoints import make_render_workspace,SKILL
        with tempfile.TemporaryDirectory(prefix='backtrack-gate-') as directory:
            w=make_render_workspace(Path(directory),SKILL/'assets/fixtures/l0-small-seed')
            r=subprocess.run([sys.executable,str(w/'render_l0_sheet.py')],cwd=w,capture_output=True,text=True)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            svg=w/'1#系统原理图.svg';root=ET.parse(svg).getroot()
            el=next(e for e in root.iter() if e.get('class')=='ln-pressure')
            points=el.get('points').split();x,y=map(float,points[0].split(','))
            el.set('points',' '.join([points[0],'%g,%g'%(x+20,y),'%g,%g'%(x+14,y)]+points[1:]))
            ET.register_namespace('','http://www.w3.org/2000/svg')
            svg.write_text(ET.tostring(root,encoding='unicode'))
            subprocess.run([sys.executable,str(w/'validate_sheet.py')],cwd=w,capture_output=True,text=True)
            report=json.loads((w/'validation-report.json').read_text())
            self.assertTrue(any(c['id']=='V13' and c['result']=='fail' and '自身折返' in c['detail'] for c in report['checks']))


if __name__=='__main__':
    unittest.main()
