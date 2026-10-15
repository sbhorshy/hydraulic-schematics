"""Public team pipeline on real Windows processes; --live uses one actual model task."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge_contract import BridgeError, atomic_json
from team import WorkCoordinator
from team_workspace import git, head


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('output')
    p.add_argument('--live', action='store_true')
    args = p.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    repo = output / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    (repo / 'base.txt').write_text('unchanged baseline\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'smoke baseline')
    base = head(repo)
    (repo / 'user-uncommitted.txt').write_text('preserve this\n')
    if not args.live:
        os.environ['ZCODE_BRIDGE_CLI'] = str(Path(__file__).with_name('fake_cli.cjs').resolve())
    c = WorkCoordinator(output / 'state')
    jobs = []
    for tid in (['a'] if args.live else ['a', 'b']):
        filename = tid + '.txt'
        prompt = ('最小集成测试：仅用 Write 在当前目录创建 ' + filename +
                  '，精确内容 BRIDGE_TEAM_OK 和一个换行。不要读其他目录、不写记忆、不用 Bash 或子代理。控制端测试。') if args.live else 'TEAM_FIXTURE:' + filename
        jobs.append({'id': tid, 'contract': {'version': 1, 'prompt': prompt, 'allowed_files': [filename],
                       'tool_policy': 'development' if args.live else 'code-local', 'allow_subagents': False,
                       'tests': [{'id': 'content', 'argv': [sys.executable, '-c',
                           f"from pathlib import Path; assert Path('{filename}').read_text() == 'BRIDGE_TEAM_OK\\n'"], 'timeout': 10}]}})
    plan = {'version': 1, 'repo': str(repo), 'tasks': jobs, 'expected_model': 'GLM-5.3-Flash' if args.live else 'fixture-model',
            'max_writers': 1 if args.live else 2, 'experimental_parallel': not args.live,
            'deadline_seconds': 240, 'task_timeout': 150, 'idle_timeout': 90,
            'integration_tests': [{'id': 'integrated-content', 'argv': [sys.executable, '-c',
                "from pathlib import Path; assert Path('base.txt').read_text() == 'unchanged baseline\\n'; "
                "assert all(p.read_text() == 'BRIDGE_TEAM_OK\\n' for p in [Path('a.txt'),Path('b.txt')] if p.exists())"], 'timeout': 10}]}
    s = c.start(plan)
    rid = s['run_id']
    restarted = False
    original_ids = None
    approved = set()
    deadline = time.monotonic() + 240
    try:
        while time.monotonic() < deadline:
            s = c.observe(rid)
            if not args.live and not restarted and all(t['state'] == 'running' for t in s['tasks'].values()):
                original_ids = {k: v['bridge_task'] for k, v in s['tasks'].items()}
                owner = json.loads((c.directory(rid) / 'daemon.json').read_text())
                os.kill(owner['pid'], signal.SIGKILL)
                # New daemon may race the old process exiting; wake is idempotent.
                time.sleep(.2)
                c.wake(rid)
                restarted = True
            for tid, t in s['tasks'].items():
                if t['state'] in ('failed', 'needs_changes', 'integration_failed'):
                    raise AssertionError(json.dumps(t, ensure_ascii=False))
                if t['state'] == 'awaiting_review':
                    assert Path(t['worktree'], tid + '.txt').read_text() == 'BRIDGE_TEAM_OK\n'
                    try:
                        c.decide(rid, s['revision'], {'action': 'approve', 'task_id': tid, 'candidate_commit': t['candidate'],
                                 'reviewer': 'deterministic-smoke-check', 'summary': 'Exact synthetic content, fixed source and passing test verified'})
                        approved.add(tid)
                    except BridgeError as exc:
                        if 'Stale revision' not in str(exc):
                            raise
                    break
            if s['status'] == 'completed':
                assert head(repo) == base
                assert (repo / 'user-uncommitted.txt').read_text() == 'preserve this\n'
                assert len(approved) == len(jobs)
                if not args.live:
                    assert restarted
                    assert original_ids == {k: v['bridge_task'] for k, v in s['tasks'].items()}
                    assert len({v['result']['sessionId'] for v in s['tasks'].values()}) == 2
                for job in jobs:
                    assert git(repo, 'show', s['integration_head'] + ':' + job['id'] + '.txt') == b'BRIDGE_TEAM_OK\n'
                summary = {'run_id': rid, 'status': s['status'], 'live_model': args.live,
                           'tasks_integrated': len(jobs), 'scheduler_restart_verified': restarted,
                           'original_workspace_preserved': True, 'integration_commit': s['integration_head'],
                           'observed_models': [t['result'].get('observed_model') for t in s['tasks'].values()],
                           'executor_tokens': s['executor_tokens']}
                atomic_json(output / 'summary.json', summary)
                print(json.dumps(summary, ensure_ascii=False))
                return
            time.sleep(.3)
        raise AssertionError('Pipeline timed out: ' + json.dumps(s, ensure_ascii=False))
    finally:
        if c.observe(rid)['status'] != 'completed':
            c.cancel(rid)
            for _ in range(100):
                if c.observe(rid)['status'] == 'cancelled':
                    break
                time.sleep(.3)


if __name__ == '__main__':
    main()
