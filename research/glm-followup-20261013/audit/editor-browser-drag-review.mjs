// Codex independent behavioral review; disposable source/project copy only.
import {browser,delay} from './cdp-client.mjs';
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {openSync,closeSync} from 'node:fs';
import path from 'node:path';
const [repo,out]=process.argv.slice(2);await mkdir(out,{recursive:true});
const project=path.join(repo,'1#系统原理图'),lp=path.join(project,'1#系统.layout.json');
const original=JSON.parse(await readFile(lp,'utf8'));
// Non-grid-aligned bounds deliberately catch snapping back outside the drawable.
original.drawable={x:3,y:7,width:1654,height:1310};original.edge_margin=30;
original.nodes['ACC-001'].x=1580; // Real alignment candidate 3 units beyond EMP maximum x.
original.nodes['EMP-001'].rot=90;original.nodes['EMP-001'].mirror='y';
await writeFile(lp,JSON.stringify(original,null,2));
const sock=createServer();await new Promise(r=>sock.listen(0,'127.0.0.1',r));const port=sock.address().port;await new Promise(r=>sock.close(r));
const log=openSync(path.join(out,'server.log'),'w');const server=spawn('python3',[path.join(repo,'editor-proto/server.py'),'--workdir',project,'--port',String(port)],{detached:true,stdio:['ignore',log,log]});closeSync(log);
let chrome,failure;const checks=[];
function check(value,name){checks.push({name,pass:!!value});if(!value)throw Error(name);}
async function until(fn,name,limit=180000){const t=Date.now();while(Date.now()-t<limit){const r=await fn();if(r)return r;await delay(200);}throw Error('Timeout '+name);}
try{
 await until(async()=>{try{return (await fetch(`http://127.0.0.1:${port}/api/layout`)).ok;}catch{return false;}},'server');
 chrome=await browser();await chrome.send('Emulation.setDeviceMetricsOverride',{width:1800,height:1600,deviceScaleFactor:1,mobile:false});
 await chrome.send('Page.navigate',{url:`http://127.0.0.1:${port}/`});
 await until(()=>chrome.evaluate("typeof layoutIndex!=='undefined' && !!layoutIndex && !!document.querySelector('#inst-EMP-001')"),'page');
 await chrome.evaluate("window.auditRequests=[];window.auditFetch=window.fetch;window.fetch=async function(url,options){if(url!='/api/delta')return window.auditFetch(url,options);const row={body:JSON.parse(options.body),done:false};window.auditRequests.push(row);try{const r=await window.auditFetch(url,options);row.response=await r.clone().json();return r;}finally{row.done=true;}};document.getElementById('gridSize').value='20';document.getElementById('alignOn').checked=true");
 async function drag(dx,dy){
  const i=await chrome.evaluate('window.auditRequests.length');
  const pt=await chrome.evaluate("(()=>{const s=document.querySelector('#inst-EMP-001').ownerSVGElement,m=s.getScreenCTM();const n=layoutIndex['EMP-001'];const p=new DOMPoint(n.x+n.w/2,n.y+n.h/2).matrixTransform(m);return {x:p.x,y:p.y,sx:m.a,sy:m.d};})()");
  // Actual pointer events delivered to the production listeners; no clamp/postDelta mocks.
  await chrome.evaluate(`(()=>{const g=document.querySelector('#inst-EMP-001');g.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,clientX:${pt.x},clientY:${pt.y}}));window.dispatchEvent(new PointerEvent('pointermove',{clientX:${pt.x+dx*pt.sx},clientY:${pt.y+dy*pt.sy}}));window.dispatchEvent(new PointerEvent('pointerup',{button:0,clientX:${pt.x+dx*pt.sx},clientY:${pt.y+dy*pt.sy}}));})()`);
  const r=await until(()=>chrome.evaluate(`window.auditRequests[${i}]?.done?window.auditRequests[${i}]:null`),'drag POST');
  await until(()=>chrome.evaluate('!busy && !!layoutIndex'),'authoritative refresh');return r;
 }
 let r=await drag(4000,4000);let lay=JSON.parse(await readFile(lp,'utf8'));let n=lay.nodes['EMP-001'];
 check(r.response?.ok,'extreme right/bottom drag persisted through real pipeline');
 check(n.x===1657-80 && n.y===1317-80,'post-snap node lands on drawable right/bottom, not canvas');
 check(r.body.dx===n.x-original.nodes['EMP-001'].x && r.body.dy===n.y-original.nodes['EMP-001'].y,'frontend sends already bounded delta');
 await chrome.evaluate("document.getElementById('alignOn').checked=false");
 r=await drag(-4000,-4000);lay=JSON.parse(await readFile(lp,'utf8'));n=lay.nodes['EMP-001'];
 check(r.response?.ok && n.x===3 && n.y===7,'nonzero drawable left/top maintained after grid snapping');
 check(n.rot===90 && n.mirror==='y','drag preserves rotation and registered mirror');
 check(chrome.errors.length===0,'no uncaught browser errors');
 const shot=await chrome.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});await writeFile(path.join(out,'editor.png'),Buffer.from(shot.data,'base64'));
}catch(e){failure=String(e);}finally{
 await writeFile(path.join(out,'result.json'),JSON.stringify({checks,failure,browser_errors:chrome?.errors},null,2));if(chrome)await chrome.close();try{process.kill(-server.pid,'SIGTERM');}catch{}
}
console.log(JSON.stringify({checks,failure}));if(failure)process.exitCode=1;
