"""Task contracts and controller-side verification. Standard library only."""
import fnmatch
from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import json
import math
import os
import re
from pathlib import Path, PurePosixPath
import stat
import subprocess
import time


class BridgeError(Exception):
    pass


def positive(value):
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        raise BridgeError('Timeout must be a finite positive number') from None
    if not math.isfinite(result) or result <= 0:
        raise BridgeError('Timeout must be a finite positive number')
    return result


def read_json(path):
    # DrvFS can briefly report ENOENT/denied while a writer replaces a record.
    # Retry only those transient read failures, never accept malformed JSON.
    for attempt in range(5):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8-sig'))
        except (FileNotFoundError, PermissionError):
            if attempt == 4:
                raise
            time.sleep(.01 * (2 ** attempt))


def atomic_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    with temp.open('w', encoding='utf-8') as out:
        json.dump(data, out, ensure_ascii=False, indent=2, allow_nan=False)
        out.write('\n')
    os.replace(temp, path)


def relative_name(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise BridgeError('Task paths must be nonempty POSIX relative paths')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or ':' in value or '\x00' in value:
        raise BridgeError('Task paths must stay inside cwd')
    return value


def contract(prompt=None, task_file=None, prompt_file=None):
    if sum(x is not None for x in (prompt, task_file, prompt_file)) != 1:
        raise BridgeError('Supply exactly one prompt, --prompt-file or --task-file')
    if task_file:
        data = read_json(task_file)
        if not isinstance(data, dict):
            raise BridgeError('Task file must be a JSON object')
        unknown = set(data) - {'version', 'prompt', 'allowed_files', 'forbidden_files',
                               'tests', 'acceptance', 'requires_shell', 'tool_policy', 'allow_subagents',
                               'reasoning_effort', 'first_delivery', 'recovery_prompt', 'recovery_context'}
        if unknown or data.get('version') != 1:
            raise BridgeError('Unknown task fields or unsupported task version')
        if 'allowed_files' not in data:
            raise BridgeError('Task file requires allowed_files (empty means no edits)')
    else:
        data = {'version': 1, 'prompt': Path(prompt_file).read_text() if prompt_file else prompt}
    if not isinstance(data.get('prompt'), str) or not data['prompt'].strip():
        raise BridgeError('Prompt must be nonempty text')
    for name in ('allowed_files', 'forbidden_files'):
        if name in data:
            if not isinstance(data[name], list):
                raise BridgeError(name + ' must be an array')
            for pattern in data[name]:
                relative_name(pattern)
    if not isinstance(data.get('requires_shell', False), bool):
        raise BridgeError('requires_shell must be boolean')
    if not isinstance(data.get('allow_subagents', False), bool):
        raise BridgeError('allow_subagents must be boolean')
    if not isinstance(data.get('acceptance', ''), str):
        raise BridgeError('acceptance must be text')
    if data.get('tool_policy', 'code-local') not in ('code-local', 'cli-default', 'development'):
        raise BridgeError('tool_policy must be development, code-local or cli-default')
    if data.get('reasoning_effort', 'inherit') not in ('low','high','max','inherit'):
        raise BridgeError('reasoning_effort must be low, high, max or inherit')
    for field in ('recovery_prompt', 'recovery_context'):
        if field in data and (not isinstance(data[field], str) or not data[field].strip() or len(data[field]) > 4000):
            raise BridgeError(field + ' must be concise nonempty text (at most 4000 characters)')
    if data.get('recovery_prompt') == data['prompt']:
        raise BridgeError('recovery_prompt must define a smaller goal, not repeat the original prompt')
    tests = data.setdefault('tests', [])
    if not isinstance(tests, list):
        raise BridgeError('tests must be an array')
    seen = set()
    for test in tests:
        if not isinstance(test, dict) or set(test) - {'id', 'argv', 'cwd', 'timeout'}:
            raise BridgeError('Invalid test specification')
        tid = test.get('id')
        if not isinstance(tid, str) or not tid or tid in seen:
            raise BridgeError('Test IDs must be unique nonempty strings')
        seen.add(tid)
        argv = test.get('argv')
        if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or '\x00' in x for x in argv):
            raise BridgeError('Each test requires an argv array; shell strings are not accepted')
        test['timeout'] = positive(test.get('timeout', 120))
        relative_name(test.get('cwd', '.'))
    validate_delivery(data)
    return data


