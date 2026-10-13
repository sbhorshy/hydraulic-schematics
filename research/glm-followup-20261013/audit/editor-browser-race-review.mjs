// Codex review: real Chrome interactions against a disposable project copy.
import {browser,delay} from './cdp-client.mjs';
import {spawn} from 'node:child_process';
import {createServer} from 'node:net';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
import {openSync,closeSync} from 'node:fs';
import path from 'node:path';
const [repo,out]=process.argv.slice(2);if(!repo||!out)throw Error('repo output required');
await mkdir(out,{recursive:true});
const project=path.join(repo,'1#系统原理图'),layoutFile=path.join(project,'1#系统.layout.json');
const sock=createServer();await new Promise(resolve=>sock.listen(0,'127.0.0.1',resolve));const port=sock.address().port;await new Promise(resolve=>sock.close(resolve));
const log=openSync(path.join(out,'server.log'),'w');
const server=spawn('python',[path.join(repo,'editor-proto/server.py'),'--workdir',project,'--port',String(port)],{detached:true,stdio:['ignore',log,log]});closeSync(log);
let chrome;const checks=[];let failure;
async function until(fn,label,limit=150000){const start=Date.now();while(Date.now()-start<limit){const value=await fn();if(value)return value;await delay(200);}throw Error('Timeout '+label);}
function assert(v,label){checks.push({check:label,pass:!!v});if(!v)throw Error(label);}
try{
 await until(async()=>{try{return (await fetch('http://127.0.0.1:'+port+'/api/layout')).ok;}catch{return false;}},'server');
 const warm=await fetch('http://127.0.0.1:'+port+'/api/sheet');await warm.json();
 chrome=await browser();await chrome.send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await chrome.send('Page.navigate',{url:'http://127.0.0.1:'+port+'/'});
 await until(()=>chrome.evaluate("typeof layoutIndex!=='undefined' && !!layoutIndex && !!layoutIndex['EMP-001'] && !!document.querySelector('#inst-EMP-001')"),'page');
 await chrome.evaluate("window.auditRequests=[];window.auditFetch=window.fetch;window.fetch=async function(url,options){if(url==='/api/layout'){if(window.auditDelayLayout){const ms=window.auditDelayLayout;window.auditDelayLayout=0;window.auditLayoutPending=true;await new Promise(r=>setTimeout(r,ms));window.auditLayoutPending=false;}if(window.auditFailLayout){window.auditFailLayout=false;throw new TypeError('audit simulated layout read failure');}}if(url!='/api/delta')return window.auditFetch(url,options);const row={body:JSON.parse(options.body),started:Date.now(),done:false};window.auditRequests.push(row);try{const r=await window.auditFetch(url,options);row.response=await r.clone().json();return r;}catch(e){row.error=e.name+': '+e.message;throw e;}finally{row.done=true;row.duration_ms=Date.now()-row.started;}}");
 async function click(id){
  const n=await chrome.evaluate('window.auditRequests.length');
  const box=await chrome.evaluate("(()=>{const r=document.getElementById("+JSON.stringify(id)+").getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()");
  await chrome.send('Input.dispatchMouseEvent',{type:'mousePressed',...box,button:'left',clickCount:1});
  await chrome.send('Input.dispatchMouseEvent',{type:'mouseReleased',...box,button:'left',clickCount:1});
  return await until(()=>chrome.evaluate('window.auditRequests['+n+']?.done ? window.auditRequests['+n+'] : null'),'button '+id);
 }
 async function key(modifiers=0,autoRepeat=false){
  await chrome.send('Input.dispatchKeyEvent',{type:'keyDown',key:modifiers===8?'M':'m',code:'KeyM',windowsVirtualKeyCode:77,nativeVirtualKeyCode:77,modifiers,autoRepeat});
  await chrome.send('Input.dispatchKeyEvent',{type:'keyUp',key:modifiers===8?'M':'m',code:'KeyM',windowsVirtualKeyCode:77,nativeVirtualKeyCode:77,modifiers});
 }
 await chrome.evaluate("select('EMP-001')");
 let response=await click('mirrorNoneBtn');
 assert(!response.error,'long mutation request completes without premature client abort');
 assert(response.response?.ok,'mirror clear accepted');
 await until(()=>chrome.evaluate("!!layoutIndex && !layoutIndex['EMP-001'].mirror && document.getElementById('selMirror').textContent==='none'"),'mirror clear UI');
 let n=await chrome.evaluate('window.auditRequests.length');
 await chrome.evaluate("const auditInput=document.createElement('input');auditInput.id='audit-focus-input';document.body.appendChild(auditInput);auditInput.focus()");
 await key();await delay(300);
 assert(await chrome.evaluate('window.auditRequests.length')===n,'M in text input does not mutate');
 await chrome.evaluate("document.getElementById('audit-focus-input').remove();document.activeElement.blur()");
 for(const modifier of [1,2,4,8]){await key(modifier);await delay(150);}
 await key(0,true);await delay(300);
 assert(await chrome.evaluate('window.auditRequests.length')===n,'modified and repeated M do not mutate');
 await key();
 response=await until(()=>chrome.evaluate('window.auditRequests['+n+']?.done ? window.auditRequests['+n+'] : null'),'M key');
 assert(!response.error && response.response?.ok,'M sends successful mirror mutation');
 await until(()=>chrome.evaluate("!!layoutIndex && layoutIndex['EMP-001'].mirror==='x'"),'M x state');
 response=await click('mirrorYBtn');
 assert(!response.error && response.response?.ok,'vertical mirror button succeeds');
 await until(()=>chrome.evaluate("!!layoutIndex && layoutIndex['EMP-001'].mirror==='y'"),'mirror y state');
 const before=await readFile(layoutFile);
 await chrome.evaluate("select('PF-001')");
 response=await click('mirrorXBtn');
 assert(response.response?.stage==='permission' && !response.response.ok,'unregistered mirror rejected by actual server');
 assert(before.equals(await readFile(layoutFile)),'rejected request does not modify layout bytes');
 const state=await chrome.evaluate("({state:document.getElementById('state').textContent,banner:document.getElementById('banner').textContent,shown:getComputedStyle(document.getElementById('banner')).display})");
 assert(!state.state.includes('已落盘') && (state.banner.includes('许可') || state.state.includes('许可')),'UI displays refusal without claiming it persisted');

 await chrome.evaluate("select('EMP-001');window.auditDelayLayout=1800");
 n=await chrome.evaluate('window.auditRequests.length');
 response=await click('mirrorXBtn');
 assert(response.response?.ok,'x mutation accepted before delayed refresh');
 await until(()=>chrome.evaluate('window.auditLayoutPending===true'),'delayed authoritative layout fetch',5000);
 await key();await delay(300);
 assert(await chrome.evaluate('window.auditRequests.length')===n+1,'M during authoritative layout refresh does not mutate');
 await until(()=>chrome.evaluate("!window.auditLayoutPending && !!layoutIndex && layoutIndex['EMP-001'].mirror==='x'"),'authoritative x refresh');
 await key();
 response=await until(()=>chrome.evaluate('window.auditRequests['+(n+1)+']?.done ? window.auditRequests['+(n+1)+'] : null'),'M after refresh');
 assert(response.body.mirror==='y' && response.response?.ok,'M after x refresh continues to y');
 await until(()=>chrome.evaluate("!!layoutIndex && layoutIndex['EMP-001'].mirror==='y'"),'authoritative y');
 await chrome.evaluate('window.auditFailLayout=true');
 response=await click('mirrorXBtn');
 assert(response.response?.ok,'server confirms save before injected read failure');
 await until(()=>chrome.evaluate("document.getElementById('mirrorXBtn').disabled && document.getElementById('rotBtn').disabled"),'controls held after layout refresh failure',5000);
 n=await chrome.evaluate('window.auditRequests.length');await key();await delay(300);
 assert(await chrome.evaluate('window.auditRequests.length')===n,'unknown layout state cannot generate another mirror mutation');
 const refreshState=await chrome.evaluate("document.getElementById('state').textContent+' '+document.getElementById('banner').textContent");
 assert(refreshState.includes('刷新') && refreshState.includes('保存'),'refresh failure explains saved-but-unavailable state');

 const shot=await chrome.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
 await writeFile(path.join(out,'editor.png'),Buffer.from(shot.data,'base64'));
}catch(error){failure=String(error);}
finally{
 const observations=chrome?await chrome.evaluate("({requests:window.auditRequests||[],state:document.getElementById('state')?.textContent,banner:document.getElementById('banner')?.textContent})").catch(()=>null):null;
 await writeFile(path.join(out,'result.json'),JSON.stringify({checks,failure,observations,browser_errors:chrome?.errors},null,2));
 if(chrome)await chrome.close();
 try{process.kill(-server.pid,'SIGTERM');}catch{}
}
console.log(JSON.stringify({checks,failure}));if(failure)process.exitCode=1;
