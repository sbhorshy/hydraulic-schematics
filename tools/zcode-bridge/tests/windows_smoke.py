"""Exercise real Windows transport with a local fixture, with no model calls."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from bridge_contract import atomic_json, read_json
from bridge_transport import WindowsBackend, ps_command


class FixtureWindows(WindowsBackend):
    def __init__(self):
        super().__init__()
        self.cli = Path(__file__).with_name('fake_cli.cjs').resolve()

    def doctor(self):
        return {'ready': True, 'probe': 'Windows fixture; no provider calls'}


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cwd = output / 'workspace'
    cwd.mkdir()
    subprocess.run(['git', 'init', '-q', str(cwd)], check=True)
    store = bridge.Store(output / 'state')
    rows = []
    for scenario, prompt, resume in [('long_prompt', "中文 $(DO_NOT_EXECUTE)`'\" " * 3000, None),
                                      ('resume', 'resume fixture', 'sess_explicit_fixture'),
                                      ('orphan_child', 'orphan', None),
                                      ('timeout_child', 'hang', None)]:
        request = {'cwd': str(cwd), 'mode': 'edit', 'resume': resume, 'timeout': 60,
                   'idle_timeout': 4 if scenario == 'timeout_child' else 30,
                   'run_tests': False, 'contract': {'version': 1, 'prompt': prompt,
                       'allowed_files': ['child.pid'], 'tests': []}}
        tid = store.create(request)
        result = bridge.worker(store, tid, FixtureWindows(), progress=False)
        expected = 'timed_out' if scenario == 'timeout_child' else 'completed'
        assert result['status'] == expected, result
        assert result['cleanup_confirmed'], result
        if scenario == 'long_prompt':
            response = json.loads(result['response'])
            assert response['length'] > 32767 and response['unicode'] and response['literal'], response
            assert set(response['disallowedTools'].split(',')) >= {'Bash', 'WebFetch', 'WebSearch', 'Agent', 'Task'}, response
        if scenario == 'resume':
            assert result['sessionId'] == resume, result
        if scenario in ('timeout_child', 'orphan_child'):
            child = int((cwd / 'child.pid').read_text())
            check = subprocess.run(ps_command(f'if (Get-Process -Id {child} -ErrorAction SilentlyContinue) {{ exit 1 }}; exit 0'),
                                   capture_output=True, timeout=20)
            assert check.returncode == 0, 'Owned Windows child survived cancellation'
        assert 'PRIVATE_WINDOWS_SENTINEL' not in (store.task(tid) / 'events.jsonl').read_text()
        rows.append({'scenario': scenario, 'task_id': tid, 'status': result['status'],
                     'cleanup_confirmed': result['cleanup_confirmed'], 'timings': result['timings']})
    env = dict(os.environ, ZCODE_BRIDGE_CLI=str(Path(__file__).with_name('fake_cli.cjs').resolve()))
    command = [sys.executable, str(Path(__file__).resolve().parents[1] / 'ask-zcode.py'),
               '--state-dir', str(store.root)]
    def cli(*args):
        response = subprocess.run(command + list(args), env=env, capture_output=True, text=True, timeout=40)
        return response.returncode, json.loads(response.stdout)
    code, submitted = cli('submit', 'hang', '--cwd', str(cwd), '--timeout', '60', '--idle-timeout', '30', '--tool-policy', 'code-local')
    assert code == 0, submitted
    task_id = submitted['task_id']
    # Wait for a real tool event before cancellation; avoid a scheduling race.
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        event_file = store.task(task_id) / 'events.jsonl'
        if event_file.exists() and 'tool.updated' in event_file.read_text():
            break
        time.sleep(.2)
    code, state = cli('status', task_id)
    assert state['status'] == 'running', state
    code, state = cli('cancel', task_id)
    assert code == 0, state
    code, final = cli('wait', task_id, '--timeout', '30')
    assert final['status'] == 'cancelled' and final['cleanup_confirmed'], final
    rows.append({'scenario': 'submit_status_cancel_wait', 'task_id': task_id, 'status': final['status'],
                 'cleanup_confirmed': final['cleanup_confirmed']})
    atomic_json(output / 'summary.json', {'passed': len(rows), 'provider_calls': 0, 'cases': rows})
    print(json.dumps({'passed': len(rows), 'provider_calls': 0, 'summary': str(output / 'summary.json')}))


if __name__ == '__main__':
    main()
