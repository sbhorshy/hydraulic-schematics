"""Separate liveness from observed artifacts and distinct test/build results."""
import time
import subprocess

from bridge_contract import BridgeError, snapshot


class _InlineProbe:
    """Synchronous adapter for deterministic tracker tests; workers use ProbeProcess."""
    def __init__(self, probe):
        self.probe = probe

    def start(self):
        started = time.monotonic()
        try:
            self.ready = {'result': self.probe()}
        except (BridgeError, OSError, ValueError, subprocess.SubprocessError):
            self.ready = {'error': 'snapshot_failed'}
        self.ready['elapsed'] = time.monotonic() - started

    def poll(self):
        return self.ready


class ProgressTracker:
    def __init__(self, started, warning, timeout, probe, initial_digest):
        self.warning = warning
        self.started = started
        self.timeout = timeout
        self.probe = probe
        self.interval = max(.05, min(5, warning, timeout / 3 if timeout else 5))
        self.cooldown = self.interval
        self.runner = probe if hasattr(probe, 'poll') else _InlineProbe(lambda: self.probe())
        self.inflight = False
        self.generation = 0
        self.flight_checks = []
        self.last_probe = self.last_tool = self.last_output = started
        self.last_stream = None
        self.active = {}
        self.dirty = False
        self.pending_checks = []
        self.seen_outputs = {initial_digest}
        self.seen_checks = set()
        self.seen_children = set()
        self.digest = initial_digest
        self.warned = False
        self.data = {'last_tool_completed_at': None, 'last_write_tool_at': None,
                     'last_command_completed_at': None, 'last_check_completed_at': None,
                     'last_artifact_observed_at': None, 'last_output_at': None,
                     'first_artifact_observed_at': None, 'time_to_first_artifact_seconds': None,
                     'output_kind': None, 'artifact_changes': 0, 'distinct_checks': 0,
                     'command_completions': 0, 'model_frames': 0, 'model_bytes': 0,
                     'probe_failures': 0, 'probe_seconds': 0,
                     'probe_count': 0, 'probe_timeouts': 0, 'probe_abandoned': 0,
                     'probe_mode': 'process' if hasattr(probe, 'poll') else 'inline',
                     'probe_control_seconds': 0,
                     'warning_after_seconds': warning, 'stop_after_seconds': timeout}

    def output(self, now, stamp, kind):
        self.last_output = now
        self.warned = False
        self.data.update(last_output_at=stamp, output_kind=kind)

    def observe(self, event, now, stamp):
        kind = event['type']
        if kind == 'model.activity':
            self.last_stream = now
            self.data['model_frames'] += 1
            self.data['model_bytes'] += event.get('bytes', 0)
            self.data['model_phase'] = event.get('phase', 'model_streaming')
        elif kind == 'subagent.completed' and event.get('callId') and event['callId'] not in self.seen_children:
            self.seen_children.add(event.get('callId'))
            self.output(now, stamp, 'subagent_result')
        elif kind == 'tool.updated':
            call = event.get('tool_call_id')
            if event['phase'] == 'started':
                self.active[call] = event.get('tool', 'unknown')
                if event.get('tool') in ('Bash', 'Edit', 'Write', 'ApplyPatch'):
                    self.dirty = True
                    self.generation += 1
                return
            tool = self.active.pop(call, 'unknown')
            event.setdefault('tool', tool)
            if event.get('success'):
                self.last_tool = now
                self.data['last_tool_completed_at'] = stamp
                if event['tool'] in ('Edit', 'Write', 'ApplyPatch'):
                    self.data['last_write_tool_at'] = stamp
                    self.dirty = True
                    self.generation += 1
            if event['tool'] == 'Bash':
                self.data['last_command_completed_at'] = stamp
                self.data['command_completions'] += 1
                self.dirty = True
                self.generation += 1
                check = event.get('command', {})
                if event.get('success') and check.get('category') in ('test', 'build') and type(check.get('exit_code')) is int and check.get('status') in ('completed', 'failed') and check.get('id'):
                    self.pending_checks.append(check)
                    self.data['last_check_completed_at'] = stamp
                    self.data['last_check_exit_code'] = check['exit_code']

    def refresh(self, now, stamp, force=False):
        started = time.monotonic()
        try:
            self._refresh(now, stamp, force)
        finally:
            self.data['probe_control_seconds'] += time.monotonic() - started

    def _refresh(self, now, stamp, force):
        # Poll first, consume all events on the main loop, and keep at most one
        # read-only helper. No waiting for a filesystem scan here.
        if not self.inflight:
            if (not force and now - self.last_probe < self.cooldown) or not (self.dirty or self.pending_checks):
                return
            self.flight_started = now
            self.flight_generation = self.generation
            self.flight_checks, self.pending_checks = self.pending_checks, []
            self.runner.start()
            self.inflight = True
        completed = self.runner.poll()
        if completed is None:
            return
        self.inflight = False
        elapsed = completed['elapsed']
        self.last_probe = max(now, self.flight_started + elapsed)
        self.cooldown = max(self.interval, min(60, self.timeout / 3 if self.timeout else 60, elapsed * 4))
        self.data['probe_seconds'] += elapsed
        self.data['probe_count'] += 1
        if completed.get('error'):
            self.data['probe_failures'] += 1
            self.data['probe_timeouts'] += completed['error'] == 'timeout'
            self.pending_checks = self.flight_checks + self.pending_checks
            self.flight_checks = []
            self.dirty = True
            return
        self._accept(completed['result'], self.flight_checks, now, stamp)
        self.flight_checks = []
        self.dirty = self.generation != self.flight_generation or any(
            tool in ('Bash', 'Edit', 'Write', 'ApplyPatch') for tool in self.active.values())

    def _accept(self, current, checks, now, stamp):
        self.digest = current['digest']
        if self.digest not in self.seen_outputs:
            self.seen_outputs.add(self.digest)
            self.data['artifact_changes'] += 1
            if self.data['first_artifact_observed_at'] is None:
                self.data['first_artifact_observed_at'] = stamp
                self.data['time_to_first_artifact_seconds'] = max(0,now-self.started)
            self.data['last_artifact_observed_at'] = stamp
            self.output(now, stamp, 'file_change')
        for check in checks:
            key = (check['id'], self.digest, check['exit_code'])
            if key not in self.seen_checks:
                self.seen_checks.add(key)
                self.data['distinct_checks'] += 1
                self.output(now, stamp, check['category'] + '_result')

    def finish(self, current, now, stamp):
        """Consume final evidence after helper and executor cleanup, without polling."""
        self._accept(current, self.flight_checks + self.pending_checks, now, stamp)
        self.flight_checks = []
        self.pending_checks = []
        self.inflight = False
        self.dirty = False

    def stopped(self, now):
        if self.inflight:
            self.data['probe_abandoned'] += 1
            self.data['probe_seconds'] += max(0, now - self.flight_started)
            self.inflight = False

    def status(self, now):
        phase = ('tool_running' if self.active else
                 self.data.get('model_phase', 'model_streaming') if self.last_stream is not None and now - self.last_stream < 5
                 else 'waiting_model')
        return {**self.data, 'seconds_without_tool_completion': max(0, now - self.last_tool),
                'seconds_without_output': max(0, now - self.last_output),
                'probe_inflight': self.inflight, 'probe_cooldown_seconds': self.cooldown,
                'warning_active': self.warned, 'active_tools': sorted(set(self.active.values())),
                'phase': phase}


def progress_probe(cwd, state_root, task):
    return snapshot(cwd, state_root, patterns=task.get('allowed_files'), forbidden=task.get('forbidden_files', []))
