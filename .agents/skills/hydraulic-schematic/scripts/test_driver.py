"""Driver orchestration: fresh artifacts, reused assets, bounded search and honest gates."""
import argparse
import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_driver as D


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hydraulic-driver-test-')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.skill = self.base / 'skill'
        self.scripts = self.skill / 'scripts'
        self.lib = self.skill / 'assets/component-library'
        self.scripts.mkdir(parents=True)
        self.lib.mkdir(parents=True)
        for name in D.SCRIPTS:
            (self.scripts / name).write_text('# fixture\n')
        (self.lib / D.CATALOG).write_text('{"components": []}')
        (self.lib / 'part.svg').write_text('<svg/>')
        self.src = self.base / 'input'
        self.src.mkdir()
        self.intent = self.src / 'intent.yaml'
        self.intent.write_text('parts: {}\npaths: []\n')
        self.wd = self.base / 'run'
        for key, value in [('HERE', str(self.scripts)), ('SKILL', str(self.skill)), ('LIB', str(self.lib))]:
            mock = patch.object(D, key, value)
            mock.start()
            self.addCleanup(mock.stop)

    def invoke(self, options=(), missing_png=False, findings=None, checks=None, default_workdir=False):
        calls = []
        def run(cmd, cwd, timeout=600):
            calls.append((cmd, timeout))
            folder = Path(cwd)
            if cmd[1] == 'preflight.py':
                return (1 if findings else 0), json.dumps({'status': 'FAIL' if findings else 'PASS',
                                                          'findings': findings or []}), ''
            if cmd[1] == 'layout_engine.py':
                (folder / D.LAYOUT_NAME).write_text('{}')
                (folder / 'layout-guard-report.json').write_text(json.dumps({
                    'optimization': {'stop_reason': 'max_evals', 'evals': 2}}))
                return 0, '', ''
            if cmd[1] == 'render_l0_sheet.py':
                (folder / D.SVG_NAME).write_text('<svg/>')
                return 0, '', ''
            if cmd[1] == 'rasterize_sheet.py':
                if missing_png:
                    return 1, '', 'renderer unavailable'
                (folder / D.READBACK).write_bytes(b'fresh image')
                return 0, '{"renderer":"test-double","width":100,"height":100}', ''
            if cmd[1] == 'validate_sheet.py':
                (folder / 'validation-report.json').write_text(json.dumps({'checks': checks or []}))
                return int(bool(checks)), '', ''
            raise AssertionError(cmd)
        workdir_args = [] if default_workdir else ['--workdir', str(self.wd)]
        with patch.object(sys, 'argv', ['driver', '--intent', str(self.intent),
                                       *workdir_args, *options]), \
             patch.object(D, 'run', side_effect=run), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = D.main()
        report = json.loads((self.wd / 'convergence-report.json').read_text())
        return code, report, calls

    def test_keep_reuses_assets_but_refreshes_input_and_invalidates_stale_outputs(self):
        self.invoke()
        stable = self.wd / 'part.svg'
        before = stable.stat().st_mtime_ns
        marker = self.wd / 'review-notes.txt'
        marker.write_text('preserve user notes')
        self.intent.write_text('parts: {}\npaths: []\nrevision: 2\n')
        (self.wd / D.READBACK).write_bytes(b'stale image')
        (self.wd / 'validation-report.json').write_text('{"old":true}')
        errors = [{'id': 'E-INPUT', 'level': 'ERROR', 'message': 'invalid',
                   'object': 'input', 'remedy': 'fix input'}]
        code, report, calls = self.invoke(['--keep'], findings=errors)
        self.assertEqual(code, 2)
        self.assertIn('revision: 2', (self.wd / D.INTENT_NAME).read_text())
        self.assertEqual(stable.stat().st_mtime_ns, before)
        self.assertTrue(marker.exists())
        self.assertFalse((self.wd / D.READBACK).exists())
        self.assertFalse((self.wd / 'validation-report.json').exists())
        self.assertFalse((self.wd / D.SVG_NAME).exists())
        self.assertGreater(report['workspace']['reused_files'], 0)
        self.assertEqual(len(calls), 1)

    def test_in_workspace_inputs_survive_keep(self):
        self.wd.mkdir()
        self.intent = self.wd / D.INTENT_NAME
        self.intent.write_text('parts: {}\npaths: []\nrevision: embedded\n')
        code, _, _ = self.invoke(['--keep'])
        self.assertEqual(code, 0)
        self.assertIn('embedded', self.intent.read_text())

    def test_skill_tree_and_ancestors_are_protected_even_through_symlinks(self):
        alias = self.base / 'skill-alias'
        alias.symlink_to(self.skill, target_is_directory=True)
        targets = [self.skill, self.scripts, self.lib, self.skill / 'assets',
                   self.scripts / 'driver-run', self.base, alias / 'assets']
        for target in targets:
            for keep in (False, True):
                with self.subTest(target=target, keep=keep), self.assertRaises(ValueError):
                    D.setup_workdir(str(target), keep=keep)
        self.assertEqual((self.lib / 'part.svg').read_text(), '<svg/>')
        self.assertTrue((self.scripts / 'preflight.py').is_file())

    def test_unmanaged_nonempty_directory_is_preserved(self):
        self.wd.mkdir()
        marker = self.wd / 'important.txt'
        marker.write_text('must survive')
        with self.assertRaises(ValueError):
            D.setup_workdir(str(self.wd))
        self.assertEqual(marker.read_text(), 'must survive')
        D.setup_workdir(str(self.wd), keep=True)
        self.assertEqual(marker.read_text(), 'must survive')

    def test_managed_directory_can_be_rebuilt(self):
        D.setup_workdir(str(self.wd))
        (self.wd / 'disposable.txt').write_text('scratch')
        D.setup_workdir(str(self.wd))
        self.assertFalse((self.wd / 'disposable.txt').exists())
        self.assertTrue((self.wd / D.MANAGED_FILES).exists())

    def test_default_workspace_is_independent_temporary_directory(self):
        default_wd = self.wd
        def create(prefix):
            self.assertEqual(prefix, 'hydraulic-driver-')
            default_wd.mkdir()
            return str(default_wd)
        with patch.object(D.tempfile, 'mkdtemp', side_effect=create):
            _, _, calls = self.invoke(default_workdir=True)
        self.assertTrue((default_wd / D.MANAGED_FILES).exists())
        self.assertFalse((self.scripts / 'driver-run').exists())
        self.assertTrue(calls)

    def test_schema_copy_is_inside_workspace_and_outside_schema_untouched(self):
        relative = Path('assets/contracts/l0-input-contract.schema.json')
        source = self.skill / relative
        source.parent.mkdir(parents=True)
        source.write_text('{"version": "current"}')
        outside = self.base / relative
        outside.parent.mkdir(parents=True)
        outside.write_text('{"version": "unrelated-project"}')
        D.setup_workdir(str(self.wd))
        self.assertEqual((self.wd / relative).read_text(), source.read_text())
        self.assertEqual(outside.read_text(), '{"version": "unrelated-project"}')

    def test_keep_rejects_asset_directory_symlink_outside_workspace(self):
        self.wd.mkdir()
        outside = self.base / 'external-symbols'
        outside.mkdir()
        (self.wd / 'symbols').symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            D.setup_workdir(str(self.wd), keep=True)
        self.assertEqual(list(outside.iterdir()), [])

    def test_missing_png_is_not_convergence_even_when_geometry_passes(self):
        code, report, calls = self.invoke(missing_png=True)
        self.assertEqual(code, 3)
        self.assertFalse(report['converged'])
        self.assertEqual(report['rounds'][0]['fails'][0]['id'], 'READBACK')
        self.assertIn('validate_sheet.py', [cmd[1] for cmd, _ in calls])
        self.assertEqual(report['rounds'][0]['stages'][2]['status'], 'failed')

    def test_bounded_search_still_runs_complete_automatic_pipeline(self):
        code, report, calls = self.invoke(['--optimize', '--max-evals', '2',
                                          '--max-steps', '1', '--max-seconds', '4'])
        layout_cmd, timeout = next((cmd, timeout) for cmd, timeout in calls if cmd[1] == 'layout_engine.py')
        self.assertIn('--max-evals', layout_cmd)
        self.assertEqual(layout_cmd[layout_cmd.index('--max-evals') + 1], '2')
        self.assertEqual(timeout, 64)
        self.assertEqual(code, 0)
        self.assertEqual(report['perceptual_review'], 'pending')
        self.assertEqual(report['rounds'][0]['optimization']['stop_reason'], 'max_evals')
        stages = report['stages'] + report['rounds'][0]['stages']
        self.assertEqual([s['stage'] for s in stages],
                         ['setup', 'preflight', 'layout', 'render', 'readback', 'validate'])
        self.assertTrue(all(s['elapsed_s'] >= 0 for s in stages))

    def test_validation_residuals_survive_optimizer_budget(self):
        code, report, _ = self.invoke(['--optimize', '--max-evals', '1'],
                                     checks=[{'id': 'V2', 'result': 'fail', 'detail': 'body collision'}])
        self.assertEqual(code, 1)
        self.assertFalse(report['converged'])
        self.assertEqual(report['residuals'][0]['id'], 'V2')

    def test_stale_validation_report_cannot_mask_child_failure(self):
        self.wd.mkdir()
        stale = self.wd / 'validation-report.json'
        stale.write_text('{"checks": []}')
        with patch.object(D, 'run', return_value=(1, '', 'failed')), self.assertRaises(RuntimeError):
            D.validate_run(str(self.wd))
        self.assertFalse(stale.exists())

    def test_local_seed_symbol_is_preserved_and_source_seed_not_modified(self):
        symbol = self.src / 'original.svg'
        symbol.write_text('<svg><path d="M 172 0"/></svg>')
        seed = self.src / 'seed.json'
        seed.write_text(json.dumps({'nodes': {'tank': {'symbol': 'original.svg'}}}))
        args = argparse.Namespace(intent=str(self.intent), catalog=None,
                                  layout_seed=str(seed), ref=None)
        files, assets, sources, _ = D.snapshot_inputs(args)
        rebuilt = json.loads(files[D.LAYOUT_NAME])
        self.assertEqual(assets[rebuilt['nodes']['tank']['symbol']], symbol.read_bytes())
        self.assertEqual(json.loads(seed.read_text())['nodes']['tank']['symbol'], 'original.svg')
        self.assertEqual(sources[0]['source'], str(symbol))

    def test_local_seed_keeps_provisional_and_draft_title_disclosures(self):
        import render_l0_sheet as R
        layout = {'title_block': {'x': 0, 'y': 0, 'w': 500, 'h': 80}, 'nodes': {}}
        catalog = {'components': []}
        for status in ('provisional', 'draft'):
            basename = status + '-part.svg'
            (self.src / basename).write_text('<svg/>')
            layout['nodes'][status] = {'symbol': basename}
            catalog['components'].append({'component_type': status + '_type',
                                          'symbol': {'asset': basename, 'symbol_status': status}})
        intent = {'system': 'test', 'l0_version': '0.1', 'catalog': 'test',
                  'maturity': 'concept', 'parts': {}, 'unknown': []}
        before = R.title_block(layout, intent, 0, [], catalog)
        seed = self.src / 'seed.json'
        seed.write_text(json.dumps(layout))
        args = argparse.Namespace(intent=str(self.intent), catalog=None,
                                  layout_seed=str(seed), ref=None)
        files, _, _, _ = D.snapshot_inputs(args)
        rebuilt = json.loads(files[D.LAYOUT_NAME])
        self.assertEqual(R.title_block(rebuilt, intent, 0, [], catalog), before)
        self.assertIn('provisional: provisional_type', ''.join(before))
        self.assertIn('draft: draft_type', ''.join(before))
        for inst, node in layout['nodes'].items():
            self.assertEqual(Path(rebuilt['nodes'][inst]['symbol']).name, Path(node['symbol']).name)

    def test_reused_seed_symbol_reference_stays_stable(self):
        self.wd.mkdir()
        symbol = self.wd / 'part.svg'
        symbol.write_text('<svg/>')
        seed = self.wd / D.LAYOUT_NAME
        seed.write_text(json.dumps({'nodes': {'part': {'symbol': 'part.svg'}}}))
        args = argparse.Namespace(intent=str(self.intent), catalog=None,
                                  layout_seed=str(seed), ref=None)
        files, assets, _, _ = D.snapshot_inputs(args)
        D.restore_inputs(str(self.wd), files, assets)
        next_files, next_assets, _, _ = D.snapshot_inputs(args)
        self.assertEqual(files, next_files)
        self.assertEqual(assets, next_assets)

    def test_stale_controlled_template_is_removed_on_keep(self):
        self.invoke()
        stale = self.wd / 'previous受控模板.yaml'
        stale.write_text('stale: true')
        self.invoke(['--keep'])
        self.assertFalse(stale.exists())

    def test_changed_asset_is_refreshed_on_keep(self):
        self.invoke()
        (self.lib / 'part.svg').write_text('<svg><path/></svg>')
        self.invoke(['--keep'])
        self.assertEqual((self.wd / 'part.svg').read_text(), '<svg><path/></svg>')
        self.assertEqual((self.wd / 'symbols/part.svg').read_text(), '<svg><path/></svg>')

    def test_subprocess_stderr_does_not_pollute_json_stdout(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc, out, err = D.run([sys.executable, '-c',
                                 'import sys; print("progress",file=sys.stderr,flush=True); print("{\\"ok\\":true}")'],
                                str(self.base))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out), {'ok': True})
        self.assertIn('progress', stderr.getvalue())
        self.assertIn('progress', err)

    def test_subprocess_timeout_is_recorded(self):
        rc, _, err = D.run([sys.executable, '-c', 'import time; time.sleep(2)'], str(self.base), timeout=0.02)
        self.assertIsNone(rc)
        self.assertIn('超时', err)


    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group integration')
    def test_inherited_pipes_do_not_escape_timeout(self):
        # 子孙持有 stdout/stderr 20 秒；真实超时必须终止组，而非等自然 EOF。
        for parent_stays in (True, False):
            with self.subTest(parent_stays=parent_stays):
                pidfile = self.base / ('child-%s.pid' % parent_stays)
                child_code = 'import time; time.sleep(20)'
                parent_code = ('import subprocess,sys,time,pathlib; '
                               'child=subprocess.Popen([sys.executable,"-c",%r]); '
                               'pathlib.Path(%r).write_text(str(child.pid)); '
                               'time.sleep(%d)' % (child_code, str(pidfile), 20 if parent_stays else 0))
                runner = ('import validate_driver as d,sys,time,json; '
                          'start=time.monotonic(); '
                          'rc,out,err=d.run([sys.executable,"-c",%r],%r,timeout=0.2); '
                          'print(json.dumps({"rc":rc,"elapsed":time.monotonic()-start,"err":err}))'
                          % (parent_code, str(self.base)))
                try:
                    completed = subprocess.run([sys.executable, '-c', runner],
                                               cwd=str(Path(D.__file__).parent), capture_output=True,
                                               text=True, timeout=3)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    result = json.loads(completed.stdout)
                    self.assertIsNone(result['rc'])
                    self.assertIn('超时', result['err'])
                    self.assertLess(result['elapsed'], 1.5)
                    self.assertTrue(pidfile.is_file(), 'must actually launch pipe-inheriting descendant')
                    child_pid = int(pidfile.read_text())
                    status = Path('/proc', str(child_pid), 'stat')
                    if status.exists():
                        self.assertEqual(status.read_text().split()[2], 'Z', 'descendant must no longer run')
                finally:
                    if pidfile.exists():
                        try:
                            os.kill(int(pidfile.read_text()), signal.SIGKILL)
                        except ProcessLookupError:
                            pass


if __name__ == '__main__':
    unittest.main()
