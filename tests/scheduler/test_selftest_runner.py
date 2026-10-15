"""selftest_runner 公开调度契约测试（真实 CLI + 临时 tiny unittest 模块）。

只经验证过的边界取材：
  * 真实 runner CLI（scripts/selftest_runner.py 子进程）；
  * 临时目录里生成的 tiny unittest 套件模块（睡眠/挂起/失败/零用例/
    subTest 失败）；
  * 产物文件（独立套件日志、合并完整日志、机器 JSON 报告、时间戳标记）；
  * 真实抓获的 unittest -v 输出片段（逐字保存的机器报告病例日志行）。
不重算实现期望——期望值全部来自 tiny 模块自身声明的行为（睡眠秒数、
打印标记、计划失败）或日志片段文本自身的事实；除输出片段回归组直接把
真实日志文本喂给 runner 模块的解析入口（断言日志自身事实，非重算实现）
外，不测私有函数。

覆盖的调度契约：
  1. --jobs 并发上限（同一时刻不得超过 N 个套件进程）与真实并行生效；
  2. --jobs 1 串行且同样工作；
  3. 逐套件超时只终止肇事套件，其他套件结果不丢；
  4. 零用例套件不允许假绿；
  5. 失败套件不吞掉其他套件结果；
  6. 输出路径（log-dir / merged-log / report）在启动任何套件之前独占预留，
     已有文件不覆盖、不留半程产物；
  7. 合并完整日志按套件整文件拼接（含每用例结果，不丢行）与机器报告内容；
  8. --jobs 越界（0 / 5）被拒绝且不启动任何套件；
  9. 预检失败的清理只删本次独占创建的产物：report/merged/logdir 已存在时
     退出 2 且原内容一字不动，后续路径失败时本次新建产物仍清干净；
 10. 带 docstring 的用例（-v 结果另起行）不丢 cases，机器记录 ID=
     module.Class.test_method；
 11. suite-timeout 拒绝 NaN/Inf/非正数；空名、重复、路径分隔符/遍历的套件
     名在启动前拒绝；
 12. 跳过用例如实披露；全套 skipped 记 all_skipped，明确不是 passed；
 13. Python 3.10 机器报告病例：方法内 subTest 失败的父方法不写结果词也
     不换行、下一个方法头接在同一行——真实 tiny 模块经 CLI（run_suites）
     报告 3 个完整唯一 ID、tests_ran=3、subTest 父方法 FAIL、普通异常
     方法 ERROR、成功 ok、suite 失败、失败/错误计数如实，subTest 不折算
     额外用例；
 14. 真实抓获的 -v 日志片段：同一行串接多个方法头时每个完整
     module.Class.method 只记一次、摘要区 FAIL:/ERROR: 标题（含 subTest
     描述）补定被截断父方法的状态——含 docstring 首行行尾串接下一方法
     头的组合（行尾结果词记给串接的方法，父方法由摘要纠正为 FAIL，不
     被误读的 ok 掩盖）；超时被杀截断、无摘要可考的用例显式记 unknown
     而非 ok；
 15. 机器报告病例 runner-docsub-review：带 docstring 的方法内 subTest 失
     败、后续成功方法串接在文档首行行尾——真实 tiny 模块经 CLI
     （run_suites）报告 2 个完整唯一 ID、tests_ran=2、docstring 父方法
     FAIL、后续成功方法 ok 不丢失、subTest 不折算额外用例数。

本组不属于 selftest.py 的 F 组固定清单。那份清单以 selftest.py 的
L0_SUITES 注册表为准，成员完整性由 test_selftest_cli.py 以显式必需模块
集合对账（存量 24 套件 + #63 的 test_mirror_policy / test_mirror_render
+ #23 的 test_bridge_allowance + #83–#88 的回归套件，须齐全、无多余、无重复）；本文件不写死
套件绝对数。
"""
from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
RUNNER = (REPO / '.agents' / 'skills' / 'hydraulic-schematic'
          / 'scripts' / 'selftest_runner.py')

TINY_PASS_BODY = """\
import json
import os
import time
import unittest


def _stamp(tag):
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, '%s.%s.json' % (__name__, tag))
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump({{'suite': __name__, 'tag': tag, 't': time.time()}}, handle)


class TestTiny(unittest.TestCase):
    def test_it(self):
        _stamp('start')
        time.sleep({sleep})
        _stamp('end')
        print('TINY-DONE-' + __name__)
"""

