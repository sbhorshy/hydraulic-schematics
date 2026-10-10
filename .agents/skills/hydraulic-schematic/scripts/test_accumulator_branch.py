"""Signed accumulator connections survive the public project drawing pipeline."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parent
PROJECT=SCRIPTS.parents[3]/'1#系统原理图'


class AccumulatorBranch(unittest.TestCase):
    def test_signed_connections_and_their_visible_geometry(self):
        with tempfile.TemporaryDirectory(prefix='accumulator-branch-') as directory:
            work=Path(directory)
            result=subprocess.run([sys.executable,str(SCRIPTS/'validate_driver.py'),
                '--intent',str(PROJECT/'1#系统.intent.yaml'),
                '--catalog',str(PROJECT/'component-catalog.json'),
                '--layout-seed',str(PROJECT/'1#系统.layout.json'),
                '--workdir',str(work)],capture_output=True,text=True)
            report=json.loads((work/'validation-report.json').read_text())
            edges=report['topology']['expected_edges']
            expected=[{'PRV-002.outlet','ACC-001.hydraulic_port'},
                      {'ACC-001.gas_port','PG-001.pressure_sense'},
                      {'PG-001.pressure_sense','ACV-001.accumulator_gas'}]
            anchors=set()
            for endpoints in expected:
                match=[edge for edge in edges if set(edge['endpoints'])==endpoints]
                self.assertEqual(len(match),1,(endpoints,edges))
                anchors.add(match[0]['anchor'])
            related=[]
            for check in report['checks']:
                if check['result']!='fail':continue
                if (check.get('anchor') in anchors or anchors.intersection(check.get('input_anchors',[]))
                    or check.get('component') in {'ACC-001','PG-001','ACV-001'}):
                    related.append(check)
            self.assertEqual(related,[],result.stdout+result.stderr)
            # The six unaffected CASE/PRESS/B1 baseline failures may remain;
            # moving the branch must not introduce body/text/bridge failures.
            self.assertLessEqual(report['fail_count'], 6, report['checks'])
            baseline=json.loads((PROJECT.parent/'research/ready-work-20261009/reservoir-49/project-result.json').read_text())['checks']
            def signature(check):
                keys=('id','kind','component','port','anchor','input_anchors','obstacle',
                      'expected_endpoints','actual_endpoints','networks','text')
                fields={k:check[k] for k in keys if k in check}
                if not check.get('kind'):fields['detail']=check['detail']
                return json.dumps(fields,sort_keys=True)
            added=Counter(signature(c) for c in report['checks'] if c['result']=='fail')-Counter(map(signature,baseline))
            self.assertEqual(added,Counter(),report['checks'])
            b1=next(b for b in report['composition_budget']['items'] if b['id']=='B1')
            self.assertLessEqual(b1['measured'], 1, b1)
            names={'ACC-001','系统蓄压器','PG-001','充气压力表','ACV-001','充气活门'}
            self.assertEqual([c for c in report['checks'] if c.get('text') in names
                              and c.get('kind') in ('text_overlap','text_clearance')],[],report['checks'])
            self.assertTrue((work/'sheet-readback.png').is_file())
            # Pressure gauge retains its one physical port.
            self.assertEqual(set(report['geometry']['nodes']['PG-001']['ports']),{'pressure_sense'})
            self.assertFalse(report['delivery']['ready'])


if __name__=='__main__':unittest.main()
