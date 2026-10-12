# -*- coding: utf-8 -*-
"""selftest_runner.py —— hydraulic-schematic 自检逐套件调度模块 v1。

深模块：把「逐套件独立进程 + 逐套件有界超时 + 有界并行 + 独占完整日志与
机器报告」的调度能力集中在此，供两处共用同一实现：

  * selftest.py 的 F 组——始终执行固定完整清单 L0_SUITES（24 模块）；
  * 本模块 CLI——对调用者点名的任意套件子集快速回归，如实报告所跑范围，
    不宣称完整自检通过（完整清单入口始终是 selftest.py，没有缩小范围却
    宣称完整通过的旁路）。

调度纪律（测试进程保护口径，不是构图/寻优预算）：
  * 每个套件 = 一个独立 `python -m unittest -v <suite>` 子进程，逐套件
    固定 -v，保证完整日志与机器报告都含每用例结果；
  * --suite-timeout（默认 600 秒）是单个套件测试进程的保护上限：超时只
    终止该套件自己的进程树（Windows: taskkill /F /T；POSIX: 进程组
    SIGKILL），不影响其他套件；
  * --jobs（默认 1，允许 1..4）为有界并行：同一时刻至多 N 个套件进程；
  * 失败 / 超时 / 启动失败 / 空发现（Ran 0） / 缺摘要行 / 全套跳过
    （all_skipped）一律不允许记为通过；总体 PASS 当且仅当每个套件
    status == 'passed'；
  * 每个套件的完整 stdout+stderr 落独立日志文件（并行时互不交错、不丢
    行）；--merged-log 按清单顺序整文件拼接合并；
  * --log-dir / --merged-log / --report 全部为新文件独占（'x' 语义），且
    在启动任何测试进程之前完成预留：路径有问题即整体报错退出，不覆盖
    旧证据、不留半程产物；失败清理只删除本次成功独占创建的文件/目录，
    绝不 unlink 调用者已有而本次未成功创建的路径；
  * 逐用例结果取自 -v 输出（日志文件保持子进程原样输出，不改写）：无
    docstring 时「method (module.Class) ... 结果」同行，有 docstring 时
    结果随文档首行另起一行，两种形态都不得丢用例；机器记录的用例 ID
    恒为 module.Class.method（unittest 括号里只给到类名，不是完整 ID）；
  * 启动前参数预检：suite-timeout 必须为有限正数（拒绝 NaN/Inf）；套件
    名必须是非空、不重复的 Python 点分模块名（拒绝路径分隔符/路径遍历；
    重复名会让两个 worker 写同一份套件日志）。

公开接口：
    run_suites(suites, *, cwd, jobs=1, suite_timeout=600.0, log_dir=None,
               merged_log_path=None, report_path=None, env=None,
               python=None) -> report(dict)
    read_log_tail(path, limit=1200) -> str
    print_summary(report) -> None
    DEFAULT_SUITE_TIMEOUT / MIN_JOBS / MAX_JOBS / SCHEMA / PreflightError

CLI：
    python selftest_runner.py [--jobs N] [--suite-timeout 秒]
                              [--log-dir 新目录] [--merged-log 新文件]
                              [--report 新文件] suite [suite ...]
退出码：0 全过 / 1 存在未过套件 / 2 用法或输出路径预检失败。
"""
import concurrent.futures
import datetime
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

DEFAULT_SUITE_TIMEOUT = 600.0
MIN_JOBS, MAX_JOBS = 1, 4
SCHEMA = 'hydraulic-selftest-runner/1'

_RAN_RE = re.compile(r'^Ran (\d+) tests? in ', re.M)
_VERDICT_OK_RE = re.compile(r'^OK\b', re.M)
_VERDICT_FAILED_RE = re.compile(r'^FAILED\b', re.M)
_COUNT_RES = (('failures', re.compile(r'failures=(\d+)')),
              ('errors', re.compile(r'errors=(\d+)')),
              ('skipped', re.compile(r'skipped=(\d+)')))
