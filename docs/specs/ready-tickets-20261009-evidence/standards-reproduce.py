"""Focused contract probes; no full suite or source mutation."""
import copy
import json
from pathlib import Path
import sys

repo = Path(__file__).resolve().parent.parent / 'integration'
skill = repo / '.agents/skills/hydraulic-schematic'
sys.path.insert(0, str(skill / 'scripts'))
from layout_contract import drawable_bounds
from preflight import load_yaml_text, preflight

layout = json.loads((skill / 'assets/fixtures/l0-small-seed/1#系统.layout.json').read_text())
layout.pop('coordinate_system')
print('Missing coordinate_system accepted:', drawable_bounds(layout))

intent, source = load_yaml_text(skill / 'assets/fixtures/l0-assembly-seed/1#系统.intent.yaml')
catalog = json.loads((skill / 'assets/component-library/component-catalog.json').read_text())
sys.modules['jsonschema'] = None  # Reproduce the documented optional-dependency absence.
aid = next(iter(intent['assemblies']))
for case in ('missing_label', 'one_member'):
    bad = copy.deepcopy(intent)
    if case == 'missing_label':
        bad['assemblies'][aid].pop('label')
    else:
        bad['assemblies'][aid]['members'] = bad['assemblies'][aid]['members'][:1]
    result = preflight(bad, catalog, source)
    print(case, json.dumps(result, ensure_ascii=False))
