"""One browser measurement pass per SVG version, shared by stroke/text checks.

collect(svg_path, output=None, timeout=30) returns root-SVG-coordinate evidence.
The adjacent browser-evidence.json cache is bound to the SVG, this collector and
Chrome version, with an integrity digest. Measurement failure is not_checked.
"""
import base64
import hashlib
from functools import lru_cache
import html
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, unquote
from svg_paint import COLOR_RGBA_JS


def digest(value):
    return hashlib.sha256(value).hexdigest()


@lru_cache(maxsize=1)
def _installed_fonts():
    """Content version of installed fonts, so unchanged SVGs cannot reuse old glyph widths."""
    executable=shutil.which('fc-list')
    if not executable:
        return None
    try:
        files=sorted(set(subprocess.check_output([executable,'--format=%{file}\n'],text=True,timeout=10).splitlines()))
        return digest(json.dumps([(p,digest(Path(p).read_bytes())) for p in files],ensure_ascii=False).encode())
    except (OSError,subprocess.SubprocessError):
        return None


def font_environment(svg_path=None):
    installed=_installed_fonts()
    if not svg_path or not Path(svg_path).is_file(): return installed
    try:
        root=ET.parse(svg_path).getroot()
        styles='\n'.join(e.text or '' for e in root.iter() if e.tag.rsplit('}',1)[-1]=='style')
        resources=[]
        for ref in re.findall(r'url\(\s*["\']?([^\)"\']+)',styles):
            ref=ref.strip()
            if ref.startswith(('#','data:')): continue
            url=urlsplit(ref)
            if url.scheme not in ('','file'): return None
            path=Path(unquote(url.path))
            if not path.is_absolute(): path=Path(svg_path).resolve().parent/path
            resources.append((ref,digest(path.read_bytes()) if path.is_file() else 'missing'))
        return digest(json.dumps([installed,resources],ensure_ascii=False).encode()) if resources else installed
    except (OSError,ET.ParseError): return None