_CASE_INLINE_RE = re.compile(r'^(\S+) \(([^)]+)\) \.\.\. (.+?)\s*$')
# 带 docstring 时 unittest -v 先输出「method (module.Class)」独立一行，
# 结果追加在 docstring 首行行尾（「文档首行 ... ok」）
_CASE_HEAD_RE = re.compile(r'^(\S+) \(([^)]+)\)[ \t]*$')
_CASE_TAIL_RE = re.compile(r'^(.*) \.\.\. (ok|ERROR|FAIL|skipped\b.*|'
                           r'expected failure|unexpected success)[ \t]*$')

USAGE = ('用法: python selftest_runner.py [--jobs N(默认1,允许1..4)] '
         '[--suite-timeout 秒(默认600,有限正数,单套件测试进程保护上限,非构图预算)] '
         '[--log-dir 新目录] [--merged-log 新文件] [--report 新文件] '
         'suite [suite ...]（套件名须为不重复的 Python 点分模块名）')


class PreflightError(Exception):
    """输出路径/参数预检失败；在任何测试进程启动之前抛出。"""


def _child_env(env=None):
    merged = dict(os.environ if env is None else env)
    merged['PYTHONIOENCODING'] = 'utf-8'
    merged['PYTHONUTF8'] = '1'
    merged['PYTHONDONTWRITEBYTECODE'] = '1'
    return merged


def _utc_iso(epoch):
    return datetime.datetime.fromtimestamp(epoch, datetime.timezone.utc).isoformat()


def read_log_tail(path, limit=1200):
    """读取日志文件末尾至多 limit 字节（失败证据摘要用）。"""
    try:
        with open(path, 'rb') as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read().decode('utf-8', 'replace')
    except OSError:
        return '(无法读取日志 %s)' % path


def _parse_unittest_output(text):
    """从 unittest -v 输出解析套件级事实：用例数、判定、计数、逐用例结果。

    逐用例有两种形态：无 docstring 时「method (module.Class) ... 结果」同行；
    有 docstring 时先输出「method (module.Class)」独立一行，结果在 docstring
    首行行尾——两种都要识别，cases 不得丢。用例 ID 记 module.Class.method
    （unittest 的括号只给到 module.Class，不是完整 ID）。
    """
    ran_match = _RAN_RE.search(text)
    counts = {}
    for key, rx in _COUNT_RES:
        match = rx.search(text)
        counts[key] = int(match.group(1)) if match else 0
    cases = []
    pending = None   # 已见用例行头、等待 docstring 行给出结果的用例
    for line in text.splitlines():
        inline = _CASE_INLINE_RE.match(line)
        if inline:
            pending = None
            cases.append({'name': inline.group(1),
                          'id': '%s.%s' % (inline.group(2), inline.group(1)),
                          'result': inline.group(3)})
            continue
        if pending is not None:
            tail = _CASE_TAIL_RE.match(line)
            if tail:
                cases.append({'name': pending[0],
                              'id': '%s.%s' % (pending[1], pending[0]),
                              'result': tail.group(2)})
                pending = None
                continue
        head = _CASE_HEAD_RE.match(line)
        if head:
            pending = (head.group(1), head.group(2))
    return {
        'ran': int(ran_match.group(1)) if ran_match else None,
        'ok': bool(_VERDICT_OK_RE.search(text)),
        'failed': bool(_VERDICT_FAILED_RE.search(text)),
        'failures': counts['failures'],
        'errors': counts['errors'],
        'skipped': counts['skipped'],
        'cases': cases,
    }


