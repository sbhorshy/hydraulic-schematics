"""selftest.py 公开 CLI 入口的快速门禁测试（不跑 F 组全量套件）。

只测参数面：--list-suites 纯 JSON 清单与 F 组必需套件集合完全一致
（不写死绝对数，按显式必需模块清单对账：原 24 套件 + #63 的
test_mirror_policy / test_mirror_render + #23 的 test_bridge_allowance + #83–#88 的 6 个回归套件，
新增/移除套件须同步本清单）；
无效 --jobs、NaN/Inf 或非正 --suite-timeout、未知参数一律退出码 2 且
不启动任何检查；已有 --report/--log-dir 输出路径保留不覆盖。逐套件
调度语义（并行/超时/清理）在 test_selftest_runner.py；F 组全量验收由
Codex 以 --jobs 2 实跑。
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

# F 组固定清单的必需模块（与 selftest.py 的 L0_SUITES 注册表对账）。
# 存量 24 套件一个不能少；#63 步骤一/二新增 mirror_policy 与 mirror_render；
# #23 新增 bridge_allowance（跳线许可登记与 B1 放行门禁）。
# --list-suites 必须恰好给出这份集合：缺失、多余、重复都是注册表漂移。
REQUIRED_SUITES = frozenset({
    # ---- 存量 24 套件 ----
    'test_coordinate_contract', 'test_assembly_layout', 'test_assemblies',
    'test_entrypoints', 'test_optimizer_budget', 'test_driver',
    'test_proofreading_evidence', 'test_route_pruning', 'test_rasterize_sheet',
    'test_priority_valve_leads', 'test_display_widths', 'test_paint_evidence',
    'test_rotation_routes', 'test_route_terminals', 'test_dangling_ports',
    'test_port_geometry', 'test_topology_reconciliation', 'test_text_display',
    'test_layout_clearance', 'test_junction_semantics', 'test_sheet_diff',
    'test_readback_review', 'test_symbol_gate', 'test_check_symbol_cli',
    # ---- #63 镜像（步骤一/二）----
    'test_mirror_policy', 'test_mirror_render',
    # ---- #23 跳线许可（B1 放行）----
    'test_bridge_allowance',
    # ---- #83–#88 可见几何检验与路由硬约束 ----
    'test_near_axis_routes', 'test_orphan_port_geometry',
    'test_suction_continuity', 'test_unintended_cycles',
    'test_upright_text', 'test_route_obstacles',
})


def _run_cli(args, timeout=60):
    return subprocess.run([sys.executable, '-u', str(SELFTEST)] + list(args),
                          cwd=str(REPO), capture_output=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


class SelftestCliGate(unittest.TestCase):
    maxDiff = None

    def test_list_suites_stays_pure_json_with_required_suites(self):
        done = _run_cli(['--list-suites'])
        combined = done.stdout + done.stderr
        self.assertEqual(done.returncode, 0, combined)
        selection = json.loads(done.stdout)  # 任何多余打印都会破坏纯 JSON
        self.assertEqual(selection['scope'], 'standalone-skill')
        suites = selection['suites']
        self.assertEqual(len(suites), len(set(suites)),
                         '套件清单不得出现重复: %s' % suites)
        self.assertEqual(set(suites), REQUIRED_SUITES,
                         'F 组清单漂移——缺失: %s 多余: %s'
                         % (sorted(REQUIRED_SUITES - set(suites)),
                            sorted(set(suites) - REQUIRED_SUITES)))
        self.assertIn('test_symbol_gate', suites)
        self.assertIn('test_check_symbol_cli', suites)
        self.assertIn('test_mirror_policy', suites)
        self.assertIn('test_mirror_render', suites)
        self.assertIn('test_bridge_allowance', suites)

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
