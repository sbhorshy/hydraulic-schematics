"""selftest.py 公开 CLI 入口的快速门禁测试（不跑 278 项全量）。

只测参数面：--list-suites 纯 JSON 清单仍为固定 24 套件；无效 --jobs、
NaN/Inf 或非正 --suite-timeout、未知参数一律退出码 2 且不启动任何检查；
已有 --report/--log-dir 输出路径保留不覆盖。逐套件调度语义（并行/超时/
清理）在 test_selftest_runner.py；F 组全量验收由 Codex 以 --jobs 2 实跑。
"""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
SELFTEST = (REPO / '.agents' / 'skills' / 'hydraulic-schematic'
            / 'scripts' / 'selftest.py')

EXPECTED_SUITE_COUNT = 24


def _run_cli(args, timeout=60):
    return subprocess.run([sys.executable, '-u', str(SELFTEST)] + list(args),
                          cwd=str(REPO), capture_output=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


class SelftestCliGate(unittest.TestCase):
    maxDiff = None

    def test_list_suites_stays_pure_json_with_24_suites(self):
        done = _run_cli(['--list-suites'])
        combined = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, combined)
        selection = json.loads(done.stdout)  # 任何多余打印都会破坏纯 JSON
        self.assertEqual(selection['scope'], 'standalone-skill')
        self.assertEqual(len(selection['suites']), EXPECTED_SUITE_COUNT)
        self.assertIn('test_symbol_gate', selection['suites'])
        self.assertIn('test_check_symbol_cli', selection['suites'])

    def test_invalid_jobs_rejected_before_any_check_runs(self):
        for bad in ('0', '5', 'abc', '1.5', ''):
            done = _run_cli(['--jobs', bad])
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 2, '值 %r 应判用法错误' % bad)
            self.assertIn('--jobs', done.stderr)
            self.assertNotIn('[PASS]', done.stdout, '用法错误不得先跑检查')

    def test_non_finite_or_invalid_suite_timeout_rejected(self):
        for bad in ('nan', 'inf', '-inf', 'Infinity', '0', '-5', 'abc'):
            done = _run_cli(['--suite-timeout', bad])
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 2, '值 %r 应判用法错误' % bad)
            self.assertIn('--suite-timeout', done.stderr)
            self.assertNotIn('范围:', done.stdout, '用法错误不得进入检查')

    def test_unknown_arguments_rejected(self):
        for args in (['--bogus'], ['stray-positional'],
                     ['--jobs', '2', '--nope'], ['--jobs']):
            done = _run_cli(args)
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 2, '参数 %r 应判用法错误' % (args,))
            self.assertNotIn('范围:', done.stdout, '用法错误不得进入检查')

    def test_value_options_require_nonempty_value(self):
        for token in ('--jobs', '--suite-timeout', '--report', '--log-dir'):
            done = _run_cli([token, ''])
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 2, '%s 空值应判用法错误' % token)
            self.assertIn(token, done.stderr)

    def test_existing_report_file_never_overwritten(self):
        with tempfile.TemporaryDirectory(prefix='cli-report-') as raw:
            victim = Path(raw) / 'report.json'
            victim.write_text('旧报告证据', encoding='utf-8')
            done = _run_cli(['--report', str(victim)])
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 2, combined)
            self.assertIn('--report', done.stderr)
            self.assertEqual(victim.read_text(encoding='utf-8'), '旧报告证据')

    def test_existing_log_dir_preserved(self):
        with tempfile.TemporaryDirectory(prefix='cli-logdir-') as raw:
            logs = Path(raw) / 'suites'
            logs.mkdir()
            (logs / 'old.log').write_text('旧套件日志', encoding='utf-8')
            done = _run_cli(['--log-dir', str(logs)])
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 2, combined)
            self.assertIn('--log-dir', done.stderr)
            self.assertEqual([p.name for p in logs.iterdir()], ['old.log'])
            self.assertEqual((logs / 'old.log').read_text(encoding='utf-8'),
                             '旧套件日志')


if __name__ == '__main__':
    unittest.main()
