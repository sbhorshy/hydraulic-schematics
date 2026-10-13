// Codex independent audit. Run only on a disposable repository copy.
import {browser,delay} from './cdp-client.mjs';
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {openSync,closeSync} from 'node:fs';
import path from 'node:path';
const [repo,out]=process.argv.slice(2);await mkdir(out,{recursive:true});
const project=path.join(repo,'1#系统原理图'),lp=path.join(project,'1#系统.layout.json');
const sock=createServer();await new Promise(r=>sock.listen(0,'127.0.0.1',r));const port=sock.address().port;await new Promise(r=>sock.close(r));
const fd=openSync(path.join(out,'server.log'),'w');const server=spawn('python3',[path.join(repo,'editor-proto/server.py'),'--workdir',project,'--port',String(port)],{detached:true,stdio:['ignore',fd,fd]});closeSync(fd);
let chrome,failure;const checks=[];let observations={};
function check(value,name,actual){checks.push({name,pass:!!value,actual});}
async function until(fn,name,limit=180000){const t=Date.now();while(Date.now()-t<limit){const v=await fn();if(v)return v;await delay(200);}throw Error('Timeout '+name);}
try{
 await until(async()=>{try{return (await fetch(`http://127.0.0.1:${port}/api/layout`)).ok;}catch{return false;}},'server');
 await (await fetch(`http://127.0.0.1:${port}/api/sheet`)).json();
 chrome=await browser();await chrome.send('Emulation.setDeviceMetricsOverride',{width:1800,height:1500,deviceScaleFactor:1,mobile:false});
 await chrome.send('Page.navigate',{url:`http://127.0.0.1:${port}/`});
 await until(()=>chrome.evaluate("typeof layoutIndex!=='undefined' && !!layoutIndex && !!document.querySelector('#inst-CDF-001')"),'page');
 async function box(id){return chrome.evaluate(`(()=>{select(${JSON.stringify(id)});const r=document.querySelector('#proto-guides .proto-sel');return r?Object.fromEntries(['x','y','width','height'].map(k=>[k,+r.getAttribute(k)])):null;})()`);}
 let r=await box('CDF-001');check(r?.width===158&&r?.height===100&&r?.x===730&&r?.y===430,'270-degree CDF selection uses actual occupied rectangle',r);
 r=await box('FSOV-001');check(r?.width===204.003&&r?.height===362.304,'270-degree non-square FSOV selection swaps width/height',r);
 r=await box('RF-001');check(r?.width===100&&r?.height===194,'180-degree selection keeps original occupied dimensions',r);
 r=await box('TANK-001');check(r?.width===218&&r?.height===564,'zero-degree selection keeps original occupied dimensions',r);
 const c=await chrome.evaluate("guideCands({id:'EMP-001'})");check(c.v.includes(888)&&c.v.includes(809)&&c.h.includes(530)&&c.h.includes(480),'rotated target contributes correct edge and center candidates',{v:c.v,h:c.h});
 await chrome.evaluate("document.getElementById('alignOn').checked=true;document.getElementById('gridSize').value='0';select('CDF-001');window.auditRequests=[];window.auditFetch=window.fetch;window.fetch=async function(url,opts){if(url!='/api/delta')return window.auditFetch(url,opts);const row={body:JSON.parse(opts.body),done:false};window.auditRequests.push(row);try{const r=await window.auditFetch(url,opts);row.response=await r.clone().json();return r;}finally{row.done=true;}};");
 const pt=await chrome.evaluate("(()=>{const g=document.querySelector('#inst-CDF-001'),m=g.ownerSVGElement.getScreenCTM(),p=new DOMPoint(750,450).matrixTransform(m);return {x:p.x,y:p.y,sx:m.a};})()");
 await chrome.evaluate(`(()=>{document.querySelector('#inst-CDF-001').dispatchEvent(new PointerEvent('pointerdown',{button:0,bubbles:true,clientX:${pt.x},clientY:${pt.y}}));window.dispatchEvent(new PointerEvent('pointermove',{clientX:${pt.x-171*pt.sx},clientY:${pt.y}}));})()`);
 const lines=await chrome.evaluate("Array.from(document.querySelectorAll('#proto-guides line')).map(r=>Object.fromEntries(['x1','x2','y1','y2'].map(k=>[k,+r.getAttribute(k)])))");
 check(lines.some(r=>Math.abs(r.x1-556.003)<1e-6&&r.x1===r.x2),'drag hint aligns to rotated FSOV right edge',lines);
 await chrome.evaluate(`window.dispatchEvent(new PointerEvent('pointerup',{button:0,clientX:${pt.x-171*pt.sx},clientY:${pt.y}}))`);
 const response=await until(()=>chrome.evaluate('window.auditRequests[0]?.done ? window.auditRequests[0]:null'),'drag save');await until(()=>chrome.evaluate('!busy && !!layoutIndex'),'drag refresh');
 const layout=JSON.parse(await readFile(lp,'utf8'));const n=layout.nodes['CDF-001'];check(response.response?.ok&&response.body.dx===-174&&n.x===556&&n.rot===270,'snap uses same rotated geometry and persists rounded target',{request:response.body,node:n});
 await chrome.evaluate("postDelta({node:'CDF-001',rot:90,dx:0,dy:0})");await until(()=>chrome.evaluate("!busy && !!layoutIndex && layoutIndex['CDF-001'].rot===90"),'90-degree refresh');
 r=await box('CDF-001');check(r?.width===158&&r?.height===100,'selection after actual rotation/authoritative refresh uses new pose',r);
 check(chrome.errors.length===0,'no uncaught browser errors',chrome.errors);
 observations=await chrome.evaluate('({requests:window.auditRequests,selected:selectedId})');
 const shot=await chrome.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(out,'editor.png'),Buffer.from(shot.data,'base64'));
}catch(e){failure=String(e);}finally{
 await writeFile(path.join(out,'result.json'),JSON.stringify({checks,failure,observations},null,2));if(chrome)await chrome.close();try{process.kill(-server.pid,'SIGTERM');}catch{}
}
console.log(JSON.stringify({checks,failure}));if(failure||checks.some(x=>!x.pass))process.exitCode=1;