def validate_delivery(data):
    delivery = data.get('first_delivery')
    if delivery is None:
        return
    if not isinstance(delivery, dict) or set(delivery) - {'files','test_ids','warning_seconds','timeout_seconds'}:
        raise BridgeError('Invalid first_delivery specification')
    files = delivery.get('files', data.get('allowed_files'))
    if not isinstance(files, list) or not files:
        raise BridgeError('first_delivery requires target file patterns')
    for pattern in files:
        relative_name(pattern)
    ids = delivery.get('test_ids')
    known = {t['id'] for t in data.get('tests', [])}
    if not isinstance(ids, list) or not ids or any(not isinstance(x,str) or x not in known for x in ids) or len(set(ids)) != len(ids):
        raise BridgeError('first_delivery requires unique declared test_ids')
    delivery['files'] = files
    delivery['warning_seconds'] = positive(delivery.get('warning_seconds', 180))
    delivery['timeout_seconds'] = positive(delivery.get('timeout_seconds', 300))
    if delivery['warning_seconds'] > delivery['timeout_seconds']:
        raise BridgeError('First-delivery warning must not exceed its timeout')


class PathMatcher:
    """Compile real globs once; literal paths never enter fnmatch's small cache."""
    def __init__(self, patterns):
        self.literals = set()
        self.globs = []
        for pattern in set(patterns):
            if any(c in pattern for c in '*?['):
                self.globs.append(re.compile(fnmatch.translate(pattern)).match)
            else:
                self.literals.add(pattern)

    def matches(self, name):
        return name in self.literals or any(match(name) for match in self.globs)


def snapshot(cwd, state_root, *, patterns=None, forbidden=()):
    """Tracked + nonignored untracked files, or all files in a non-git directory.

    Symlinks are recorded, never followed. Existing dirty content is the baseline.
    The metadata directory and git internals are excluded explicitly.
    Optional patterns/forbidden are for progress probes only. Exact paths skip
    inventory (and can include explicitly named ignored files); acceptance uses
    the unfiltered default inventory.
    """
    cwd = Path(cwd).resolve()
    state_root = Path(state_root).resolve()
    if state_root == cwd:
        raise BridgeError('State directory must not be the source workspace root')
    # A coordinator may put isolated worktrees under its state directory. Only
    # exclude metadata that is actually INSIDE this source tree, not its ancestor.
    exclude_metadata = state_root.is_relative_to(cwd)
    allowed_matcher = PathMatcher(patterns) if patterns is not None else None
    forbidden_matcher = PathMatcher(forbidden)
    exact_paths = allowed_matcher is not None and not allowed_matcher.globs
    git = None if exact_paths else subprocess.run(['git', '-C', str(cwd), 'rev-parse', '--show-toplevel'],
                                                  capture_output=True, timeout=20)
    if exact_paths:
        names = sorted(set(patterns))
        coverage = 'explicit task paths for progress only; not acceptance inventory'
    elif git.returncode == 0:
        result = subprocess.run(['git', '-C', str(cwd), 'ls-files', '-z', '--cached',
                                 '--others', '--exclude-standard'],
                                capture_output=True, check=True, timeout=60)
        names = sorted(set(os.fsdecode(x) for x in result.stdout.split(b'\0') if x))
        coverage = 'git tracked and nonignored untracked files; ignored files excluded'
    else:
        names = []
        for root, dirs, files in os.walk(cwd, followlinks=False):
            dirs[:] = [d for d in dirs if d != '.git' and Path(root, d).resolve() != state_root]
            for d in list(dirs):
                if Path(root, d).is_symlink():
                    files.append(d)
                    dirs.remove(d)
            names.extend(str(Path(root, f).relative_to(cwd)).replace(os.sep, '/') for f in files)
        coverage = 'all regular files and symlinks except .git and bridge state'
    groups = {}
    for name in names:
        if (not exact_paths and allowed_matcher is not None and not allowed_matcher.matches(name)) or forbidden_matcher.matches(name):
            continue
        parts = tuple(Path(name).parts)
        p = cwd / name
        # Exclude our own metadata without following workspace symlinks.
        if (exclude_metadata and (p == state_root or state_root in p.parents)) or '.git' in Path(name).parts:
            continue
        if not parts or '..' in parts or Path(name).is_absolute():
            raise BridgeError('Invalid path from file inventory')
        groups.setdefault(parts[:-1], []).append((parts[-1], name))
    # Open each directory chain once per bounded batch, not once per file.
    # openat/O_NOFOLLOW prevents following ancestor or leaf symlinks even when
    # they change between enumeration and hashing. All regular bytes are hashed
    # on every call: no timestamp-only or cross-snapshot content cache.
    root_fd = os.open(cwd, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        batches = [(parent, files[i:i + 32]) for parent, files in groups.items()
                   for i in range(0, len(files), 32)]
        entries = {}
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(batches)))) as pool:
            for batch in pool.map(lambda item: _hash_batch(root_fd, *item), batches):
                entries.update(batch)
    finally:
        os.close(root_fd)
    entries = dict(sorted(entries.items()))
    encoded = json.dumps(entries, sort_keys=True, separators=(',', ':')).encode()
    return {'files': entries, 'digest': hashlib.sha256(encoded).hexdigest(), 'coverage': coverage}


