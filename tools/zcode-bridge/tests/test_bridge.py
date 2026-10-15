import contextlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from bridge_contract import BridgeError, atomic_json, contract, positive, read_json, snapshot
from bridge_transport import WindowsBackend, ps_command, ps_quote


class FixtureBackend:
    def __init__(self, cleanup_ok=True):
        self.cleanup_ok = cleanup_ok
        self.launched = False

    def doctor(self):
        return {'ready': True, 'capabilities': {'shell': False}}

    def launch(self, request, directory):
        self.launched = True
        self.request = request
        atomic_json(directory / 'transport.json', {'fixture': True})
        fixture = directory / 'fake_cli.py'
        fixture.write_bytes(Path(__file__).with_name('fake_cli.py').read_bytes())
        return subprocess.Popen([sys.executable, str(fixture),
                                 str(directory / 'request.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)

    def cleanup(self, process, directory):
        if process:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)
        return self.cleanup_ok


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cwd = self.root / 'workspace'
        self.cwd.mkdir()
        self.store = bridge.Store(self.root / 'state')

    def request(self, scenario='ok', **options):
        task = {'version': 1, 'prompt': scenario, 'tests': [], 'allowed_files': ['allowed.txt', 'child.pid']}
        task.update(options.pop('task', {}))
        request = {'cwd': str(self.cwd), 'mode': 'edit', 'resume': None, 'timeout': 5,
                   'idle_timeout': 2, 'contract': task, 'run_tests': False}
        request.update(options)
        return self.store.create(request)

    def run_task(self, scenario='ok', backend=None, **options):
        tid = self.request(scenario, **options)
        result = bridge.worker(self.store, tid, backend or FixtureBackend(), progress=False)
        return tid, result

    def test_completed_preserves_legacy_fields_but_does_not_claim_validation(self):
        tid, result = self.run_task()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['sessionId'], 'sess_fixture')
        self.assertEqual(result['response'], 'done')
        self.assertEqual(result['validation_status'], 'not_run')
        self.assertEqual(result['implementation_status'], 'reported_complete')
        self.assertEqual(result['usage']['inputTokens'], 100)
        self.assertEqual(self.store.status(tid)['status'], 'completed')
        self.assertTrue(result['cleanup_confirmed'])

    def test_event_allowlist_never_persists_private_payloads(self):
        tid, result = self.run_task()
        events = (self.store.task(tid) / 'events.jsonl').read_text()
        combined = events + json.dumps(result)
        for value in ('PRIVATE_', 'private-session-data', 'secret'):
            self.assertNotIn(value, combined)
        self.assertIn('tool.updated', events)
        self.assertNotIn('model.streaming', events)

    def test_permission_denial_stops_early_and_is_not_success(self):
        tid, result = self.run_task('deny')
        self.assertEqual(result['status'], 'blocked_permission')
        self.assertEqual(result['counters']['permission_denials'], 1)
        self.assertEqual(result['validation_status'], 'not_run')

    def test_shell_requirement_fails_before_launch(self):
        backend = FixtureBackend()
        _, result = self.run_task(backend=backend, task={'requires_shell': True})
        self.assertFalse(backend.launched)
        self.assertEqual(result['status'], 'blocked_permission')

    def test_subagents_require_verified_runtime_before_launch(self):
        backend = FixtureBackend()
        _, result = self.run_task(backend=backend, tool_policy='development', allow_subagents=True)
        self.assertFalse(backend.launched)
        self.assertIn('Constrained subagents require', ' '.join(result['blockers']))

    def test_model_identity_is_observed_and_mismatch_fails_closed(self):
        _, result = self.run_task(expected_model='fixture-model')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['observed_model'], 'fixture-model')
        _, result = self.run_task(expected_model='different-model')
        self.assertEqual(result['status'], 'model_mismatch')
        _, result = self.run_task('no_model', expected_model='fixture-model')
        self.assertEqual(result['status'], 'model_unverified')

    def test_stderr_diagnostic_is_classified_without_raw_output(self):
        tid, result = self.run_task('stderr_deny')
        self.assertEqual(result['status'], 'blocked_permission')
        self.assertIn('permission_client_missing', result['blockers'])
        self.assertNotIn('SECRET_STDERR', (self.store.task(tid) / 'events.jsonl').read_text())

    def test_invalid_empty_failed_and_nonzero_results_fail_closed(self):
        for scenario in ('empty', 'invalid', 'failturn', 'nonzero', 'duplicate'):
            with self.subTest(scenario=scenario):
                _, result = self.run_task(scenario)
                self.assertEqual(result['status'], 'failed')
                self.assertNotIn('secret-raw-invalid-output', json.dumps(result))

    def test_needs_clarification_is_a_distinct_nonzero_outcome(self):
        _, result = self.run_task('clarify')
        self.assertEqual(result['status'], 'needs_clarification')
        self.assertNotEqual(result['exit_code'], 0)

    def test_explicit_resume_and_feedback_are_in_prompt(self):
        backend = FixtureBackend()
        _, result = self.run_task(backend=backend, resume='sess_existing',
                                  test_feedback={'status': 'failed', 'tests': []})
        self.assertEqual(result['sessionId'], 'sess_existing')
        self.assertEqual(backend.request['resume'], 'sess_existing')
        self.assertIn('Controller verification', backend.request['prompt'])

    def test_idle_timeout(self):
        _, result = self.run_task('hang', idle_timeout=.2)
        self.assertEqual(result['status'], 'timed_out')
        self.assertIn('idle_timeout', result['blockers'])

    def test_total_timeout_despite_continuous_activity(self):
        _, result = self.run_task('heartbeat', timeout=2, idle_timeout=1)
        self.assertEqual(result['status'], 'timed_out')
        self.assertIn('total_timeout', result['blockers'])

    def test_owned_child_process_is_stopped_on_timeout(self):
        _, result = self.run_task('child', idle_timeout=1)
        self.assertEqual(result['status'], 'timed_out')
        pid = int((self.cwd / 'child.pid').read_text())
        try:
            state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
            self.assertEqual(state, 'Z')  # killed, awaiting init reaping
        except FileNotFoundError:
            pass

    def test_cancellation_and_live_progress(self):
        tid = self.request('hang')
        holder = []
        thread = threading.Thread(target=lambda: holder.append(bridge.worker(self.store, tid, FixtureBackend(), False)))
        thread.start()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            events = self.store.task(tid) / 'events.jsonl'
            if events.exists() and 'tool.updated' in events.read_text():
                break
            time.sleep(.02)
        self.assertTrue(thread.is_alive())
        answer = bridge.cancel_or_recover(self.store, tid, FixtureBackend())
        self.assertEqual(answer['status'], 'cancel_requested')
        thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(holder[0]['status'], 'cancelled')

    def test_scope_change_compares_existing_dirty_content_and_preserves_it(self):
        (self.cwd / 'baseline.txt').write_text('user dirty original')
        _, result = self.run_task('forbidden', task={'forbidden_files': ['baseline.txt']})
        self.assertEqual(result['status'], 'scope_violation')
        self.assertEqual(result['scope_violations'], ['baseline.txt'])
        self.assertEqual((self.cwd / 'baseline.txt').read_text(), 'new content')

    def test_permitted_edit_is_accepted(self):
        _, result = self.run_task('edit')
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['changed_files'], ['allowed.txt'])

    def test_cwd_lock_prevents_second_writer(self):
        with self.store.lock(str(self.cwd)):
            backend = FixtureBackend()
            _, result = self.run_task(backend=backend)
            self.assertFalse(backend.launched)
            self.assertEqual(result['status'], 'failed')
            self.assertIn('cwd is busy', result['blockers'])

    def test_stale_active_marker_blocks_new_task_until_recovery(self):
        tid = self.request()
        active = self.store.root / 'locks' / (bridge.cwd_key(self.cwd) + '.active.json')
        atomic_json(active, {'task_id': tid})
        _, result = self.run_task()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('cleanup unconfirmed', result['blockers'][0])
        bridge.cancel_or_recover(self.store, tid, FixtureBackend())
        self.assertFalse(active.exists())
        _, result = self.run_task()
        self.assertEqual(result['status'], 'completed')

    def test_cleanup_failure_blocks_new_work_and_recover_clears_it(self):
        tid, result = self.run_task(backend=FixtureBackend(cleanup_ok=False))
        self.assertEqual(result['status'], 'cleanup_failed')
        _, blocked = self.run_task()
        self.assertEqual(blocked['status'], 'failed')
        self.assertIn('cleanup unconfirmed', blocked['blockers'][0])
        bridge.cancel_or_recover(self.store, tid, FixtureBackend())
        _, result = self.run_task()
        self.assertEqual(result['status'], 'completed')

    def test_test_runner_pass_fail_timeout_and_no_tests_are_separate(self):
        for body, expected in [('print(1)', 'passed'), ('raise SystemExit(1)', 'failed'),
                               ('import time; time.sleep(30)', 'failed')]:
            with self.subTest(body=body):
                _, result = self.run_task(run_tests=True, task={'tests': [
                    {'id': 'unit', 'argv': [sys.executable, '-c', body], 'timeout': .3}]})
                self.assertEqual(result['validation_status'], expected)
                self.assertEqual(result['status'], 'completed' if expected == 'passed' else 'validation_failed')

    def test_verify_feedback_binds_session_scope_and_current_source(self):
        tid, _ = self.run_task('edit', task={'tests': [
            {'id': 'unit', 'argv': [sys.executable, '-c', "print('diagnostic'); raise SystemExit(1)"], 'timeout': 2}]})
        verification = bridge.verify(self.store, tid)
        self.assertEqual(verification['status'], 'failed')
        req = bridge.feedback_request(self.store, tid)
        self.assertEqual(req['resume'], 'sess_fixture')
        self.assertEqual(req['contract']['allowed_files'], ['allowed.txt', 'child.pid'])
        self.assertIn('diagnostic', req['test_feedback']['tests'][0]['output_tail'])
        (self.cwd / 'allowed.txt').write_text('external concurrent edit')
        backend = FixtureBackend()
        new_id = self.store.create(req)
        result = bridge.worker(self.store, new_id, backend, False)
        self.assertFalse(backend.launched)
        self.assertEqual(result['status'], 'failed')

    def test_tests_modifying_source_cannot_claim_validation(self):
        _, result = self.run_task(run_tests=True, task={'tests': [
            {'id': 'unit', 'argv': [sys.executable, '-c', "open('allowed.txt','w').write('changed')"], 'timeout': 2}]})
        self.assertEqual(result['validation_status'], 'source_changed')
        self.assertNotEqual(result['status'], 'completed')

    def test_verify_invalid_test_directory_finishes_and_releases_workspace(self):
        tid, _ = self.run_task(task={'tests': [
            {'id': 'unit', 'argv': [sys.executable, '-c', 'pass'],
             'cwd': 'missing', 'timeout': 2}]})
        report = bridge.verify(self.store, tid)
        self.assertEqual(report['status'], 'failed')
        self.assertIn('Test cwd', report['error'])
        self.assertEqual(self.store.status(tid)['status'], 'validation_failed')
        self.assertFalse((self.store.root / 'locks' /
                          (bridge.cwd_key(self.cwd) + '.active.json')).exists())
        _, result = self.run_task()
        self.assertEqual(result['status'], 'completed')

    def test_verify_snapshot_error_does_not_leave_validating_state(self):
        tid, _ = self.run_task(task={'tests': [
            {'id': 'unit', 'argv': [sys.executable, '-c', 'pass'], 'timeout': 2}]})
        before = snapshot(self.cwd, self.store.root)
        with patch.object(bridge, 'snapshot', side_effect=[before, BridgeError('File changed during snapshot')]):
            report = bridge.verify(self.store, tid)
        self.assertEqual(report['status'], 'failed')
        self.assertFalse(report['source_unchanged'])
        self.assertEqual(self.store.status(tid)['status'], 'validation_failed')
        with self.store.lock(self.cwd):
            pass

    def test_test_owner_record_failure_still_terminates_started_process(self):
        import bridge_contract
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                   start_new_session=True)
        def cleanup():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        self.addCleanup(cleanup)
        task = {'tests': [{'id': 'unit', 'argv': [sys.executable], 'timeout': 1}]}
        with patch.object(bridge_contract.subprocess, 'Popen', return_value=process), \
                patch.object(bridge_contract, 'atomic_json', side_effect=PermissionError('owner record unavailable')):
            with self.assertRaises(PermissionError):
                bridge_contract.execute_tests(task, self.cwd, self.root, lambda: False, lambda _: None)
        self.assertIsNotNone(process.poll(), 'Started test survived an ownership-record failure')

    def test_task_already_completed_cannot_be_run_again(self):
        tid, _ = self.run_task()
        with self.assertRaisesRegex(BridgeError, 'already started'):
            bridge.worker(self.store, tid, FixtureBackend(), False)

    def test_status_marks_missing_worker_without_guessing_it_failed(self):
        tid = self.request()
        state = read_json(self.store.task(tid) / 'state.json')
        state.update(status='running', worker_pid=999999999, worker_start='0')
        atomic_json(self.store.task(tid) / 'state.json', state)
        status = self.store.status(tid)
        self.assertTrue(status['worker_missing'])
        self.assertEqual(status['status'], 'running')

    def test_legacy_entrypoint_and_long_prompt_file(self):
        prompt_file = self.root / 'prompt.txt'
        prompt_file.write_text('Long text 中文 ' * 10000)
        with patch.object(bridge, 'WindowsBackend', FixtureBackend), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = bridge.main(['--state-dir', str(self.store.root), '--prompt-file', str(prompt_file), '--cwd', str(self.cwd), '--tool-policy', 'code-local'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['response'], 'done')


class ContractTest(unittest.TestCase):
    def test_transient_record_replace_gap_is_retried_but_missing_file_fails(self):
        with patch.object(Path, 'read_text', side_effect=[FileNotFoundError(), '{"ok": true}']):
            self.assertEqual(read_json('record.json'), {'ok': True})
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError()):
            with self.assertRaises(FileNotFoundError):
                read_json('record.json')
    def test_finite_positive_timeouts(self):
        for value in (0, -1, 'nan', 'inf', '-inf', None, 10 ** 400):
            with self.subTest(value=value), self.assertRaises(BridgeError):
                positive(value)

    def test_path_scope_and_unknown_fields_validation(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'task.json'
            for update in ({'allowed_files': ['../escape']}, {'allowed_files': ['/abs']},
                           {'allowed_files': ['C:\\escape']}, {'typo': True},
                           {'tests': [{'id': 'x', 'argv': 'rm -rf .'}]},
                           {'tests': [{'id': 'x', 'argv': ['true'], 'timeout': 'nan'}]}):
                path.write_text(json.dumps({'version': 1, 'prompt': 'task', 'allowed_files': [], **update}))
                with self.subTest(update=update), self.assertRaises(BridgeError):
                    contract(task_file=path)

    def test_test_cwd_escape_via_symlink_is_rejected(self):
        from bridge_contract import execute_tests
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'outside').symlink_to('/tmp')
            with self.assertRaises(BridgeError):
                execute_tests({'tests': [{'id': 'x', 'argv': ['true'], 'timeout': 1, 'cwd': 'outside'}]}, root, root, lambda: False, lambda _: None)

    def test_symlink_snapshot_does_not_read_target(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'link').symlink_to('/nonexistent/private')
            value = snapshot(root, root / 'state')
            self.assertEqual(value['files']['link']['kind'], 'symlink')

    def test_state_dir_is_excluded_from_snapshot(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'state').mkdir()
            (root / 'state' / 'private').write_text('private')
            self.assertEqual(snapshot(root, root / 'state')['files'], {})

    def test_worktree_under_state_directory_still_has_source_provenance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            work = root / 'state' / 'worktree'
            work.mkdir(parents=True)
            (work / 'code.py').write_text('original')
            before = snapshot(work, root / 'state')
            (work / 'code.py').write_text('changed')
            after = snapshot(work, root / 'state')
            self.assertIn('code.py', before['files'])
            self.assertNotEqual(before['digest'], after['digest'])

    def test_ps_quoting_does_not_interpolate_prompt(self):
        self.assertEqual(ps_quote("a'b$(x)`"), "'a''b$(x)`'")
        self.assertIn('-EncodedCommand', ps_command('exit 0'))


if __name__ == '__main__':
    unittest.main()
