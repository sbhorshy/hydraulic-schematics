#!/usr/bin/env python3
"""Small read-only feasibility probes for issue #113.

Copies the active 1# inputs into ignored sandbox workdirs and calls only the
official skill scripts.  No production source, input or branch file is edited.
Outputs compact textual evidence in research/issue113/evidence/probe-paths.json.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/hydraulic-schematic/scripts'
SRC = ROOT / '1#系统原理图'
OUT = ROOT / '.artifacts/issue113'
EVIDENCE = ROOT / 'research/issue113/evidence/probe-paths.json'
INTENT = '1#系统.intent.yaml'
LAYOUT = '1#系统.layout.json'
SVG = '1#系统原理图.svg'
PNG = 'sheet-readback.png'


def run(script, *args, allow=(0,)):
    done = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          cwd='/tmp', capture_output=True, text=True)
    m = re.search(r'^((?:ValueError|SystemExit|RuntimeError):.*)$', done.stderr, re.M)
    return {'rc': done.returncode, 'stdout': done.stdout.strip()[-600:],
            'stderr': done.stderr.strip()[-900:],
            'error_line': m.group(1)[:400] if m else None}


def sandbox(name):
    work = OUT / name
    if work.exists():
        import shutil
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for item in (INTENT, '1#系统组件.json', 'component-catalog.json'):
        (work / item).write_bytes((SRC / item).read_bytes())
    import shutil
    shutil.copytree(SRC / 'symbols', work / 'symbols')
    (work / LAYOUT).write_bytes((SRC / LAYOUT).read_bytes())
    return work


def chain(work):
    render = run('render_l0_sheet.py', work)
    svg = work / SVG
    if render['rc'] != 0 or not svg.exists():
        return {'render': render, 'svg_written': svg.exists()}
    raster = run('rasterize_sheet.py', svg, '-o', work / PNG)
    validate = run('validate_sheet.py', work)
    report = json.loads((work / 'validation-report.json').read_text(encoding='utf-8'))
    return {'render': render, 'rasterize': raster, 'validate': validate,
            'svg_written': True,
            'fail_ids': sorted({c['id'] for c in report['checks'] if c['result'] == 'fail'}),
            'fail_count': report['fail_count'], 'warn_count': report['warn_count'],
            'fails': [{'id': c['id'], 'detail': c.get('detail', '')[:400]}
                      for c in report['checks'] if c['result'] == 'fail']}


def inject_v2(work):
    """Same single post-render SVG edit as issue110's v2-through-body case."""
    path = work / SVG
    raw = path.read_text(encoding='utf-8')
    m = re.search(r'<polyline class="ln-pressure" points="([^"]+)"', raw)
    pts = [tuple(float(v) for v in pair.split(',')) for pair in m.group(1).split()]
    a, b = pts[0], pts[-1]
    new = [a, (a[0], 320.0), (1400.0, 320.0), (1400.0, b[1]), b]
    text = ' '.join('%.1f,%.1f' % p for p in new)
    raw = raw[:m.start(1)] + text + raw[m.end(1):]
    path.write_text(raw, encoding='utf-8')
    return {'before': pts, 'after': new, 'target': 'PRV-001 x=1330..1470 y=290..368'}


def perturb_layout(work, inst, axis, delta):
    p = work / LAYOUT
    layout = json.loads(p.read_text(encoding='utf-8'))
    before = layout['nodes'][inst][axis]
    layout['nodes'][inst][axis] = before + delta
    p.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {'inst': inst, 'axis': axis, 'before': before, 'after': before + delta}


