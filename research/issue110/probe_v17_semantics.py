#!/usr/bin/env python3
"""Record the input-side V17 suction-semantics variant blocked before render.

Adds one suction-to-pressure path to a sandbox copy and runs the official
renderer; it raises ValueError on incompatible suction terminals, so no SVG is
produced. The renderable V17 sample in this study is the manual SVG slash case.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_unseen_cases import ROOT, SCRIPTS, SRC, INTENT, LAYOUT, dump_yaml, load_yaml  # noqa: E402

WORK = ROOT / '.artifacts/issue110/cases/v17-suction-semantics'
OUT = ROOT / 'research/issue110/evidence/v17-semantics-blocked.json'
ADDED = ['TANK-001.suction_out', 'USER-001.pressure_in']


def main():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.mkdir(parents=True)
    for item in (INTENT, '1#系统组件.json', 'component-catalog.json'):
        shutil.copy2(SRC / item, WORK / item)
    shutil.copytree(SRC / 'symbols', WORK / 'symbols')
    (WORK / LAYOUT).write_bytes((SRC / LAYOUT).read_bytes())
    intent = load_yaml(SRC / INTENT)
    intent['paths'].append(ADDED)
    dump_yaml(intent, WORK / INTENT)
    done = subprocess.run([sys.executable, str(SCRIPTS / 'render_l0_sheet.py'), str(WORK)],
                          cwd='/tmp', capture_output=True, text=True)
    result = {'case': 'v17-suction-semantics', 'input_edit': {'paths.append': ADDED},
              'command': 'python3 <skill>/scripts/render_l0_sheet.py <workdir>',
              'render_rc': done.returncode, 'svg_written': (WORK / '1#系统原理图.svg').exists(),
              'stderr': done.stderr.strip()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('render_rc=%d svg=%s stderr_tail=%s' % (
        done.returncode, result['svg_written'], done.stderr.strip()[-200:]))


if __name__ == '__main__':
    main()
