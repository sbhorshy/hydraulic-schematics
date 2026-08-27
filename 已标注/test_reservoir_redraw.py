#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试重画油箱符号符合 stroke_geometry 标准。"""
import unittest
import xml.etree.ElementTree as ET

class ReservoirRedrawTest(unittest.TestCase):
    def setUp(self):
        self.path = '/mnt/d/File/COMAC/组件库/已标注/reservoir-bootstrap-redraw.svg'
        self.tree = ET.parse(self.path)
        self.root = self.tree.getroot()
        self.NS = '{http://www.w3.org/2000/svg}'

    def test_data_symbol_form_is_stroke_geometry(self):
        """规范 6.3.2 第一条：几何必须是描边，不得是填充轮廓。"""
        form = self.root.get('data-symbol-form')
        self.assertEqual(form, 'stroke_geometry',
                         'C8 门禁要求 stroke_geometry')

    def test_viewBox_width_height_consistent(self):
        """规范 6.3.2 第二条：width/height 数值与 viewBox 后两位一致。"""
        vb = self.root.get('viewBox').split()
        w = self.root.get('width')
        h = self.root.get('height')
        self.assertEqual(vb[2], w, 'viewBox[2] 必须等于 width')
        self.assertEqual(vb[3], h, 'viewBox[3] 必须等于 height')
        self.assertNotIn('pt', w, '禁止 pt 单位')
        self.assertNotIn('px', w, '禁止 px 后缀')

    def test_no_absolute_stroke_width_in_symbol_group(self):
        """规范：禁止写死绝对线宽，由整图 .sym-outline 统一施加 1.5T。"""
        for g in self.root.findall(self.NS+'g'):
            if g.get('id') == 'symbol':
                for e in g.iter():
                    sw = e.get('stroke-width')
                    self.assertIsNone(sw, f'{e.tag} {e.get("id")} 不得有 stroke-width')

    def test_ports_on_viewBox_boundary(self):
        """规范 6.3.2 第三条：端口坐标必须落在 viewBox 边界上。"""
        vb = self.root.get('viewBox').split()
        vb = [float(x) for x in vb]
        vb_xmin, vb_ymin, vb_w, vb_h = vb
        vb_xmax = vb_xmin + vb_w
        vb_ymax = vb_ymin + vb_h
        for g in self.root.findall(self.NS+'g'):
            if g.get('id') == 'connection-points':
                for c in g.findall(self.NS+'circle'):
                    cx, cy = float(c.get('cx')), float(c.get('cy'))
                    on_boundary = (abs(cx - vb_xmin) < 1 or abs(cx - vb_xmax) < 1 or
                                   abs(cy - vb_ymin) < 1 or abs(cy - vb_ymax) < 1)
                    self.assertTrue(on_boundary,
                                    f'{c.get("id")} ({cx},{cy}) 不在 viewBox 边界')

    def test_symbol_internal_arrows_preserved(self):
        """规范 10.6.2：禁止渲染器添加管线方向箭头，
        但符号内部受控方向特征（泵、油箱运动箭头）必须保留。"""
        ids = {e.get('id') for e in self.tree.iter() if e.get('id')}
        self.assertIn('motion-arrow-up', ids, '油箱上行运动箭头必须保留')
        self.assertIn('motion-arrow-down', ids, '油箱下行运动箭头必须保留')

    def test_no_fill_traced_outlines(self):
        """规范 6.3.2 第一条和 6.4 第 8 条：symbol 组内无 fill 非 none 的轮廓。"""
        for g in self.root.findall(self.NS+'g'):
            if g.get('id') == 'symbol':
                for e in g.iter():
                    tag = e.tag.split('}')[-1]
                    if tag in ('path', 'polyline', 'polygon', 'rect', 'circle', 'line'):
                        fill = e.get('fill')
                        # 允许显式 stroke="none" 的实心箭头，但必须 fill 明确非黑
                        if fill and fill not in ('none', '#ffffff', 'white'):
                            stroke = e.get('stroke')
                            if stroke != 'none':  # 正常描边几何不应有非白非无 fill
                                self.assertIn(fill, ('none',),
                                              f'{e.get("id")} 有非 none fill {fill}')

if __name__ == '__main__':
    unittest.main()

