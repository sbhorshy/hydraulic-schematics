"""Junction/crossing acceptance at renderer and validator CLI output seams."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import SKILL, make_render_workspace


class JunctionCLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='junction-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.work=make_render_workspace(Path(self.tmp.name),SKILL/'assets/fixtures/l0-small-seed')
        self.svg=self.work/'1#系统原理图.svg'
        self.render()

    def render(self):
        p=subprocess.run([sys.executable,str(SKILL/'scripts/render_l0_sheet.py'),str(self.work)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def edit(self,change):
        root=ET.parse(self.svg).getroot();change(root)
        ET.register_namespace('','http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root,encoding='unicode'))

    def validate(self):
        p=subprocess.run([sys.executable,str(SKILL/'scripts/validate_sheet.py'),str(self.work)],capture_output=True,text=True)
        self.assertTrue((self.work/'validation-report.json').exists(),p.stdout+p.stderr)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertEqual(p.returncode,1 if report['fail_count'] else 0,p.stdout+p.stderr)
        return report

    def current(self):
        for name in ('1#系统.intent.yaml','1#系统.layout.json'):
            shutil.copy2(SKILL/'assets/fixtures/l0-current'/name,self.work/name)
        self.render()

    def test_renderer_marks_shared_suction_fork_away_from_bus(self):
        self.current()
        root=ET.parse(self.svg).getroot()
        dots=[e for g in root.iter() if g.get('id')=='junctions' for e in g
              if e.get('class')=='jn' and abs(float(e.get('cx'))-320)<.1 and abs(float(e.get('cy'))-686)<.1]
        self.assertEqual(len(dots),1,'The actual suction fork at root(320,686) needs one junction dot')
        self.assertIn('paths[0][0->1]',dots[0].get('data-edges',''))
        self.assertIn('paths[1][0->1]',dots[0].get('data-edges',''))

    def test_missing_suction_fork_dot_fails_at_both_input_connections(self):
        self.current()
        def erase(root):
            group=next(e for e in root.iter() if e.get('id')=='junctions')
            group.remove(next(e for e in group if abs(float(e.get('cx'))-320)<.1 and abs(float(e.get('cy'))-686)<.1))
        self.edit(erase)
        findings=[c for c in self.validate()['checks'] if c['id']=='V4' and c['result']=='fail']
        finding=next(c for c in findings if c.get('kind')=='missing_junction' and c.get('position')==[320.0,686.0])
        self.assertEqual(finding['input_anchors'],['paths[0][0->1]','paths[1][0->1]'])

    # Injections retain their original final/root positions after removal of the sheet x transform.
    def crossing(self, bridge=True):
        def edit(root):
            suction=next(e for e in root.iter() if e.get('data-edge')=='paths[0][0->1]')
            suction.set('points','308,530 328,530 328,450 770,450 770,610 550,610 550,530 570,530')
            if bridge:
                group=next(e for e in root.iter() if e.get('id')=='lines')
                pressure=next(e for e in group if e.get('data-edge')=='paths[1][0->1]')
                pressure.set('points','650,530 765,530')
                ET.SubElement(group,pressure.tag,{**pressure.attrib,'id':'pressure-tail','points':'775,530 850,530'})
                arcs=next(e for e in root.iter() if e.get('id')=='bridges')
                ET.SubElement(arcs,'{http://www.w3.org/2000/svg}path',{
                    'class':'brg-hi','id':'cross-bridge','d':'M765 530 A5 5 0 0 1 775 530',
                    'data-edge':'paths[1][0->1]','data-input-anchor':'paths[1][0->1]'})
        self.edit(edit)

    def test_true_unconnected_crossing_with_continuous_bridge_passes(self):
        self.crossing()
        report=self.validate()
        self.assertFalse([c for c in report['checks'] if c['id'] in ('V4','V14')])
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V14'),'pass')
        events=next(e['events'] for e in report['evidence'] if e['id']=='V14')
        crossing=next(e for e in events if e['kind']=='crossing')
        self.assertEqual(crossing['position'],[770,530])
        self.assertEqual(crossing['input_anchors'],['paths[0][0->1]','paths[1][0->1]'])

    def test_false_dot_cannot_legalize_unbridged_crossing(self):
        self.crossing(False)
        def dot(root):
            group=next(e for e in root.iter() if e.get('id')=='junctions')
            ET.SubElement(group,'{http://www.w3.org/2000/svg}circle',{'class':'jn','cx':'770','cy':'530','r':'3','data-edges':'paths[1][0->1]','data-network':'pressure'})
        self.edit(dot)
        findings=[c for c in self.validate()['checks'] if c['id'] in ('V4','V14')]
        self.assertTrue(any(c.get('kind')=='false_junction' and c.get('position')==[770,530] for c in findings),findings)
        self.assertTrue(any(c.get('kind')=='missing_bridge' for c in findings),findings)

    def test_legend_and_internal_symbol_example_dots_are_excluded(self):
        def dot(root):
            group=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
            ET.SubElement(group,'{http://www.w3.org/2000/svg}circle',{'class':'jn','cx':'40','cy':'40','r':'3'})
        self.edit(dot)
        report=self.validate()
        self.assertFalse([c for c in report['checks'] if c['id']=='V4'])
        self.assertEqual(next(e['junctions'] for e in report['evidence'] if e['id']=='V4'),0)

    def test_deleted_bridge_is_detected_even_though_crossing_has_a_gap(self):
        self.crossing()
        def erase(root):
            group=next(e for e in root.iter() if e.get('id')=='bridges')
            group.remove(next(e for e in group if e.get('id')=='cross-bridge'))
        self.edit(erase)
        findings=[c for c in self.validate()['checks'] if c['id']=='V14']
        self.assertTrue(any(c.get('kind')=='missing_bridge' and c.get('position')==[770,530] for c in findings),findings)

    def test_offset_bridge_fails_actual_center_and_continuity(self):
        self.crossing()
        self.edit(lambda root:next(e for e in root.iter() if e.get('id')=='cross-bridge').set('d','M767 530 A5 5 0 0 1 777 530'))
        findings=[c for c in self.validate()['checks'] if c['id']=='V14']
        self.assertTrue(any(c.get('kind')=='bridge_gap' for c in findings),findings)
        self.assertTrue(any(c.get('kind')=='missing_bridge' and c.get('position')==[770,530] for c in findings),findings)

    def test_wrong_corner_dot_and_offset_dot_are_rejected(self):
        self.crossing()
        def dot(root):
            group=next(e for e in root.iter() if e.get('id')=='junctions')
            ET.SubElement(group,'{http://www.w3.org/2000/svg}circle',{'class':'jn','cx':'328','cy':'450','r':'3'})
        self.edit(dot)
        findings=[c for c in self.validate()['checks'] if c['id']=='V4']
        self.assertTrue(any(c.get('kind')=='unexpected_junction' and c.get('position')==[328,450] for c in findings),findings)
        self.current()
        def offset(root):
            group=next(e for e in root.iter() if e.get('id')=='junctions')
            dot=next(e for e in group if abs(float(e.get('cx'))-320)<.1 and abs(float(e.get('cy'))-686)<.1)
            dot.set('cx','323')
        self.edit(offset)
        findings=[c for c in self.validate()['checks'] if c['id']=='V4']
        self.assertTrue(any(c.get('kind')=='missing_junction' and c.get('position')==[320,686] for c in findings),findings)
        self.assertTrue(any(c.get('kind')=='unexpected_junction' and c.get('position')==[323,686] for c in findings),findings)

    def test_outline_only_transparent_and_css_hidden_fork_dots_are_missing(self):
        for style in ('fill:none;stroke:black;stroke-width:2','fill-opacity:0','opacity:0'):
            with self.subTest(style=style):
                self.current()
                def hide(root):
                    group=next(e for e in root.iter() if e.get('id')=='junctions')
                    dot=next(e for e in group if abs(float(e.get('cx'))-320)<.1 and abs(float(e.get('cy'))-686)<.1)
                    style_node=next(e for e in root.iter() if e.tag.endswith('style'))
                    style_node.text += '\n#'+dot.get('id')+' {'+style+';}'
                self.edit(hide)
                findings=[c for c in self.validate()['checks'] if c['id']=='V4']
                self.assertTrue(any(c.get('kind')=='missing_junction' and c.get('position')==[320,686] for c in findings),findings)

    def test_correct_branches_buses_and_bridges_have_complete_coverage(self):
        self.current()
        path=self.work/'1#系统.layout.json';layout=json.loads(path.read_text())
        layout['buses']['CASE']['x']=730;layout['nodes']['ACV-001']['rot']=180
        path.write_text(json.dumps(layout));self.render()
        report=self.validate()
        self.assertFalse([c for c in report['checks'] if c['id'] in ('V4','V10','V14')])
        self.assertEqual({c['id']:c['status'] for c in report['coverage'] if c['id'] in ('V4','V14')},{'V4':'pass','V14':'pass'})

    def test_straight_baseline_under_bridge_is_not_an_unconnected_crossing(self):
        self.crossing()
        def unsplit(root):
            group=next(e for e in root.iter() if e.get('id')=='lines')
            group.remove(next(e for e in group if e.get('id')=='pressure-tail'))
            next(e for e in group if e.get('data-edge')=='paths[1][0->1]').set('points','650,530 850,530')
        self.edit(unsplit)
        findings=[c for c in self.validate()['checks'] if c['id']=='V14']
        self.assertTrue(any(c.get('kind')=='bridge_not_split' for c in findings),findings)

    def test_bridge_may_not_cut_a_genuine_shared_trunk_branch(self):
        self.current()
        def bridge(root):
            group=next(e for e in root.iter() if e.get('id')=='lines')
            trunk=next(e for e in group if e.get('data-edge')=='paths[0][0->1]')
            tail=trunk.get('points').split()[1:]
            trunk.set('points','308,686 315,686')
            ET.SubElement(group,trunk.tag,{**trunk.attrib,'id':'fork-tail','points':'325,686 '+' '.join(tail)})
            arcs=next(e for e in root.iter() if e.get('id')=='bridges')
            ET.SubElement(arcs,'{http://www.w3.org/2000/svg}path',{
                'class':'brg-lo','id':'fork-bridge','d':'M315 686 A5 5 0 0 1 325 686',
                'data-edge':'paths[0][0->1]','data-input-anchor':'paths[0][0->1]'})
        self.edit(bridge)
        findings=[c for c in self.validate()['checks'] if c['id']=='V14']
        self.assertTrue(any(c.get('kind')=='bridge_breaks_connection' and c.get('position')==[320,686] for c in findings),findings)

    def test_inherited_marker_clip_is_explicitly_not_checked(self):
        self.current()
        def clip(root):
            defs=ET.SubElement(root,'{http://www.w3.org/2000/svg}defs')
            path=ET.SubElement(defs,'{http://www.w3.org/2000/svg}clipPath',{'id':'dot-clip'})
            ET.SubElement(path,'{http://www.w3.org/2000/svg}rect',{'x':'0','y':'0','width':'100','height':'100'})
            group=next(e for e in root.iter() if e.get('id')=='junctions');group.set('class','clipped-dots')
            style=next(e for e in root.iter() if e.tag.endswith('style'));style.text+='\n.clipped-dots{clip-path:url(#dot-clip)}'
        self.edit(clip)
        report=self.validate()
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V4'),'not_checked')

    def test_hidden_junction_ancestor_does_not_count_as_painted_marker(self):
        self.current()
        self.edit(lambda root:next(e for e in root.iter() if e.get('id')=='junctions').set('style','opacity:0'))
        findings=[c for c in self.validate()['checks'] if c['id']=='V4']
        self.assertTrue(any(c.get('kind')=='missing_junction' and c.get('position')==[320,686] for c in findings),findings)

    def test_bridge_claim_cannot_change_its_actual_pipe_owner(self):
        self.crossing()
        def change(root):
            arc=next(e for e in root.iter() if e.get('id')=='cross-bridge')
            arc.set('data-edge','paths[0][0->1]');arc.set('data-input-anchor','paths[0][0->1]')
        self.edit(change)
        findings=[c for c in self.validate()['checks'] if c['id']=='V14']
        self.assertTrue(any(c.get('kind')=='bridge_gap' for c in findings),findings)

    def test_real_four_way_junction_is_a_semantic_topology_vertex(self):
        from ruamel.yaml import YAML
        yaml=YAML();path=self.work/'1#系统.intent.yaml';intent=yaml.load(path.read_text())
        intent['extern']={'S':'inlet','A':'outlet','B':'outlet'}
        intent['paths']=[['S','A'],['S','B']]
        with path.open('w') as f:yaml.dump(intent,f)
        path=self.work/'1#系统.layout.json';layout=json.loads(path.read_text())
        layout['externs']={name:{'x':x,'y':y,'anchor':anchor,'label':name} for name,x,y,anchor in
                           [('S',530,800,'right'),('A',1130,800,'left'),('B',930,900,'left')]}
        path.write_text(json.dumps(layout));self.render()
        def cross(root):
            lines=next(e for e in root.iter() if e.get('id')=='lines')
            next(e for e in lines if e.get('data-edge')=='paths[0][0->1]').set('points','530,800 1130,800')
            next(e for e in lines if e.get('data-edge')=='paths[1][0->1]').set('points','530,800 550,800 550,700 830,700 830,900 930,900')
            dots=next(e for e in root.iter() if e.get('id')=='junctions')
            dots.clear();dots.set('id','junctions')
            for x,y in [(550,800),(830,800)]:
                ET.SubElement(dots,'{http://www.w3.org/2000/svg}circle',{'class':'jn','cx':str(x),'cy':str(y),'r':'3'})
        self.edit(cross)
        report=self.validate()
        crossing=next(v for v in report['topology']['vertices'] if v['position']==[830,800])
        self.assertEqual(crossing['degree'],4)
        self.assertFalse([c for c in report['checks'] if c['id'] in ('V4','V10','V14')])
        runs=next(item['runs'] for item in report['composition_budget']['items'] if item['id']=='B4')
        self.assertTrue(any(run['start']==[830,800] or run['end']==[830,800] for run in runs))

    def test_unpainted_bridge_cannot_supply_continuity(self):
        self.crossing()
        self.edit(lambda root:next(e for e in root.iter() if e.get('id')=='cross-bridge').set('style','stroke:rgba(255,255,255,0.5)'))
        findings=[c for c in self.validate()['checks'] if c['id']=='V14']
        self.assertTrue(any(c.get('kind')=='missing_bridge' for c in findings),findings)

    def test_missing_bridge_claim_reports_failure_without_crashing(self):
        self.crossing()
        def remove(root):
            arc=next(e for e in root.iter() if e.get('id')=='cross-bridge')
            del arc.attrib['data-edge']
        self.edit(remove)
        findings=[c for c in self.validate()['checks'] if c['id']=='V14']
        self.assertTrue(any(c.get('kind')=='bridge_gap' for c in findings),findings)

    def test_correct_bridge_does_not_exempt_existing_zero_crossing_budget(self):
        self.crossing()
        report=self.validate()
        self.assertFalse([c for c in report['checks'] if c['id']=='V14'])
        budget=next(item for item in report['composition_budget']['items'] if item['id']=='B1')
        self.assertEqual(budget['measured'],1)
        self.assertEqual(budget['status'],'fail')

    def test_optimizer_cli_b1_matches_final_bridged_crossing_budget(self):
        self.current()
        self.assertFalse((self.work/'browser-evidence.json').exists())
        result=subprocess.run([sys.executable,str(SKILL/'scripts/proto_optimize.py'),
            str(self.work/'1#系统.layout.json'),'--intent',str(self.work/'1#系统.intent.yaml'),
            '--catalog',str(self.work/'component-catalog.json'),'--max-evals','1','--max-steps','0',
            '-o',str(self.work/'candidate')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertFalse((self.work/'browser-evidence.json').exists(),'Candidate B1 needs no browser measurements')
        candidate=json.loads((self.work/'candidate-opt-log.json').read_text())
        self.assertEqual(candidate['seed_bp']['b1'],1)
        report=self.validate()
        budget=next(item for item in report['composition_budget']['items'] if item['id']=='B1')
        self.assertEqual(candidate['seed_bp']['b1'],budget['measured'])
        self.assertEqual(candidate['final_bp']['b1'],budget['measured'])


if __name__=='__main__':
    unittest.main()
