# -*- coding: utf-8 -*-
"""#63 步骤二:镜像接入渲染/几何/校核的便携回归。

事实来源 = skill 单源库两泵符号的实读 SVG 与字节摘要;测试内的许可登记
一律在**临时 catalog / 条目副本**上按当前资产/端口契约构造,或显式剥离
许可字段构造未登记负例——本文件不写生产文件。生产 catalog 已按 #63
登记两泵(axes x/y),其现状断言在 tests/repository/test_mirror_registration.py
(仓库级,不在 skill 便携自检内)。
几何期望在本文件内独立推导(符号 connection-points 实读 + 字面量镜像/
旋转表),不复用 renderer 内部状态;CLI 用例走真实 render_l0_sheet.py /
validate_sheet.py 子进程,正例不靠未接线图冒充通过。
"""
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

from test_entrypoints import make_render_workspace, SKILL

LIB = SKILL / 'assets' / 'component-library'
PROD_CATALOG = json.loads((LIB / 'component-catalog.json').read_text(encoding='utf-8'))
SMALL = SKILL / 'assets' / 'fixtures' / 'l0-small-seed'
PUMPS = ('engine_driven_pump', 'electric_motor_driven_pump')

# 登记口径键清单(#63 固定,测试内独立字面量,勿从被测模块取;端口类别
# 是目录真实字段 ports[].kind,枚举名才是 port_kind)
PORT_FIELDS = ('id', 'svg_element_id', 'medium', 'role',
               'flow_capability', 'anchor_direction', 'kind')

# place() 既有 90/180/270° 锚向表,字面量拷贝只组合不重算;镜像锚向表按
# #63 契约(先镜像再旋转)同样以字面量给出。
MIRROR_ANCHOR = {'x': {'left': 'right', 'right': 'left'},
                 'y': {'up': 'down', 'down': 'up'}}
ROT_ANCHOR = {90: {'left': 'up', 'up': 'right', 'right': 'down', 'down': 'left'},
              180: {'left': 'right', 'right': 'left', 'up': 'down', 'down': 'up'},
              270: {'left': 'down', 'down': 'right', 'right': 'up', 'up': 'left'}}

MINI_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="20 10 80 40" data-component-type="mini_mirror_pump">
  <g id="symbol"><path id="mini-body" d="M30 20 H90 V40 H30 Z"/></g>
  <g id="connection-points">
    <circle id="port-in" data-port-id="inlet" cx="20" cy="30" r="2"
            data-anchor-direction="left" data-port-role="pressure" data-medium="hydraulic"/>
    <circle id="port-out" data-port-id="outlet" cx="100" cy="30" r="2"
            data-anchor-direction="right" data-port-role="pressure" data-medium="hydraulic"/>
    <circle id="port-top" data-port-id="vent" cx="60" cy="10" r="2"
            data-anchor-direction="up" data-port-role="measurement" data-medium="pneumatic"/>
  </g>
</svg>
'''

# 审核反例口径:小 k(96/96000 = 0.001)大 viewBox。姿态对账必须按变换后的
# 控制点在真实 SVG 单位下判尺度——系数绝对 epsilon 会把 -0.001 与 -0.002
# 都收进 0.01 而放过成倍缩放。
BIG_VIEWBOX_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-48000 0 96000 142000" data-component-type="big_viewbox_pump">
  <g id="symbol"><path id="big-body" d="M-48000 0 H48000 V142000 H-48000 Z"/></g>
  <g id="connection-points">
    <circle id="port-a" data-port-id="inlet" cx="-48000" cy="71000" r="200"
            data-anchor-direction="left" data-port-role="pressure" data-medium="hydraulic"/>
    <circle id="port-b" data-port-id="outlet" cx="48000" cy="71000" r="200"
            data-anchor-direction="right" data-port-role="pressure" data-medium="hydraulic"/>
  </g>
</svg>
'''

# k = 80/240 = 1/3,渲染器以 %g 六位有效数字输出 scale(0.333333):
# 姿态对账须保留 %g 舍入余量,正常舍入不得误拒。
THIRD_SCALE_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 240" data-component-type="third_scale_pump">
  <g id="symbol"><path id="third-body" d="M0 0 H240 V240 H0 Z"/></g>
  <g id="connection-points">
    <circle id="port-a" data-port-id="inlet" cx="0" cy="120" r="4"
            data-anchor-direction="left" data-port-role="pressure" data-medium="hydraulic"/>
    <circle id="port-b" data-port-id="outlet" cx="240" cy="120" r="4"
            data-anchor-direction="right" data-port-role="pressure" data-medium="hydraulic"/>
  </g>
