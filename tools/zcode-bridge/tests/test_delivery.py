import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bridge_contract import BridgeError, atomic_json, contract
from bridge_delivery import execution_defaults
import test_bridge as bridge_fixtures
import test_team as team_fixtures
import bridge


class DeliveryTest(unittest.TestCase):
    setUp = bridge_fixtures.BridgeTest.setUp
    request = bridge_fixtures.BridgeTest.request
    run_task = bridge_fixtures.BridgeTest.run_task

    def task(self):
        marker = str(self.root/'checks.log')
        return {'tests':[{'id':'behavior','argv':[sys.executable,'-B','-c',
            "from pathlib import Path; n={}; exec(Path('allowed.txt').read_text(),n); assert n['value']()==42; "
            f"p=Path({marker!r}); p.write_text(p.read_text()+'x' if p.exists() else 'x')"], 'timeout':2}],
            'first_delivery':{'files':['allowed.txt'],'test_ids':['behavior'],'warning_seconds':1,'timeout_seconds':3}}

    def test_real_behavior_required_and_passed_check_is_not_repeated(self):
        _, result=self.run_task('delivery_code',task=self.task(),run_tests=True)
        self.assertEqual(result['status'],'completed',result)
        self.assertEqual(result['first_delivery']['status'],'passed')
        self.assertEqual(result['validation_status'],'passed')
        self.assertEqual((self.root/'checks.log').read_text(),'x')
        self.assertEqual(len(result['tests_executed']),1)

    def test_verified_acknowledgement_does_not_require_another_edit(self):
        tid,_=self.run_task('delivery_code',task=self.task(),run_tests=True)
        followup=bridge.feedback_request(self.store,tid)
        self.assertIsNone(followup['contract']['first_delivery'])
        next_id=self.store.create(followup)
        result=bridge.worker(self.store,next_id,bridge_fixtures.FixtureBackend(),progress=False)
        self.assertEqual(result['status'],'completed',result)

    def test_empty_and_todo_skeleton_do_not_pass_delivery(self):
        for scenario, expected in [('delivery_empty','no_artifact'),('delivery_stub','failed')]:
            with self.subTest(scenario=scenario):
                _,r=self.run_task(scenario,task=self.task())
                self.assertEqual(r['status'],'validation_failed',r)
                self.assertEqual(r['first_delivery']['status'],expected)

    def test_first_delivery_deadline_is_not_renewed_by_todo_activity(self):
        task=self.task();task['first_delivery'].update(warning_seconds=.15,timeout_seconds=.6)
        tid,r=self.run_task('todo_loop',task=task,progress_timeout=None)
        self.assertEqual(r['status'],'timed_out')
        self.assertIn('first_delivery_timeout',r['blockers'])
        self.assertTrue(r['cleanup_confirmed'])
        self.assertIn('first_delivery.warning',(self.store.task(tid)/'events.jsonl').read_text())

    def test_file_changes_alone_do_not_complete_the_stage(self):
        task=self.task();task['first_delivery'].update(warning_seconds=.2,timeout_seconds=.8)
        _,r=self.run_task('tool_progress',task=task,progress_timeout=None)
        self.assertEqual(r['status'],'timed_out')
        self.assertIn('first_delivery_timeout',r['blockers'])
        self.assertIn('allowed.txt',r['changed_files'])
        self.assertNotEqual(r['first_delivery']['status'],'passed')

    def test_checkpoint_test_must_not_change_source(self):
        task=self.task()
        task['tests'][0]['argv']=[sys.executable,'-c',"from pathlib import Path; Path('allowed.txt').write_text('changed')"]
        _,r=self.run_task('delivery_code',task=task)
        self.assertEqual(r['status'],'validation_failed')
        self.assertEqual(r['first_delivery']['status'],'source_changed')

    def test_defaults_and_invalid_checkpoint_are_explicit(self):
        task={'version':1,'prompt':'implement a slice','allowed_files':['a.py'],
              'tests':[{'id':'behavior','argv':['python3','test.py'],'timeout':2}]}
        defaults=execution_defaults(task)
        self.assertEqual(defaults['reasoning_effort'],'high')
        self.assertEqual(defaults['first_delivery']['test_ids'],['behavior'])
        self.assertNotIn('first_delivery',task)
        self.assertIsNone(execution_defaults({**task,'first_delivery':None})['first_delivery'])
        file=self.root/'bad.json'
        atomic_json(file,{**task,'first_delivery':{'test_ids':['unknown']}})
        with self.assertRaises(BridgeError):contract(task_file=file)

    def test_reasoning_selection_rejects_unsupported_or_ignored_settings(self):
        script=r'''
const assert=require('node:assert/strict');
const {configureReasoning}=require(process.argv[1]);
async function test(){
 const snap=current=>({session:{sessionId:'s'},settings:{thoughtLevel:{current,available:[{value:'low'},{value:'high'}]}}});
 let calls=[]; const events=[];
 const rpc=async(method,p)=>{calls.push(method);if(method==='session/setThoughtLevel')assert.equal(p.persistAsWorkspaceLastUsed,false);return snap('low');};
 await configureReasoning(rpc,snap('high'),'low',e=>events.push(e));
 assert.deepEqual(calls,['session/setThoughtLevel','session/read']);
 assert.equal(events.at(-1).payload.effective,'low');
 calls=[];await assert.rejects(configureReasoning(rpc,snap('high'),'max',()=>{}));assert.equal(calls.length,0);
 await assert.rejects(configureReasoning(async()=>snap('high'),snap('high'),'low',()=>{}));
}
test().catch(e=>{console.error(e);process.exitCode=1});
'''
        p=subprocess.run(['node','-e',script,str(Path(__file__).resolve().parents[1]/'reasoning.cjs')],capture_output=True,text=True,timeout=10)
        self.assertEqual(p.returncode,0,p.stderr)

    def test_protocol_does_not_dispatch_when_effort_readback_mismatches(self):
        root=Path(__file__).resolve().parents[1]
        cwd=self.root/'effort-ignored';cwd.mkdir()
        launch=self.root/'launch.json';marker=self.root/'sent.marker'
        atomic_json(launch,{'version':1,'token':'fixture','cli':str(root/'tests/fake_protocol.cjs'),
            'argv':[],'ownerFile':str(self.root/'owner.json'),
            'development':{'cwd':str(cwd),'mode':'edit','prompt':'test','reasoningEffort':'low'}})
        result=subprocess.run(['node',str(root/'launcher.cjs'),str(launch)],
            capture_output=True,text=True,timeout=20,env={**os.environ,'BRIDGE_FIXTURE_SEND_MARKER':str(marker)})
        self.assertNotEqual(result.returncode,0)
        self.assertIn('reasoning_mismatch',result.stdout)
        self.assertFalse(marker.exists(),'Model prompt was sent despite failed configuration verification')