def _kill_process_tree(proc):
    """只终止 proc 自己的进程树（套件子进程 + 其浏览器等后代），不碰他人。"""
    if os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _run_suite_process(suite, command, cwd, env, timeout, log_path):
    """运行单个套件子进程并产出记录 dict；进程级异常都落在记录里，不上抛。"""
    started = time.time()
    record = {'suite': suite, 'command': list(command), 'status': 'startup_error',
              'exit_code': None, 'timed_out': False, 'duration_seconds': None,
              'log': os.path.abspath(log_path), 'tests_ran': None,
              'failures': None, 'errors': None, 'skipped': None,
              'cases': [], 'detail': ''}
    try:
        handle = open(log_path, 'wb')
    except OSError as error:
        record['detail'] = '无法打开套件日志 %s: %s' % (log_path, error)
        record['duration_seconds'] = time.time() - started
        return record
    try:
        popen_kwargs = {'cwd': cwd, 'env': env, 'stdout': handle,
                        'stderr': subprocess.STDOUT}
        if os.name != 'nt':
            # POSIX 下自成进程组，超时可整组终止而不伤其他任务
            popen_kwargs['start_new_session'] = True
        proc = subprocess.Popen(command, **popen_kwargs)
    except OSError as error:
        handle.close()
        record['detail'] = '无法启动套件进程: %s' % error
        record['duration_seconds'] = time.time() - started
        return record
    handle.close()
    timed_out = False
    try:
        exit_code = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_process_tree(proc)
        exit_code = proc.returncode
    record['exit_code'] = exit_code
    record['timed_out'] = timed_out
    record['duration_seconds'] = time.time() - started
    try:
        with open(log_path, 'rb') as fresh:
            text = fresh.read().decode('utf-8', 'replace')
    except OSError:
        text = ''
    parsed = _parse_unittest_output(text)
    record['tests_ran'] = parsed['ran']
    record['failures'] = parsed['failures']
    record['errors'] = parsed['errors']
    record['skipped'] = parsed['skipped']
    record['cases'] = parsed['cases']
    if timed_out:
        record['status'] = 'timeout'
        record['detail'] = ('超过 %.0f 秒套件测试进程保护上限（非构图预算），'
                            '已终止该套件进程树；被杀前输出保留于套件日志'
                            % timeout)
    elif parsed['ran'] is None:
        record['status'] = 'no_summary'
        record['detail'] = '输出缺少「Ran N tests」摘要行，无法证实任何用例运行'
    elif parsed['ran'] == 0:
        record['status'] = 'no_tests'
        record['detail'] = '该套件发现 0 个用例（空发现不允许记为通过）'
    elif exit_code != 0:
        record['status'] = 'failed'
        record['detail'] = ('退出码 %s（失败/错误用例或模块导入失败）：'
                            'ran=%s failures=%s errors=%s skipped=%s'
                            % (exit_code, parsed['ran'], parsed['failures'],
                               parsed['errors'], parsed['skipped']))
    elif parsed['skipped'] >= parsed['ran']:
        record['status'] = 'all_skipped'
        record['detail'] = ('全套 %s 个用例均被跳过（skipped=%s），没有任何'
                            '用例真正执行，不允许记为通过'
                            % (parsed['ran'], parsed['skipped']))
    elif parsed['ok'] and not parsed['failed']:
        record['status'] = 'passed'
    else:
        record['status'] = 'no_verdict'
        record['detail'] = '退出码 0 但缺少 OK 判定行，fail-closed 记为未通过'
    return record


