"""Observable SVG/CLI regressions for effective external lead stroke widths."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_entrypoints import make_render_workspace, FIXTURE

NS = '{http://www.w3.org/2000/svg}'


class DisplayWidths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='display-widths-')
        self.addCleanup(self.temp.cleanup)
        self.work = make_render_workspace(Path(self.temp.name), FIXTURE)
        self.svg = self.work / '1#系统原理图.svg'

    def run_cli(self, script):
        result = subprocess.run([sys.executable, str(self.work / script)], cwd=self.work,
                                capture_output=True, text=True, timeout=40)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)

    def validate(self):
        self.run_cli('validate_sheet.py')
        return json.loads((self.work / 'validation-report.json').read_text())

    def test_equivalent_source_path_and_polyline_leads_follow_network(self):
        symbol = self.work / 'symbols/priority-valve.svg'
        tree = ET.parse(symbol)
        leads = [e for e in tree.getroot().iter() if e.get('data-interface-port')]
        for e, kind in zip(leads, ('path', 'polyline')):
            coords = [e.attrib.pop(a) for a in ('x1', 'y1', 'x2', 'y2')]
            e.tag = NS + kind
            e.set('d' if kind == 'path' else 'points',
                  'M%s %s H%s' % (coords[0], coords[1], coords[2]) if kind == 'path'
                  else '%s,%s %s,%s %s,%s' % tuple(coords[:2]+coords))
        ET.register_namespace('', NS[1:-1])
        tree.write(symbol, encoding='unicode')
        self.run_cli('render_l0_sheet.py')
        report = self.validate()
        failures = [c for c in report['checks'] if c['id'] == 'V16' and c['result'] == 'fail']
        self.assertEqual(failures, [])
        evidence = next(e for e in report['evidence'] if e['id'] == 'V16')
        measured = [m for m in evidence['measurements'] if m['component'].startswith('PRV-')]
        self.assertEqual(len(measured), 4, evidence)
        self.assertTrue(all(abs(m['effective_width'] - 3.6) < .02 for m in measured), measured)

    def test_current_leads_have_complete_browser_measurement_coverage(self):
        self.run_cli('render_l0_sheet.py')
        report = self.validate()
        for ident in ('V15', 'V16'):
            coverage = next(c for c in report['coverage'] if c['id'] == ident)
            self.assertEqual(coverage['status'], 'pass', coverage)
        measurements = next(e for e in report['evidence'] if e['id'] == 'V16')['measurements']
        self.assertTrue({'PRV-001','PRV-002','PF-001','EDP-001'} <= {m['component'] for m in measurements})

    def save(self, root):
        ET.register_namespace('', NS[1:-1])
        self.svg.write_text(ET.tostring(root, encoding='unicode'))

    def target(self, root):
        return next(e for e in root.iter() if e.get('id') == 'PRV-001__port-lead-inlet')

    def failures(self, report, ident='V16'):
        return [c['detail'] for c in report['checks'] if c['id'] == ident and c['result'] == 'fail']

    def test_use_lead_is_explicitly_unchecked_with_object_location(self):
        self.run_cli('render_l0_sheet.py')
        root = ET.parse(self.svg).getroot()
        lead = self.target(root)
        copied = ET.fromstring(ET.tostring(lead))
        copied.set('id', 'reused-lead')
        copied.attrib.pop('data-interface-port')
        defs = ET.SubElement(root, NS+'defs')
        defs.append(copied)
        lead.attrib.clear()
        lead.tag = NS+'use'
        lead.set('href','#reused-lead')
        lead.set('id','PRV-001__port-lead-inlet')
        lead.set('data-interface-port','inlet')
        self.save(root)
        report = self.validate()
        ev = next(e for e in report['evidence'] if e['id']=='V16')
        self.assertEqual(ev['coverage_status'],'not_checked')
        self.assertTrue(any(e.get('component')=='PRV-001' and e.get('port')=='inlet' and e.get('position')
                            for e in ev['unchecked']), ev)
        self.assertFalse(any('PRV-001.inlet' in f for f in self.failures(report)))

    def test_css_overrides_and_extra_scale_cannot_hide_behind_correct_class(self):
        self.run_cli('render_l0_sheet.py')
        original = self.svg.read_text()
        for kind in ('inline', 'selector', 'nested-scale'):
            with self.subTest(kind=kind):
                root = ET.fromstring(original)
                lead = self.target(root)
                if kind == 'inline':
                    lead.set('style', 'stroke-width:1.8px')
                elif kind == 'selector':
                    style = ET.SubElement(root, NS+'style')
                    style.text = '#PRV-001__port-lead-inlet { stroke-width: 1.8px !important; }'
                else:
                    parent = next(p for p in root.iter() if lead in list(p))
                    parent.remove(lead)
                    wrapper = ET.SubElement(parent, NS+'g', {'transform':'scale(2)'})
                    for key in ('x1','y1','x2','y2'):
                        lead.set(key, str(float(lead.get(key))/2))
                    wrapper.append(lead)
                self.save(root)
                self.assertTrue(any('PRV-001.inlet' in f and 'effective lead width' in f
                                    for f in self.failures(self.validate())))

    def test_inherited_width_and_compensated_nested_source_scale_are_valid(self):
        symbol = self.work / 'symbols/priority-valve.svg'
        tree = ET.parse(symbol)
        lead = next(e for e in tree.getroot().iter() if e.get('data-interface-port')=='inlet')
        parent = next(p for p in tree.getroot().iter() if lead in list(p))
        parent.remove(lead)
        wrapper = ET.SubElement(parent, NS+'g', {'transform':'translate(0,0) scale(2)'})
        for key in ('x1','y1','x2','y2'):
            lead.set(key, str(float(lead.get(key))/2))
        wrapper.append(lead)
        ET.register_namespace('', NS[1:-1])
        tree.write(symbol,encoding='unicode')
        self.run_cli('render_l0_sheet.py')
        root = ET.parse(self.svg).getroot()
        lead = self.target(root)
        lead.attrib.pop('class')
        parent = next(p for p in root.iter() if lead in list(p))
        parent.set('style','stroke-width:1.8px')
        self.save(root)
        report = self.validate()
        self.assertEqual(self.failures(report), [])
        browser = json.loads((self.work/'browser-evidence.json').read_text())
        housing = next(e for e in browser['elements'] if e['id']=='PRV-001__housing')
        internal = next(e for e in browser['elements'] if e['id']=='PRV-001__main-pipeline-left')
        self.assertEqual(housing['style']['stroke-width'], 'calc(1.8px)')
        self.assertEqual(internal['style']['stroke-width'], 'calc(1.8px)')

    def test_width_transition_in_blank_lead_is_rejected(self):
        self.run_cli('render_l0_sheet.py')
        root = ET.parse(self.svg).getroot()
        lead = self.target(root)
        parent = next(p for p in root.iter() if lead in list(p))
        rest = ET.fromstring(ET.tostring(lead))
        lead.set('x2','16')
        rest.set('x1','16')
        rest.set('id','premature-outline-transition')
        rest.set('class','sym-outline')
        rest.attrib.pop('data-interface-port')
        parent.append(rest)
        self.save(root)
        failures = self.failures(self.validate())
        self.assertTrue(any('PRV-001.inlet' in f and 'body boundary' in f for f in failures), failures)

    def test_browser_unavailable_is_unchecked_and_stale_sidecar_is_not_reused(self):
        self.run_cli('render_l0_sheet.py')
        self.validate()
        import os
        env = dict(os.environ, PATH='')
        result = subprocess.run([sys.executable, str(self.work/'validate_sheet.py')],cwd=self.work,
                                env=env,capture_output=True,text=True,timeout=30)
        self.assertIn(result.returncode,(0,1),result.stderr)
        report = json.loads((self.work/'validation-report.json').read_text())
        for ident in ('V15','V16'):
            self.assertEqual(next(e for e in report['coverage'] if e['id']==ident)['status'],'not_checked')

    def test_actual_png_width_ratios_at_normal_and_double_scale(self):
        import os
        import shutil
        from PIL import Image
        self.run_cli('render_l0_sheet.py')
        self.validate()
        original = self.svg.read_text()
        executable = shutil.which('google-chrome') or shutil.which('chromium')
        self.assertTrue(executable, 'Actual browser PNG evidence requires Chrome')
        energies = []
        for scale in (1,2):
            root = ET.fromstring(original)
            root.set('width',str(1680*scale))
            root.set('height',str(1390*scale))
            source = self.work / ('scale-%d.svg' % scale)
            source.write_text(ET.tostring(root,encoding='unicode'))
            png = self.work / ('scale-%d.png' % scale)
            command = [executable,'--headless','--disable-gpu','--hide-scrollbars',
                       '--force-device-scale-factor=1','--user-data-dir='+str(self.work/('profile-%d'%scale)),
                       '--window-size=%d,%d'%(1680*scale,1390*scale),'--screenshot='+str(png)]
            if hasattr(os,'geteuid') and os.geteuid()==0:
                command.append('--no-sandbox')
            result = subprocess.run(command+[source.as_uri()],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            image = Image.open(png).convert('L')
            def ink(x,y):
                x,y = round(x*scale),round(y*scale)
                return sum((255-image.getpixel((x,yy)))/255 for yy in range(y-6*scale,y+6*scale+1))
            lead,pipe,body = ink(1345,317.2222),ink(1310,317.2222),ink(1370,303.8272)
            # Integrated darkness tolerates edge antialiasing without arbitrary binary pixel counts.
            self.assertAlmostEqual(lead/pipe,1,delta=.12)
            self.assertAlmostEqual(body/lead,.5,delta=.15)
            self.assertAlmostEqual(lead/scale,3.6,delta=.5)
            energies.append(lead)
        self.assertAlmostEqual(energies[1]/energies[0],2,delta=.2)

    def test_pressure_lead_cannot_extend_past_defined_body_boundary(self):
        self.run_cli('render_l0_sheet.py')
        root = ET.parse(self.svg).getroot()
        self.target(root).set('x2','42')
        self.save(root)
        failures = self.failures(self.validate())
        self.assertTrue(any('PRV-001.inlet' in f and 'boundary' in f for f in failures), failures)

    def test_tampered_browser_measurements_are_invalidated_and_remeasured(self):
        self.run_cli('render_l0_sheet.py')
        self.validate()
        sidecar = self.work/'browser-evidence.json'
        evidence = json.loads(sidecar.read_text())
        row = next(e for e in evidence['elements'] if e['id']=='PRV-001__port-lead-inlet')
        row['style']['stroke-width']='1.8px'
        sidecar.write_text(json.dumps(evidence))
        result = subprocess.run([sys.executable,str(self.work/'proofreading_evidence.py'),'verify',str(self.work)],
                                cwd=self.work,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,1,result.stdout)
        self.assertIn('browser_evidence',result.stdout)
        report = self.validate()
        self.assertEqual(self.failures(report),[])
        measurements = next(e for e in report['evidence'] if e['id']=='V16')['measurements']
        lead = next(m for m in measurements if m['component']=='PRV-001' and m['port']=='inlet')
        self.assertAlmostEqual(lead['effective_width'],3.6,places=2)

    def test_unannotated_curved_source_lead_cannot_disappear_from_coverage(self):
        symbol = self.work/'symbols/priority-valve.svg'
        tree = ET.parse(symbol)
        lead = next(e for e in tree.getroot().iter() if e.get('data-interface-port')=='inlet')
        lead.tag = NS+'path'
        lead.attrib.clear()
        lead.set('d','M0 27.2222 C10 20 20 20 32.8395 27.2222')
        ET.register_namespace('',NS[1:-1])
        tree.write(symbol,encoding='unicode')
        self.run_cli('render_l0_sheet.py')
        report = self.validate()
        evidence = next(e for e in report['evidence'] if e['id']=='V16')
        self.assertEqual(evidence['coverage_status'],'not_checked')
        self.assertTrue(any(e.get('component')=='PRV-001' and e.get('port')=='inlet'
                            for e in evidence['unchecked']),evidence['unchecked'])


if __name__ == '__main__':
    unittest.main()
