# SysML v2 诊断脚本:拉起 SysIDE 语言服务(VS Code 扩展自带 syside.exe server),
# 模拟编辑器打开指定 .sysml 并打印诊断。用法:
#   python sysml_lsp_check.py <文件.sysml>
# 有问题则打印 ERR/WARN 行;干净文件 SysIDE 不发通知,脚本静默结束。
import json, subprocess, threading, queue, urllib.parse, sys, time

EXE = r"C:\Users\24270\.vscode\extensions\sensmetry.syside-editor-0.10.3-win32-x64\dist\syside.exe"
PATH = sys.argv[1]
ROOT = r"C:\Users\24270\AppData\Local\Temp\sysmlcheck\tests"

def uri(p):
    return urllib.parse.quote("file:///" + p.replace("\\", "/"), safe="/:")

q = queue.Queue()
proc = subprocess.Popen([EXE, "server", "--log-level", "info"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

def reader(stream):
    while True:
        length = None
        while True:
            line = stream.readline()
            if not line: return
            if line in (b"\r\n", b"\n"):
                break
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":")[1].strip())
        if length is None: return
        body = stream.read(length)
        try:
            q.put(json.loads(body.decode("utf-8")))
        except Exception as e:
            q.put({"parse_error": str(e)})

threading.Thread(target=reader, args=(proc.stdout,), daemon=True).start()

msg_id = [0]
def send(method, params=None, notify=True):
    msg_id[0] += 1
    msg = {"jsonrpc": "2.0", "method": method}
    if params is not None: msg["params"] = params
    if not notify: msg["id"] = msg_id[0]
    data = json.dumps(msg).encode("utf-8")
    proc.stdin.write(b"Content-Length: %d\r\n\r\n" % len(data) + data)
    proc.stdin.flush()
    return msg_id[0]

send("initialize", {
    "processId": None,
    "rootUri": uri(ROOT),
    "capabilities": {},
    "workspaceFolders": [{"uri": uri(ROOT), "name": "sheet"}],
}, notify=False)
send("initialized", {}, notify=True)
text = open(PATH, encoding="utf-8").read()
send("textDocument/didOpen", {"textDocument": {
    "uri": uri(PATH), "languageId": "sysml", "version": 1, "text": text}})

deadline = time.time() + 120
got = False
while time.time() < deadline:
    try:
        m = q.get(timeout=2)
    except queue.Empty:
        if got: break
        continue
    if "parse_error" in m: print("JSON-RPC parse error:", m["parse_error"]); continue
    if "id" in m and "error" in m: print("LSP error:", m["error"]); break
    if m.get("method") == "textDocument/publishDiagnostics":
        p = m["params"]
        if p["uri"] == uri(PATH):
            got = True
            for d in p["diagnostics"]:
                r = d["range"]["start"]
                sev = {1:"ERR",2:"WARN",3:"INFO",4:"HINT"}.get(d.get("severity"), d.get("severity"))
                print(f"{sev} L{r['line']+1}:C{r['character']+1} {d['message']}")
            print("DIAG COUNT:", len(p["diagnostics"]))
            if p["diagnostics"]: break
send("shutdown", None, notify=False)
proc.terminate()
print("done")
