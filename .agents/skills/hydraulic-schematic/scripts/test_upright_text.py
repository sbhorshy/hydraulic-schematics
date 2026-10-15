"""Upright opt-in labels are checked from actual browser glyph orientation."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from ruamel.yaml import YAML
from test_entrypoints import make_render_workspace,SKILL

class UprightTextCLI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='upright-text-');self.addCleanup(self.temp.cleanup)
        self.work=make_render_workspace(Path(self.temp.name),SKILL/'assets/fixtures/l0-small-seed')
        y=YAML();p=self.work/'1#系统.intent.yaml';intent=y.load(p)
        intent['parts']['FSOV-TEST']='firewall_shutoff_valve'
        intent['paths']=[['TANK-001.suction_out','FSOV-TEST.main_upper'],['FSOV-TEST.main_lower','EDP-001.suction']]+intent['paths'][1:]
        with p.open('w') as f:y.dump(intent,f)
        self.layout=self.work/'1#系统.layout.json';l=json.loads(self.layout.read_text())
        l['canvas'].update(width=1800,height=1400);l['drawable'].update(width=1770,height=1400)
        l['nodes']['FSOV-TEST']={'x':1100,'y':700,'w':362.304,'h':204.0034,'rot':270,'symbol':'symbols/firewall-shutoff-valve.svg'}
        l['labels']['FSOV-TEST']='FSOV';l['label_pos']['FSOV-TEST']='above'
        self.layout.write_text(json.dumps(l));self.svg=self.work/'1#系统原理图.svg'
        self.symbol=self.work/'symbols/firewall-shutoff-valve.svg'

    def render(self,rotation=270):
        l=json.loads(self.layout.read_text());l['nodes']['FSOV-TEST']['rot']=rotation;self.layout.write_text(json.dumps(l))
        p=subprocess.run([sys.executable,str(self.work/'render_l0_sheet.py'),str(self.work)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def validate(self):
        p=subprocess.run([sys.executable,str(self.work/'validate_sheet.py'),str(self.work)],capture_output=True,text=True,timeout=90)
        self.assertIn(p.returncode,(0,1),p.stdout+p.stderr)
        return json.loads((self.work/'validation-report.json').read_text())

    def test_declared_motor_text_is_upright_in_all_four_positions(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation):
                self.render(rotation);report=self.validate()
                record=next(r for r in report['text_geometry']['upright_text'] if r['component']=='FSOV-TEST')
                self.assertEqual(record['status'],'pass',record)
                self.assertTrue(all(abs(a)<1e-4 for a in record['angles_deg']))
                self.assertLessEqual(record['pivot_error'],.1)
                text=next(e for e in ET.parse(self.svg).getroot().iter() if e.get('id')=='FSOV-TEST__motor-text')
                self.assertEqual(text.get('font-size'),'19.2003')

    def test_final_rotated_and_mirrored_glyphs_fail_even_with_source_flag(self):
        self.render();original=self.svg.read_text()
        for tamper in ('rotate(90 94.8494 98.9232)','translate(94.8494 98.9232) scale(-1 1) translate(-94.8494 -98.9232)'):
            with self.subTest(tamper=tamper):
                root=ET.fromstring(original);text=next(e for e in root.iter() if e.get('id')=='FSOV-TEST__motor-text')
                text.set('transform',text.get('transform','')+' '+tamper)
                ET.register_namespace('','http://www.w3.org/2000/svg');self.svg.write_text(ET.tostring(root,encoding='unicode'))
                report=self.validate()
                self.assertTrue([c for c in report['checks'] if c.get('kind')=='upright_orientation'])

    def test_undeclared_text_keeps_existing_rotation_behavior(self):
        tree=ET.parse(self.symbol);text=next(e for e in tree.getroot().iter() if e.get('id')=='motor-text')
        text.attrib.pop('data-keep-upright');text.attrib.pop('data-upright-pivot')
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        self.render();report=self.validate()
        self.assertFalse(report['text_geometry']['upright_text'])

    def test_nested_uniform_source_scale_keeps_pivot_and_glyph_direction(self):
        tree=ET.parse(self.symbol);group=next(e for e in tree.getroot().iter() if e.get('id')=='motor-m')
        group.set('transform','translate(10 10) scale(0.9)')
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        self.render(90);report=self.validate()
        record=next(r for r in report['text_geometry']['upright_text'] if r['component']=='FSOV-TEST')
        self.assertEqual(record['status'],'pass',record)

    def test_unsupported_multirun_is_explicitly_unchecked(self):
        tree=ET.parse(self.symbol);text=next(e for e in tree.getroot().iter() if e.get('id')=='motor-text')
        ET.SubElement(text,'{http://www.w3.org/2000/svg}tspan').text='N'
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        self.render();report=self.validate()
        self.assertTrue(any('single unrotated text run' in x.get('reason','') for x in report['text_geometry']['unchecked']))

    def test_root_level_declared_text_is_embedded_and_kept_upright(self):
        tree=ET.parse(self.symbol);root=tree.getroot()
        for parent in root.iter():
            target=next((e for e in parent if e.get('id')=='motor-text'),None)
            if target is not None:
                parent.remove(target);root.append(target);break
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        self.render(270);report=self.validate()
        record=next(r for r in report['text_geometry']['upright_text'] if r['component']=='FSOV-TEST')
        self.assertEqual(record['status'],'pass',record)

if __name__=='__main__':unittest.main()
