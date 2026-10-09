"""Frozen content-addressed sheet evidence, independent of live tools/assets.

Snapshots preserve the original validation report and every file it fingerprints.
Historical scripts are retained as evidence, never executed by the comparison.
"""
import json
from pathlib import Path
import shutil

from proofreading_evidence import (SVG, PNG, REPORT, assess_png, digest_json,
                                   file_digest, verify_report)

MANIFEST = 'version.json'


def _inside(root, relative):
    path = (root / relative).resolve()
    if path == root or root not in path.parents:
        raise ValueError('Frozen artifact path leaves its version directory: ' + relative)
    return path


def read_version(path):
    """Return verified current SVG/PNG/report paths for a live or frozen version."""
    root = Path(path).resolve()
    if not (root / MANIFEST).is_file():
        verified = verify_report(root)
        if verified['status'] != 'current' or verified.get('png', {}).get('status') != 'pass':
            raise ValueError('Version requires current report and PNG provenance: ' + str(verified))
        report = json.loads((root / REPORT).read_text(encoding='utf-8'))
        return {'root': root, 'report': report, 'files': {
            key: Path(item['path']) if item['sha256'] is not None else None
            for key, item in report['artifacts']['files'].items()},
            'verification': verified, 'report_path': root / REPORT}
    manifest = json.loads((root / MANIFEST).read_text(encoding='utf-8'))
    if manifest.get('schema') != 'frozen-sheet-v1':
        raise ValueError('Unsupported frozen sheet schema')
    if manifest.get('integrity') != digest_json({k: v for k, v in manifest.items() if k != 'integrity'}):
        raise ValueError('Frozen version manifest integrity changed')
    report_path = root / REPORT
    if file_digest(report_path) != manifest['report_sha256']:
        raise ValueError('Frozen validation report content changed')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    if report.get('report_fingerprint') != digest_json({k: v for k, v in report.items() if k != 'report_fingerprint'}):
        raise ValueError('Frozen validation report fingerprint changed')
    expected = report['artifacts']
    if set(manifest['files']) != set(expected['files']):
        raise ValueError('Frozen artifact inventory differs from the validated version')
    files = {}
    for logical, item in manifest['files'].items():
        source = expected['files'][logical]
        local = _inside(root, item['path']) if item['path'] is not None else None
        actual = file_digest(local) if local else None
        if actual != source['sha256'] or actual != item['sha256']:
            raise ValueError('Frozen artifact content changed: ' + logical)
        files[logical] = local
    fingerprint = digest_json({'files': {k: v['sha256'] for k, v in manifest['files'].items()},
                               'versions': expected['versions']})
    if fingerprint != expected['fingerprint'] or fingerprint != manifest['artifact_fingerprint']:
        raise ValueError('Frozen artifact fingerprint differs from original validation')
    png = assess_png(root)
    if png['status'] != 'pass' or files.get('svg') != root / SVG or files.get('png') != root / PNG:
        raise ValueError('Frozen SVG/PNG provenance is not current: ' + str(png))
    return {'root': root, 'report': report, 'files': files, 'report_path': report_path,
            'verification': {'status': 'current', 'png': png, 'kind': 'frozen',
                             'fingerprint': fingerprint,
                             'perceptual_review': report.get('phases', {}).get('perceptual', {})}}


def freeze_version(source, output):
    """Copy verified evidence; refuse stale inputs or overwrite of prior history."""
    version = read_version(source)
    target = Path(output).resolve()
    if target == version['root'] or version['root'] in target.parents:
        raise ValueError('Frozen version must be outside its source directory')
    if target.exists():
        raise ValueError('Frozen version output already exists: ' + str(target))
    target.mkdir(parents=True)
    try:
        original = version['report']['artifacts']
        files = {}
        for logical, source_path in version['files'].items():
            relative = None
            if source_path is not None:
                if logical in ('svg', 'png', 'png_provenance'):
                    relative = {'svg': SVG, 'png': PNG, 'png_provenance': PNG + '.evidence.json'}[logical]
                elif logical.startswith('tool:'):
                    relative = 'tools/' + source_path.name
                else:
                    relative = 'artifacts/' + digest_json(logical)[:16] + '-' + source_path.name
                copied = _inside(target, relative)
                copied.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source_path, copied)
            files[logical] = {'path': relative, 'sha256': original['files'][logical]['sha256']}
        shutil.copyfile(version['report_path'], target / REPORT)
        manifest = {'schema': 'frozen-sheet-v1', 'artifact_fingerprint': original['fingerprint'],
                    'validation_fingerprint': version['report']['validation_fingerprint'],
                    'report_sha256': file_digest(target / REPORT), 'files': files,
                    'versions': original['versions'], 'source': str(version['root'])}
        manifest['integrity'] = digest_json(manifest)
        (target / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        # Detect concurrent source mutation or an incomplete copy before publishing success.
        frozen = read_version(target)
        current = read_version(source)
        if frozen['verification']['fingerprint'] != current['verification']['fingerprint']:
            raise ValueError('Source changed while freezing its evidence')
        return frozen
    except Exception:
        shutil.rmtree(target)
        raise
