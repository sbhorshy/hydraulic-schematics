"""Unconnected-port geometry must be real, not backed only by a red dot."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_entrypoints import make_render_workspace, SKILL

class OrphanPortCLI(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='orphan-interface-');self.addCleanup(self.temp.cleanup)
        self.work=make_render_workspace(Path(self.temp.name),SKILL/'assets/fixtures/l0-small-seed')
        self.symbol=self.work/'symbols/edp-provisional-stroke.svg'

    def run_sheet(self):
        for script in ('render_l0_sheet.py','validate_sheet.py'):
            p=subprocess.run([sys.executable,str(self.work/script),str(self.work)],capture_output=True,text=True,timeout=90)
            self.assertIn(p.returncode,(0,1),p.stdout+p.stderr)
        return json.loads((self.work/'validation-report.json').read_text())

    def failures(self,report,port='drive_shaft'):
        return [c for c in report['checks'] if c['id']=='V16' and c['result']=='fail' and port in c['detail']]

    def test_real_unconnected_lead_and_body_tap_have_evidence(self):
        r=self.run_sheet()
        self.assertEqual(self.failures(r),[])
        self.assertEqual(self.failures(r,'body_sense_tap'),[])
        ev=next(e for e in r['evidence'] if e['id']=='V16')
        self.assertTrue(any(m['component']=='EDP-001' and m['port']=='drive_shaft' and m['connected'] is False for m in ev['measurements']))

    def test_metadata_only_marker_at_empty_corner_fails(self):
        tree=ET.parse(self.symbol)
        next(e for e in tree.getroot().iter() if e.get('data-port-id')=='drive_shaft').set('cx','0')
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        r=self.run_sheet();self.assertTrue(self.failures(r))
        ev=next(e for e in r['evidence'] if e['id']=='V16')
        record=next(e for e in ev['port_presence'] if e['component']=='EDP-001' and e['port']=='drive_shaft')
        self.assertEqual(record['status'],'missing');self.assertIn('position',record)

    def test_hidden_unconnected_lead_is_not_evidence(self):
        tree=ET.parse(self.symbol)
        lead=next(e for e in tree.getroot().iter() if e.tag.endswith('line') and e.get('x1')=='40' and e.get('y2')=='0')
        lead.set('style','stroke-opacity:0')
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        self.assertTrue(self.failures(self.run_sheet()))

    def test_gap_between_unconnected_lead_and_body_fails(self):
        tree=ET.parse(self.symbol)
        lead=next(e for e in tree.getroot().iter() if e.tag.endswith('line') and e.get('x1')=='40' and e.get('y2')=='0')
        lead.set('y1','12')
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        self.assertTrue(self.failures(self.run_sheet()))

    def test_explicit_body_tap_can_touch_a_body_without_external_lead(self):
        symbol=self.work/'symbols/bootstrap-type-reservoir.svg';tree=ET.parse(symbol)
        port=next(e for e in tree.getroot().iter() if e.get('data-port-id')=='body_sense_tap')
        port.set('cx','8');port.set('cy','200')
        tree.write(symbol,encoding='utf-8',xml_declaration=True)
        report=self.run_sheet()
        self.assertEqual(self.failures(report,'body_sense_tap'),[])
        evidence=next(e for e in report['evidence'] if e['id']=='V16')
        record=next(e for e in evidence['port_presence'] if e['port']=='body_sense_tap')
        self.assertEqual(record['status'],'measured')

    def test_unsupported_declared_curve_is_unchecked_not_passed(self):
        tree=ET.parse(self.symbol)
        lead=next(e for e in tree.getroot().iter() if e.tag.endswith('line') and e.get('x1')=='40' and e.get('y2')=='0')
        lead.tag='{http://www.w3.org/2000/svg}path';lead.attrib.clear()
        lead.set('d','M40 0 C40 6 40 12 40 18');lead.set('data-interface-port','drive_shaft')
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        report=self.run_sheet()
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V16'),'not_checked')

    def test_deleted_port_disappears_from_inventory_marker_and_title(self):
        tree=ET.parse(self.symbol)
        for parent in tree.getroot().iter():
            for child in list(parent):
                if child.get('data-port-id')=='drive_shaft':parent.remove(child)
        tree.write(self.symbol,encoding='utf-8',xml_declaration=True)
        path=self.work/'component-catalog.json';catalog=json.loads(path.read_text())
        pump=next(c for c in catalog['components'] if c['component_type']=='engine_driven_pump')
        pump['ports']=[p for p in pump['ports'] if p['id']!='drive_shaft']
        path.write_text(json.dumps(catalog))
        report=self.run_sheet()
        evidence=next(e for e in report['evidence'] if e['id']=='V5')
        self.assertNotIn('EDP-001.drive_shaft',evidence['dangling'])
        root=ET.parse(self.work/'1#系统原理图.svg').getroot()
        self.assertFalse([e for e in root.iter() if e.get('data-port')=='EDP-001.drive_shaft'])
        title=next(e for e in root.iter() if e.get('id')=='title')
        self.assertNotIn('EDP-001.drive_shaft',''.join(title.itertext()))

    def test_clipped_direct_body_tap_is_unchecked_not_counted_as_contact(self):
        symbol=self.work/'symbols/bootstrap-type-reservoir.svg';tree=ET.parse(symbol);root=tree.getroot()
        ns='{http://www.w3.org/2000/svg}'
        defs=ET.SubElement(root,ns+'defs');clip=ET.SubElement(defs,ns+'clipPath',{'id':'body-clip'})
        ET.SubElement(clip,ns+'rect',{'x':'0','y':'0','width':'10','height':'10'})
        next(e for e in root.iter() if e.get('id')=='confirmed-shell').set('clip-path','url(#body-clip)')
        port=next(e for e in root.iter() if e.get('data-port-id')=='body_sense_tap')
        port.set('cx','8');port.set('cy','200')
        tree.write(symbol,encoding='utf-8',xml_declaration=True)
        report=self.run_sheet();evidence=next(e for e in report['evidence'] if e['id']=='V16')
        self.assertTrue(any(e.get('port')=='body_sense_tap' for e in evidence['unchecked']))
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V16'),'not_checked')

if __name__=='__main__':unittest.main()
