"""Environment doctor: reports every missing dependency in one pass, exit 0/1."""
import io
import json
import sys
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch
import doctor as D

REQUIRED = {p.module for p in D.PACKAGES if not p.optional}
OPTIONAL = {p.module for p in D.PACKAGES if p.optional}
ALL_MODULES = REQUIRED | OPTIONAL


def pinned_version(dist):
    return D.read_requirements()[dist][2:]


class DoctorTests(unittest.TestCase):
    def run_main(self, argv, missing_modules=(), rasterizer=('chrome', '/bin/chrome'),
                 versions=pinned_version):
        out = io.StringIO()
        if rasterizer:
            renderer = patch.object(D, 'find_rasterizer', return_value=rasterizer)
        else:
            renderer = patch.object(D, 'find_rasterizer', side_effect=RuntimeError('缺少可用的本机 Inkscape/Chrome'))
        with patch.object(D, 'module_present', side_effect=lambda n: n not in missing_modules), \
                patch.object(D, 'installed_version', side_effect=versions), renderer, redirect_stdout(out):
            code = D.main(argv)
        return code, out.getvalue()

    def test_all_present_exits_zero(self):
        code, _ = self.run_main([])
        self.assertEqual(code, 0)

    def test_all_missing_reported_in_one_pass(self):
        code, text = self.run_main(['--json'], missing_modules=ALL_MODULES, rasterizer=None)
        self.assertEqual(code, 1)
        report = json.loads(text)
        self.assertEqual({m['module'] for m in report['missing']}, REQUIRED | {'rasterizer'})
        self.assertEqual({m['module'] for m in report['optional_missing']}, OPTIONAL)
        self.assertFalse(report['ok'])

    def test_single_missing_required_package_fails(self):
        code, text = self.run_main(['--json'], missing_modules={'kiwisolver'})
        self.assertEqual(code, 1)
        self.assertEqual([m['module'] for m in json.loads(text)['missing']], ['kiwisolver'])

    def test_missing_optional_package_does_not_fail(self):
        code, text = self.run_main(['--json'], missing_modules={'jsonschema'})
        self.assertEqual(code, 0)
        report = json.loads(text)
        self.assertTrue(report['ok'])
        self.assertEqual([m['module'] for m in report['optional_missing']], ['jsonschema'])

    def test_missing_rasterizer_alone_fails(self):
        code, text = self.run_main(['--json'], rasterizer=None)
        self.assertEqual(code, 1)
        self.assertEqual([m['module'] for m in json.loads(text)['missing']], ['rasterizer'])

    def test_version_differing_from_pin_is_reported_but_not_fatal(self):
        code, text = self.run_main(['--json'], versions=lambda dist: '99.0.0')
        self.assertEqual(code, 0)
        report = json.loads(text)
        self.assertEqual({m['module'] for m in report['version_mismatch']}, ALL_MODULES)
        self.assertEqual(report['version_mismatch'][0]['installed'], '99.0.0')

    def test_uninstalled_version_lookup_is_not_a_mismatch(self):
        code, text = self.run_main(['--json'], versions=lambda dist: None)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text)['version_mismatch'], [])

    def test_text_output_names_every_missing_item_with_quoted_install_hint(self):
        code, text = self.run_main([], missing_modules={'PIL', 'numpy'}, rasterizer=None)
        self.assertEqual(code, 1)
        for needle in ('Pillow', 'numpy', 'Inkscape', '-m pip install -r "'):
            self.assertIn(needle, text)
        self.assertIn(sys.executable, text)

    def test_requirements_file_pins_every_package_exactly(self):
        pins = D.read_requirements()
        self.assertEqual({D.dist_name(m) for m in ALL_MODULES}, set(pins))
        for name, spec in pins.items():
            self.assertTrue(spec.startswith('=='), '%s 未固定版本: %r' % (name, spec))


class RealDetectionTests(unittest.TestCase):
    """These do not patch module_present / find_rasterizer's search."""

    def test_module_present_real_lookups(self):
        self.assertTrue(D.module_present('json'))
        self.assertFalse(D.module_present('definitely_not_a_module_xyz'))

    def test_dotted_name_with_absent_parent_is_false_not_an_error(self):
        self.assertFalse(D.module_present('definitely_not_a_pkg_xyz.sub'))

    def test_find_rasterizer_falls_back_when_renderer_import_breaks(self):
        broken = {'rasterize_sheet': None}  # None in sys.modules makes `import` raise ImportError
        with patch.dict(sys.modules, broken), \
                patch.object(D.shutil, 'which', side_effect=lambda n: '/bin/chromium' if n == 'chromium' else None):
            self.assertEqual(D.find_rasterizer(), ('chrome', '/bin/chromium'))

    def test_fallback_reports_missing_when_nothing_found(self):
        with patch.object(D.shutil, 'which', return_value=None), \
                patch.object(D.os.path, 'isfile', return_value=False):
            with self.assertRaisesRegex(RuntimeError, '缺少'):
                D._fallback_rasterizer()

    def test_fallback_checks_windows_inkscape_paths(self):
        with patch.object(D.shutil, 'which', return_value=None), \
                patch.object(D.os, 'name', 'nt'), \
                patch.object(D.os.path, 'isfile', side_effect=lambda p: p.startswith('C:')):
            kind, exe = D._fallback_rasterizer()
        self.assertEqual(kind, 'inkscape')
        self.assertTrue(exe.startswith('C:'))

    def test_find_rasterizer_survives_non_importerror_failure(self):
        class Boom:
            def __getattr__(self, name):
                raise RuntimeError('module init exploded')
        with patch.dict(sys.modules, {'rasterize_sheet': Boom()}), \
                patch.object(D.shutil, 'which', side_effect=lambda n: '/bin/google-chrome' if n == 'google-chrome' else None):
            self.assertEqual(D.find_rasterizer(), ('chrome', '/bin/google-chrome'))


if __name__ == '__main__':
    unittest.main()
