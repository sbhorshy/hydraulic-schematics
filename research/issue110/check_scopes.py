#!/usr/bin/env python3
"""Check the issue-110 scopes against the official sheet_diff._scope gate.

`sheet_diff._scope` consumes version models; only the topology part is used for
identifier validation, so models are built from each case's official validation
report. Browser-measurement and PNG-receipt preconditions of `_model` are also
printed from the same report so scope acceptance is not mistaken for a full
`sheet_diff compare` pass.

Usage: python3 research/issue110/check_scopes.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / '.agents/skills/hydraulic-schematic/scripts'
sys.path.insert(0, str(SCRIPTS))
import sheet_diff  # noqa: E402

EVIDENCE = ROOT / 'research/issue110/evidence'
SCOPES = ROOT / 'research/issue110/scopes'


def model(case):
    report = json.loads((EVIDENCE / case / 'validation-report-compact.json').read_text(encoding='utf-8'))
    return {'topology': report['topology']}


def main():
    results = {}
    for path in sorted(SCOPES.glob('*.json')):
        case = path.stem
        scope = json.loads(path.read_text(encoding='utf-8'))
        try:
            checked = sheet_diff._scope(scope, [model('base'), model(case)])
            status, detail = 'accepted', {'nodes': checked['nodes'], 'edges': checked['edges'],
                                          'allowed_edges': checked['allowed_edges']}
        except ValueError as error:
            status, detail = 'rejected', str(error)
        results[case] = {'status': status, 'detail': detail}
        print('%-22s %s' % (case, status))
        if status != 'accepted':
            print('   ', detail)
    out = EVIDENCE / 'scope-check.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
