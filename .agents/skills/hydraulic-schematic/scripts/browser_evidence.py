"""One browser measurement pass per SVG version, shared by stroke/text checks.

collect(svg_path, output=None, timeout=30) returns root-SVG-coordinate evidence.
The adjacent browser-evidence.json cache is bound to the SVG, this collector and
Chrome version, with an integrity digest. Measurement failure is not_checked.
"""
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time


def digest(value):
    return hashlib.sha256(value).hexdigest()


def content_digest(record):
    return digest(json.dumps({k: v for k, v in record.items() if k != 'integrity'},
                             sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())


SCRIPT = r'''
(async () => {
  try {
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
        style:Object.fromEntries(['stroke','stroke-width','stroke-opacity','stroke-dasharray','stroke-linecap',
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
        row.text=el.textContent; row.characters=[];
        for(let i=0;i<el.getNumberOfChars();i++) {
          try {row.characters.push(bounds(m,el.getExtentOfChar(i)));} catch(_) {}
        }
      }
      rows.push(row);
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
          return (b.style.stroke !== 'none' && !['rgb(255, 255, 255)','rgba(0, 0, 0, 0)'].includes(b.style.stroke) && el.isPointInStroke(local)) ||
            (b.style.fill !== 'none' && !['rgb(255, 255, 255)','rgba(0, 0, 0, 0)'].includes(b.style.fill) && el.isPointInFill(local));
        });
      }).map(b=>b.key));
    }
    document.getElementById('evidence').textContent=JSON.stringify({status:'pass',viewbox:[vb.x,vb.y,vb.width,vb.height],elements:rows});
  } catch(error) {document.getElementById('evidence').textContent=JSON.stringify({status:'not_checked',reason:String(error)});}
})();
'''


def collect(svg_path, output=None, timeout=30):
    svg_path = Path(svg_path).resolve()
    output = Path(output) if output else svg_path.parent / 'browser-evidence.json'
    started = time.monotonic()
    record = {'schema': 'sheet-browser-v1', 'status': 'not_checked', 'elements': []}
    try:
        source = svg_path.read_bytes()
        executable = next((shutil.which(n) for n in ('google-chrome','chromium','chromium-browser','chrome')
                           if shutil.which(n)), None)
        if not executable:
            raise RuntimeError('Chrome unavailable; computed SVG display measurements were not collected')
        version = subprocess.run([executable, '--version'], capture_output=True, text=True, timeout=10).stdout.strip()
        binding = {'svg_sha256': digest(source), 'collector_sha256': digest(Path(__file__).read_bytes()),
                   'renderer': {'backend': 'chrome', 'version': version}}
        record.update(binding)
        if output.is_file():
            try:
                cached = json.loads(output.read_text(encoding='utf-8'))
                if (cached.get('status') == 'pass' and all(cached.get(k) == v for k,v in binding.items())
                        and cached.get('integrity') == content_digest(cached)):
                    return cached
            except (ValueError, OSError):
                pass
        with tempfile.TemporaryDirectory(prefix='sheet-measure-') as tmp:
            page = Path(tmp, 'measure.html')
            page.write_text('<!doctype html><meta charset="utf-8"><style>html,body{margin:0;padding:0}</style>'
                            '<pre id="evidence" style="display:none"></pre><script>' +
                            SCRIPT.replace('__SVG__', base64.b64encode(source).decode()) + '</script>', encoding='utf-8')
            command = [executable, '--headless', '--disable-gpu', '--disable-dev-shm-usage',
                       '--no-first-run', '--no-default-browser-check', '--user-data-dir='+str(Path(tmp,'profile')),
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
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
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