def _file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _hash_batch(root_fd, parent, files):
    directory = os.dup(root_fd)
    entries = {}
    try:
        for part in parent:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory)
            except OSError as exc:
                if exc.errno in (errno.ENOENT, errno.ELOOP, errno.ENOTDIR):
                    return {}  # deleted directory, or an ancestor replaced by a symlink
                raise
            os.close(directory)
            directory = child
        for leaf, name in files:
            try:
                info = os.stat(leaf, dir_fd=directory, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISLNK(info.st_mode):
                digest = hashlib.sha256(os.fsencode(os.readlink(leaf, dir_fd=directory))).hexdigest()
                if _file_identity(os.stat(leaf, dir_fd=directory, follow_symlinks=False)) != _file_identity(info):
                    raise BridgeError('Symlink changed during snapshot: ' + name)
                kind = 'symlink'
            elif stat.S_ISREG(info.st_mode):
                descriptor = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                with os.fdopen(descriptor, 'rb') as src:
                    if _file_identity(os.fstat(src.fileno())) != _file_identity(info):
                        raise BridgeError('File replaced during snapshot: ' + name)
                    h = hashlib.sha256()
                    for block in iter(lambda: src.read(1024 * 1024), b''):
                        h.update(block)
                    if _file_identity(os.fstat(src.fileno())) != _file_identity(info):
                        raise BridgeError('File changed during snapshot: ' + name)
                digest, kind = h.hexdigest(), 'file'
            else:
                continue
            entries[name] = {'sha256': digest, 'kind': kind, 'executable': bool(info.st_mode & 0o111)}
        return entries
    finally:
        os.close(directory)


def changes(before, after, task):
    old, new = before['files'], after['files']
    changed = [p for p in sorted(old.keys() | new.keys()) if old.get(p) != new.get(p)]
    allowed = task.get('allowed_files')
    forbidden = task.get('forbidden_files', [])
    allowed_matcher = PathMatcher(allowed) if allowed is not None else None
    forbidden_matcher = PathMatcher(forbidden)
    violations = [p for p in changed if forbidden_matcher.matches(p)
                  or (allowed_matcher is not None and not allowed_matcher.matches(p))]
    return {'changed_files': changed, 'scope_violations': violations,
            'scope_checked': allowed is not None or bool(forbidden), 'scope_coverage': after['coverage']}


def execute_tests(task, cwd, directory, cancelled, event):
    """Run only the controller's predeclared argv, never commands from model output."""
    import signal
    results = []
    for index, test in enumerate(task['tests']):
        if cancelled():
            break
        test_cwd = (Path(cwd) / test.get('cwd', '.')).resolve()
        if not test_cwd.is_relative_to(Path(cwd)) or not test_cwd.is_dir():
            raise BridgeError('Test cwd must be an existing directory inside task cwd')
        start = time.monotonic()
        log = Path(directory) / f'test-{index}.log'
        event({'type': 'test.started', 'test_id': test['id']})
        timeout = False
        with log.open('xb') as out:
            try:
                p = subprocess.Popen(test['argv'], cwd=test_cwd, stdout=out, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                results.append({'id': test['id'], 'status': 'launch_failed', 'exit_code': None,
                                'seconds': time.monotonic() - start, 'log': str(log)})
                continue
            try:
                start_identity = Path(f'/proc/{p.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
                atomic_json(Path(directory) / 'active-test.json', {'pid': p.pid, 'start': start_identity})
                while p.poll() is None:
                    timeout = time.monotonic() - start >= test['timeout']
                    if timeout or cancelled():
                        break
                    time.sleep(.05)
            finally:
                # Always clear any descendants of our POSIX test group, even if
                # its leader exited. Only this process group is touched.
                try:
                    os.killpg(p.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                p.wait(timeout=10)
                (Path(directory) / 'active-test.json').unlink(missing_ok=True)
        status = 'timed_out' if timeout else 'cancelled' if cancelled() else 'passed' if p.returncode == 0 else 'failed'
        row = {'id': test['id'], 'status': status, 'exit_code': p.returncode,
               'seconds': time.monotonic() - start, 'log': str(log), 'argv': test['argv']}
        results.append(row)
        event({'type': 'test.finished', 'test_id': test['id'], 'status': status})
    passed = bool(results) and len(results) == len(task['tests']) and all(r['status'] == 'passed' for r in results)
    return {'status': 'passed' if passed else 'not_run' if not task['tests'] else 'failed', 'tests': results,
            'executor': 'WSL controller; explicit argv; no shell=True'}
