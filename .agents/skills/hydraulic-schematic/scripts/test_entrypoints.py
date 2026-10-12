"""Current L0 entry regression; no dependence on files outside this skill."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from ruamel.yaml import YAML

import layout_engine as engine

SKILL = Path(__file__).resolve().parents[1]
CATALOG = SKILL / 'assets/component-library/component-catalog.json'
FIXTURE = SKILL / 'assets/fixtures/l0-current'


def make_render_workspace(root, fixture):
    """Copy templates before running, using only packaged catalog/symbol assets."""
    work = root / 'run'
    work.mkdir()
    for name in ('layout_contract.py', 'assembly_checks.py', 'render_l0_sheet.py', 'preflight.py', 'validate_sheet.py',
                 'topology_confirm.py', 'endpoint_usage.py', 'proofreading_evidence.py',
                 'browser_evidence.py', 'lead_geometry.py', 'stroke_checks.py', 'text_checks.py', 'svg_paint.py',
                 'sheet_geometry.py', 'endpoint_checks.py', 'topology_reconciliation.py', 'layout_clearance.py', 'junction_semantics.py',
                 'sheet_version.py', 'sheet_diff.py', 'readback_review.py'):
        shutil.copy2(SKILL / 'scripts' / name, work / name)
    shutil.copytree(SKILL / 'assets/contracts', root / 'assets/contracts')
    shutil.copytree(CATALOG.parent, work / 'symbols')
    shutil.copy2(CATALOG, work / CATALOG.name)
    for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
        shutil.copy2(fixture / name, work / name)
    # Catalog-relative bare asset names are supported by assembly seeds too.
    for node in json.loads((work / '1#系统.layout.json').read_text())['nodes'].values():
        ref = node.get('symbol', '')
        if ref and Path(ref).name == ref and (CATALOG.parent / ref).is_file():
            shutil.copy2(CATALOG.parent / ref, work / ref)
    return work


class LayoutEntrypoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.intent = engine.load_yaml(FIXTURE / '1#系统.intent.yaml')
        cls.catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
        cls.ref = json.loads((FIXTURE / '1#系统.layout.json').read_text(encoding='utf-8'))

    def test_current_refuel_type_is_placed_without_changing_topology(self):
        intent = copy.deepcopy(self.intent)
        layout, structure = engine.rules(intent, self.catalog, engine.P, self.ref)
        self.assertEqual(intent, self.intent)
        self.assertEqual(set(layout['nodes']), set(intent['parts']))
        self.assertEqual(layout['nodes']['CV-002']['symbol'], 'symbols/check-valve.svg')
        self.assertIn('CV-002', structure['rows']['refuel'])
        layout, report = engine.guard(layout, structure, engine.P)
        self.assertIn('zero_drift', report)

    def test_no_reference_labels_allow_renderer_to_prepare_all_nodes(self):
        # Remove refuel solely to isolate the pre-existing missing-label bug.
        intent = copy.deepcopy(self.intent)
        del intent['parts']['CV-002']
        intent['paths'] = [p for p in intent['paths'] if 'CV-002' not in p]
        layout, _ = engine.rules(intent, self.catalog, engine.P)
        self.assertEqual(set(layout['labels']), set(intent['parts']))
        self.assertTrue(all(layout['labels'].values()))
        with tempfile.TemporaryDirectory(prefix='l0-entry-renderer-') as directory:
            target = Path(directory) / 'render_l0_sheet.py'
            shutil.copy2(SKILL / 'scripts/render_l0_sheet.py', target)
            spec = importlib.util.spec_from_file_location('entry_renderer', target)
            renderer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(renderer)
            sheet = renderer.Sheet(intent, layout, self.catalog,
                                   cat_dir=str(CATALOG.parent))
            sheet.place()
            sheet.build_textboxes()

    def test_partial_reference_labels_keep_defaults_for_other_nodes(self):
        layout, _ = engine.rules(self.intent, self.catalog, engine.P,
                                 {'labels': {'TANK-001': 'Custom reservoir'}})
        self.assertEqual(layout['labels']['TANK-001'], 'Custom reservoir')
        self.assertEqual(set(layout['labels']), set(self.intent['parts']))

    def test_unknown_and_unregistered_types_fail_with_actionable_message(self):
        for registered in (False, True):
            with self.subTest(registered=registered):
                intent, cat = copy.deepcopy(self.intent), copy.deepcopy(self.catalog)
                intent['parts']['NEW-001'] = 'future_component'
                if registered:
                    cat['components'].append({'component_type': 'future_component', 'ports': []})
                with self.assertRaisesRegex(SystemExit, 'NEW-001.*future_component'):
                    engine.rules(intent, cat, engine.P)

    def test_unsupported_refuel_connection_is_not_guessed(self):
        intent = copy.deepcopy(self.intent)
        intent['paths'] = [p for p in intent['paths'] if 'CV-002' not in p]
        intent['paths'].append(['@USERR', 'CV-002.inlet'])
        with self.assertRaisesRegex(SystemExit, '未布元件.*CV-002'):
            engine.rules(intent, self.catalog, engine.P)

    def run_script(self, path, work, arguments=(), expected=0):
        result = subprocess.run([sys.executable, str(path), *map(str, arguments)],
                                cwd=work, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def test_current_fixture_cli_preflight_and_rule_layout(self):
        with tempfile.TemporaryDirectory(prefix='l0-entry-cli-') as directory:
            work = make_render_workspace(Path(directory), FIXTURE)
            output = work / '1#系统.layout.json'
            self.run_script(work / 'preflight.py', work,
                            ['1#系统.intent.yaml', '--catalog', 'component-catalog.json'])
            self.run_script(SKILL / 'scripts/layout_engine.py', work,
                            [work / '1#系统.intent.yaml', CATALOG, '-', '-o', output])
            layout = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(len(layout['nodes']), 23)
            self.assertEqual(len(layout['labels']), 23)
            self.run_script(work / 'render_l0_sheet.py', work)
            self.assertTrue((work / '1#系统原理图.svg').is_file())

    def test_current_seed_renders_and_retains_geometry_failure_gate(self):
        with tempfile.TemporaryDirectory(prefix='l0-current-seed-') as directory:
            work = make_render_workspace(Path(directory), FIXTURE)
            self.run_script(work / 'render_l0_sheet.py', work)
            self.run_script(work / 'validate_sheet.py', work, expected=1)
            report = json.loads((work / 'validation-report.json').read_text(encoding='utf-8'))
            failures = {c['id'] for c in report['checks'] if c['result'] == 'fail'}
            # 短净距出桩修复已消除原 V17；此未修正种子仍有气侧穿本体，
            # 且 V3/V13 独立检查会抓住同一支路原先漏检的反向折返。
            # V19 also retains the documented B1 zero-crossing gate: the real
            # PRESS/RET crossing at root (970,368) counts even with its bridge.
            self.assertEqual(failures, {'V2', 'V3', 'V10', 'V13', 'V14', 'V19'})
            self.assertTrue(any(c['id'] == 'V13' and '自身折返' in c['detail']
                                and 'ln-sense' in c['detail'] for c in report['checks']))
            self.assertEqual(report['visual_review'], 'pending')

    def test_small_seed_passes_preflight_render_and_geometry(self):
        with tempfile.TemporaryDirectory(prefix='l0-small-seed-') as directory:
            fixture = SKILL / 'assets/fixtures/l0-small-seed'
            work = make_render_workspace(Path(directory), fixture)
            result = self.run_script(work / 'preflight.py', work,
                                     ['1#系统.intent.yaml', '--catalog', 'component-catalog.json'])
            self.assertNotIn('W-SHAPE', result.stdout)
            self.run_script(work / 'render_l0_sheet.py', work)
            self.run_script(work / 'validate_sheet.py', work)
            report = json.loads((work / 'validation-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['fail_count'], 0)
            # Geometry success does not certify the perceptual readback stage.
            self.assertEqual(report['visual_review'], 'pending')

    def test_in_place_validation_uses_catalog_symbols_without_local_copies(self):
        with tempfile.TemporaryDirectory(prefix='l0-catalog-symbols-') as directory:
            work = Path(directory)
            fixture = SKILL / 'assets/fixtures/l0-small-seed'
            for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
                shutil.copy2(fixture / name, work / name)
            self.run_script(SKILL / 'scripts/render_l0_sheet.py', work, [work])
            self.run_script(SKILL / 'scripts/validate_sheet.py', work, [work])
            report = json.loads((work / 'validation-report.json').read_text(encoding='utf-8'))
            self.assertEqual(report['geometry']['nodes']['EDP-001']['ports']['pressure_out']['position'],
                             [650.0, 530.0])
            self.assertEqual(report['artifacts']['files']['catalog']['path'], str(CATALOG))
            for key, artifact in report['artifacts']['files'].items():
                if key.startswith('symbol:'):
                    self.assertEqual(Path(artifact['path']).parent, CATALOG.parent)
            self.run_script(SKILL / 'scripts/proofreading_evidence.py', work, ['verify', work])


class FootprintRegistration45(unittest.TestCase):
    """#45 清单外新增类型的足迹登记口径（2026-10-12）。

    独立事实来源 = 实际符号 SVG（viewBox 与 connection-points 实读）与 skill 册
    catalog；接缝 = layout_engine.py CLI 公开接口——真实 intent/catalog 文件进出、
    守门随 CLI 实际执行、以输出 layout 节点的 w/h/symbol 对账 SVG 事实；不断言
    引擎内部表。eco_bottle（无符号/无目录）与 quick_disconnect_coupling 接通位
    （符号无端口组，B-2 挂账）事实不足不登记，CLI 须按类型逐条点名 fail-closed，
    不得 KeyError。
    """

    @classmethod
    def setUpClass(cls):
        cls.intent = engine.load_yaml(FIXTURE / '1#系统.intent.yaml')
        cls.catalog = json.loads(CATALOG.read_text(encoding='utf-8'))

    def symbol_facts(self, name):
        """实读符号文件：viewBox 尺寸 + connection-points 端口组事实。"""
        root = ET.parse(CATALOG.parent / name).getroot()
        _vx, _vy, w, h = (float(v) for v in
                          root.get('viewBox').replace(',', ' ').split())
        ports = {}
        for group in root.iter():
            if group.get('id') != 'connection-points':
                continue
            for circle in group:
                ports[circle.get('data-port-id')] = dict(
                    element_id=circle.get('id'),
                    y=float(circle.get('cy')),
                    medium=circle.get('data-medium'),
                    role=circle.get('data-port-role'),
                    flow=circle.get('data-flow-capability'),
                    anchor=circle.get('data-anchor-direction'))
        return w, h, ports

    def catalog_entry(self, component_type):
        return next(c for c in self.catalog['components']
                    if c['component_type'] == component_type)

    def run_cli(self, intent_path, output, guard_report, expected=0):
        """真实执行 layout_engine.py CLI（含 guard），返回子进程结果。"""
        result = subprocess.run(
            [sys.executable, str(SKILL / 'scripts/layout_engine.py'),
             str(intent_path), str(CATALOG), '-', '-o', str(output),
             '--guard-report', str(guard_report)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def write_intent(self, directory, intent):
        source = Path(directory) / '1#系统.intent.yaml'
        yaml = YAML(typ='safe', pure=True)
        with open(source, 'w', encoding='utf-8') as f:
            yaml.dump(intent, f)
        return source

    def test_refuel_catalog_entry_matches_symbol_facts(self):
        w, h, ports = self.symbol_facts('check-valve.svg')
        self.assertEqual((w, h), (80.0, 80.0))
        entry = self.catalog_entry('check_valve_refuel')
        self.assertEqual(Path(entry['symbol']['asset']).name, 'check-valve.svg')
        self.assertEqual({'inlet', 'outlet'}, set(ports))
        # 变体 role=return 是 2026-09-07 用户签认口径（共用符号先例，登记在册），
        # 与符号通用 pressure 端口注记的分歧不由此测试改写；端口对集合仍须一致。
        self.assertEqual({p['id'] for p in entry['ports']}, set(ports))
        self.assertEqual(entry['main_path'], {'in': 'inlet', 'out': 'outlet'})
        self.assertFalse(entry['layout']['allow_mirror'])

    def test_cli_places_spring_valve_and_reports_nodes_matching_symbol_facts(self):
        """冻结 l0-current 插入弹簧阀走真实 CLI：输出节点 w/h/symbol 对账 SVG 实读。

        不查引擎内部足迹表；登记是否正确由 CLI 落盘的 layout 节点与符号
        viewBox 事实对账体现，且 guard 随 CLI 实际执行（--guard-report 落盘）。
        """
        intent = copy.deepcopy(self.intent)
        intent['parts']['X-001'] = 'check_valve_spring'
        chain = next(p for p in intent['paths'] if 'FSOV-001' in p)
        chain.insert(chain.index('FSOV-001') + 1, 'X-001')
        spring_w, spring_h, _ports = self.symbol_facts('check-valve-spring.svg')
        refuel_w, refuel_h, _rp = self.symbol_facts('check-valve.svg')
        with tempfile.TemporaryDirectory(prefix='issue45-cli-place-') as directory:
            work = Path(directory)
            source = self.write_intent(work, intent)
            output, report_p = work / 'out.layout.json', work / 'guard.json'
            self.run_cli(source, output, report_p)
            layout = json.loads(output.read_text(encoding='utf-8'))
            self.assertEqual(len(layout['nodes']), 24)
            node = layout['nodes']['X-001']
            self.assertEqual((node['w'], node['h']), (spring_w, spring_h))
            self.assertEqual(Path(node['symbol']).name, 'check-valve-spring.svg')
            # 既有 CV-002（check_valve_refuel）经同一 CLI 输出一并对账。
            cv = layout['nodes']['CV-002']
            self.assertEqual((cv['w'], cv['h']), (refuel_w, refuel_h))
            self.assertEqual(Path(cv['symbol']).name, 'check-valve.svg')
            report = json.loads(report_p.read_text(encoding='utf-8'))
            self.assertIn('zero_drift', report)
            self.assertIn('constraints', report)

    def test_spring_valve_catalog_entry_matches_symbol_port_group(self):
        _w, _h, ports = self.symbol_facts('check-valve-spring.svg')
        entry = self.catalog_entry('check_valve_spring')
        self.assertEqual(entry['connection_role'], 'inline')
        self.assertEqual(entry['main_path'], {'in': 'inlet', 'out': 'outlet'})
        self.assertFalse(entry['layout']['allow_mirror'])
        declared = {p['id']: p for p in entry['ports']}
        self.assertEqual(set(declared), set(ports))
        for pid, port in declared.items():
            fact = ports[pid]
            self.assertEqual(port['svg_element_id'], fact['element_id'])
            self.assertEqual(port['medium'], fact['medium'])
            self.assertEqual(port['role'], fact['role'])
            self.assertEqual(port['flow_capability'], fact['flow'])
            self.assertEqual(port['anchor_direction'], fact['anchor'])

    def test_cli_reports_unregistered_types_fail_closed_with_actionable_list(self):
        # 事实缺口未登记前，CLI 门禁按类型逐条点名；不 KeyError、不猜拓扑。
        intent = copy.deepcopy(self.intent)
        intent['parts']['ECO-001'] = 'eco_bottle'
        for qd in ('QD-001', 'QD-002', 'QD-003'):
            intent['parts'][qd] = 'quick_disconnect_coupling'
        with tempfile.TemporaryDirectory(prefix='issue45-cli-gate-') as directory:
            work = Path(directory)
            source = self.write_intent(work, intent)
            result = self.run_cli(source, work / 'out.layout.json',
                                  work / 'guard.json', expected=1)
            self.assertIn('类型未登记到 catalog', result.stderr)
            for inst, typ in (('ECO-001', 'eco_bottle'),
                              ('QD-001', 'quick_disconnect_coupling'),
                              ('QD-002', 'quick_disconnect_coupling'),
                              ('QD-003', 'quick_disconnect_coupling')):
                self.assertIn('%s (%s): 类型未登记到 catalog' % (inst, typ),
                              result.stderr)
            self.assertNotIn('KeyError', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
