"""Regression for the priority-valve external leads and V16's former path blind spot."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import make_render_workspace, FIXTURE

NS = '{http://www.w3.org/2000/svg}'


class PriorityValveLeads(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='priority-leads-')
        self.addCleanup(self.temp.cleanup)
        self.work = make_render_workspace(Path(self.temp.name), FIXTURE)
        self.svg = self.work / '1#系统原理图.svg'
        result = subprocess.run([sys.executable, str(self.work / 'render_l0_sheet.py')],
                                cwd=self.work, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.root = ET.parse(self.svg).getroot()

    def instance(self, name):
        return next(e for e in self.root.iter() if e.get('id') == 'inst-' + name)

    def leads(self, name):
        return [e for e in self.instance(name).iter() if e.get('data-interface-port')]

    def check_v16(self):
        result = subprocess.run([sys.executable, str(self.work / 'validate_sheet.py')],
                                cwd=self.work, capture_output=True, text=True, timeout=15)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        report = json.loads((self.work / 'validation-report.json').read_text())
        return [c['detail'] for c in report['checks'] if c['id'] == 'V16' and c['result'] == 'fail']

    def test_pressure_leads_match_connected_network_for_both_rotations(self):
        for name in ('PRV-001', 'PRV-002'):
            with self.subTest(instance=name):
                leads = self.leads(name)
                self.assertEqual(len(leads), 2)
                for lead in leads:
                    self.assertEqual(lead.tag, NS + 'line')
                    self.assertIn('pl-pressure', lead.get('class', '').split())
                # The internal passages and housing retain outline styling.
                for e in self.instance(name).iter():
                    if e.get('id', '').endswith(('__housing', '__main-pipeline-left', '__main-pipeline-right')):
                        self.assertNotIn('pl-pressure', e.get('class', ''))

    def test_valid_external_leads_pass_v16(self):
        self.assertEqual(self.check_v16(), [])

    def test_missing_pressure_style_is_rejected(self):
        for name in ('PRV-001', 'PRV-002'):
            for lead in self.leads(name):
                lead.attrib.pop('class', None)
        ET.register_namespace('', NS[1:-1])
        self.svg.write_text(ET.tostring(self.root, encoding='unicode'))
        failures = self.check_v16()
        self.assertTrue(any('PRV-001' in f for f in failures), failures)
        self.assertTrue(any('PRV-002' in f for f in failures), failures)

    def test_port_path_cannot_evade_width_check(self):
        for name in ('PRV-001', 'PRV-002'):
            for lead in self.leads(name):
                if lead.tag == NS + 'line':
                    lead.set('d', 'M%s %s L%s %s' % tuple(lead.attrib.pop(k) for k in ('x1', 'y1', 'x2', 'y2')))
                    lead.tag = NS + 'path'
                # Reproduce the original path-inheriting-outline failure.
                lead.attrib.pop('class', None)
        ET.register_namespace('', NS[1:-1])
        self.svg.write_text(ET.tostring(self.root, encoding='unicode'))
        failures = self.check_v16()
        self.assertTrue(any('PRV-001' in f for f in failures), failures)
        self.assertTrue(any('PRV-002' in f for f in failures), failures)


if __name__ == '__main__':
    unittest.main()
