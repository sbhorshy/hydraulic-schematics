"""The active project renders the canonical reservoir contract after retirement."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from repository_context import REPO, SCRIPTS
PROJECT = REPO / '1#系统原理图'


class ReservoirRetirement(unittest.TestCase):
    def test_project_renders_current_reservoir_ports(self):
        with tempfile.TemporaryDirectory(prefix='reservoir-retirement-') as directory:
            work = Path(directory)
            run = subprocess.run([
                sys.executable, str(SCRIPTS / 'validate_driver.py'),
                '--intent', str(PROJECT / '1#系统.intent.yaml'),
                '--catalog', str(PROJECT / 'component-catalog.json'),
                '--layout-seed', str(PROJECT / '1#系统.layout.json'),
                '--workdir', str(work),
            ], capture_output=True, text=True)
            report = json.loads((work / 'convergence-report.json').read_text())
            render = [s for r in report['rounds'] for s in r['stages'] if s['stage'] == 'render']
            self.assertTrue(render and render[-1]['status'] == 'completed', run.stdout + run.stderr)
            svg = ET.parse(work / '1#系统原理图.svg').getroot()
            ports = {e.get('data-port-id'): e for e in svg.iter() if e.get('data-node') == 'TANK-001' and e.get('data-port-id')}
            # The old pressure lead was x=172 after subtracting its viewBox
            # origin. Canonical signed geometry places it at x=155.
            self.assertEqual(float(ports['bootstrap_pressure_in'].get('data-x')), 155)
            self.assertEqual(float(ports['body_sense_tap'].get('data-x')), 50)
            self.assertEqual(float(ports['body_sense_tap'].get('data-y')), 564)
            self.assertTrue((work / 'sheet-readback.png').is_file())
            validation = json.loads((work / 'validation-report.json').read_text())
            self.assertFalse(any(c['result'] == 'fail' and c['id'] in ('V5', 'V8') and 'TANK-001' in c.get('detail', '') for c in validation['checks']))
            # Other baseline geometry and human signoff remain independent.
            self.assertFalse(validation['delivery']['ready'])


if __name__ == '__main__':
    unittest.main()
