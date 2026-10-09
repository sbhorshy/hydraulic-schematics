"""Budget behavior through canonical SVG rendering and validator CLI reports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_entrypoints import SKILL, make_render_workspace


class LayoutClearanceCLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='layout-clearance-')
        self.addCleanup(self.tmp.cleanup)
        self.work=make_render_workspace(Path(self.tmp.name),SKILL/'assets/fixtures/l0-small-seed')
        self.svg=self.work/'1#系统原理图.svg'
        self.render()

    def render(self):
        p=subprocess.run([sys.executable,str(SKILL/'scripts/render_l0_sheet.py'),str(self.work)],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)

    def edit(self,change):
        root=ET.parse(self.svg).getroot()
        change(root)
        ET.register_namespace('','http://www.w3.org/2000/svg')
        self.svg.write_text(ET.tostring(root,encoding='unicode'))

    def validate(self):
        p=subprocess.run([sys.executable,str(SKILL/'scripts/validate_sheet.py'),str(self.work)],capture_output=True,text=True)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertEqual(p.returncode,1 if report['fail_count'] else 0,p.stdout+p.stderr)
        return report

    @staticmethod
    def budget(report,bid):
        return next(item for item in report['composition_budget']['items'] if item['id']==bid)

    def test_arbitrary_collinear_svg_split_does_not_change_short_segment_budget(self):
        before=self.budget(self.validate(),'B4')
        self.assertEqual(before['status'],'pass')
        def split(root):
            group=next(e for e in root.iter() if e.get('id')=='lines')
            pipe=next(e for e in group if e.get('data-edge')=='paths[1][0->1]')
            pipe.set('points','621,530 638,530 820,530')
            ET.SubElement(group,'{http://www.w3.org/2000/svg}line',{
                'class':'ln-pressure','stroke':'black','id':'storage-cut','data-edge':'paths[1][0->1]',
                'data-input-anchor':'paths[1][0->1]','x1':'620','y1':'530','x2':'621','y2':'530'})
        self.edit(split)
        after=self.budget(self.validate(),'B4')
        self.assertEqual(after['measured'],before['measured'])
        self.assertEqual(after['status'],'pass')

    def test_component_gap_uses_final_instance_position_and_reports_nearest_pair(self):
        def move(root):
            node=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
            node.set('transform','translate(-175,0) '+node.get('transform'))
        self.edit(move)
        item=self.budget(self.validate(),'B5')
        self.assertAlmostEqual(item['measured'],25)
        self.assertEqual(item['status'],'over')
        self.assertEqual(item['nearest']['components'],['EDP-001','PF-001'])
        self.assertAlmostEqual(item['nearest']['deficit'],15)
        self.assertEqual(item['nearest']['positions'],[[650,490],[675,490]])

    def test_pipe_corridor_reports_actual_gap_and_deficit_as_warning(self):
        def detour(root):
            pipe=next(e for e in root.iter() if e.get('data-edge')=='paths[1][0->1]')
            pipe.set('points','620,530 640,530 640,80 288,80 288,450 800,450 800,530 820,530')
        self.edit(detour)
        report=self.validate()
        item=self.budget(report,'B6')
        self.assertEqual(item['measured']['avoid_corridor'],10)
        nearest=item['nearest_corridor']
        self.assertEqual(nearest['component'],'TANK-001')
        self.assertEqual(nearest['anchor'],'paths[1][0->1]')
        self.assertEqual(nearest['deficit'],2)
        self.assertEqual(nearest['positions'],[[318,120],[308,120]])
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='B6.avoid_corridor'),'warn')
        self.assertTrue(any(c['result']=='warn' and 'B6' in c['detail'] and 'TANK-001' in c['detail'] for c in report['checks']))

    def test_group_padding_is_measured_from_actual_frame_and_member_footprint(self):
        from ruamel.yaml import YAML
        yaml=YAML()
        path=self.work/'1#系统.intent.yaml'
        intent=yaml.load(path.read_text())
        intent['groups']=[{'id':'FILTER','label':'Filter','members':['PF-001'],'reason':'clearance regression'}]
        with path.open('w') as f: yaml.dump(intent,f)
        self.render()
        def narrow(root):
            frame=next(e for e in root.iter() if e.get('class')=='grp')
            frame.set('x','815');frame.set('width','105')
        self.edit(narrow)
        report=self.validate()
        item=self.budget(report,'B6')
        self.assertEqual(item['measured']['group_padding'],5)
        self.assertEqual(item['nearest_group']['group'],'FILTER')
        self.assertEqual(item['nearest_group']['component'],'PF-001')
        self.assertEqual(item['nearest_group']['deficit'],9)
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='B6.group_padding'),'warn')

    def test_unpainted_group_frame_cannot_certify_padding_or_membership(self):
        from ruamel.yaml import YAML
        yaml=YAML();path=self.work/'1#系统.intent.yaml';intent=yaml.load(path)
        intent['groups']=[{'id':'FILTER','label':'Filter','members':['PF-001'],'reason':'actual frame display'}]
        yaml.dump(intent,path)
        self.render()
        original=self.svg.read_text()
        for style in ('stroke:none;fill:none', 'stroke:none;fill:black', 'stroke-opacity:0', 'stroke-width:0',
                      'stroke:rgba(208,0,0,0)'):
            with self.subTest(style=style):
                self.svg.write_text(original.replace('</style>','.grp {'+style+';}</style>'))
                report=self.validate()
                coverage={c['id']:c['status'] for c in report['coverage']}
                self.assertEqual(coverage['V8'],'fail')
                self.assertEqual(coverage['B6.group_padding'],'not_checked')
                self.assertTrue(any(c.get('kind')=='missing_visible_frame' and c.get('group')=='FILTER'
                                    for c in report['checks']))
                self.assertTrue(self.budget(report,'B6')['groups']['unchecked'])

    def test_real_short_bend_and_foldback_remain_short(self):
        for points in ('620,530 640,530 640,536 800,536 800,530 820,530',
                       '620,530 640,530 634,530 634,470 800,470 800,530 820,530'):
            with self.subTest(points=points):
                self.render()
                self.edit(lambda root:next(e for e in root.iter() if e.get('data-edge')=='paths[1][0->1]').set('points',points))
                report=self.validate()
                item=self.budget(report,'B4')
                self.assertEqual(item['measured'],6)
                self.assertEqual(item['status'],'over')
                self.assertTrue(any(c['id']=='V19' and c['result']=='warn' and 'B4' in c['detail'] for c in report['checks']))

    def test_nonsquare_scaled_symbol_90_and_270_use_actual_footprint(self):
        symbol=self.work/'symbols/filter-line-shutoff-stroke.svg'
        symbol.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 20 80 40">
          <g fill="none" stroke="black"><rect x="25" y="30" width="50" height="20"/>
          <line x1="10" y1="40" x2="25" y2="40"/><line x1="75" y1="40" x2="90" y2="40"/></g>
          <g id="connection-points"><circle cx="10" cy="40" data-port-id="inlet" data-anchor-direction="left" data-medium="hydraulic" data-port-role="pressure"/>
          <circle cx="90" cy="40" data-port-id="outlet" data-anchor-direction="right" data-medium="hydraulic" data-port-role="pressure"/></g></svg>''')
        path=self.work/'1#系统.layout.json'
        layout=json.loads(path.read_text())
        for rotation in (90,270):
            with self.subTest(rotation=rotation):
                layout['nodes']['PF-001'].update(x=390,w=160,h=160,rot=rotation)
                path.write_text(json.dumps(layout));self.render()
                report=self.validate()
                item=self.budget(report,'B5')
                self.assertAlmostEqual(item['measured'],70)
                self.assertEqual(item['status'],'pass')
                self.assertEqual(item['nearest']['components'],['EDP-001','PF-001'])

    def test_plain_terminal_departures_have_measured_corridor_coverage(self):
        report=self.validate()
        coverage=next(c for c in report['coverage'] if c['id']=='B6.avoid_corridor')
        self.assertEqual(coverage['status'],'pass')
        item=self.budget(report,'B6')
        self.assertGreaterEqual(item['measured']['avoid_corridor'],12)
        self.assertTrue(item['corridors']['terminal_exemptions'])
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='B6.group_padding'),'not_applicable')

    def test_bridge_arc_clearance_uses_curved_ink_instead_of_chord(self):
        def bridge(root):
            group=next(e for e in root.iter() if e.get('id')=='lines')
            pipe=next(e for e in group if e.get('data-edge')=='paths[1][0->1]')
            pipe.set('points','620,530 735,530')
            ET.SubElement(group,pipe.tag,{**pipe.attrib,'id':'bridge-tail','points':'745,530 820,530'})
            arcs=next(e for e in root.iter() if e.get('id')=='bridges')
            ET.SubElement(arcs,'{http://www.w3.org/2000/svg}path',{'class':'brg-hi','id':'clearance-bridge',
                'd':'M735 530 A5 5 0 0 1 745 530','data-edge':'paths[1][0->1]','data-input-anchor':'paths[1][0->1]'})
            tank=next(e for e in root.iter() if e.get('id')=='inst-TANK-001')
            tank.set('transform','translate(640,-164) '+tank.get('transform'))
        self.edit(bridge)
        report=self.validate()
        item=self.budget(report,'B6')
        self.assertAlmostEqual(item['measured']['avoid_corridor'],5)
        self.assertEqual(item['nearest_corridor']['svg_ids'],['clearance-bridge'])
        self.assertEqual(item['nearest_corridor']['positions'],[[770,525],[770,520]])
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='B6.avoid_corridor'),'warn')

    def test_connected_component_is_not_exempt_after_terminal_run_turns(self):
        self.edit(lambda root:next(e for e in root.iter() if e.get('data-edge')=='paths[1][0->1]').set(
            'points','620,530 621,530 621,450 800,450 800,530 820,530'))
        item=self.budget(self.validate(),'B6')
        self.assertEqual(item['measured']['avoid_corridor'],1)
        self.assertEqual(item['nearest_corridor']['component'],'EDP-001')

    def test_body_crossing_stays_a_failure_in_addition_to_corridor_warning(self):
        self.edit(lambda root:next(e for e in root.iter() if e.get('data-edge')=='paths[1][0->1]').set(
            'points','620,530 640,530 640,510 920,510 920,600 800,600 800,530 820,530'))
        report=self.validate()
        self.assertEqual(self.budget(report,'B6')['measured']['avoid_corridor'],0)
        self.assertTrue(any(c['id']=='V2' and c['result']=='fail' and c.get('obstacle')=='PF-001' for c in report['checks']))

    def test_real_branch_is_a_semantic_end_for_short_segment_budget(self):
        def branch(root):
            group=next(e for e in root.iter() if e.get('id')=='lines')
            ET.SubElement(group,'{http://www.w3.org/2000/svg}polyline',{
                'class':'ln-pressure','points':'625,530 625,600','id':'branch',
                'data-edge':'paths[1][0->1]','data-input-anchor':'paths[1][0->1]'})
        self.edit(branch)
        item=self.budget(self.validate(),'B4')
        self.assertEqual(item['measured'],5)
        self.assertEqual(item['status'],'over')

    def prepare_edge_filter(self):
        symbol=self.work/'symbols/filter-line-shutoff-stroke.svg'
        symbol.write_text('''<svg xmlns="http://www.w3.org/2000/svg" viewBox="10 20 80 40">
          <g fill="none" stroke="black"><rect x="25" y="30" width="50" height="20"/>
          <line x1="10" y1="40" x2="25" y2="40"/><line x1="75" y1="40" x2="90" y2="40"/></g>
          <g id="connection-points"><circle cx="10" cy="40" data-port-id="inlet" data-anchor-direction="left" data-medium="hydraulic" data-port-role="pressure"/>
          <circle cx="90" cy="40" data-port-id="outlet" data-anchor-direction="right" data-medium="hydraulic" data-port-role="pressure"/></g></svg>''')
        path=self.work/'1#系统.layout.json';layout=json.loads(path.read_text())
        layout['nodes']['PF-001'].update(x=1560,y=800,w=160,h=160,rot=90)
        path.write_text(json.dumps(layout));self.render()

    def test_rotated_nonsquare_component_that_fits_canvas_has_no_false_bound_failure(self):
        self.prepare_edge_filter()
        report=self.validate()
        self.assertEqual([round(v,4) for v in report['geometry']['nodes']['PF-001']['footprint']],[1590,800,1670,960])
        self.assertFalse([c for c in report['checks'] if c['id']=='V6'])

    def test_actual_component_canvas_overflow_identifies_component_and_extent(self):
        self.prepare_edge_filter()
        def move(root):
            node=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
            node.set('transform','translate(20,0) '+node.get('transform'))
        self.edit(move)
        failures=[c for c in self.validate()['checks'] if c['id']=='V6']
        finding=next(c for c in failures if c.get('component')=='PF-001')
        self.assertAlmostEqual(finding['overflow']['right'],10)

    def test_moved_actual_legend_frame_occlusion_is_detected(self):
        self.edit(lambda root:next(e for e in root.iter() if e.get('id')=='legend').set('transform','translate(440,-540)'))
        failures=[c for c in self.validate()['checks'] if c['id']=='V7']
        self.assertTrue(any(c.get('component')=='PF-001' and c.get('frame')=='legend' for c in failures),failures)

    def test_expanded_actual_group_frame_catches_foreign_component(self):
        from ruamel.yaml import YAML
        yaml=YAML();path=self.work/'1#系统.intent.yaml';intent=yaml.load(path.read_text())
        intent['groups']=[{'id':'FILTER','label':'Filter','members':['PF-001'],'reason':'frame bounds regression'}]
        with path.open('w') as f: yaml.dump(intent,f)
        self.render()
        def expand(root):
            frame=next(e for e in root.iter() if e.get('class')=='grp')
            frame.set('x','530');frame.set('width','390')
        self.edit(expand)
        failures=[c for c in self.validate()['checks'] if c['id']=='V8']
        self.assertTrue(any(c.get('component')=='EDP-001' and c.get('group')=='FILTER' for c in failures),failures)

    def test_unchecked_frame_clip_is_disclosed_instead_of_certified(self):
        def clip(root):
            defs=ET.SubElement(root,'{http://www.w3.org/2000/svg}defs')
            path=ET.SubElement(defs,'{http://www.w3.org/2000/svg}clipPath',{'id':'frame-clip'})
            ET.SubElement(path,'{http://www.w3.org/2000/svg}rect',{'x':'0','y':'0','width':'100','height':'100'})
            group=next(e for e in root.iter() if e.get('id')=='legend')
            group.set('clip-path','url(#frame-clip)')
        self.edit(clip)
        report=self.validate()
        self.assertEqual(next(c['status'] for c in report['coverage'] if c['id']=='V7'),'not_checked')

    def test_rotated_nonsquare_component_does_not_falsely_overlap_adjacent_legend(self):
        self.prepare_edge_filter()
        path=self.work/'1#系统.layout.json';layout=json.loads(path.read_text())
        layout['nodes']['PF-001'].update(x=820,y=490)
        layout['legend'].update(x=950,y=490)
        path.write_text(json.dumps(layout));self.render()
        self.assertFalse([c for c in self.validate()['checks'] if c['id']=='V7' and
                          (c.get('component')=='PF-001' or '元件 PF-001' in c['detail'])])

    def test_rotated_nonsquare_nonmember_outside_group_has_no_false_overlap(self):
        self.prepare_edge_filter()
        path=self.work/'1#系统.layout.json';layout=json.loads(path.read_text())
        layout['nodes']['PF-001'].update(x=390,y=490)
        path.write_text(json.dumps(layout))
        from ruamel.yaml import YAML
        yaml=YAML();path=self.work/'1#系统.intent.yaml';intent=yaml.load(path.read_text())
        intent['groups']=[{'id':'PUMP','label':'Pump','members':['EDP-001'],'reason':'rotated footprint regression'}]
        with path.open('w') as f: yaml.dump(intent,f)
        self.render()
        self.assertFalse([c for c in self.validate()['checks'] if c['id']=='V8'])


if __name__=='__main__':
    unittest.main()
