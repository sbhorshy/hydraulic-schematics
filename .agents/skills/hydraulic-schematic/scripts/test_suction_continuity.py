"""Suction semantics survive split paths and generic inline symbol roles."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from ruamel.yaml import YAML
from test_entrypoints import make_render_workspace,SKILL
from topology_reconciliation import infer_suction_network

class SuctionContinuityCLI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='suction-chain-');self.addCleanup(self.temp.cleanup)
        self.work=make_render_workspace(Path(self.temp.name),SKILL/'assets/fixtures/l0-small-seed')
        y=YAML();p=self.work/'1#系统.intent.yaml';self.intent=y.load(p)
        self.intent['parts'].update({'PASS-A':'priority_valve','PASS-B':'priority_valve'})
        self.intent['paths']=[['TANK-001.suction_out','PASS-A.inlet'],['PASS-A.outlet','PASS-B.inlet'],
                              ['PASS-B.outlet','EDP-001.suction']]+self.intent['paths'][1:]
        with p.open('w') as f:y.dump(self.intent,f)
        self.catalog=json.loads((self.work/'component-catalog.json').read_text())
        p=self.work/'1#系统.layout.json';l=json.loads(p.read_text())
        l['canvas']['width']=1800;l['drawable']['width']=1770
        l['nodes']['EDP-001']['x']=1000;l['nodes']['PF-001']['x']=1250
        l['externs']['USR-001']['x']=1540
        for name,x in [('PASS-A',400),('PASS-B',650)]:
            l['nodes'][name]={'x':x,'y':502.7778,'w':140,'h':77.7778,'symbol':'symbols/priority-valve.svg'}
            l['labels'][name]=name;l['label_pos'][name]='above'
        p.write_text(json.dumps(l))
        self.svg=self.work/'1#系统原理图.svg'

    def render(self):
        p=subprocess.run([sys.executable,str(self.work/'render_l0_sheet.py'),str(self.work)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def validate(self):
        p=subprocess.run([sys.executable,str(self.work/'validate_sheet.py'),str(self.work)],capture_output=True,text=True,timeout=90)
        self.assertIn(p.returncode,(0,1),p.stdout+p.stderr)
        return json.loads((self.work/'validation-report.json').read_text())

    def test_split_generic_inline_chain_stays_suction_without_changing_catalog(self):
        before=copy.deepcopy(self.catalog);self.render();root=ET.parse(self.svg).getroot()
        for i in range(3):
            lines=[e for e in root.iter() if e.get('data-edge')=='paths[%d][0->1]'%i and e.tag.endswith('polyline')]
            self.assertTrue(lines);self.assertTrue(all(e.get('class')=='ln-suction' for e in lines))
        high=[e for e in root.iter() if e.get('data-edge')=='paths[3][0->1]' and e.tag.endswith('polyline')]
        self.assertTrue(all(e.get('class')=='ln-pressure' for e in high))
        r=self.validate();self.assertFalse([c for c in r['checks'] if c.get('kind','').startswith('suction_')])
        self.assertEqual(self.catalog,before)

    def test_matching_wrong_pipe_and_lead_widths_still_fail_input_semantics(self):
        self.render();root=ET.parse(self.svg).getroot()
        for e in root.iter():
            if e.get('data-edge')=='paths[1][0->1]' and e.tag.endswith('polyline'):e.set('class','ln-pressure')
            if e.get('id') in ('PASS-A__port-lead-outlet','PASS-B__port-lead-inlet'):
                e.set('class',e.get('class','').replace('pl-suction','pl-pressure'))
        ET.register_namespace('','http://www.w3.org/2000/svg');self.svg.write_text(ET.tostring(root,encoding='unicode'))
        r=self.validate();hits=[c for c in r['checks'] if c.get('kind')=='suction_line_class']
        self.assertTrue(hits);self.assertEqual(hits[0]['anchor'],'paths[1][0->1]')
        self.assertTrue([c for c in r['checks'] if c.get('kind')=='suction_line_width'])

    def test_pump_and_pressure_return_user_paths_are_not_transparent(self):
        result=infer_suction_network(self.intent,self.catalog)
        self.assertNotIn('EDP-001.pressure_out',result['ports'])
        self.assertNotIn('paths[3][0->1]',result['anchors'])
        intent=copy.deepcopy(self.intent);intent['parts']['USER-X']='hydraulic_user'
        intent['paths'].append(['EDP-001.pressure_out','USER-X.pressure_in'])
        intent['paths'].append(['USER-X.return_out','TANK-001.return_in'])
        result=infer_suction_network(intent,self.catalog)
        self.assertNotIn('USER-X.return_out',result['ports'])

    def test_contradictory_pressure_source_is_reported_not_silently_reclassified(self):
        intent=copy.deepcopy(self.intent);intent['paths'].append(['EDP-001.pressure_out','PASS-A.inlet'])
        before=copy.deepcopy(intent);r=infer_suction_network(intent,self.catalog)
        self.assertTrue(any(e['endpoint']=='EDP-001.pressure_out' for e in r['errors']))
        self.assertEqual(intent,before)

if __name__=='__main__':unittest.main()