TINY_FAIL_BODY = """\
import unittest


class TestTiny(unittest.TestCase):
    def test_it(self):
        print('TINY-DONE-' + __name__)
        self.fail('planned failure for scheduler test')
"""

TINY_EMPTY_BODY = "MARKER = 'no test cases in this module'\n"

TINY_DOC_BODY = '''\
import unittest


class TestTinyDoc(unittest.TestCase):
    def test_with_docstring(self):
        """多行文档首行：验证带 docstring 的用例在 -v 输出中结果另起一行。"""
        self.assertTrue(True)
'''

TINY_SKIP_BODY = '''\
import unittest


class TestTinyAllSkip(unittest.TestCase):
    @unittest.skip('planned whole-suite skip for scheduler test')
    def test_skipped(self):
        self.fail('skipped case body must not run')
'''

TINY_MIX_BODY = '''\
import unittest


class TestTinyMix(unittest.TestCase):
    def test_passing(self):
        self.assertTrue(True)

    @unittest.skip('planned single-case skip for scheduler test')
    def test_skipped(self):
        self.fail('skipped case body must not run')
'''

TINY_SUBTEST_BODY = '''\
import unittest


class TestTinySubTest(unittest.TestCase):
    # 方法名决定运行顺序（unittest 按字母序）：subTest 父方法在最前——
    # Python 3.10 的 unittest 不为 subTest 失败的父方法补写结果词也不
    # 换行，后继方法头会接在同一行（机器报告病例的真实形态）。
    def test_a_subtest_parent_fail(self):
        for value in (1, 2):
            with self.subTest(value=value):
                self.assertNotEqual(value, 2)

    def test_b_plain_error(self):
        raise RuntimeError('planned error for subtest parsing test')

    def test_c_ok(self):
        self.assertTrue(True)
'''

# 机器报告病例 runner-docsub-review 的组合形态：subTest 失败的父方法带
# docstring——Python 3.10 不为父方法补写结果词也不换行，下一方法头串接
# 在文档首行行尾，行尾的「ok」属于 test_b 而非 test_a。
TINY_DOCSUB_BODY = '''\
import unittest


class TestTinyDocSub(unittest.TestCase):
    def test_a(self):
        """Descriptive case first line."""
        for value in (1, 2):
            with self.subTest(value=value):
                self.assertNotEqual(value, 2)

    def test_b(self):
        self.assertTrue(True)
'''

# 本轮机器报告病例的真实抓获片段：../skill-final-validation/suites/
# test_rotation_routes.log 首行逐字保存（该套件 tests_ran=4、failures=2，
# 其中 test_other_rf_and_cv_orientations 因 subTest 失败未在本行收尾，
# 下一个方法头直接接在同一行）；其后为 Python 3.10 unittest 摘要区
# 标准形态补全。
ROTATION_LOG_FRAGMENT = """\
test_other_rf_and_cv_orientations (test_rotation_routes.RotationRoutes) ... test_rf_270_does_not_move_its_collision_into_the_neighbor (test_rotation_routes.RotationRoutes) ... FAIL
test_rf_and_cv_neighbors_reconciled (test_rotation_routes.RotationRoutes) ... ok
test_symmetric_mirror_kept_under_rotation (test_rotation_routes.RotationRoutes) ... ok

======================================================================
FAIL: test_other_rf_and_cv_orientations (test_rotation_routes.RotationRoutes) [rotation='rf270']
----------------------------------------------------------------------
Traceback (most recent call last):
  File "test_rotation_routes.py", line 88, in test_other_rf_and_cv_orientations
    with self.subTest(rotation=rotation):
AssertionError: False is not true

======================================================================
FAIL: test_rf_270_does_not_move_its_collision_into_the_neighbor (test_rotation_routes.RotationRoutes)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "test_rotation_routes.py", line 147, in test_rf_270_does_not_move_its_collision_into_the_neighbor
    self.assertTrue(moved_into_neighbor)
AssertionError: False is not true

----------------------------------------------------------------------
Ran 4 tests in 0.012s

FAILED (failures=2)
"""

