"""Validate observable, edited SVG geometry through the standalone CLI."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import make_render_workspace, SKILL


class PortGeometryCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='port-geometry-')
        self.addCleanup(self.tmp.cleanup)
        self.work = make_render_workspace(Path(self.tmp.name), SKILL / 'assets/fixtures/l0-small-seed')
        result = subprocess.run([sys.executable, str(self.work / 'render_l0_sheet.py')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.svg = self.work / '1#系统原理图.svg'

    def edit(self, change):
        root = ET.parse(self.svg).getroot()
        change(root)
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root, encoding='unicode'), encoding='utf-8')

    def validate(self):
        result = subprocess.run([sys.executable, str(self.work / 'validate_sheet.py')],
                                capture_output=True, text=True)
        report = json.loads((self.work / 'validation-report.json').read_text())
        self.assertEqual(result.returncode, 1 if report['fail_count'] else 0,
                         result.stdout + result.stderr)
        return report

    def render(self):
        result = subprocess.run([sys.executable, str(self.work / 'render_l0_sheet.py')],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_completed_port_check_explains_its_actual_coverage(self):
        report = self.validate()
        coverage = next(c for c in report['coverage'] if c['id'] == 'V3')
        self.assertEqual(coverage['status'], 'pass')
        self.assertEqual(coverage['detail'],
                         'Declared terminals checked against final SVG pipe endpoints')

    def test_visible_endpoint_gap_fails_with_port_and_input_location(self):
        def damage(root):
            line = next(e for e in root.iter() if e.get('class') == 'ln-pressure')
            points = line.get('points').split()
            points[0] = '622.0,530.0'  # EDP pressure_out is (620,530), before canvas shift.
            line.set('points', ' '.join(points))
        self.edit(damage)
        failures = [c for c in self.validate()['checks'] if c['id'] == 'V3']
        self.assertTrue(failures, 'A visible 2 px disconnection must fail V3')
        finding = next(c for c in failures if c.get('port') == 'pressure_out')
        self.assertEqual(finding['component'], 'EDP-001')
        self.assertEqual(finding['anchor'], 'paths[1][0->1]')
        self.assertEqual(finding['position'], [650.0, 530.0])
        self.assertAlmostEqual(finding['distance'], 2.0)

    def test_reverse_incidence_fails_even_when_endpoint_is_exact(self):
        def damage(root):
            line = next(e for e in root.iter() if e.get('class') == 'ln-pressure')
            points = line.get('points').split()
            line.set('points', ' '.join([points[0], '610.0,530.0', '610.0,470.0',
                                         '800.0,470.0', '800.0,530.0'] + points[-1:]))
        self.edit(damage)
        failures = [c for c in self.validate()['checks'] if c['id'] == 'V3']
        self.assertTrue(any(c.get('kind') == 'anchor_direction' and
                            c.get('component') == 'EDP-001' for c in failures))

    def test_boundary_coordinate_does_not_exempt_a_body_crossing(self):
        def damage(root):
            line = next(e for e in root.iter() if e.get('class') == 'ln-pressure')
            line.set('points', '620,530 620,510 820,510 920,510 920,480 '
                               '800,480 800,530 820,530')
        self.edit(damage)
        failures = [c for c in self.validate()['checks'] if c['id'] == 'V2']
        finding = next((c for c in failures if c.get('obstacle') == 'PF-001'), None)
        self.assertIsNotNone(finding, 'Segment beginning on a box boundary still crosses its body')
        self.assertEqual(finding['anchor'], 'paths[1][0->1]')
        self.assertEqual(finding['segment'], [[850.0, 510.0], [950.0, 510.0]])

    def test_six_pixel_foldback_has_v3_connection_location(self):
        def damage(root):
            line = next(e for e in root.iter() if e.get('class') == 'ln-pressure')
            points = line.get('points').split()
            line.set('points', ' '.join([points[0], '640,530', '634,530'] + points[1:]))
        self.edit(damage)
        failures = [c for c in self.validate()['checks'] if c['id'] == 'V3']
        finding = next((c for c in failures if c.get('kind') == 'foldback'), None)
        self.assertIsNotNone(finding)
        self.assertEqual(finding['anchor'], 'paths[1][0->1]')
        self.assertEqual(finding['position'], [670.0, 530.0])

    def test_connection_cannot_cross_an_unrelated_reservoir_body(self):
        def damage(root):
            line = next(e for e in root.iter() if e.get('class') == 'ln-pressure')
            line.set('points', '620,530 640,530 640,100 60,100 60,200 300,200 '
                               '300,100 800,100 800,530 820,530')
        self.edit(damage)
        failures = [c for c in self.validate()['checks'] if c['id'] == 'V2']
        finding = next(c for c in failures if c.get('obstacle') == 'TANK-001')
        self.assertEqual(finding['anchor'], 'paths[1][0->1]')
        self.assertEqual(finding['port'], 'pressure_out')
        self.assertGreater(finding['penetration'], 200)

    def test_scaled_nonzero_origin_symbol_in_all_four_rotations(self):
        symbol = self.work / 'symbols/filter-line-shutoff-stroke.svg'
        symbol.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 20 80 40">
          <g fill="none" stroke="black"><rect x="25" y="30" width="50" height="20"/>
          <line x1="10" y1="40" x2="25" y2="40"/>
          <line x1="75" y1="40" x2="90" y2="40"/></g>
          <g id="connection-points">
          <circle cx="10" cy="40" data-port-id="inlet" data-anchor-direction="left"
            data-medium="hydraulic" data-port-role="pressure"/>
          <circle cx="90" cy="40" data-port-id="outlet" data-anchor-direction="right"
            data-medium="hydraulic" data-port-role="pressure"/></g></svg>''')
        cases = [(0, [850, 530], [-1, 0], [850, 490, 1010, 570]),
                 (90, [890, 490], [0, -1], [850, 490, 930, 650]),
                 (180, [1010, 530], [1, 0], [850, 490, 1010, 570]),
                 (270, [890, 650], [0, 1], [850, 490, 930, 650])]
        layout_path = self.work / '1#系统.layout.json'
        layout = json.loads(layout_path.read_text())
        for rotation, position, direction, box in cases:
            with self.subTest(rotation=rotation):
                layout['nodes']['PF-001'].update(w=160, h=80, rot=rotation)
                layout_path.write_text(json.dumps(layout))
                self.render()
                report = self.validate()
                self.assertFalse([c for c in report['checks'] if c['id'] in ('V2', 'V3')])
                node = report['geometry']['nodes']['PF-001']
                self.assertEqual([round(v, 6) for v in node['footprint']], box)
                self.assertEqual([round(v, 6) for v in node['ports']['inlet']['position']], position)
                self.assertEqual([round(v, 6) for v in node['ports']['inlet']['direction']], direction)

    def test_actual_nested_svg_transform_is_used_for_ports_and_pipes(self):
        def move(root):
            sheet = next(e for e in root.iter() if e.get('id') == 'sheet')
            sheet.set('transform', 'translate(30,0) translate(5,-7) matrix(1 0 0 1 0 0)')
        self.edit(move)
        report = self.validate()
        self.assertFalse([c for c in report['checks'] if c['id'] == 'V3'])
        self.assertEqual(report['geometry']['nodes']['EDP-001']['ports']['pressure_out']['position'],
                         [655.0, 523.0])

    def test_mutating_only_the_visible_instance_cannot_reuse_layout_ports(self):
        def move(root):
            pump = next(e for e in root.iter() if e.get('id') == 'inst-EDP-001')
            pump.set('transform', 'translate(2,0) ' + pump.get('transform'))
        self.edit(move)
        failures = [c for c in self.validate()['checks'] if c['id'] == 'V3']
        self.assertTrue(any(c.get('kind') == 'endpoint_gap' and
                            c.get('position') == [652.0, 530.0] for c in failures))

    def test_current_firewall_valve_short_clearance_is_a_positive_endpoint_case(self):
        import shutil
        for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
            shutil.copy2(SKILL / 'assets/fixtures/l0-current' / name, self.work / name)
        self.render()
        report = self.validate()
        # This fixture retains unrelated gas tap defects; the reported FSOV/EDP
        # short-clearance connection must have both endpoints independently checked.
        evidence = next(e for e in report['evidence'] if e['id'] == 'V3')
        valve = next(t for t in evidence['terminals'] if t['component'] == 'FSOV-001'
                     and t['port'] == 'main_lower')
        self.assertLessEqual(valve['distance'], .1)
        self.assertTrue(any(t['component'] == 'EDP-001' and t['port'] == 'suction'
                            and t['anchor'] == valve['anchor'] for t in evidence['terminals']))
        self.assertFalse([c for c in report['checks'] if c['id'] == 'V3'
                          and c.get('anchor') == valve['anchor']])

    def test_unsupported_visible_geometry_is_explicitly_rejected(self):
        def damage(root):
            line = next(e for e in root.iter() if e.get('class') == 'ln-pressure')
            line.tag = '{http://www.w3.org/2000/svg}path'
            line.set('d', 'M620 530 Q700 420 820 530')
            del line.attrib['points']
        self.edit(damage)
        self.assertTrue(any(c.get('kind') == 'unsupported_geometry'
                            for c in self.validate()['checks']))


if __name__ == '__main__':
    unittest.main()
