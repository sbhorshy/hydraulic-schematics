#!/usr/bin/env python3
"""Dependency-aware worktrees, review handoffs, and a serialized integration queue."""
import argparse
import copy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid

from bridge import Store, TERMINAL, cancel_or_recover, identity, utc
from bridge_contract import BridgeError, atomic_json, changes, contract, execute_tests, positive, read_json, snapshot
from bridge_transport import ROOT
from bridge_delivery import execution_defaults, zero_output_timeout
from team_workspace import (add_worktree, apply_candidate, canonical, clean, common_dir,
                            freeze, git, head, repository_lock, repo_root)

RUN_DONE = {'completed', 'cancelled'}
JOB_ACTIVE = {'dispatching', 'running'}


def launch_background(argv):
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, start_new_session=True)
    threading.Thread(target=process.wait, daemon=True).start()
    return process.pid


def alive(owner):
    if identity(owner['pid']) != owner['start']:
        return False
    try:
        return Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(')', 1)[1].split()[0] != 'Z'
    except OSError:
        return False


def name(value):
    import re
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', value):
        raise BridgeError('IDs must be short alphanumeric names without paths')
    return value


def strings(value, field):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise BridgeError(field + ' must be a list of nonempty strings')
    if len(set(value)) != len(value):
        raise BridgeError(field + ' contains duplicates')
    return value


def validate_plan(raw):
    p = copy.deepcopy(raw)
    allowed = {'version', 'repo', 'base', 'tasks', 'expected_model', 'max_writers',
               'experimental_parallel', 'max_repairs', 'max_pending_reviews', 'deadline_seconds',
               'executor_token_limit', 'integration_tests', 'task_timeout', 'idle_timeout'}
    allowed |= {'progress_warning', 'progress_timeout'}
    if not isinstance(p, dict) or set(p) - allowed or p.get('version') != 1:
        raise BridgeError('Invalid team plan fields/version')
    p['repo'] = str(repo_root(p['repo']))
    p['base'] = git(p['repo'], 'rev-parse', '--verify', '--end-of-options', str(p.get('base', 'HEAD')) + '^{commit}').decode().strip()
    p['expected_model'] = name(p.get('expected_model', 'GLM-5.3-Flash'))
    for k, default, lo, hi in [('max_writers', 1, 1, 2), ('max_repairs', 2, 0, 10), ('max_pending_reviews', 2, 1, 10)]:
        v = p.setdefault(k, default)
        if type(v) is not int or not lo <= v <= hi:
            raise BridgeError('Invalid ' + k)
    if p['max_writers'] == 2 and p.get('experimental_parallel') is not True:
        raise BridgeError('Two writers require explicit experimental_parallel=true')
    for k, default in [('deadline_seconds', 14400), ('task_timeout', 3600), ('idle_timeout', 600)]:
        p[k] = positive(p.get(k, default))
    p['progress_warning'] = positive(p.get('progress_warning', 120))
    p['progress_timeout'] = positive(p['progress_timeout']) if p.get('progress_timeout') is not None else None
    limit = p.setdefault('executor_token_limit', None)
    if limit is not None and (type(limit) is not int or limit <= 0):
        raise BridgeError('executor_token_limit must be a positive integer or null')
    tasks = p.get('tasks')
    if not isinstance(tasks, list) or not tasks or len(tasks) > 100:
        raise BridgeError('Plan requires 1..100 tasks')
    ids, claims = set(), set()
    with tempfile.TemporaryDirectory(prefix='zcode-team-validate-') as temp:
        file = Path(temp) / 'contract.json'
        for t in tasks:
            if not isinstance(t, dict) or set(t) - {'id', 'claim_key', 'depends_on', 'contract', 'external_blocks', 'resources'}:
                raise BridgeError('Invalid task fields')
            tid = name(t['id'])
            if tid in ids:
                raise BridgeError('Duplicate task ID')
            ids.add(tid)
            claim = t.setdefault('claim_key', tid)
            if not isinstance(claim, str) or not claim or claim in claims:
                raise BridgeError('claim_key must be unique within the plan')
            claims.add(claim)
            for k in ('depends_on', 'external_blocks', 'resources'):
                strings(t.setdefault(k, []), k)
            file.write_text(json.dumps(t['contract']))
            t['contract'] = contract(task_file=file)
            # Freeze the default at plan creation; existing saved plans retain
            # their original permissions when resumed after a bridge upgrade.
            t['contract'].setdefault('tool_policy', 'development')
            t['contract'].setdefault('allow_subagents', True)
            t['contract'] = execution_defaults(t['contract'], 'edit', t['contract']['tool_policy'])
        file.write_text(json.dumps({'version': 1, 'prompt': 'integration checks', 'allowed_files': [],
                                    'tests': p.get('integration_tests', [])}))
        p['integration_tests'] = contract(task_file=file)['tests']
    deps = {t['id']: set(t['depends_on']) for t in tasks}
    if any(not d <= ids for d in deps.values()):
        raise BridgeError('Unknown dependency')
    remaining = set(ids)
    while remaining:
        ready = {x for x in remaining if not (deps[x] & remaining)}
        if not ready:
            raise BridgeError('Task dependency cycle')
        remaining -= ready
    return p