def run_suites(suites, *, cwd, jobs=1, suite_timeout=DEFAULT_SUITE_TIMEOUT,
               log_dir=None, merged_log_path=None, report_path=None,
               env=None, python=None):
    """逐套件独立进程执行 unittest 套件清单，返回机器可读报告 dict。

    参数：
      suites            unittest 模块名清单（无 .py 后缀），按此顺序汇报与合并；
      cwd               子进程工作目录（套件模块所在处）；
      jobs              并行度，允许 1..4，默认 1；
      suite_timeout     单套件测试进程保护上限秒数，默认 600（非构图预算）；
      log_dir           逐套件独立日志目录；None=自动临时目录（由调用者决定
                        是否保留，报告里有路径）；显式给出时必须不存在；
      merged_log_path   合并完整日志路径，新文件独占，None=不写；
      report_path       机器 JSON 报告路径，新文件独占，None=不写；
      env               子进程环境基线（会强制 UTF-8 输出开关）；
      python            解释器，默认当前 sys.executable。

    任何输出路径问题都在启动任何测试进程之前以 PreflightError 报错；
    套件失败/超时/启动失败/空发现不上抛，落在各套件记录与 summary 里。
    """
    suites = list(suites)
    if not suites:
        raise ValueError('套件清单不能为空')
    seen = set()
    for suite in suites:
        if (not isinstance(suite, str) or not suite
                or not all(part.isidentifier() for part in suite.split('.'))):
            raise ValueError(
                '套件名 %r 非法：只接受 Python 点分模块名（拒绝空名、路径'
                '分隔符与路径遍历）' % (suite,))
        if suite in seen:
            raise ValueError('套件 %r 重复：两个 worker 会写同一份套件日志，'
                             '拒绝执行' % suite)
        seen.add(suite)
    try:
        jobs = int(jobs)
    except (TypeError, ValueError):
        raise ValueError('--jobs 需为整数，收到 %r' % (jobs,))
    if not MIN_JOBS <= jobs <= MAX_JOBS:
        raise ValueError('--jobs 允许 %d..%d，收到 %d' % (MIN_JOBS, MAX_JOBS, jobs))
    try:
        suite_timeout = float(suite_timeout)
    except (TypeError, ValueError):
        raise ValueError('--suite-timeout 需为数字，收到 %r' % (suite_timeout,))
    if not math.isfinite(suite_timeout) or suite_timeout <= 0:
        raise ValueError('--suite-timeout 需为有限正数，收到 %r' % suite_timeout)
    python = python or sys.executable
    cwd = os.path.abspath(cwd)
    child_env = _child_env(env)
    started = time.time()

    owns_dir = log_dir in (None, '')
    if owns_dir:
        log_dir = tempfile.mkdtemp(prefix='selftest-suites-')
    dir_created = owns_dir
    log_paths = {suite: os.path.join(log_dir, suite + '.log') for suite in suites}
    created = []   # 仅登记本次成功独占创建的路径；清理绝不碰调用者已有文件
    merged_handle = None
    report_handle = None
    try:
        if not owns_dir:
            os.makedirs(log_dir)
            dir_created = True
        for suite, path in log_paths.items():
            reserve = open(path, 'xb')
            reserve.close()
            created.append(path)
        if merged_log_path:
            merged_handle = open(merged_log_path, 'xb')
            created.append(merged_log_path)
        if report_path:
            report_handle = open(report_path, 'xb')
            created.append(report_path)
    except OSError as error:
        for handle in (merged_handle, report_handle):
            if handle is not None:
                handle.close()
        for path in created:
            try:
                os.unlink(path)
            except OSError:
                pass
        if dir_created:
            shutil.rmtree(log_dir, ignore_errors=True)
        raise PreflightError(
            '输出路径预检失败（未启动任何测试进程）: %s' % error) from error

    commands = {suite: [python, '-m', 'unittest', '-v', suite]
                for suite in suites}
    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {suite: pool.submit(_run_suite_process, suite, commands[suite],
                                      cwd, child_env, suite_timeout,
                                      log_paths[suite])
                   for suite in suites}
        # 汇报顺序恒等于清单顺序，与完成顺序无关
        records = [futures[suite].result() for suite in suites]

    if merged_handle is not None:
        try:
            for record in records:
                header = ('===== SUITE %s | %s | status=%s | %.1fs =====\n'
                          % (record['suite'], ' '.join(record['command']),
                             record['status'],
                             record['duration_seconds'] or 0.0))
                try:
                    with open(record['log'], 'rb') as fresh:
                        body = fresh.read()
                except OSError:
                    body = ('(无法读取套件日志 %s)\n'
                            % record['log']).encode('utf-8')
                merged_handle.write(header.encode('utf-8'))
                merged_handle.write(body)
                if not body.endswith(b'\n'):
                    merged_handle.write(b'\n')
                merged_handle.write(b'\n')
        finally:
            merged_handle.close()

    finished = time.time()
    by_status = {}
    for record in records:
        by_status[record['status']] = by_status.get(record['status'], 0) + 1
    summary = {
        'status': 'PASS' if all(r['status'] == 'passed' for r in records)
                  else 'FAIL',
        'suites_total': len(records),
        'suites_by_status': by_status,
        'tests_ran': sum(r['tests_ran'] or 0 for r in records),
        'failures': sum(r['failures'] or 0 for r in records),
        'errors': sum(r['errors'] or 0 for r in records),
        'skipped': sum(r['skipped'] or 0 for r in records),
    }
    report = {
        'schema': SCHEMA,
        'started_at': _utc_iso(started),
        'finished_at': _utc_iso(finished),
        'wall_seconds': round(finished - started, 3),
        'jobs': jobs,
        'suite_timeout_seconds': suite_timeout,
        'python': python,
        'cwd': cwd,
        'log_dir': os.path.abspath(log_dir),
        'merged_log': os.path.abspath(merged_log_path) if merged_log_path else None,
        'report': os.path.abspath(report_path) if report_path else None,
        'suites': records,
        'summary': summary,
    }
    if report_handle is not None:
        try:
            report_handle.write(json.dumps(report, ensure_ascii=False,
                                           indent=2).encode('utf-8'))
        finally:
            report_handle.close()
    return report