# 套件进程超时被杀的截断形态：只剩未收尾的方法头，没有摘要区可考。
TRUNCATED_LOG_FRAGMENT = (
    "test_rotates_all_eight_directions "
    "(test_rotation_routes.RotationRoutes) ... \n"
    "test_mirror_policy_holds (test_rotation_routes.RotationRoutes)")

# 机器报告病例 runner-docsub-review 的真实抓获形态：带 docstring 的
# subTest 失败父方法——Python 3.10 不为父方法补写结果词也不换行，下一
# 方法头串接在文档首行行尾，行尾的「ok」属于 test_b 而非 test_a；其中
# traceback 与摘要区按 Python 3.10 unittest 标准形态补全。
DOCSUB_LOG_FRAGMENT = """\
test_a (docsub.Cases)
Descriptive case first line. ... test_b (docsub.Cases) ... ok

======================================================================
FAIL: test_a (docsub.Cases) (value=1)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "docsub.py", line 6, in test_a
    with self.subTest(value=value):
AssertionError: 1 == 1

----------------------------------------------------------------------
Ran 2 tests in 0.001s

FAILED (failures=1)
"""


def _make_suite(directory, name, kind='pass', sleep='1.2'):
    if kind == 'pass':
        body = TINY_PASS_BODY.format(sleep=sleep)
    elif kind == 'fail':
        body = TINY_FAIL_BODY
    elif kind == 'empty':
        body = TINY_EMPTY_BODY
    elif kind == 'hang':
        body = TINY_PASS_BODY.format(sleep='60.0')
    elif kind == 'doc':
        body = TINY_DOC_BODY
    elif kind == 'skip':
        body = TINY_SKIP_BODY
    elif kind == 'mix':
        body = TINY_MIX_BODY
    elif kind == 'subtest':
        body = TINY_SUBTEST_BODY
    elif kind == 'docsub':
        body = TINY_DOCSUB_BODY
    else:
        raise ValueError(kind)
    (directory / (name + '.py')).write_text(body, encoding='utf-8')


def _run_runner(tmp, suites, jobs=1, suite_timeout='600', with_outputs=True,
                timeout=90):
    command = [sys.executable, '-u', str(RUNNER),
               '--jobs', str(jobs), '--suite-timeout', str(suite_timeout)]
    if with_outputs:
        command += ['--log-dir', str(tmp / 'logs'),
                    '--merged-log', str(tmp / 'merged.log'),
                    '--report', str(tmp / 'report.json')]
    command += list(suites)
    return subprocess.run(command, cwd=str(tmp), capture_output=True,
                          encoding='utf-8', errors='replace', timeout=timeout)


def _marker(tmp, suite, tag):
    path = tmp / ('%s.%s.json' % (suite, tag))
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding='utf-8'))


def _load_report(tmp):
    return json.loads((tmp / 'report.json').read_text(encoding='utf-8'))


def _max_concurrency(intervals):
    events = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort()
    current = peak = 0
    for _, delta in events:
        current += delta
        peak = max(peak, current)
    return peak


