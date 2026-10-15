"""Version-bound evidence through the validator, rasterizer and review CLIs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_entrypoints import SKILL, make_render_workspace


class ProofreadingEvidenceCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='proofreading-evidence-')
        self.addCleanup(self.tmp.cleanup)
        self.work = make_render_workspace(Path(self.tmp.name), SKILL / 'assets/fixtures/l0-small-seed')
        self.run_cli(self.work / 'render_l0_sheet.py')

    def run_cli(self, script, *args, expected=0):
        result = subprocess.run([sys.executable, str(script), *map(str, args)],
                                cwd=self.work, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def validate(self):
        self.run_cli(self.work / 'validate_sheet.py')
        return json.loads((self.work / 'validation-report.json').read_text())

    def rasterize(self):
        self.run_cli(SKILL / 'scripts/rasterize_sheet.py', self.work / '1#系统原理图.svg',
                     '-o', self.work / 'sheet-readback.png', '--backend', 'chrome')

    def evidence_cli(self, *args, expected=0):
        return self.run_cli(self.work / 'proofreading_evidence.py', *args,
                            self.work, expected=expected)

    def test_geometry_success_discloses_unchecked_required_evidence(self):
        report = self.validate()
        self.assertEqual(report['validation'], 'passed')
        self.assertEqual(report['fail_count'], 0)
        coverage = {item['id']: item for item in report['coverage']}
        self.assertEqual(coverage['V1']['status'], 'pass')
        self.assertEqual(coverage['B6.avoid_corridor']['status'], 'pass')
        self.assertEqual(coverage['B7']['status'], 'warn')
        self.assertTrue(coverage['B7']['evidence'][0]['violations'])
        self.assertEqual(coverage['PNG']['status'], 'not_checked')
        self.assertEqual(coverage['PERCEPTUAL']['status'], 'not_checked')
        self.assertEqual(report['phases']['automated']['status'], 'incomplete')
        self.assertFalse(report['delivery']['ready'])
        self.assertTrue(all(item['evidence'] for item in coverage.values()))

    def test_review_is_bound_to_content_and_report_not_filenames(self):
        self.rasterize()
        report = self.validate()
        self.assertEqual(report['phases']['perceptual']['status'], 'pending')
        self.assertEqual(next(c for c in report['coverage'] if c['id'] == 'PNG')['status'], 'pass')
        self.evidence_cli('record-review', '--reviewer', 'test reviewer',
                          '--decision', 'confirmed', '--note', 'Whole sheet inspected.')
        report = self.validate()
        self.assertEqual(report['phases']['perceptual']['status'], 'confirmed')
        fingerprint = report['artifacts']['fingerprint']
        self.assertEqual(self.validate()['artifacts']['fingerprint'], fingerprint)
        self.evidence_cli('verify')
        targets = ['1#系统原理图.svg', 'sheet-readback.png', '1#系统.layout.json',
                   '1#系统.intent.yaml', 'symbols/edp-provisional-stroke.svg',
                   'component-catalog.json', 'validate_sheet.py', 'validation-report.json', 'browser-evidence.json']
        for name in targets:
            with self.subTest(name=name):
                path = self.work / name
                original = path.read_bytes()
                path.write_bytes(original + b'\n ')
                result = self.evidence_cli('verify', expected=1)
                self.assertIn('invalid', result.stdout)
                self.assertNotIn('"status": "confirmed"', result.stdout)
                path.write_bytes(original)
                self.evidence_cli('verify')

    def test_windows_symbol_reference_binds_the_selected_catalog_asset(self):
        import shutil
        layout_path=self.work/'1#系统.layout.json';layout=json.loads(layout_path.read_text())
        name='edp-provisional-stroke.svg'
        actual=self.work/name
        shutil.copy2(self.work/'symbols'/name,actual)
        layout['nodes']['EDP-001']['symbol']='symbols'+chr(92)+name
        layout_path.write_text(json.dumps(layout))
        self.run_cli(self.work/'render_l0_sheet.py');self.rasterize();report=self.validate()
        selected=report['artifacts']['files']['symbol:EDP-001']
        self.assertEqual(Path(selected['path']),actual)
        self.assertIsNotNone(selected['sha256'])
        self.evidence_cli('verify')
        actual.write_text(actual.read_text()+'\n<!-- content version changed -->\n')
        changed=self.evidence_cli('verify',expected=1)
        self.assertIn('symbol:EDP-001',changed.stdout)

    def test_missing_required_symbol_keeps_diagnostics_but_cannot_verify_current(self):
        self.rasterize();self.validate()
        (self.work/'symbols/edp-provisional-stroke.svg').unlink()
        self.run_cli(self.work/'validate_sheet.py',expected=1)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertEqual(report['validation'],'failed')
        result=self.evidence_cli('verify',expected=1)
        self.assertIn('symbol:EDP-001',result.stdout)

    def test_driver_does_not_deliver_automated_success_without_perceptual_review(self):
        output = Path(self.tmp.name) / 'driver'
        self.run_cli(SKILL / 'scripts/validate_driver.py',
                     '--intent', self.work / '1#系统.intent.yaml',
                     '--layout-seed', self.work / '1#系统.layout.json',
                     '--workdir', output, expected=4)
        report = json.loads((output / 'convergence-report.json').read_text())
        self.assertTrue(report['converged'])
        self.assertFalse(report['delivery']['ready'])
        self.assertEqual(report['perceptual_review'], 'pending')
        self.assertIn('PERCEPTUAL', report['delivery']['blocking_checks'])
        self.assertEqual(report['automated_validation']['status'], 'complete')
        self.assertEqual(report['delivery']['blocking_checks'], ['PERCEPTUAL', 'READBACK_ITEMS'])

    def test_same_size_replaced_png_is_unchecked_after_revalidation(self):
        self.rasterize()
        self.validate()
        self.evidence_cli('record-review', '--reviewer', 'reviewer',
                          '--decision', 'confirmed', '--note', 'Inspected current image.')
        from PIL import Image
        path = self.work / 'sheet-readback.png'
        with Image.open(path) as original:
            Image.new('RGB', original.size, 'white').save(path)
        report = self.validate()
        self.assertEqual(report['phases']['perceptual']['status'], 'invalidated')
        self.assertEqual(next(c for c in report['coverage'] if c['id'] == 'PNG')['status'], 'not_checked')
        self.evidence_cli('record-review', '--reviewer', 'reviewer', '--decision', 'confirmed',
                          '--note', 'Cannot sign an unverified image.', expected=1)

    def test_parse_failure_replaces_old_success_report(self):
        self.validate()
        (self.work / '1#系统原理图.svg').write_text('<svg broken')
        self.run_cli(self.work / 'validate_sheet.py', expected=1)
        report = json.loads((self.work / 'validation-report.json').read_text())
        self.assertEqual(report['validation'], 'failed')
        coverage = {e['id']: e for e in report['coverage']}
        self.assertEqual(coverage['V1']['status'], 'fail')
        self.assertEqual(coverage['V2']['status'], 'not_checked')

    def test_standalone_validator_accepts_explicit_workdir(self):
        self.run_cli(SKILL / 'scripts/validate_sheet.py', self.work)
        report = json.loads((self.work / 'validation-report.json').read_text())
        self.assertEqual(report['fail_count'], 0)
        self.assertEqual(report['artifacts']['files']['input']['path'], str(self.work / '1#系统.intent.yaml'))


if __name__ == '__main__':
    unittest.main()
