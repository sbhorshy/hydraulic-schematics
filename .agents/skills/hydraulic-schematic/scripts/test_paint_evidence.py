"""Actual paint regressions at the SVG, fresh PNG and validator CLI boundary."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from PIL import Image
from test_entrypoints import SKILL, make_render_workspace

NS='{http://www.w3.org/2000/svg}'

class PaintEvidenceCLI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='paint-evidence-')
        self.addCleanup(self.temp.cleanup)
        self.work=make_render_workspace(Path(self.temp.name),SKILL/'assets/fixtures/l0-small-seed')
        self.svg=self.work/'1#系统原理图.svg'
        self.run_cli('render_l0_sheet.py',self.work)

    def run_cli(self,name,*args):
        result=subprocess.run([sys.executable,str(SKILL/'scripts'/name),*map(str,args)],capture_output=True,text=True,timeout=60)
        self.assertIn(result.returncode,(0,1),result.stdout+result.stderr)
        return result

    def save(self,root):
        ET.register_namespace('',NS[1:-1]);self.svg.write_text(ET.tostring(root,encoding='unicode'))

    def measure(self):
        self.run_cli('rasterize_sheet.py',self.svg,'-o',self.work/'sheet-readback.png')
        self.run_cli('validate_sheet.py',self.work)
        return json.loads((self.work/'validation-report.json').read_text())

    def coverage(self,report,ident):
        return next(e['status'] for e in report['coverage'] if e['id']==ident)

    def test_transparent_colored_lead_has_no_png_ink_and_fails_width_checks(self):
        root=ET.parse(self.svg).getroot()
        inst=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
        lead=next(e for e in inst.iter() if e.get('data-interface-port')=='inlet')
        lead.set('style','stroke:rgba(255,0,0,0)!important')
        self.save(root);report=self.measure()
        with Image.open(self.work/'sheet-readback.png') as image:
            self.assertEqual(sum(255-v for v in image.convert('L').crop((854,526,864,535)).getdata()),0)
        for ident in ('V15','V16'):
            self.assertEqual(self.coverage(report,ident),'fail')
            self.assertTrue(any(c['id']==ident and 'PF-001' in c['detail'] for c in report['checks'] if c['result']=='fail'))

    def test_transparent_colored_pipe_has_no_png_ink_and_cannot_connect_terminals(self):
        root=ET.parse(self.svg).getroot()
        pipe=next(e for e in root.iter() if e.get('id')=='wire-1-0')
        pipe.set('style','stroke:rgba(0,200,80,0)!important')
        self.save(root);report=self.measure()
        with Image.open(self.work/'sheet-readback.png') as image:
            self.assertEqual(sum(255-v for v in image.convert('L').crop((690,526,810,535)).getdata()),0)
        self.assertEqual(self.coverage(report,'V10'),'fail')
        self.assertEqual(self.coverage(report,'V15'),'fail')
        self.assertFalse(any(set(e['endpoints'])=={'EDP-001.pressure_out','PF-001.inlet'} for e in report['topology']['actual_edges']))

    def test_transparent_colored_body_cannot_supply_lead_transition_contact(self):
        import shutil
        for name in ('1#系统.intent.yaml','1#系统.layout.json'):
            shutil.copy2(SKILL/'assets/fixtures/l0-current'/name,self.work/name)
        self.run_cli('render_l0_sheet.py',self.work)
        root=ET.parse(self.svg).getroot()
        dial=next(e for e in root.iter() if e.get('id')=='PG-001__dial')
        dial.set('style','stroke:rgba(30,120,255,0)!important;fill:none!important')
        self.save(root);report=self.measure()
        self.assertEqual(self.coverage(report,'V16'),'not_checked')
        browser=json.loads((self.work/'browser-evidence.json').read_text())
        dial=next(e for e in browser['elements'] if e['id']=='PG-001__dial')
        lead=next(e for e in browser['elements'] if e['id']=='PG-001__pressure-sense-line')
        self.assertFalse(any(dial['key'] in contacts for contacts in lead['endpoint_contacts']))
        self.assertTrue(any('PG-001'==u.get('component') and 'body contact' in u['reason']
                            for e in report['evidence'] if e['id']=='V16' for u in e['unchecked']))

    def test_supported_visible_color_passes_and_paint_servers_remain_unchecked(self):
        original=self.svg.read_text()
        for target,paint,status in (('lead','rgba(255,0,0,0.5)','pass'),('lead','url(#colored)','not_checked'),('pipe','url(#colored)','not_checked')):
            with self.subTest(target=target,paint=paint):
                root=ET.fromstring(original)
                defs=ET.SubElement(root,NS+'defs');gradient=ET.SubElement(defs,NS+'linearGradient',{'id':'colored'})
                ET.SubElement(gradient,NS+'stop',{'offset':'0','stop-color':'red'})
                ET.SubElement(gradient,NS+'stop',{'offset':'1','stop-color':'blue'})
                inst=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
                el=next(e for e in inst.iter() if e.get('data-interface-port')=='inlet') if target=='lead' else next(e for e in root.iter() if e.get('id')=='wire-1-0')
                el.set('style','stroke:'+paint+'!important');self.save(root);report=self.measure()
                self.assertEqual(self.coverage(report,'V15'),status)
                self.assertEqual(self.coverage(report,'V16'),status)
                if target=='pipe':self.assertEqual(self.coverage(report,'V10'),'not_checked')

    def test_dashed_pressure_lead_is_not_a_continuous_measured_connection(self):
        original=self.svg.read_text()
        for target,dash,check,status in (('lead','2px 12px','V16','fail'),('pipe','2px 12px','V15','fail'),('lead','2px 0px','V16','pass')):
            with self.subTest(target=target,dash=dash):
                root=ET.fromstring(original)
                inst=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
                el=next(e for e in inst.iter() if e.get('data-interface-port')=='inlet') if target=='lead' else next(e for e in root.iter() if e.get('id')=='wire-1-0')
                el.set('style','stroke-dasharray:'+dash+'!important;stroke-linecap:butt!important')
                self.save(root);report=self.measure()
                if target=='lead':
                    with Image.open(self.work/'sheet-readback.png') as image:
                        pixel=image.convert('L').getpixel((858,530))
                        self.assertGreater(pixel,240) if status=='fail' else self.assertLess(pixel,128)
                self.assertEqual(self.coverage(report,check),status)
                if target=='pipe':self.assertEqual(self.coverage(report,'V10'),'not_checked')

    def test_fat_symbol_body_fails_while_its_pressure_leads_keep_correct_width(self):
        root=ET.parse(self.svg).getroot()
        body=next(e for e in root.iter() if e.get('id')=='PF-001__symbol')
        for el in body.iter():
            if not el.get('data-interface-port'):el.set('style','stroke-width:12px!important')
        self.save(root);report=self.measure()
        self.assertEqual(self.coverage(report,'V15'),'fail')
        findings=[c['detail'] for c in report['checks'] if c['id']=='V15' and c['result']=='fail']
        self.assertTrue(any('PF-001' in f and 'body' in f for f in findings),findings)
        leads=next(e for e in report['evidence'] if e['id']=='V16')['measurements']
        self.assertTrue(all(abs(m['effective_width']-3.6)<.02 for m in leads if m['component']=='PF-001'))

    def test_percentage_stroke_preserves_report_and_discloses_unmeasured_width(self):
        root=ET.parse(self.svg).getroot()
        pipe=next(e for e in root.iter() if e.get('id')=='wire-1-0')
        pipe.set('style','stroke-width:0.2%!important')
        self.save(root);report=self.measure()
        for ident in ('V10','V15','V16'):
            self.assertEqual(self.coverage(report,ident),'not_checked')
        unchecked=report['topology']['display_evidence']['unchecked']
        self.assertTrue(any(u.get('svg_id')=='wire-1-0' and u.get('position') for u in unchecked),unchecked)

    def test_each_body_primitive_rejects_a_12px_stroke(self):
        original=self.svg.read_text()
        shapes={'circle':{'cx':'40','cy':'40','r':'16'},
                'ellipse':{'cx':'40','cy':'40','rx':'16','ry':'12'},
                'rect':{'x':'24','y':'24','width':'32','height':'32'},
                'polygon':{'points':'24,40 40,24 56,40 40,56'}}
        for tag,attrs in shapes.items():
            with self.subTest(tag=tag):
                root=ET.fromstring(original)
                body=next(e for e in root.iter() if e.get('id')=='PF-001__symbol')
                shape=next(e for e in body if e.tag==NS+'circle')
                shape.tag=NS+tag;shape.attrib.clear();shape.attrib.update(attrs)
                shape.set('id','damaged-body');shape.set('style','stroke-width:12px!important')
                self.save(root);report=self.measure()
                self.assertEqual(self.coverage(report,'V15'),'fail')
                self.assertTrue(any(c['id']=='V15' and c['result']=='fail' and 'damaged-body' in c['detail']
                                    for c in report['checks']),report['checks'])

    def test_source_scaled_body_primitives_keep_prescribed_display_width(self):
        source=self.work/'symbols/filter-line-shutoff-stroke.svg';original=source.read_text()
        # Doubled coordinates followed by source-local 0.5 scale preserve the
        # real body geometry. The prescribed visible stroke must remain 1.8.
        shapes={'circle':{'cx':'80','cy':'80','r':'32'},
                'ellipse':{'cx':'80','cy':'80','rx':'32','ry':'24'},
                'rect':{'x':'48','y':'48','width':'64','height':'64'},
                'polygon':{'points':'48,80 80,48 112,80 80,112'}}
        for tag,attrs in shapes.items():
            with self.subTest(tag=tag):
                root=ET.fromstring(original);body=next(e for e in root.iter() if e.get('id')=='symbol')
                shape=next(e for e in body if e.tag==NS+'circle');body.remove(shape)
                group=ET.SubElement(body,NS+'g',{'transform':'scale(0.5)'})
                shape.tag=NS+tag;shape.attrib.clear();shape.attrib.update(attrs);shape.set('id','scaled-body');group.append(shape)
                ET.register_namespace('',NS[1:-1]);source.write_text(ET.tostring(root,encoding='unicode'))
                self.run_cli('render_l0_sheet.py',self.work);report=self.measure()
                self.assertEqual(self.coverage(report,'V15'),'pass')
                measured=next(m for e in report['evidence'] if e['id']=='V15' for m in e['measurements'] if m['element']=='PF-001__scaled-body')
                self.assertTrue(measured['effective_widths'])
                for value in measured['effective_widths']:self.assertAlmostEqual(value,1.8,places=4)
                with Image.open(self.work/'sheet-readback.png') as image:
                    self.assertGreater(sum(255-v for v in image.convert('L').crop((873,512,907,548)).getdata()),0)

    def test_nonuniform_body_primitives_are_explicitly_unchecked(self):
        original=self.svg.read_text()
        shapes={'circle':{'cx':'40','cy':'40','r':'16'},
                'ellipse':{'cx':'40','cy':'40','rx':'16','ry':'12'},
                'rect':{'x':'24','y':'24','width':'32','height':'32'},
                'polygon':{'points':'24,40 40,24 56,40 40,56'}}
        for tag,attrs in shapes.items():
            with self.subTest(tag=tag):
                root=ET.fromstring(original);body=next(e for e in root.iter() if e.get('id')=='PF-001__symbol')
                shape=next(e for e in body if e.tag==NS+'circle');shape.tag=NS+tag;shape.attrib.clear();shape.attrib.update(attrs)
                shape.set('id','nonuniform-body');shape.set('transform','translate(40 40) scale(2 1) translate(-40 -40)')
                self.save(root);report=self.measure()
                self.assertEqual(self.coverage(report,'V15'),'not_checked')
                evidence=next(e for e in report['evidence'] if e['id']=='V16')
                self.assertTrue(any(u.get('element')=='nonuniform-body' and u.get('position') and 'nonuniform' in u['reason'] for u in evidence['unchecked']))

    def test_transparent_colored_geometry_does_not_create_a_text_obstacle(self):
        from PIL import ImageChops
        baseline=self.measure()
        with Image.open(self.work/'sheet-readback.png') as image:before=image.convert('RGB').copy()
        root=ET.parse(self.svg).getroot()
        ET.SubElement(root,NS+'rect',{'x':'585','y':'470','width':'50','height':'20',
                                     'fill':'rgba(100,180,220,0)','stroke':'rgba(200,10,30,0)'})
        self.save(root);report=self.measure()
        with Image.open(self.work/'sheet-readback.png') as image:
            self.assertIsNone(ImageChops.difference(before,image.convert('RGB')).getbbox())
        self.assertEqual(self.coverage(report,'V12'),self.coverage(baseline,'V12'))
        self.assertEqual(self.coverage(report,'B7'),self.coverage(baseline,'B7'))

if __name__=='__main__':unittest.main()
