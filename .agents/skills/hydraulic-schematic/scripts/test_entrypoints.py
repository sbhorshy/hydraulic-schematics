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

import layout_engine as engine

SKILL = Path(__file__).resolve().parents[1]
CATALOG = SKILL / 'assets/component-library/component-catalog.json'
FIXTURE = SKILL / 'assets/fixtures/l0-current'


def make_render_workspace(root, fixture):
    """Copy templates before running, using only packaged catalog/symbol assets."""
    work = root / 'run'
    work.mkdir()
    for name in ('render_l0_sheet.py', 'preflight.py', 'validate_sheet.py',
                 'topology_confirm.py', 'sheet_geometry.py', 'endpoint_checks.py'):
        shutil.copy2(SKILL / 'scripts' / name, work / name)
    shutil.copytree(SKILL / 'assets/contracts', root / 'assets/contracts')
    shutil.copytree(CATALOG.parent, work / 'symbols')
    shutil.copy2(CATALOG, work / CATALOG.name)
    for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
        shutil.copy2(fixture / name, work / name)
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
            self.assertEqual(failures, {'V2', 'V3', 'V13'})
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


if __name__ == '__main__':
    unittest.main()
