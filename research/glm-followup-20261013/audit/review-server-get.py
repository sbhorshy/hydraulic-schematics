from pathlib import Path
import importlib.util,json,tempfile,threading,urllib.request,urllib.error,sys,subprocess
repo=Path(sys.argv[1]); spec=importlib.util.spec_from_file_location('server_review',repo/'editor-proto/server.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
rows=[]
with tempfile.TemporaryDirectory() as d:
 p=Path(d); s.Handler.workdir=d
 server=s.ThreadingHTTPServer(('127.0.0.1',0),s.Handler);t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
 try:
  valid=json.loads((repo/'1#系统原理图/1#系统.layout.json').read_text())
  for name,layout,intent in [('null-layout',None,'parts: {}'),('valid-contract-invalid-intent',valid,'null')]:
   (p/'1#系统.layout.json').write_text(json.dumps(layout));(p/'1#系统.intent.yaml').write_text(intent)
   try:
    r=urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/layout'); result={'http':r.status,'body':r.read().decode()}
   except urllib.error.HTTPError as e:result={'http':e.code,'body':e.read().decode()}
   except Exception as e:result={'error':type(e).__name__,'detail':str(e)}
   rows.append({'case':name,**result})
 finally:server.shutdown();server.server_close();t.join()
print(json.dumps({'commit':subprocess.run(['git','rev-parse','HEAD'],cwd=repo,text=True,capture_output=True).stdout.strip() or 'native archive snapshot','cases':rows},ensure_ascii=False,indent=2))
