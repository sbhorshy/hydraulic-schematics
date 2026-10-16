"""Pre-push hook ships with the repo, and CI runs the same library check (#92)."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from ruamel.yaml import YAML

from repository_context import REPO

HOOK = REPO / '.githooks' / 'pre-push'
WORKFLOW = REPO / '.github' / 'workflows' / 'library-check.yml'
CHECK = '.agents/skills/hydraulic-schematic/scripts/check_library.py'


def run_hook(check_exit, path=None):
    """Run the shipped hook inside a throwaway repo whose check_library exits as told."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp, 'repo')
        script = repo / CHECK
        script.parent.mkdir(parents=True)
        script.write_text('import sys\nsys.exit(%d)\n' % check_exit)
        subprocess.run(['git', 'init', '-q', str(repo)], check=True)
        env = dict(os.environ)
        if path is not None:
            env['PATH'] = path
        return subprocess.run(['/bin/sh', str(HOOK)], cwd=repo, env=env,
                              capture_output=True, text=True)


class HookTests(unittest.TestCase):
    def test_hook_is_shipped_and_executable(self):
        self.assertTrue(HOOK.is_file())
        self.assertTrue(os.stat(HOOK).st_mode & 0o111, 'pre-push 必须带执行位')

    def test_passing_library_check_allows_push(self):
        self.assertEqual(run_hook(0).returncode, 0)

    def test_failing_library_check_blocks_push_and_explains(self):
        result = run_hook(1)
        self.assertEqual(result.returncode, 1)
        self.assertIn('[pre-push]', result.stderr)
        self.assertIn('--no-verify', result.stderr)

    def test_missing_python_blocks_push_instead_of_passing_silently(self):
        with tempfile.TemporaryDirectory() as bindir:
            os.symlink(shutil.which('git'), os.path.join(bindir, 'git'))
            result = run_hook(0, path=bindir)
        self.assertEqual(result.returncode, 1)
        self.assertIn('python', result.stderr.lower())


class CiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = YAML(typ='safe').load(WORKFLOW.read_text(encoding='utf-8'))

    def test_runs_on_push_and_pull_request(self):
        triggers = self.doc['on']
        self.assertIn('push', triggers)
        self.assertIn('pull_request', triggers)

    def test_a_step_runs_the_library_check(self):
        steps = [s for job in self.doc['jobs'].values() for s in job['steps']]
        self.assertTrue(any(CHECK in s.get('run', '') for s in steps),
                        'CI 必须运行 check_library.py')

    def test_ci_does_not_run_the_known_red_full_symbol_scan(self):
        text = WORKFLOW.read_text(encoding='utf-8')
        self.assertNotIn('check_symbol', text)


class DocsTests(unittest.TestCase):
    def setUp(self):
        self.readme = (REPO / '.githooks' / 'README.md').read_text(encoding='utf-8')

    def test_install_command_is_documented(self):
        self.assertIn('git config core.hooksPath .githooks', self.readme)

    def test_exclusion_of_full_symbol_scan_is_explained(self):
        self.assertIn('check_symbol', self.readme)
        self.assertIn('#31', self.readme)


if __name__ == '__main__':
    unittest.main()
