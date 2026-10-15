import json
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from team import WorkCoordinator


class SubagentTest(unittest.TestCase):
    def test_native_port_policy(self):
        p = subprocess.run(['node', str(Path(__file__).with_name('subagent_policy_test.cjs'))],
                           capture_output=True, text=True, timeout=15)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('tests passed', p.stdout)

    def test_incomplete_child_usage_stays_incomplete_with_known_parent_tokens(self):
        result = bridge.terminal_result({'type':'result','sessionId':'s','response':'done',
            'usage':{'totalTokens':12}, 'usageComplete':False,
            'subagents':{'calls':1,'completed':0,'failed':1,'usage':{},'usage_complete':False}})
        self.assertFalse(result['usage_complete'])
        state = {'executor_tokens':0,'usage_records':{},'usage_history_complete':True}
        WorkCoordinator._account_result(None, state, 'task', result)
        WorkCoordinator._account_result(None, state, 'task', result)
        self.assertEqual(state['executor_tokens'],12)
        self.assertEqual(state['unknown_execution_count'],1)
        self.assertFalse(state['executor_usage_complete'])

    def test_safe_subagent_event_does_not_include_prompt_or_output(self):
        event = bridge.safe_event({'type':'subagent.completed','sessionId':'s','payload':{
            'callId':'call-1','childSessionId':'child-1','prompt':'PRIVATE','response':'PRIVATE',
            'usage':{'totalTokens':10,'private':'PRIVATE'},'usageComplete':True}})
        self.assertNotIn('PRIVATE',json.dumps(event))
        self.assertEqual(event['usage']['totalTokens'],10)


if __name__ == '__main__':
    unittest.main()