def append_intent_path(work):
    from ruamel.yaml import YAML
    p = work / INTENT
    y = YAML(typ='safe', pure=True)
    intent = y.load(p.read_text(encoding='utf-8'))
    added = ['TANK-001.suction_out', 'USER-001.pressure_in']
    intent['paths'].append(added)
    out = YAML()
    out.default_flow_style = False
    out.allow_unicode = True
    out.width = 4096
    with p.open('w', encoding='utf-8') as fh:
        out.dump(intent, fh)
    return added


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    result = {
        'python': sys.version.split()[0],
        'head': subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                               capture_output=True, text=True).stdout.strip(),
        'script_sha256': {p.name: sha(p) for p in sorted(SCRIPTS.glob('*.py'))
                          if p.name in ('render_l0_sheet.py', 'validate_sheet.py',
                                        'bridge_allowance.py', 'sheet_diff.py')},
        'scenarios': {},
    }

    # 1. controlled post-render injection: official chain still arbitrates.
    w = sandbox('post-render-v2')
    render = run('render_l0_sheet.py', w)
    edit = inject_v2(w)
    raster = run('rasterize_sheet.py', w / SVG, '-o', w / PNG)
    validate = run('validate_sheet.py', w)
    report = json.loads((w / 'validation-report.json').read_text(encoding='utf-8'))
    result['scenarios']['post-render-v2'] = {
        'edit': edit, 'render_rc': render['rc'], 'rasterize_rc': raster['rc'],
        'validate_rc': validate['rc'], 'fail_ids': sorted({c['id'] for c in report['checks']
                                                           if c['result'] == 'fail'}),
        'v2_details': [c.get('detail', '')[:400] for c in report['checks']
                       if c['id'] == 'V2' and c['result'] == 'fail']}

    # 2. layout targets that pass the hard gate: do they expose the defect?
    for name, inst, axis, delta in (('gate-pass-acc', 'ACC-001', 'y', -60),
                                    ('gate-pass-prv', 'PRV-002', 'y', 60)):
        w = sandbox(name)
        edit = perturb_layout(w, inst, axis, delta)
        result['scenarios'][name] = {'edit': edit, **chain(w)}

    # 3. V17 suction-semantics input edit: block before any SVG.
    w = sandbox('v17-semantics')
    added = append_intent_path(w)
    render = run('render_l0_sheet.py', w)
    result['scenarios']['v17-semantics'] = {
        'intent_paths_append': added, 'render': render,
        'render_error_line': render['error_line'],
        'svg_written': (w / SVG).exists(),
        'routing_error_written': (w / 'routing-error.json').exists()}

    # 4. byte-bound bridge registration: intent byte change alone fails closed.
    w = sandbox('bridge-binding')
    base = chain(w)
    p = w / INTENT
    before_hash = sha(p)
    with p.open('a', encoding='utf-8') as fh:
        fh.write('\n# issue113 probe: byte change only, no semantic edit\n')
    after_hash = sha(p)
    validate = run('validate_sheet.py', w)
    report = json.loads((w / 'validation-report.json').read_text(encoding='utf-8'))
    result['scenarios']['bridge-binding'] = {
        'baseline_fail_ids': base.get('fail_ids'), 'intent_sha256_before': before_hash,
        'intent_sha256_after': after_hash, 'validate_rc': validate['rc'],
        'fail_ids': sorted({c['id'] for c in report['checks'] if c['result'] == 'fail'}),
        'v19_details': [c.get('detail', '')[:400] for c in report['checks']
                        if c['id'] == 'V19' and c['result'] == 'fail']}

    # 5. is the registry injection seam reachable from the production entry?
    sys.path.insert(0, str(SCRIPTS))
    import inspect
    import bridge_allowance as BA
    result['registry_seam'] = {
        'check_bridge_policy_signature': str(inspect.signature(BA.check_bridge_policy)),
        'resolve_policy_signature': str(inspect.signature(BA.resolve_policy)),
        'production_policy_ids': sorted(BA.PRODUCTION_BRIDGE_POLICIES)}

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n',
                        encoding='utf-8')
    for name, row in result['scenarios'].items():
        print(name, json.dumps({k: row.get(k) for k in
                                ('fail_ids', 'svg_written', 'render_rc', 'validate_rc')},
                               ensure_ascii=False))


if __name__ == '__main__':
    main()
