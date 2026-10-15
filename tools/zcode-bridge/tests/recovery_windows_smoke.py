"""Real Windows worker/coordinator recovery, using a local CLI fixture only."""
import json
import os
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from bridge_contract import atomic_json, read_json
from team import WorkCoordinator
from team_workspace import git


def main():
    output=Path(sys.argv[1]).resolve();output.mkdir(parents=True,exist_ok=False)
    repo=output/'repo';repo.mkdir();git(repo,'init','-q')
    (repo/'base.txt').write_text('unchanged\n');git(repo,'add','.');git(repo,'commit','-qm','base')
    os.environ['ZCODE_BRIDGE_CLI']=str(Path(__file__).with_name('fake_cli.cjs').resolve())
    c=WorkCoordinator(output/'state')
    task={'version':1,'prompt':'TEAM_NO_OUTPUT full multi-stage fixture',
          'recovery_prompt':'TEAM_FIXTURE:a.txt','recovery_context':'Only a.txt is required for this checkpoint',
          'allowed_files':['a.txt'],'tool_policy':'code-local','allow_subagents':False,
          'first_delivery':{'files':['a.txt'],'test_ids':['content'],'warning_seconds':2,'timeout_seconds':10},
          'tests':[{'id':'content','argv':[sys.executable,'-c',"from pathlib import Path; assert Path('a.txt').read_text()=='BRIDGE_TEAM_OK\\n'"],'timeout':5}]}
    state=c.start({'version':1,'repo':str(repo),'expected_model':'fixture-model','max_repairs':1,
                   'deadline_seconds':120,'task_timeout':40,'tasks':[{'id':'slice','contract':task}]})
    rid=state['run_id'];deadline=time.monotonic()+120
    try:
        while time.monotonic()<deadline:
            state=c.observe(rid);t=state['tasks']['slice']
            if t['state'] in ('failed','needs_changes','integration_failed'):
                raise AssertionError(t)
            if t['state']=='awaiting_review':
                c.decide(rid,state['revision'],{'action':'approve','task_id':'slice','candidate_commit':t['candidate'],
                    'reviewer':'deterministic-smoke','summary':'Exact fixture bytes and declared behavior check passed'})
            if state['status']=='completed':
                full=read_json(c.directory(rid)/'state.json');job=full['tasks']['slice']
                assert job['attempt']==2 and job['zero_output_retries']==1,job
                req=read_json(c.executor.store.task(job['bridge_task'])/'request.json')
                assert req['resume'] is None and 'TEAM_NO_OUTPUT' not in req['contract']['prompt'],req
                assert job['result']['first_delivery']['status']=='passed',job
                summary={'run_id':rid,'status':'completed','attempts':2,'fresh_session':True,
                         'first_delivery':'passed','provider_calls':0,'original_workspace_unchanged':not (repo/'a.txt').exists()}
                atomic_json(output/'summary.json',summary);print(json.dumps(summary));return
            time.sleep(.2)
        raise AssertionError('Recovery pipeline timed out')
    finally:
        if c.observe(rid)['status']!='completed':c.cancel(rid)


if __name__=='__main__':main()
