from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_contract import BridgeError
from bridge_progress import ProgressTracker, progress_probe
from bridge import safe_event


class OutputProgressTest(unittest.TestCase):
    def tracker(self):
        clock = patch('bridge_progress.time.monotonic', return_value=0.0)
        clock.start()
        self.addCleanup(clock.stop)
        self.digest = 'a'
        return ProgressTracker(0, 1, 3, lambda: {'digest': self.digest}, 'a')

    def finish_tool(self, tracker, tool, at, command=None):
        tracker.observe({'type':'tool.updated','phase':'started','tool_call_id':'call','tool':tool}, at, str(at))
        event = {'type':'tool.updated','phase':'result','tool_call_id':'call','success':True}
        if command:
            event['command'] = command
        tracker.observe(event, at, str(at))

    def test_new_bytes_count_but_rewriting_and_reverting_do_not(self):
        t = self.tracker()
        self.finish_tool(t, 'Write', 1)
        t.refresh(1, '1')
        self.assertEqual(t.last_output, 0)
        self.digest = 'b'
        self.finish_tool(t, 'Bash', 2)
        t.refresh(2, '2')
        self.assertEqual(t.last_output, 2)
        self.digest = 'a'
        self.finish_tool(t, 'Write', 3)
        t.refresh(3, '3')
        self.assertEqual(t.last_output, 2)
        self.assertEqual(t.status(3)['artifact_changes'], 1)

    def test_failing_and_passing_checks_count_once_per_source_and_exit(self):
        t = self.tracker()
        check = {'category':'test','id':'a'*64,'exit_code':1,'status':'failed'}
        for at in [1, 2]:
            self.finish_tool(t, 'Bash', at, check)
            t.refresh(at, str(at))
        self.assertEqual(t.last_output, 1)
        check.update(exit_code=0,status='completed')
        self.finish_tool(t, 'Bash', 3, check)
        t.refresh(3, '3')
        self.assertEqual(t.last_output, 3)
        self.digest = 'b'
        self.finish_tool(t, 'Bash', 4, check)
        t.refresh(4, '4')
        self.assertEqual(t.data['distinct_checks'], 3)

    def test_activity_phase_and_payload_redaction(self):
        t = self.tracker()
        self.finish_tool(t,'TodoWrite',1)
        t.observe(safe_event({'type':'transport.heartbeat','payload':{
            'phase':'tool_input','bytes':200,'delta':'PRIVATE'}}),2,'2')
        self.assertEqual(t.status(3)['phase'], 'tool_input')
        self.assertEqual(t.status(8)['phase'], 'waiting_model')
        self.assertEqual(t.status(3)['seconds_without_output'],3)
        t.observe({'type':'tool.updated','phase':'started','tool':'Bash','tool_call_id':'b'},3,'3')
        self.assertEqual(t.status(3)['phase'], 'tool_running')
        self.assertNotIn('PRIVATE', str(t.status(3)))

    def test_racing_probe_does_not_reset_or_crash(self):
        t = self.tracker()
        def fail():
            raise BridgeError('File changed during snapshot')
        t.probe = fail
        self.finish_tool(t,'Write',1)
        t.refresh(1,'1')
        self.assertEqual(t.last_output,0)
        self.assertEqual(t.data['probe_failures'],1)

    def test_scope_and_same_size_content_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); work = root/'work'; work.mkdir()
            (work/'code').write_text('aaaa')
            task = {'allowed_files':['code'], 'forbidden_files':['private']}
            initial = progress_probe(work,root/'state',task)
            (work/'private').write_text('irrelevant')
            self.assertEqual(progress_probe(work,root/'state',task)['digest'],initial['digest'])
            (work/'code').write_text('bbbb')
            self.assertNotEqual(progress_probe(work,root/'state',task)['digest'],initial['digest'])

    def test_command_metadata_recognition_is_conservative(self):
        script = r'''
const assert = require('node:assert/strict');
const {identify,outcome} = require(process.argv[1]);
for(const command of ['python -m unittest -v','pytest tests','node --test x.cjs','npm test','cargo build']) assert.ok(identify(command));
for(const command of ['echo npm test','python -m unittest | tail -20','npm test; true','cd x && npm test','ls','npm install','node -e "test"']) assert.equal(identify(command),null);
assert.equal(identify('python  -m unittest').id,identify('python -m unittest').id);
const result = {perf:{detail:{command:{exitCode:1,status:'failed'}}}};
assert.equal(outcome(result,identify('python -m unittest')).exit_code,1);
assert.equal(outcome({success:true},identify('python -m unittest')),undefined);
result.perf.detail.command.timedOut = true;
assert.equal(outcome(result,identify('python -m unittest')),undefined);
'''
        p = subprocess.run(['node','-e',script,str(Path(__file__).resolve().parents[1]/'command-evidence.cjs')],
                           capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)


if __name__ == '__main__':
    unittest.main()
