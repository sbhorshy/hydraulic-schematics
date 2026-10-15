"""Exercise development protocol through the real Windows process transport."""
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from bridge_contract import atomic_json
from bridge_transport import WindowsBackend, ps_command


class Fixture(WindowsBackend):
    def __init__(self):
        super().__init__()
        self.cli = Path(__file__).with_name('fake_protocol.cjs').resolve()

    def doctor(self):
        return {'ready': True}


def main():
    output = Path(sys.argv[1]).resolve()
    output.mkdir(parents=True, exist_ok=False)
    cwd = output / 'workspace'
    cwd.mkdir()
    subprocess.run(['git', 'init', '-q', str(cwd)], check=True)
    store = bridge.Store(output / 'state')
    rows = []
    for scenario, resume in [('allow_only', None), ('allow_only resume', 'sess_protocol_fixture'), ('hang', None)]:
        request = {'cwd': str(cwd), 'mode': 'edit', 'resume': resume,
                   'timeout': 50, 'idle_timeout': 4 if scenario == 'hang' else 25,
                   'progress_warning': .2,
                   'run_tests': False, 'tool_policy': 'development', 'expected_model': 'fixture-model',
                   'contract': {'version': 1, 'prompt': scenario, 'allowed_files': ['child.pid'],
                                'requires_shell': True, 'tests': []}}
        tid = store.create(request)
        result = bridge.worker(store, tid, Fixture(), progress=False)
        assert result['status'] == ('timed_out' if scenario == 'hang' else 'completed'), result
        assert result['cleanup_confirmed'], result
        assert 'PRIVATE_PROTOCOL_SENTINEL' not in (store.task(tid) / 'events.jsonl').read_text()
        if scenario == 'hang':
            assert result['progress']['probe_mode'] == 'process'
            assert result['progress']['probe_count'] >= 1, result
            assert not result['progress']['probe_inflight'], result
            pid = int((cwd / 'child.pid').read_text())
            p = subprocess.run(ps_command(f'if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 1 }}; exit 0'),
                               capture_output=True, timeout=20)
            assert p.returncode == 0, 'Nested owned child survived cancellation'
        rows.append({'scenario': scenario, 'task_id': tid, 'status': result['status'], 'cleanup_confirmed': True})
    atomic_json(output / 'summary.json', {'passed': len(rows), 'provider_calls': 0, 'cases': rows})
    print(json.dumps({'passed': len(rows), 'provider_calls': 0}))


if __name__ == '__main__':
    main()
