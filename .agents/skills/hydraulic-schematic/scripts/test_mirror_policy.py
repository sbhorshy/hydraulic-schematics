# -*- coding: utf-8 -*-
"""mirror_policy 契约测试(#63 步骤一:纯策略/坐标契约,不接入渲染)。

只经公开函数与真实(临时)SVG 校验;几何期望一律独立字面量手算,
不用被测模块反推期望。审批数据(登记)用 hashlib+json 在本文件内
按 #63 口径独立构造,不复用 mirror_policy 的实现;测试数据只取
skill 内资产与临时文件,不依赖 skill 外的任何事实指针文件。
"""
import copy
import hashlib
import importlib.util
import json
import math
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(HERE, name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mp = _load('mirror_policy')
sg = _load('sheet_geometry')

CATALOG = os.path.normpath(os.path.join(
    HERE, '..', 'assets', 'component-library', 'component-catalog.json'))
LIB = os.path.dirname(CATALOG)

# 登记口径的键清单(测试内独立字面量,勿从被测模块取;端口类别是目录
# 真实字段 ports[].kind,枚举名才是 port_kind)
PORT_FIELDS = ('id', 'svg_element_id', 'medium', 'role',
               'flow_capability', 'anchor_direction', 'kind')

MINIMAL_SYMBOL_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80" data-component-type="mini_pump">
  <g id="symbol">
    <path id="mini-pump-body" d="M8 8 H72 V72 H8 Z"/>
  </g>
  <g id="connection-points">
    <circle id="port-suction" data-port-id="suction" cx="0" cy="40" r="3"
            data-anchor-direction="left" data-port-role="suction" data-medium="hydraulic"/>
    <circle id="port-pressure-out" data-port-id="pressure_out" cx="80" cy="40" r="3"
            data-anchor-direction="right" data-port-role="pressure" data-medium="hydraulic"/>
  </g>
</svg>
'''


def _catalog_entry(component_type):
    with open(CATALOG, encoding='utf-8') as handle:
        catalog = json.load(handle)
    return next(c for c in catalog['components']
                if c['component_type'] == component_type)


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _ports_sha256(component_type, ports, fields=PORT_FIELDS):
    trimmed = [{key: port[key] for key in fields if key in port}
               for port in ports]
    trimmed.sort(key=lambda port: port['id'])
    payload = {'component_type': component_type, 'ports': trimmed}
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'))
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class MirrorValueDomainTest(unittest.TestCase):
    """mirror 值域与严格类型;非镜像不要求任何登记。"""

    BARE = {'component_type': 'engine_driven_pump', 'ports': []}

    def test_no_mirror_values_are_compatible_without_registration(self):
        # 缺省/None/False/'none' 均为不镜像,且不触碰资产路径。
        self.assertIsNone(mp.check_mirror({}, self.BARE, '/nonexistent.svg'))
        for value in (None, False, 'none'):
            with self.subTest(mirror=value):
                self.assertIsNone(
                    mp.check_mirror({'mirror': value}, self.BARE, None))

    def test_zero_is_not_false(self):
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 0}, self.BARE, '/nonexistent.svg')

    def test_rejected_mirror_values(self):
        rejected = (True, 1, -1, 1.5, 0.0, '', 'X', 'x ', 'xy', 'none ',
                    'None', b'x', ['x'], ('x',), {'axis': 'x'},
                    {'x'}, set())
        for value in rejected:
            with self.subTest(mirror=value):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': value}, self.BARE,
                                    '/nonexistent.svg')

    def test_node_must_be_a_dict(self):
        for bad in ([], 'EDP-001', None, 7):
            with self.subTest(node=bad):
                with self.assertRaises(ValueError):
                    mp.check_mirror(bad, self.BARE, '/nonexistent.svg')


class MirrorGeometryTest(unittest.TestCase):
    """mirror_point / mirror_anchor / mirror_svg_transform 的字面量期望。"""

    def test_x_reflection_only_touches_x(self):
        self.assertEqual(mp.mirror_point(10, 20, 80, 60, 'x'), (70.0, 20.0))
        self.assertEqual(mp.mirror_point(0, 0, 80, 60, 'x'), (80.0, 0.0))
        self.assertEqual(mp.mirror_point(80, 60, 80, 60, 'x'), (0.0, 60.0))
        self.assertEqual(mp.mirror_point(30, 45, 80, 60, 'x'), (50.0, 45.0))

    def test_y_reflection_only_touches_y(self):
        self.assertEqual(mp.mirror_point(10, 20, 80, 60, 'y'), (10.0, 40.0))
        self.assertEqual(mp.mirror_point(0, 0, 80, 60, 'y'), (0.0, 60.0))
        self.assertEqual(mp.mirror_point(80, 60, 80, 60, 'y'), (80.0, 0.0))
        self.assertEqual(mp.mirror_point(30, 45, 80, 60, 'y'), (30.0, 15.0))

    def test_none_axis_is_identity(self):
        self.assertEqual(mp.mirror_point(10, 20, 80, 60, None), (10.0, 20.0))
        self.assertEqual(mp.mirror_anchor('left', None), 'left')
        self.assertEqual(mp.mirror_anchor('down', None), 'down')

    def test_anchor_swaps_all_four_directions_on_x(self):
        self.assertEqual(mp.mirror_anchor('left', 'x'), 'right')
        self.assertEqual(mp.mirror_anchor('right', 'x'), 'left')
        self.assertEqual(mp.mirror_anchor('up', 'x'), 'up')
        self.assertEqual(mp.mirror_anchor('down', 'x'), 'down')

    def test_anchor_swaps_all_four_directions_on_y(self):
        self.assertEqual(mp.mirror_anchor('up', 'y'), 'down')
        self.assertEqual(mp.mirror_anchor('down', 'y'), 'up')
        self.assertEqual(mp.mirror_anchor('left', 'y'), 'left')
        self.assertEqual(mp.mirror_anchor('right', 'y'), 'right')

    def test_point_rejects_nonfinite_or_nonpositive_dimensions(self):
        for width, height in ((0, 60), (80, 0), (-80, 60), (80, -60),
                              (float('nan'), 60), (80, float('inf')),
                              (float('-inf'), 60), (True, 60), ('80', 60),
                              (None, 60)):
            with self.subTest(width=width, height=height):
                with self.assertRaises(ValueError):
                    mp.mirror_point(10, 20, width, height, 'x')

    def test_point_rejects_bad_coordinates_and_axes(self):
        for x, y in ((float('nan'), 20), (10, float('inf')), ('10', 20),
                     (True, 20)):
            with self.subTest(x=x, y=y):
                with self.assertRaises(ValueError):
                    mp.mirror_point(x, y, 80, 60, 'x')
        for axis in ('none', '', 'X', 'xy', True, False, 0, 1, ['x']):
            with self.subTest(axis=axis):
                with self.assertRaises(ValueError):
                    mp.mirror_point(10, 20, 80, 60, axis)

    def test_anchor_rejects_non_directions_and_bad_axes(self):
        for anchor in ('Left', 'LEFT', '', 'diagonal', None, 0, ['left']):
            with self.subTest(anchor=anchor):
                with self.assertRaises(ValueError):
                    mp.mirror_anchor(anchor, 'x')
        for axis in ('none', '', 'X', True, 0, ['x']):
            with self.subTest(axis=axis):
                with self.assertRaises(ValueError):
                    mp.mirror_anchor('left', axis)

    def test_svg_transform_strings_are_literal(self):
        self.assertEqual(mp.mirror_svg_transform(80, 60, 'x'),
                         'translate(80,0) scale(-1,1)')
        self.assertEqual(mp.mirror_svg_transform(80, 60, 'y'),
                         'translate(0,60) scale(1,-1)')
        self.assertEqual(mp.mirror_svg_transform(80, 60, None), '')
        self.assertEqual(mp.mirror_svg_transform(80.5, 60.25, 'x'),
                         'translate(80.5,0) scale(-1,1)')

    def test_svg_transform_validates_arguments_even_without_mirror(self):
        for args in ((0, 60, 'x'), (80, 0, 'y'), (80, 60, 'z'),
                     (float('nan'), 60, 'x'), (80, 60, 'none'),
                     (True, 60, 'x')):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    mp.mirror_svg_transform(*args)
        # 尺寸校验不因无镜像而豁免
        for args in ((0, 60, None), (-80, 60, None), ('80', 60, None)):
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    mp.mirror_svg_transform(*args)
        self.assertEqual(mp.mirror_svg_transform(80, 60, None), '')

    def test_transform_string_reflects_points(self):
        # 变换串语义用 sheet_geometry 求值(实际值),期望为字面量。
        tx = sg.transform(mp.mirror_svg_transform(80, 60, 'x'))
        self.assertEqual(sg.point(tx, (0.0, 0.0)), (80.0, 0.0))
        self.assertEqual(sg.point(tx, (80.0, 0.0)), (0.0, 0.0))
        self.assertEqual(sg.point(tx, (10.0, 25.0)), (70.0, 25.0))
        ty = sg.transform(mp.mirror_svg_transform(80, 60, 'y'))
        self.assertEqual(sg.point(ty, (0.0, 0.0)), (0.0, 60.0))
        self.assertEqual(sg.point(ty, (10.0, 25.0)), (10.0, 35.0))
        self.assertEqual(sg.transform(''), sg.IDENTITY)


class MirrorRegistrationTest(unittest.TestCase):
    """三道闸、轴批准、登记与当前资产/端口契约的绑定(真实 EDP 资产)。"""

    def setUp(self):
        self.entry = copy.deepcopy(_catalog_entry('engine_driven_pump'))
        self.asset = os.path.join(LIB, self.entry['symbol']['asset'])
        self.assertTrue(os.path.isfile(self.asset))
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def _enabled(self, axes=('x', 'y'), ports=None):
        component = copy.deepcopy(self.entry)
        component['mirror_safe'] = True
        component['layout']['allow_mirror'] = True
        component['mirror_registration'] = {
            'axes': list(axes),
            'asset_sha256': _file_sha256(self.asset),
            'ports_sha256': _ports_sha256(
                component['component_type'],
                component['ports'] if ports is None else ports),
        }
        return component

    def test_explicitly_unregistered_entry_rejects_mirror(self):
        # 负例口径:目录条目的临时副本显式删除全部许可字段后再请求镜像,
        # 必须被拒。"未登记=未许可"是独立事实,不与生产 catalog 登记现状
        # 耦合——生产已按 #63 登记两泵后,本负例仍以剥离字段后的副本成立。
        for ctype in ('engine_driven_pump', 'electric_motor_driven_pump'):
            entry = copy.deepcopy(_catalog_entry(ctype))
            entry.pop('mirror_safe', None)
            entry.pop('mirror_registration', None)
            entry.setdefault('layout', {}).pop('allow_mirror', None)
            with self.assertRaises(ValueError):
                mp.check_mirror(
                    {'mirror': 'x'}, entry,
                    os.path.join(LIB, entry['symbol']['asset']))

    def test_registered_mirror_passes_both_axes(self):
        component = self._enabled()
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, component, self.asset), 'x')
        self.assertEqual(
            mp.check_mirror({'mirror': 'y'}, component, self.asset), 'y')

    def test_gate_mirror_safe_must_be_strictly_true(self):
        for value in (False, 1, 'true', None):
            component = self._enabled()
            component['mirror_safe'] = value
            with self.subTest(mirror_safe=value):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, component, self.asset)
        component = self._enabled()
        del component['mirror_safe']
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)

    def test_gate_layout_allow_mirror_must_be_strictly_true(self):
        for value in (False, 1, 'true', None):
            component = self._enabled()
            component['layout']['allow_mirror'] = value
            with self.subTest(allow_mirror=value):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, component, self.asset)
        component = self._enabled()
        component['layout'] = {'allowed_rotations_deg': [0, 90, 180, 270]}
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)
        component = self._enabled()
        del component['layout']
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)

    def test_gate_registration_must_exist(self):
        component = self._enabled()
        del component['mirror_registration']
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)

    def test_gate_axis_must_be_registered(self):
        component = self._enabled(axes=('x',))
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, component, self.asset), 'x')
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'y'}, component, self.asset)

    def test_gate_malformed_axes_are_rejected(self):
        for axes in ('x', '', [], ['xy'], ['X'], ['x', 'x'], [True],
                     [None], ('x',), [['x']]):
            component = self._enabled()
            # 直接注坏 axes,登记其余部分仍按当前资产/端口构造
            component['mirror_registration']['axes'] = axes
            with self.subTest(axes=axes):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, component, self.asset)

    def test_gate_digest_fields_must_be_hex64(self):
        for key, value in (('asset_sha256', 'deadbeef'),
                           ('asset_sha256', 123),
                           ('asset_sha256', None),
                           ('asset_sha256', 'ABCD' + '0' * 60),
                           ('ports_sha256', 'z' * 64),
                           ('ports_sha256', '')):
            component = self._enabled()
            component['mirror_registration'][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, component, self.asset)
        component = self._enabled()
        del component['mirror_registration']['asset_sha256']
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)

    def test_registration_binds_to_current_asset_bytes(self):
        component = self._enabled()
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, component, self.asset), 'x')
        tampered = os.path.join(self.tmp, 'edp-tampered.svg')
        with open(self.asset, 'rb') as src, open(tampered, 'wb') as dst:
            dst.write(src.read() + b'\n<!-- post-approval edit -->\n')
        # 登记绑旧字节,文件已改 -> 拒绝
        with self.assertRaises(ValueError) as ctx:
            mp.check_mirror({'mirror': 'x'}, component, tampered)
        self.assertIn('失效', str(ctx.exception))
        # 登记绑新字节,拿来镜像旧文件 -> 同样拒绝
        rebound = self._enabled()
        rebound['mirror_registration']['asset_sha256'] = _file_sha256(tampered)
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, rebound, self.asset)
        # 登记绑新字节并镜像新文件 -> 通过(登记如实跟随当前资产)
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, rebound, tampered), 'x')

    def test_registration_binds_to_current_port_contract(self):
        # 登记后改端口契约(任一契约字段) -> 拒绝
        for mutate in (
                lambda ports: ports[0].__setitem__('role', 'return'),
                lambda ports: ports[0].__setitem__('anchor_direction', 'up'),
                lambda ports: ports.append(dict(ports[0], id='extra_port')),
                lambda ports: ports.pop()):
            component = self._enabled()
            mutate(component['ports'])
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, component, self.asset)
        # 登记按删改后的口径构造,与目录现契约不符 -> 拒绝
        component = self._enabled()
        mutated = copy.deepcopy(component['ports'])
        mutated[0]['flow_capability'] = 'bidirectional'
        component['mirror_registration']['ports_sha256'] = _ports_sha256(
            component['component_type'], mutated)
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)

    def test_port_kind_participates_and_extras_are_ignored(self):
        component = self._enabled()
        component['ports'] = [
            {'id': 'a', 'svg_element_id': 'port-a', 'medium': 'hydraulic',
             'role': 'measurement', 'flow_capability': 'none',
             'anchor_direction': 'down', 'kind': 'body_tap'},
            {'id': 'b', 'svg_element_id': 'port-b', 'medium': 'hydraulic',
             'role': 'pressure', 'flow_capability': 'out',
             'anchor_direction': 'right'},
        ]
        component['mirror_registration']['ports_sha256'] = _ports_sha256(
            component['component_type'], component['ports'])
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, component, self.asset), 'x')
        # 七键之外的说明字段不参与契约:加 role_note 不失效
        component['ports'][0]['role_note'] = '说明不入摘要'
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, component, self.asset), 'x')
        # kind 被排除的口径登记 -> 必须拒绝(证明该字段参与契约)
        without_kind = tuple(f for f in PORT_FIELDS if f != 'kind')
        component['mirror_registration']['ports_sha256'] = _ports_sha256(
            component['component_type'], component['ports'], fields=without_kind)
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)

    def test_port_kind_add_or_change_invalidates_registration(self):
        # 公开 check_mirror 回归(2026-10-12 审核 A):目录真实字段是
        # ports[].kind(枚举 port_kind:flow/body_tap,缺省 flow,见
        # symbol-library"本体感测口"),不是 'port_kind' 键。生产两泵现存
        # ports 均无 kind,登记按无 kind 口径成立;登记后给任一端口新增
        # kind、或改写其值,端口契约摘要必须变化而令登记失效,重按新契约
        # 登记后才重新放行。
        component = self._enabled()  # 按当前 EDP 端口(无 kind)登记
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, component, self.asset), 'x')
        added = copy.deepcopy(component)
        added['ports'][0]['kind'] = 'body_tap'
        with self.assertRaises(ValueError) as ctx:
            mp.check_mirror({'mirror': 'x'}, added, self.asset)
        self.assertIn('失效', str(ctx.exception))
        rebound = copy.deepcopy(added)
        rebound['mirror_registration']['ports_sha256'] = _ports_sha256(
            rebound['component_type'], rebound['ports'])
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, rebound, self.asset), 'x')
        rebound['ports'][0]['kind'] = 'flow'
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, rebound, self.asset)

    def test_asset_path_must_be_readable(self):
        component = self._enabled()
        for bad in (os.path.join(self.tmp, 'missing.svg'), None, 123, True):
            with self.subTest(asset_path=bad):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, component, bad)

    def test_component_must_be_a_dict_when_mirroring(self):
        for bad in (None, [], 'engine_driven_pump'):
            with self.subTest(component=bad):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, bad, self.asset)

    def test_errors_are_locatable(self):
        # #63 生产登记后 self.entry（真实目录条目）已带三道闸许可，
        # check_mirror 不再天然抛错；错误定位断言改用明确剥离许可字段的
        # 副本（mirror_safe / mirror_registration / layout.allow_mirror），
        # 首个拒绝仍须带 component_type 与符号资产名定位。
        unregistered = copy.deepcopy(self.entry)
        unregistered.pop('mirror_safe', None)
        unregistered.pop('mirror_registration', None)
        layout = unregistered.get('layout')
        if isinstance(layout, dict):
            layout.pop('allow_mirror', None)
        node = {'mirror': 'x', 'symbol': unregistered['symbol']['asset']}
        with self.assertRaises(ValueError) as ctx:
            mp.check_mirror(node, unregistered, self.asset)
        message = str(ctx.exception)
        self.assertIn('engine_driven_pump', message)
        self.assertIn('edp-provisional-stroke.svg', message)
        with self.assertRaises(ValueError) as ctx:
            mp.check_mirror(
                {'mirror': ['x'], 'symbol': self.entry['symbol']['asset']},
                self.entry, self.asset)
        self.assertIn('edp-provisional-stroke.svg', str(ctx.exception))


class ProductionRegistrationTest(unittest.TestCase):
    """生产登记现状(#63,2026-10-12):规范源 catalog 仅两泵获准 x/y。

    只用 skill 自带 catalog 与库内符号资产,不依赖 skill 外事实;摘要值
    不写字面量——check_mirror 以当前文件字节/端口契约对账,登记漂移
    (符号或端口变更未重登记)即失败。1# 工作目录 catalog 的对应现状由
    tests/repository/test_mirror_registration.py 断言(skill 拷贝件之外)。
    """

    PUMPS = ('engine_driven_pump', 'electric_motor_driven_pump')

    @classmethod
    def setUpClass(cls):
        cls.entries = {}
        with open(CATALOG, encoding='utf-8') as handle:
            catalog = json.load(handle)
        for entry in catalog['components']:
            cls.entries[entry['component_type']] = entry

    def test_only_the_two_pumps_carry_mirror_permission(self):
        enabled = {ctype for ctype, entry in self.entries.items()
                   if entry.get('mirror_safe') is True}
        self.assertEqual(enabled, set(self.PUMPS))

    def test_registered_pumps_pass_check_mirror_on_real_assets(self):
        for ctype in self.PUMPS:
            entry = self.entries[ctype]
            asset = os.path.join(LIB, entry['symbol']['asset'])
            self.assertTrue(os.path.isfile(asset), asset)
            self.assertEqual(entry['mirror_registration']['axes'],
                             ['x', 'y'])
            for axis in ('x', 'y'):
                with self.subTest(ctype=ctype, axis=axis):
                    self.assertEqual(
                        mp.check_mirror({'mirror': axis}, entry, asset),
                        axis)

    def test_every_other_type_is_denied_by_default(self):
        for ctype, entry in self.entries.items():
            if ctype in self.PUMPS:
                continue
            asset = os.path.join(LIB, entry['symbol']['asset'])
            with self.subTest(ctype=ctype):
                with self.assertRaises(ValueError):
                    mp.check_mirror({'mirror': 'x'}, entry, asset)


class TempSymbolMirrorTest(unittest.TestCase):
    """真实临时 SVG:最小符号,登记绑定文件字节与字面量端口契约。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.asset = os.path.join(tmp.name, 'mini-pump.svg')
        with open(self.asset, 'w', encoding='utf-8', newline='') as handle:
            handle.write(MINIMAL_SYMBOL_SVG)

    def _component(self):
        component = {
            'component_type': 'mini_pump',
            'ports': [
                {'id': 'suction', 'svg_element_id': 'port-suction',
                 'medium': 'hydraulic', 'role': 'suction',
                 'flow_capability': 'in', 'anchor_direction': 'left'},
                {'id': 'pressure_out', 'svg_element_id': 'port-pressure-out',
                 'medium': 'hydraulic', 'role': 'pressure',
                 'flow_capability': 'out', 'anchor_direction': 'right'},
            ],
            'mirror_safe': True,
            'layout': {'allowed_rotations_deg': [0, 90, 180, 270],
                       'allow_mirror': True},
        }
        component['mirror_registration'] = {
            'axes': ['x'],
            'asset_sha256': _file_sha256(self.asset),
            'ports_sha256': _ports_sha256(component['component_type'],
                                          component['ports']),
        }
        return component

    def test_registered_mirror_passes_on_temp_symbol(self):
        self.assertEqual(
            mp.check_mirror({'mirror': 'x'}, self._component(), self.asset),
            'x')

    def test_source_edit_invalidates_registration(self):
        component = self._component()
        with open(self.asset, 'a', encoding='utf-8') as handle:
            handle.write('<!-- post-approval edit -->\n')
        with self.assertRaises(ValueError) as ctx:
            mp.check_mirror({'mirror': 'x'}, component, self.asset)
        self.assertIn('失效', str(ctx.exception))

    def test_port_contract_edit_invalidates_registration(self):
        component = self._component()
        component['ports'][1]['anchor_direction'] = 'up'
        with self.assertRaises(ValueError):
            mp.check_mirror({'mirror': 'x'}, component, self.asset)


class MirrorTransformChainTest(unittest.TestCase):
    """镜像段插在 rotate 之后、scale(k) 之前(字符串序)的落位与次序。"""

    # 渲染器 place() 既有 90° 锚向表,字面量拷贝,只组合不重算。
    ROT90_ANCHOR = {'left': 'up', 'up': 'right',
                    'right': 'down', 'down': 'left'}

    def _chain(self, mirror, rot=90, x=100.0, y=200.0, k=1.0,
               vx=0.0, vy=0.0, W=80.0, H=80.0):
        comp = {0: (0.0, 0.0), 90: (H, 0.0),
                180: (W, H), 270: (0.0, W)}[rot]
        segment = mp.mirror_svg_transform(W, H, mirror)
        # 条件拼接:空串不带分隔空格(无镜像链与现网渲染逐字节一致),
        # 非空段后补一个空格再接 scale(k)。
        spacer = segment + ' ' if segment else ''
        return ('translate(%g,%g) translate(%g,%g) rotate(%d) %sscale(%g) '
                'translate(%g,%g)'
                % (x, y, comp[0], comp[1], rot, spacer, k, -vx, -vy))

    def _at(self, chain, px, py):
        return sg.point(sg.transform(chain), (px, py))

    def test_no_mirror_chain_matches_renderer_bytes(self):
        # 插入点在无镜像时产出空串,整链与现网 symbols() 逐字节一致。
        current = ('translate(100,200) translate(80,0) rotate(90) scale(1) '
                   'translate(-0,-0)')
        self.assertEqual(self._chain(None), current)

    def test_mirror_segment_sits_between_rotate_and_scale(self):
        self.assertEqual(
            self._chain('x'),
            'translate(100,200) translate(80,0) rotate(90) '
            'translate(80,0) scale(-1,1) scale(1) translate(-0,-0)')

    def test_mirror_precedes_rotation_in_application_order(self):
        # 本地盒左中点 (0,40):无镜像 rot90 -> (140,200);
        # 先 x 镜像到右中点 (80,40) 再 rot90 -> (140,280)。
        base = self._at(self._chain(None), 0.0, 40.0)
        self.assertAlmostEqual(base[0], 140.0, places=6)
        self.assertAlmostEqual(base[1], 200.0, places=6)
        mirrored = self._at(self._chain('x'), 0.0, 40.0)
        self.assertAlmostEqual(mirrored[0], 140.0, places=6)
        self.assertAlmostEqual(mirrored[1], 280.0, places=6)

    def test_nonzero_viewbox_origin_and_scale(self):
        # viewBox "20 10 80 80",k=0.5 -> 盒 40x40。端口原始 (20,50)
        # 归零缩放后 (0,20);x 镜像 -> (40,20);rot0 落位 (100,200)
        # -> (140,220)。
        chain = self._chain('x', rot=0, k=0.5, vx=20.0, vy=10.0,
                            W=40.0, H=40.0)
        self.assertEqual(self._at(chain, 20.0, 50.0), (140.0, 220.0))
        # 顶边原始 (20,10) -> (0,0) -> y 镜像 -> (0,40) -> (100,240)。
        chain = self._chain('y', rot=0, k=0.5, vx=20.0, vy=10.0,
                            W=40.0, H=40.0)
        self.assertEqual(self._at(chain, 20.0, 10.0), (100.0, 240.0))

    def test_anchor_mirror_then_rotation_is_hand_derived(self):
        def anchored(anchor, mirror):
            return self.ROT90_ANCHOR[mp.mirror_anchor(anchor, mirror)]

        # 手算:先 x 镜像(left/right 互换),再 90° 旋转。
        self.assertEqual(anchored('left', 'x'), 'down')
        self.assertEqual(anchored('right', 'x'), 'up')
        self.assertEqual(anchored('up', 'x'), 'right')
        self.assertEqual(anchored('down', 'x'), 'left')


if __name__ == '__main__':
    unittest.main()
