"""The prototype uses current production gates after a persisted rotation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from test_entrypoints import make_render_workspace, SKILL

spec = importlib.util.spec_from_file_location('editor_server', SKILL.parents[2] / 'editor-proto/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class EditorRotation(unittest.TestCase):
    def test_rotation_persists_and_runs_canonical_chain_without_legacy_scripts(self):
        with tempfile.TemporaryDirectory() as directory:
            work = make_render_workspace(Path(directory), SKILL / 'assets/fixtures/l0-small-seed')
            server.Handler.workdir = str(work)
            http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                req = urllib.request.Request('http://127.0.0.1:%d/api/delta' % http.server_port,
                    data=json.dumps({'node':'PF-001','rot':90}).encode(), headers={'Content-Type':'application/json'})
                result = json.load(urllib.request.urlopen(req, timeout=90))
                self.assertTrue(result['ok'], result)
                self.assertEqual(json.loads((work / '1#系统.layout.json').read_text())['nodes']['PF-001']['rot'], 90)
                self.assertFalse(result['passed'])  # no perceptual signoff
                self.assertEqual(result['evidence']['status'], 'current')
                self.assertTrue((work / 'sheet-readback.png').exists())
                # Invalid manual geometry is kept and accurately shown red.
                req.data = json.dumps({'node':'PF-001','dx':-280}).encode()
                result = json.load(urllib.request.urlopen(req, timeout=90))
                self.assertFalse(result['passed'])
                self.assertTrue(any(i['sev']=='red' for i in result['issues']), result)
                self.assertEqual(json.loads((work / '1#系统.layout.json').read_text())['nodes']['PF-001']['x'], 570)
            finally:
                http.shutdown(); http.server_close(); worker.join()

if __name__ == '__main__': unittest.main()
