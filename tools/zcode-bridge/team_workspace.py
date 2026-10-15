"""Git worktree ownership and immutable candidates for the team coordinator."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess

from bridge_contract import BridgeError, atomic_json, read_json


def git(repo, *args, input=None):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_AUTHOR_NAME='ZCode Bridge',
               GIT_AUTHOR_EMAIL='zcode-bridge@localhost', GIT_COMMITTER_NAME='ZCode Bridge',
               GIT_COMMITTER_EMAIL='zcode-bridge@localhost')
    p = subprocess.run(['git', '-C', str(repo), *args], input=input,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, env=env)
    if p.returncode:
        raise BridgeError('git ' + args[0] + ': ' + p.stderr.decode('utf-8', 'replace')[-3000:])
    return p.stdout


def common_dir(repo):
    return Path(os.fsdecode(git(repo, 'rev-parse', '--path-format=absolute', '--git-common-dir')).strip()).resolve()


def repo_root(repo):
    return Path(os.fsdecode(git(repo, 'rev-parse', '--show-toplevel')).strip()).resolve()


def canonical(path):
    value = str(Path(path).resolve())
    return value.casefold() if value.startswith('/mnt/') else value


@contextmanager
def repository_lock(repo):
    directory = common_dir(repo) / 'zcode-bridge-team'
    directory.mkdir(exist_ok=True)
    with (directory / 'coordinator.lock').open('a+') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield directory


def check_bridge_owner(cwd, run_id=None):
    """All updated bridge entry points honor a team claim, including nested cwd."""
    try:
        directory = common_dir(cwd) / 'zcode-bridge-team'
    except BridgeError:
        return
    with repository_lock(cwd) as directory:
        _check_owner(directory, cwd, run_id)


def _check_owner(directory, cwd, run_id):
    owner_file = directory / 'owner.json'
    if not owner_file.exists():
        if run_id:
            raise BridgeError('Team repository claim has been released; refusing a late worker')
        return
    owner = read_json(owner_file)
    if owner['run_id'] != run_id or canonical(cwd) not in owner['worktrees']:
        raise BridgeError('Repository is claimed by team ' + owner['run_id'] +
                          '; use its coordinator instead of another cwd/state-dir')


def claim_bridge(cwd, run_id, tid, task_dir):
    try:
        common_dir(cwd)
    except BridgeError:
        return None
    with repository_lock(cwd) as directory:
        _check_owner(directory, cwd, run_id)
        if run_id:
            return None
        lease = directory / ('execution-' + tid + '.json')
        atomic_json(lease, {'task_id': tid, 'task_dir': str(task_dir), 'cwd': str(cwd)})
        return str(lease)


def release_bridge_claim(path, tid):
    if not path:
        return
    p = Path(path)
    with (p.parent / 'coordinator.lock').open('a+') as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if p.exists() and read_json(p).get('task_id') == tid:
            p.unlink()


def add_worktree(repo, path, commit):
    path = Path(path)
    if path.exists():
        raise BridgeError('Worktree destination already exists')
    git(repo, 'worktree', 'add', '--detach', str(path), commit)


def head(repo):
    return git(repo, 'rev-parse', 'HEAD').decode().strip()


def clean(repo):
    return not git(repo, 'status', '--porcelain', '--untracked-files=all').strip()


def freeze(repo, parent, message):
    if head(repo) != parent:
        raise BridgeError('Worker changed Git HEAD; candidate requires inspection')
    git(repo, 'add', '--all', '--', '.')
    tree = git(repo, 'write-tree').decode().strip()
    # Plumbing commits avoid invoking application hooks or changing user identity.
    commit = git(repo, 'commit-tree', tree, '-p', parent, input=(message + '\n').encode()).decode().strip()
    git(repo, 'update-ref', 'HEAD', commit, parent)
    return commit


def apply_candidate(repo, trial, integration_head, base, candidate):
    add_worktree(repo, trial, integration_head)
    patch = git(repo, 'diff', '--binary', base, candidate, '--', '.')
    if patch:
        git(trial, 'apply', '--3way', '--index', '-', input=patch)
    return freeze(trial, integration_head, 'Integrate reviewed candidate ' + candidate)
