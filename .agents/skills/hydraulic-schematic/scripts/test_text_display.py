"""Actual rendered text bounds at validator/renderer/PNG public seams."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_entrypoints import make_render_workspace, FIXTURE, SKILL

NS = '{http://www.w3.org/2000/svg}'


class TextDisplay(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='text-display-')
        self.addCleanup(self.temp.cleanup)
        self.work = make_render_workspace(Path(self.temp.name), FIXTURE)
        self.svg = self.work/'1#系统原理图.svg'

    def render(self):
        result = subprocess.run([sys.executable,str(self.work/'render_l0_sheet.py')],cwd=self.work,
                                capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def save(self, root):
        ET.register_namespace('',NS[1:-1])
        self.svg.write_text(ET.tostring(root,encoding='unicode'))

    def validate(self):
        result = subprocess.run([sys.executable,str(self.work/'validate_sheet.py')],cwd=self.work,
                                capture_output=True,text=True,timeout=40)
        self.assertIn(result.returncode,(0,1),result.stdout+result.stderr)
        return json.loads((self.work/'validation-report.json').read_text())

    def text_failures(self, report):
        return [c for c in report['checks'] if c['id']=='V12' and c['result']=='fail']

    def test_long_title_is_rejected_even_though_its_origin_and_frame_fit(self):
        self.render()
        root=ET.parse(self.svg).getroot()
        title=next(e for e in root.iter() if e.get('id')=='title')
        lines=list(title.iter(NS+'text'))
        if len(lines)==3:
            lines[1].text=(lines[1].text or '')+(lines[2].text or '')
            title.remove(lines[2])
        self.save(root)
        report = self.validate()
        failures = self.text_failures(report)
        self.assertTrue(any(c.get('kind')=='text_overflow' and c.get('container')=='title'
                            and c.get('overflow',{}).get('right',0)>100 for c in failures),failures)

    def probe_text(self, root, y, text='H', **attrs):
        e=ET.SubElement(root,NS+'text',{'id':'probe-text','x':'700','y':str(y),'font-size':'20',
                                      'font-family':'Arial','fill':'black',**attrs})
        e.text=text
        return e

    def test_pipeline_crossing_actual_glyphs_reports_text_box_and_connection(self):
        self.render()
        root=ET.parse(self.svg).getroot()
        self.probe_text(root,334)
        self.save(root)
        report=self.validate()
        hits=[c for c in self.text_failures(report) if c.get('element')=='probe-text' and c.get('kind')=='text_overlap']
        self.assertTrue(hits,self.text_failures(report))
        self.assertEqual(hits[0]['obstacle_kind'],'pipe')
        self.assertTrue(hits[0]['bbox'])
        self.assertTrue(hits[0]['obstacle'])

    def test_long_cjk_user_name_is_checked_against_its_own_frame(self):
        layout=self.work/'1#系统.layout.json'
        data=json.loads(layout.read_text())
        data['labels']['USER-001']='中文用户名超出用油设备框但基点仍在框内'
        layout.write_text(json.dumps(data,ensure_ascii=False))
        self.render()
        report=self.validate()
        hits=[c for c in self.text_failures(report) if c.get('kind')=='text_overflow'
              and c.get('container')=='USER-001__user-box']
        self.assertTrue(hits,self.text_failures(report))
        self.assertTrue(hits[0]['text'].startswith('中文用户名'))

    def test_two_independent_texts_overlapping_are_localized(self):
        self.render()
        root=ET.parse(self.svg).getroot()
        self.probe_text(root,900,'ABC')
        other=self.probe_text(root,900,'XYZ',x='710')
        other.set('id','other-text')
        self.save(root)
        report=self.validate()
        self.assertTrue(any(c.get('element')=='probe-text' and c.get('obstacle')=='other-text'
                            and c.get('obstacle_kind')=='text' for c in self.text_failures(report)),self.text_failures(report))

    def test_generated_three_line_title_fits_without_smaller_font(self):
        self.render()
        root=ET.parse(self.svg).getroot()
        title=next(e for e in root.iter() if e.get('id')=='title')
        self.assertEqual(len(list(title.iter(NS+'text'))),3)
        report=self.validate()
        self.assertFalse(any(c.get('container')=='title' for c in self.text_failures(report)))
        rows=[r for r in report['text_geometry']['texts'] if r.get('owner')=='title']
        self.assertTrue(all(r['font_size']=='11px' for r in rows),rows)

    def test_b7_measures_six_pixel_clearance_without_calling_near_text_overlap(self):
        self.render()
        original=self.svg.read_text()
        for baseline,near in ((318,False),(325,True)):
            root=ET.fromstring(original)
            self.probe_text(root,baseline)
            self.save(root)
            report=self.validate()
            hits=[c for c in report['checks'] if c.get('element')=='probe-text' and c.get('budget_id')=='B7']
            self.assertEqual(bool(hits),near,hits)
            self.assertFalse(any(c['id']=='V12' for c in hits))
            if near:
                self.assertAlmostEqual(hits[0]['distance'],3.2,delta=.1)
                self.assertEqual(hits[0]['result'],'warn')
            self.assertNotEqual(next(c for c in report['coverage'] if c['id']=='B7')['status'],'not_checked')

    def test_multiline_cjk_name_and_motor_text_keep_their_own_containers(self):
        layout=self.work/'1#系统.layout.json'
        data=json.loads(layout.read_text());data['labels']['USER-001']='液压\n控制面'
        layout.write_text(json.dumps(data,ensure_ascii=False))
        self.render();report=self.validate()
        expected={'USER-001__user-name':'USER-001__user-box','FSOV-001__motor-text':'FSOV-001__motor-circle'}
        for element,container in expected.items():
            record=next(t for t in report['text_geometry']['texts'] if t['element']==element)
            self.assertEqual(record['container'],container)
            self.assertFalse(any(c.get('element')==element for c in self.text_failures(report)))

    def test_font_fallback_change_can_make_the_same_name_overflow(self):
        layout=self.work/'1#系统.layout.json';data=json.loads(layout.read_text())
        data['labels']['USER-001']='iiiiiiiiiiii';layout.write_text(json.dumps(data))
        self.render();original=self.svg.read_text();widths=[]
        for family,overflow in (('serif',False),('UnavailableTicket06Font, monospace',True)):
            root=ET.fromstring(original)
            next(e for e in root.iter() if e.get('id')=='USER-001__user-name').set('style','font-family:'+family)
            self.save(root);report=self.validate()
            record=next(t for t in report['text_geometry']['texts'] if t['element']=='USER-001__user-name')
            widths.append(record['bbox'][2]-record['bbox'][0])
            self.assertEqual(any(c.get('container')=='USER-001__user-box' for c in self.text_failures(report)),overflow)
            self.assertEqual(record['font_size'],'12px')
        self.assertGreater(widths[1],widths[0]*1.5)

    def test_rotated_scaled_anchor_and_left_viewport_clipping_use_actual_bounds(self):
        self.render();root=ET.parse(self.svg).getroot()
        text=self.probe_text(root,0,'ABC',x='0',**{'text-anchor':'middle','transform':'translate(1100,80) rotate(90) scale(1.5)'})
        self.save(root);report=self.validate()
        record=next(t for t in report['text_geometry']['texts'] if t['element']=='probe-text')
        self.assertGreater(record['bbox'][3]-record['bbox'][1],record['bbox'][2]-record['bbox'][0])
        self.assertFalse(any(c.get('element')=='probe-text' for c in self.text_failures(report)),self.text_failures(report))
        text.attrib.pop('transform');text.set('x','5');text.set('y','800');text.set('text-anchor','end')
        self.save(root);report=self.validate()
        self.assertTrue(any(c.get('element')=='probe-text' and c.get('container')=='viewport'
                            and c['overflow']['left']>10 for c in self.text_failures(report)))

    def test_unowned_label_inside_a_symbol_is_not_an_internal_annotation(self):
        self.render();root=ET.parse(self.svg).getroot()
        self.probe_text(root,334,'H',x='602',**{'font-size':'11'})
        self.save(root);report=self.validate()
        self.assertTrue(any(c.get('element')=='probe-text' and c.get('obstacle_kind')=='symbol_body'
                            for c in self.text_failures(report)),self.text_failures(report))

    def test_browser_unavailable_keeps_v12_and_b7_explicitly_unchecked(self):
        import os
        self.render();self.validate()
        result=subprocess.run([sys.executable,str(self.work/'validate_sheet.py')],cwd=self.work,
                              capture_output=True,text=True,env=dict(os.environ,PATH=''),timeout=40)
        self.assertIn(result.returncode,(0,1),result.stderr)
        report=json.loads((self.work/'validation-report.json').read_text())
        for name in ('V12','B7'):
            self.assertEqual(next(c for c in report['coverage'] if c['id']==name)['status'],'not_checked')
        self.assertTrue(report['text_geometry']['unchecked'])

    def test_legend_text_cannot_overflow_its_frame(self):
        self.render();root=ET.parse(self.svg).getroot()
        legend=next(e for e in root.iter() if e.get('id')=='legend')
        text=next(e for e in legend.iter(NS+'text'))
        text.text='图例说明文本超出边界 '*25
        self.save(root);report=self.validate()
        self.assertTrue(any(c.get('container')=='legend' and c['overflow']['right']>100
                            for c in self.text_failures(report)))

    def test_v17_and_v12_share_root_coordinates_for_suction_marks(self):
        self.render();root=ET.parse(self.svg).getroot()
        sheet=next(e for e in root.iter() if e.get('id')=='sheet')
        sheet.set('transform','translate(200,0) '+sheet.get('transform',''))
        root.set('viewBox','0 0 2400 1390');root.set('width','2400')
        mark=next(e for e in root.iter() if e.get('class')=='suc-mark')
        x,y=float(mark.get('x1')),float(mark.get('y1'))
        text=self.probe_text(root,y+4,'H',x=str(x-4),**{'font-size':'11','class':'lbl'})
        self.save(root);report=self.validate()
        self.assertFalse(any(c['id']=='V17' and '文字 H' in c['detail'] for c in report['checks']))
        text.set('x',str(x+200-4))
        self.save(root);report=self.validate()
        self.assertTrue(any(c['id']=='V17' and '文字 H' in c['detail'] for c in report['checks']))
        self.assertTrue(any(c.get('element')=='probe-text' and c.get('obstacle_kind')=='suction_marker'
                            for c in self.text_failures(report)))

    def test_real_png_ink_agrees_with_measured_rotated_cjk_text(self):
        from PIL import Image
        self.render();root=ET.parse(self.svg).getroot()
        self.probe_text(root,0,'液压ABC',x='0',**{'text-anchor':'middle','transform':'translate(1100,110) rotate(90) scale(1.5)'})
        self.save(root)
        result=subprocess.run([sys.executable,str(SKILL/'scripts/rasterize_sheet.py'),str(self.svg),
                               '-o',str(self.work/'sheet-readback.png'),'--backend','chrome'],
                              capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stderr)
        report=self.validate();record=next(t for t in report['text_geometry']['texts'] if t['element']=='probe-text')
        import math
        box=record['bbox'];crop_box=(math.floor(box[0])-3,math.floor(box[1])-3,math.ceil(box[2])+3,math.ceil(box[3])+3)
        image=Image.open(self.work/'sheet-readback.png').convert('L').crop(crop_box)
        ink=image.point(lambda v:255 if v<128 else 0).getbbox()
        self.assertIsNotNone(ink)
        actual=[ink[0]+crop_box[0],ink[1]+crop_box[1],ink[2]+crop_box[0],ink[3]+crop_box[1]]
        for measured,pixel in zip(box,actual): self.assertAlmostEqual(measured,pixel,delta=2)
        self.assertEqual(next(c for c in report['coverage'] if c['id']=='V12')['status'],'pass')

    def test_driver_and_standalone_use_identical_text_evidence(self):
        fixture=SKILL/'assets/fixtures/l0-small-seed';work=Path(self.temp.name)/'driver'
        result=subprocess.run([sys.executable,str(SKILL/'scripts/validate_driver.py'),'--intent',str(fixture/'1#系统.intent.yaml'),
                               '--layout-seed',str(fixture/'1#系统.layout.json'),'--workdir',str(work),'--rounds','1'],
                              capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)
        before=json.loads((work/'validation-report.json').read_text())
        self.work=work;self.svg=work/'1#系统原理图.svg'
        after=self.validate()
        self.assertEqual(before['text_geometry'],after['text_geometry'])
        self.assertEqual(next(e for e in after['coverage'] if e['id']=='V12')['status'],'pass')

    def test_internal_text_uses_its_circular_container_not_only_its_box(self):
        self.render();root=ET.parse(self.svg).getroot()
        text=next(e for e in root.iter() if e.get('id')=='FSOV-001__motor-text')
        text.set('x','113');text.set('y','125')
        self.save(root);report=self.validate()
        self.assertTrue(any(c.get('element')=='FSOV-001__motor-text' and c.get('kind')=='text_overflow'
                            and c.get('container')=='FSOV-001__motor-circle'
                            for c in self.text_failures(report)),self.text_failures(report))

    def test_required_component_labels_hidden_by_stylesheet_fail(self):
        self.render()
        self.svg.write_text(self.svg.read_text().replace('</style>','#labels {display:none;}</style>'))
        report=self.validate()
        self.assertTrue(any(c.get('kind')=='text_hidden' for c in self.text_failures(report)),self.text_failures(report))
        self.assertIn(next(c for c in report['coverage'] if c['id']=='B7')['status'],('fail','not_checked'))

    def test_missing_declared_labels_and_title_text_cannot_look_complete(self):
        self.render();original=self.svg.read_text()
        for target in ('labels','USER-001__user-name','title-row-1'):
            with self.subTest(target=target):
                root=ET.fromstring(original)
                element=next(e for e in root.iter() if e.get('id')==target)
                parent=next(p for p in root.iter() if element in list(p))
                parent.remove(element)
                self.save(root);report=self.validate()
                self.assertTrue(any(c.get('kind')=='missing_required_text' for c in self.text_failures(report)),self.text_failures(report))
                self.assertIn(next(c for c in report['coverage'] if c['id']=='B7')['status'],('fail','not_checked'))

    def test_unpainted_user_span_and_hidden_title_are_known_failures(self):
        self.render();original=self.svg.read_text()
        for target in ('user-span','title-row-1'):
            with self.subTest(target=target):
                root=ET.fromstring(original)
                if target=='user-span':
                    user=next(e for e in root.iter() if e.get('id')=='USER-001__user-name')
                    next(user.iter(NS+'tspan')).set('style','fill:none;stroke:none')
                else:
                    next(e for e in root.iter() if e.get('id')==target).set('style','opacity:0')
                self.save(root);report=self.validate()
                self.assertTrue(any(c.get('kind')=='text_hidden' for c in self.text_failures(report)),self.text_failures(report))
                self.assertIn(next(c for c in report['coverage'] if c['id']=='B7')['status'],('fail','not_checked'))


if __name__=='__main__':
    unittest.main()
