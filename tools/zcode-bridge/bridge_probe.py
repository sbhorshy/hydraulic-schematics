"""One bounded, cancellable, read-only snapshot subprocess per bridge worker."""
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from bridge_contract import BridgeError, atomic_json, read_json, snapshot


def process_identity(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def recover_probe(directory):
    owner = Path(directory) / 'active-probe.json'
    if not owner.exists():
        return True
    record = read_json(owner)
    pid = record['pid']
    current = process_identity(pid)
    if current is not None and current != record['start']:
        return False  # Never signal a reused PID.
    if current is None:
        try:
            os.killpg(pid, 0)
        except ProcessLookupError:
            owner.unlink(missing_ok=True)
            return True
        return False  # An orphan group cannot be attributed from this record alone.
    try:
        if os.getpgid(pid) != pid:
            return False
        os.killpg(pid, signal.SIGKILL)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
                if fields[0] == 'Z':
                    break
            except FileNotFoundError:
                break
            time.sleep(.02)
        else:
            return False
    except ProcessLookupError:
        pass
    owner.unlink(missing_ok=True)
    return True


class ProbeProcess:
    def __init__(self, directory, cwd, state_root, task, timeout=30):
        self.directory = Path(directory)
        self.owner = self.directory / 'active-probe.json'
        self.config = self.directory / 'progress-probe.json'
        self.process = None
        self.timeout = timeout
        atomic_json(self.config, {'cwd': str(cwd), 'state_root': str(state_root),
                                 'patterns': task.get('allowed_files'),
                                 'forbidden': task.get('forbidden_files', [])})

    def command(self):
        return [sys.executable, str(Path(__file__).resolve()), str(self.config)]

    def start(self):
        if self.process is not None or self.owner.exists():
            raise BridgeError('A progress probe is already owned by this task')
        self.started = time.monotonic()
        self.process = subprocess.Popen(self.command(), stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            os.set_blocking(self.process.stdout.fileno(), False)
            identity = process_identity(self.process.pid)
            if identity is None:
                raise BridgeError('Cannot identify progress probe process')
            atomic_json(self.owner, {'pid': self.process.pid, 'start': identity})
        except BaseException:
            self.close()
            raise

    def poll(self):
        if self.process is None:
            return None
        elapsed = time.monotonic() - self.started
        if self.process.poll() is None:
            if elapsed < self.timeout:
                return None
            if not self.close():
                raise BridgeError('Progress probe cleanup unconfirmed')
            return {'error': 'timeout', 'elapsed': elapsed}
        process = self.process
        raw = process.stdout.read(4097) or b''
        ok = process.returncode == 0
        self.close()
        try:
            result = json.loads(raw) if ok and len(raw) <= 4096 else {}
            if not isinstance(result, dict) or not re.fullmatch('[a-f0-9]{64}', result.get('digest', '')):
                raise ValueError('Invalid probe result')
            return {'result': result, 'elapsed': elapsed}
        except (ValueError, TypeError):
            return {'error': 'snapshot_failed', 'elapsed': elapsed}

    def close(self):
        if self.process is None:
            return not self.owner.exists()
        process = self.process
        try:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        except ProcessLookupError:
            process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return False
        if process.stdout:
            process.stdout.close()
        self.process = None
        self.owner.unlink(missing_ok=True)
        return True


if __name__ == '__main__':
    config = read_json(sys.argv[1])
    result = snapshot(config['cwd'], config['state_root'], patterns=config['patterns'],
                      forbidden=config['forbidden'])
    print(json.dumps({'digest': result['digest']}))