class BridgeExecutor:
    def __init__(self, root):
        self.store = Store(root)

    def prepare(self, request):
        return self.store.create(request)

    def launch(self, tid):
        if self.store.status(tid)['status'] != 'queued':
            return
        launch_background([sys.executable, str(ROOT / 'ask-zcode.py'), '--state-dir', str(self.store.root), '_worker', tid])

    def poll(self, tid):
        state = self.store.status(tid)
        file = self.store.task(tid) / 'result.json'
        return read_json(file) if state['status'] in TERMINAL and file.exists() else state

    def cancel(self, tid):
        return cancel_or_recover(self.store, tid)

    def progress(self, tid):
        return self.store.status(tid).get('progress')


class WorkCoordinator:
    def __init__(self, state_dir=None, executor=None):
        self.root = Path(state_dir or os.environ.get('ZCODE_TEAM_STATE_DIR', str(ROOT / '.teams'))).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.executor = executor or BridgeExecutor(self.root / 'executions')

    def directory(self, rid):
        p = self.root / name(rid)
        if not p.is_dir():
            raise BridgeError('Unknown team run')
        return p

    def _load(self, rid):
        return read_json(self.directory(rid) / 'state.json')

    def _save(self, s, event):
        s['revision'] += 1
        s['updated_at'] = utc()
        d = self.root / s['run_id']
        atomic_json(d / 'state.json', s)
        with (d / 'events.jsonl').open('a', encoding='utf-8') as f:
            f.write(json.dumps({'revision': s['revision'], 'at': s['updated_at'], 'event': event}, ensure_ascii=False) + '\n')

    def start(self, plan, background=True):
        p = validate_plan(plan)
        rid = 'team-' + uuid.uuid4().hex
        d = self.root / rid
        with repository_lock(p['repo']) as lockdir:
            leases = list(lockdir.glob('execution-*.json'))
            if leases:
                raise BridgeError('An existing bridge execution claims this repository; finish/recover it first: ' + str(leases[0]))
            if (lockdir / 'owner.json').exists():
                owner = read_json(lockdir / 'owner.json')
                previous = Path(owner['state_dir']) / owner['run_id'] / 'state.json'
                if previous.is_file() and read_json(previous).get('status') in RUN_DONE:
                    (lockdir / 'owner.json').unlink()
                else:
                    raise BridgeError('Repository already claimed: ' + json.dumps(owner, ensure_ascii=False))
            d.mkdir()
            (d / 'worktrees').mkdir()
            (d / 'checks').mkdir()
            s = {'version': 1, 'run_id': rid, 'revision': 0, 'status': 'running', 'plan': p,
                 'created_at': utc(), 'deadline': time.time() + p['deadline_seconds'],
                 'integration_head': p['base'], 'integration_branch': 'refs/heads/zcode-team/' + rid,
                 'executor_tokens': 0, 'usage_records': {}, 'usage_history_complete': True,
                 'unknown_execution_count': 0, 'executor_usage_complete': True,
                 'external_agent_usage': 'unknown', 'source_workspace_dirty': not clean(p['repo']),
                 'tasks': {t['id']: {'spec': t, 'state': 'planned', 'attempt': 0,
                    'external_blocks': list(t['external_blocks']), 'history': []} for t in p['tasks']}}
            atomic_json(d / 'state.json', s)
            atomic_json(lockdir / 'owner.json', {'run_id': rid, 'state_dir': str(self.root), 'worktrees': []})
            git(p['repo'], 'update-ref', s['integration_branch'], p['base'], '0' * 40)
            self._save(s, 'run.started')
        if background:
            self.wake(rid)
        return self.observe(rid)

    def wake(self, rid):
        self.directory(rid)
        launch_background([sys.executable, str(ROOT / 'team.py'), '--state-dir', str(self.root), '_run', rid])

    def observe(self, rid):
        s = self._load(rid)
        daemon = self.directory(rid) / 'daemon.json'
        s['scheduler_alive'] = False
        if daemon.exists():
            owner = read_json(daemon)
            s['scheduler_alive'] = alive(owner)
        s['next_decisions'] = [{'task_id': tid, 'state': t['state'], 'candidate_commit': t.get('candidate'),
                                'review_packet': t.get('review_packet'), 'reason': t.get('error'),
                                'external_blocks': t['external_blocks']}
                               for tid, t in s['tasks'].items()
                               if t['state'] in ('awaiting_review', 'needs_changes', 'failed', 'integration_failed') or t['external_blocks']]
        # Keep repeated observations small; full contracts, model responses and
        # test logs remain in versioned local artifacts, not every status reply.
        s['state_file'] = str(self.directory(rid) / 'state.json')
        s.setdefault('executor_usage_complete', False)
        s.setdefault('unknown_execution_count', None)
        s['plan'] = {k: v for k, v in s['plan'].items() if k not in ('tasks', 'integration_tests')}
        for tid, t in s['tasks'].items():
            if t['state'] in JOB_ACTIVE and callable(getattr(self.executor, 'progress', None)):
                progress = self.executor.progress(t['bridge_task'])
                if progress:
                    t['progress'] = progress
                    if progress.get('warning_active') or progress.get('first_delivery', {}).get('warning_active'):
                        s['next_decisions'].append({'task_id': tid, 'state': t['state'],
                             'reason': 'first_delivery_pending' if progress.get('first_delivery',{}).get('warning_active') else 'no_observable_progress',
                             'progress': progress})
            t['spec'] = {k: v for k, v in t['spec'].items() if k != 'contract'}
            for key in ('history', 'repair_evidence', 'repair_findings', 'fresh_recovery_prompt', 'fresh_recovery_context'):
                t.pop(key, None)
            if 'result' in t:
                t['result'] = {k: v for k, v in t['result'].items() if k in
                    ('status', 'sessionId', 'observed_model', 'observed_provider', 'usage', 'usage_complete', 'subagents',
                     'progress', 'cleanup_confirmed', 'result_file', 'blockers', 'reasoning_effort', 'requested_reasoning_effort', 'supported_reasoning_efforts', 'first_delivery')}
                if isinstance(t['result'].get('first_delivery'),dict):
                    delivery=t['result']['first_delivery']
                    t['result']['first_delivery']={k:v for k,v in delivery.items() if k!='files'}
                    t['result']['first_delivery']['file_count']=len(delivery.get('files',[]))
            for key, source in [('validation', 'check'), ('integration_validation', 'integration_check')]:
                if key in t:
                    t[key] = {k: v for k, v in t[key].items() if k != 'tests'}
                    if t.get(source):
                        t[key]['report_file'] = str(Path(t[source]) / 'result.json')
        return s

    def _assert_owner(self, s, lockdir):
        owner = read_json(lockdir / 'owner.json')
        if owner['run_id'] != s['run_id'] or owner['state_dir'] != str(self.root):
            raise BridgeError('Repository ownership changed')
        return owner

    def _candidate_valid(self, t):
        return head(t['worktree']) == t['candidate'] and clean(t['worktree']) and \
            snapshot(t['worktree'], self.root)['digest'] == t['candidate_digest']

    def decide(self, rid, expected_revision, decision, background=True):
        original = self._load(rid)
        with repository_lock(original['plan']['repo']) as lockdir:
            s = self._load(rid)
            self._assert_owner(s, lockdir)
            if s['revision'] != expected_revision:
                raise BridgeError('Stale revision; observe again and confirm the candidate is unchanged')
            if not isinstance(decision, dict):
                raise BridgeError('Decision must be an object')
            action = decision.get('action')
            tid = decision.get('task_id')
            if tid not in s['tasks']:
                raise BridgeError('Unknown task ID')
            t = s['tasks'][tid]
            if action == 'resolve_block':
                block = decision.get('block')
                if block not in t['external_blocks'] or not decision.get('evidence'):
                    raise BridgeError('Resolve an existing block with evidence')
                t['external_blocks'].remove(block)
            elif action in ('approve', 'revise'):
                if t['state'] not in ('awaiting_review', 'needs_changes', 'integration_failed'):
                    raise BridgeError('Task has no reviewable candidate')
                if decision.get('candidate_commit') != t.get('candidate') or not self._candidate_valid(t):
                    raise BridgeError('Candidate changed; old review is invalid')
                if not isinstance(decision.get('reviewer'), str) or not decision['reviewer'].strip() or not decision.get('summary'):
                    raise BridgeError('Decision needs reviewer and evidence summary')
                if action == 'approve':
                    if t['state'] != 'awaiting_review' or t.get('validation', {}).get('status') not in ('passed', 'not_run'):
                        raise BridgeError('Failed tests or integration cannot be approved away')
                    t['review'] = copy.deepcopy(decision)
                    t['state'] = 'accepted'
                else:
                    strings(decision.get('findings', []), 'findings')
                    if not decision.get('findings'):
                        raise BridgeError('Revision requires concrete findings')
                    self._repair(s, t, decision['findings'])
            elif action == 'retry':
                if t['state'] not in ('failed', 'needs_changes') or not decision.get('summary'):
                    raise BridgeError('Retry needs a failed execution and diagnosis')
                latest = self.executor.poll(t['bridge_task']) if t.get('bridge_task') else t.get('result', {})
                if latest.get('cleanup_confirmed') is False:
                    raise BridgeError('Recover the bridge process before retrying')
                if zero_output_timeout(latest) and not t.get('has_implementation') and not t.get('candidate'):
                    self._zero_recovery(s,t,decision.get('recovery_prompt') or t['spec']['contract'].get('recovery_prompt'),
                                        decision.get('recovery_context',t['spec']['contract'].get('recovery_context','')))
                else:
                    self._repair(s, t, [decision['summary']])
            elif action == 'retry_integration':
                if t['state'] != 'integration_failed' or not decision.get('summary') or not self._candidate_valid(t):
                    raise BridgeError('Retry integration needs unchanged candidate and diagnosis')
                t['state'] = 'accepted'
                t.pop('integration_check', None)
                t.pop('trial', None)
            elif action == 'retry_checks':
                if t['state'] != 'needs_changes' or not decision.get('summary') or not self._candidate_valid(t):
                    raise BridgeError('Retry checks needs an unchanged candidate and diagnosis')
                if t.get('check_retries', 0) >= s['plan']['max_repairs']:
                    raise BridgeError('Check retry budget exhausted; replan')
                t['check_retries'] = t.get('check_retries', 0) + 1
                t['state'] = 'checking'
                t.pop('check', None)
                t.pop('validation', None)
            else:
                raise BridgeError('Unknown decision action')
            t['history'].append({'at': utc(), 'decision': copy.deepcopy(decision)})
            t.pop('error', None)
            self._save(s, 'decision.' + action)
        if background:
            self.wake(rid)
        return self.observe(rid)

    def _repair(self, s, t, findings):
        if t['attempt'] >= 1 + s['plan']['max_repairs']:
            raise BridgeError('Repair budget exhausted; coordinator must replan')
        t.pop('fresh_recovery_prompt', None)
        t.pop('fresh_recovery_context', None)
        t['repair_findings'] = findings
        evidence = t.get('integration_validation') if t['state'] == 'integration_failed' else t.get('validation')
        if evidence:
            t['repair_evidence'] = copy.deepcopy(evidence)
            run_dir = self.directory(s['run_id'])
            for test in t['repair_evidence'].get('tests', []):
                log = Path(test['log']).resolve()
                if not log.is_relative_to(run_dir):
                    raise BridgeError('Verification log is outside this run')
                with log.open('rb') as f:
                    f.seek(max(0, log.stat().st_size - 12000))
                    test['output_tail'] = f.read().decode('utf-8', 'replace')
        t['state'] = 'ready'
        for key in ('validation', 'review', 'check', 'integration_check', 'trial'):
            t.pop(key, None)

    def _zero_recovery(self, s, t, prompt, context=''):
        if t.get('zero_output_retries',0) >= 1:
            raise BridgeError('Second zero-output failure; coordinator must replan, not retry again')
        if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>4000 or prompt.strip()==t['spec']['contract']['prompt'].strip():
            raise BridgeError('Zero-output retry requires an explicit smaller recovery_prompt')
        if not isinstance(context,str) or len(context)>4000:
            raise BridgeError('recovery_context must be concise verified facts')
        self._repair(s,t,[])
        t.pop('repair_evidence',None)
        t['zero_output_retries'] = t.get('zero_output_retries',0)+1
        t['fresh_recovery_prompt'] = prompt
        t['fresh_recovery_context'] = context
        t.pop('error',None)

    def cancel(self, rid, background=True):
        d = self.directory(rid)
        (d / 'cancel.request').touch(exist_ok=True)
        if background:
            self.wake(rid)
        return {'run_id': rid, 'status': 'cancel_requested'}

    def _start_check(self, s, t, integration=False):
        d = self.directory(s['run_id']) / 'checks' / uuid.uuid4().hex
        d.mkdir()
        workspace = t['trial'] if integration else t['worktree']
        tests = s['plan']['integration_tests'] if integration else t['spec']['contract']['tests']
        # The test worker rechecks the expected candidate digest before execution.
        # Reuse that already frozen digest instead of hashing it again here.
        expected = snapshot(workspace, self.root)['digest'] if integration else t['candidate_digest']
        job = {'run_dir': str(self.directory(s['run_id'])), 'cwd': workspace, 'tests': tests,
               'source_digest': expected, 'state_root': str(self.root),
               'commit': head(workspace), 'deadline': s['deadline']}
        atomic_json(d / 'request.json', job)
        key = 'integration_check' if integration else 'check'
        t[key] = str(d)
        self._save(s, 'check.reserved')
        launch_background([sys.executable, str(ROOT / 'team.py'), '_check', str(d)])

    def _poll_check(self, path):
        d = Path(path)
        if (d / 'result.json').exists():
            return read_json(d / 'result.json')
        if (d / 'owner.json').exists():
            owner = read_json(d / 'owner.json')
            if not alive(owner):
                cleanup_tests(d)
                return {'status': 'interrupted', 'tests': [], 'source_unchanged': False}
        elif time.time() - (d / 'request.json').stat().st_mtime > 15:
            return {'status': 'not_started', 'tests': [], 'source_unchanged': False}
        return None

    def _freeze(self, s, t, result):
        self._account_result(s, t['bridge_task'], result)
        t['has_implementation'] = bool(t.get('has_implementation') or t.get('candidate')
                                      or t.get('result',{}).get('changed_files') or result.get('changed_files'))
        t['result'] = result
        if result.get('status') != 'completed' or result.get('cleanup_confirmed') is not True:
            t.update(state='failed', error='Bridge execution was not completed with confirmed cleanup')
            if zero_output_timeout(result) and not t['has_implementation']:
                prompt = t['spec']['contract'].get('recovery_prompt')
                if prompt and not t.get('zero_output_retries') and t['attempt'] < 1+s['plan']['max_repairs'] and result.get('observed_model') == s['plan']['expected_model']:
                    self._zero_recovery(s,t,prompt,t['spec']['contract'].get('recovery_context',''))
                    t['history'].append({'at':utc(),'action':'auto_recovery','reason':'zero_output_timeout','session':'fresh'})
                else:
                    t['error'] = ('Second zero-output failure; replan required' if t.get('zero_output_retries') else
                                  'Zero-output timeout; supply a smaller recovery_prompt or replan')
            return
        if result.get('observed_model') != s['plan']['expected_model']:
            t.update(state='failed', error='Expected model was not verified')
            return
        latest = snapshot(t['worktree'], self.root)
        scope = changes(read_json(Path(t['worktree']).parent / (t['spec']['id'] + '-initial.json')),
                        latest, t['spec']['contract'])
        if scope['scope_violations']:
            t.update(state='failed', error='Cumulative scope violation: ' + ', '.join(scope['scope_violations']))
            return
        t['state'] = 'freezing'
        self._save(s, 'candidate.freezing')
        t['candidate'] = freeze(t['worktree'], t['attempt_head'], 'Candidate ' + s['run_id'] + '/' + t['spec']['id'])
        t['candidate_digest'] = snapshot(t['worktree'], self.root)['digest']
        packet = self.directory(s['run_id']) / (t['spec']['id'] + '-review.json')
        patch_file = packet.with_suffix('.patch')
        patch_file.write_bytes(git(s['plan']['repo'], 'diff', '--binary', t['base'], t['candidate'], '--', '.'))
        atomic_json(packet, {'task_id': t['spec']['id'], 'candidate_commit': t['candidate'],
                    'base_commit': t['base'], 'source_digest': t['candidate_digest'],
                    'worktree': t['worktree'], 'patch': str(patch_file), 'contract': t['spec']['contract'],
                    'instructions': 'Review this fixed candidate independently. Check specification and standards. '
                                    'Return concrete findings; do not edit source. Verification is recorded in team state.'})
        t.update(state='checking', review_packet=str(packet))

    def _account_result(self, s, bridge_task, result):
        if 'usage_records' not in s:
            s.update(usage_records={}, legacy_usage_tokens=s['executor_tokens'], usage_history_complete=False)
        if bridge_task not in s['usage_records']:
            tokens = result.get('usage', {}).get('totalTokens')
            s['usage_records'][bridge_task] = {'tokens': tokens if type(tokens) is int else None,
                                              'complete': result.get('usage_complete', type(tokens) is int),
                                              'status': result.get('status')}
        rows = s['usage_records'].values()
        s['executor_tokens'] = s.get('legacy_usage_tokens', 0) + sum(r['tokens'] for r in rows if r['tokens'] is not None)
        s['unknown_execution_count'] = sum(r['tokens'] is None or r.get('complete') is False for r in rows) if s.get('usage_history_complete') else None
        s['executor_usage_complete'] = s.get('usage_history_complete', False) and s['unknown_execution_count'] == 0

    def _dispatch(self, s, t, lockdir):
        tid = t['spec']['id']
        owner = self._assert_owner(s, lockdir)
        if not t.get('worktree'):
            workspace = self.directory(s['run_id']) / 'worktrees' / tid
            t.update(state='preparing', worktree=str(workspace), base=s['integration_head'])
            self._save(s, 'worktree.preparing')
            add_worktree(s['plan']['repo'], workspace, t['base'])
            atomic_json(workspace.parent / (tid + '-initial.json'), snapshot(workspace, self.root))
        owner['worktrees'] = sorted(set(owner['worktrees'] + [canonical(t['worktree'])]))
        atomic_json(lockdir / 'owner.json', owner)
        t['attempt_head'] = head(t['worktree'])
        c = copy.deepcopy(t['spec']['contract'])
        resume = None
        if t.get('fresh_recovery_prompt'):
            c['prompt'] = t['fresh_recovery_prompt']
            if t.get('fresh_recovery_context'):
                c['prompt'] += '\nVerified controller facts:\n' + t['fresh_recovery_context']
            c = execution_defaults(c,'edit',c.get('tool_policy','code-local'))
        elif t.get('repair_findings'):
            c['prompt'] += '\nController findings to fix within the same scope:\n' + '\n'.join(t['repair_findings'])
            previous = t.get('result', {})
            if previous.get('observed_model') == s['plan']['expected_model']:
                resume = previous.get('sessionId')
        request = {'cwd': t['worktree'], 'mode': 'edit', 'resume': resume, 'contract': c,
                   'timeout': min(s['plan']['task_timeout'], max(1, s['deadline'] - time.time())),
                   'idle_timeout': s['plan']['idle_timeout'], 'run_tests': False,
                   'progress_warning': s['plan'].get('progress_warning', 120),
                   'progress_timeout': s['plan'].get('progress_timeout'),
                   'expected_model': s['plan']['expected_model'], 'team_run': s['run_id']}
        if t.get('repair_evidence'):
            request['test_feedback'] = t['repair_evidence']
        t['bridge_task'] = self.executor.prepare(request)
        t['attempt'] += 1
        t['state'] = 'dispatching'
        self._save(s, 'execution.reserved')
        self.executor.launch(t['bridge_task'])
        t['state'] = 'running'

    def tick(self, rid):
        initial = self._load(rid)
        if initial['status'] in RUN_DONE:
            with repository_lock(initial['plan']['repo']) as lockdir:
                owner = lockdir / 'owner.json'
                if owner.exists() and read_json(owner)['run_id'] == rid:
                    owner.unlink()
            return initial
        with repository_lock(initial['plan']['repo']) as lockdir:
            s = self._load(rid)
            self._assert_owner(s, lockdir)
            before = json.dumps(s, sort_keys=True)
            d = self.directory(rid)
            expired = time.time() >= s['deadline']
            if (d / 'cancel.request').exists() or expired:
                (d / 'cancel.request').touch(exist_ok=True)
                pending = False
                for t in s['tasks'].values():
                    if t['state'] in JOB_ACTIVE:
                        self.executor.cancel(t['bridge_task'])
                        result = self.executor.poll(t['bridge_task'])
                        if result.get('status') in TERMINAL:
                            self._account_result(s, t['bridge_task'], result)
                        if result.get('status') not in TERMINAL or result.get('cleanup_confirmed') is False:
                            pending = True
                            continue
                    for key in ('check', 'integration_check'):
                        if t.get(key) and self._poll_check(t[key]) is None:
                            pending = True
                    if t['state'] != 'integrated':
                        t['state'] = 'cancelled'
                s['status'] = 'cancelling' if pending else 'cancelled'
                s['cancel_reason'] = 'deadline' if expired else 'controller'
                self._save(s, 'run.cancellation')
                if not pending:
                    (lockdir / 'owner.json').unlink()
                return s
            for t in s['tasks'].values():
                try:
                    if t['state'] == 'dispatching':
                        self.executor.launch(t['bridge_task'])
                        t['state'] = 'running'
                    if t['state'] == 'running':
                        result = self.executor.poll(t['bridge_task'])
                        if result.get('status') in TERMINAL:
                            self._freeze(s, t, result)
                        elif result.get('worker_missing'):
                            t['error'] = 'Bridge worker missing; cancel/recover before resuming'
                    elif t['state'] == 'preparing_integration':
                        t.update(state='integration_failed', error='Integration Git operation interrupted; inspect retained trial before retry')
                    elif t['state'] in ('preparing', 'freezing'):
                        t.update(state='failed', error='Coordinator interrupted a Git operation; inspect retained worktree before retry')
                    if t['state'] == 'checking' and t.get('check'):
                        result = self._poll_check(t['check'])
                        if result:
                            t['validation'] = result
                            t['state'] = 'awaiting_review' if result['status'] in ('passed', 'not_run') and self._candidate_valid(t) else 'needs_changes'
                    if t['state'] == 'integrating' and t.get('integration_check'):
                        result = self._poll_check(t['integration_check'])
                        if result:
                            t['integration_validation'] = result
                            if result['status'] in ('passed', 'not_run') and self._candidate_valid(t) and clean(t['trial']) and head(t['trial']) == t['trial_commit']:
                                current = git(s['plan']['repo'], 'rev-parse', s['integration_branch']).decode().strip()
                                if current == s['integration_head']:
                                    git(s['plan']['repo'], 'update-ref', s['integration_branch'], t['trial_commit'], current)
                                elif current != t['trial_commit']:
                                    raise BridgeError('Integration branch changed externally')
                                s['integration_head'] = t['trial_commit']
                                t['state'] = 'integrated'
                            else:
                                t.update(state='integration_failed', error='Integration verification failed or source changed')
                except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
                    t.update(state='integration_failed' if t['state'] in ('integrating', 'preparing_integration') else 'failed', error=str(exc))
            check_busy = any(t['state'] in ('checking', 'integrating') and
                             (t.get('check') if t['state'] == 'checking' else t.get('integration_check'))
                             for t in s['tasks'].values())
            if not check_busy:
                for t in s['tasks'].values():
                    if t['state'] == 'checking' and not t.get('check'):
                        self._start_check(s, t)
                        check_busy = True
                        break
            if not check_busy:
                for t in s['tasks'].values():
                    if t['state'] == 'accepted':
                        try:
                            if not self._candidate_valid(t):
                                raise BridgeError('Reviewed candidate was modified')
                            t['state'] = 'preparing_integration'
                            t['trial'] = str(d / 'worktrees' / ('integration-' + uuid.uuid4().hex[:12]))
                            self._save(s, 'integration.preparing')
                            t['trial_commit'] = apply_candidate(s['plan']['repo'], t['trial'], s['integration_head'], t['base'], t['candidate'])
                            t['state'] = 'integrating'
                            self._start_check(s, t, integration=True)
                        except (BridgeError, OSError, subprocess.SubprocessError) as exc:
                            t.update(state='integration_failed', error=str(exc))
                        break
            active = sum(t['state'] in JOB_ACTIVE for t in s['tasks'].values())
            backlog = sum(t['state'] in ('checking', 'awaiting_review', 'accepted', 'integrating') for t in s['tasks'].values())
            budget_ok = s['plan']['executor_token_limit'] is None or (s['executor_tokens'] < s['plan']['executor_token_limit'] and s.get('executor_usage_complete', False))
            s['admission_blocker'] = None if budget_ok else 'executor token limit reached or usage incomplete; replan before new calls'
            for t in s['tasks'].values():
                if t['state'] not in ('planned', 'blocked', 'ready'):
                    continue
                dependencies = [x for x in t['spec']['depends_on'] if s['tasks'][x]['state'] != 'integrated']
                occupied = [x for x in s['tasks'].values() if x is not t and x['attempt'] and x['state'] != 'integrated']
                overlaps = any(task_overlap(t['spec'], x['spec']) for x in occupied)
                t['state'] = 'blocked' if dependencies or t['external_blocks'] or overlaps else 'ready'
                t['waiting_for'] = dependencies + t['external_blocks'] + (['shared write scope/resource'] if overlaps else [])
                if t['state'] == 'ready' and active < s['plan']['max_writers'] and backlog + active < s['plan']['max_pending_reviews'] and budget_ok:
                    try:
                        self._dispatch(s, t, lockdir)
                        active += 1
                    except (BridgeError, OSError, subprocess.SubprocessError) as exc:
                        t.update(state='failed', error=str(exc))
            if all(t['state'] == 'integrated' for t in s['tasks'].values()):
                s['status'] = 'completed'
            if json.dumps(s, sort_keys=True) != before:
                self._save(s, 'run.progress')
            if s['status'] == 'completed':
                (lockdir / 'owner.json').unlink()
            return s


