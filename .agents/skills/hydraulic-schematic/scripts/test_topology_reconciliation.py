"""Topology acceptance through canonical renderer and standalone validator CLIs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import make_render_workspace, SKILL


class TopologyCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='topology-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.work = make_render_workspace(Path(self.tmp.name), SKILL / 'assets/fixtures/l0-small-seed')
        self.svg = self.work / '1#系统原理图.svg'
        self.render()

    def render(self):
        p = subprocess.run([sys.executable, str(SKILL / 'scripts/render_l0_sheet.py'), str(self.work)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def edit(self, mutate):
        root = ET.parse(self.svg).getroot()
        mutate(root)
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root, encoding='unicode'))

    def validate(self):
        p = subprocess.run([sys.executable, str(SKILL / 'scripts/validate_sheet.py'), str(self.work)],
                           capture_output=True, text=True)
        report = json.loads((self.work / 'validation-report.json').read_text())
        self.assertEqual(p.returncode, 1 if report['fail_count'] else 0, p.stdout + p.stderr)
        return report

    def test_renderer_emits_input_anchors_and_manifest_without_extra_script(self):
        manifest = self.work / '1#系统原理图-topology.json'
        self.assertTrue(manifest.exists(), 'Canonical rendering must emit the traceability manifest')
        data = json.loads(manifest.read_text())
        self.assertEqual([(e['anchor'], e['endpoints']) for e in data['edges']], [
            ('paths[0][0->1]', ['TANK-001.suction_out', 'EDP-001.suction']),
            ('paths[1][0->1]', ['EDP-001.pressure_out', 'PF-001.inlet']),
            ('paths[1][1->2]', ['PF-001.outlet', 'USR-001'])])
        self.assertEqual(len(data['unknown']), 4)
        root = ET.parse(self.svg).getroot()
        node = next(e for e in root.iter() if e.get('id') == 'inst-EDP-001')
        self.assertEqual(node.get('data-node'), 'EDP-001')
        self.assertEqual(node.get('data-input-anchor'), 'parts.EDP-001')
        for line in root.iter():
            if line.get('class', '').startswith('ln-'):
                self.assertIn(line.get('data-edge'), {e['anchor'] for e in data['edges']})
                self.assertTrue(line.get('id'))
        self.assertTrue((self.work / '1#系统原理图-topology.md').exists())

    def test_deleted_connection_fails_at_its_input_anchor(self):
        def damage(root):
            group = next(e for e in root.iter() if e.get('id') == 'lines')
            group.remove(next(e for e in group if e.get('data-edge') == 'paths[1][0->1]'))
        self.edit(damage)
        report = self.validate()
        findings = [c for c in report['checks'] if c['id'] == 'V10']
        self.assertTrue(any(c.get('kind') == 'missing_connection' and
                            c.get('anchor') == 'paths[1][0->1]' for c in findings), findings)

    def test_series_connections_are_measured_and_coverage_is_complete(self):
        report = self.validate()
        self.assertFalse([c for c in report['checks'] if c['id'] == 'V10'])
        self.assertEqual({tuple(e['endpoints']) for e in report['topology']['actual_edges']}, {
            ('EDP-001.suction', 'TANK-001.suction_out'),
            ('EDP-001.pressure_out', 'PF-001.inlet'),
            ('PF-001.outlet', 'USR-001')})
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id'] == 'V10'), 'pass')

    def test_current_two_pumps_buses_and_gas_taps_reconcile(self):
        import shutil
        for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
            shutil.copy2(SKILL / 'assets/fixtures/l0-current' / name, self.work / name)
        self.render()
        report = self.validate()
        self.assertFalse([c for c in report['checks'] if c['id'] == 'V10'])
        self.assertEqual(len(report['topology']['expected_edges']), 31)
        self.assertTrue(any(e['anchor'] == 'taps[1]' for e in report['topology']['expected_edges']))


if __name__ == '__main__':
    unittest.main()
