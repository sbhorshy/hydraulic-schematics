#!/usr/bin/env python3
"""Issue 110 one-shot injection harness.

Reuses the official chain from research/issue102/make_cases.py:
  render_l0_sheet.py -> rasterize_sheet.py -> validate_sheet.py
Inputs are copied from the active 1# sheet; every edit stays in the sandbox
workdir under .artifacts/issue110/cases/. No main source is modified.

Usage: python3 research/issue110/make_unseen_cases.py [case ...]
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/hydraulic-schematic/scripts'
SRC = ROOT / '1#系统原理图'
OUT = ROOT / '.artifacts/issue110/cases'
EVIDENCE = ROOT / 'research/issue110/evidence'

INTENT = '1#系统.intent.yaml'
LAYOUT = '1#系统.layout.json'
SVG = '1#系统原理图.svg'
PNG = 'sheet-readback.png'


def run(*args, allow=(0,)):
    done = subprocess.run([sys.executable, *map(str, args)], cwd='/tmp',
                          capture_output=True, text=True)
    if done.returncode not in allow:
        print(done.stdout[-3000:], done.stderr[-3000:], file=sys.stderr)
        raise SystemExit('command failed rc=%s: %s' % (done.returncode, args[0]))
    return done


def dump_yaml(data, path):
    from ruamel.yaml import YAML
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 4096
    with path.open('w', encoding='utf-8') as fh:
        y.dump(data, fh)


def load_yaml(path):
    from ruamel.yaml import YAML
    return YAML(typ='safe', pure=True).load(path.read_text(encoding='utf-8'))


def apply_symbol_edits(work, edits, log):
    for filename, changes in (edits or {}).items():
        path = work / 'symbols' / filename
        raw = path.read_text(encoding='utf-8')
        for element_id, attr, value in changes:
            tag = re.search(r'<[^>]*\bid="%s"[^>]*>' % re.escape(element_id), raw)
            if not tag:
                raise RuntimeError('symbol edit target not found: %s %s' % (filename, element_id))
            old_tag = tag.group(0)
            found = re.search(r'\b%s="([^"]*)"' % re.escape(attr), old_tag)
            if found:
                new_tag = old_tag[:found.start(1)] + value + old_tag[found.end(1):]
                before = found.group(1)
            else:
                close = '/>' if old_tag.endswith('/>') else '>'
                new_tag = old_tag[:-len(close)] + ' %s="%s"%s' % (attr, value, close)
                before = None
            raw = raw[:tag.start()] + new_tag + raw[tag.end():]
            log.append({'file': 'symbols/' + filename, 'element_id': element_id,
                        'attribute': attr, 'before': before, 'after': value})
        path.write_text(raw, encoding='utf-8')


def apply_layout(layout, edits, log):
    for path, value in edits.items():
        path = path.split('.') if isinstance(path, str) else list(path)
        here = layout
        for key in path[:-1]:
            here = here[key]
        before = here[path[-1]]
        here[path[-1]] = value
        log.append({'file': LAYOUT, 'path': '.'.join(map(str, path)),
                    'before': before, 'after': value})


def polylines(raw):
    return [(m.group(1), m.group(2), m.span(2))
            for m in re.finditer(r'<polyline class="(ln-[a-z_]+)" points="([^"]+)"', raw)]


def first_polyline(raw, cls=None):
    for c, points, span in polylines(raw):
        if cls is None or c == cls:
            return c, points, span
    raise RuntimeError('no polyline ' + str(cls))


def parse_points(text):
    return [tuple(float(v) for v in pair.split(',')) for pair in text.split()]


def format_points(points):
    return ' '.join('%.1f,%.1f' % p for p in points)


def replace_points(raw, span, points):
    return raw[:span[0]] + format_points(points) + raw[span[1]:]


def svg_edit(raw, name, log):
    """Manual SVG edits are explicit and recorded with before/after geometry."""
    if name == 'v2-through-body':
        cls, points, span = first_polyline(raw, 'ln-pressure')
        pts = parse_points(points)
        a, b = pts[0], pts[-1]
        # Drive an orthogonal detour through the declared PRV-001 footprint
        # (layout x=1330..1470, y=290..368), well away from the original route.
        crossing = [(a[0], 320.0), (1400.0, 320.0), (1400.0, b[1])]
        new = [a] + crossing + [b]
        log.append({'file': SVG, 'edit': name, 'class': cls,
                    'before': pts, 'after': new,
                    'target_footprint': 'PRV-001 x=1330..1470 y=290..368'})
        return replace_points(raw, span, new)
    if name == 'v3-endpoint-gap':
        cls, points, span = first_polyline(raw)
        pts = parse_points(points)
        old = pts[-1]
        pts[-1] = (round(old[0] + 2.0, 1), round(old[1] + 2.0, 1))
        log.append({'file': SVG, 'edit': name, 'class': cls,
                    'before_endpoint': old, 'after_endpoint': pts[-1]})
        return replace_points(raw, span, pts)
    if name == 'v11-diagonal':
        cls, points, span = first_polyline(raw)
        pts = parse_points(points)
        if len(pts) < 3:
            raise RuntimeError('polyline needs >=3 points')
        old = pts[1]
        pts[1] = (round(old[0] + 11.0, 1), round(old[1] + 7.0, 1))
        log.append({'file': SVG, 'edit': name, 'class': cls,
                    'before_vertex': old, 'after_vertex': pts[1]})
        return replace_points(raw, span, pts)
    if name == 'v15-single-width':
        idx = raw.find('id="wire-3-0"')
        if idx < 0:
            raise RuntimeError('wire-3-0 not found')
        start = raw.rfind('<polyline', 0, idx)
        end = raw.find('/>', idx) + 2
        old = raw[start:end]
        close = '/>' if old.endswith('/>') else '>'
        new = old[:-len(close)] + ' style="stroke-width:4.8"' + close
        log.append({'file': SVG, 'edit': name, 'target': 'wire-3-0',
                    'before': old, 'after': new,
                    'expected': '3 * base_T = 3.60; inline 4.80 overrides CSS'})
        return raw[:start] + new + raw[end:]
    if name == 'v16-single-lead':
        m = re.search(r'<line[^>]*id="USER-001__port-stub-left"[^>]*>', raw)
        if not m:
            raise RuntimeError('USER-001__port-stub-left not found')
        old = m.group(0)
        close = '/>' if old.endswith('/>') else '>'
        new = old[:-len(close)] + ' style="stroke-width:1.8"' + close
        log.append({'file': SVG, 'edit': name, 'target': 'USER-001__port-stub-left',
                    'before': old, 'after': new,
                    'expected': 'pressure network 3.60; inline lead 1.80'})
        return raw[:m.start()] + new + raw[m.end():]
    if name == 'v15-network-width':
        m = re.search(r'(\.ln-pressure\s*\{\s*stroke-width:\s*)([\d.]+)', raw)
        if not m:
            raise RuntimeError('no .ln-pressure stroke-width in SVG CSS')
        old = m.group(2)
        raw = raw[:m.start(2)] + '4.80' + raw[m.end(2):]
        log.append({'file': SVG, 'edit': name, 'rule': '.ln-pressure stroke-width',
                    'before': old, 'after': '4.80', 'expected': '3 * base_T = 3.60'})
        return raw
    if name == 'v17-missing-slash':
        m = re.search(r'(<g class="suc-mark-group">)(.*?)(</g>)', raw, re.S)
        if not m:
            raise RuntimeError('no suc-mark-group in SVG')
        lines = re.findall(r'<line class="suc-mark"[^>]*/>', m.group(2))
        if len(lines) != 5:
            raise RuntimeError('expected five slashes, got %d' % len(lines))
        new_inner = m.group(2).replace(lines[0], '', 1)
        log.append({'file': SVG, 'edit': name, 'removed_slash': lines[0],
                    'before_count': 5, 'after_count': 4})
        return raw[:m.start(2)] + new_inner + raw[m.end(2):]
    if name == 'v16-lead-width':
        m = re.search(r'(\.pl-pressure\s*\{\s*stroke-width:\s*calc\()([\d.]+)', raw)
        if not m:
            raise RuntimeError('no .pl-pressure stroke-width in SVG CSS')
        old = m.group(2)
        raw = raw[:m.start(2)] + '4.80' + raw[m.end(2):]
        log.append({'file': SVG, 'edit': name, 'rule': '.pl-pressure stroke-width',
                    'before': old, 'after': '4.80', 'expected': '3 * base_T = 3.60'})
        return raw
    raise SystemExit('unknown svg edit ' + name)


CASES = {
    'base': {},
    # input-side injections
    'v7-legend-title': {'layout': {'legend.y': 1060}},
    'v8-foreign-member': {'groups': [
        {'id': 'ZONE', 'label': 'ACC/PG zone',
         'members': ['ACC-001', 'PG-001'], 'reason': 'V8 foreign frame coverage'}]},
    'v16-single-lead': {'svg': 'v16-single-lead'},
    'v20-assembly-crossing': {'assemblies': {
        'PUMPZONE': {'label': 'Pump zone', 'members': ['EDP-001', 'EMP-001']}}},
    # manual SVG injections (base render first, then edit final SVG)
    'v2-through-body': {'svg': 'v2-through-body'},
    'v3-endpoint-gap': {'svg': 'v3-endpoint-gap'},
    'v11-diagonal': {'svg': 'v11-diagonal'},
    'v15-single-width': {'svg': 'v15-single-width'},
    'v17-missing-slash': {'svg': 'v17-missing-slash'},
}


def build(name, spec):
    work = OUT / name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for item in (INTENT, '1#系统组件.json', 'component-catalog.json'):
        shutil.copy2(SRC / item, work / item)
    shutil.copytree(SRC / 'symbols', work / 'symbols')
    layout = json.loads((SRC / LAYOUT).read_text(encoding='utf-8'))
    intent = load_yaml(SRC / INTENT)
    log = []
    intent_touched = bool(spec.get('groups') or spec.get('assemblies') or spec.get('intent_paths'))
    apply_layout(layout, spec.get('layout') or {}, log)
    if spec.get('groups'):
        intent['groups'] = spec['groups']
        log.append({'file': INTENT, 'edit': 'groups', 'after': spec['groups']})
    if spec.get('assemblies'):
        intent['assemblies'] = spec['assemblies']
        log.append({'file': INTENT, 'edit': 'assemblies', 'after': spec['assemblies']})
    if spec.get('intent_paths'):
        intent['paths'].extend(spec['intent_paths'])
        log.append({'file': INTENT, 'edit': 'paths', 'appended': spec['intent_paths']})
    apply_symbol_edits(work, spec.get('symbol_edits'), log)
    if intent_touched:
        dump_yaml(intent, work / INTENT)
        log.append({'file': INTENT, 'note': 'YAML re-dump invalidates the byte-bound bridge registration; expect an extra V19 fail'})
    (work / LAYOUT).write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    rendered = run(SCRIPTS / 'render_l0_sheet.py', work)
    svg_path = work / SVG
    if spec.get('svg'):
        raw = svg_path.read_text(encoding='utf-8')
        svg_path.write_text(svg_edit(raw, spec['svg'], log), encoding='utf-8')
    raster = run(SCRIPTS / 'rasterize_sheet.py', svg_path, '-o', work / PNG)
    validated = subprocess.run([sys.executable, str(SCRIPTS / 'validate_sheet.py'), str(work)],
                               cwd='/tmp', capture_output=True, text=True)
    report_path = work / 'validation-report.json'
    if not report_path.exists():
        print(validated.stdout[-3000:], validated.stderr[-3000:], file=sys.stderr)
        raise SystemExit('validate_sheet produced no report')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    summary = {
        'case': name, 'spec': spec, 'edits': log,
        'official_chain': {
            'render_rc': rendered.returncode, 'rasterize_rc': raster.returncode,
            'validate_rc': validated.returncode,
            'render_stdout': rendered.stdout.strip(), 'rasterize_stdout': raster.stdout.strip(),
            'validate_stdout': validated.stdout.strip(), 'validate_stderr': validated.stderr.strip()},
        'fail_count': report['fail_count'], 'warn_count': report['warn_count'],
        'fails': [c for c in report['checks'] if c['result'] == 'fail'],
        'warns': [c for c in report['checks'] if c['result'] == 'warn'],
        'coverage': report.get('coverage', []),
        'artifacts': report.get('artifacts', {}),
        'topology_coverage': report.get('topology', {}).get('coverage_status'),
        'geometry_issues': report.get('geometry', {}).get('issues', []),
    }
    edir = EVIDENCE / name
    edir.mkdir(parents=True, exist_ok=True)
    (edir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    # Keep full report compact: checks + coverage + topology identity are enough
    # for the triage gate; the full report stays in the ignored workdir.
    compact = {k: report.get(k) for k in ('report_schema', 'fail_count', 'warn_count', 'checks',
                                          'coverage', 'artifacts', 'topology', 'geometry',
                                          'phases', 'delivery') if k in report}
    (edir / 'validation-report-compact.json').write_text(
        json.dumps(compact, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    fails = sorted({c['id'] for c in summary['fails']})
    print('%-22s render=%d raster=%d validate=%d fail=%-2d warn=%-2d %s' % (
        name, rendered.returncode, raster.returncode, validated.returncode,
        summary['fail_count'], summary['warn_count'], ','.join(fails)), flush=True)
    return summary


if __name__ == '__main__':
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for case in (sys.argv[1:] or list(CASES)):
        if case not in CASES:
            raise SystemExit('unknown case ' + case)
        build(case, CASES[case])
