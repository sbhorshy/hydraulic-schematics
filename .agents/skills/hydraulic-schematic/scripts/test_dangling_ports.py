"""V5 regressions at the render/validator CLI and SVG/report output seams."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import make_render_workspace, FIXTURE
from ruamel.yaml import YAML

SCRIPTS = Path(__file__).resolve().parent


OPEN_PORTS = [
    'CV-002.inlet', 'EDP-001.drive_shaft', 'EMP-001.elec_power',
    'QDP-001.ground_side', 'QDR-001.ground_side', 'TANK-001.body_sense_tap',
]


class DanglingPorts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dangling-ports-')
        self.addCleanup(self.temp.cleanup)
        self.work = make_render_workspace(Path(self.temp.name), FIXTURE)
        self.svg = self.work / '1#系统原理图.svg'

    def run_cli(self, name):
        result = subprocess.run([sys.executable, str(self.work / name)],
                                cwd=self.work, capture_output=True, text=True, timeout=30)
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        return result

    def render(self):
        result = self.run_cli('render_l0_sheet.py')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def validate(self):
        self.run_cli('validate_sheet.py')
        report = json.loads((self.work / 'validation-report.json').read_text())
        return report, next(e for e in report['evidence'] if e['id'] == 'V5')

    def assert_disclosure(self, expected):
        report, evidence = self.validate()
        self.assertEqual(evidence['dangling'], expected)
        self.assertFalse([c for c in report['checks']
                          if c['id'] == 'V5' and c['result'] == 'fail'])
        root = ET.parse(self.svg).getroot()
        group = next(e for e in root.iter() if e.get('id') == 'dangling')
        marks = list(group)
        self.assertEqual(sorted(e.get('data-port') for e in marks), expected)
        title = next(e for e in root.iter() if e.get('id') == 'title')
        text = ''.join(title.itertext())
        self.assertRegex(text, r'悬空端口\s+%d\b' % len(expected))
        for endpoint in expected:
            self.assertIn(endpoint, text)

    def test_connected_gas_taps_agree_with_open_ports_circles_and_title(self):
        self.render()
        self.assert_disclosure(OPEN_PORTS)

    def test_bare_last_instance_uses_only_main_path_in_and_inline_uses_both(self):
        def edit(intent):
            path = next(p for p in intent['paths'] if p[0] == 'CV-002')
            path.reverse()
        self.change_intent(edit)
        self.render()
        self.assert_disclosure(['CV-002.outlet'] + OPEN_PORTS[1:])

    def test_missing_red_circle_is_drawing_omission_not_input_change(self):
        self.render()
        root = ET.parse(self.svg).getroot()
        group = next(e for e in root.iter() if e.get('id') == 'dangling')
        group.remove(next(e for e in group if e.get('data-port') == 'EDP-001.drive_shaft'))
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root, encoding='unicode'))
        report, evidence = self.validate()
        self.assertEqual(evidence['dangling'], OPEN_PORTS)
        failures = [c for c in report['checks'] if c['id'] == 'V5' and c['result'] == 'fail']
        self.assertTrue(any('EDP-001.drive_shaft' in c['detail'] for c in failures), failures)

    def test_local_symbol_missing_open_port_is_contract_error(self):
        self.render()
        symbol = self.work / 'symbols/bootstrap-type-reservoir.svg'
        tree = ET.parse(symbol)
        group = next(e for e in tree.getroot().iter() if e.get('id') == 'connection-points')
        group.remove(next(e for e in group if e.get('data-port-id') == 'body_sense_tap'))
        tree.write(symbol, encoding='unicode')
        report, evidence = self.validate()
        self.assertEqual(evidence['dangling'], OPEN_PORTS)
        issues = evidence.get('contract_issues', [])
        self.assertTrue(any(i.get('endpoint') == 'TANK-001.body_sense_tap' for i in issues), issues)
        self.assertTrue(any(c['id'] == 'V5' and c['result'] == 'fail' for c in report['checks']))

    def test_missing_connected_port_marker_is_drawing_error(self):
        self.render()
        root = ET.parse(self.svg).getroot()
        instance = next(e for e in root.iter() if e.get('id') == 'inst-PG-001')
        markers = [e for e in instance if e.get('data-port') == 'PG-001.pressure_sense']
        self.assertEqual(len(markers), 1)
        instance.remove(markers[0])
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root, encoding='unicode'))
        report, evidence = self.validate()
        self.assertEqual(evidence['dangling'], OPEN_PORTS)
        self.assertEqual(evidence['contract_issues'], [])
        self.assertTrue(any(q.get('endpoint') == 'PG-001.pressure_sense'
                            and q['kind'] == 'drawn_port' for q in evidence['drawing_issues']))

    def change_intent(self, edit):
        path = self.work / '1#系统.intent.yaml'
        yaml = YAML()
        intent = yaml.load(path)
        edit(intent)
        yaml.dump(intent, path)

    def test_removing_tap_exposes_both_endpoints_and_keeps_unknowns(self):
        self.change_intent(lambda i: i['taps'].pop())
        self.render()
        expected = sorted(OPEN_PORTS + ['ACV-001.charge_port', 'PG-001.pressure_sense'])
        self.assert_disclosure(expected)
        _, evidence = self.validate()
        self.assertIn('accumulator-charge-source-not-declared', evidence['unknown'])
        self.assertIn('EDP-001-drive-shaft-destination', evidence['unknown'])

    def test_body_tap_consumes_measurement_anchor_without_exempting_other_open_ports(self):
        self.change_intent(lambda i: i['taps'].append(
            {'sensor': 'PG-001.pressure_sense', 'at': 'TANK-001.body_sense_tap'}))
        self.render()
        self.assert_disclosure(OPEN_PORTS[:-1])

    def test_stale_title_count_is_rejected(self):
        self.render()
        text = self.svg.read_text().replace('悬空端口 6:', '悬空端口 9:')
        self.svg.write_text(text)
        _, evidence = self.validate()
        self.assertEqual(evidence['dangling'], OPEN_PORTS)
        self.assertTrue(any(q['kind'] == 'dangling_title' for q in evidence['drawing_issues']))

    def test_hidden_red_circle_group_cannot_satisfy_disclosure(self):
        self.render()
        self.svg.write_text(self.svg.read_text().replace(
            '<g id="dangling">', '<g id="dangling" style="display:none">'))
        _, evidence = self.validate()
        self.assertTrue(any(q['kind'] == 'dangling_marker' for q in evidence['drawing_issues']))

    def test_broken_local_port_group_blocks_render_and_validation_with_same_contract(self):
        self.render()
        symbol = self.work / 'symbols/air-charging-valve.svg'
        tree = ET.parse(symbol)
        group = next(e for e in tree.getroot().iter() if e.get('id') == 'connection-points')
        tree.getroot().remove(group)
        tree.write(symbol, encoding='unicode')
        result = self.run_cli('render_l0_sheet.py')
        self.assertEqual(result.returncode, 1)
        before = json.loads((self.work / 'validation-report.json').read_text())['evidence'][0]
        _, after = self.validate()
        self.assertEqual(after['contract_issues'], before['contract_issues'])
        self.assertEqual(after['dangling'], OPEN_PORTS)
        self.assertEqual(after['drawing_status'], 'not_checked')
        self.assertTrue(any(q['kind'] == 'port_group' for q in after['contract_issues']))

    def test_standalone_cli_resolves_workdir_and_catalog_assets_from_elsewhere(self):
        # No copied scripts/catalog/symbols: canonical CLIs must resolve bundled assets.
        work = Path(self.temp.name) / 'standalone'
        work.mkdir()
        for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
            (work / name).write_bytes((FIXTURE / name).read_bytes())
        for name in ('render_l0_sheet.py', 'validate_sheet.py'):
            result = subprocess.run([sys.executable, str(SCRIPTS / name), str(work)],
                                    cwd=self.temp.name, capture_output=True, text=True, timeout=30)
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        report = json.loads((work / 'validation-report.json').read_text())
        evidence = next(e for e in report['evidence'] if e['id'] == 'V5')
        self.assertEqual(evidence['dangling'], OPEN_PORTS)
        self.assertEqual(evidence['contract_issues'], [])
        self.assertEqual(evidence['drawing_issues'], [])

    def test_full_driver_preserves_local_contract_failure_for_standalone_validation(self):
        symbol = self.work / 'symbols/air-charging-valve.svg'
        tree = ET.parse(symbol)
        group = next(e for e in tree.getroot().iter() if e.get('id') == 'connection-points')
        tree.getroot().remove(group)
        tree.write(symbol, encoding='unicode')
        work = Path(self.temp.name) / 'driver'
        result = subprocess.run([
            sys.executable, str(SCRIPTS / 'validate_driver.py'),
            '--intent', str(self.work / '1#系统.intent.yaml'),
            '--layout-seed', str(self.work / '1#系统.layout.json'),
            '--workdir', str(work), '--rounds', '1'],
            capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((work / 'validation-report.json').read_text())
        before = next(e for e in report['evidence'] if e['id'] == 'V5')
        self.assertTrue(any(q['kind'] == 'port_group' for q in before['contract_issues']))
        self.assertEqual(before['dangling'], OPEN_PORTS)
        self.assertFalse((work / 'sheet-readback.png').exists())
        result = subprocess.run([sys.executable, str(SCRIPTS / 'validate_sheet.py'), str(work)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        after = json.loads((work / 'validation-report.json').read_text())
        self.assertEqual(next(e for e in after['evidence'] if e['id'] == 'V5'), before)


if __name__ == '__main__':
    unittest.main()