def print_summary(report):
    for record in report['suites']:
        print('[%s] %-32s %7.1fs ran=%s failures=%s errors=%s skipped=%s'
              % (record['status'], record['suite'],
                 record['duration_seconds'] or 0.0,
                 record['tests_ran'] if record['tests_ran'] is not None else '?',
                 record['failures'], record['errors'], record['skipped']))
        if record['status'] != 'passed':
            print('       %s' % record['detail'])
            tail = read_log_tail(record['log'], 800)
            if tail:
                print('       输出尾部：\n       %s'
                      % tail.replace('\n', '\n       '))
    summary = report['summary']
    print('selftest-runner: %s | 套件 %s/%s 通过 | 用例 %s | 失败 %s 错误 %s '
          '跳过 %s | jobs=%s suite-timeout=%ss'
          % (summary['status'], summary['suites_by_status'].get('passed', 0),
             summary['suites_total'], summary['tests_ran'],
             summary['failures'], summary['errors'], summary['skipped'],
             report['jobs'], report['suite_timeout_seconds']))
    print('套件日志目录: %s' % report['log_dir'])
    if report['merged_log']:
        print('完整日志: %s' % report['merged_log'])
    if report['report']:
        print('机器报告: %s' % report['report'])


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError, OSError):
            pass
    args = list(sys.argv[1:] if argv is None else argv)
    options = {'--jobs': '1', '--suite-timeout': str(DEFAULT_SUITE_TIMEOUT),
               '--log-dir': None, '--merged-log': None, '--report': None}
    suites = []
    index = 0
    while index < len(args):
        token = args[index]
        if token in options:
            if index + 1 >= len(args):
                sys.stderr.write('selftest-runner: %s 缺参数值\n%s\n'
                                 % (token, USAGE))
                return 2
            options[token] = args[index + 1]
            index += 2
        else:
            suites.append(token)
            index += 1
    if not suites:
        sys.stderr.write('selftest-runner: 至少需要一个套件名\n%s\n' % USAGE)
        return 2
    try:
        report = run_suites(suites, cwd=os.getcwd(), jobs=options['--jobs'],
                            suite_timeout=options['--suite-timeout'],
                            log_dir=options['--log-dir'],
                            merged_log_path=options['--merged-log'],
                            report_path=options['--report'])
    except (ValueError, PreflightError) as error:
        sys.stderr.write('selftest-runner: %s\n%s\n' % (error, USAGE))
        return 2
    print_summary(report)
    return 0 if report['summary']['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
