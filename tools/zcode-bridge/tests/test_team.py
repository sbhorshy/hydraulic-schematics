import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_contract import BridgeError, atomic_json, read_json
from team import WorkCoordinator, validate_plan
from team_workspace import check_bridge_owner, common_dir, git, head


class FakeExecutor:
    def __init__(self):
        self.requests = {}
        self.results = {}
        self.launches = []
        self.auto = True

    def prepare(self, request):
        tid = 'exec-' + str(len(self.requests) + 1)
        self.requests[tid] = copy.deepcopy(request)
        return tid

    def launch(self, tid):
        if tid not in self.launches:
            self.launches.append(tid)

    def poll(self, tid):
        if tid in self.results:
            return self.results[tid]
        if not self.auto:
            return {'status': 'running'}
        req = self.requests[tid]
        filename = req['contract']['allowed_files'][0]
        Path(req['cwd'], filename).write_text('fixed\n')
        self.results[tid] = {'status': 'completed', 'cleanup_confirmed': True,
                             'observed_model': req['expected_model'], 'sessionId': 'sess_' + tid,
                             'usage': {'totalTokens': 100}, 'response': 'done'}
        return self.results[tid]

    def cancel(self, tid):
        self.results[tid] = {'status': 'cancelled', 'cleanup_confirmed': True}