</svg>
'''

# 审核反例口径(2026-10-12 第二轮):巨大且可抵消的 viewBox 原点。源坐标
# 1e9 经 mirror/scale 后落回图纸普通坐标,|a*x| 与 |e| 各自 ~1e9 但互相抵消;
# 旧预算把这两个大数的绝对值和当容差基数,错位 100px 时容差已 ~2e5,
# 整符号平移仍被接受。预算必须跟随变换后点自身的图上幅度。
HUGE_ORIGIN_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="1000000000 0 80 80" data-component-type="huge_origin_pump">
  <g id="symbol"><path id="huge-body" d="M1000000000 0 H1000000090 V80 H1000000000 Z"/></g>
  <g id="connection-points">
    <circle id="port-a" data-port-id="inlet" cx="1000000000" cy="40" r="2"
            data-anchor-direction="left" data-port-role="pressure" data-medium="hydraulic"/>
    <circle id="port-b" data-port-id="outlet" cx="1000000080" cy="40" r="2"
            data-anchor-direction="right" data-port-role="pressure" data-medium="hydraulic"/>
  </g>
</svg>
'''


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _ports_digest(component_type, ports):
    trimmed = [{key: port[key] for key in PORT_FIELDS if key in port}
               for port in ports]
    trimmed.sort(key=lambda port: port['id'])
    payload = {'component_type': component_type, 'ports': trimmed}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _entry(component_type):
    return copy.deepcopy(next(c for c in PROD_CATALOG['components']
                              if c['component_type'] == component_type))


def _enabled(component_type, axes=('x', 'y')):
    """目录条目副本 + 按当前资产/端口契约构造的许可登记(生产条目不动)。"""
    entry = _entry(component_type)
    entry['mirror_safe'] = True
    entry['layout'] = dict(entry.get('layout') or {}, allow_mirror=True)
    entry['mirror_registration'] = {
        'axes': list(axes),
        'asset_sha256': _sha256(LIB / entry['symbol']['asset']),
        'ports_sha256': _ports_digest(component_type, entry['ports']),
    }
    return entry


def _unregistered(entry):
    """条目副本显式剥离全部许可字段 = 显式未登记(负例专用,不依赖也不
    改动生产登记现状:"未登记=拒绝"在登记上线后仍是独立事实)。"""
    entry = copy.deepcopy(entry)
    entry.pop('mirror_safe', None)
    entry.pop('mirror_registration', None)
    layout = entry.get('layout')
    if isinstance(layout, dict):
        layout.pop('allow_mirror', None)
    return entry


def read_ports(svg_path):
    """实读符号 viewBox 与 connection-points,独立于渲染器实现。"""
    root = ET.parse(svg_path).getroot()
    vb = [float(v) for v in root.get('viewBox').replace(',', ' ').split()]
    ports = {}
    for group in root.iter():
        if group.get('id') != 'connection-points':
            continue
        for circle in group:
            ports[circle.get('data-port-id')] = (
                float(circle.get('cx')), float(circle.get('cy')),
                circle.get('data-anchor-direction'))
    return (vb[0], vb[1], vb[2], vb[3]), ports