class RecoveryTest(unittest.TestCase):
    setUp=team_fixtures.TeamTest.setUp
    cleanup=team_fixtures.TeamTest.cleanup
    task=team_fixtures.TeamTest.task
    start=team_fixtures.TeamTest.start

    def fail_zero(self, bridge_task):
        self.executor.results[bridge_task]={'status':'timed_out','cleanup_confirmed':True,
            'changed_files':[],'blockers':['first_delivery_timeout'],'observed_model':'GLM-5.3-Flash',
            'sessionId':'stuck-session','usage':{'totalTokens':100}}

    def test_one_automatic_recovery_is_fresh_and_replaces_large_prompt(self):
        job=self.task('a');job['contract'].update(prompt='Original large multi-stage requirement',
            recovery_prompt='Write just a.txt with the required content',recovery_context='Base file already inspected')
        self.executor.auto=False
        self.start(tasks=[job]);s=self.coordinator.tick(self.rid)
        old=s['tasks']['a']['bridge_task'];self.fail_zero(old)
        s=self.coordinator.tick(self.rid);new=s['tasks']['a']['bridge_task']
        self.assertNotEqual(old,new)
        req=self.executor.requests[new]
        self.assertIsNone(req['resume'])
        self.assertNotIn('Original large',req['contract']['prompt'])
        self.assertIn('Base file already inspected',req['contract']['prompt'])
        self.fail_zero(new);s=self.coordinator.tick(self.rid)
        self.assertEqual(s['tasks']['a']['state'],'failed')
        self.assertEqual(len(self.executor.launches),2)
        with self.assertRaisesRegex(BridgeError,'Second zero-output'):
            self.coordinator.decide(self.rid,s['revision'],{'action':'retry','task_id':'a',
                'summary':'again','recovery_prompt':'Even smaller'},background=False)

    def test_no_invented_recovery_when_smaller_goal_missing(self):
        self.executor.auto=False;self.start();s=self.coordinator.tick(self.rid)
        self.fail_zero(s['tasks']['a']['bridge_task']);s=self.coordinator.tick(self.rid)
        self.assertEqual(s['tasks']['a']['state'],'failed')
        self.assertEqual(len(self.executor.launches),1)
        with self.assertRaisesRegex(BridgeError,'smaller recovery_prompt'):
            self.coordinator.decide(self.rid,s['revision'],{'action':'retry','task_id':'a','summary':'again'},background=False)

    def test_existing_implementation_keeps_session_even_if_repair_makes_no_new_edits(self):
        self.executor.auto=False;self.start();s=self.coordinator.tick(self.rid)
        tid=s['tasks']['a']['bridge_task']
        Path(s['tasks']['a']['worktree'],'a.txt').write_text('partial code')
        self.executor.results[tid]={'status':'validation_failed','cleanup_confirmed':True,
            'changed_files':['a.txt'],'observed_model':'GLM-5.3-Flash','sessionId':'code-session','usage':{'totalTokens':1}}
        s=self.coordinator.tick(self.rid)
        self.coordinator.decide(self.rid,s['revision'],{'action':'retry','task_id':'a','summary':'Fix the concrete failing check'},background=False)
        s=self.coordinator.tick(self.rid);second=s['tasks']['a']['bridge_task']
        self.assertEqual(self.executor.requests[second]['resume'],'code-session')
        self.fail_zero(second);self.executor.results[second]['sessionId']='code-session'
        s=self.coordinator.tick(self.rid)
        self.coordinator.decide(self.rid,s['revision'],{'action':'retry','task_id':'a','summary':'Apply a precise correction to existing code'},background=False)
        s=self.coordinator.tick(self.rid);third=s['tasks']['a']['bridge_task']
        self.assertEqual(self.executor.requests[third]['resume'],'code-session')
        self.assertEqual(s['tasks']['a'].get('zero_output_retries',0),0)


if __name__=='__main__':unittest.main()
