"""Coverage and content-bound evidence shared by validation and review tools.

Checks may add ``coverage_status`` and ``coverage_detail`` to their evidence
records. A missing measurement must use not_checked, never a synthetic pass.
The legacy validation/checks/counts fields describe executed geometry checks.
Only delivery.ready describes complete, current evidence and perceptual review.
"""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
from pathlib import Path
import sys

INTENT = '1#系统.intent.yaml'
LAYOUT = '1#系统.layout.json'
SVG = '1#系统原理图.svg'
PNG = 'sheet-readback.png'
REPORT = 'validation-report.json'
REVIEW = 'perceptual-review.json'


def digest_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def digest_json(value):
    return digest_bytes(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                   separators=(',', ':'), allow_nan=False).encode('utf-8'))


def file_digest(path):
    path = Path(path)
    return digest_bytes(path.read_bytes()) if path.is_file() else None


def resolve_catalog(workdir, catalog_path=None, tool_dir=None):
    workdir = Path(workdir).resolve()
    if catalog_path:
        return Path(catalog_path).resolve()
    local = workdir / 'component-catalog.json'
    return local if local.is_file() else Path(tool_dir or Path(__file__).parent).resolve().parent / 'assets/component-library/component-catalog.json'


def build_snapshot(workdir, catalog_path=None, tool_dir=None):
    """Return SHA-256 versions of inputs, actual symbols, tools, SVG and PNG.

    Logical IDs keep fingerprints independent of temporary workspace names.
    Paths are retained for verification and diagnostics, not used as versions.
    """
    workdir = Path(workdir).resolve()
    tool_dir = Path(tool_dir or Path(__file__).parent).resolve()
    catalog = resolve_catalog(workdir, catalog_path, tool_dir)
    files = {}

    def add(key, path):
        path = Path(path).resolve()
        files[key] = {'path': str(path), 'sha256': file_digest(path)}

    for key, name in [('input', INTENT), ('layout', LAYOUT), ('svg', SVG), ('png', PNG),
                      ('topology_manifest', '1#系统原理图-topology.json'),
                      ('topology_manifest_markdown', '1#系统原理图-topology.md'),
                      ('png_provenance', PNG + '.evidence.json')]:
        add(key, workdir / name)
    add('catalog', catalog)
    for path in sorted(workdir.glob('*受控模板.yaml')):
        add('template:' + path.name, path)
    layout = json.loads((workdir / LAYOUT).read_text(encoding='utf-8'))
    for inst, node in sorted(layout.get('nodes', {}).items()):
        ref = node.get('symbol')
        if ref:
            path = workdir / ref
            if not path.is_file():
                path = catalog.parent / Path(ref).name
            add('symbol:' + inst, path)
    for path in sorted(tool_dir.glob('*.py')):
        if not path.name.startswith(('test_', 'selftest')):
            add('tool:' + path.name, path)
    versions = {'python': platform.python_version()}
    for package in ('Pillow', 'numpy', 'ruamel.yaml', 'jsonschema', 'kiwisolver'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    receipt = workdir / (PNG + '.evidence.json')
    if receipt.is_file():
        try:
            backend = json.loads(receipt.read_text(encoding='utf-8')).get('renderer', {}).get('backend')
            candidates = {'chrome': ('google-chrome', 'chromium', 'chromium-browser', 'chrome'),
                          'inkscape': ('inkscape',)}.get(backend, ())
            executable = next((shutil.which(name) for name in candidates if shutil.which(name)), None)
            versions['rasterizer'] = (subprocess.run([executable, '--version'], capture_output=True,
                                                    text=True, timeout=10).stdout.strip()
                                      if executable else None)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            versions['rasterizer'] = None
    fingerprint = digest_json({'files': {key: value['sha256'] for key, value in files.items()},
                               'versions': versions})
    return {'schema': 'sheet-artifacts-v1', 'algorithm': 'sha256',
            'fingerprint': fingerprint, 'files': files, 'versions': versions,
            'catalog_path': str(catalog), 'tool_dir': str(tool_dir)}


def write_png_receipt(svg, png, renderer):
    """Raster export evidence; never a perceptual-review decision."""
    record = {'schema': 'sheet-raster-v1', 'svg_sha256': file_digest(svg),
              'png_sha256': file_digest(png), 'renderer': renderer}
    Path(str(png) + '.evidence.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record


def assess_png(workdir):
    workdir = Path(workdir)
    png, svg = workdir / PNG, workdir / SVG
    receipt = Path(str(png) + '.evidence.json')
    if not png.is_file() or not receipt.is_file():
        return {'status': 'not_checked', 'detail': 'PNG or rasterization provenance is missing.'}
    try:
        record = json.loads(receipt.read_text(encoding='utf-8'))
        if record.get('schema') != 'sheet-raster-v1' or not record.get('renderer'):
            raise ValueError('Rasterization provenance is incomplete.')
        if record.get('svg_sha256') != file_digest(svg) or record.get('png_sha256') != file_digest(png):
            raise ValueError('PNG/SVG content differs from the rasterization provenance.')
        from PIL import Image
        with Image.open(png) as image:
            image.verify()
        return {'status': 'pass', 'detail': 'PNG matches the current SVG and rasterization receipt.',
                'receipt': record}
    except (OSError, ValueError, ImportError) as exc:
        return {'status': 'not_checked', 'detail': str(exc)}


def automated_payload(report):
    """Stable validation evidence, excluding the separately recorded review."""
    return {key: value for key, value in report.items()
            if key not in ('visual_review', 'phases', 'delivery', 'perceptual_review',
                           'validation_fingerprint', 'report_fingerprint', 'coverage')}


def validation_fingerprint(report):
    payload = automated_payload(report)
    payload['coverage'] = [e for e in report.get('coverage', []) if e['id'] != 'PERCEPTUAL']
    return digest_json(payload)


def assess_review(workdir, snapshot, report):
    path = Path(workdir) / REVIEW
    if not path.is_file():
        return {'status': 'pending', 'detail': 'No perceptual review has been recorded.'}
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        if (record.get('artifact_fingerprint') != snapshot['fingerprint'] or
                record.get('validation_fingerprint') != validation_fingerprint(report)):
            raise ValueError('Review is invalidated by changed artifacts or validation evidence.')
        if not record.get('reviewer') or not record.get('note') or record.get('decision') not in ('confirmed', 'questioned'):
            raise ValueError('Review does not contain an explicit decision, reviewer and note.')
        return {'status': record['decision'], 'detail': record['note'], 'record': record}
    except (OSError, ValueError) as exc:
        return {'status': 'invalidated', 'detail': str(exc)}


def write_report(report, path):
    report['report_fingerprint'] = digest_json({k: v for k, v in report.items() if k != 'report_fingerprint'})
    payload = json.dumps(report, ensure_ascii=False, indent=2).encode('utf-8')
    Path(path).write_bytes(payload)
    Path(str(path) + '.sha256').write_text(digest_bytes(payload), encoding='ascii')


def verify_report(workdir, report_path=None):
    """Reusable gate for crops/diffs: never trust an old report's success field.

    Returns status=current/invalidated plus changed artifact IDs and current
    review state. Callers must require current before consuming SVG/PNG evidence.
    """
    workdir = Path(workdir)
    path = Path(report_path) if report_path else workdir / REPORT
    try:
        payload = path.read_bytes()
        report = json.loads(payload)
        if Path(str(path) + '.sha256').read_text().strip() != digest_bytes(payload):
            raise ValueError('Validation report content has changed.')
        if report.get('report_fingerprint') != digest_json({k: v for k, v in report.items() if k != 'report_fingerprint'}):
            raise ValueError('Validation report fingerprint is invalid.')
        recorded = report['artifacts']
        current = build_snapshot(workdir, recorded['catalog_path'], recorded['tool_dir'])
        changed = sorted(key for key in set(recorded['files']) | set(current['files'])
                         if recorded['files'].get(key, {}).get('sha256') != current['files'].get(key, {}).get('sha256'))
        if recorded['versions'] != current['versions']:
            changed.append('tool_versions')
        if recorded['fingerprint'] != current['fingerprint']:
            return {'status': 'invalidated', 'changed': changed,
                    'perceptual_review': {'status': 'invalidated'}}
        return {'status': 'current', 'fingerprint': current['fingerprint'], 'changed': [],
                'png': assess_png(workdir), 'perceptual_review': assess_review(workdir, current, report)}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {'status': 'invalidated', 'detail': str(exc),
                'perceptual_review': {'status': 'invalidated'}}


# Baseline limitations are retired individually by measured evidence from a check.
LIMITATIONS = {
    'V3': 'Port arrival/direction coverage is incomplete in the legacy checker.',
    'V4': 'Legacy junction check uses bus coordinates, not reconciled connectivity.',
    'V10': 'Network counts do not establish edge-by-edge connectivity.',
    'V12': 'Legacy text bounds are estimated; rendered text has not been measured.',
    'V16': 'Computed display widths have not been measured for every lead.',
    'B6.avoid_corridor': 'Pipe-to-body clearance has not been measured.',
    'B7': 'Rendered label clearance has not been measured.',
}


def coverage_for(report):
    """Expose each check, preserving failures and explicit incomplete evidence."""
    records = report.get('evidence', [])
    coverage = []
    for check_id in [*(f'V{i}' for i in range(1, 20)), 'B6.avoid_corridor', 'B7']:
        evidence = [e for e in records if e.get('id') == check_id]
        findings = [e for e in report.get('checks', []) if e.get('id') == check_id]
        explicit = [e for e in evidence if 'coverage_status' in e]
        status = 'not_checked' if check_id in LIMITATIONS else 'pass'
        detail = LIMITATIONS.get(check_id, 'The checker executed for this SVG.')
        if explicit:
            # Any unchecked sub-check prevents a blanket pass for this check ID.
            priority = {'fail': 5, 'not_checked': 4, 'warn': 3, 'pass': 2, 'not_applicable': 1}
            chosen = max(explicit, key=lambda e: priority[e['coverage_status']])
            status = chosen['coverage_status']
            detail = chosen.get('coverage_detail', chosen.get('detail', detail))
        if any(e['result'] == 'fail' for e in findings):
            status = 'fail'
        elif status == 'pass' and any(e['result'] == 'warn' for e in findings):
            status = 'warn'
        coverage.append(dict(id=check_id, status=status, required=True,
                             evidence=evidence + findings or [{'detail': detail}], detail=detail))
    for item in report.get('composition_budget', {}).get('items', []):
        if item['id'] == 'B7':
            continue  # The rendered measurement evidence above owns B7.
        check_id = 'B6.group_padding' if item['id'] == 'B6' else item['id']
        status = {'over': 'warn', 'exempt': 'warn', 'not_measured': 'not_checked'}.get(item['status'], item['status'])
        detail = item.get('detail') or 'Composition budget measured by the validator.'
        if check_id == 'B6.group_padding' and item.get('measured', {}).get('group_padding') is None:
            status, detail = 'not_applicable', 'No group padding is declared in this layout.'
        coverage.append(dict(id=check_id, status=status, required=True,
                             evidence=[item], detail=detail))
    return coverage


def enrich_report(report, workdir, **kwargs):
    coverage = coverage_for(report)
    png = assess_png(workdir)
    coverage.extend([
        dict(id='PNG', status=png['status'], required=True,
             detail=png['detail'], evidence=[png]),
        dict(id='PERCEPTUAL', status='not_checked', required=True,
             detail='No current perceptual review.', evidence=[{'path': 'perceptual-review.json'}]),
    ])
    report['report_schema'] = 'proofreading-evidence-v1'
    report['artifacts'] = build_snapshot(workdir, **kwargs)
    report['coverage'] = coverage
    review = assess_review(workdir, report['artifacts'], report)
    coverage[-1].update(status='pass' if review['status'] == 'confirmed' else 'not_checked',
                        detail=review['detail'], evidence=[review])
    missing = [e['id'] for e in coverage if e['status'] in ('not_checked', 'fail')]
    report['phases'] = {
        'automated': {'status': 'failed' if any(e['status'] == 'fail' for e in coverage) else
                     ('incomplete' if any(e != 'PERCEPTUAL' for e in missing) else 'complete')},
        'perceptual': review,
    }
    report['visual_review'] = 'passed' if review['status'] == 'confirmed' else 'pending'
    report['delivery'] = {'ready': not missing, 'status': 'ready' if not missing else 'incomplete',
                          'blocking_checks': missing}
    report['validation_fingerprint'] = validation_fingerprint(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    verify = commands.add_parser('verify', help='Verify the report against current artifact contents')
    verify.add_argument('workdir')
    review = commands.add_parser('record-review', help='Record an explicit review of current SVG/PNG evidence')
    review.add_argument('workdir')
    review.add_argument('--reviewer', required=True)
    review.add_argument('--decision', choices=('confirmed', 'questioned'), required=True)
    review.add_argument('--note', required=True)
    args = parser.parse_args()
    result = verify_report(args.workdir)
    if args.command == 'record-review' and result['status'] == 'current':
        if result['png']['status'] != 'pass':
            result = {'status': 'invalidated', 'detail': 'A verified current PNG is required for review.'}
        elif not args.reviewer.strip() or not args.note.strip():
            result = {'status': 'invalidated', 'detail': 'Reviewer and review note cannot be empty.'}
        else:
            report = json.loads((Path(args.workdir) / REPORT).read_text(encoding='utf-8'))
            record = {'schema': 'sheet-perceptual-review-v1', 'reviewer': args.reviewer,
                      'decision': args.decision, 'note': args.note,
                      'artifact_fingerprint': result['fingerprint'],
                      'validation_fingerprint': report['validation_fingerprint']}
            (Path(args.workdir) / REVIEW).write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
            result['perceptual_review'] = {'status': args.decision}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'current' else 1


if __name__ == '__main__':
    sys.exit(main())