def task_overlap(a, b):
    if set(a['resources']) & set(b['resources']):
        return True
    def prefix(value):
        import re
        return re.split(r'[?*\[]', value, 1)[0]
    for p in a['contract']['allowed_files']:
        for q in b['contract']['allowed_files']:
            pp, qq = prefix(p), prefix(q)
            if p == q or ((pp != p or qq != q) and (pp.startswith(qq) or qq.startswith(pp))):
                return True
    return False


def cleanup_tests(directory):
    owner_file = Path(directory) / 'active-test.json'
    if owner_file.exists():
        owner = read_json(owner_file)
        if identity(owner['pid']) == owner['start'] and os.getpgid(owner['pid']) == owner['pid']:
            os.killpg(owner['pid'], signal.SIGKILL)


def check_worker(directory):
    d = Path(directory)
    import fcntl
    with (d / 'worker.lock').open('a+') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (d / 'result.json').exists():
            return
        atomic_json(d / 'owner.json', {'pid': os.getpid(), 'start': identity(os.getpid())})
        req = read_json(d / 'request.json')
        stopped = [False]
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: stopped.__setitem__(0, True))
        cancelled = lambda: stopped[0] or (Path(req['run_dir']) / 'cancel.request').exists() or time.time() >= req['deadline']
        try:
            before = snapshot(req['cwd'], req['state_root'])
            if before['digest'] != req['source_digest'] or head(req['cwd']) != req['commit']:
                raise BridgeError('Source changed before verification')
            result = execute_tests({'tests': req['tests']}, req['cwd'], d, cancelled, lambda _: None)
            after = snapshot(req['cwd'], req['state_root'])
            result.update(source_digest=before['digest'], commit=req['commit'],
                          source_unchanged=after['digest'] == before['digest'] and head(req['cwd']) == req['commit'])
            if not result['source_unchanged']:
                result['status'] = 'source_changed'
            if cancelled():
                result['status'] = 'cancelled'
        except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
            cleanup_tests(d)
            result = {'status': 'failed', 'error': str(exc), 'source_unchanged': False}
        result['finished_at'] = utc()
        atomic_json(d / 'result.json', result)


