#!/usr/bin/env python3
"""Reproduce the pre-render hard route gate blockers cited in the issue-110 README.

Each probe copies the active 1# inputs, makes one layout perturbation, and runs
only the official renderer. A blocked probe has routing-error.json and no SVG.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / '1#系统原理图'
SCRIPTS = ROOT / '.agents/skills/hydraulic-schematic/scripts'
OUT = ROOT / '.artifacts/issue110/probes'
EVIDENCE = ROOT / 'research/issue110/evidence/route-gate-probe.json'

PROBES = [
    ('ACC-001', 'y', 170), ('PRV-002', 'y', -60), ('PG-001', 'x', 60),
    ('ACV-001', 'y', 60), ('EDP-001', 'x', 60), ('EMP-001', 'y', -60),
    ('CDF-001', 'x', 60), ('ACC-001', 'y', -60), ('PRV-002', 'y', 60),
]


def main():
    rows = []
    for inst, axis, delta in PROBES:
        name = '%s-%s%+d' % (inst, axis, delta)
        work = OUT / name
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)
        for item in ('1#系统.intent.yaml', '1#系统组件.json', 'component-catalog.json'):
            shutil.copy2(SRC / item, work / item)
        shutil.copytree(SRC / 'symbols', work / 'symbols')
        layout = json.loads((SRC / '1#系统.layout.json').read_text(encoding='utf-8'))
        before = layout['nodes'][inst][axis]
        layout['nodes'][inst][axis] = before + delta
        (work / '1#系统.layout.json').write_text(
            json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        done = subprocess.run([sys.executable, str(SCRIPTS / 'render_l0_sheet.py'), str(work)],
                              cwd='/tmp', capture_output=True, text=True)
        err = work / 'routing-error.json'
        info = json.loads(err.read_text(encoding='utf-8')) if err.exists() else None
        rows.append({'probe': name, 'edit': '%s.%s: %s -> %s' % (inst, axis, before, before + delta),
                     'render_rc': done.returncode,
                     'svg_written': (work / '1#系统原理图.svg').exists(),
                     'routing_error': info,
                     'render_stderr_tail': done.stderr[-400:]})
        print('%-18s rc=%d blocked=%s anchor=%s' % (
            name, done.returncode, info is not None,
            (info or {}).get('anchor')), flush=True)
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
