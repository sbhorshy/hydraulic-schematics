"""Root-SVG layout migration and drawable paint bounds at public CLI seams."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_entrypoints import SKILL, make_render_workspace


class CoordinateContract(unittest.TestCase):
    def test_legacy_seed_keeps_actual_positions_and_gains_explicit_right_margin(self):
        with tempfile.TemporaryDirectory(prefix='coordinate-contract-') as directory:
            source = Path(directory) / 'old.layout.json'
            target = Path(directory) / 'root.layout.json'
            legacy = {
                'canvas': {'width':1680, 'height':1390}, 'canvas_shift_x':30,
                'nodes': {'RF': {'x':1200, 'y':1012, 'w':100, 'h':194, 'rot':180}},
                'buses': {'USERR':{'kind':'v', 'x':1646}},
                'externs': {'END':{'x':1480, 'y':300, 'anchor':'left', 'label':'END'}},
                'lanes':[890], 'vlanes':[20,290], 'boundary_terminals':[[1480,300]],
                'legend':{'x':380, 'y':1020, 'w':540, 'h':290},
                'title_block':{'x':40, 'y':1330, 'w':1600, 'h':56},
            }
            source.write_text(json.dumps(legacy))
            result = subprocess.run([sys.executable, str(SKILL/'scripts/migrate_layout.py'),
                                     str(source), '-o', str(target)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            migrated = json.loads(target.read_text())
            self.assertNotIn('canvas_shift_x', migrated)
            self.assertEqual(migrated['nodes']['RF']['x'], 1230)
            self.assertEqual(migrated['buses']['USERR']['x'], 1676)
            self.assertEqual(migrated['externs']['END']['x'], 1510)
            self.assertEqual(migrated['vlanes'], [50,320])
            self.assertEqual(migrated['boundary_terminals'], [[1510,300]])
            self.assertEqual(migrated['legend'], legacy['legend'])
            self.assertEqual(migrated['title_block'], legacy['title_block'])
            self.assertEqual(migrated['edge_margin'], 30)
            self.assertEqual(migrated['canvas']['width'], 1710)
            self.assertEqual(migrated['drawable'], {'x':0, 'y':0, 'width':1680, 'height':1390})
            self.assertEqual(json.loads(source.read_text()), legacy)

    def test_renderer_rejects_legacy_shift_with_an_actionable_migration_error(self):
        with tempfile.TemporaryDirectory(prefix='legacy-contract-') as directory:
            work = make_render_workspace(Path(directory), SKILL/'assets/fixtures/l0-small-seed')
            path = work/'1#系统.layout.json'
            layout = json.loads(path.read_text());layout['canvas_shift_x']=30
            path.write_text(json.dumps(layout))
            run = subprocess.run([sys.executable,str(SKILL/'scripts/render_l0_sheet.py'),str(work)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('migrate_layout.py',run.stdout+run.stderr)
            self.assertFalse((work/'1#系统原理图.svg').exists())

    def test_validator_checks_bus_paint_not_only_centerline_against_drawable(self):
        with tempfile.TemporaryDirectory(prefix='paint-margin-') as directory:
            work = make_render_workspace(Path(directory), SKILL/'assets/fixtures/l0-current')
            path = work/'1#系统.layout.json'
            run = subprocess.run([sys.executable,str(SKILL/'scripts/migrate_layout.py'),str(path),'-o',str(path)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            layout=json.loads(path.read_text())
            layout['drawable']['width']=layout['buses']['USERR']['x']
            path.write_text(json.dumps(layout))
            run=subprocess.run([sys.executable,str(SKILL/'scripts/render_l0_sheet.py'),str(work)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            subprocess.run([sys.executable,str(SKILL/'scripts/validate_sheet.py'),str(work)],capture_output=True,text=True)
            report=json.loads((work/'validation-report.json').read_text())
            hits=[c for c in report['checks'] if c['id']=='V6' and c.get('anchor')=='buses.USERR']
            self.assertTrue(hits,report['checks'])
            self.assertGreater(hits[0]['overflow']['right'],0.5)

    def test_system_and_assembly_engines_emit_the_same_explicit_contract(self):
        with tempfile.TemporaryDirectory(prefix='engine-contract-') as directory:
            for name in ('l0-current','l0-assembly-seed'):
                with self.subTest(fixture=name):
                    source=SKILL/'assets/fixtures'/name
                    target=Path(directory)/(name+'.json')
                    run=subprocess.run([sys.executable,str(SKILL/'scripts/layout_engine.py'),
                        str(source/'1#系统.intent.yaml'),str(SKILL/'assets/component-library/component-catalog.json'),
                        str(source/'1#系统.layout.json'),'-o',str(target)],capture_output=True,text=True)
                    self.assertEqual(run.returncode,0,run.stdout+run.stderr)
                    layout=json.loads(target.read_text())
                    self.assertNotIn('canvas_shift_x',layout)
                    self.assertEqual(layout['edge_margin'],30)
                    self.assertEqual(layout['drawable']['x']+layout['drawable']['width']+30,layout['canvas']['width'])

    def test_visible_component_stroke_beyond_its_viewbox_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='body-paint-margin-') as directory:
            work=make_render_workspace(Path(directory),SKILL/'assets/fixtures/l0-small-seed')
            path=work/'1#系统.layout.json';layout=json.loads(path.read_text())
            layout['drawable']['width']=930
            path.write_text(json.dumps(layout))
            run=subprocess.run([sys.executable,str(SKILL/'scripts/render_l0_sheet.py'),str(work)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            svg=work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
            instance=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
            ET.SubElement(instance,'{http://www.w3.org/2000/svg}line',{
                'id':'body-edge-probe','x1':'80','y1':'20','x2':'80','y2':'60',
                'style':'stroke:black;stroke-width:10!important;fill:none'})
            ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
            subprocess.run([sys.executable,str(SKILL/'scripts/validate_sheet.py'),str(work)],capture_output=True,text=True)
            report=json.loads((work/'validation-report.json').read_text())
            hits=[c for c in report['checks'] if c['id']=='V6' and c.get('component')=='PF-001']
            self.assertTrue(hits,report['checks'])
            self.assertGreaterEqual(max(c['overflow']['right'] for c in hits),4.9)

    def test_closed_acute_miter_stroke_cannot_escape_the_drawable_gate(self):
        with tempfile.TemporaryDirectory(prefix='miter-paint-margin-') as directory:
            work=make_render_workspace(Path(directory),SKILL/'assets/fixtures/l0-small-seed')
            path=work/'1#系统.layout.json';layout=json.loads(path.read_text());layout['drawable']['width']=945
            path.write_text(json.dumps(layout))
            run=subprocess.run([sys.executable,str(SKILL/'scripts/render_l0_sheet.py'),str(work)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            svg=work/'1#系统原理图.svg';original=svg.read_text()
            for tag,attrs in (('polygon',{'points':'80,20 50,10 50,30'}),
                              ('path',{'d':'M80 20 L50 10 L50 30 Z'})):
                with self.subTest(primitive=tag):
                    root=ET.fromstring(original);instance=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
                    ET.SubElement(instance,'{http://www.w3.org/2000/svg}'+tag,{
                        'id':'miter-edge-probe',**attrs,
                        'style':'stroke:black;stroke-width:20!important;fill:none;stroke-linejoin:miter;stroke-miterlimit:4'})
                    ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
                    subprocess.run([sys.executable,str(SKILL/'scripts/validate_sheet.py'),str(work)],capture_output=True,text=True)
                    report=json.loads((work/'validation-report.json').read_text())
                    hits=[c for c in report['checks'] if c['id']=='V6' and c.get('svg_id')=='miter-edge-probe']
                    self.assertTrue(hits,report['checks'])
                    # Worked triangle: r/sin(arctan(1/3)) = 10*sqrt(10).
                    self.assertAlmostEqual(hits[0]['box'][2],930+10*(10**.5),places=5)
                    self.assertGreater(hits[0]['overflow']['right'],16)
                    # The same corner with miterlimit 3 becomes a bevel; do not
                    # invent an oversized miter or reject its actual paint.
                    probe=next(e for e in root.iter() if e.get('id')=='miter-edge-probe')
                    probe.set('style',probe.get('style').replace('miterlimit:4','miterlimit:3'))
                    svg.write_text(ET.tostring(root,encoding='unicode'))
                    subprocess.run([sys.executable,str(SKILL/'scripts/validate_sheet.py'),str(work)],capture_output=True,text=True)
                    clipped=json.loads((work/'validation-report.json').read_text())
                    self.assertFalse([c for c in clipped['checks'] if c['id']=='V6' and c.get('svg_id')=='miter-edge-probe'])



if __name__ == '__main__': unittest.main()