def daemon(coordinator, rid):
    import fcntl
    d = coordinator.directory(rid)
    with (d / 'daemon.lock').open('a+') as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        atomic_json(d / 'daemon.json', {'pid': os.getpid(), 'start': identity(os.getpid())})
        while True:
            try:
                s = coordinator.tick(rid)
                if s['status'] in RUN_DONE:
                    return
            except (BridgeError, OSError, ValueError, subprocess.SubprocessError) as exc:
                atomic_json(d / 'scheduler-error.json', {'at': utc(), 'error': str(exc)})
                return
            time.sleep(1)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir')
    sub = parser.add_subparsers(dest='command', required=True)
    start = sub.add_parser('start')
    start.add_argument('--plan', required=True)
    for cmd in ('observe', 'resume', 'cancel', '_run'):
        p = sub.add_parser(cmd)
        p.add_argument('run_id')
    p = sub.add_parser('decide')
    p.add_argument('run_id')
    p.add_argument('--revision', type=int, required=True)
    p.add_argument('--decision-file', required=True)
    p = sub.add_parser('_check')
    p.add_argument('directory')
    args = parser.parse_args(argv)
    try:
        if args.command == '_check':
            check_worker(args.directory)
            return 0
        c = WorkCoordinator(args.state_dir)
        if args.command == 'start':
            result = c.start(read_json(args.plan))
        elif args.command == 'decide':
            result = c.decide(args.run_id, args.revision, read_json(args.decision_file))
        elif args.command == 'cancel':
            result = c.cancel(args.run_id)
        elif args.command == 'resume':
            c.wake(args.run_id)
            result = c.observe(args.run_id)
        elif args.command == '_run':
            daemon(c, args.run_id)
            return 0
        else:
            result = c.observe(args.run_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except (BridgeError, OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
