"""Environment doctor: reports every missing dependency in one pass, exit 0/1."""
import io
import json
from contextlib import redirect_stdout
import unittest
from unittest.mock import patch
import doctor as D

ALL_MODULES = {m for m, _ in D.PACKAGES}


class DoctorTests(unittest.TestCase):
    def run_main(self, argv, missing_modules=(), rasterizer=('chrome', '/bin/chrome')):
        def fake_find_spec(name):
            return None if name in missing_modules else object()
        out = io.StringIO()
        renderer = (patch.object(D, 'find_rasterizer', return_value=rasterizer) if rasterizer
                    else patch.object(D, 'find_rasterizer', side_effect=RuntimeError('缺少可用的本机 Inkscape/Chrome')))
        with patch.object(D, 'module_present', side_effect=lambda n: n not in missing_modules), renderer, redirect_stdout(out):
            code = D.main(argv)
        return code, out.getvalue()

    def test_all_present_exits_zero(self):
        code, _ = self.run_main([])
        self.assertEqual(code, 0)

    def test_all_missing_reported_in_one_pass(self):
        code, text = self.run_main(['--json'], missing_modules=ALL_MODULES, rasterizer=None)
        self.assertEqual(code, 1)
        report = json.loads(text)
        self.assertEqual({m['module'] for m in report['missing']}, ALL_MODULES | {'rasterizer'})
        self.assertFalse(report['ok'])

    def test_single_missing_package_fails(self):
        code, text = self.run_main(['--json'], missing_modules={'kiwisolver'})
        self.assertEqual(code, 1)
        self.assertEqual([m['module'] for m in json.loads(text)['missing']], ['kiwisolver'])

    def test_missing_rasterizer_alone_fails(self):
        code, text = self.run_main(['--json'], rasterizer=None)
        self.assertEqual(code, 1)
        self.assertEqual([m['module'] for m in json.loads(text)['missing']], ['rasterizer'])

    def test_text_output_names_every_missing_item_with_install_hint(self):
        code, text = self.run_main([], missing_modules={'PIL', 'numpy'}, rasterizer=None)
        self.assertEqual(code, 1)
        for needle in ('Pillow', 'numpy', 'Inkscape', 'requirements.txt'):
            self.assertIn(needle, text)

    def test_requirements_file_pins_every_package_exactly(self):
        pins = D.read_requirements()
        self.assertEqual({D.dist_name(m) for m in ALL_MODULES}, set(pins))
        for name, spec in pins.items():
            self.assertTrue(spec.startswith('=='), '%s 未固定版本: %r' % (name, spec))


if __name__ == '__main__':
    unittest.main()
