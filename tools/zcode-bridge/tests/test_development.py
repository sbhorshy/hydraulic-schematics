import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from bridge_contract import contract, atomic_json

ROOT = Path(__file__).resolve().parents[1]


class DevelopmentTest(unittest.TestCase):
    def test_task_scoped_protocol_permissions_resume_and_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for resume in (None, 'sess_resumed_fixture'):
                launch = root / 'launch.json'
                atomic_json(launch, {'version': 1, 'token': 'fixture', 'cli': str(ROOT / 'tests/fake_protocol.cjs'),
                    'argv': [], 'ownerFile': str(root / ('owner-' + str(resume))),
                    'development': {'cwd': str(root), 'mode': 'edit', 'resume': resume, 'prompt': 'test'}})
                p = subprocess.run(['node', str(ROOT / 'launcher.cjs'), str(launch)],
                                   capture_output=True, text=True, timeout=20)
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertNotIn('PRIVATE_PROTOCOL_SENTINEL', p.stdout)
                self.assertNotIn('private-test-name', p.stdout)
                rows = [json.loads(line) for line in p.stdout.splitlines()]
                terminal = [r for r in rows if r['type'] == 'result']
                self.assertEqual(len(terminal), 1)
                self.assertEqual(terminal[0]['sessionId'], resume or 'sess_protocol_fixture')
                decisions = [r['payload']['decision'] for r in rows if r['type'] == 'permission.resolved']
                self.assertEqual(decisions.count('allow'), 3)
                self.assertEqual(decisions.count('deny'), 5)
                evidence = [r['payload']['command'] for r in rows if r['type'] == 'tool.updated' and r['payload'].get('command')]
                self.assertEqual(evidence[0]['category'], 'test')
                self.assertEqual(evidence[0]['exit_code'], 1)

    def test_plan_permission_client_never_grants_execution(self):
        p = subprocess.run(['node', '-e', "const p=require(process.argv[1]); "
            "if(p.permissionDecision({sessionId:'s',toolName:'Bash',riskLevel:'low'},'s','plan').decision!=='deny')process.exit(1)",
            str(ROOT / 'protocol.cjs')], capture_output=True, timeout=10)
        self.assertEqual(p.returncode, 0)

    def test_development_contract_and_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / 'task.json'
            atomic_json(file, {'version': 1, 'prompt': 'fix', 'allowed_files': ['x'],
                              'tool_policy': 'development', 'requires_shell': True, 'tests': []})
            task = contract(task_file=file)
            prompt = bridge.prompt_for({'contract': task})
            self.assertIn('You may use Bash', prompt)
            self.assertIn('not in an OS sandbox', prompt)
            self.assertNotIn('Bash, WebFetch, WebSearch, Agent and Task are disabled', prompt)


if __name__ == '__main__':
    unittest.main()
