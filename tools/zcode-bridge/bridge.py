"""Persistent single-task bridge with safe progress and controller validation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
import uuid

from bridge_contract import (BridgeError, atomic_json, changes, contract, execute_tests,
                             positive, read_json, snapshot)
from bridge_transport import WindowsBackend, ROOT
from bridge_progress import ProgressTracker, progress_probe
from bridge_probe import ProbeProcess, recover_probe
from bridge_delivery import execution_defaults, verify_delivery

TERMINAL = {'completed', 'blocked_permission', 'needs_clarification', 'timed_out',
            'cancelled', 'failed', 'scope_violation', 'validation_failed', 'cleanup_failed',
            'model_mismatch', 'model_unverified'}
EXITS = {'completed': 0, 'failed': 1, 'scope_violation': 3, 'blocked_permission': 4,
         'needs_clarification': 5, 'validation_failed': 6, 'cleanup_failed': 7,
         'timed_out': 124, 'cancelled': 130, 'model_mismatch': 8, 'model_unverified': 8}
ID = re.compile(r'^[A-Za-z0-9_.-]{1,160}$')
USAGE_KEYS = {'modelRequestCount', 'inputTokens', 'outputTokens', 'totalTokens',
              'cacheReadTokens', 'cacheWriteTokens', 'reasoningTokens',
              'webFetchRequests', 'webSearchRequests'}


def utc():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def identity(pid):
    try:
        # starttime after the final ')' so spaces in a process name are safe.
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def cwd_key(cwd):
    value = str(Path(cwd).resolve())
    if re.match(r'^/mnt/[a-zA-Z]/', value):
        value = value.casefold()  # Windows paths are case-insensitive here.
    return hashlib.sha256(value.encode()).hexdigest()


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (self.root / 'locks').mkdir(exist_ok=True)

    def task(self, tid):
        if not ID.fullmatch(tid) or tid in ('.', '..'):
            raise BridgeError('Invalid task ID')
        directory = self.root / tid
        if not directory.is_dir() or directory.is_symlink():
            raise BridgeError('Unknown task ID')
        return directory

    def create(self, request):
        tid = 'task-' + uuid.uuid4().hex
        directory = self.root / tid
        directory.mkdir(mode=0o700)
        request.update(task_id=tid, created_at=utc())
        atomic_json(directory / 'request.json', request)
        atomic_json(directory / 'state.json', {'task_id': tid, 'status': 'queued',
                    'cwd': request['cwd'], 'created_at': request['created_at']})
        return tid

    def lock(self, cwd, allow_unsafe=False):
        path = self.root / 'locks' / cwd_key(cwd)
        handle = path.open('a+')
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if (path.with_suffix('.unsafe.json').exists() or path.with_suffix('.active.json').exists()) and not allow_unsafe:
                raise BridgeError('Previous process cleanup unconfirmed; run recover for that task first')
        except (BlockingIOError, BridgeError) as exc:
            handle.close()
            raise BridgeError('cwd is busy' if isinstance(exc, BlockingIOError) else str(exc)) from None
        return handle

    def unsafe(self, cwd, tid):
        atomic_json(self.root / 'locks' / (cwd_key(cwd) + '.unsafe.json'), {'task_id': tid})

    def status(self, tid):
        state = read_json(self.task(tid) / 'state.json')
        if state['status'] not in TERMINAL and state.get('worker_pid'):
            if identity(state['worker_pid']) != state.get('worker_start'):
                state['worker_missing'] = True
                state['guidance'] = 'cancel or recover this task before retrying; files may be partially written'
        return state


def safe_event(raw):
    """Never forward arbitrary payload fields or strings from tool output."""
    if not isinstance(raw, dict):
        return None
    kind = raw.get('type')
    p = raw.get('payload')
    p = p if isinstance(p, dict) else {}
    result = {'type': kind}
    if kind in ('transport.heartbeat', 'model.streaming'):
        phase = p.get('phase')
        result = {'type': 'model.activity', 'phase': phase if phase in ('model_streaming', 'model_output', 'tool_input') else 'model_streaming'}
        if type(p.get('bytes')) is int and 0 <= p['bytes'] <= 8 * 1024 * 1024:
            result['bytes'] = p['bytes']
        return result
    if kind == 'reasoning.selected':
        return {'type':kind, 'requested':p.get('requested') if p.get('requested') in ('low','high','max','inherit') else None,
                'effective':p.get('effective') if isinstance(p.get('effective'),str) and ID.fullmatch(p['effective']) else None}
    if kind == 'configuration.error' and p.get('code') in ('reasoning_unsupported','reasoning_configuration_failed','reasoning_mismatch'):
        return {'type':kind, 'code':p['code'], 'available':[x for x in p.get('available',[]) if x in ('low','high','max')]}
    sid = raw.get('sessionId')
    if isinstance(sid, str) and ID.fullmatch(sid):
        result['session_id'] = sid
    if kind == 'session.updated' and isinstance(p.get('modelId'), str) and ID.fullmatch(p['modelId']):
        result.update(type='model.selected', model_id=p['modelId'])
        if isinstance(p.get('providerId'), str) and ID.fullmatch(p['providerId']):
            result['provider_id'] = p['providerId']
        return result
    if kind in ('session.created', 'session.resumed', 'turn.started', 'turn.completed', 'turn.failed'):
        return result
    if kind == 'tool.updated':
        phase = p.get('kind')
        if phase not in ('started', 'result', 'error'):
            return None
        result['phase'] = phase
        for source, dest in [('toolName', 'tool'), ('toolCallId', 'tool_call_id'), ('childSessionId', 'child_session_id'), ('agentId', 'agent_id')]:
            value = p.get(source)
            if isinstance(value, str) and ID.fullmatch(value):
                result[dest] = value
        tool_result = p.get('result') if isinstance(p.get('result'), dict) else {}
        error = p.get('error') or tool_result.get('error')
        message = error.get('message', '') if isinstance(error, dict) else error if isinstance(error, str) else ''
        message = message if isinstance(message, str) else ''
        failed = phase == 'error' or bool(error) or tool_result.get('success') is False or tool_result.get('isError') is True
        if phase != 'started':
            result['success'] = not failed
        command = p.get('command')
        if isinstance(command, dict) and type(command.get('exit_code')) is int and command.get('status') in ('completed', 'failed'):
            result['command'] = {'exit_code': command['exit_code'], 'status': command['status'],
                                 'category': command.get('category') if command.get('category') in ('test', 'build') else 'other'}
            if isinstance(command.get('id'), str) and re.fullmatch('[a-f0-9]{64}', command['id']):
                result['command']['id'] = command['id']
        if failed:
            lowered = message.lower()
            result['error_code'] = next((code for patterns, code in [
                (('no permission client configured',), 'permission_client_missing'),
                (('enoent', 'no such file', 'file not found', 'does not exist'), 'not_found'),
                (('eacces', 'permission denied'), 'permission_denied'),
                (('timeout', 'timed out'), 'timeout'),
                (('econnreset', 'tls connection', 'fetch failed', 'enotfound'), 'network_error'),
                (('invalid argument', 'validation'), 'invalid_input'),
                (('not unique', 'multiple matches', 'ambiguous'), 'ambiguous_match'),
            ] if any(p in lowered for p in patterns)), 'tool_failed')
        return result
    if kind in ('permission.requested', 'permission.resolved'):
        if p.get('decision') in ('allow', 'deny', 'ask'):
            result['decision'] = p['decision']
        if isinstance(p.get('toolName'), str) and ID.fullmatch(p['toolName']):
            result['tool'] = p['toolName']
        return result
    if kind in ('subagent.queued', 'subagent.started', 'subagent.completed', 'subagent.failed', 'subagent.cancelled'):
        for key in ('callId', 'childSessionId', 'parentToolCallId'):
            if isinstance(p.get(key), str) and ID.fullmatch(p[key]):
                result[key] = p[key]
        result['usage'] = {k: v for k, v in p.get('usage', {}).items()
                           if k in USAGE_KEYS and type(v) is int and v >= 0} if isinstance(p.get('usage'), dict) else {}
        result['usage_complete'] = p.get('usageComplete') is True
        return result
    return None


def terminal_result(raw):
    if not isinstance(raw, dict) or raw.get('type') != 'result':
        return None
    if not isinstance(raw.get('sessionId'), str) or not ID.fullmatch(raw['sessionId']):
        raise BridgeError('Invalid terminal sessionId')
    if not isinstance(raw.get('response'), str):
        raise BridgeError('Invalid terminal response')
    result = {'sessionId': raw['sessionId'], 'response': raw['response']}
    if isinstance(raw.get('usageComplete'), bool):
        result['usage_complete'] = raw['usageComplete']
    if isinstance(raw.get('subagents'), dict):
        children = raw['subagents']
        result['subagents'] = {k: v for k, v in children.items()
                               if k in ('calls', 'completed', 'failed') and type(v) is int and v >= 0}
        result['subagents']['usage_complete'] = children.get('usage_complete') is True
        result['subagents']['usage'] = {k: v for k, v in children.get('usage', {}).items()
                                        if k in USAGE_KEYS and type(v) is int and v >= 0} if isinstance(children.get('usage'), dict) else {}
    for name in ('traceId', 'turnId'):
        if isinstance(raw.get(name), str) and ID.fullmatch(raw[name]):
            result[name] = raw[name]
    usage = raw.get('usage', {})
    result['usage'] = {k: v for k, v in usage.items() if k in USAGE_KEYS and type(v) is int and v >= 0} if isinstance(usage, dict) else {}
    if isinstance(usage, dict) and usage.get('source') == 'provider':
        result['usage']['source'] = 'provider'
    projection = raw.get('projection', {})
    result['projection'] = {k: v for k, v in projection.items()
                            if (k == 'status' and v in ('idle', 'running', 'error', 'failed', 'interrupted', 'waiting'))
                            or (k in ('turnCount', 'totalTokenCount', 'contextUsed', 'contextWindow') and (v is None or type(v) is int))} if isinstance(projection, dict) else {}
    if type(raw.get('eventCount')) is int:
        result['eventCount'] = raw['eventCount']
    return result


def read_pipe(pipe, channel, output, stop):
    # Bound individual lines and queue length; unknown/raw data is never persisted.
    def send(value):
        while not stop.is_set():
            try:
                output.put(value, timeout=.1)
                return
            except queue.Full:
                pass
    try:
        while not stop.is_set():
            line = pipe.readline(2 * 1024 * 1024 + 1)
            if not line:
                break
            if len(line) > 2 * 1024 * 1024:
                send(('protocol_error', None))
                break
            if channel == 'stderr':
                send(('stderr', len(line)))
                lowered = line.lower()
                for marker, code in ((b'vsock', 'windows_interop_unavailable'),
                                     (b'no permission client configured', 'permission_client_missing'),
                                     (b'unknown option', 'unsupported_cli_option'),
                                     (b'cannot find module', 'cli_module_missing')):
                    if marker in lowered:
                        send(('diagnostic', code))
                continue
            try:
                value = json.loads(line.decode('utf-8-sig'))
            except (ValueError, UnicodeError):
                send(('protocol_error', None))
            else:
                send(('event', value))
    finally:
        send((channel + '_eof', None))
        pipe.close()


def prompt_for(request):
    task = request['contract']
    policy = request.get('tool_policy', task.get('tool_policy', 'code-local'))
    guidance = ('\n\n[Bridge execution contract]\n'
                'Do not retry shell execution or dispatch another agent to bypass permission failures. '
                'Distinguish your own checks from independent controller verification. '
                'If blocked, state BLOCKED-PERMISSION: or NEED-CLARIFICATION: explicitly.\n')
    if policy == 'development':
        guidance += ('You may use Bash to build, test, inspect git and debug; use WebFetch/WebSearch for task-related documentation. '
                     'Bash timeout is in milliseconds (e.g. 120000 for two minutes). '
                     'Commands execute on the Windows host, not in an OS sandbox. Stay within the task workspace and file scope. '
                     'Do not access credentials, publish, push, deploy or change global configuration. '
                     'TEAM coordinates parallel work. Do not leave background commands running. '
                     'Record commands actually run and their outcomes.\n')
        if request.get('allow_subagents', task.get('allow_subagents', False)):
            guidance += ('Agent/Task may delegate read-only investigation or review using Explore or general-purpose. '
                         'Delegate independent questions when parallel investigation helps; handle simple work directly. '
                         'Maximum 2 concurrent children, 1 level, 8 calls per task, 12 turns per child. '
                         'Children have Read/Glob/Grep/WebFetch/WebSearch only, no Bash, edits, skills or further agents. '
                         'All calls finish in the foreground; background requests are forced to wait. '
                         'Summarize findings before finishing. Writing delegation requires a controller TEAM task.\n')
        else:
            guidance += 'Do not spawn agents; Agent/Task are disabled for this task.\n'
    if task.get('first_delivery'):
        guidance += ('This call is one runnable stage. Finish this stage and return for independent verification; '
                     'do not implement later stages. Empty files and TODO skeletons are not delivery. '
                     'The controller requires changed target source plus declared behavior checks.\n'
                     + 'First delivery: ' + json.dumps(task['first_delivery'], ensure_ascii=False) + '\n')
    if policy == 'code-local':
        guidance += 'Use local Read/Edit/Write tools. Bash, WebFetch, WebSearch, Agent and Task are disabled for this task.\n'
    for key in ('allowed_files', 'forbidden_files', 'acceptance'):
        if key in task:
            guidance += key + ': ' + json.dumps(task[key], ensure_ascii=False) + '\n'
    if task['tests']:
        guidance += ('Controller test requests (WSL argv; use host equivalents for your checks): ' if policy == 'development'
                     else 'Controller test requests (do not execute): ') + json.dumps(task['tests'], ensure_ascii=False) + '\n'
    if request.get('test_feedback'):
        guidance += 'Controller verification of previous attempt:\n' + json.dumps(request['test_feedback'], ensure_ascii=False) + '\n'
    return task['prompt'] + guidance


def worker(store, tid, backend=None, progress=True):
    with (store.task(tid) / 'worker.lock').open('a+') as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise BridgeError('Task already has a worker') from None
        return _worker(store, tid, backend, progress)


def _worker(store, tid, backend=None, progress=True):
    backend = backend or WindowsBackend()
    directory = store.task(tid)
    request = read_json(directory / 'request.json')
    state = read_json(directory / 'state.json')
    if state['status'] != 'queued':
        raise BridgeError('Task already started; use a new task with --resume')
    started = time.monotonic()
    state.update(status='starting', worker_pid=os.getpid(), worker_start=identity(os.getpid()), started_at=utc())
    atomic_json(directory / 'state.json', state)
    cancelled_flag = [False]
    old_signals = {}
    if threading.current_thread() is threading.main_thread():
        for sig in (signal.SIGTERM, signal.SIGINT):
            old_signals[sig] = signal.signal(sig, lambda *_: cancelled_flag.__setitem__(0, True))
    def cancelled():
        return cancelled_flag[0] or (directory / 'cancel.request').exists()
    events = (directory / 'events.jsonl').open('x', encoding='utf-8', buffering=1)
    def emit(event):
        event = {'task_id': tid, 'timestamp': utc(), **event}
        events.write(json.dumps(event, ensure_ascii=False) + '\n')
        if progress:
            print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)
    lock = None
    process = None
    probe_runner = tracker = None
    cleanup_ok = True
    repo_lease = None
    stop_readers = threading.Event()
    readers = []
    result = {'task_id': tid, 'sessionId': request.get('resume'), 'response': '',
              'status': 'failed', 'implementation_status': 'incomplete',
              'validation_status': 'not_run', 'tests_executed': [], 'blockers': [],
              'usage': {}, 'changed_files': [], 'scope_violations': [], 'created_at': request['created_at']}
    result['requested_reasoning_effort'] = request.get('reasoning_effort', request['contract'].get('reasoning_effort','inherit'))
    state['requested_reasoning_effort'] = result['requested_reasoning_effort']
    before = after = None
    delivery = request['contract'].get('first_delivery')
    delivery_deadline = started + delivery['timeout_seconds'] if delivery else None
    delivery_warned = False
    delivery_report = None
    subagent_records = {}
    exit_code = None
    counters = {'events_received': 0, 'tool_starts': 0, 'tool_errors': 0,
                'permission_denials': 0, 'stderr_bytes_suppressed': 0}
    timings = {'first_event_seconds': None, 'execution_seconds': 0, 'test_seconds': 0}
    try:
        from team_workspace import claim_bridge
        repo_lease = claim_bridge(request['cwd'], request.get('team_run'), tid, directory)
        if repo_lease:
            atomic_json(directory / 'repo-claim.json', {'path': repo_lease})
        lock = store.lock(request['cwd'])
        atomic_json(store.root / 'locks' / (cwd_key(request['cwd']) + '.active.json'), {'task_id': tid})
        capabilities = backend.doctor()
        atomic_json(directory / 'doctor.json', capabilities)
        if not capabilities['ready']:
            raise BridgeError('Capability preflight failed; see doctor.json')
        requested_effort = request.get('reasoning_effort', request['contract'].get('reasoning_effort', 'inherit'))
        if requested_effort != 'inherit' and request.get('tool_policy', request['contract'].get('tool_policy', 'code-local')) != 'development':
            raise BridgeError('Explicit reasoning effort requires development protocol')
        if request.get('allow_subagents', request['contract'].get('allow_subagents', False)) and request.get('tool_policy', request['contract'].get('tool_policy', 'code-local')) == 'development':
            if not capabilities.get('capabilities', {}).get('constrained_subagents'):
                raise BridgeError('Constrained subagents require the verified ZCode bundle; see doctor.json')
        if request['contract'].get('requires_shell') and (request.get('tool_policy', request['contract'].get('tool_policy', 'code-local')) != 'development' or request['mode'] == 'plan'):
            result['status'] = 'blocked_permission'
            raise BridgeError('Headless executor has no shell permission client; use controller tests')
        progress_warning = positive(request.get('progress_warning', 120))
        progress_timeout = positive(request['progress_timeout']) if request.get('progress_timeout') is not None else None
        before = snapshot(request['cwd'], store.root)
        atomic_json(directory / 'before.json', before)
        initial_progress = progress_probe(request['cwd'], store.root, request['contract'])
        if request.get('expected_digest') and before['digest'] != request['expected_digest']:
            raise BridgeError('Workspace changed since test feedback; verify the current source again')
        if time.monotonic() - started >= request['timeout']:
            result['status'] = 'timed_out'
            result['blockers'].append('total_timeout_before_launch')
        elif delivery_deadline is not None and time.monotonic() >= delivery_deadline:
            result['status'] = 'timed_out'
            result['blockers'].append('first_delivery_timeout')
        elif cancelled():
            result['status'] = 'cancelled'
        else:
            state['status'] = 'running'
            atomic_json(directory / 'state.json', state)
            emit({'type': 'task.started', 'mode': request['mode']})
            process = backend.launch({**request, 'prompt': prompt_for(request)}, directory)
            state['transport_pid'] = process.pid
            atomic_json(directory / 'state.json', state)
            channel = queue.Queue(maxsize=256)
            for name in ('stdout', 'stderr'):
                thread = threading.Thread(target=read_pipe, args=(getattr(process, name), name, channel, stop_readers), daemon=True)
                thread.start()
                readers.append(thread)
            last_activity = last_state = execution_start = time.monotonic()
            probe_runner = ProbeProcess(directory, request['cwd'], store.root, request['contract'])
            tracker = ProgressTracker(execution_start, progress_warning, progress_timeout, probe_runner,
                                      initial_progress['digest'])
            first = True
            terminal = None
            ended = set()
            reason = None
            while True:
                now = time.monotonic()
                if cancelled():
                    reason = 'cancelled'
                    break
                if delivery_deadline is not None:
                    elapsed = now - started
                    if elapsed >= delivery['warning_seconds'] and not delivery_warned:
                        delivery_warned = True
                        emit({'type':'first_delivery.warning', 'elapsed_seconds':elapsed,
                              'phase':tracker.status(now)['phase'], 'active_tools':tracker.status(now)['active_tools'],
                              'action':'finish_current_stage'})
                    if now >= delivery_deadline:
                        reason = 'timed_out'
                        result['blockers'].append('first_delivery_timeout')
                        break
                if now - started >= request['timeout'] or now - last_activity >= request['idle_timeout']:
                    reason = 'timed_out'
                    result['blockers'].append('total_timeout' if now - started >= request['timeout'] else 'idle_timeout')
                    break
                try:
                    kind, raw = channel.get(timeout=.1)
                except queue.Empty:
                    kind, raw = None, None
                now = time.monotonic()
                if kind == 'event':
                    counters['events_received'] += 1
                    last_activity = now
                    if first:
                        timings['first_event_seconds'] = now - started
                        first = False
                    parsed = terminal_result(raw)
                    if parsed is not None:
                        if terminal is not None:
                            raise BridgeError('Duplicate terminal result')
                        if request.get('resume') and parsed['sessionId'] != request['resume']:
                            raise BridgeError('CLI resumed a different session')
                        terminal = parsed
                    event = safe_event(raw)
                    if event:
                        tracker.observe(event, now, utc())
                        if event['type'].startswith('subagent.') and event.get('callId'):
                            subagent_records[event['callId']] = {**subagent_records.get(event['callId'], {}), **event}
                        if event.get('session_id'):
                            result['sessionId'] = event['session_id']
                        if event['type'] == 'model.selected':
                            result['observed_model'] = event['model_id']
                            result['observed_provider'] = event.get('provider_id')
                            if request.get('expected_model') and event['model_id'] != request['expected_model']:
                                reason = 'model_mismatch'
                                result['blockers'].append('Actual model does not match expected_model')
                        if event['type'] == 'reasoning.selected':
                            result['reasoning_effort'] = event.get('effective')
                            state['reasoning_effort'] = event.get('effective')
                            result['requested_reasoning_effort'] = requested_effort
                            if requested_effort != 'inherit' and event.get('effective') != requested_effort:
                                reason = 'failed'
                                result['blockers'].append('reasoning_mismatch')
                        if event['type'] == 'configuration.error':
                            reason = 'failed'
                            result['blockers'].append(event['code'])
                            result['supported_reasoning_efforts'] = event.get('available',[])
                        if event['type'] == 'tool.updated':
                            counters['tool_starts'] += event['phase'] == 'started'
                            if event['phase'] != 'started':
                                counters['tool_errors'] += not event.get('success', False)
                        if event.get('decision') == 'deny' or event.get('error_code') == 'permission_client_missing':
                            counters['permission_denials'] += 1
                            reason = 'blocked_permission'
                        if event['type'] == 'turn.failed':
                            reason = 'failed'
                        if event['type'] != 'model.activity':
                            emit(event)
                    if reason:
                        break
                elif kind == 'protocol_error':
                    raise BridgeError('Invalid or oversized stream JSON; raw content was not persisted')
                elif kind == 'stderr':
                    counters['stderr_bytes_suppressed'] += raw
                elif kind == 'diagnostic':
                    if raw not in result['blockers']:
                        result['blockers'].append(raw)
                        emit({'type': 'transport.diagnostic', 'code': raw})
                    if raw == 'permission_client_missing':
                        reason = 'blocked_permission'
                        break
                elif kind in ('stdout_eof', 'stderr_eof'):
                    ended.add(kind)
                if terminal is None:
                    tracker.refresh(now, utc())
                    now = time.monotonic()
                    silence = now - tracker.last_output
                    if silence >= progress_warning and not tracker.warned:
                        tracker.warned = True
                        emit({'type': 'progress.warning', 'metric': 'output',
                              **tracker.status(now), 'action': 'controller_review'})
                    if progress_timeout is not None and silence >= progress_timeout:
                        reason = 'timed_out'
                        result['blockers'].append('no_progress_timeout')
                        break
                if now - last_state >= 1:
                    if subagent_records:
                        state['subagents'] = {'calls': len(subagent_records), **{
                            phase: sum(r['type'] == 'subagent.' + phase for r in subagent_records.values())
                            for phase in ('queued', 'started', 'completed', 'failed', 'cancelled')}}
                    state.update(session_id=result['sessionId'], last_event_at=utc() if now - last_activity < 1 else state.get('last_event_at'),
                                 elapsed_seconds=now - started, counters=counters.copy(), progress=tracker.status(now))
                    if delivery:
                        state['progress']['first_delivery'] = {'status':'pending','warning_active':delivery_warned,
                            'elapsed_seconds':now-started,'timeout_seconds':delivery['timeout_seconds']}
                    atomic_json(directory / 'state.json', state)
                    last_state = now
                if process.poll() is not None and len(ended) == 2 and channel.empty():
                    break
            timings['execution_seconds'] = time.monotonic() - execution_start
            result['progress'] = tracker.status(time.monotonic())
            if reason:
                result['status'] = reason
            elif terminal is None:
                raise BridgeError('Process exited without a terminal result')
            elif requested_effort != 'inherit' and result.get('reasoning_effort') != requested_effort:
                raise BridgeError('Requested reasoning effort was not verified')
            elif request.get('expected_model') and result.get('observed_model') is None:
                result.update(terminal)
                result['status'] = 'model_unverified'
                result['blockers'].append('No model identity was observed in the CLI event stream')
            else:
                result.update(terminal)
                response = result['response'].lstrip()
                if process.returncode != 0 or terminal.get('projection', {}).get('status') in ('failed', 'error', 'interrupted'):
                    result['status'] = 'failed'
                elif response.startswith('NEED-CLARIFICATION:'):
                    result['status'] = 'needs_clarification'
                elif response.startswith('BLOCKED-PERMISSION:'):
                    result['status'] = 'blocked_permission'
                else:
                    result['status'] = 'completed'
                    result['implementation_status'] = 'reported_complete'
    except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        # These messages are controller-generated; never include raw provider output.
        result['blockers'].append(str(exc))
    finally:
        stop_readers.set()
        if probe_runner is not None:
            try:
                cleanup_ok = probe_runner.close()
            except (OSError, ValueError, subprocess.SubprocessError):
                cleanup_ok = False
            if cleanup_ok and tracker is not None:
                tracker.stopped(time.monotonic())
                result['progress'] = tracker.status(time.monotonic())
        if process is not None:
            try:
                backend_ok = backend.cleanup(process, directory)
                cleanup_ok = cleanup_ok and backend_ok
            except (OSError, ValueError, subprocess.SubprocessError):
                cleanup_ok = False
            exit_code = process.poll()
            if not cleanup_ok:
                result['status'] = 'cleanup_failed'
                result['blockers'].append('Process tree termination unconfirmed; cwd locked against new tasks')
                store.unsafe(request['cwd'], tid)
        elif (directory / 'transport.json').exists():
            # Popen can fail after writing ownership metadata.
            backend_ok = backend.cleanup(None, directory)
            cleanup_ok = cleanup_ok and backend_ok
            if not cleanup_ok:
                result['status'] = 'cleanup_failed'
                store.unsafe(request['cwd'], tid)
        for thread in readers:
            thread.join(timeout=1)
        try:
            if before is not None and cleanup_ok:
                after = snapshot(request['cwd'], store.root)
                atomic_json(directory / 'after.json', after)
                result.update(changes(before, after, request['contract']))
                if tracker is not None and result['status'] == 'completed':
                    tracker.finish(progress_probe(request['cwd'], store.root, request['contract']), time.monotonic(), utc())
                    result['progress'] = tracker.status(time.monotonic())
                if result['scope_violations']:
                    result['implementation_status'] = 'rejected_scope'
                    if result['status'] == 'completed':
                        result['status'] = 'scope_violation'
                if result['status'] == 'completed' and delivery:
                    state['status'] = 'validating'
                    state.setdefault('progress',{})['first_delivery'] = {'status':'checking','warning_active':delivery_warned,
                        'elapsed_seconds':time.monotonic()-started,'timeout_seconds':delivery['timeout_seconds']}
                    atomic_json(directory / 'state.json', state)
                    check_started = time.monotonic()
                    def checking_cancelled():
                        nonlocal delivery_warned
                        if not delivery_warned and time.monotonic()-started >= delivery['warning_seconds']:
                            delivery_warned = True
                            state['progress']['first_delivery'].update(warning_active=True,elapsed_seconds=time.monotonic()-started)
                            state['progress']['phase'] = 'controller_test_running'
                            atomic_json(directory/'state.json',state)
                            emit({'type':'first_delivery.warning','elapsed_seconds':time.monotonic()-started,
                                  'phase':'controller_test_running','action':'check_stage_budget'})
                        return cancelled()
                    delivery_report, checked = verify_delivery(request['contract'], before, after,
                        request['cwd'], store.root, directory, min(delivery_deadline,started+request['timeout']), checking_cancelled, emit)
                    timings['test_seconds'] += time.monotonic() - check_started
                    result['first_delivery'] = {k:v for k,v in delivery_report.items() if k != 'tests'}
                    result['first_delivery']['seconds'] = time.monotonic() - started
                    result['tests_executed'] = delivery_report['tests']
                    result.update(changes(before,checked,request['contract']))
                    if (directory/'first-delivery'/'active-test.json').exists():
                        cleanup_ok = False
                        store.unsafe(request['cwd'],tid)
                        result['status'] = 'cleanup_failed'
                    elif delivery_report['status'] != 'passed':
                        result['validation_status'] = 'failed'
                        result['status'] = ('cancelled' if delivery_report['status']=='cancelled' else
                                            'timed_out' if delivery_report['status']=='timed_out' else 'validation_failed')
                        result['blockers'].append('first_delivery_timeout' if delivery_report['status']=='timed_out' else 'first_delivery_failed')
                    else:
                        all_checked = {t['id'] for t in delivery_report['tests']} == {t['id'] for t in request['contract']['tests']}
                        result['validation_status'] = 'passed' if all_checked else 'partial'
                        if all_checked:
                            atomic_json(directory/'verification.json',{**delivery_report,'task_id':tid,'finished_at':utc()})
                if result['status'] == 'completed' and request.get('run_tests'):
                    state['status'] = 'validating'
                    atomic_json(directory / 'state.json', state)
                    test_started = time.monotonic()
                    completed_checks = delivery_report['tests'] if delivery_report and delivery_report['status']=='passed' else []
                    checked_ids = {t['id'] for t in completed_checks}
                    remaining = [t for t in request['contract']['tests'] if t['id'] not in checked_ids]
                    verification = execute_tests({'tests':remaining}, request['cwd'], directory,
                                                 lambda: cancelled() or time.monotonic() - started >= request['timeout'], emit)
                    verification['tests'] = completed_checks + verification['tests']
                    if completed_checks and verification['status']=='not_run' and not remaining:
                        verification['status'] = 'passed'
                    verified_snapshot = snapshot(request['cwd'], store.root)
                    verification.update(task_id=tid, source_digest=after['digest'], finished_at=utc(),
                                        source_unchanged=verified_snapshot['digest'] == after['digest'])
                    if not verification['source_unchanged']:
                        verification['status'] = 'source_changed'
                    atomic_json(directory / 'verification.json', verification)
                    timings['test_seconds'] += time.monotonic() - test_started
                    result['validation_status'] = verification['status']
                    result['tests_executed'] = verification['tests']
                    if cancelled():
                        result['status'] = 'cancelled'
                    elif time.monotonic() - started >= request['timeout']:
                        result['status'] = 'timed_out'
                    elif verification['status'] not in ('passed', 'not_run'):
                        result['status'] = 'validation_failed'
                    result.update(changes(before, verified_snapshot, request['contract']))
                    if result['scope_violations']:
                        result['status'] = 'scope_violation'
        except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
            result['status'] = 'failed'
            result['blockers'].append(str(exc))
        timings['total_seconds'] = time.monotonic() - started
        if delivery and 'first_delivery' not in result:
            result['first_delivery'] = {'status':'timed_out' if 'first_delivery_timeout' in result['blockers'] else 'not_verified',
                                         'seconds':time.monotonic()-started,'warning_active':delivery_warned}
        result.update(timings=timings, counters=counters, process_exit_code=exit_code,
                      cleanup_confirmed=cleanup_ok, finished_at=utc(), result_file=str(directory / 'result.json'))
        if subagent_records and 'subagents' not in result:
            known_usage = {}
            for row in subagent_records.values():
                for key, value in row['usage'].items():
                    known_usage[key] = known_usage.get(key, 0) + value
            result['subagents'] = {'calls': len(subagent_records), 'usage': known_usage, 'usage_complete': False}
            result['usage'] = known_usage
            result['usage_complete'] = False
        result['usage_complete'] = result.get('usage_complete', True) and type(result.get('usage', {}).get('totalTokens')) is int
        result['exit_code'] = EXITS[result['status']]
        atomic_json(directory / 'result.json', result)
        state.update(status=result['status'], session_id=result['sessionId'], finished_at=result['finished_at'],
                     result_file=result['result_file'], exit_code=result['exit_code'])
        if 'subagents' in result:
            state['subagents'] = result['subagents']
        if 'first_delivery' in result:
            state['first_delivery'] = {k:v for k,v in result['first_delivery'].items() if k != 'files'}
            state['first_delivery']['file_count'] = len(result['first_delivery'].get('files',[]))
            state.setdefault('progress',{})['first_delivery'] = {
                'status':result['first_delivery']['status'], 'seconds':result['first_delivery']['seconds'],
                'warning_active':False, 'timeout_seconds':delivery['timeout_seconds']}
        atomic_json(directory / 'state.json', state)
        emit({'type': 'task.finished', 'status': result['status'], 'validation_status': result['validation_status']})
        events.close()
        if repo_lease and cleanup_ok:
            from team_workspace import release_bridge_claim
            release_bridge_claim(repo_lease, tid)
        if lock is not None:
            active = store.root / 'locks' / (cwd_key(request['cwd']) + '.active.json')
            if cleanup_ok and active.exists() and read_json(active).get('task_id') == tid:
                active.unlink()
            lock.close()
        for sig, previous in old_signals.items():
            signal.signal(sig, previous)
    return result


def verify(store, tid):
    from team_workspace import claim_bridge, release_bridge_claim
    directory = store.task(tid)
    req = read_json(directory / 'request.json')
    with store.lock(req['cwd']):
        result = read_json(directory / 'result.json')
        if result['status'] not in ('completed', 'validation_failed'):
            raise BridgeError('Only completed implementations can be verified')
        repo_lease = claim_bridge(req['cwd'], req.get('team_run'), tid, directory)
        active = store.root / 'locks' / (cwd_key(req['cwd']) + '.active.json')
        old_signals = {}
        try:
            if repo_lease:
                atomic_json(directory / 'repo-claim.json', {'path': repo_lease})
            before = snapshot(req['cwd'], store.root)
            if before['digest'] != read_json(directory / 'after.json')['digest']:
                raise BridgeError('Workspace changed since implementation; create a new task')
            # Each attempt keeps its own logs, including failed verification setup.
            logdir = directory / ('verify-' + uuid.uuid4().hex[:12])
            logdir.mkdir()
            atomic_json(active, {'task_id': tid})
            state = read_json(directory / 'state.json')
            state.update(status='validating', worker_pid=os.getpid(), worker_start=identity(os.getpid()))
            atomic_json(directory / 'state.json', state)
            interrupted = [False]
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGINT, signal.SIGTERM):
                    old_signals[sig] = signal.signal(sig, lambda *_: interrupted.__setitem__(0, True))
            report = {'status': 'failed', 'tests': [], 'source_unchanged': False}
            try:
                report = execute_tests(req['contract'], req['cwd'], logdir,
                                       lambda: interrupted[0] or (directory / 'cancel.request').exists(), lambda _: None)
                after = snapshot(req['cwd'], store.root)
                report['source_unchanged'] = before['digest'] == after['digest']
                if not report['source_unchanged']:
                    report['status'] = 'source_changed'
            except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
                report.update(status='failed', error=str(exc), source_unchanged=False)
            report.update(task_id=tid, source_digest=before['digest'], finished_at=utc())
            atomic_json(logdir / 'verification.json', report)
            atomic_json(directory / 'verification.json', report)
            result.update(validation_status=report['status'], tests_executed=report['tests'])
            result['status'] = 'completed' if report['status'] in ('passed', 'not_run') else 'validation_failed'
            # An outstanding test owner means termination was not confirmed.
            cleanup_ok = not (logdir / 'active-test.json').exists()
            if not cleanup_ok:
                result.update(status='cleanup_failed', cleanup_confirmed=False)
                store.unsafe(req['cwd'], tid)
            result['exit_code'] = EXITS[result['status']]
            atomic_json(directory / 'result.json', result)
            state.update(status=result['status'], exit_code=result['exit_code'])
            atomic_json(directory / 'state.json', state)
            if cleanup_ok:
                active.unlink()
            return report
        finally:
            for sig, previous in old_signals.items():
                signal.signal(sig, previous)
            # Keep the lease on interruption or an unconfirmed test process so
            # recover can clear it only after confirming process cleanup.
            if not active.exists():
                release_bridge_claim(repo_lease, tid)


def feedback_request(store, tid):
    directory = store.task(tid)
    old = read_json(directory / 'request.json')
    result = read_json(directory / 'result.json')
    evidence = read_json(directory / 'verification.json')
    if not result.get('sessionId') or not evidence.get('source_unchanged'):
        raise BridgeError('Feedback requires a session and verification of unchanged source')
    if evidence.get('status') == 'not_run':
        raise BridgeError('No executed tests to feed back')
    req = {k: old[k] for k in ('cwd', 'mode', 'timeout', 'idle_timeout', 'contract', 'run_tests')}
    req.update(resume=result['sessionId'], parent_task=tid, expected_digest=evidence['source_digest'])
    if evidence.get('status') == 'passed':
        # A verified acknowledgement explicitly asks for no edits; it is not
        # a new implementation stage requiring a new source artifact.
        req['contract']['first_delivery'] = None
    for key in ('expected_model', 'team_run', 'progress_warning', 'progress_timeout', 'tool_policy', 'allow_subagents', 'reasoning_effort'):
        if key in old:
            req[key] = old[key]
    # Test output excerpts are explicit controller feedback, not progress events.
    evidence = json.loads(json.dumps(evidence))
    for test in evidence['tests']:
        log = Path(test['log'])
        if not log.resolve().is_relative_to(directory):
            raise BridgeError('Test log is not owned by this task')
        with log.open('rb') as src:
            src.seek(max(0, log.stat().st_size - 12000))
            test['output_tail'] = src.read().decode('utf-8', errors='replace')
    req['test_feedback'] = evidence
    req['contract']['prompt'] = ('Continue this task using the controller test results below. Fix only permitted files; '
                                 'if all tests passed, acknowledge without additional edits.\n\n' + old['contract']['prompt'])
    return req


def cancel_or_recover(store, tid, backend=None):
    directory = store.task(tid)
    state = store.status(tid)
    if state.get('worker_pid') and not state.get('worker_missing') and state['status'] not in TERMINAL:
        (directory / 'cancel.request').touch(exist_ok=True)
        return {'task_id': tid, 'status': 'cancel_requested'}
    if state['status'] in TERMINAL and state['status'] != 'cleanup_failed':
        lease = directory / 'repo-claim.json'
        if lease.exists():
            from team_workspace import release_bridge_claim
            release_bridge_claim(read_json(lease)['path'], tid)
        return state
    request = read_json(directory / 'request.json')
    backend = backend or WindowsBackend()
    with store.lock(request['cwd'], allow_unsafe=True):
        ok = not (directory / 'transport.json').exists() or backend.cleanup(None, directory)
        probe_ok = recover_probe(directory)
        ok = ok and probe_ok
        for test_owner in [directory / 'active-test.json', directory/'first-delivery'/'active-test.json', *directory.glob('verify-*/active-test.json')]:
            if test_owner.exists():
                owner = read_json(test_owner)
                if identity(owner['pid']) == owner['start']:
                    try:
                        if os.getpgid(owner['pid']) != owner['pid']:
                            ok = False
                        else:
                            os.killpg(owner['pid'], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                test_owner.unlink()
        state.update(status='cancelled' if ok else 'cleanup_failed', cleanup_confirmed=ok, finished_at=utc())
        if ok:
            lease = directory / 'repo-claim.json'
            if lease.exists():
                from team_workspace import release_bridge_claim
                release_bridge_claim(read_json(lease)['path'], tid)
            unsafe = store.root / 'locks' / (cwd_key(request['cwd']) + '.unsafe.json')
            if unsafe.exists() and read_json(unsafe).get('task_id') == tid:
                unsafe.unlink()
            active = store.root / 'locks' / (cwd_key(request['cwd']) + '.active.json')
            if active.exists() and read_json(active).get('task_id') == tid:
                active.unlink()
        else:
            store.unsafe(request['cwd'], tid)
        atomic_json(directory / 'state.json', state)
        result = {'task_id': tid, 'sessionId': state.get('session_id'), 'response': '',
                  'status': state['status'], 'validation_status': 'not_run',
                  'implementation_status': 'incomplete', 'cleanup_confirmed': ok,
                  'blockers': ['Worker interrupted; inspect partial changes before resuming'],
                  'exit_code': EXITS[state['status']]}
        atomic_json(directory / 'result.json', result)
    return state


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--state-dir', default=os.environ.get('ZCODE_BRIDGE_STATE_DIR', str(ROOT / '.runs')))
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('doctor')
    sub.add_parser('team', help='Team coordinator (team --help)')
    for name in ('run', 'submit'):
        r = sub.add_parser(name)
        r.add_argument('prompt', nargs='?')
        r.add_argument('--prompt-file')
        r.add_argument('--task-file')
        r.add_argument('--cwd', default=os.getcwd())
        r.add_argument('--mode', choices=('plan', 'edit', 'build'), default='edit')
        r.add_argument('--resume')
        r.add_argument('--expected-model', help='Reject missing or mismatching observed model identity')
        r.add_argument('--timeout', type=float, default=3600)
        r.add_argument('--idle-timeout', type=float, default=600)
        r.add_argument('--progress-warning', type=float, default=120, help='Warn after this many seconds without new artifacts, distinct test/build results or child findings')
        r.add_argument('--progress-timeout', type=float, help='Optional hard stop for no substantive output, even if tools/streaming continue')
        r.add_argument('--tool-policy', choices=('development', 'code-local', 'cli-default'))
        r.add_argument('--reasoning-effort', choices=('low','high','max','inherit'))
        r.add_argument('--run-tests', action='store_true', help='Execute predeclared controller test argv')
    for name in ('status', 'wait', 'cancel', 'recover', 'verify', 'feedback', '_worker'):
        s = sub.add_parser(name)
        s.add_argument('task_id')
        if name == 'wait':
            s.add_argument('--timeout', type=float, default=60)
    return p


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {'doctor', 'run', 'submit', 'status', 'wait', 'cancel', 'recover', 'verify', 'feedback', '_worker'}
    # Preserve `ask-zcode.sh 'prompt' --cwd ...`; new commands are reserved words.
    prefix = []
    if argv[:1] == ['--state-dir'] and len(argv) >= 2:
        prefix, argv = argv[:2], argv[2:]
    if argv[:1] == ['team']:
        from team import main as team_main
        return team_main(prefix + argv[1:])
    if argv and argv[0] not in commands and argv[0] not in ('-h', '--help'):
        argv.insert(0, 'run')
    args = parser().parse_args(prefix + argv)
    try:
        if args.command == 'doctor':
            value = WindowsBackend().doctor()
            code = 0 if value['ready'] else 1
        else:
            store = Store(args.state_dir)
            if args.command in ('run', 'submit', 'feedback'):
                if args.command == 'feedback':
                    request = feedback_request(store, args.task_id)
                else:
                    cwd = Path(args.cwd).resolve(strict=True)
                    if not cwd.is_dir():
                        raise BridgeError('cwd must be a directory')
                    task = contract(args.prompt, args.task_file, args.prompt_file)
                    if args.mode == 'plan':
                        task['allowed_files'] = []
                    policy = args.tool_policy or task.get('tool_policy','development')
                    if args.reasoning_effort:
                        task['reasoning_effort'] = args.reasoning_effort
                    task = execution_defaults(task,args.mode,policy)
                    if args.resume and not ID.fullmatch(args.resume):
                        raise BridgeError('Invalid resume session ID')
                    if args.expected_model and not ID.fullmatch(args.expected_model):
                        raise BridgeError('Invalid expected model ID')
                    request = {'cwd': str(cwd), 'mode': args.mode, 'resume': args.resume,
                               'timeout': positive(args.timeout), 'idle_timeout': positive(args.idle_timeout),
                               'contract': task, 'run_tests': args.run_tests, 'expected_model': args.expected_model,
                               'progress_warning': positive(args.progress_warning),
                               'progress_timeout': positive(args.progress_timeout) if args.progress_timeout is not None else None,
                               'tool_policy': policy, 'reasoning_effort':task['reasoning_effort'],
                               'allow_subagents': task.get('allow_subagents', True)}
                tid = store.create(request)
                if args.command == 'submit':
                    command = [sys.executable, str(ROOT / 'ask-zcode.py'), '--state-dir', str(store.root), '_worker', tid]
                    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, start_new_session=True)
                    value, code = {'task_id': tid, 'status': 'submitted', 'state_dir': str(store.root)}, 0
                else:
                    value = worker(store, tid)
                    code = value['exit_code']
            elif args.command == '_worker':
                value = worker(store, args.task_id, progress=False)
                code = value['exit_code']
            elif args.command in ('cancel', 'recover'):
                value = cancel_or_recover(store, args.task_id)
                code = 7 if value['status'] == 'cleanup_failed' else 0
            elif args.command == 'verify':
                value = verify(store, args.task_id)
                code = 0 if value['status'] == 'passed' else 6
            else:
                deadline = time.monotonic() + positive(args.timeout) if args.command == 'wait' else 0
                while True:
                    value = store.status(args.task_id)
                    if value['status'] in TERMINAL or value.get('worker_missing') or time.monotonic() >= deadline:
                        break
                    time.sleep(.2)
                result_file = store.task(args.task_id) / 'result.json'
                if args.command == 'wait' and value['status'] in TERMINAL and result_file.exists():
                    value = read_json(result_file)
                code = value.get('exit_code', 0) if value['status'] in TERMINAL else 0 if args.command == 'status' else 2
        print(json.dumps(value, ensure_ascii=False, allow_nan=False), flush=True)
        return code
    except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False), flush=True)
        return 2
