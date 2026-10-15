"""Stage policy, first-delivery verification, and zero-output recovery predicate."""
import copy
import hashlib
from pathlib import Path
import subprocess
import time

from bridge_contract import BridgeError, PathMatcher, atomic_json, execute_tests, snapshot, validate_delivery


def execution_defaults(task, mode='edit', policy='development'):
    task = copy.deepcopy(task)
    task.setdefault('reasoning_effort', 'high' if policy == 'development' else 'inherit')
    if 'first_delivery' not in task and mode != 'plan' and task.get('allowed_files') and task.get('tests'):
        task['first_delivery'] = {'files': task['allowed_files'], 'test_ids': [t['id'] for t in task['tests']],
                                  'warning_seconds': 180, 'timeout_seconds': 300}
    if mode == 'plan' and task.get('first_delivery'):
        raise BridgeError('First delivery requires a writing task')
    validate_delivery(task)
    return task


def zero_output_timeout(result):
    return (result.get('status') == 'timed_out' and result.get('cleanup_confirmed') is True
            and result.get('changed_files') == []
            and any(b in ('first_delivery_timeout','no_progress_timeout') for b in result.get('blockers', [])))


def verify_delivery(task, before, candidate, cwd, state_root, directory, deadline, cancelled, emit):
    delivery = task['first_delivery']
    folder = Path(directory) / 'first-delivery'
    folder.mkdir()
    matcher = PathMatcher(delivery['files'])
    empty = hashlib.sha256(b'').hexdigest()
    files = [name for name, value in candidate['files'].items() if matcher.matches(name)
             and value['kind'] == 'file' and value['sha256'] != empty
             and value['sha256'] != before['files'].get(name, {}).get('sha256')]
    report = {'status':'no_artifact', 'files':files, 'tests':[], 'source_unchanged':True,
              'source_digest':candidate['digest'], 'report_file':str(folder/'verification.json')}
    after = candidate
    if files:
        tests = [test for test in task['tests'] if test['id'] in delivery['test_ids']]
        emit({'type':'first_delivery.check_started','test_count':len(tests)})
        try:
            report.update(execute_tests({'tests':tests},cwd,folder,
                lambda: cancelled() or time.monotonic() >= deadline, emit))
            after = snapshot(cwd,state_root)
            report['source_unchanged'] = candidate['digest'] == after['digest']
            if not report['source_unchanged']:
                report['status'] = 'source_changed'
        except (BridgeError,OSError,ValueError,subprocess.SubprocessError) as exc:
            report.update(status='failed',error=str(exc),source_unchanged=False)
    if cancelled():
        report['status'] = 'cancelled'
    elif time.monotonic() >= deadline:
        report['status'] = 'timed_out'
    atomic_json(folder/'verification.json',report)
    emit({'type':'first_delivery.checked','status':report['status']})
    return report, after
