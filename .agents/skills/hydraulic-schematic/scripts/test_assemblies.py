"""Assembly contracts at the public preflight, renderer and validator CLIs."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from ruamel.yaml import YAML
from test_entrypoints import SKILL, make_render_workspace

class AssemblyCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='assembly-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.work = make_render_workspace(Path(self.tmp.name), SKILL/'assets/fixtures/l0-small-seed')
        self.intent_path = self.work/'1#系统.intent.yaml'
        self.intent = YAML().load(self.intent_path)
        self.intent['assemblies'] = {'SUPPLY': {'label':'Supply assembly', 'members':['EDP-001','PF-001']}}

    def write_intent(self):
        YAML().dump(self.intent,self.intent_path)

    def cli(self, name, *args):
        return subprocess.run([sys.executable,str(SKILL/'scripts'/name),*map(str,args)],capture_output=True,text=True)

    def test_preflight_rejects_undeclared_assembly_member_even_in_concept(self):
        self.intent['assemblies']['SUPPLY']['members'][1]='MISSING'
        self.write_intent()
        result=self.cli('preflight.py',self.intent_path,'--json')
        self.assertEqual(result.returncode,1,result.stdout+result.stderr)
        report=json.loads(result.stdout)
        self.assertTrue(any(f['level']=='ERROR' and f['id'].startswith('E-ASSEMBLY') for f in report['findings']))

    def test_assembly_invariants_hold_without_optional_jsonschema(self):
        dependency_dir=Path(self.tmp.name)/'optional-dependency'
        dependency_dir.mkdir()
        (dependency_dir/'jsonschema.py').write_text('raise ImportError("optional jsonschema unavailable")\n')
        env=dict(os.environ,PYTHONPATH=str(dependency_dir))
        original=copy.deepcopy(self.intent)
        cases=[('valid',lambda a:None,0),
               ('missing_label',lambda a:a['SUPPLY'].pop('label'),1),
               ('blank_label',lambda a:a['SUPPLY'].update(label='  '),1),
               ('one_member',lambda a:a['SUPPLY'].update(members=['PF-001']),1),
               ('missing_members',lambda a:a['SUPPLY'].pop('members'),1),
               ('members_not_list',lambda a:a['SUPPLY'].update(members='PF-001'),1),
               ('invalid_member',lambda a:a['SUPPLY'].update(members=['PF-001',None]),1),
               ('invalid_declaration',lambda a:a.update(SUPPLY=None),1)]
        for name,mutate,expected in cases:
            with self.subTest(case=name):
                self.intent=copy.deepcopy(original)
                mutate(self.intent['assemblies']);self.write_intent()
                result=subprocess.run([sys.executable,str(SKILL/'scripts/preflight.py'),str(self.intent_path),'--json'],
                                      env=env,capture_output=True,text=True)
                report=json.loads(result.stdout)
                self.assertTrue(any(f['id']=='W-SHAPE-DEP' for f in report['findings']),report)
                self.assertEqual(result.returncode,expected,report)
                if expected:
                    self.assertTrue(any(f['id'].startswith('E-ASSEMBLY') and f['level']=='ERROR' for f in report['findings']),report)
                    self.assertFalse(report['ok'])
                else:
                    self.assertTrue(report['ok'])

    def test_renderer_encloses_actual_long_member_labels_and_keeps_groups_distinct(self):
        from browser_evidence import collect
        self.intent['groups']=[{'id':'FILTER','label':'Filter zone','members':['PF-001'],'reason':'routing'}]
        self.write_intent()
        path=self.work/'1#系统.layout.json'
        layout=json.loads(path.read_text())
        layout['labels']['EDP-001']='Pump with a very long assembly member label'
        path.write_text(json.dumps(layout))
        result=self.cli('render_l0_sheet.py',self.work)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        measured=collect(self.work/'1#系统原理图.svg')
        frames=[r for r in measured['elements'] if r['attrs'].get('data-assembly')=='SUPPLY' and r['tag']=='rect']
        self.assertEqual(len(frames),1)
        frame=frames[0]
        self.assertAlmostEqual(float(frame['style']['stroke-width'].removesuffix('px')),1.8)
        group=next(r for r in measured['elements'] if r['attrs'].get('data-group')=='FILTER')
        self.assertAlmostEqual(float(group['style']['stroke-width'].removesuffix('px')),1.2)
        label=next(r for r in measured['elements'] if r['attrs'].get('data-label-for')=='EDP-001')
        self.assertGreaterEqual(label['ink_bbox'][0]-frame['bbox'][0],14)
        self.assertGreaterEqual(frame['bbox'][2]-label['ink_bbox'][2],14)
        self.assertGreaterEqual(frame['bbox'][3]-label['ink_bbox'][3],14)

    def test_validator_rejects_assembly_frame_cutting_member_and_wrong_width(self):
        import xml.etree.ElementTree as ET
        self.write_intent()
        result=self.cli('render_l0_sheet.py',self.work)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        svg=self.work/'1#系统原理图.svg'
        root=ET.parse(svg).getroot()
        frame=next(e for e in root.iter() if e.get('id')=='assembly-SUPPLY')
        frame.set('width','20')
        frame.set('style','stroke-width:1.2px')
        ET.register_namespace('','http://www.w3.org/2000/svg')
        svg.write_text(ET.tostring(root,encoding='unicode'))
        self.cli('validate_sheet.py',self.work)
        report=json.loads((self.work/'validation-report.json').read_text())
        kinds={c.get('kind') for c in report['checks']}
        self.assertIn('assembly_member_containment',kinds)
        self.assertIn('assembly_style',kinds)

    def test_cdf_seed_driver_produces_png_and_assembly_crossing_evidence(self):
        fixture=SKILL/'assets/fixtures/l0-assembly-seed'
        result=self.cli('validate_driver.py','--intent',fixture/'1#系统.intent.yaml',
                        '--layout-seed',fixture/'1#系统.layout.json','--workdir',Path(self.tmp.name)/'driver','--rounds','1')
        work=Path(self.tmp.name)/'driver'
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)  # perceptual signoff remains pending
        report=json.loads((work/'validation-report.json').read_text())
        self.assertEqual(report['fail_count'],0,report['checks'])
        assembly=next(e for e in report['evidence'] if e['id']=='V20')
        self.assertEqual(assembly['coverage_status'],'pass',assembly)
        self.assertEqual({c['member_port'] for c in assembly['assemblies'][0]['crossings']},
                         {'CDF-001-BODY.inlet','CDF-001-CV.outlet'})
        self.assertTrue((work/'sheet-readback.png').is_file())
        manifest=json.loads((work/'1#系统原理图-topology.json').read_text())
        self.assertEqual(manifest['assemblies'][0]['anchor'],'assemblies.CDF-001')
        readback=json.loads((work/'readback-manifest.json').read_text())
        self.assertTrue(any(o['kind']=='assembly' for o in readback['objects']))

    def test_preflight_structural_errors_are_not_downgraded_for_concept(self):
        cases=[('empty_label',lambda a:a['SUPPLY'].update(label='  ')),
               ('missing_label',lambda a:a['SUPPLY'].pop('label')),
               ('one_member',lambda a:a['SUPPLY'].update(members=['PF-001'])),
               ('duplicate',lambda a:a['SUPPLY'].update(members=['PF-001','PF-001'])),
               ('two_owners',lambda a:a.update(SECOND={'label':'Second','members':['EDP-001','TANK-001']})),
               ('nested',lambda a:a['SUPPLY'].update(members=['PF-001','SUPPLY'])),
               ('bad_id',lambda a:a.update({'bad.id':a.pop('SUPPLY')}))]
        original=copy.deepcopy(self.intent)
        for name,mutate in cases:
            with self.subTest(name=name):
                self.intent=copy.deepcopy(original);mutate(self.intent['assemblies']);self.write_intent()
                result=self.cli('preflight.py',self.intent_path,'--json')
                self.assertEqual(result.returncode,1,result.stdout+result.stderr)
                self.assertTrue(any(f['level']=='ERROR' for f in json.loads(result.stdout)['findings']))
        self.intent=original;self.intent['paths'][1][-1]='SUPPLY.inlet';self.write_intent()
        result=self.cli('preflight.py',self.intent_path,'--json')
        self.assertEqual(result.returncode,1)
        self.assertTrue(any(f['id']=='E-ASSEMBLY-ENDPOINT' for f in json.loads(result.stdout)['findings']))

    def test_validator_rejects_unrelated_pipe_crossing_enclosure(self):
        import xml.etree.ElementTree as ET
        self.write_intent()
        self.assertEqual(self.cli('render_l0_sheet.py',self.work).returncode,0)
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        lines=next(e for e in root.iter() if e.get('id')=='lines')
        ET.SubElement(lines,'{http://www.w3.org/2000/svg}polyline',{
            'id':'foreign-pipe','class':'ln-return','points':'400,520 1100,520',
            'data-input-anchor':'paths[0][0->1]','data-edge':'paths[0][0->1]'})
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.cli('validate_sheet.py',self.work)
        report=json.loads((self.work/'validation-report.json').read_text())
        crossing=[c for c in report['checks'] if c.get('kind')=='assembly_boundary_crossing']
        self.assertTrue(crossing,report['checks'])
        self.assertTrue(all(c['result']=='fail' and c.get('position') and c.get('anchor')=='assemblies.SUPPLY' for c in crossing))

    def test_validator_rejects_enclosure_including_a_nonmember(self):
        import xml.etree.ElementTree as ET
        self.write_intent();self.assertEqual(self.cli('render_l0_sheet.py',self.work).returncode,0)
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        frame=next(e for e in root.iter() if e.get('id')=='assembly-SUPPLY')
        frame.set('x','50');frame.set('y','70');frame.set('width','1000');frame.set('height','700')
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.cli('validate_sheet.py',self.work)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertTrue(any(c.get('kind')=='assembly_nonmember' and c.get('component')=='TANK-001' for c in report['checks']))

    def test_preflight_allows_auxiliary_member_without_new_connections(self):
        self.intent['parts']['PG-AUX']='pressure_gauge'
        self.intent['assemblies']['SUPPLY']['members'].append('PG-AUX')
        self.intent.setdefault('unknown',[]).append('PG-AUX connection pending')
        self.write_intent()
        result=self.cli('preflight.py',self.intent_path,'--json')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_missing_glyph_measurement_cannot_certify_enclosure(self):
        import xml.etree.ElementTree as ET
        self.write_intent();self.assertEqual(self.cli('render_l0_sheet.py',self.work).returncode,0)
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        label=next(e for e in root.iter() if e.get('data-label-for')=='EDP-001')
        label.set('filter','url(#unknown-filter)')
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.cli('validate_sheet.py',self.work)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V20'),'not_checked')

    def test_assembly_label_must_stay_left_aligned_above_frame(self):
        import xml.etree.ElementTree as ET
        self.write_intent();self.assertEqual(self.cli('render_l0_sheet.py',self.work).returncode,0)
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        label=next(e for e in root.iter() if e.get('id')=='assembly-label-SUPPLY')
        label.set('transform','translate(50,0)')
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.cli('validate_sheet.py',self.work)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertTrue(any(c.get('kind')=='assembly_label' for c in report['checks']))

    def test_assembly_panel_overlap_has_zero_budget(self):
        import xml.etree.ElementTree as ET
        self.write_intent();self.assertEqual(self.cli('render_l0_sheet.py',self.work).returncode,0)
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        frame=next(e for e in root.iter() if e.get('id')=='assembly-SUPPLY')
        legend=next(e for e in root.iter() if e.get('class')=='lg')
        frame.set('x',legend.get('x'));frame.set('y',legend.get('y'))
        frame.set('width','50');frame.set('height','50')
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.cli('validate_sheet.py',self.work)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertTrue(any(c.get('kind')=='assembly_panel_overlap' and c['id']=='V7' for c in report['checks']))
