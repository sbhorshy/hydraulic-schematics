import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_contract import snapshot
from bridge_transport import cli_arguments
import test_bridge as bridge_fixtures


class ProgressTest(unittest.TestCase):
    setUp = bridge_fixtures.BridgeTest.setUp
    request = bridge_fixtures.BridgeTest.request
    run_task = bridge_fixtures.BridgeTest.run_task
    def test_progress_warning_and_deadline_ignore_stream_heartbeats(self):
        _, result = self.run_task('heartbeat', timeout=4, idle_timeout=2,
                                  progress_warning=.15, progress_timeout=.6)
        self.assertEqual(result['status'], 'timed_out')
        self.assertIn('no_progress_timeout', result['blockers'])
        self.assertGreater(result['counters']['events_received'], 2)
        self.assertTrue(result['cleanup_confirmed'])

    def test_warning_only_does_not_kill_slow_success(self):
        tid, result = self.run_task('delay', progress_warning=.15)
        self.assertEqual(result['status'], 'completed')
        events = (self.store.task(tid) / 'events.jsonl').read_text()
        self.assertIn('progress.warning', events)

    def test_actual_artifacts_reset_deadline_but_errors_do_not(self):
        # Allow helper process startup while requiring multiple renewals across
        # a 2.4s writer; a task with no observed output still cannot finish.
        _, result = self.run_task('tool_progress', progress_warning=.2, progress_timeout=1.25)
        self.assertEqual(result['status'], 'completed')
        self.assertGreaterEqual(result['progress']['artifact_changes'], 2)
        tid, result = self.run_task('error_loop', progress_warning=.15, progress_timeout=.5)
        self.assertIn('no_progress_timeout', result['blockers'])
        events = (self.store.task(tid) / 'events.jsonl').read_text()
        self.assertIn('not_found', events)
        self.assertNotIn('PRIVATE_PATH_SECRET', events)
        self.assertFalse(result['usage_complete'])

    def test_todo_reads_noop_writes_and_shell_activity_cannot_extend_output_deadline(self):
        (self.cwd / 'allowed.txt').write_text('unchanged')
        for scenario in ('todo_loop', 'read_loop', 'noop_write_loop', 'shell_loop'):
            with self.subTest(scenario=scenario):
                _, result = self.run_task(scenario, progress_warning=.15, progress_timeout=.5)
                self.assertEqual(result['status'], 'timed_out')
                self.assertIn('no_progress_timeout', result['blockers'])
                self.assertEqual(result['progress']['artifact_changes'], 0)
                self.assertLess(result['progress']['seconds_without_tool_completion'], .2)
                self.assertGreaterEqual(result['progress']['seconds_without_output'], .5)
                self.assertTrue(result['cleanup_confirmed'])

    def test_repeated_failing_test_is_evidence_once_not_per_tool_call(self):
        _, result = self.run_task('repeated_test_loop', progress_warning=.15, progress_timeout=1.25)
        self.assertEqual(result['status'], 'timed_out')
        self.assertEqual(result['progress']['distinct_checks'], 1)
        self.assertEqual(result['progress']['last_check_exit_code'], 1)
        self.assertGreater(result['progress']['command_completions'], 2)

    def test_local_policy_reaches_cli_without_disabling_file_tools(self):
        request = {'mode': 'edit', 'prompt': 'literal $(x)', 'contract': {}}
        argv = cli_arguments(request, 'C:\\workspace')
        disabled = argv[argv.index('--disallowed-tools') + 1].split(',')
        self.assertTrue({'Bash', 'WebFetch', 'WebSearch', 'Agent', 'Task'} <= set(disabled))
        self.assertFalse({'Read', 'Edit', 'Write'} & set(disabled))
        argv = cli_arguments({**request, 'tool_policy': 'cli-default'}, 'C:\\workspace')
        self.assertNotIn('--disallowed-tools', argv)


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / 'work'
        self.work.mkdir()
        self.state = self.root / 'state'

    def test_full_hash_detects_same_size_edit_with_restored_mtime(self):
        file = self.work / 'file'
        file.write_text('aaaa')
        info = file.stat()
        before = snapshot(self.work, self.state)
        file.write_text('bbbb')
        os.utime(file, ns=(info.st_atime_ns, info.st_mtime_ns))
        after = snapshot(self.work, self.state)
        self.assertNotEqual(before['digest'], after['digest'])
        self.assertEqual(after['files']['file']['sha256'], hashlib.sha256(b'bbbb').hexdigest())

    def test_git_tracked_directory_replaced_by_symlink_does_not_follow_target(self):
        subprocess.run(['git', 'init', '-q', str(self.work)], check=True)
        (self.work / 'nested').mkdir()
        (self.work / 'nested' / 'file').write_text('original')
        subprocess.run(['git', '-C', str(self.work), 'add', '.'], check=True)
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'file').write_text('DO_NOT_READ')
        (self.work / 'nested' / 'file').unlink()
        (self.work / 'nested').rmdir()
        (self.work / 'nested').symlink_to(outside)
        value = snapshot(self.work, self.state)
        self.assertNotIn('nested/file', value['files'])
        self.assertEqual(value['files']['nested']['kind'], 'symlink')

    def test_mixed_files_links_modes_and_deletions(self):
        subprocess.run(['git', 'init', '-q', str(self.work)], check=True)
        for i in range(80):
            folder = self.work / ('folder-' + str(i % 4))
            folder.mkdir(exist_ok=True)
            (folder / f'file-{i}').write_text(str(i))
        executable = self.work / 'executable'
        executable.write_text('run')
        executable.chmod(0o755)
        (self.work / 'link').symlink_to('missing')
        (self.work / '.gitignore').write_text('ignored\n')
        (self.work / 'ignored').write_text('not covered')
        subprocess.run(['git', '-C', str(self.work), 'add', '.'], check=True)
        (self.work / 'folder-0' / 'file-0').unlink()
        value = snapshot(self.work, self.state)
        self.assertEqual(len(value['files']), 82)
        self.assertNotIn('ignored', value['files'])
        self.assertNotIn('folder-0/file-0', value['files'])
        self.assertTrue(value['files']['executable']['executable'])
        self.assertEqual(value['files']['link']['sha256'], hashlib.sha256(b'missing').hexdigest())


if __name__ == '__main__':
    unittest.main()