class MirrorPlacementTest(unittest.TestCase):
    """Sheet.place/symbols:两泵真实符号的镜像端口/锚向/变换串。"""

    def setUp(self):
        import render_l0_sheet as renderer
        self.renderer = renderer
        self.tmp = tempfile.TemporaryDirectory(prefix='mirror-render-')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        (self.work / 'symbols').mkdir()
        for ctype in PUMPS:
            entry = _entry(ctype)
            shutil.copy2(LIB / entry['symbol']['asset'],
                         self.work / 'symbols' / Path(entry['symbol']['asset']).name)

    def build(self, specs):
        """specs: [(inst, component_dict, node_extra)] -> 已构造未 place 的 Sheet。"""
        nodes, parts, components = {}, {}, []
        for inst, component, extra in specs:
            node = {'x': 100.0, 'y': 200.0, 'w': 80.0, 'h': 80.0,
                    'symbol': 'symbols/' + Path(component['symbol']['asset']).name}
            node.update(extra)
            nodes[inst] = node
            parts[inst] = component['component_type']
            components.append(component)
        layout = {'canvas': {'width': 2000, 'height': 2000}, 'nodes': nodes,
                  'externs': {}, 'buses': {}}
        intent = {'parts': parts, 'paths': [], 'extern': {}, 'unknown': []}
        return self.renderer.Sheet(intent, layout, {'components': components},
                                   cat_dir=str(LIB), workdir=str(self.work))

    def expect(self, ref, rot, mirror, x=100.0, y=200.0, w=80.0, h=80.0):
        """独立推导:归零缩放 -> 镜像 -> 旋转 -> 平移(与 place 口径对账)。"""
        (vx, vy, vw, vh), ports = read_ports(self.work / ref)
        k = min(w / vw, h / vh)
        W, H = vw * k, vh * k
        out = {}
        for pid, (px, py, anchor) in ports.items():
            lx, ly = (px - vx) * k, (py - vy) * k
            if mirror in MIRROR_ANCHOR:
                if mirror == 'x':
                    lx = W - lx
                else:
                    ly = H - ly
                anchor = MIRROR_ANCHOR[mirror].get(anchor, anchor)
            if rot == 90:
                lx, ly = H - ly, lx
            elif rot == 180:
                lx, ly = W - lx, H - ly
            elif rot == 270:
                lx, ly = ly, W - lx
            if rot in ROT_ANCHOR:
                anchor = ROT_ANCHOR[rot][anchor]
            out[pid] = (x + lx, y + ly, anchor)
        return out

    def assertAbs(self, sheet, inst, expected):
        """expected: {port: (x, y, anchor)}。sheet.abs 以 (实例, 端口) 为键,
        期望按夹具实例 ID 补全同样的键后整体对账——实例/端口身份与数值
        同样必须一致,不得只比值或抹掉实例维度。"""
        self.assertEqual(
            {key: (round(v[0], 6), round(v[1], 6), v[2])
             for key, v in sheet.abs.items()},
            {(inst, pid): (round(v[0], 6), round(v[1], 6), v[2])
             for pid, v in expected.items()})

    def test_real_pump_ports_and_anchors_across_axes_and_rotations(self):
        for ctype in PUMPS:
            component = _enabled(ctype)
            ref = 'symbols/' + Path(component['symbol']['asset']).name
            for mirror in (None, 'none', 'x', 'y'):
                for rot in (0, 90, 180, 270):
                    with self.subTest(ctype=ctype, mirror=mirror, rot=rot):
                        extra = {'rot': rot}
                        if mirror is not None:
                            extra['mirror'] = mirror
                        sheet = self.build([('P-001', component, extra)])
                        sheet.place()
                        self.assertAbs(sheet, 'P-001',
                                       self.expect(ref, rot, mirror))

    def test_nonzero_viewbox_scaled_mirror_matches_independent_derivation(self):
        asset = self.work / 'symbols' / 'mini-mirror-pump.svg'
        asset.write_text(MINI_SVG, encoding='utf-8')
        ports = [
            {'id': 'inlet', 'svg_element_id': 'port-in', 'medium': 'hydraulic',
             'role': 'pressure', 'flow_capability': 'in',
             'anchor_direction': 'left'},
            {'id': 'outlet', 'svg_element_id': 'port-out', 'medium': 'hydraulic',
             'role': 'pressure', 'flow_capability': 'out',
             'anchor_direction': 'right'},
            {'id': 'vent', 'svg_element_id': 'port-top', 'medium': 'pneumatic',
             'role': 'measurement', 'flow_capability': 'none',
             'anchor_direction': 'up'},
        ]
        component = {'component_type': 'mini_mirror_pump',
                     'symbol': {'asset': 'mini-mirror-pump.svg',
                                'symbol_status': 'provisional'},
                     'main_path': {'in': 'inlet', 'out': 'outlet'},
                     'ports': ports, 'mirror_safe': True,
                     'layout': {'allowed_rotations_deg': [0, 90, 180, 270],
                                'allow_mirror': True},
                     'mirror_registration': {
                         'axes': ['x', 'y'],
                         'asset_sha256': _sha256(asset),
                         'ports_sha256': _ports_digest('mini_mirror_pump', ports)}}
        for mirror in ('x', 'y'):
            with self.subTest(mirror=mirror):
                sheet = self.build([('M-001', component,
                                     {'mirror': mirror, 'w': 40.0, 'h': 20.0})])
                sheet.place()
                self.assertAbs(
                    sheet, 'M-001',
                    self.expect('symbols/mini-mirror-pump.svg', 0, mirror,
                                w=40.0, h=20.0))
        # 手算字面量(viewBox 20 10 80 40,w=40 h=20 -> k=0.5,盒 40x20):
        # inlet 本地 (0,10) x 镜像 -> (40,10) -> (140,210),锚 left->right;
        # outlet 本地 (80,10) -> (0,10) -> (100,210),锚 right->left。
        sheet = self.build([('M-001', component,
                             {'mirror': 'x', 'w': 40.0, 'h': 20.0})])
        sheet.place()
        self.assertEqual(sheet.abs[('M-001', 'inlet')], (140.0, 210.0, 'right'))
        self.assertEqual(sheet.abs[('M-001', 'outlet')], (100.0, 210.0, 'left'))

    def test_symbols_chain_and_instance_attributes(self):
        component = _enabled('engine_driven_pump')
        sheet = self.build([('P-001', component, {'mirror': 'x', 'rot': 90})])
        sheet.place()
        markup = sheet.symbols()[0]
        g = ET.fromstring(markup)
        self.assertEqual(g.get('data-mirror'), 'x')
        self.assertEqual(g.get('data-mirror-input-anchor'), 'nodes.P-001.mirror')
        self.assertEqual(
            g.get('transform'),
            'translate(100,200) translate(80,0) rotate(90) '
            'translate(80,0) scale(-1,1) scale(1) translate(-0,-0)')
        # 端口身份元数据保持源符号事实:id/锚向不因镜像交换。
        meta = {m.get('data-port-id'): m for m in g.iter()
                if m.tag.endswith('metadata')}
        _vb, source = read_ports(LIB / component['symbol']['asset'])
        self.assertEqual(set(meta), set(source))
        for pid, marker in meta.items():
            self.assertEqual(marker.get('data-port'), 'P-001.' + pid)
            self.assertEqual(marker.get('data-anchor-direction'),
                             source[pid][2])

    def test_no_mirror_markup_stays_byte_compatible(self):
        component = _enabled('engine_driven_pump')
        sheet = self.build([('P-001', component, {'rot': 90})])
        sheet.place()
        markup = sheet.symbols()[0]
        self.assertNotIn('data-mirror', markup)
        self.assertNotIn('scale(-1,1)', markup)
        self.assertNotIn('scale(1,-1)', markup)
        g = ET.fromstring(markup)
        self.assertEqual(
            g.get('transform'),
            'translate(100,200) translate(80,0) rotate(90) scale(1) translate(-0,-0)')

    def test_place_rejects_explicitly_unregistered_entry(self):
        # 生产条目已按 #63 登记;负例改用显式剥离许可字段的副本,
        # "未登记=拒绝"的意图不随生产登记现状翻转。
        sheet = self.build([('P-001', _unregistered(_entry('engine_driven_pump')),
                             {'mirror': 'x'})])
        with self.assertRaises(ValueError) as ctx:
            sheet.place()
        self.assertIn('P-001', str(ctx.exception))
        self.assertIn('mirror_safe', str(ctx.exception))

    def test_place_rejects_illegal_values_and_wrong_axis(self):
        component = _enabled('engine_driven_pump')
        for bad in (True, 0, 1.5, 'X', ['x'], 'none '):
            with self.subTest(mirror=bad):
                sheet = self.build([('P-001', component, {'mirror': bad})])
                with self.assertRaises(ValueError):
                    sheet.place()
        only_x = _enabled('engine_driven_pump', axes=('x',))
        sheet = self.build([('P-001', only_x, {'mirror': 'y'})])
        with self.assertRaises(ValueError) as ctx:
            sheet.place()
        self.assertIn('未在登记', str(ctx.exception))

    def test_place_rejects_stale_registration_after_asset_edit(self):
        component = _enabled('electric_motor_driven_pump')
        asset = self.work / 'symbols' / Path(component['symbol']['asset']).name
        asset.write_bytes(asset.read_bytes() + b'\n<!-- post-approval edit -->\n')
        sheet = self.build([('P-001', component, {'mirror': 'x'})])
        with self.assertRaises(ValueError) as ctx:
            sheet.place()
        self.assertIn('失效', str(ctx.exception))

    def test_place_rejects_stale_registration_after_port_kind_edit(self):
        # 登记后端口契约新增/改写 ports[].kind(目录真实字段,枚举
        # port_kind:flow/body_tap)——摘要必须变化,place 硬失败不换帧。
        component = _enabled('engine_driven_pump')
        component['ports'][0]['kind'] = 'body_tap'
        sheet = self.build([('P-001', component, {'mirror': 'x'})])
        with self.assertRaises(ValueError) as ctx:
            sheet.place()
        self.assertIn('失效', str(ctx.exception))

    def test_mirror_axes_reports_only_permitted_instances(self):
        edp = _enabled('engine_driven_pump')
        emp = _enabled('electric_motor_driven_pump', axes=('y',))
        sheet = self.build([('P-001', edp, {'mirror': 'x'}),
                            ('P-002', emp, {'mirror': 'y'})])
        sheet.place()
        self.assertEqual(sheet.mirror_axes(), {'P-001': 'x', 'P-002': 'y'})


