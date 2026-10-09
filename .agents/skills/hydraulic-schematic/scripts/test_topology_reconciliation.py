"""Topology acceptance through canonical renderer and standalone validator CLIs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import make_render_workspace, SKILL


class TopologyCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='topology-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.work = make_render_workspace(Path(self.tmp.name), SKILL / 'assets/fixtures/l0-small-seed')
        self.svg = self.work / '1#系统原理图.svg'
        self.render()

    def render(self):
        p = subprocess.run([sys.executable, str(SKILL / 'scripts/render_l0_sheet.py'), str(self.work)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def edit(self, mutate):
        root = ET.parse(self.svg).getroot()
        mutate(root)
        ET.register_namespace('', 'http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root, encoding='unicode'))

    def validate(self):
        p = subprocess.run([sys.executable, str(SKILL / 'scripts/validate_sheet.py'), str(self.work)],
                           capture_output=True, text=True)
        report = json.loads((self.work / 'validation-report.json').read_text())
        self.assertEqual(p.returncode, 1 if report['fail_count'] else 0, p.stdout + p.stderr)
        return report

    def test_renderer_emits_input_anchors_and_manifest_without_extra_script(self):
        manifest = self.work / '1#系统原理图-topology.json'
        self.assertTrue(manifest.exists(), 'Canonical rendering must emit the traceability manifest')
        data = json.loads(manifest.read_text())
        self.assertEqual([(e['anchor'], e['endpoints']) for e in data['edges']], [
            ('paths[0][0->1]', ['TANK-001.suction_out', 'EDP-001.suction']),
            ('paths[1][0->1]', ['EDP-001.pressure_out', 'PF-001.inlet']),
            ('paths[1][1->2]', ['PF-001.outlet', 'USR-001'])])
        self.assertEqual(len(data['unknown']), 4)
        root = ET.parse(self.svg).getroot()
        node = next(e for e in root.iter() if e.get('id') == 'inst-EDP-001')
        self.assertEqual(node.get('data-node'), 'EDP-001')
        self.assertEqual(node.get('data-input-anchor'), 'parts.EDP-001')
        for line in root.iter():
            if line.get('class', '').startswith('ln-'):
                self.assertIn(line.get('data-edge'), {e['anchor'] for e in data['edges']})
                self.assertTrue(line.get('id'))
        self.assertTrue((self.work / '1#系统原理图-topology.md').exists())

    def test_deleted_connection_fails_at_its_input_anchor(self):
        def damage(root):
            group = next(e for e in root.iter() if e.get('id') == 'lines')
            group.remove(next(e for e in group if e.get('data-edge') == 'paths[1][0->1]'))
        self.edit(damage)
        report = self.validate()
        findings = [c for c in report['checks'] if c['id'] == 'V10']
        self.assertTrue(any(c.get('kind') == 'missing_connection' and
                            c.get('anchor') == 'paths[1][0->1]' for c in findings), findings)

    def test_series_connections_are_measured_and_coverage_is_complete(self):
        report = self.validate()
        self.assertFalse([c for c in report['checks'] if c['id'] == 'V10'])
        self.assertEqual({tuple(e['endpoints']) for e in report['topology']['actual_edges']}, {
            ('EDP-001.suction', 'TANK-001.suction_out'),
            ('EDP-001.pressure_out', 'PF-001.inlet'),
            ('PF-001.outlet', 'USR-001')})
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id'] == 'V10'), 'pass')

    def test_current_seed_discloses_actual_pressure_case_and_gas_short_circuits(self):
        import shutil
        for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
            shutil.copy2(SKILL / 'assets/fixtures/l0-current' / name, self.work / name)
        self.render()
        report = self.validate()
        joins = [c for c in report['topology']['findings'] if c['kind'] == 'wrong_network_join']
        self.assertTrue(any('@CASE' in c['endpoints'] and '@PRESS' in c['endpoints'] for c in joins))
        self.assertTrue(any('ACV-001.charge_port' in c['endpoints'] and 'ACV-001.accumulator_gas' in c['endpoints'] for c in joins))
        self.assertEqual(len(report['topology']['expected_edges']), 40)
        self.assertTrue(any(e['anchor'] == 'taps[1]' for e in report['topology']['expected_edges']))

    def test_added_connection_cannot_borrow_an_existing_edge_claim(self):
        def damage(root):
            group = next(e for e in root.iter() if e.get('id') == 'lines')
            ET.SubElement(group, '{http://www.w3.org/2000/svg}polyline', {
                'class':'ln-pressure', 'points':'620,530 700,530 700,650 540,650',
                'id':'added-wire', 'data-edge':'paths[1][0->1]',
                'data-input-anchor':'paths[1][0->1]'})
        self.edit(damage)
        findings = [c for c in self.validate()['checks'] if c['id'] == 'V10']
        self.assertTrue(any(c.get('anchor') == 'paths[1][0->1]' for c in findings), findings)

    def test_target_ports_swapped_with_same_edge_count_and_claims_fail(self):
        def damage(root):
            a = next(e for e in root.iter() if e.get('data-edge') == 'paths[1][0->1]')
            b = next(e for e in root.iter() if e.get('data-edge') == 'paths[1][1->2]')
            # EDP now bypasses PF and feeds the external user; PF loops onto itself.
            a.set('points', '620,530 620,450 1120,450 1120,530')
            b.set('points', '900,530 920,530 920,600 800,600 800,530 820,530')
        self.edit(damage)
        findings = [c for c in self.validate()['checks'] if c['id'] == 'V10']
        self.assertEqual({c['anchor'] for c in findings if c.get('kind') == 'additional_or_wrong_connection'},
                         {'paths[1][0->1]', 'paths[1][1->2]'})

    def test_missing_port_anchor_is_a_topology_traceability_failure(self):
        def damage(root):
            node=next(e for e in root.iter() if e.get('id')=='inst-EDP-001')
            node.remove(next(e for e in node if e.get('data-port')=='EDP-001.pressure_out'))
        self.edit(damage)
        findings=[c for c in self.validate()['checks'] if c['id']=='V10']
        self.assertTrue(any(c.get('kind')=='port_anchor' and c.get('port')=='pressure_out' for c in findings), findings)

    def test_contiguous_split_and_bridge_fragments_remain_one_connection(self):
        def split(root):
            group=next(e for e in root.iter() if e.get('id')=='lines')
            line=next(e for e in group if e.get('data-edge')=='paths[1][0->1]')
            line.set('points','620,530 735,530')
            ET.SubElement(group,line.tag,{**line.attrib,'id':'wire-split','points':'745,530 820,530'})
            bridges=next(e for e in root.iter() if e.get('id')=='bridges')
            ET.SubElement(bridges,'{http://www.w3.org/2000/svg}path',{
                'id':'test-bridge','class':'brg-hi','d':'M735 530 A5 5 0 0 1 745 530',
                'data-edge':'paths[1][0->1]','data-input-anchor':'paths[1][0->1]'})
        self.edit(split)
        report=self.validate()
        self.assertFalse([c for c in report['checks'] if c['id']=='V10'])
        self.assertEqual(len(report['topology']['actual_edges']),3)

    def test_unknowns_are_disclosed_and_never_generate_edges(self):
        report=self.validate()
        self.assertEqual(len(report['topology']['unknown']),4)
        self.assertEqual(len(report['topology']['expected_edges']),3)
        self.assertEqual(len(report['topology']['actual_edges']),3)

    def render_connected_current(self):
        import shutil
        for name in ('1#系统.intent.yaml', '1#系统.layout.json'):
            shutil.copy2(SKILL / 'assets/fixtures/l0-current' / name, self.work / name)
        path=self.work/'1#系统.layout.json'
        layout=json.loads(path.read_text())
        # A local positive drawing: move case trunk off pressure terminals and
        # orient the charging valve to prevent the retained gas-side foldback.
        layout['buses']['CASE']['x']=700
        layout['nodes']['ACV-001']['rot']=180
        path.write_text(json.dumps(layout))
        self.render()

    def test_two_pumps_shared_suction_buses_branches_and_gas_taps(self):
        self.render_connected_current()
        report=self.validate()
        self.assertFalse([c for c in report['checks'] if c['id']=='V10'])
        self.assertEqual(len(report['topology']['expected_edges']),40)
        self.assertEqual(len(report['topology']['actual_edges']),40)
        self.assertTrue(report['topology']['bridges'])

    def test_branch_moved_to_wrong_bus_fails_at_its_input_anchor(self):
        self.render_connected_current()
        def damage(root):
            for group in root.iter():
                for el in list(group):
                    if el.get('data-edge')=='paths[2][0->1]': group.remove(el)
            group=next(e for e in root.iter() if e.get('id')=='lines')
            ET.SubElement(group,'{http://www.w3.org/2000/svg}polyline',{
                'class':'ln-pressure','points':'620,330 700,330','id':'wrong-bus-branch',
                'data-edge':'paths[2][0->1]','data-input-anchor':'paths[2][0->1]'})
        self.edit(damage)
        failures=[c for c in self.validate()['checks'] if c['id']=='V10']
        finding=next(c for c in failures if c.get('kind')=='additional_or_wrong_connection' and c.get('anchor')=='paths[2][0->1]')
        self.assertEqual(finding['actual_endpoints'],['@CASE','EDP-001.pressure_out'])

    def test_css_hidden_line_is_missing_even_though_geometry_and_claim_remain(self):
        def damage(root):
            style=next(e for e in root.iter() if e.tag.endswith('style'))
            style.text += '\n#lines [data-edge="paths[1][0->1]"] { display: none !important; }'
        self.edit(damage)
        findings=[c for c in self.validate()['checks'] if c['id']=='V10']
        self.assertTrue(any(c.get('kind')=='missing_connection' and c.get('anchor')=='paths[1][0->1]' for c in findings),findings)

    def test_unclassified_extra_visible_wire_cannot_escape_topology(self):
        def damage(root):
            group=next(e for e in root.iter() if e.get('id')=='lines')
            ET.SubElement(group,'{http://www.w3.org/2000/svg}line',{
                'id':'unclaimed','x1':'620','y1':'530','x2':'1120','y2':'530',
                'stroke':'black','stroke-width':'3.6'})
        self.edit(damage)
        failures=[c for c in self.validate()['checks'] if c['id']=='V10']
        self.assertTrue(any(c.get('svg_id')=='unclaimed' for c in failures),failures)

    def test_hidden_component_cannot_supply_a_visible_terminal(self):
        def damage(root):
            node=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
            node.set('style','visibility:hidden')
        self.edit(damage)
        failures=[c for c in self.validate()['checks'] if c['id']=='V10']
        self.assertTrue(any(c.get('kind')=='hidden_node' and c.get('component')=='PF-001' for c in failures),failures)

    def test_driver_and_standalone_report_same_measured_topology(self):
        output=Path(self.tmp.name)/'driver'
        result=subprocess.run([sys.executable,str(SKILL/'scripts/validate_driver.py'),
            '--intent',str(self.work/'1#系统.intent.yaml'),
            '--layout-seed',str(self.work/'1#系统.layout.json'),
            '--workdir',str(output),'--rounds','1'],capture_output=True,text=True)
        self.assertEqual(result.returncode,4,result.stdout+result.stderr)
        driver=json.loads((output/'validation-report.json').read_text())
        self.assertEqual(next(c['status'] for c in driver['coverage'] if c['id']=='V10'),'pass')
        self.work=output
        standalone=self.validate()
        self.assertEqual(driver['topology'],standalone['topology'])
        self.assertTrue((output/'1#系统原理图-topology.json').exists())

    def test_missing_browser_measurement_never_claims_visible_graph_pass(self):
        import os
        result=subprocess.run([sys.executable,str(SKILL/'scripts/validate_sheet.py'),str(self.work)],
                              capture_output=True,text=True,env={**os.environ,'PATH':'/nonexistent'})
        report=json.loads((self.work/'validation-report.json').read_text())
        coverage=next(c for c in report['coverage'] if c['id']=='V10')
        self.assertEqual(coverage['status'],'not_checked',result.stdout+result.stderr)
        self.assertIn('Display/geometry reconciliation incomplete',coverage['detail'])


if __name__ == '__main__':
    unittest.main()
