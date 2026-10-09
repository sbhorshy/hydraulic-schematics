"""Local readback evidence through real PNG/validator/review CLI boundaries."""
import json
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


if __name__=='__main__':
    unittest.main()
