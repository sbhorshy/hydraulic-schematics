#!/usr/bin/env python3
"""Prepare/review a hash-bound install plan, then install with an original backup."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import uuid

ROOT = Path(__file__).resolve().parent
FILES = ['bridge_contract.py', 'bridge_delivery.py', 'bridge_probe.py', 'bridge_progress.py',
         'subagent-policy.cjs', 'subagent-runtime.cjs', 'command-evidence.cjs', 'reasoning.cjs', 'protocol.cjs', 'launcher.cjs',
         'bridge_transport.py', 'team_workspace.py', 'bridge.py', 'team.py',
         'README.md', 'TEAM.md', 'team.example.json', 'team.staged.example.json', 'task.example.json', '.gitignore',
         'tests/fake_cli.py', 'tests/fake_cli.cjs', 'tests/fake_protocol.cjs', 'tests/test_development.py', 'tests/test_bridge.py',
         'tests/subagent_policy_test.cjs', 'tests/test_subagents.py',
         'tests/test_output_progress.py',
         'tests/test_probe_performance.py',
         'tests/test_delivery.py',
         'tests/recovery_windows_smoke.py',
         'tests/windows_smoke.py', 'tests/development_windows_smoke.py', 'tests/live_smoke.py', 'tests/test_team.py', 'tests/team_smoke.py', 'tests/test_optimization.py',
         'ask-zcode.sh', 'ask-zcode.py']


def digest(path):
    if path.is_symlink():
        raise RuntimeError('Refusing symlink install path: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True)
    parser.add_argument('--plan', required=True)
    parser.add_argument('--prepare', action='store_true')
    args = parser.parse_args()
    target = Path(args.target).resolve(strict=True)
    plan_path = Path(args.plan).resolve()
    if args.prepare:
        plan = {'version': 1, 'source': str(ROOT), 'target': str(target), 'files': {
            name: {'source_sha256': digest(ROOT / name), 'previous_sha256': digest(target / name)} for name in FILES}}
        with plan_path.open('x', encoding='utf-8') as out:
            json.dump(plan, out, ensure_ascii=False, indent=2)
        print(json.dumps({'prepared': str(plan_path), 'files': len(FILES)}, ensure_ascii=False))
        return
    plan = json.loads(plan_path.read_text())
    if plan['source'] != str(ROOT) or plan['target'] != str(target) or set(plan['files']) != set(FILES):
        raise RuntimeError('Install plan does not match this source/target/file set')
    for name, entry in plan['files'].items():
        if digest(ROOT / name) != entry['source_sha256'] or digest(target / name) != entry['previous_sha256']:
            raise RuntimeError('Files changed since plan preparation: ' + name)
        if any(p.is_symlink() for p in (target / name).parents if p != target and target in p.parents):
            raise RuntimeError('Refusing symlink parent')
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    backup = target / '.backups' / tag
    backup.mkdir(parents=True)
    (backup / 'install-plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2))
    for name in FILES:
        if (target / name).exists():
            (backup / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target / name, backup / name)
    installed = []
    try:
        for name in FILES:
            dest = target / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            temp = dest.with_name(dest.name + '.install-' + tag)
            shutil.copy2(ROOT / name, temp)
            # Check again immediately before replacing an existing file.
            if digest(dest) != plan['files'][name]['previous_sha256']:
                temp.unlink()
                raise RuntimeError('Target changed during install: ' + name)
            os.replace(temp, dest)
            installed.append(name)
        assert all(digest(target / name) == plan['files'][name]['source_sha256'] for name in FILES)
    except BaseException:
        for name in reversed(installed):
            dest = target / name
            if digest(dest) != plan['files'][name]['source_sha256']:
                continue  # never overwrite a later external edit while rolling back
            if (backup / name).exists():
                shutil.copy2(backup / name, dest)
            else:
                dest.unlink()
        raise
    receipt = {'target': str(target), 'backup': str(backup), 'files': len(FILES),
               'verified_sha256': {name: digest(target / name) for name in FILES}}
    receipt_path = plan_path.with_name(plan_path.stem + '-receipt.json')
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'installed': str(target), 'backup': str(backup), 'receipt': str(receipt_path)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
