# -*- coding: utf-8 -*-
import importlib.util
import os
import re
import unittest
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location('sheet_render', os.path.join(HERE, 'render.py'))
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class SuctionMarkerTest(unittest.TestCase):
    def test_suction_geometry_is_derived_from_S(self):
        g = r.suction_marker_geometry(8.0)
        self.assertEqual(g['count'], 5)
        self.assertAlmostEqual(g['slash_height'], 16.0)
        self.assertAlmostEqual(g['slash_angle_deg'], 60.0)
        self.assertAlmostEqual(g['intra_spacing'], 10.0)
        self.assertAlmostEqual(g['group_pitch'], 100.0)
        self.assertAlmostEqual(g['end_clearance'], 32.0)

    def test_S_scales_every_dimension(self):
        a = r.suction_marker_geometry(8.0)
        b = r.suction_marker_geometry(12.0)
        for key in ('slash_height', 'intra_spacing', 'group_pitch', 'end_clearance'):
            self.assertAlmostEqual(b[key] / a[key], 1.5)
        self.assertEqual(a['slash_angle_deg'], b['slash_angle_deg'])
        self.assertEqual(a['count'], b['count'])

    def test_S_changes_rendered_slash_height(self):
        a = r.suction_markers([(0, 50), (400, 50)], blocked=[], S=8.0)
        b = r.suction_markers([(0, 50), (600, 50)], blocked=[], S=12.0)
        ah = abs(a[0][1][1] - a[0][0][1])
        bh = abs(b[0][1][1] - b[0][0][1])
        self.assertAlmostEqual(bh / ah, 1.5)

    def test_suction_path_kind_propagates_through_inline_component(self):
        self.assertEqual(
            r.path_line_type(['TANK-001.suction_out', 'FSOV-001',
                              'EDP-001.suction']),
            'suction')
        self.assertIsNone(
            r.path_line_type(['EDP-001.pressure_out', '@PRESS']))

    def test_inline_component_does_not_reset_terminal_clearance(self):
        path = [(0, 50), (90, 50)]
        terminal = r.suction_markers(path, blocked=[], S=8.0)
        through_fsov = r.suction_markers(
            path, blocked=[], S=8.0,
            start_terminal=False, end_terminal=True)
        self.assertEqual(terminal, [])
        self.assertEqual(len(through_fsov), 5)

    def test_fsov_to_edp_segment_is_marked_as_suction(self):
        r.main()
        path = os.path.join(HERE, '1#系统原理图.svg')
        with open(path, encoding='utf-8') as f:
            raw = f.read()
        root = ET.fromstring(raw.encode('utf-8'))
        ns = '{http://www.w3.org/2000/svg}'
        suction_paths = [e.get('points') for e in root.iter(ns + 'polyline')
                         if e.get('class') == 'ln-suction']
        self.assertTrue(any(p.startswith('410.0,290.0') and p.endswith('500.0,290.0')
                            for p in suction_paths))
        groups = [g for g in root.iter(ns + 'g')
                  if g.get('class') == 'suc-mark-group']
        on_fsov_edp = []
        for g in groups:
            lines = list(g)
            cx = sum((float(e.get('x1')) + float(e.get('x2'))) / 2.0
                     for e in lines) / len(lines)
            cy = sum((float(e.get('y1')) + float(e.get('y2'))) / 2.0
                     for e in lines) / len(lines)
            if 410 < cx < 500 and abs(cy - 290) < 0.5:
                on_fsov_edp.append(g)
        self.assertEqual(len(on_fsov_edp), 1)
        self.assertEqual(len(list(on_fsov_edp[0])), 5)

    def test_end_clearance_is_measured_to_group_outer_edge(self):
        marks = r.suction_markers([(0, 50), (200, 50)], blocked=[], S=8.0)
        xs = [x for a, b in marks for x in (a[0], b[0])]
        self.assertGreaterEqual(min(xs), 32.0)
        self.assertLessEqual(max(xs), 168.0)

    def test_horizontal_line_gets_groups_of_five_slashes(self):
        marks = r.suction_markers([(0, 50), (400, 50)], blocked=[])
        self.assertGreaterEqual(len(marks), 10)
        self.assertEqual(len(marks) % 5, 0)
        for a, b in marks:
            self.assertLess(a[0], b[0])
            self.assertGreater(a[1], b[1])
            self.assertLessEqual(abs(a[1] - b[1]), 20)

    def test_vertical_line_rotates_the_same_marker(self):
        marks = r.suction_markers([(50, 0), (50, 400)], blocked=[])
        self.assertGreaterEqual(len(marks), 10)
        self.assertEqual(len(marks) % 5, 0)
        for a, b in marks:
            self.assertLess(a[0], b[0])
            self.assertLess(a[1], b[1])

    def test_marker_group_is_rejected_when_it_hits_obstacle(self):
        clear = r.suction_markers([(0, 50), (200, 50)], blocked=[])
        blocked = r.suction_markers([(0, 50), (200, 50)], blocked=[(55, 30, 105, 70)])
        self.assertGreater(len(clear), len(blocked))
        for a, b in blocked:
            self.assertFalse(55 <= min(a[0], b[0]) and max(a[0], b[0]) <= 105)

    def test_short_port_stub_has_no_marker(self):
        self.assertEqual(r.suction_markers([(0, 0), (35, 0)], blocked=[]), [])

    def test_collinear_router_fragments_are_one_visual_run(self):
        whole = r.suction_markers([(0, 50), (140, 50)], blocked=[], S=8.0)
        split = r.suction_markers([(0, 50), (20, 50), (120, 50), (140, 50)],
                                   blocked=[], S=8.0)
        self.assertEqual(split, whole)
        self.assertEqual(len(split), 5)

    def test_v17_reports_declared_S(self):
        import json
        import subprocess
        r.main()
        subprocess.run(['python3', os.path.join(HERE, 'validate_sheet.py')],
                       cwd=HERE, check=False, capture_output=True, text=True)
        with open(os.path.join(HERE, 'validation-report.json'), encoding='utf-8') as f:
            report = json.load(f)
        v17 = next(e for e in report['evidence'] if e['id'] == 'V17')
        self.assertEqual(v17['S'], 8.0)
        self.assertEqual(v17['slash_height'], 16.0)
        self.assertEqual(v17['slash_angle_deg'], 60.0)
        self.assertEqual(v17['intra_spacing'], 10.0)
        self.assertEqual(v17['group_pitch'], 100.0)
        self.assertEqual(v17['end_clearance'], 32.0)

    def test_sheet_has_no_renderer_pipeline_arrows(self):
        r.main()
        path = os.path.join(HERE, '1#系统原理图.svg')
        with open(path, encoding='utf-8') as f:
            raw = f.read()
        root = ET.fromstring(raw.encode('utf-8'))
        ns = '{http://www.w3.org/2000/svg}'
        self.assertFalse(any(e.get('class') == 'arw' for e in root.iter()))
        self.assertFalse(any(e.get('id') == 'arrows' for e in root.iter(ns + 'g')))
        self.assertIn('EDP-001__symbol', raw)
        self.assertIn('EMP-001__symbol', raw)
        # 只删 renderer-owned 管线箭头；受控符号内部的方向特征必须保留。
        self.assertIn('TANK-001__motion-arrow-up', raw)
        self.assertIn('TANK-001__motion-arrow-down', raw)
        self.assertIn('M62 40 L48 32 L48 48 Z', raw)  # 泵内部排油三角形

    def test_rendered_sheet_has_solid_baseline_and_grouped_slashes(self):
        r.main()
        path = os.path.join(HERE, '1#系统原理图.svg')
        with open(path, encoding='utf-8') as f:
            raw = f.read()
        style = re.search(r'<style>(.*?)</style>', raw, re.S).group(1)
        suction_rule = re.search(r'\.ln-suction\s*\{([^}]*)\}', style).group(1)
        self.assertNotIn('stroke-dasharray', suction_rule)
        root = ET.fromstring(raw.encode('utf-8'))
        ns = '{http://www.w3.org/2000/svg}'
        marks = [e for e in root.iter(ns + 'line')
                 if 'suc-mark' in (e.get('class') or '')]
        self.assertGreaterEqual(len(marks), 10)
        self.assertEqual(len(marks) % 5, 0)
        groups = [e for e in root.iter(ns + 'g')
                  if 'suc-mark-group' in (e.get('class') or '')]
        self.assertGreaterEqual(len(groups), 2)
        for group in groups:
            self.assertEqual(len(list(group)), 5)

        legend = next(e for e in root.iter(ns + 'g') if e.get('id') == 'legend')
        sample_base = [e for e in legend.iter(ns + 'line')
                       if e.get('class') == 'suc-sample-base']
        sample_marks = [e for e in legend.iter(ns + 'line')
                        if e.get('class') == 'suc-sample-mark']
        self.assertEqual(len(sample_base), 1)
        self.assertEqual(len(sample_marks), 5)

        def bbox_line(e):
            xs = [float(e.get('x1')), float(e.get('x2'))]
            ys = [float(e.get('y1')), float(e.get('y2'))]
            return min(xs), min(ys), max(xs), max(ys)

        def overlap(a, b, pad=0):
            return not (a[2] + pad < b[0] or a[0] - pad > b[2]
                        or a[3] + pad < b[1] or a[1] - pad > b[3])

        # 吸油标记不得压住同一路径上的流向箭头。
        arrow_boxes = []
        for e in root.iter(ns + 'path'):
            if e.get('class') != 'arw':
                continue
            nums = [float(v) for v in re.findall(r'[-\d.]+', e.get('d') or '')]
            arrow_boxes.append((min(nums[0::2]), min(nums[1::2]),
                                max(nums[0::2]), max(nums[1::2])))
        for mark in marks:
            self.assertFalse(any(overlap(bbox_line(mark), b, pad=2)
                                 for b in arrow_boxes))

        # 吸油标记不得穿过装配分组虚线边界。
        group_edges = []
        for e in root.iter(ns + 'rect'):
            if e.get('class') != 'grp':
                continue
            x, y = float(e.get('x')), float(e.get('y'))
            w, h = float(e.get('width')), float(e.get('height'))
            group_edges += [(x - 3, y - 3, x + w + 3, y + 3),
                            (x - 3, y + h - 3, x + w + 3, y + h + 3),
                            (x - 3, y - 3, x + 3, y + h + 3),
                            (x + w - 3, y - 3, x + w + 3, y + h + 3)]
        for mark in marks:
            self.assertFalse(any(overlap(bbox_line(mark), b)
                                 for b in group_edges))


if __name__ == '__main__':
    unittest.main()