def _load_runner_module():
    """按路径加载 runner 模块本体（仅输出片段回归组使用，喂真实日志）。"""
    spec = importlib.util.spec_from_file_location('selftest_runner_parse',
                                                  RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SelftestRunnerScheduling(unittest.TestCase):
    maxDiff = None

    def test_bounded_jobs_cap_and_real_parallelism(self):
        with tempfile.TemporaryDirectory(prefix='sched-cap-') as raw:
            tmp = Path(raw)
            names = ['tiny_%d' % index for index in range(4)]
            for name in names:
                _make_suite(tmp, name, sleep='1.2')
            done = _run_runner(tmp, names, jobs=2, timeout=120)
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            self.assertEqual(report['summary']['status'], 'PASS')
            self.assertEqual(report['jobs'], 2)
            intervals = []
            for name in names:
                start = _marker(tmp, name, 'start')
                end = _marker(tmp, name, 'end')
                self.assertIsNotNone(start, '套件 %s 未运行' % name)
                self.assertIsNotNone(end, '套件 %s 未完成' % name)
                intervals.append((start['t'], end['t']))
            peak = _max_concurrency(intervals)
            self.assertLessEqual(peak, 2, '并发超过 --jobs 2 上限')
            self.assertGreaterEqual(peak, 2,
                                    '子进程自记的 start/end 区间无重叠，'
                                    '未见真实并行')

    def test_jobs_one_runs_suites_sequentially(self):
        with tempfile.TemporaryDirectory(prefix='sched-ser-') as raw:
            tmp = Path(raw)
            for name in ('ser_a', 'ser_b'):
                _make_suite(tmp, name, sleep='1.2')
            done = _run_runner(tmp, ['ser_a', 'ser_b'], jobs=1, timeout=120)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            intervals = []
            for name in ('ser_a', 'ser_b'):
                start = _marker(tmp, name, 'start')
                end = _marker(tmp, name, 'end')
                self.assertIsNotNone(start, '套件 %s 未运行' % name)
                self.assertIsNotNone(end, '套件 %s 未完成' % name)
                intervals.append((start['t'], end['t']))
            intervals.sort()
            self.assertGreaterEqual(intervals[1][0], intervals[0][1],
                                    'jobs=1 下两个套件的 start/end 区间重叠')

    def test_suite_timeout_kills_only_offending_suite(self):
        with tempfile.TemporaryDirectory(prefix='sched-to-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'hang_suite', kind='hang')
            _make_suite(tmp, 'quick_suite', sleep='0.2')
            done = _run_runner(tmp, ['hang_suite', 'quick_suite'], jobs=2,
                               suite_timeout='2', timeout=90)
            combined = done.stdout + done.stderr
            self.assertNotEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            by_suite = {r['suite']: r for r in report['suites']}
            self.assertEqual(by_suite['hang_suite']['status'], 'timeout')
            self.assertTrue(by_suite['hang_suite']['timed_out'])
            self.assertEqual(by_suite['quick_suite']['status'], 'passed')
            self.assertEqual(by_suite['quick_suite']['tests_ran'], 1)
            self.assertLess(report['wall_seconds'], 20.0,
                            '超时套件未被及时终止（保护上限 2 秒）')
            merged = (tmp / 'merged.log').read_text(encoding='utf-8',
                                                    errors='replace')
            self.assertIn('TINY-DONE-quick_suite', merged)
            self.assertIsNone(_marker(tmp, 'hang_suite', 'end'),
                              '挂起套件不应跑完')

    def test_zero_test_suite_cannot_go_green(self):
        with tempfile.TemporaryDirectory(prefix='sched-zero-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'empty_suite', kind='empty')
            _make_suite(tmp, 'ok_suite', sleep='0.2')
            done = _run_runner(tmp, ['empty_suite', 'ok_suite'], jobs=1)
            combined = done.stdout + done.stderr
            self.assertNotEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            by_suite = {r['suite']: r for r in report['suites']}
            self.assertEqual(by_suite['empty_suite']['status'], 'no_tests')
            self.assertEqual(by_suite['ok_suite']['status'], 'passed')
            self.assertEqual(report['summary']['status'], 'FAIL')
            self.assertEqual(report['summary']['suites_by_status']['no_tests'], 1)

    def test_failing_suite_keeps_other_suite_results(self):
        with tempfile.TemporaryDirectory(prefix='sched-fail-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'bad_suite', kind='fail')
            _make_suite(tmp, 'good_suite', sleep='0.2')
            done = _run_runner(tmp, ['bad_suite', 'good_suite'], jobs=2)
            combined = done.stdout + done.stderr
            self.assertNotEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            by_suite = {r['suite']: r for r in report['suites']}
            self.assertEqual(by_suite['bad_suite']['status'], 'failed')
            self.assertEqual(by_suite['bad_suite']['failures'], 1)
            self.assertEqual(by_suite['bad_suite']['cases'][0]['result'], 'FAIL')
            self.assertEqual(by_suite['good_suite']['status'], 'passed')
            self.assertEqual(by_suite['good_suite']['tests_ran'], 1)
            summary = report['summary']
            self.assertEqual(summary['status'], 'FAIL')
            self.assertEqual(summary['tests_ran'], 2)
            self.assertEqual(summary['failures'], 1)
            merged = (tmp / 'merged.log').read_text(encoding='utf-8',
                                                    errors='replace')
            self.assertIn('planned failure for scheduler test', merged)

    def test_output_paths_are_reserved_before_any_suite_starts(self):
        for target in ('report.json', 'merged.log', 'logs'):
            with tempfile.TemporaryDirectory(prefix='sched-pre-') as raw:
                tmp = Path(raw)
                _make_suite(tmp, 'tiny_a', sleep='0.2')
                victim = tmp / target
                if target == 'logs':
                    victim.mkdir()
                    (victim / 'old.log').write_text('旧套件日志',
                                                    encoding='utf-8')
                else:
                    victim.write_text('旧证据不得覆盖', encoding='utf-8')
                done = _run_runner(tmp, ['tiny_a'])
                combined = done.stdout + done.stderr
                self.assertNotEqual(done.returncode, 0, combined)
                self.assertIn('预检', combined)
                self.assertEqual(list(tmp.glob('*.start.json')), [],
                                 '预检失败前不应有任何套件进程启动')
                if target == 'logs':
                    self.assertTrue(victim.is_dir())
                    self.assertEqual(
                        [p.name for p in victim.iterdir()], ['old.log'])
                    self.assertEqual(
                        (victim / 'old.log').read_text(encoding='utf-8'),
                        '旧套件日志')
                else:
                    self.assertEqual(victim.read_text(encoding='utf-8'),
                                     '旧证据不得覆盖')
                if target == 'report.json':
                    self.assertFalse((tmp / 'merged.log').exists(),
                                     '预检失败后不应残留新的合并日志')
                if target == 'merged.log':
                    self.assertFalse((tmp / 'report.json').exists(),
                                     '预检失败后不应残留新的报告')

    def test_merged_log_and_machine_report_contents(self):
        with tempfile.TemporaryDirectory(prefix='sched-log-') as raw:
            tmp = Path(raw)
            names = ['alpha_suite', 'beta_suite']
            for name in names:
                _make_suite(tmp, name, sleep='0.2')
            done = _run_runner(tmp, names, jobs=2)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            merged = (tmp / 'merged.log').read_text(encoding='utf-8',
                                                    errors='replace')
            self.assertEqual(merged.count('Ran 1 test'), len(names))
            self.assertEqual(merged.count('... ok'), len(names))
            for name in names:
                self.assertIn('TINY-DONE-' + name, merged)
                self.assertIn('test_it (', merged)
                suite_log = tmp / 'logs' / (name + '.log')
                self.assertTrue(suite_log.is_file(),
                                '缺独立套件日志 %s' % suite_log)
            report = _load_report(tmp)
            self.assertEqual([r['suite'] for r in report['suites']], names)
            for record, name in zip(report['suites'], names):
                self.assertEqual(record['command'][1:],
                                 ['-m', 'unittest', '-v', name])
                self.assertEqual(record['status'], 'passed')
                self.assertGreater(record['duration_seconds'], 0)
                self.assertEqual(record['tests_ran'], 1)
                self.assertEqual(record['cases'][0]['name'], 'test_it')
                self.assertEqual(record['cases'][0]['result'], 'ok')
            summary = report['summary']
            self.assertEqual(summary['status'], 'PASS')
            self.assertEqual(summary['suites_total'], len(names))
            self.assertEqual(summary['tests_ran'], len(names))
            self.assertEqual(summary['failures'], 0)
            self.assertEqual(summary['errors'], 0)
            self.assertEqual(report['suite_timeout_seconds'], 600.0)

    def test_jobs_out_of_range_is_rejected(self):
        for bad in ('0', '5'):
            with tempfile.TemporaryDirectory(prefix='sched-jobs-') as raw:
                tmp = Path(raw)
                _make_suite(tmp, 'tiny_a', sleep='0.2')
                done = _run_runner(tmp, ['tiny_a'], jobs=bad)
                combined = done.stdout + done.stderr
                self.assertNotEqual(done.returncode, 0, combined)
                self.assertIn('--jobs', combined)
                self.assertEqual(list(tmp.glob('*.start.json')), [],
                                 '参数被拒后不应启动任何套件')

    def test_minimal_invocation_without_optional_outputs(self):
        with tempfile.TemporaryDirectory(prefix='sched-min-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'tiny_a', sleep='0.2')
            done = _run_runner(tmp, ['tiny_a'], with_outputs=False)
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertIn('[passed]', done.stdout)
            self.assertFalse((tmp / 'report.json').exists())

    def test_preflight_failure_only_cleans_files_created_this_run(self):
        with tempfile.TemporaryDirectory(prefix='sched-keep-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'tiny_a', sleep='0.2')
            (tmp / 'merged.log').write_text('旧合并证据', encoding='utf-8')
            (tmp / 'report.json').write_text('旧报告证据', encoding='utf-8')
            done = _run_runner(tmp, ['tiny_a'])
            combined = done.stdout + done.stderr
            self.assertNotEqual(done.returncode, 0, combined)
            self.assertIn('预检', combined)
            self.assertEqual((tmp / 'merged.log').read_text(encoding='utf-8'),
                             '旧合并证据', '用户已有合并日志被删除或改写')
            self.assertEqual((tmp / 'report.json').read_text(encoding='utf-8'),
                             '旧报告证据', '用户已有报告被删除或改写')
            self.assertFalse((tmp / 'logs').exists(),
                             '本次自建的日志目录应整体清理，不留半程产物')
            self.assertEqual(list(tmp.glob('*.start.json')), [],
                             '预检失败前不应有任何套件进程启动')

    def test_docstring_case_result_recorded_with_full_id(self):
        with tempfile.TemporaryDirectory(prefix='sched-doc-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'tiny_doc', kind='doc')
            done = _run_runner(tmp, ['tiny_doc'])
            combined = done.stdout + done.stderr
            self.assertEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            record = report['suites'][0]
            self.assertEqual(record['status'], 'passed')
            self.assertEqual(record['tests_ran'], 1)
            self.assertEqual(len(record['cases']), 1,
                             '带 docstring 的用例结果另起行，cases 不得丢失')
            case = record['cases'][0]
            self.assertEqual(case['name'], 'test_with_docstring')
            self.assertEqual(case['id'],
                             'tiny_doc.TestTinyDoc.test_with_docstring')
            self.assertEqual(case['result'], 'ok')
            merged = (tmp / 'merged.log').read_text(encoding='utf-8',
                                                    errors='replace')
            self.assertIn('test_with_docstring (tiny_doc.TestTinyDoc)', merged)
            self.assertIn('多行文档首行', merged)

    def test_invalid_timeout_and_suite_names_rejected_before_launch(self):
        for bad_timeout in ('nan', 'inf', '-inf', '0', '-3'):
            with tempfile.TemporaryDirectory(prefix='sched-timeout-') as raw:
                tmp = Path(raw)
                _make_suite(tmp, 'tiny_a', sleep='0.2')
                done = _run_runner(tmp, ['tiny_a'], suite_timeout=bad_timeout)
                combined = done.stdout + done.stderr
                self.assertNotEqual(done.returncode, 0, combined)
                self.assertIn('--suite-timeout', combined)
                self.assertEqual(list(tmp.glob('*.start.json')), [],
                                 '参数被拒后不应启动任何套件')
        for suites, why in [(('',), '空套件名'),
                            (('tiny_a', 'tiny_a'), '重复套件名'),
                            (('tiny_a', '../escape'), '路径遍历套件名'),
                            (('tiny_a', 'a/b'), '路径分隔符套件名')]:
            with tempfile.TemporaryDirectory(prefix='sched-name-') as raw:
                tmp = Path(raw)
                _make_suite(tmp, 'tiny_a', sleep='0.2')
                done = _run_runner(tmp, list(suites))
                combined = done.stdout + done.stderr
                self.assertNotEqual(done.returncode, 0, why)
                self.assertIn('套件', combined)
                self.assertEqual(list(tmp.glob('*.start.json')), [],
                                 '%s 应在启动前被拒绝' % why)

    def test_skipped_disclosed_and_all_skipped_suite_not_passed(self):
        with tempfile.TemporaryDirectory(prefix='sched-skip-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'tiny_skip', kind='skip')
            _make_suite(tmp, 'tiny_mix', kind='mix')
            done = _run_runner(tmp, ['tiny_skip', 'tiny_mix'], jobs=2)
            combined = done.stdout + done.stderr
            self.assertNotEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            by_suite = {r['suite']: r for r in report['suites']}
            allskip = by_suite['tiny_skip']
            self.assertEqual(allskip['status'], 'all_skipped')
            self.assertEqual(allskip['tests_ran'], 1)
            self.assertEqual(allskip['skipped'], 1)
            self.assertTrue(allskip['cases'][0]['result'].startswith('skipped'))
            mix = by_suite['tiny_mix']
            self.assertEqual(mix['status'], 'passed')
            self.assertEqual(mix['tests_ran'], 2)
            self.assertEqual(mix['skipped'], 1)
            results = {c['name']: c['result'] for c in mix['cases']}
            self.assertEqual(len(results), 2, 'mix 套件两个用例都应在 cases 里')
            self.assertEqual(results['test_passing'], 'ok')
            self.assertTrue(results['test_skipped'].startswith('skipped'),
                            '跳过用例必须披露为 skipped，不得记为通过')
            summary = report['summary']
            self.assertEqual(summary['status'], 'FAIL')
            self.assertEqual(summary['suites_by_status']['all_skipped'], 1)
            self.assertEqual(summary['skipped'], 2)

    def test_subtest_failure_case_ids_complete_and_honest(self):
        with tempfile.TemporaryDirectory(prefix='sched-subtest-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'tiny_subtest', kind='subtest')
            done = _run_runner(tmp, ['tiny_subtest'])
            combined = done.stdout + done.stderr
            self.assertNotEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            record = report['suites'][0]
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['tests_ran'], 3)
            cases = record['cases']
            self.assertEqual(len(cases), 3,
                             'subTest 失败截断父方法行时用例不得丢失')
            by_id = {case['id']: case['result'] for case in cases}
            self.assertEqual(len(by_id), 3,
                             '每个完整 module.Class.method 只记一次')
            self.assertEqual(
                by_id.get('tiny_subtest.TestTinySubTest.test_a_subtest_parent_fail'),
                'FAIL',
                'subTest 失败的父方法应由摘要区 FAIL: 标题补定状态，'
                '而不是吞掉串接在同一行的下一个方法头')
            self.assertEqual(
                by_id.get('tiny_subtest.TestTinySubTest.test_b_plain_error'),
                'ERROR')
            self.assertEqual(
                by_id.get('tiny_subtest.TestTinySubTest.test_c_ok'), 'ok')
            self.assertNotIn('unknown', by_id.values())
            self.assertEqual(record['failures'], 1)
            self.assertEqual(record['errors'], 1)
            summary = report['summary']
            self.assertEqual(summary['status'], 'FAIL')
            self.assertEqual(summary['tests_ran'], 3)
            self.assertEqual(summary['failures'], 1)
            self.assertEqual(summary['errors'], 1)
            merged = (tmp / 'merged.log').read_text(encoding='utf-8',
                                                    errors='replace')
            self.assertIn('(value=2)', merged,
                          'subTest 条件描述应保留在完整日志证据里')

    def test_docstring_subtest_parent_and_glued_next_method_both_recorded(self):
        with tempfile.TemporaryDirectory(prefix='sched-docsub-') as raw:
            tmp = Path(raw)
            _make_suite(tmp, 'tiny_docsub', kind='docsub')
            done = _run_runner(tmp, ['tiny_docsub'])
            combined = done.stdout + done.stderr
            self.assertNotEqual(done.returncode, 0, combined)
            report = _load_report(tmp)
            record = report['suites'][0]
            self.assertEqual(record['status'], 'failed')
            self.assertEqual(record['tests_ran'], 2,
                             'subTest 失败不折算额外用例数（共 2 个方法）')
            cases = record['cases']
            self.assertEqual(len(cases), 2,
                             'docstring 首行行尾串接下一方法头时用例不得丢失')
            by_id = {case['id']: case['result'] for case in cases}
            self.assertEqual(len(by_id), 2,
                             '每个完整 module.Class.method 只记一次')
            self.assertEqual(
                by_id.get('tiny_docsub.TestTinyDocSub.test_a'), 'FAIL',
                'subTest 失败的 docstring 父方法由摘要区 FAIL: 标题纠正，'
                '不得窃取串接在文档首行行尾的下一方法结果词')
            self.assertEqual(
                by_id.get('tiny_docsub.TestTinyDocSub.test_b'), 'ok',
                '串接在 docstring 首行行尾的后续成功方法不得丢失')
            self.assertNotIn('unknown', by_id.values())
            self.assertEqual(record['failures'], 1)
            self.assertEqual(record['errors'], 0)
            summary = report['summary']
            self.assertEqual(summary['status'], 'FAIL')
            self.assertEqual(summary['tests_ran'], 2)
            self.assertEqual(summary['failures'], 1)
            merged = (tmp / 'merged.log').read_text(encoding='utf-8',
                                                    errors='replace')
            self.assertIn('Descriptive case first line. ... test_b (', merged,
                          '组合病例证据：下一方法头串接在 docstring 首行行尾')
            self.assertIn('(value=2)', merged,
                          'subTest 条件描述应保留在完整日志证据里')


class SelftestRunnerCapturedOutputParsing(unittest.TestCase):
    """真实抓获的 unittest -v 输出片段回归（机器报告病例的解析口径）。

    例外说明：本组直接把保存的真实日志文本喂给 runner 模块的解析入口
    （_parse_unittest_output，机器报告路径上的事实提取函数），期望值全部
    来自日志文本自身的事实；公开 run_suites/CLI 路径的同类回归见
    SelftestRunnerScheduling.test_subtest_failure_case_ids_complete_and_honest，
    两者互补，并非只测内部实现。
    """
    maxDiff = None

    def setUp(self):
        self.runner = _load_runner_module()

    def test_captured_concatenated_headers_parse_every_parent_once(self):
        parsed = self.runner._parse_unittest_output(ROTATION_LOG_FRAGMENT)
        self.assertEqual(parsed['ran'], 4)
        self.assertEqual(parsed['failures'], 2)
        self.assertTrue(parsed['failed'])
        cases = parsed['cases']
        self.assertEqual(len(cases), 4,
                         '同一行串接两个方法头（subTest 截断父方法）时'
                         '用例不得丢失')
        ids = [case['id'] for case in cases]
        self.assertEqual(len(set(ids)), 4,
                         '每个完整 module.Class.method 只记一次')
        by_id = {case['id']: case['result'] for case in cases}
        expected = {
            'test_rotation_routes.RotationRoutes.'
            'test_other_rf_and_cv_orientations': 'FAIL',
            'test_rotation_routes.RotationRoutes.'
            'test_rf_270_does_not_move_its_collision_into_the_neighbor': 'FAIL',
            'test_rotation_routes.RotationRoutes.'
            'test_rf_and_cv_neighbors_reconciled': 'ok',
            'test_rotation_routes.RotationRoutes.'
            'test_symmetric_mirror_kept_under_rotation': 'ok',
        }
        self.assertEqual(by_id, expected)
        for case in cases:
            self.assertNotIn(' ', case['id'], '串接的方法名不得进 ID')
            self.assertNotIn(' ', case['result'], '串接的方法头不得塞进 result')

    def test_captured_truncated_output_marks_cases_unknown(self):
        parsed = self.runner._parse_unittest_output(TRUNCATED_LOG_FRAGMENT)
        by_id = {case['id']: case['result'] for case in parsed['cases']}
        self.assertEqual(by_id, {
            'test_rotation_routes.RotationRoutes.'
            'test_rotates_all_eight_directions': 'unknown',
            'test_rotation_routes.RotationRoutes.'
            'test_mirror_policy_holds': 'unknown',
        }, '进程被杀截断、无摘要可考的用例必须显式 unknown，不得臆断为 ok')

    def test_captured_docstring_tail_glued_header_keeps_both_cases(self):
        parsed = self.runner._parse_unittest_output(DOCSUB_LOG_FRAGMENT)
        self.assertEqual(parsed['ran'], 2)
        self.assertEqual(parsed['failures'], 1)
        self.assertTrue(parsed['failed'])
        cases = parsed['cases']
        self.assertEqual(len(cases), 2,
                         'docstring 首行行尾串接下一方法头时用例不得丢失')
        by_id = {case['id']: case['result'] for case in cases}
        self.assertEqual(by_id, {
            'docsub.Cases.test_a': 'FAIL',
            'docsub.Cases.test_b': 'ok',
        }, 'subTest 失败的 docstring 父方法由摘要区 FAIL: 标题纠正为 '
           'FAIL（不得窃取串接方法头的 ok），串接的后续成功方法不得丢失')
        for case in cases:
            self.assertNotIn(' ', case['id'])
            self.assertNotIn(' ', case['result'])


if __name__ == '__main__':
    unittest.main()
