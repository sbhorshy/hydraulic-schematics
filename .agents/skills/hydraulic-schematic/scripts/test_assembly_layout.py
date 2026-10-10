"""Single-row assembly layout through the engine and fresh driver CLI seams."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_entrypoints import SKILL
FIXTURE=SKILL/'assets/fixtures/l0-assembly-seed'
CATALOG=SKILL/'assets/component-library/component-catalog.json'

class AssemblyLayoutCLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='assembly-layout-')
        self.addCleanup(self.tmp.cleanup)
        self.work=Path(self.tmp.name)

    def engine(self,*params,ref=None,intent=None,catalog=None):
        args=[sys.executable,str(SKILL/'scripts/layout_engine.py'),str(intent or FIXTURE/'1#系统.intent.yaml'),
              str(catalog or CATALOG),str(ref or FIXTURE/'1#系统.layout.json'),'-o',str(self.work/'layout.json'),
              '--guard-report',str(self.work/'guard.json')]
        for value in params:args+=['--param',value]
        return subprocess.run(args,capture_output=True,text=True)

    def test_cdf_no_tank_layout_aligns_real_ports_and_passes_fresh_driver(self):
        result=self.engine()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        layout=json.loads((self.work/'layout.json').read_text())
        body,cv=(layout['nodes'][n] for n in ('CDF-001-BODY','CDF-001-CV'))
        self.assertEqual([body['w'],body['h']],[100,158])
        self.assertAlmostEqual(body['y']+114,cv['y']+40)
        self.assertGreaterEqual(cv['x']-body['x']-100,40)
        self.assertEqual(cv['rot'],180)
        self.assertEqual(layout['buses'],{})
        result=subprocess.run([sys.executable,str(SKILL/'scripts/validate_driver.py'),'--intent',str(FIXTURE/'1#系统.intent.yaml'),
                               '--layout-seed',str(self.work/'layout.json'),'--workdir',str(self.work/'driver'),'--rounds','1'],capture_output=True,text=True)
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)
        report=json.loads((self.work/'driver/validation-report.json').read_text())
        self.assertEqual(report['fail_count'],0,report['checks'])
        self.assertTrue(all(i['status']=='pass' for i in report['composition_budget']['items']),report['composition_budget'])
        self.assertTrue((self.work/'driver/sheet-readback.png').is_file())

    def test_long_body_label_flips_next_label_above_at_b5_minimum(self):
        ref=json.loads((FIXTURE/'1#系统.layout.json').read_text())
        ref['labels']['CDF-001-BODY']='Long assembly member label with wide readable text across the row'
        ref['labels']['CDF-001-CV']='CV'
        reference=self.work/'ref.json';reference.write_text(json.dumps(ref))
        result=self.engine(ref=reference)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        layout=json.loads((self.work/'layout.json').read_text());body=layout['nodes']['CDF-001-BODY'];cv=layout['nodes']['CDF-001-CV']
        self.assertEqual(layout['label_pos']['CDF-001-CV'],'above')
        self.assertAlmostEqual(cv['x']-body['x']-100,40)
        self.assertIn('font_environment',layout['assembly_layout']['text_measurement'])

    def test_changed_nonsquare_symbol_rotates_actual_source_ports_and_ignores_old_size(self):
        symbol=self.work/'changed-body.svg'
        symbol.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 20 40 100">
          <g fill="none" stroke="black"><rect x="15" y="40" width="30" height="60"/>
          <line x1="30" y1="20" x2="30" y2="40"/><line x1="30" y1="100" x2="30" y2="120"/></g>
          <g id="connection-points"><circle cx="30" cy="120" data-port-id="inlet" data-anchor-direction="down" data-medium="hydraulic" data-port-role="case_drain"/>
          <circle cx="30" cy="20" data-port-id="outlet" data-anchor-direction="up" data-medium="hydraulic" data-port-role="case_drain"/></g></svg>''')
        ref=json.loads((FIXTURE/'1#系统.layout.json').read_text());ref['nodes']['CDF-001-BODY'].update(symbol=str(symbol),rot=90,w=1,h=1)
        reference=self.work/'ref.json';reference.write_text(json.dumps(ref))
        result=self.engine(ref=reference)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        layout=json.loads((self.work/'layout.json').read_text());body=layout['nodes']['CDF-001-BODY'];cv=layout['nodes']['CDF-001-CV']
        self.assertEqual([body['w'],body['h'],body['rot']],[40,100,90])
        self.assertAlmostEqual(body['y'],280)
        self.assertGreaterEqual(cv['x']-body['x']-100,40)
        self.assertAlmostEqual(layout['externs']['CASE-IN']['y'],300)
        self.assertAlmostEqual(layout['externs']['CASE-OUT']['y'],300)

    def test_knobs_control_run_height_gap_and_endpoint_leads(self):
        result=self.engine('ASSEMBLY_RUN_Y=400','ASSEMBLY_START_X=350','ASSEMBLY_STUB_IN=130','ASSEMBLY_STUB_OUT=150','BOX_GAP=60')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        layout=json.loads((self.work/'layout.json').read_text());body=layout['nodes']['CDF-001-BODY'];cv=layout['nodes']['CDF-001-CV']
        self.assertAlmostEqual(body['y']+114,400)
        self.assertAlmostEqual(body['x'],350)
        self.assertAlmostEqual(layout['externs']['CASE-IN']['x'],220)
        self.assertAlmostEqual(layout['externs']['CASE-OUT']['x'],cv['x']+80+150)
        self.assertGreaterEqual(cv['x']-body['x']-100,60)

    def test_unsupported_graph_fails_closed_and_removes_previous_output(self):
        from ruamel.yaml import YAML
        self.assertEqual(self.engine().returncode,0)
        intent=YAML().load(FIXTURE/'1#系统.intent.yaml')
        intent['paths'].append(['CDF-001-CV.outlet','CASE-OUT'])
        path=self.work/'intent.yaml';YAML().dump(intent,path)
        result=self.engine(intent=path)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('R17',result.stderr)
        self.assertNotIn('Traceback',result.stderr)
        self.assertFalse((self.work/'layout.json').exists())
        self.assertFalse((self.work/'guard.json').exists())

    def test_driver_without_seed_selects_assembly_branch_and_real_png(self):
        result=subprocess.run([sys.executable,str(SKILL/'scripts/validate_driver.py'),'--intent',str(FIXTURE/'1#系统.intent.yaml'),
                               '--workdir',str(self.work/'driver'),'--rounds','1'],capture_output=True,text=True)
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)
        report=json.loads((self.work/'driver/validation-report.json').read_text())
        self.assertEqual(report['fail_count'],0,report['checks'])
        layout=json.loads((self.work/'driver/1#系统.layout.json').read_text())
        self.assertEqual(layout['assembly_layout']['rule'],'R17')
        self.assertEqual(layout['nodes']['CDF-001-CV']['rot'],180)

    def test_unsupported_orientation_and_lowered_budgets_are_actionable(self):
        reference=self.work/'ref.json';ref=json.loads((FIXTURE/'1#系统.layout.json').read_text())
        ref['nodes']['CDF-001-CV']['rot']=90;reference.write_text(json.dumps(ref))
        result=self.engine(ref=reference)
        self.assertNotEqual(result.returncode,0);self.assertIn('R17',result.stderr);self.assertNotIn('Traceback',result.stderr)
        for parameter in ('BOX_GAP=20','ASSEMBLY_TEXT_CLEAR=3','ASSEMBLY_RUN_Y=-1'):
            with self.subTest(parameter=parameter):
                result=self.engine(parameter)
                self.assertNotEqual(result.returncode,0);self.assertIn('R17',result.stderr)
                self.assertFalse((self.work/'layout.json').exists())

    def test_below_labels_expand_gap_only_as_far_as_actual_ink_requires(self):
        ref=json.loads((FIXTURE/'1#系统.layout.json').read_text())
        ref['labels']['CDF-001-BODY']='W'*18;ref['labels']['CDF-001-CV']='W'*10
        reference=self.work/'ref.json';reference.write_text(json.dumps(ref))
        result=self.engine(ref=reference)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        layout=json.loads((self.work/'layout.json').read_text());body=layout['nodes']['CDF-001-BODY'];cv=layout['nodes']['CDF-001-CV']
        gap=cv['x']-body['x']-100
        self.assertGreater(gap,40);self.assertLessEqual(gap,80)
        self.assertEqual(layout['label_pos']['CDF-001-CV'],'below')
        result=subprocess.run([sys.executable,str(SKILL/'scripts/validate_driver.py'),'--intent',str(FIXTURE/'1#系统.intent.yaml'),
                               '--layout-seed',str(self.work/'layout.json'),'--workdir',str(self.work/'driver'),'--rounds','1'],capture_output=True,text=True)
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)
        report=json.loads((self.work/'driver/validation-report.json').read_text())
        self.assertEqual(next(b['status'] for b in report['composition_budget']['items'] if b['id']=='B7'),'pass',report['checks'])

    def test_boundary_lead_too_short_for_padded_enclosure_is_rejected(self):
        result=self.engine('ASSEMBLY_STUB_IN=1')
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('R17',result.stderr)
        self.assertFalse((self.work/'layout.json').exists())

    def test_narrow_canvas_rejects_panels_instead_of_emitting_clipped_layout(self):
        result=self.engine('CANVAS_W=700')
        self.assertNotEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse((self.work/'layout.json').exists())
