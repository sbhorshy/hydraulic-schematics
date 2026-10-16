"""check_library --json: stable machine summary, text mode unchanged (#94)."""
import glob
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = str(HERE / 'check_library.py')
REAL_LIB = HERE.parent / 'assets' / 'component-library'

GOOD_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
            '<g id="connection-points"><circle data-port-id="in"/><circle data-port-id="out"/></g></svg>')
NO_PORTS_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"/>'


def run(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True)


def sandbox(extra_files=None, components=None):
    tmp = tempfile.TemporaryDirectory(prefix='check-library-json-')
    lib = Path(tmp.name)
    (lib / 'a.svg').write_text(GOOD_SVG)
    (lib / 'b.svg').write_text(GOOD_SVG)
    # 白名单内的无端口组符号：计入 svg_files，但不计入 port_groups
    (lib / 'quick-disconnect-coupling.svg').write_text(NO_PORTS_SVG)
    for name, text in (extra_files or {}).items():
        (lib / name).write_text(text)
    comps = components if components is not None else [
        {'component_type': 't1', 'symbol': {'asset': 'a.svg'}, 'ports': [{'id': 'in'}]},
        {'component_type': 't2', 'symbol': {'asset': 'a.svg'}, 'ports': [{'id': 'out'}]},  # 共用 a.svg
    ]
    (lib / 'component-catalog.json').write_text(json.dumps({'components': comps}))
    return tmp, lib


class JsonSummary(unittest.TestCase):
    def test_counts_distinguish_files_port_groups_whitelist_and_catalog(self):
        tmp, lib = sandbox()
        self.addCleanup(tmp.cleanup)
        result = run('--lib', str(lib), '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['svg_files'], 3)
        self.assertEqual(report['port_groups'], 2)
        self.assertEqual(report['whitelisted'], ['quick-disconnect-coupling.svg'])
        self.assertEqual(report['catalog_components'], 2)
        self.assertEqual(report['catalog_assets'], 1)           # t1、t2 共用 a.svg
        self.assertEqual(report['unreferenced_svgs'], ['b.svg', 'quick-disconnect-coupling.svg'])
        self.assertEqual((report['ok'], report['fails']), (True, []))

    def test_failure_is_reported_and_exit_code_is_one(self):
        tmp, lib = sandbox({'broken.svg': 'not xml'})
        self.addCleanup(tmp.cleanup)
        result = run('--lib', str(lib), '--json')
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertFalse(report['ok'])
        self.assertTrue(any('broken.svg' in f for f in report['fails']))

    def test_stdout_is_only_json_in_json_mode(self):
        tmp, lib = sandbox()
        self.addCleanup(tmp.cleanup)
        json.loads(run('--lib', str(lib), '--json').stdout)  # 抛异常即失败

    def test_missing_catalog_is_a_failure_with_null_catalog_counts(self):
        tmp, lib = sandbox()
        self.addCleanup(tmp.cleanup)
        os.remove(lib / 'component-catalog.json')
        result = run('--lib', str(lib), '--json')
        self.assertEqual(result.returncode, 1)
        report = json.loads(result.stdout)
        self.assertIsNone(report['catalog_components'])
        self.assertIsNone(report['catalog_assets'])


class TextModeUnchanged(unittest.TestCase):
    def test_text_output_and_exit_code_without_flag(self):
        tmp, lib = sandbox()
        self.addCleanup(tmp.cleanup)
        result = run('--lib', str(lib))
        self.assertEqual(result.returncode, 0)
        self.assertIn('== check_library ==', result.stdout)
        self.assertIn('库: %s（SVG 3，端口组 2，白名单 1）' % lib, result.stdout)
        self.assertIn('结论: 通过（INFO 1 / FAIL 0）', result.stdout)
        with self.assertRaises(ValueError):
            json.loads(result.stdout)


class RealLibrary(unittest.TestCase):
    def test_json_counts_match_the_files_on_disk(self):
        report = json.loads(run('--json').stdout)
        self.assertEqual(report['svg_files'], len(glob.glob(str(REAL_LIB / '*.svg'))))
        catalog = json.loads((REAL_LIB / 'component-catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(report['catalog_components'], len(catalog['components']))
        for name in report['unreferenced_svgs']:
            self.assertTrue((REAL_LIB / name).is_file(), name)


if __name__ == '__main__':
    unittest.main()