def content_digest(record):
    return digest(json.dumps({k: v for k, v in record.items() if k != 'integrity'},
                             sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())


SCRIPT = r'''
(async () => {
  try {
    __COLOR_RGBA__
    const foreground = (style,kind) => {
      const color=colorRGBA(style[kind]);
      return color && color[3]>0 && !color.slice(0,3).every(v=>v===255) && Number(style[kind+'-opacity'])>0;
    };
    const source = new TextDecoder().decode(Uint8Array.from(atob('__SVG__'), c => c.charCodeAt(0)));
    const parsed = new DOMParser().parseFromString(source, 'image/svg+xml');
    const svg = document.importNode(parsed.documentElement, true);
    document.body.append(svg);
    const vb = svg.viewBox.baseVal;
    svg.style.width = vb.width + 'px'; svg.style.height = vb.height + 'px';
    svg.getBBox(); // Flush layout to start all used font loads before awaiting them.
    await document.fonts.ready;
    const rootInverse = svg.getScreenCTM().inverse();
    const all = [svg, ...svg.querySelectorAll('*')];
    const matrix = m => [m.a,m.b,m.c,m.d,m.e,m.f];
    const xy = (m,x,y) => {const p = new DOMPoint(x,y).matrixTransform(m); return [p.x,p.y];};
    const bounds = (m,b) => {
      const pp = [[b.x,b.y],[b.x+b.width,b.y],[b.x,b.y+b.height],[b.x+b.width,b.y+b.height]].map(p=>xy(m,...p));
      return [Math.min(...pp.map(p=>p[0])),Math.min(...pp.map(p=>p[1])),
              Math.max(...pp.map(p=>p[0])),Math.max(...pp.map(p=>p[1]))];
    };
    const rows = [];
    for (const [index, el] of all.entries()) {
      if (!(el instanceof SVGGraphicsElement)) continue;
      const cs = getComputedStyle(el);
      const ancestors = []; let visible = !['hidden','collapse'].includes(cs.visibility), opacity = 1;
      for (let a=el; a && a instanceof SVGElement; a=a.parentElement) {
        const ac = getComputedStyle(a); opacity *= parseFloat(ac.opacity);
        if(['defs','clipPath','mask','symbol'].includes(a.localName)) visible=false;
        if(ac.display === 'none') visible=false;
        ancestors.push({id:a.id, tag:a.localName, effects:Object.fromEntries(['clip-path','mask','filter'].map(k=>[k,ac.getPropertyValue(k)])), attrs:Object.fromEntries([...a.attributes].map(x=>[x.name,x.value]))});
      }
      const cm = el.getScreenCTM(); if (!cm) continue;
      const m = rootInverse.multiply(cm), bb = el.getBBox(), cb = el.getBoundingClientRect();
      const row = {key:index,id:el.id,tag:el.localName,instance:el.closest('[id^="inst-"]')?.id.slice(5) || null,
        attrs:Object.fromEntries([...el.attributes].map(a=>[a.name,a.value])), ancestors,
        matrix:matrix(m), bbox:bounds(m,bb), local_bbox:[bb.x,bb.y,bb.width,bb.height],
        client_bbox:bounds(rootInverse,cb), visible:visible && opacity>0, opacity,
        style:Object.fromEntries(['stroke','stroke-width','stroke-opacity','stroke-dasharray','stroke-linecap','stroke-linejoin','stroke-miterlimit',
          'fill','fill-opacity','vector-effect','display','visibility','font-family','font-size','font-weight',
          'text-anchor','clip-path','mask','filter'].map(k=>[k,cs.getPropertyValue(k)]))};
      if(el instanceof SVGGeometryElement) {
        row.length=el.getTotalLength();
        row.local_endpoints=[el.getPointAtLength(0),el.getPointAtLength(row.length)].map(p=>[p.x,p.y]);
        row.endpoints=row.local_endpoints.map(p=>xy(m,...p));
        row.tangents=[];
        for(const f of [0.1,0.5,0.9]) {
          const p=el.getPointAtLength(row.length*f), q=el.getPointAtLength(Math.min(row.length,row.length*f+.01));
          row.tangents.push([q.x-p.x,q.y-p.y]);
        }
      }
      if(el instanceof SVGTextContentElement) {
        row.text=el.textContent; row.characters=[]; row.ink_quads=[];
        const count=el.getNumberOfChars();
        for(let i=0;i<count;i++) {
          try {row.characters.push(bounds(m,el.getExtentOfChar(i)));} catch(_) {}
        }
        try {
          const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT), chars=[];
          for(let node=walker.nextNode();node;node=walker.nextNode())
            for(const c of Array.from(node.textContent)) chars.push({c,element:node.parentElement});
          const collapsed=[];
          for(const char of chars) {
            if(/\s/.test(char.c)) {if(collapsed.length && collapsed[collapsed.length-1].c!==' ') collapsed.push({...char,c:' '});}
            else collapsed.push(char);
          }
          if(collapsed[collapsed.length-1]?.c===' ') collapsed.pop();
          const mapped=chars.length===count?chars:collapsed;
          if(mapped.length!==count) throw new Error('SVG character mapping unsupported');
          const ctx=document.createElement('canvas').getContext('2d');
          for(let i=0;i<count;i++) {
            const char=mapped[i], font=getComputedStyle(char.element);
            if(el.hasAttribute('textLength') || char.element.hasAttribute('textLength')) throw new Error('textLength glyph adjustment needs additional ink measurement');
            const nested=rootInverse.multiply(char.element.getScreenCTM());
            if(['a','b','c','d'].some(k=>Math.abs(nested[k]-m[k])>1e-8)) throw new Error('Nested glyph transform requires additional ink measurement');
            if(font.direction==='rtl' || font.writingMode!=='horizontal-tb') throw new Error('Vertical/RTL ink measurement unsupported');
            ctx.font=font.font; ctx.fontKerning=font.fontKerning;
            const metrics=ctx.measureText(char.c), origin=el.getStartPositionOfChar(i);
            if(!Number.isFinite(metrics.actualBoundingBoxAscent)) throw new Error('Actual glyph metrics unavailable');
            if(metrics.actualBoundingBoxLeft+metrics.actualBoundingBoxRight===0 || metrics.actualBoundingBoxAscent+metrics.actualBoundingBoxDescent===0) continue;
            const sw=Number(font.strokeWidth.replace(/^calc\(/,'').replace(/\)$/,'').replace(/px$/,''));
            const strokeColor=colorRGBA(font.stroke);
            if(!strokeColor) throw new Error('Text stroke paint needs additional measurement');
            const pad=strokeColor[3]>0 && Number(font.strokeOpacity)>0?sw/2:0;
            if(!Number.isFinite(pad)) throw new Error('Text stroke width unresolved');
            const x0=-metrics.actualBoundingBoxLeft-pad,y0=-metrics.actualBoundingBoxAscent-pad;
            const x1=metrics.actualBoundingBoxRight+pad,y1=metrics.actualBoundingBoxDescent+pad;
            const gm=m.translate(origin.x,origin.y).rotate(el.getRotationOfChar(i));
            row.ink_quads.push([[x0,y0],[x1,y0],[x1,y1],[x0,y1]].map(p=>xy(gm,...p)));
          }
          const points=row.ink_quads.flat();
          row.ink_bbox=points.length?[Math.min(...points.map(p=>p[0])),Math.min(...points.map(p=>p[1])),
                                     Math.max(...points.map(p=>p[0])),Math.max(...points.map(p=>p[1]))]:null;
          row.ink_status='pass';
        } catch(error) {row.ink_status='not_checked';row.ink_reason=String(error);}
      }
      rows.push(row);
    }
    // Native contours and geometric containment share the text measurement pass.
    const textRows=rows.filter(r=>r.tag==='text' && r.visible && r.ink_status==='pass' && r.ink_bbox);
    for(const row of rows) {
      const el=all[row.key];
      if(!(el instanceof SVGGeometryElement) || !row.visible) continue;
      if(!colorRGBA(row.style.stroke) || !colorRGBA(row.style.fill)) {row.outline_status='not_checked';continue;}
      const stroke=foreground(row.style,'stroke');
      const fill=row.tag!=='line' && foreground(row.style,'fill');
      if(!stroke && !fill) continue;
      const m=new DOMMatrix(row.matrix), factor=Math.hypot(m.a,m.b,m.c,m.d);
      const rectangular=row.tag==='rect' && Math.abs(row.length-2*(row.local_bbox[2]+row.local_bbox[3]))<.001;
      const simple=['line','polyline','polygon'].includes(row.tag) || rectangular;
      row.linear_outline=simple;
      const count=simple?1:Math.max(1,Math.ceil(row.length*factor/.25));
      if(count>100000) {row.outline_status='not_checked';continue;}
      row.outline=[]; row.outline_step=row.length*factor/count;
      for(let i=0;i<=count;i++) {const p=el.getPointAtLength(row.length*i/count);row.outline.push(xy(m,p.x,p.y));}
      row.outline_status='pass'; row.contains_text=[]; row.filled_text_hits=[];row.enclosed_text_hits=[];row.outside_text_points={};row.anchors_inside=[];
      row.closed=['rect','circle','ellipse','polygon'].includes(row.tag) || (row.tag==='path' && /[zZ]/.test(row.attrs.d||''));
      if(!row.closed && !fill) continue;
      const inverse=m.inverse();
      for(const text of textRows) {
        const box=text.ink_bbox;
        if(row.bbox[2]<box[0] || row.bbox[0]>box[2] || row.bbox[3]<box[1] || row.bbox[1]>box[3]) continue;
        const probes=text.ink_quads.flat();
        const hits=probes.map(p=>el.isPointInFill(new DOMPoint(...p).matrixTransform(inverse)));
        if(hits.every(Boolean)) row.contains_text.push(text.key);
        else row.outside_text_points[text.key]=probes.filter((p,i)=>!hits[i]);
        if(fill && hits.some(Boolean)) row.filled_text_hits.push(text.key);
        if(row.closed && hits.some(Boolean)) row.enclosed_text_hits.push(text.key);
        const start=all[text.key].getStartPositionOfChar(0), anchor=xy(new DOMMatrix(text.matrix),start.x,start.y);
        if(el.isPointInFill(new DOMPoint(...anchor).matrixTransform(inverse))) row.anchors_inside.push(text.key);
      }
    }
    // Native hit testing provides independent body contact evidence for lead ends.
    const bodies=rows.filter(r=>r.instance && r.visible && all[r.key] instanceof SVGGeometryElement);
    for(const row of bodies) {
      if(!['line','path','polyline'].includes(row.tag)) continue;
      row.endpoint_contacts=(row.endpoints||[]).map((p, endpointIndex)=>bodies.filter(b=>{
        if(b.key===row.key || b.instance!==row.instance) return false;
        const el=all[b.key], inverse=new DOMMatrix(b.matrix).inverse();
        const probes=[p];
        // A round/square cap is real lead ink beyond the geometric endpoint.
        // Check its extent, rather than treating nearby unrelated ink as contact.
        const width=Number(row.style['stroke-width'].replace(/^calc\(/,'').replace(/\)$/,'').replace(/px$/,''));
        if(['round','square'].includes(row.style['stroke-linecap']) && Number.isFinite(width)) {
          const own=all[row.key], inner=own.getPointAtLength(endpointIndex ? Math.max(0,row.length-.01) : Math.min(.01,row.length));
          const edge=row.local_endpoints[endpointIndex], dx=edge[0]-inner.x, dy=edge[1]-inner.y, n=Math.hypot(dx,dy);
          if(n) probes.push(xy(new DOMMatrix(row.matrix),edge[0]+dx/n*width/2,edge[1]+dy/n*width/2));
        }
        return probes.some(q=>{
          const local=new DOMPoint(...q).matrixTransform(inverse);
          return (foreground(b.style,'stroke') && el.isPointInStroke(local)) ||
            (foreground(b.style,'fill') && el.isPointInFill(local));
        });
      }).map(b=>b.key));
    }
    document.getElementById('evidence').textContent=JSON.stringify({status:'pass',viewbox:[vb.x,vb.y,vb.width,vb.height],elements:rows});
  } catch(error) {document.getElementById('evidence').textContent=JSON.stringify({status:'not_checked',reason:String(error)});}
})();
'''.replace('__COLOR_RGBA__', COLOR_RGBA_JS)


def collect(svg_path, output=None, timeout=30):
    svg_path = Path(svg_path).resolve()
    output = Path(output) if output else svg_path.parent / 'browser-evidence.json'
    started = time.monotonic()
    record = {'schema': 'sheet-browser-v1', 'status': 'not_checked', 'elements': []}
    try:
        source = svg_path.read_bytes()
        viewbox = list(map(float, ET.fromstring(source).get('viewBox', '').replace(',', ' ').split()))
        if len(viewbox) != 4 or not all(math.isfinite(v) for v in viewbox) or min(viewbox[2:]) <= 0:
            raise ValueError('A finite positive SVG viewBox is required for browser measurement')
        viewport = [math.ceil(viewbox[2]), math.ceil(viewbox[3])]
        executable = next((shutil.which(n) for n in ('google-chrome','chromium','chromium-browser','chrome')
                           if shutil.which(n)), None)
        if not executable:
            raise RuntimeError('Chrome unavailable; computed SVG display measurements were not collected')
        version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=10).stdout.strip()
        binding = {'svg_sha256': digest(source), 'collector_sha256': digest(Path(__file__).read_bytes()+COLOR_RGBA_JS.encode()),
                   'font_environment': font_environment(svg_path),
                   'renderer': {'backend': 'chrome', 'version': version}}
        record.update(binding)
        if output.is_file():
            try:
                cached = json.loads(output.read_text(encoding='utf-8'))
                if (binding['font_environment'] is not None and cached.get('status') == 'pass' and all(cached.get(k) == v for k,v in binding.items())
                        and cached.get('integrity') == content_digest(cached)):
                    return cached
            except (ValueError, OSError):
                pass
        with tempfile.TemporaryDirectory(prefix='sheet-measure-') as tmp:
            page = Path(tmp, 'measure.html')
            page.write_text('<!doctype html><meta charset="utf-8"><base href="'+html.escape(svg_path.as_uri(), quote=True)+'"><style>html,body{margin:0;padding:0}</style>'
                            '<pre id="evidence" style="display:none"></pre><script>' +
                            SCRIPT.replace('__SVG__', base64.b64encode(source).decode()) + '</script>', encoding='utf-8')
            command = [executable, '--headless', '--disable-gpu', '--disable-dev-shm-usage',
                       '--no-first-run', '--no-default-browser-check', '--user-data-dir='+str(Path(tmp,'profile')),
                       '--window-size=%d,%d' % tuple(viewport),
                       '--dump-dom', '--virtual-time-budget=3000']
            if hasattr(os, 'geteuid') and os.geteuid() == 0:
                command.append('--no-sandbox')
            proc = subprocess.run(command+[page.as_uri()], capture_output=True, text=True,
                                  encoding='utf-8', errors='replace', timeout=timeout)
            match = re.search(r'<pre id="evidence"[^>]*>(.*?)</pre>', proc.stdout, flags=re.S)
            if proc.returncode or not match or not match.group(1):
                raise RuntimeError('Chrome measurement did not complete: '+proc.stderr[-500:])
            record.update(json.loads(html.unescape(match.group(1))))
        if digest(svg_path.read_bytes()) != binding['svg_sha256']:
            raise RuntimeError('SVG changed during browser measurements')
    except (OSError, RuntimeError, ValueError, ET.ParseError, subprocess.TimeoutExpired) as error:
        record.update(status='not_checked', reason=str(error), elements=[])
    record['elapsed_s'] = round(time.monotonic()-started, 6)
    record['integrity'] = content_digest(record)
    output.write_text(json.dumps(record, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return record


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('svg')
    parser.add_argument('-o','--output')
    args = parser.parse_args()
    result = collect(args.svg, args.output)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