class MirrorGeometryLoadTest(unittest.TestCase):
    """load_geometry:默认拒绝反射;许可轴+姿态(控制点口径)+追溯一致
    才放行获准镜像。"""

    EDP = LIB / 'edp-provisional-stroke.svg'
    NODE = {'x': 100.0, 'y': 200.0, 'w': 80.0, 'h': 80.0,
            'symbol': 'edp-provisional-stroke.svg'}
    CHAIN_X = ('translate(100,200) translate(0,0) rotate(0) '
               'translate(80,0) scale(-1,1) scale(1) translate(-0,-0)')
    CHAIN_PLAIN = ('translate(100,200) translate(0,0) rotate(0) '
                   'scale(1) translate(-0,-0)')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mirror-geom-')
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def symbol(self, markup):
        path = self.work / (markup.split('data-component-type="', 1)[1]
                            .split('"', 1)[0] + '.svg')
        path.write_text(markup, encoding='utf-8')
        return path

    def load(self, transform, node=None, axes=None, meta=None, symbol=None):
        """构造实例 g 并读几何。meta=None 按渲染器口径随节点声明落
        data-mirror / data-mirror-input-anchor(正例带真实 renderer 元数据
        形态);dict 显式给定属性(追溯反例);'strip' 全无(剥离反例)。"""
        import sheet_geometry as sg
        if meta is None:
            declared = (node or self.NODE).get('mirror')
            attrs = (' data-mirror="%s" data-mirror-input-anchor="nodes.P.mirror"'
                     % declared) if declared in ('x', 'y') else ''
        elif meta == 'strip':
            attrs = ''
        else:
            attrs = ''.join(' %s="%s"' % item for item in sorted(meta.items()))
        root = ET.fromstring(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<g id="inst-P"%s transform="%s"/></svg>' % (attrs, transform))
        return sg.load_geometry(root, {'nodes': {'P': dict(node or self.NODE)}},
                                lambda _: str(symbol or self.EDP), axes)

    def issues_text(self, geometry):
        return ' | '.join(str(issue.get('detail')) for issue in geometry['issues'])

    def test_permitted_reflection_loads_mirrored_ports(self):
        geometry = self.load(self.CHAIN_X, dict(self.NODE, mirror='x'),
                             axes={'P': 'x'})
        self.assertEqual(geometry['issues'], [])
        ports = geometry['nodes']['P']['ports']
        # x 镜像:suction (0,40)->(180,240) 锚 right;pressure_out ->(100,240)
        # 锚 left;竖直口只换锚向归属的坐标不变(case_drain 仍 down)。
        self.assertEqual(ports['suction']['position'], (180.0, 240.0))
        self.assertEqual(ports['suction']['anchor_direction'], 'right')
        self.assertEqual(ports['pressure_out']['position'], (100.0, 240.0))
        self.assertEqual(ports['pressure_out']['anchor_direction'], 'left')
        self.assertEqual(ports['case_drain']['position'], (140.0, 280.0))
        self.assertEqual(ports['case_drain']['anchor_direction'], 'down')

    def test_reflection_without_permission_is_rejected_by_default(self):
        geometry = self.load(self.CHAIN_X, dict(self.NODE, mirror='x'))
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn('no validated catalog permission', self.issues_text(geometry))

    def test_undeclared_reflection_is_rejected_even_without_declaration(self):
        geometry = self.load(self.CHAIN_X)
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn('without a declared mirror', self.issues_text(geometry))

    def test_permission_axis_must_match_declaration(self):
        geometry = self.load(self.CHAIN_X, dict(self.NODE, mirror='y'),
                             axes={'P': 'x'})
        self.assertIn('differs from the validated permission axis',
                      self.issues_text(geometry))

    def test_wrong_axis_or_pose_is_an_explicit_issue(self):
        geometry = self.load(self.CHAIN_X, dict(self.NODE, mirror='y'),
                             axes={'P': 'y'})
        self.assertIn('reflects the x axis', self.issues_text(geometry))
        shifted = self.CHAIN_X.replace('translate(100,200)',
                                       'translate(101,200)')
        geometry = self.load(shifted, dict(self.NODE, mirror='x'),
                             axes={'P': 'x'})
        self.assertIn('does not match the declared layout',
                      self.issues_text(geometry))

    def test_declared_mirror_missing_from_matrix_is_an_issue(self):
        geometry = self.load(self.CHAIN_PLAIN, dict(self.NODE, mirror='x'),
                             axes={'P': 'x'})
        self.assertIn('no reflection', self.issues_text(geometry))

    def test_plain_transform_keeps_existing_behaviour(self):
        geometry = self.load(self.CHAIN_PLAIN)
        self.assertEqual(geometry['issues'], [])
        self.assertIn('P', geometry['nodes'])

    # ---- 姿态容差:按变换后控制点对账(审核反例) ----

    def test_small_k_large_viewbox_doubled_scale_is_rejected(self):
        # viewBox(-48000,0,96000,142000),节点 (100,200,96,142,mirror x)
        # -> k=0.001,期望矩阵 (-0.001,0,0,0.001,148,200)。实际放大一倍
        # (-0.002,...,148,200) 平移恰好相同:矩阵系数绝对差仅 0.001,
        # 但控制点变换后差 48 个根单位,必须拒绝,不得 issues=[]。
        big = self.symbol(BIG_VIEWBOX_SVG)
        node = {'x': 100.0, 'y': 200.0, 'w': 96.0, 'h': 142.0,
                'mirror': 'x', 'symbol': big.name}
        geometry = self.load('matrix(-0.002,0,0,0.002,148,200)', node,
                             axes={'P': 'x'}, symbol=big)
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn('does not match the declared layout',
                      self.issues_text(geometry))

    def test_small_k_large_viewbox_correct_pose_loads(self):
        # 同一符号、正确矩阵:非零原点 + 小 k 正常放行,端口/足迹与
        # 手算一致(k=0.001,W=96,H=142;inlet 源 (-48000,71000) 镜像后
        # (196,271) 锚 right,outlet (100,271) 锚 left)。
        big = self.symbol(BIG_VIEWBOX_SVG)
        node = {'x': 100.0, 'y': 200.0, 'w': 96.0, 'h': 142.0,
                'mirror': 'x', 'symbol': big.name}
        geometry = self.load('matrix(-0.001,0,0,0.001,148,200)', node,
                             axes={'P': 'x'}, symbol=big)
        self.assertEqual(geometry['issues'], [])
        self.assertIn('P', geometry['nodes'])
        ports = geometry['nodes']['P']['ports']
        self.assertEqual([round(v, 3) for v in ports['inlet']['position']],
                         [196.0, 271.0])
        self.assertEqual(ports['inlet']['anchor_direction'], 'right')
        self.assertEqual([round(v, 3) for v in ports['outlet']['position']],
                         [100.0, 271.0])
        self.assertEqual(ports['outlet']['anchor_direction'], 'left')
        self.assertEqual([round(v, 3) for v in geometry['nodes']['P']['footprint']],
                         [100.0, 200.0, 196.0, 342.0])

    def test_percent_g_scale_rounding_still_passes(self):
        # k=80/240=1/3,渲染器以 %g 六位有效数字输出 scale(0.333333):
        # 正常 %g 舍入不得误拒(控制点预算保留舍入余量)。
        third = self.symbol(THIRD_SCALE_SVG)
        node = {'x': 100.0, 'y': 200.0, 'w': 80.0, 'h': 80.0,
                'mirror': 'x', 'symbol': third.name}
        geometry = self.load(
            'translate(100,200) translate(0,0) rotate(0) translate(80,0) '
            'scale(-1,1) scale(0.333333) translate(-0,-0)', node,
            axes={'P': 'x'}, symbol=third)
        self.assertEqual(geometry['issues'], [])
        self.assertIn('P', geometry['nodes'])

    def test_cancellable_huge_viewbox_origin_cannot_buy_tolerance(self):
        # 公开 load_geometry 反例(2026-10-12 审核):viewBox=(1e9,0,80,80)、
        # 节点 (100,200,80,80,mirror x),期望矩阵 (-1,0,0,1,1000000180,200);
        # 实际矩阵 e 多 100(1000000280)——整个符号在图上平移 100px。
        # 旧口径把 |a*x|+|e| 的可抵消大数(~2e9)算进相对预算(容差 ~2e5)
        # 仍判匹配;此前"大 viewBox 倍缩放"修复(按控制点判尺度)解决了
        # 小 k 系数盲区,但预算基数仍随源坐标放大,这轮修掉。100px 错位
        # 在最终图纸上就是 100 个 SVG 单位,必须拒绝。
        huge = self.symbol(HUGE_ORIGIN_SVG)
        node = {'x': 100.0, 'y': 200.0, 'w': 80.0, 'h': 80.0,
                'mirror': 'x', 'symbol': huge.name}
        geometry = self.load('matrix(-1,0,0,1,1000000280,200)', node,
                             axes={'P': 'x'}, symbol=huge)
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn('does not match the declared layout',
                      self.issues_text(geometry))

    def test_huge_origin_exact_pose_still_loads(self):
        # 同一符号、无错位仍放行:修复收紧的是容差尺度(不随可抵消源坐标
        # 放大),不是一刀切拒绝大原点;1e9 恰可被 %g 精确表示,姿态对账
        # 差为 0。无法用该容差表达的精度会被拒绝而不是被吞掉。
        huge = self.symbol(HUGE_ORIGIN_SVG)
        node = {'x': 100.0, 'y': 200.0, 'w': 80.0, 'h': 80.0,
                'mirror': 'x', 'symbol': huge.name}
        geometry = self.load('matrix(-1,0,0,1,1000000180,200)', node,
                             axes={'P': 'x'}, symbol=huge)
        self.assertEqual(geometry['issues'], [])
        self.assertIn('P', geometry['nodes'])
        ports = geometry['nodes']['P']['ports']
        self.assertEqual([round(v, 6) for v in ports['inlet']['position']],
                         [180.0, 240.0])
        self.assertEqual([round(v, 6) for v in ports['outlet']['position']],
                         [100.0, 240.0])

    # ---- 追溯一致性:声明/许可/矩阵都成立,记录仍须对得上 ----

    def test_recorded_mirror_axis_must_match_declaration(self):
        geometry = self.load(self.CHAIN_X, dict(self.NODE, mirror='x'),
                             axes={'P': 'x'},
                             meta={'data-mirror': 'y',
                                   'data-mirror-input-anchor': 'nodes.P.mirror'})
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn("records data-mirror='y'", self.issues_text(geometry))

    def test_recorded_input_anchor_must_point_at_own_node(self):
        geometry = self.load(self.CHAIN_X, dict(self.NODE, mirror='x'),
                             axes={'P': 'x'},
                             meta={'data-mirror': 'x',
                                   'data-mirror-input-anchor': 'nodes.OTHER.mirror'})
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn('data-mirror-input-anchor', self.issues_text(geometry))
        self.assertIn('nodes.OTHER.mirror', self.issues_text(geometry))

    def test_mirror_attributes_without_declaration_are_rejected(self):
        geometry = self.load(self.CHAIN_PLAIN,
                             meta={'data-mirror': 'y',
                                   'data-mirror-input-anchor': 'nodes.P.mirror'})
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn('layout declares no mirror', self.issues_text(geometry))

    def test_declared_mirror_without_trace_attributes_is_rejected(self):
        geometry = self.load(self.CHAIN_X, dict(self.NODE, mirror='x'),
                             axes={'P': 'x'}, meta='strip')
        self.assertNotIn('P', geometry['nodes'])
        self.assertIn('records data-mirror', self.issues_text(geometry))


class MirrorRenderCLI(unittest.TestCase):
    """真实 CLI:临时 catalog 启用两泵;小基准图 mirror=y 正例与拒绝负例。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mirror-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.work = make_render_workspace(Path(self.tmp.name), SMALL)
        catalog = copy.deepcopy(PROD_CATALOG)
        enabled = {ctype: _enabled(ctype) for ctype in PUMPS}
        catalog['components'] = [enabled.get(c['component_type'], c)
                                 for c in catalog['components']]
        (self.work / 'component-catalog.json').write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')

    def run_cli(self, script, expect=0):
        result = subprocess.run([sys.executable, str(self.work / script)],
                                cwd=self.work, capture_output=True,
                                text=True, timeout=240)
        self.assertEqual(result.returncode, expect,
                         result.stdout + result.stderr)
        return result

    def set_mirror(self, value):
        layout_path = self.work / '1#系统.layout.json'
        layout = json.loads(layout_path.read_text(encoding='utf-8'))
        layout['nodes']['EDP-001']['mirror'] = value
        layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2),
                               encoding='utf-8')

    def test_small_sheet_mirrors_edp_on_y_and_stays_green(self):
        # mirror=y @ rot0:EDP 左右主口(suction/pressure_out)位置与锚向不变,
        # 既有接线不靠"未接线"冒充通过;上下口(case_drain/drive_shaft)互换。
        self.set_mirror('y')
        self.run_cli('render_l0_sheet.py')
        svg = (self.work / '1#系统原理图.svg').read_text(encoding='utf-8')
        pump = next(e for e in ET.fromstring(svg).iter()
                    if e.get('id') == 'inst-EDP-001')
        self.assertEqual(pump.get('data-mirror'), 'y')
        self.assertEqual(pump.get('data-mirror-input-anchor'),
                         'nodes.EDP-001.mirror')
        self.assertIn('translate(0,80) scale(1,-1)', pump.get('transform'))
        manifest = (self.work / '1#系统原理图-topology.md').read_text(encoding='utf-8')
        self.assertIn('EDP-001: mirror=y', manifest)
        self.assertIn('不因镜像提升', manifest)
        self.run_cli('validate_sheet.py')
        report = json.loads((self.work / 'validation-report.json')
                            .read_text(encoding='utf-8'))
        self.assertEqual(report['fail_count'], 0, report['checks'])
        ports = report['geometry']['nodes']['EDP-001']['ports']
        self.assertEqual([round(v, 6) for v in ports['suction']['position']],
                         [570.0, 530.0])
        self.assertEqual(ports['suction']['anchor_direction'], 'left')
        self.assertEqual([round(v, 6) for v in ports['pressure_out']['position']],
                         [650.0, 530.0])
        self.assertEqual(ports['pressure_out']['anchor_direction'], 'right')

    def test_no_mirror_output_is_byte_identical_to_production_catalog(self):
        # make_render_workspace 只创建 root/run,假定 root 已存在;
        # baseline 是临时根下的嵌套父目录,须先建好再复制模板。
        baseline_root = Path(self.tmp.name) / 'baseline'
        baseline_root.mkdir()
        baseline = make_render_workspace(baseline_root, SMALL)
        result = subprocess.run([sys.executable, str(baseline / 'render_l0_sheet.py')],
                                cwd=baseline, capture_output=True, text=True,
                                timeout=240)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.run_cli('render_l0_sheet.py')
        produced = (self.work / '1#系统原理图.svg').read_text(encoding='utf-8')
        self.assertEqual(produced,
                         (baseline / '1#系统原理图.svg').read_text(encoding='utf-8'))
        self.assertNotIn('data-mirror', produced)
        self.run_cli('validate_sheet.py')
        report = json.loads((self.work / 'validation-report.json')
                            .read_text(encoding='utf-8'))
        self.assertEqual(report['fail_count'], 0, report['checks'])

    def test_cli_contract_failure_on_explicitly_unregistered_catalog(self):
        self.set_mirror('x')
        # 显式剥离两泵许可字段的临时目录(负例不依赖生产登记现状,
        # 生产已按 #63 登记,见 tests/repository/test_mirror_registration.py)
        # -> contract 级硬失败,不出图。
        catalog = copy.deepcopy(PROD_CATALOG)
        catalog['components'] = [
            _unregistered(c) if c.get('component_type') in PUMPS else c
            for c in catalog['components']]
        (self.work / 'component-catalog.json').write_text(
            json.dumps(catalog, ensure_ascii=False, indent=2), encoding='utf-8')
        result = self.run_cli('render_l0_sheet.py', expect=1)
        self.assertIn('镜像许可', result.stdout)
        self.assertIn('mirror_safe', result.stdout)
        self.assertIn('EDP-001', result.stdout)
        self.assertFalse((self.work / '1#系统原理图.svg').exists())

    def test_cli_contract_failure_on_illegal_value(self):
        self.set_mirror(True)
        result = self.run_cli('render_l0_sheet.py', expect=1)
        self.assertIn('不支持的 mirror', result.stdout)
        self.assertFalse((self.work / '1#系统原理图.svg').exists())

    def test_cli_contract_failure_on_stale_registration(self):
        self.set_mirror('y')
        asset = self.work / 'symbols' / 'edp-provisional-stroke.svg'
        asset.write_bytes(asset.read_bytes() + b'\n<!-- edit after registration -->\n')
        result = self.run_cli('render_l0_sheet.py', expect=1)
        self.assertIn('失效', result.stdout)
        self.assertFalse((self.work / '1#系统原理图.svg').exists())

    def test_validator_fails_wrong_axis_reflection_in_final_svg(self):
        self.set_mirror('y')
        self.run_cli('render_l0_sheet.py')
        svg_path = self.work / '1#系统原理图.svg'
        svg_path.write_text(svg_path.read_text(encoding='utf-8').replace(
            'translate(0,80) scale(1,-1)', 'translate(80,0) scale(-1,1)'),
            encoding='utf-8')
        result = self.run_cli('validate_sheet.py', expect=1)
        report = json.loads((self.work / 'validation-report.json')
                            .read_text(encoding='utf-8'))
        failures = [c for c in report['checks'] if c['result'] == 'fail']
        self.assertTrue(any(c['id'] == 'V3'
                            and 'reflects the x axis' in c['detail']
                            for c in failures), failures)

    def test_validator_fails_undeclared_reflection_in_final_svg(self):
        self.run_cli('render_l0_sheet.py')
        svg_path = self.work / '1#系统原理图.svg'
        svg_path.write_text(svg_path.read_text(encoding='utf-8').replace(
            'rotate(0) scale(1)',
            'rotate(0) translate(80,0) scale(-1,1) scale(1)'),
            encoding='utf-8')
        self.run_cli('validate_sheet.py', expect=1)
        report = json.loads((self.work / 'validation-report.json')
                            .read_text(encoding='utf-8'))
        failures = [c for c in report['checks'] if c['result'] == 'fail']
        self.assertTrue(any(c['id'] == 'V3'
                            and 'without a declared mirror' in c['detail']
                            for c in failures), failures)

    def test_validator_fails_inconsistent_mirror_trace_in_final_svg(self):
        # 真实 renderer 元数据被篡改:矩阵/许可/声明均正确,但实例组
        # data-mirror 记错轴、输入锚指错节点,校核必须 FAIL,不得 issues=[]。
        self.set_mirror('y')
        self.run_cli('render_l0_sheet.py')
        svg_path = self.work / '1#系统原理图.svg'
        svg_path.write_text(svg_path.read_text(encoding='utf-8').replace(
            'data-mirror="y" data-mirror-input-anchor="nodes.EDP-001.mirror"',
            'data-mirror="x" data-mirror-input-anchor="nodes.OTHER.mirror"'),
            encoding='utf-8')
        self.run_cli('validate_sheet.py', expect=1)
        report = json.loads((self.work / 'validation-report.json')
                            .read_text(encoding='utf-8'))
        failures = [c for c in report['checks'] if c['result'] == 'fail']
        self.assertTrue(any(c['id'] == 'V3'
                            and 'records data-mirror' in c['detail']
                            for c in failures), failures)

    def test_validator_fails_mirror_attributes_without_declaration(self):
        # 无声明却挂镜像属性也不能通过:给非镜像渲染的实例组补上
        # data-mirror 属性,校核必须 FAIL。
        self.run_cli('render_l0_sheet.py')
        svg_path = self.work / '1#系统原理图.svg'
        svg_path.write_text(svg_path.read_text(encoding='utf-8').replace(
            'data-input-anchor="parts.EDP-001"',
            'data-input-anchor="parts.EDP-001" data-mirror="x" '
            'data-mirror-input-anchor="nodes.EDP-001.mirror"', 1),
            encoding='utf-8')
        self.run_cli('validate_sheet.py', expect=1)
        report = json.loads((self.work / 'validation-report.json')
                            .read_text(encoding='utf-8'))
        failures = [c for c in report['checks'] if c['result'] == 'fail']
        self.assertTrue(any(c['id'] == 'V3'
                            and 'layout declares no mirror' in c['detail']
                            for c in failures), failures)


if __name__ == '__main__':
    unittest.main()
