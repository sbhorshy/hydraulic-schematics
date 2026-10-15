import fnmatch
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bridge
from bridge_contract import PathMatcher, atomic_json, snapshot
from bridge_progress import ProgressTracker
from bridge_probe import ProbeProcess, recover_probe
from test_bridge import FixtureBackend


class ProbeRegressionTest(unittest.TestCase):
    def test_literal_and_glob_rules_keep_fnmatchcase_semantics(self):
        patterns=['exact.py','src/**/*.py','src/[ab]?.txt','!literal','中文/*','[unclosed']
        matcher=PathMatcher(patterns)
        for name in ['exact.py','EXACT.py','src/x/a.py','src/a.py','src/a1.txt','src/c1.txt','!literal','中文/目录/x','[unclosed','other']:
            self.assertEqual(matcher.matches(name),any(fnmatch.fnmatchcase(name,p) for p in patterns))

    def test_large_literal_scope_has_bounded_pattern_compilation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); work = root/'work'; work.mkdir()
            names = [f'file-{i:04d}.txt' for i in range(499)]
            for name in names[:3]: (work/name).write_text(name)
            fnmatch._compile_pattern.cache_clear()
            with patch('fnmatch.translate', wraps=fnmatch.translate) as compile_pattern:
                actual = snapshot(work,root/'state',patterns=names,forbidden=['private/**'])
            self.assertEqual(set(actual['files']),set(names[:3]))
            self.assertLessEqual(compile_pattern.call_count,len(names)+1,
                                 'Large literal scopes must not thrash the pattern cache')

    def test_cooldown_starts_after_a_slow_probe_finishes(self):
        clock = [0.0]; calls = []
        def probe():
            calls.append(clock[0]); clock[0] += 9.5
            return {'digest':'same'}
        t = ProgressTracker(0,120,900,probe,'same')
        t.observe({'type':'tool.updated','phase':'started','tool':'Bash','tool_call_id':'b'},0,'0')
        with patch('bridge_progress.time.monotonic',side_effect=lambda:clock[0]):
            clock[0]=5; t.refresh(clock[0],'first')
            clock[0]+=.1; t.refresh(clock[0],'next')
        self.assertEqual(len(calls),1,'Slow probe must not run again immediately')

    def test_events_during_probe_are_not_lost_and_probes_never_overlap(self):
        class Runner:
            starts = 0
            ready = None
            def start(self): self.starts += 1
            def poll(self): return self.ready
        runner = Runner()
        t = ProgressTracker(0,1,5,runner,'before')
        t.observe({'type':'tool.updated','phase':'started','tool':'Write','tool_call_id':'one'},0,'0')
        t.refresh(1,'1')
        t.observe({'type':'tool.updated','phase':'result','success':True,'tool_call_id':'one'},1.2,'1.2')
        t.refresh(1.3,'1.3')
        self.assertEqual(runner.starts,1)
        runner.ready = {'result':{'digest':'after'},'elapsed':.5}
        t.refresh(1.5,'1.5')
        self.assertTrue(t.dirty, 'A write completed while scanning; another scan is needed')
        self.assertEqual(t.last_output,1.5)
        t.refresh(2,'2')
        self.assertEqual(runner.starts,1)
        runner.ready = None
        t.refresh(3.6,'3.6')
        self.assertEqual(runner.starts,2)

    def worker_with_slow_probe(self, cancel=False):
        with tempfile.TemporaryDirectory(prefix='probe-regression-') as temp:
            root=Path(temp);work=root/'work';work.mkdir();store=bridge.Store(root/'state')
            script=root/'producer.py'
            script.write_text('''import json,time,sys
from pathlib import Path
def out(kind,**kw):print(json.dumps(dict(type=kind,sessionId='s',**kw)),flush=True)
out('tool.updated',payload=dict(kind='started',toolName='Bash',toolCallId='b'))
time.sleep(.15)
if sys.argv[2]=='cancel':time.sleep(30)
for i in range(30):out('transport.heartbeat',payload=dict(phase='model_streaming',bytes=1))
out('tool.updated',payload=dict(kind='result',toolCallId='b',result=dict(success=True)))
out('result',response='already finished',usage=dict(totalTokens=0),projection=dict(status='idle'))
Path(sys.argv[1]).write_text('done')
''')
            class Backend(FixtureBackend):
                def launch(self, request, directory):
                    atomic_json(directory/'transport.json',{'fixture':True})
                    return subprocess.Popen([sys.executable,str(script),str(root/'finished'),'cancel' if cancel else 'complete'],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
            tid=store.create({'cwd':str(work),'mode':'edit','timeout':5,'idle_timeout':3,
                'progress_warning':.05,'progress_timeout':2 if cancel else .6,
                'contract':{'version':1,'prompt':'fixture','allowed_files':[],'tests':[]}})
            cancel_errors=[]
            def cancel_when_probe_starts():
                until=time.monotonic()+2
                while time.monotonic()<until:
                    if (store.task(tid)/'active-probe.json').exists():
                        (store.task(tid)/'cancel.request').touch();return
                    time.sleep(.01)
                cancel_errors.append('No probe started')
            thread = threading.Thread(target=cancel_when_probe_starts) if cancel else None
            if thread:thread.start()
            with patch.object(ProbeProcess,'command',return_value=[sys.executable,'-c','import time; time.sleep(30)']):
                began=time.monotonic();result=bridge.worker(store,tid,Backend(),progress=False);elapsed=time.monotonic()-began
            if thread:thread.join(timeout=3)
            self.assertFalse(cancel_errors)
            self.assertTrue(result['cleanup_confirmed'],result)
            self.assertFalse((store.task(tid)/'active-probe.json').exists())
            self.assertLess(elapsed,2, 'A 30-second scan must not delay completion or cancellation')
            self.assertGreaterEqual(result['progress']['probe_abandoned'],1)
            if not cancel:self.assertTrue((root/'finished').exists())
            return result

    def test_completed_executor_is_not_timed_out_behind_a_slow_probe(self):
        self.assertEqual(self.worker_with_slow_probe()['status'],'completed')

    def test_cancel_does_not_wait_for_a_slow_probe(self):
        self.assertEqual(self.worker_with_slow_probe(cancel=True)['status'],'cancelled')

    def test_orphan_probe_is_recoverable_and_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);work=root/'work';work.mkdir()
            probe=ProbeProcess(root,work,root/'state',{'allowed_files':[]},timeout=.05)
            with patch.object(probe,'command',return_value=[sys.executable,'-c','import time;time.sleep(30)']):
                probe.start()
                self.assertTrue(recover_probe(root))
                self.assertTrue(probe.close())
                probe.start();time.sleep(.07)
                result=probe.poll()
                self.assertEqual(result['error'],'timeout')
                self.assertFalse(probe.owner.exists())


if __name__ == '__main__':
    unittest.main()
