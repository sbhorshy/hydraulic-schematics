"""Rotation changes routing, never the declared hydraulic connection."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_entrypoints import make_render_workspace, SKILL


class RotationRoutes(unittest.TestCase):
    def test_rf_zero_rotation_avoids_its_body(self):
        self.check_rotation('RF-001', 0)

    def test_rf_270_does_not_move_its_collision_into_the_neighbor(self):
        self.check_rotation('RF-001', 270)

    def test_other_rf_and_cv_orientations(self):
        for component, angles in (('RF-001', (90, 180)), ('CV-002', (0, 90, 180, 270))):
            for angle in angles:
                with self.subTest(component=component, angle=angle):
                    self.check_rotation(component, angle)

    def test_rotation_positive_has_zero_failures_and_all_budgets(self):
        with tempfile.TemporaryDirectory(prefix='rotation-positive-') as directory:
            work = make_render_workspace(Path(directory), SKILL / 'assets/fixtures/l0-rotation')
            commands = [
                ['render_l0_sheet.py', str(work)],
                ['rasterize_sheet.py', str(work / '1#系统原理图.svg'), '-o', str(work / 'sheet-readback.png')],
                ['validate_sheet.py', str(work)],
            ]
            for script, *args in commands:
                result = subprocess.run([sys.executable, str(SKILL / 'scripts' / script), *args], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads((work / 'validation-report.json').read_text())
            self.assertEqual(report['fail_count'], 0)
            self.assertTrue(all(b['status']=='pass' for b in report['composition_budget']['items']), report['composition_budget'])
            self.assertFalse(report['delivery']['ready'])  # no human signoff invented

    def check_rotation(self, component, angle):
        with tempfile.TemporaryDirectory(prefix='rotation-route-') as directory:
            work = make_render_workspace(Path(directory), SKILL / 'assets/fixtures/l0-current')
            layout_path = work / '1#系统.layout.json'
            layout = json.loads(layout_path.read_text())
            layout['nodes'][component]['rot'] = angle
            layout_path.write_text(json.dumps(layout))
            original_layout = layout_path.read_bytes()
            original_intent = (work / '1#系统.intent.yaml').read_bytes()
            result = subprocess.run([sys.executable, str(SKILL / 'scripts/render_l0_sheet.py'), str(work)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            subprocess.run([sys.executable, str(SKILL / 'scripts/validate_sheet.py'), str(work)], capture_output=True, text=True, check=False)
            report = json.loads((work / 'validation-report.json').read_text())
            failures = [c for c in report['checks'] if c['result'] == 'fail' and c['id'] in ('V2', 'V3', 'V13') and (c.get('component') == component or c.get('obstacle') == component or component in c['detail'] or ('自身折返' in c['detail'] and 'ln-return' in c['detail']))]
            self.assertEqual(failures, [])
            # Compare structured input provenance across the whole sheet: a new
            # neighboring-body collision or a later broken branch is not legacy.
            baseline = json.loads((SKILL / 'assets/fixtures/l0-current/rotation-baseline-failures.json').read_text())['checks']
            def signature(c):
                keys = ('id', 'kind', 'component', 'port', 'anchor', 'input_anchors',
                        'obstacle', 'expected_endpoints', 'actual_endpoints', 'networks')
                fields = {k:c[k] for k in keys if k in c}
                if not c.get('kind'):
                    fields['detail'] = c['detail']
                return json.dumps(fields, sort_keys=True)
            added = Counter(signature(c) for c in report['checks'] if c['result']=='fail') - Counter(map(signature, baseline))
            self.assertEqual(added, Counter(), [c for c in report['checks'] if signature(c) in added])
            self.assertEqual(next(b for b in report['composition_budget']['items'] if b['id']=='B4')['status'], 'pass')
            names = layout['labels'][component].split('\n')
            self.assertEqual([c for c in report['checks'] if c.get('text') in names and c.get('obstacle_kind')=='pipe'], [])
            if component == 'RF-001' and angle == 270:
                labels = [e for e in ET.parse(work / '1#系统原理图.svg').iter() if e.get('data-label-for') == component]
                self.assertTrue(all(float(e.get('y')) > 1112 for e in labels))  # still below the rotated RF

            if component == 'RF-001' and angle == 180:
                expected = json.loads((SKILL / 'assets/fixtures/l0-current/rotation-default-routes.json').read_text())
                actual = {}
                for element in ET.parse(work / '1#系统原理图.svg').iter():
                    if element.get('data-edge') and element.get('points'):
                        actual.setdefault(element.get('data-edge'), []).append(element.get('points'))
                self.assertEqual(actual, expected)
            self.assertEqual(layout_path.read_bytes(), original_layout)
            self.assertEqual((work / '1#系统.intent.yaml').read_bytes(), original_intent)


if __name__ == '__main__':
    unittest.main()
