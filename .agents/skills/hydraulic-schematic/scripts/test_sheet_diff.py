"""Version freezing and scoped comparison through real SVG/PNG/report CLIs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import SKILL, make_render_workspace


class SheetDiffCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='sheet-diff-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.work = make_render_workspace(self.base, SKILL / 'assets/fixtures/l0-small-seed')
        self.run_cli(self.work / 'render_l0_sheet.py')
        self.refresh()

    def run_cli(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, str(script), *map(str, args)],
                                cwd=self.work, capture_output=True, text=True, timeout=120)
        if expected is None:
            self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        else:
            self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def refresh(self, expected=0):
        self.run_cli(SKILL / 'scripts/rasterize_sheet.py', self.work / '1#系统原理图.svg',
                     '-o', self.work / 'sheet-readback.png', '--backend', 'chrome')
        self.run_cli(self.work / 'validate_sheet.py', expected=expected)

    def diff_cli(self, *args, expected=0):
        return self.run_cli(SKILL / 'scripts/sheet_diff.py', *args, expected=expected)

    def test_freeze_preserves_tool_and_symbol_versions_independent_of_live_workspace(self):
        frozen = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', frozen)
        manifest = json.loads((frozen / 'version.json').read_text())
        for logical in ('tool:validate_sheet.py', 'symbol:EDP-001'):
            record = manifest['files'][logical]
            self.assertTrue((frozen / record['path']).is_file())
        script = self.work / 'validate_sheet.py'
        script.write_text(script.read_text() + '\n# future tool version\n')
        symbol = self.work / 'symbols/edp-provisional-stroke.svg'
        symbol.write_text(symbol.read_text() + '\n<!-- future symbol version -->\n')
        verified = json.loads(self.diff_cli('verify', frozen).stdout)
        self.assertEqual(verified['status'], 'current')
        self.assertEqual(verified['png']['status'], 'pass')
        self.diff_cli('freeze', self.work, '--output', self.base / 'stale', expected=2)
        copied = frozen / manifest['files']['symbol:EDP-001']['path']
        copied.write_text(copied.read_text() + '\n<!-- altered frozen symbol -->\n')
        self.diff_cli('verify', frozen, expected=2)

    def test_local_lead_repair_reports_unchanged_topology_and_local_pixels(self):
        svg = self.work / '1#系统原理图.svg'
        correct = svg.read_text()
        root = ET.fromstring(correct)
        node = next(e for e in root.iter() if e.get('id') == 'inst-PF-001')
        lead = next(e for e in node.iter() if e.get('data-interface-port') == 'inlet')
        lead.set('style', 'stroke-width:1.8px')
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        svg.write_text(ET.tostring(root, encoding='unicode'))
        self.refresh(expected=1)
        before = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', before)
        svg.write_text(correct)
        self.refresh()
        scope = self.base / 'scope.json'
        scope.write_text(json.dumps({'nodes': ['PF-001'], 'edges': [],
                                     'include_adjacent_edges': True,
                                     'note': 'Repair the pressure inlet lead width.'}))
        output = self.base / 'comparison'
        self.diff_cli('compare', before, self.work, '--scope', scope, '--output', output)
        report = json.loads((output / 'change-report.json').read_text())
        self.assertEqual(report['status'], 'pass')
        self.assertTrue(report['topology']['unchanged'])
        self.assertEqual(report['objects']['changed_nodes'], ['PF-001'])
        self.assertGreater(report['pixels']['changed'], 0)
        self.assertEqual(report['pixels']['unexpected'], 0)
        self.assertFalse(report['delivery_certified'])
        self.assertTrue((output / 'diff-overlay.png').is_file())

    def test_port_swap_inside_target_and_adjacent_edge_scope_is_unexpected_topology(self):
        before = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', before)
        svg = self.work / '1#系统原理图.svg'
        root = ET.parse(svg).getroot()
        line = next(e for e in root.iter() if e.get('data-edge') == 'paths[1][0->1]')
        line.set('points', '620,530 640,530 640,470 920,470 920,530 900,530')
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        svg.write_text(ET.tostring(root, encoding='unicode'))
        self.refresh(expected=1)
        scope = self.base / 'scope.json'
        scope.write_text(json.dumps({'nodes': ['PF-001'], 'edges': ['paths[1][0->1]'],
                                     'include_adjacent_edges': True,
                                     'note': 'Adjust the target filter and its attached pipe.'}))
        output = self.base / 'comparison'
        self.diff_cli('compare', before, self.work, '--scope', scope, '--output', output, expected=1)
        report = json.loads((output / 'change-report.json').read_text())
        self.assertFalse(report['topology']['unchanged'])
        self.assertTrue(any(f['kind'] == 'unexpected_topology' for f in report['findings']))

    def test_unrelated_object_change_is_reported_outside_the_declared_node(self):
        before = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', before)
        svg = self.work / '1#系统原理图.svg'
        root = ET.parse(svg).getroot()
        node = next(e for e in root.iter() if e.get('id') == 'inst-EDP-001')
        circle = next(e for e in node.iter() if e.tag.endswith('circle'))
        circle.set('style', 'stroke:blue')
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        svg.write_text(ET.tostring(root, encoding='unicode'))
        self.refresh()
        scope = self.base / 'scope.json'
        scope.write_text(json.dumps({'nodes': ['PF-001'], 'note': 'Repair only the filter lead.'}))
        output = self.base / 'comparison'
        self.diff_cli('compare', before, self.work, '--scope', scope, '--output', output, expected=1)
        report = json.loads((output / 'change-report.json').read_text())
        self.assertIn('EDP-001', report['objects']['changed_nodes'])
        self.assertIn('node:EDP-001', report['objects']['unexpected'])
        self.assertGreater(report['pixels']['unexpected'], 0)

    def test_canvas_mismatch_writes_an_explicit_not_comparable_report(self):
        before = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', before)
        svg = self.work / '1#系统原理图.svg'
        root = ET.parse(svg).getroot()
        root.set('viewBox', '0 0 1700 1390')
        root.set('width', '1700')
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        svg.write_text(ET.tostring(root, encoding='unicode'))
        self.refresh()
        scope = self.base / 'scope.json'
        scope.write_text(json.dumps({'global': True, 'note': 'Explicit canvas enlargement.'}))
        output = self.base / 'comparison'
        self.diff_cli('compare', before, self.work, '--scope', scope, '--output', output, expected=2)
        report = json.loads((output / 'change-report.json').read_text())
        self.assertEqual(report['status'], 'not_comparable')
        self.assertIsNone(report['pixels'])
        self.assertIn('align', report['reason'])

    def test_explicit_topology_transition_is_checked_against_both_input_and_actual_edges(self):
        before = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', before)
        from ruamel.yaml import YAML
        yaml = YAML()
        path = self.work / '1#系统.intent.yaml'
        intent = yaml.load(path)
        intent['paths'][1][1] = 'PF-001.outlet'
        yaml.dump(intent, path)
        self.run_cli(self.work / 'render_l0_sheet.py')
        self.refresh(expected=None)
        scope = self.base / 'scope.json'
        scope.write_text(json.dumps({'global': True, 'edges': ['paths[1][0->1]'],
            'note': 'Deliberately rewire the pressure branch; review all resulting drawing changes.',
            'topology_changes': {'paths[1][0->1]': {
                'before': ['EDP-001.pressure_out', 'PF-001.inlet'],
                'after': ['EDP-001.pressure_out', 'PF-001.outlet']}}}))
        output = self.base / 'comparison'
        self.diff_cli('compare', before, self.work, '--scope', scope, '--output', output)
        report = json.loads((output / 'change-report.json').read_text())
        self.assertFalse(report['topology']['unchanged'])
        self.assertEqual(report['topology']['authorized_changes'], ['paths[1][0->1]'])
        self.assertEqual(report['topology']['unexpected_changes'], [])
        self.assertEqual(report['timing']['derived_rasterizations'], 0)

    def test_global_font_change_is_explicit_and_needs_no_scope_rasterizations(self):
        before = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', before)
        svg = self.work / '1#系统原理图.svg'
        svg.write_text(svg.read_text().replace('</style>',
                       'text {font-family:monospace!important;font-size:12px!important;}</style>'))
        self.refresh(expected=None)
        scope = self.base / 'scope.json'
        scope.write_text(json.dumps({'global': True, 'note': 'Review the deliberate whole-sheet font replacement.'}))
        output = self.base / 'comparison'
        self.diff_cli('compare', before, self.work, '--scope', scope, '--output', output)
        report = json.loads((output / 'change-report.json').read_text())
        self.assertTrue(report['scope']['global'])
        self.assertTrue(report['topology']['unchanged'])
        self.assertGreater(report['pixels']['changed'], 0)
        self.assertEqual(report['timing']['derived_rasterizations'], 0)

    def test_driver_compares_after_full_validation_and_preserves_pending_delivery(self):
        before = self.base / 'before'
        self.diff_cli('freeze', self.work, '--output', before)
        scope = self.base / 'scope.json'
        scope.write_text(json.dumps({'nodes': ['PF-001'], 'note': 'Verify an unchanged full rerender.'}))
        output = self.base / 'driver'
        comparison = self.base / 'comparison'
        self.run_cli(SKILL / 'scripts/validate_driver.py', '--intent', self.work / '1#系统.intent.yaml',
                     '--layout-seed', self.work / '1#系统.layout.json', '--workdir', output,
                     '--rounds', '1', '--compare-against', before, '--change-scope', scope,
                     '--comparison-output', comparison, expected=4)
        report = json.loads((output / 'convergence-report.json').read_text())
        self.assertEqual(report['change_comparison']['status'], 'pass')
        self.assertTrue(report['rounds'][0]['coverage'])
        self.assertFalse(report['delivery']['ready'])
        self.assertEqual(report['perceptual_review'], 'pending')
        self.assertFalse(json.loads((comparison / 'change-report.json').read_text())['delivery_certified'])


if __name__ == '__main__':
    unittest.main()