class TeamTest(unittest.TestCase):
    def test_verify_honors_team_claim_and_claims_repo_during_tests(self):
        import bridge
        from test_bridge import FixtureBackend
        store = bridge.Store(self.root / 'bridge-state')
        tid = store.create({'cwd': str(self.repo), 'mode': 'edit', 'resume': None,
            'timeout': 5, 'idle_timeout': 2, 'run_tests': False,
            'contract': {'version': 1, 'prompt': 'ok', 'allowed_files': [],
                         'tests': [{'id': 'unit', 'argv': [sys.executable, '-c', 'pass'], 'timeout': 2}]}})
        self.assertEqual(bridge.worker(store, tid, FixtureBackend(), False)['status'], 'completed')
        run_tests = bridge.execute_tests

        def check_claim(*args, **kwargs):
            with self.assertRaisesRegex(BridgeError, 'existing bridge execution'):
                self.coordinator.start({'version': 1, 'repo': str(self.repo),
                                        'tasks': [self.task('a')]}, background=False)
            return run_tests(*args, **kwargs)

        with patch.object(bridge, 'execute_tests', side_effect=check_claim):
            self.assertEqual(bridge.verify(store, tid)['status'], 'passed')
        self.start()
        with patch.object(bridge, 'execute_tests') as execute:
            with self.assertRaisesRegex(BridgeError, 'claimed by team'):
                bridge.verify(store, tid)
            execute.assert_not_called()

    def test_new_plan_freezes_development_and_preserves_explicit_policy(self):
        raw = {'version': 1, 'repo': str(self.repo), 'tasks': [self.task('a')]}
        normalized = validate_plan(raw)
        self.assertEqual(normalized['tasks'][0]['contract']['tool_policy'], 'development')
        self.assertNotIn('tool_policy', raw['tasks'][0]['contract'])
        raw['tasks'][0]['contract']['tool_policy'] = 'code-local'
        self.assertEqual(validate_plan(raw)['tasks'][0]['contract']['tool_policy'], 'code-local')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='zcode-team-test-')
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / 'base.txt').write_text('base\n')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'base')
        self.original = head(self.repo)
        self.executor = FakeExecutor()
        self.coordinator = WorkCoordinator(self.root / 'state', self.executor)
        self.rid = None
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.rid:
            self.coordinator.cancel(self.rid, background=False)
            for _ in range(100):
                s = self.coordinator.tick(self.rid)
                if s['status'] in ('cancelled', 'completed'):
                    break
                time.sleep(.05)
        self.temp.cleanup()

    def task(self, tid, depends=(), tests=None, **kwargs):
        return {'id': tid, 'depends_on': list(depends), 'contract': {
            'version': 1, 'prompt': 'implement ' + tid, 'allowed_files': [tid + '.txt'],
            'tests': tests if tests is not None else [{'id': 'content', 'argv': [sys.executable, '-c',
                        f"from pathlib import Path; assert Path('{tid}.txt').read_text() == 'fixed\\n'"], 'timeout': 5}]}, **kwargs}

    def start(self, tasks=None, **options):
        plan = {'version': 1, 'repo': str(self.repo), 'tasks': tasks or [self.task('a')], **options}
        s = self.coordinator.start(plan, background=False)
        self.rid = s['run_id']
        return s

    def until(self, predicate, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            s = self.coordinator.tick(self.rid)
            if predicate(s):
                return s
            time.sleep(.05)
        self.fail('Timed out: ' + json.dumps(self.coordinator.observe(self.rid)))

    def approve(self, s, tid):
        return self.coordinator.decide(self.rid, s['revision'], {'action': 'approve', 'task_id': tid,
                        'candidate_commit': s['tasks'][tid]['candidate'], 'reviewer': 'independent-test-reviewer',
                        'summary': 'checked fixed diff and expected behavior'}, background=False)

    def test_pipeline_dependency_review_and_integration(self):
        (self.repo / 'user-dirty.txt').write_text('do not touch')
        self.start([self.task('a'), self.task('b', depends=['a'])])
        s = self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')
        self.assertEqual(s['tasks']['b']['state'], 'blocked')
        self.assertEqual(len(self.executor.launches), 1)
        self.approve(s, 'a')
        s = self.until(lambda s: s['tasks']['b']['state'] == 'awaiting_review')
        self.assertEqual(s['tasks']['a']['state'], 'integrated')
        self.assertEqual(s['tasks']['b']['base'], s['integration_head'])
        self.approve(s, 'b')
        s = self.until(lambda s: s['status'] == 'completed')
        self.assertEqual(git(self.repo, 'show', s['integration_head'] + ':a.txt'), b'fixed\n')
        self.assertEqual(git(self.repo, 'show', s['integration_head'] + ':b.txt'), b'fixed\n')
        self.assertEqual(head(self.repo), self.original)
        self.assertEqual((self.repo / 'user-dirty.txt').read_text(), 'do not touch')
        self.assertFalse((self.repo / 'a.txt').exists())

    def test_independent_task_runs_during_first_review(self):
        self.start([self.task('a'), self.task('b')])
        s = self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')
        self.assertEqual(len(self.executor.launches), 2)
        self.assertNotEqual(s['tasks']['a']['worktree'], s['tasks']['b']['worktree'])

    def test_same_repo_claim_across_state_dirs_and_nested_cwd(self):
        self.start()
        nested = self.repo / 'nested'
        nested.mkdir()
        other = WorkCoordinator(self.root / 'other', FakeExecutor())
        with self.assertRaisesRegex(BridgeError, 'claimed'):
            other.start({'version': 1, 'repo': str(nested), 'tasks': [self.task('b')]}, background=False)
        with self.assertRaisesRegex(BridgeError, 'claimed'):
            check_bridge_owner(nested)

    def test_existing_bridge_lease_blocks_team_and_late_team_worker_is_refused(self):
        from team_workspace import claim_bridge, release_bridge_claim
        lease = claim_bridge(self.repo, None, 'task-old', self.root / 'old-task')
        with self.assertRaisesRegex(BridgeError, 'existing bridge'):
            self.start()
        release_bridge_claim(lease, 'task-old')
        self.start()
        s = self.coordinator.tick(self.rid)
        workspace = s['tasks']['a']['worktree']
        self.coordinator.cancel(self.rid, background=False)
        self.coordinator.tick(self.rid)
        with self.assertRaisesRegex(BridgeError, 'released'):
            claim_bridge(workspace, self.rid, 'task-late', self.root / 'late-task')

    def test_external_block_needs_evidence(self):
        self.start([self.task('a', external_blocks=['issue:45'])])
        s = self.coordinator.tick(self.rid)
        self.assertFalse(self.executor.launches)
        with self.assertRaises(BridgeError):
            self.coordinator.decide(self.rid, s['revision'], {'action': 'resolve_block', 'task_id': 'a', 'block': 'issue:45'}, False)
        self.coordinator.decide(self.rid, s['revision'], {'action': 'resolve_block', 'task_id': 'a',
                               'block': 'issue:45', 'evidence': 'accepted upstream commit'}, False)
        self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')

    def test_cycles_and_unknown_worker_fields_rejected_before_claim(self):
        for tasks in ([self.task('a', ['b']), self.task('b', ['a'])], [self.task('a', ['missing'])]):
            with self.assertRaises(BridgeError):
                validate_plan({'version': 1, 'repo': str(self.repo), 'tasks': tasks})
        t = self.task('a')
        t['contract']['expected_model'] = 'not a worker contract field'
        with self.assertRaises(BridgeError):
            validate_plan({'version': 1, 'repo': str(self.repo), 'tasks': [t]})
        self.assertFalse((common_dir(self.repo) / 'zcode-bridge-team' / 'owner.json').exists())

    def test_stale_revision_and_changed_candidate_rejected(self):
        self.start()
        s = self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')
        decision = {'action': 'approve', 'task_id': 'a', 'candidate_commit': s['tasks']['a']['candidate'],
                    'reviewer': 'reviewer', 'summary': 'passed'}
        with self.assertRaisesRegex(BridgeError, 'Stale'):
            self.coordinator.decide(self.rid, s['revision'] - 1, decision, False)
        Path(s['tasks']['a']['worktree'], 'a.txt').write_text('external edit')
        with self.assertRaisesRegex(BridgeError, 'changed'):
            self.coordinator.decide(self.rid, s['revision'], decision, False)

    def test_failed_tests_cannot_be_approved(self):
        self.start([self.task('a', tests=[{'id': 'fail', 'argv': [sys.executable, '-c', 'raise SystemExit(1)'], 'timeout': 5}])])
        s = self.until(lambda s: s['tasks']['a']['state'] == 'needs_changes')
        with self.assertRaisesRegex(BridgeError, 'cannot be approved'):
            self.approve(s, 'a')

    def test_review_repair_uses_same_session_and_bounded_attempts(self):
        self.start(max_repairs=1)
        s = self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')
        decision = {'action': 'revise', 'task_id': 'a', 'candidate_commit': s['tasks']['a']['candidate'],
                    'reviewer': 'reviewer', 'summary': 'specific issue', 'findings': ['Preserve expected newline']}
        self.coordinator.decide(self.rid, s['revision'], decision, False)
        s = self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')
        self.assertEqual(self.executor.requests['exec-2']['resume'], 'sess_exec-1')
        self.assertEqual(s['tasks']['a']['attempt'], 2)
        decision['candidate_commit'] = s['tasks']['a']['candidate']
        with self.assertRaisesRegex(BridgeError, 'budget exhausted'):
            self.coordinator.decide(self.rid, s['revision'], decision, False)

    def test_integration_failure_does_not_advance_branch(self):
        self.start(integration_tests=[{'id': 'integration', 'argv': [sys.executable, '-c', 'raise SystemExit(1)'], 'timeout': 5}])
        s = self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')
        self.approve(s, 'a')
        s = self.until(lambda s: s['tasks']['a']['state'] == 'integration_failed')
        self.assertEqual(s['integration_head'], self.original)
        self.assertEqual(git(self.repo, 'rev-parse', s['integration_branch']).decode().strip(), self.original)

    def test_restart_reuses_existing_execution_and_cancellation_releases_claim(self):
        self.executor.auto = False
        self.start()
        self.coordinator.tick(self.rid)
        restarted = WorkCoordinator(self.root / 'state', self.executor)
        restarted.tick(self.rid)
        self.assertEqual(len(self.executor.requests), 1)
        self.coordinator.cancel(self.rid, background=False)
        s = self.coordinator.tick(self.rid)
        self.assertEqual(s['status'], 'cancelled')
        check_bridge_owner(self.repo)
        self.assertFalse((common_dir(self.repo) / 'zcode-bridge-team' / 'owner.json').exists())

    def test_token_limit_stops_admission_without_invented_cost(self):
        self.start([self.task('a'), self.task('b')], executor_token_limit=100)
        s = self.until(lambda s: s['tasks']['a']['state'] == 'awaiting_review')
        self.assertEqual(len(self.executor.requests), 1)
        self.assertEqual(s['executor_tokens'], 100)
        self.assertEqual(s['external_agent_usage'], 'unknown')
        self.assertIn('limit', s['admission_blocker'])

    def test_two_writers_require_opt_in_and_resource_overlap_blocks(self):
        with self.assertRaisesRegex(BridgeError, 'experimental'):
            self.start(max_writers=2)
        self.executor.auto = False
        self.start([self.task('a', resources=['catalog']), self.task('b', resources=['catalog']), self.task('c')],
                   max_writers=2, experimental_parallel=True)
        s = self.coordinator.tick(self.rid)
        self.assertEqual(len(self.executor.requests), 2)
        self.assertEqual(s['tasks']['b']['state'], 'blocked')
        self.assertEqual(s['tasks']['a']['state'], 'running')
        self.assertEqual(s['tasks']['c']['state'], 'running')

    def test_wrong_model_is_failed_even_if_executor_claims_success(self):
        self.start()
        s = self.coordinator.tick(self.rid)
        tid = s['tasks']['a']['bridge_task']
        self.executor.results[tid] = {'status': 'completed', 'cleanup_confirmed': True, 'observed_model': 'wrong'}
        s = self.coordinator.tick(self.rid)
        self.assertEqual(s['tasks']['a']['state'], 'failed')

    def test_progress_warning_is_visible_without_changing_plan_revision(self):
        self.executor.auto = False
        self.start()
        self.coordinator.tick(self.rid)
        self.executor.progress = lambda _: {'warning_active': True, 'seconds_without_tool_completion': 125}
        a = self.coordinator.observe(self.rid)
        b = self.coordinator.observe(self.rid)
        self.assertEqual(a['revision'], b['revision'])
        self.assertEqual(a['next_decisions'][0]['reason'], 'no_observable_progress')

    def test_interrupted_usage_is_unknown_and_not_silently_zero(self):
        self.executor.auto = False
        self.start()
        self.coordinator.tick(self.rid)
        self.coordinator.cancel(self.rid, background=False)
        s = self.coordinator.tick(self.rid)
        self.assertEqual(s['executor_tokens'], 0)  # known/accounted tokens only
        self.assertEqual(s['unknown_execution_count'], 1)
        self.assertFalse(s['executor_usage_complete'])

    def test_cumulative_scope_cannot_be_hidden_by_retry_baseline(self):
        self.start()
        s = self.coordinator.tick(self.rid)
        Path(s['tasks']['a']['worktree'], 'base.txt').write_text('forbidden change')
        s = self.coordinator.tick(self.rid)
        self.assertEqual(s['tasks']['a']['state'], 'failed')
        self.assertIn('scope violation', s['tasks']['a']['error'])
        self.coordinator.decide(self.rid, s['revision'], {'action': 'retry', 'task_id': 'a',
                               'summary': 'Repair scope violation and rerun checks'}, False)
        s = self.coordinator.tick(self.rid)
        s = self.coordinator.tick(self.rid)
        self.assertEqual(s['tasks']['a']['state'], 'failed')
        self.assertIn('scope violation', s['tasks']['a']['error'])

    def test_legacy_bridge_entrypoint_cannot_bypass_team_claim(self):
        from bridge import Store, worker
        from unittest.mock import Mock
        self.start()
        store = Store(self.root / 'another-bridge-state')
        tid = store.create({'cwd': str(self.repo), 'mode': 'edit', 'resume': None,
                            'contract': self.task('a')['contract'], 'timeout': 10, 'idle_timeout': 5, 'run_tests': False})
        backend = Mock()
        result = worker(store, tid, backend, progress=False)
        self.assertEqual(result['status'], 'failed')
        self.assertIn('claimed', result['blockers'][0])
        backend.launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
