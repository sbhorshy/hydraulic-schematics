# -*- coding: utf-8 -*-
"""跳线许可登记与 B1 放行门禁（#23 定案 2026-10-12）。

真实 CLI 负例复用 test_junction_semantics 的 fixture 与交叉/桥注入手法
（make_render_workspace + 直接编辑渲染后 SVG）：未申请政策的普通 fixture
即使桥画得完全正确，B1 仍按 allowance 0 失败；显式声明未登记 id、或登记
id 但工作区 intent 字节与登记摘要不符（错 intent），都硬失败而非静默按 0；
布局写数字预算键一律拒绝。单元接缝 resolve_policy 允许测试自建登记表，
但生产入口 check_bridge_policy 没有 registry 参数——validate_sheet 的
放行只能来自生产登记表，预算无法经生产接口注入。
"""
import hashlib
import inspect
import json
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from test_entrypoints import SKILL, make_render_workspace

import bridge_allowance as BA

POLICY_ID = 'current-1-verified-single-bridge-20261012'


def _file_sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(65536), b''):
            digest.update(chunk)
    return digest.hexdigest()


class RegistryResolutionTest(unittest.TestCase):
    """纯登记裁决接缝：None 默认 0；未知 id/错摘要/坏登记形态硬失败。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='bridge-registry-')
        self.addCleanup(self.tmp.cleanup)
        self.intent = Path(self.tmp.name) / '1#系统.intent.yaml'
        self.intent.write_bytes('fixture-intent-bytes\n'.encode('utf-8'))
        self.digest = _file_sha256(self.intent)
        self.registry = {POLICY_ID: {
            'intent_path': 'fixtures/1#系统.intent.yaml',
            'intent_sha256': self.digest,
            'maximum_verified_bridges': 2,
            'decision': 'test registry entry',
            'evidence': 'test',
        }}

    def test_no_policy_request_defaults_to_zero_without_reading_intent(self):
        # 未声明 = 未申请：任意旧布局（连 intent 文件都不存在）都按 0 走。
        missing = Path(self.tmp.name) / 'no-such-intent.yaml'
        self.assertEqual(
            BA.check_bridge_policy({'layout_version': 'legacy'}, missing),
            {'policy_id': None, 'allowance': 0})

    def test_none_policy_id_resolves_to_none(self):
        self.assertIsNone(
            BA.resolve_policy(None, self.digest, registry=self.registry))

    def test_matching_digest_grants_registered_allowance(self):
        entry = BA.resolve_policy(POLICY_ID, self.digest, registry=self.registry)
        self.assertEqual(entry['maximum_verified_bridges'], 2)
        entry['maximum_verified_bridges'] = 99
        self.assertEqual(
            self.registry[POLICY_ID]['maximum_verified_bridges'], 2,
            'resolve_policy 返回副本，改副本不得改登记表')

    def test_unknown_policy_id_is_a_hard_failure(self):
        with self.assertRaises(ValueError) as ctx:
            BA.resolve_policy('made-up-id', self.digest, registry=self.registry)
        message = str(ctx.exception)
        self.assertIn('made-up-id', message)
        self.assertIn('未登记', message)
        self.assertIn(POLICY_ID, message)

    def test_stale_intent_digest_hard_fails_with_both_digests(self):
        other = '0' * 64
        with self.assertRaises(ValueError) as ctx:
            BA.resolve_policy(POLICY_ID, other, registry=self.registry)
        message = str(ctx.exception)
        self.assertIn('失效', message)
        self.assertIn('sha256', message)
        self.assertIn(other, message)
        self.assertIn(self.digest, message)

    def test_bad_policy_id_shapes_are_rejected(self):
        for bad in (1, 0, True, '', ['x'], {'id': 1}):
            with self.subTest(policy_id=bad):
                with self.assertRaises(ValueError):
                    BA.resolve_policy(bad, self.digest, registry=self.registry)

    def test_registry_entry_shape_is_validated(self):
        for mutate in (lambda e: e.__setitem__('maximum_verified_bridges', True),
                       lambda e: e.__setitem__('maximum_verified_bridges', -1),
                       lambda e: e.__setitem__('maximum_verified_bridges', '1'),
                       lambda e: e.__setitem__('maximum_verified_bridges', 1.5),
                       lambda e: e.__setitem__('intent_sha256', 'XYZ'),
                       lambda e: e.__setitem__('intent_sha256', None)):
            registry = {POLICY_ID: dict(self.registry[POLICY_ID])}
            mutate(registry[POLICY_ID])
            with self.subTest(mutate=mutate):
                with self.assertRaises(ValueError):
                    BA.resolve_policy(POLICY_ID, self.digest, registry=registry)

    def test_production_registry_binds_exactly_the_decided_grant(self):
        # #23 定案的生产登记现状：恰好一条政策，放行 1 处；摘要为 64 位
        # 小写十六进制。与真实 1# intent 文件的对账在
        # tests/repository/test_bridge_registration.py（skill 外事实）。
        self.assertEqual(set(BA.PRODUCTION_BRIDGE_POLICIES), {POLICY_ID})
        entry = BA.PRODUCTION_BRIDGE_POLICIES[POLICY_ID]
        self.assertEqual(entry['maximum_verified_bridges'], 1)
        self.assertEqual(entry['intent_path'], '1#系统原理图/1#系统.intent.yaml')
        self.assertRegex(entry['intent_sha256'], r'^[0-9a-f]{64}$')

    def test_production_entrypoint_has_no_registry_injection(self):
        # 生产接口不收 registry：预算只能来自生产登记表，测试接缝仅
        # resolve_policy。
        self.assertNotIn('registry',
                         inspect.signature(BA.check_bridge_policy).parameters)

    def test_layout_numeric_budget_keys_are_rejected(self):
        intent = str(self.intent)
        for key in BA.FORBIDDEN_LAYOUT_KEYS:
            for value in (1, 0, None):
                with self.subTest(key=key, value=value):
                    with self.assertRaises(ValueError) as ctx:
                        BA.check_bridge_policy(
                            {'bridge_policy': POLICY_ID, key: value}, intent)
                    self.assertIn(key, str(ctx.exception))

    def test_non_string_policy_field_is_rejected(self):
        for bad in (1, True, ['x'], 0):
            with self.subTest(bridge_policy=bad):
                with self.assertRaises(ValueError):
                    BA.check_bridge_policy(
                        {'bridge_policy': bad}, str(self.intent))

    def test_production_registry_cannot_be_satisfied_by_arbitrary_bytes(self):
        # 生产入口绑定真实 1# intent：临时内容即使声明了登记 id 也必须
        # 硬失败——生产接口没有自定义登记表通道（fixture 可测性走
        # resolve_policy 的 registry 接缝，见上）。
        with self.assertRaises(ValueError) as ctx:
            BA.check_bridge_policy({'bridge_policy': POLICY_ID},
                                   str(self.intent))
        self.assertIn('失效', str(ctx.exception))


class BridgeAllowanceCLI(unittest.TestCase):
    """真实 CLI 负例：fixture 工作区 + 渲染后 SVG 注入（junction 手法）。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='bridge-cli-')
        self.addCleanup(tmp.cleanup)
        self.work = make_render_workspace(
            Path(tmp.name), SKILL / 'assets/fixtures/l0-small-seed')
        self.svg = self.work / '1#系统原理图.svg'
        p = subprocess.run(
            [sys.executable, str(SKILL / 'scripts/render_l0_sheet.py'),
             str(self.work)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def edit(self, change):
        root = ET.parse(self.svg).getroot()
        change(root)
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root, encoding='unicode'))

    def validate(self):
        p = subprocess.run(
            [sys.executable, str(SKILL / 'scripts/validate_sheet.py'),
             str(self.work)], capture_output=True, text=True)
        self.assertTrue((self.work / 'validation-report.json').exists(),
                        p.stdout + p.stderr)
        report = json.loads(
            (self.work / 'validation-report.json').read_text())
        self.assertEqual(p.returncode, 1 if report['fail_count'] else 0,
                         p.stdout + p.stderr)
        return report

    def b1(self, report):
        return next(item for item in report['composition_budget']['items']
                    if item['id'] == 'B1')

    def v19(self, report):
        return next(e for e in report['evidence'] if e['id'] == 'V19')

    def assert_same_verified_disclosure(self, report):
        # verified_bridges 的两处出口（B1 item 与 V19 evidence）必须同口径：
        # covered 才逐点报数，否则整组 0——不允许一个出口 0、另一个还挂
        # 着未过滤计数（raw 计数只留在 measured/crossings，判定预算不动）。
        b1 = self.b1(report)
        self.assertEqual(self.v19(report)['verified_bridges'],
                         b1['verified_bridges'])
        return b1

    def set_layout(self, **fields):
        path = self.work / '1#系统.layout.json'
        layout = json.loads(path.read_text())
        layout.update(fields)
        path.write_text(json.dumps(layout, ensure_ascii=False))

    def crossing(self, bridge=True):
        # 与 test_junction_semantics.JunctionCLI.crossing 同手法：吸油线
        # 改道在 (770,530) 压力线上留一个真实非连通交叉，压力线按桥拆分。
        def edit(root):
            suction = next(e for e in root.iter()
                           if e.get('data-edge') == 'paths[0][0->1]')
            suction.set('points', '308,530 328,530 328,450 770,450 770,610 '
                                  '550,610 550,530 570,530')
            if bridge:
                group = next(e for e in root.iter() if e.get('id') == 'lines')
                pressure = next(e for e in group
                                if e.get('data-edge') == 'paths[1][0->1]')
                pressure.set('points', '650,530 765,530')
                ET.SubElement(group, pressure.tag, {
                    **pressure.attrib, 'id': 'pressure-tail',
                    'points': '775,530 850,530'})
                arcs = next(e for e in root.iter() if e.get('id') == 'bridges')
                ET.SubElement(arcs, '{http://www.w3.org/2000/svg}path', {
                    'class': 'brg-hi', 'id': 'cross-bridge',
                    'd': 'M765 530 A5 5 0 0 1 775 530',
                    'data-edge': 'paths[1][0->1]',
                    'data-input-anchor': 'paths[1][0->1]'})
        self.edit(edit)

    def two_crossings(self):
        # 同一压力线上两处都按规范拆桥：两处交叉各自"完全验证通过"，
        # 但 allowance 0 → 仍 fail（第二处交叉不因第一处豁免）。
        # 吸油线去程走 y=400、回程走 y=450，两水平段不共线：旧路线去程
        # 与回程同贴 y=450（328→700 与 760→550 重叠），V10/V13/
        # missing_junction 先炸，测不到 B1 本身。两桥 x=700/x=760 与
        # 压力线断桥段（695-705/755-765）一一对应。
        def edit(root):
            suction = next(e for e in root.iter()
                           if e.get('data-edge') == 'paths[0][0->1]')
            suction.set('points', '308,530 328,530 328,400 760,400 760,610 '
                                  '700,610 700,450 550,450 550,530 570,530')
            group = next(e for e in root.iter() if e.get('id') == 'lines')
            pressure = next(e for e in group
                            if e.get('data-edge') == 'paths[1][0->1]')
            pressure.set('points', '650,530 695,530')
            for identifier, points in (('pressure-mid', '705,530 755,530'),
                                       ('pressure-tail', '765,530 850,530')):
                ET.SubElement(group, pressure.tag, {
                    **pressure.attrib, 'id': identifier, 'points': points})
            arcs = next(e for e in root.iter() if e.get('id') == 'bridges')
            for identifier, d in (('cross-bridge-a', 'M695 530 A5 5 0 0 1 705 530'),
                                  ('cross-bridge-b', 'M755 530 A5 5 0 0 1 765 530')):
                ET.SubElement(arcs, '{http://www.w3.org/2000/svg}path', {
                    'class': 'brg-hi', 'id': identifier, 'd': d,
                    'data-edge': 'paths[1][0->1]',
                    'data-input-anchor': 'paths[1][0->1]'})
        self.edit(edit)

    def test_plain_seed_b1_stays_zero_and_unclaimed(self):
        b1 = self.b1(self.validate())
        self.assertEqual(b1['measured'], 0)
        self.assertEqual(b1['status'], 'pass')
        self.assertIsNone(b1['policy'])
        self.assertEqual(b1['allowance'], 0)
        self.assertEqual(b1['verified_bridges'], 0)

    def test_unapproved_fixture_verified_bridge_keeps_b1_fail(self):
        # 未申请政策的普通 fixture：桥完全合规（V4/V14 全空）也只是
        # verified=1，allowance=0 仍 fail——放行只能来自登记。
        self.crossing()
        report = self.validate()
        self.assertFalse([c for c in report['checks']
                          if c['id'] in ('V4', 'V14')])
        b1 = self.assert_same_verified_disclosure(report)
        self.assertEqual(b1['measured'], 1)
        self.assertEqual(b1['verified_bridges'], 1)
        self.assertIsNone(b1['policy'])
        self.assertEqual(b1['allowance'], 0)
        self.assertEqual(b1['status'], 'fail')

    def test_second_verified_crossing_still_fails(self):
        self.two_crossings()
        report = self.validate()
        self.assertFalse([c for c in report['checks']
                          if c['id'] in ('V4', 'V14')], report['checks'])
        b1 = self.assert_same_verified_disclosure(report)
        self.assertEqual(b1['measured'], 2)
        self.assertEqual(b1['verified_bridges'], 2)
        self.assertEqual(b1['allowance'], 0)
        self.assertEqual(b1['status'], 'fail')
        self.assertTrue(any(c['id'] == 'V19' and '交叉 2 处超出放行预算 0'
                            in c['detail'] for c in report['checks']),
                        report['checks'])

    def test_registered_policy_with_wrong_intent_bytes_hard_fails(self):
        # 错 intent：声明的 id 已登记，但工作区 intent 字节与登记摘要不符
        # → 硬失败（fail-closed），绝不静默按 allowance 0 放行通过。
        self.set_layout(bridge_policy=POLICY_ID)
        self.crossing()
        report = self.validate()
        self.assertEqual(report['validation'], 'failed')
        failures = [c for c in report['checks']
                    if c['id'] == 'V19' and c['result'] == 'fail']
        self.assertTrue(any('失效' in c['detail'] and 'sha256' in c['detail']
                            and POLICY_ID in c['detail'] for c in failures),
                        failures)
        b1 = self.b1(report)
        self.assertEqual(b1['status'], 'fail')
        self.assertIn('失效', b1['detail'])

    def test_unknown_policy_id_hard_fails_not_silently_zero(self):
        self.set_layout(bridge_policy='made-up-policy-id')
        self.crossing()
        report = self.validate()
        self.assertEqual(report['validation'], 'failed')
        failures = [c for c in report['checks']
                    if c['id'] == 'V19' and c['result'] == 'fail']
        self.assertTrue(any('made-up-policy-id' in c['detail']
                            and '未登记' in c['detail'] for c in failures),
                        failures)
        b1 = self.b1(report)
        self.assertEqual(b1['status'], 'fail')
        self.assertIn('未登记', b1['detail'])

    def test_layout_numeric_budget_keys_hard_fail(self):
        # 布局写数字预算 = 自行扩预算，出现即硬失败（值是什么都一样）。
        for key in ('bridge_allowance', 'b1_budget'):
            with self.subTest(key=key):
                self.set_layout(**{key: 1})
                self.crossing()
                report = self.validate()
                self.assertEqual(report['validation'], 'failed')
                self.assertTrue(any(
                    c['id'] == 'V19' and key in c['detail']
                    for c in report['checks']), report['checks'])
                b1 = self.b1(report)
                self.assertEqual(b1['status'], 'fail')
                self.assertEqual(b1['allowance'], 0)

    def test_missing_bridge_and_false_dot_leave_crossing_unverified(self):
        # 无桥 + 假接点：V4/V14 findings 非空，verified_bridges=0，
        # B1 fail——证据缺口不能按"经验证跳线"放行。
        self.crossing(False)
        def dot(root):
            group = next(e for e in root.iter() if e.get('id') == 'junctions')
            ET.SubElement(group, '{http://www.w3.org/2000/svg}circle', {
                'class': 'jn', 'cx': '770', 'cy': '530', 'r': '3',
                'data-edges': 'paths[1][0->1]', 'data-network': 'pressure'})
        self.edit(dot)
        report = self.validate()
        kinds = {c.get('kind') for c in report['checks']
                 if c['id'] in ('V4', 'V14')}
        self.assertIn('false_junction', kinds)
        self.assertIn('missing_bridge', kinds)
        b1 = self.assert_same_verified_disclosure(report)
        self.assertEqual(b1['measured'], 1)
        self.assertEqual(b1['verified_bridges'], 0)
        self.assertEqual(b1['status'], 'fail')

    def test_wrong_bridge_owner_is_not_a_verified_bridge(self):
        # 错归属：桥存在且居中，但 data-edge 冒领不相接管段 → bridge_gap，
        # verified_bridges 仍 0。
        self.crossing()
        def change(root):
            arc = next(e for e in root.iter()
                       if e.get('id') == 'cross-bridge')
            arc.set('data-edge', 'paths[0][0->1]')
            arc.set('data-input-anchor', 'paths[0][0->1]')
        self.edit(change)
        report = self.validate()
        kinds = {c.get('kind') for c in report['checks'] if c['id'] == 'V14'}
        self.assertIn('bridge_gap', kinds)
        b1 = self.b1(report)
        self.assertEqual(b1['measured'], 1)
        self.assertEqual(b1['verified_bridges'], 0)
        self.assertEqual(b1['status'], 'fail')

    def test_unknown_marker_paint_blocks_b1_and_verified_disclosure(self):
        # 真实 SVG 负例（复现 ../probe-bridge-gate.py 诊断）：交点叠一枚
        # paint 不可判定的 marker——circle.jn 的 fill 是 linearGradient
        # 引用（defs 两端黑色）。junction_semantics 只能记 V4 not_checked
        # （unsupported marker），V14 仍 pass 且无 findings——B1 若只查
        # V14 覆盖就凭单侧证据放行"经验证跳线"。必须 V4/V14 覆盖均
        # pass 才放行，verified_bridges 不得报 1；measured 仍不减。
        self.crossing()
        def marker(root):
            defs = ET.SubElement(root, '{http://www.w3.org/2000/svg}defs')
            gradient = ET.SubElement(
                defs, '{http://www.w3.org/2000/svg}linearGradient',
                {'id': 'audit-gradient'})
            ET.SubElement(gradient, '{http://www.w3.org/2000/svg}stop',
                          {'offset': '0', 'stop-color': 'black'})
            ET.SubElement(gradient, '{http://www.w3.org/2000/svg}stop',
                          {'offset': '1', 'stop-color': 'black'})
            ET.SubElement(root, '{http://www.w3.org/2000/svg}circle', {
                'id': 'audit-unknown-marker', 'class': 'jn',
                'cx': '770', 'cy': '530', 'r': '3',
                'style': 'fill:url(#audit-gradient)'})
        self.edit(marker)
        report = self.validate()
        coverage = {e['id']: e.get('coverage_status')
                    for e in report['evidence'] if e['id'] in ('V4', 'V14')}
        self.assertEqual(coverage.get('V4'), 'not_checked', coverage)
        b1 = self.assert_same_verified_disclosure(report)
        self.assertEqual(b1['measured'], 1)
        self.assertEqual(b1['status'], 'fail')
        self.assertNotEqual(b1['verified_bridges'], 1)
        self.assertEqual(b1['verified_bridges'], 0)

    def test_dashed_bridge_fails_b1_without_verified_disclosure(self):
        # 桥已在位但被画成虚线（stroke-dasharray）：V14 记 dashed_bridge
        # 失败，B1 fail——披露不得仍报 verified_bridges=1（旧实现一边
        # fail 一边报 1，读起来像"桥本身没问题只是超预算"）。连续/
        # 归属逐点核实只是必要条件，V4/V14 任一 findings 存在时整组
        # 按 0 披露；measured 仍是真实交叉数。
        self.crossing()
        def dash(root):
            arc = next(e for e in root.iter()
                       if e.get('id') == 'cross-bridge')
            arc.set('style', (arc.get('style') or '') + ';stroke-dasharray:1 1')
        self.edit(dash)
        report = self.validate()
        kinds = {c.get('kind') for c in report['checks'] if c['id'] == 'V14'}
        self.assertIn('dashed_bridge', kinds)
        b1 = self.assert_same_verified_disclosure(report)
        self.assertEqual(b1['measured'], 1)
        self.assertEqual(b1['status'], 'fail')
        self.assertNotEqual(b1['verified_bridges'], 1)
        self.assertEqual(b1['verified_bridges'], 0)


if __name__ == '__main__':
    unittest.main()
