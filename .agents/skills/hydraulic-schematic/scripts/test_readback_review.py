"""Local readback evidence through real PNG/validator/review CLI boundaries."""
import json
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from PIL import Image

from test_entrypoints import SKILL,make_render_workspace


class ReadbackCLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='readback-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.work=make_render_workspace(Path(self.tmp.name),SKILL/'assets/fixtures/l0-small-seed')
        self.run_cli('render_l0_sheet.py',self.work)
        self.run_cli('rasterize_sheet.py',self.work/'1#系统原理图.svg','-o',self.work/'sheet-readback.png')
        self.run_cli('validate_sheet.py',self.work)

    def run_cli(self,name,*args,expected=0):
        p=subprocess.run([sys.executable,str(SKILL/'scripts'/name),*map(str,args)],capture_output=True,text=True)
        self.assertEqual(p.returncode,expected,p.stdout+p.stderr)
        return p

    def generate(self):
        self.run_cli('readback_review.py','generate',self.work)
        return json.loads((self.work/'readback-manifest.json').read_text())

    def test_verified_png_produces_all_port_crops_without_signing_review(self):
        png=self.work/'sheet-readback.png';before=png.read_bytes();mtime=png.stat().st_mtime_ns
        manifest=self.generate()
        self.assertEqual({o['id'] for o in manifest['objects'] if o['kind']=='port'}, {
            'port:EDP-001.suction','port:EDP-001.pressure_out','port:EDP-001.case_drain','port:EDP-001.drive_shaft',
            'port:PF-001.inlet','port:PF-001.outlet','port:TANK-001.bootstrap_pressure_in',
            'port:TANK-001.suction_out','port:TANK-001.return_in','port:TANK-001.body_sense_tap'})
        self.assertTrue(all(o['review']['status']=='unviewed' for o in manifest['objects']))
        for region in manifest['regions']:
            self.assertTrue((self.work/region['file']).is_file())
        self.assertEqual(png.read_bytes(),before)
        self.assertEqual(png.stat().st_mtime_ns,mtime)
        self.assertEqual(manifest['rasterizations'],0)
        self.assertFalse((self.work/'perceptual-review.json').exists())
        self.assertEqual(json.loads((self.work/'validation-report.json').read_text())['visual_review'],'pending')

    def test_localized_foldback_finding_and_component_overviews_are_covered(self):
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        line=next(e for e in root.iter() if e.get('data-edge')=='paths[1][0->1]')
        line.set('points','620,530 640,530 640,494 640,500 800,500 800,530 820,530')
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.run_cli('rasterize_sheet.py',svg,'-o',self.work/'sheet-readback.png')
        self.run_cli('validate_sheet.py',self.work,expected=1)
        manifest=self.generate()
        finding=next(o for o in manifest['objects'] if o.get('check_id')=='V3' and o.get('finding_kind')=='foldback')
        self.assertEqual(finding['position'],[670,494])
        self.assertIn('component:EDP-001',{o['id'] for o in manifest['objects']})
        region=next(r for r in manifest['regions'] if r['id'] in finding['region_ids'] and r['pixel_box'][0]<=670<r['pixel_box'][2] and r['pixel_box'][1]<=495<r['pixel_box'][3])
        with Image.open(self.work/region['file']) as image:
            x,y=(670-region['pixel_box'][0])*4,(495-region['pixel_box'][1])*4
            self.assertLess(max(image.convert('RGB').getpixel((x,y))),128)

    def test_static_report_links_each_crop_to_its_full_image_roi(self):
        from html.parser import HTMLParser
        manifest=self.generate()
        class Tags(HTMLParser):
            def __init__(self):super().__init__();self.tags=[]
            def handle_starttag(self,tag,attrs):self.tags.append((tag,dict(attrs)))
        parser=Tags();parser.feed((self.work/'readback.html').read_text())
        rects={attrs.get('id'):attrs for tag,attrs in parser.tags if tag=='rect'}
        hrefs={attrs.get('href') for tag,attrs in parser.tags if tag=='a'}
        for region in manifest['regions']:
            key='loc-'+region['id'];self.assertIn(key,rects)
            self.assertIn('#'+key,hrefs)
            rect=rects[key];x,y,right,bottom=region['pixel_box']
            self.assertEqual([float(rect[k]) for k in ('x','y','width','height')],[x,y,right-x,bottom-y])
        self.assertTrue(any(len(r['object_ids'])>1 for r in manifest['regions']))

    def test_explicit_item_review_survives_regeneration_and_revalidation(self):
        first=self.generate();oid='port:PF-001.inlet'
        self.run_cli('readback_review.py','record-item',self.work,oid,'--decision','confirmed','--reviewer','Fixture reviewer','--note','Test-only explicit inspection')
        self.run_cli('validate_sheet.py',self.work)
        again=self.generate()
        self.assertEqual(first['review_binding'],again['review_binding'])
        item=next(o for o in again['objects'] if o['id']==oid)
        self.assertEqual(item['review']['status'],'confirmed')
        self.assertTrue(any(o['review']['status']=='unviewed' for o in again['objects']))
        self.assertFalse((self.work/'perceptual-review.json').exists())

    def test_replaced_crop_invalidates_confirmation_and_blocks_new_signing(self):
        manifest=self.generate();oid='port:PF-001.inlet'
        self.run_cli('readback_review.py','record-item',self.work,oid,'--decision','confirmed','--reviewer','Fixture reviewer','--note','Test-only explicit inspection')
        item=next(o for o in manifest['objects'] if o['id']==oid)
        crop=next(r for r in manifest['regions'] if r['id'] in item['region_ids'])
        path=self.work/crop['file']
        with Image.open(path) as old: Image.new('RGB',old.size,'white').save(path)
        result=self.run_cli('readback_review.py','verify',self.work,expected=1)
        self.assertEqual(json.loads(result.stdout)['review_counts']['confirmed'],0)
        self.run_cli('readback_review.py','record-item',self.work,oid,'--decision','confirmed','--reviewer','Fixture reviewer','--note','Cannot sign altered crop',expected=1)

    def test_whole_sheet_confirmation_does_not_complete_unviewed_local_items(self):
        self.generate()
        self.run_cli('proofreading_evidence.py','record-review',self.work,'--reviewer','Fixture reviewer','--decision','confirmed','--note','Test-only whole sheet review')
        self.run_cli('validate_sheet.py',self.work)
        report=json.loads((self.work/'validation-report.json').read_text())
        self.assertEqual(report['phases']['perceptual']['status'],'confirmed')
        self.assertFalse(report['delivery']['ready'])
        self.assertIn('READBACK_ITEMS',report['delivery']['blocking_checks'])
        self.assertFalse(report['phases']['local_readback']['complete'])

    def test_full_driver_produces_current_unviewed_readback_bundle(self):
        target=Path(self.tmp.name)/'driver'
        self.run_cli('validate_driver.py','--intent',self.work/'1#系统.intent.yaml',
                     '--layout-seed',self.work/'1#系统.layout.json','--workdir',target,'--rounds','1',expected=4)
        self.assertTrue((target/'readback.html').is_file())
        manifest=json.loads((target/'readback-manifest.json').read_text())
        self.assertTrue(all(o['review']['status']=='unviewed' for o in manifest['objects']))
        driver=json.loads((target/'convergence-report.json').read_text())
        self.assertIn('READBACK_ITEMS',driver['delivery']['blocking_checks'])
        self.assertEqual(driver['local_readback']['status'],'current')
        self.run_cli('readback_review.py','verify',target)

    def test_keep_preserves_explicit_version_reviews_and_changed_layout_resets_them(self):
        target=Path(self.tmp.name)/'driver'
        args=['--intent',self.work/'1#系统.intent.yaml','--layout-seed',self.work/'1#系统.layout.json','--workdir',target,'--rounds','1']
        self.run_cli('validate_driver.py',*args,expected=4)
        manifest=json.loads((target/'readback-manifest.json').read_text())
        ids=[o['id'] for o in manifest['objects']]
        self.run_cli('readback_review.py','record-item',target,*ids,'--decision','confirmed','--reviewer','Fixture reviewer','--note','Test-only explicit local inspections')
        self.run_cli('proofreading_evidence.py','record-review',target,'--reviewer','Fixture reviewer','--decision','confirmed','--note','Test-only separate whole-sheet inspection')
        self.run_cli('validate_driver.py',*args,'--keep',expected=0)
        kept=json.loads((target/'readback-manifest.json').read_text())
        self.assertEqual(kept['review_binding'],manifest['review_binding'])
        self.assertTrue(all(o['review']['status']=='confirmed' for o in kept['objects']))
        path=self.work/'1#系统.layout.json';layout=json.loads(path.read_text());layout['nodes']['PF-001']['x']+=10
        path.write_text(json.dumps(layout))
        self.run_cli('validate_driver.py',*args,'--keep',expected=4)
        changed=json.loads((target/'readback-manifest.json').read_text())
        self.assertNotEqual(changed['review_binding'],manifest['review_binding'])
        self.assertTrue(all(o['review']['status']=='unviewed' for o in changed['objects']))

    def test_changed_manifest_is_rejected_without_reusing_confirmed_state(self):
        manifest=self.generate();oid='port:PF-001.inlet'
        self.run_cli('readback_review.py','record-item',self.work,oid,'--decision','confirmed','--reviewer','Fixture reviewer','--note','Test-only explicit inspection')
        path=self.work/'readback-manifest.json';data=json.loads(path.read_text());data['objects'][0]['label']='replaced manifest'
        path.write_text(json.dumps(data))
        result=self.run_cli('readback_review.py','verify',self.work,expected=1)
        self.assertEqual(json.loads(result.stdout)['review_counts']['confirmed'],0)

    def test_questioned_item_remains_independent_and_blocks_delivery(self):
        manifest=self.generate();ids=[o['id'] for o in manifest['objects']]
        self.run_cli('readback_review.py','record-item',self.work,*ids,'--decision','confirmed','--reviewer','Fixture reviewer','--note','Test-only local inspections')
        self.run_cli('readback_review.py','record-item',self.work,'port:PF-001.inlet','--decision','questioned','--reviewer','Fixture reviewer','--note','Test-only concern')
        result=json.loads(self.run_cli('readback_review.py','verify',self.work).stdout)
        self.assertEqual(result['review_status'],'questioned')
        self.assertFalse(result['complete'])
        self.assertIn('READBACK_ITEMS',json.loads((self.work/'validation-report.json').read_text())['delivery']['blocking_checks'])

    def test_priority_width_and_six_pixel_firewall_tail_are_visible_in_bound_crops(self):
        for name in ('1#系统.intent.yaml','1#系统.layout.json'):
            shutil.copy2(SKILL/'assets/fixtures/l0-current'/name,self.work/name)
        self.run_cli('render_l0_sheet.py',self.work)
        svg=self.work/'1#系统原理图.svg';png=self.work/'sheet-readback.png'
        self.run_cli('rasterize_sheet.py',svg,'-o',png)
        with Image.open(png) as image:before=image.convert('L').copy()
        root=ET.parse(svg).getroot()
        valve=next(e for e in root.iter() if e.get('id')=='inst-PRV-001')
        for lead in valve.iter():
            if lead.get('data-interface-port'):lead.attrib.pop('class',None)
        pipe=next(e for e in root.iter() if e.get('data-edge')=='paths[1][1->2]')
        pipe.set('points','506,449 529,449 523,449 523,330 540,330')
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.run_cli('rasterize_sheet.py',svg,'-o',png)
        self.run_cli('validate_sheet.py',self.work,expected=1)
        manifest=self.generate()
        ids={o['id'] for o in manifest['objects']}
        self.assertTrue({'component:PRV-001','port:PRV-001.inlet','component:FSOV-001','port:FSOV-001.main_lower'}<=ids)
        self.assertTrue(any(o['kind']=='intersection' and o.get('position')==[320,686] for o in manifest['objects']))
        def region_for(oid,x,y):
            obj=next(o for o in manifest['objects'] if o['id']==oid)
            return next(r for r in manifest['regions'] if r['id'] in obj['region_ids'] and r['pixel_box'][0]<=x<r['pixel_box'][2] and r['pixel_box'][1]<=y<r['pixel_box'][3])
        valve_region=region_for('port:PRV-001.inlet',1346,317)
        self.assertGreaterEqual(valve_region['pixel_box'][2],1363,'Port crop includes the measured lead/body boundary')
        with Image.open(self.work/valve_region['file']) as image:
            gray=image.convert('L');left,top,_,_=valve_region['pixel_box']
            thin=sum((255-gray.getpixel(((1346-left)*4,y)))/255 for y in range((310-top)*4,(325-top)*4))/4
        normal=sum((255-before.getpixel((1346,y)))/255 for y in range(310,325))
        self.assertLess(thin,normal-1)
        tail=region_for('port:FSOV-001.main_lower',557,449)
        self.assertGreater(before.getpixel((557,449)),240)
        with Image.open(self.work/tail['file']) as image:
            x,y=(557-tail['pixel_box'][0])*4,(449-tail['pixel_box'][1])*4
            self.assertLess(image.convert('L').getpixel((x,y)),128)
        self.assertTrue(any(o.get('check_id')=='V3' and o.get('finding_kind')=='foldback' for o in manifest['objects']))

    def test_driver_with_current_residuals_still_produces_local_review(self):
        target=Path(self.tmp.name)/'residual-driver';fixture=SKILL/'assets/fixtures/l0-current'
        self.run_cli('validate_driver.py','--intent',fixture/'1#系统.intent.yaml','--layout-seed',fixture/'1#系统.layout.json',
                     '--workdir',target,'--rounds','1',expected=1)
        manifest=json.loads((target/'readback-manifest.json').read_text())
        self.assertTrue(any(o['kind']=='finding' for o in manifest['objects']))
        self.assertTrue(all(o['review']['status']=='unviewed' for o in manifest['objects']))
        self.run_cli('readback_review.py','verify',target)

    def test_replaced_source_png_cannot_reuse_existing_local_confirmation(self):
        self.generate();oid='port:PF-001.inlet'
        self.run_cli('readback_review.py','record-item',self.work,oid,'--decision','confirmed','--reviewer','Fixture reviewer','--note','Test-only local inspection')
        path=self.work/'sheet-readback.png'
        with Image.open(path) as old:Image.new('RGB',old.size,'white').save(path)
        result=self.run_cli('readback_review.py','verify',self.work,expected=1)
        self.assertEqual(json.loads(result.stdout)['review_counts']['confirmed'],0)
        self.run_cli('readback_review.py','generate',self.work,expected=1)

    def test_off_sheet_targets_remain_explicitly_unavailable(self):
        svg=self.work/'1#系统原理图.svg';root=ET.parse(svg).getroot()
        node=next(e for e in root.iter() if e.get('id')=='inst-PF-001')
        node.set('transform','translate(3000,0) '+node.get('transform'))
        ET.register_namespace('','http://www.w3.org/2000/svg');svg.write_text(ET.tostring(root,encoding='unicode'))
        self.run_cli('rasterize_sheet.py',svg,'-o',self.work/'sheet-readback.png')
        self.run_cli('validate_sheet.py',self.work,expected=1)
        manifest=self.generate()
        self.assertIn('port:PF-001.inlet',manifest['coverage']['unavailable'])
        obj=next(o for o in manifest['objects'] if o['id']=='port:PF-001.inlet')
        self.assertEqual(obj['region_ids'],[])
        self.assertTrue(obj['unavailable_reason'])
        self.assertFalse(json.loads(self.run_cli('readback_review.py','verify',self.work).stdout)['complete'])


if __name__=='__main__':
    unittest.main()
