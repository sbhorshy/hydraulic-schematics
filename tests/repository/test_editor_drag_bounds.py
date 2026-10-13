"""#60 原型缺口：服务端 drawable 夹取回归（apply_delta 直调 + HTTP）。

夹取与落盘永远真实：apply_delta 按 layout_contract.drawable_bounds 的显式
drawable 收紧坐标，经 write_layout_atomic 原子写盘——两者都不作任何替换；
仅昂贵的 render/rasterize/validate 子进程链用记账执行器（与
test_editor_mirror 同法：setUpClass 真渲染一次，提供成功路径读取的真实
链产物）。覆盖：非零 drawable 起点夹取、右缘夹取（margin 不二次扣）、
90/270 旋转占位宽高交换、越界拖拽、旋转后放不下/无效尺寸/坏契约/非有限
坐标拒绝、非有限位移（NaN/±Inf，含 HTTP 入口）拒绝——拒绝场景 layout
字节、layout_version、revision_log 与渲染链调用均不动。GET /api/layout
披露 drawable_bounds 数组，契约坏档（含顶层 null/数组/标量）HTTP 400，
intent 坏档组装异常 JSON 500——均结构化错误、不断连、不写盘，其余字段
兼容。
"""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

from repository_context import REPO, SKILL
from test_entrypoints import make_render_workspace

spec = importlib.util.spec_from_file_location(
    'editor_server_bounds', REPO / 'editor-proto/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

SMALL = SKILL / 'assets' / 'fixtures' / 'l0-small-seed'
LAYOUT_NAME = '1#系统.layout.json'
# seed 契约：drawable (0,0)-(1650,1390)（canvas 1680×1390，右缘 margin 30）。
SEED_DRAWABLE_BOUNDS = [0.0, 0.0, 1650.0, 1390.0]


class EditorDragBounds(unittest.TestCase):
    """drawable 夹取与坏输入写盘前拒绝（记账执行器，真实夹取与写盘）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='editor-drag-bounds-')
        cls.addClassCleanup(cls.tmp.cleanup)
        # make_render_workspace 自建 root/'run' 子目录：传已存在的 tmp 根，
        # 不要再拼 'run'（同 test_editor_mirror）。
        cls.work = make_render_workspace(Path(cls.tmp.name), SMALL)
        # 真实渲染一次，提供 apply_delta 成功路径读取的真实链产物；
        # 快速用例的记账执行器只跳过重复子进程，夹取与写入不替换。
        for script in ('render_l0_sheet.py', 'rasterize_sheet.py', 'validate_sheet.py'):
            if script == 'rasterize_sheet.py':
                # 与 server._run 同形：SVG 位置参数 + -o 读回 PNG；
                # rasterize_sheet.py 不在 make_render_workspace 拷贝清单内，
                # 用 skill 规范源脚本。
                args = [sys.executable, str(SKILL / 'scripts' / script),
                        str(cls.work / '1#系统原理图.svg'),
                        '-o', str(cls.work / 'sheet-readback.png')]
            else:
                args = [sys.executable, str(cls.work / script), str(cls.work)]
            done = subprocess.run(args, cwd=cls.work, capture_output=True, text=True, timeout=300)
            assert done.returncode == 0, script + done.stdout + done.stderr
        cls.baseline = (cls.work / LAYOUT_NAME).read_bytes()
        cls.intent_baseline = (cls.work / '1#系统.intent.yaml').read_bytes()
        cls.catalog_baseline = (cls.work / 'component-catalog.json').read_bytes()

    def setUp(self):
        (self.work / LAYOUT_NAME).write_bytes(self.baseline)
        (self.work / '1#系统.intent.yaml').write_bytes(self.intent_baseline)
        (self.work / 'component-catalog.json').write_bytes(self.catalog_baseline)
        self.calls = []
        self.real_run = server._run

        def bookkeeping(workdir, script, timeout=300):
            self.calls.append(script)
            return (0, '', '', 1)

        server._run = bookkeeping
        self.addCleanup(setattr, server, '_run', self.real_run)

    # -- 辅助 ----------------------------------------------------------

    def layout(self):
        return json.loads((self.work / LAYOUT_NAME).read_text(encoding='utf-8'))

    def rewrite_layout(self, layout):
        (self.work / LAYOUT_NAME).write_text(
            json.dumps(layout, ensure_ascii=False, indent=2), encoding='utf-8')

    def restore(self):
        (self.work / LAYOUT_NAME).write_bytes(self.baseline)

    def edit_node(self, node, **fields):
        layout = self.layout()
        layout['nodes'][node].update(fields)
        self.rewrite_layout(layout)

    def edit_drawable(self, x, y, width, height):
        layout = self.layout()
        layout['drawable'] = {'x': x, 'y': y, 'width': width, 'height': height}
        self.rewrite_layout(layout)

    def assert_transaction_unchanged(self, before):
        self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)
        after = self.layout()
        stocked = json.loads(before.decode('utf-8'))
        self.assertEqual(after['layout_version'], stocked['layout_version'])
        self.assertEqual(len(after.get('revision_log') or []),
                         len(stocked.get('revision_log') or []))

    def _serve(self):
        server.Handler.workdir = str(self.work)
        http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
        worker = threading.Thread(target=http.serve_forever, daemon=True)
        worker.start()
        # addCleanup LIFO：shutdown → server_close → join。
        self.addCleanup(worker.join)
        self.addCleanup(http.server_close)
        self.addCleanup(http.shutdown)
        return http.server_port

    # -- 直调 apply_delta：夹取落盘 ------------------------------------

    def test_clamps_to_nonzero_drawable_origin_not_canvas_zero(self):
        # drawable 起点 (40,50)：向左上拖出界夹到 drawable 起点，
        # 而非 canvas 原点 (0,0)。
        self.edit_drawable(40, 50, 1610, 1340)  # 右缘仍 1650，下缘仍 1390
        result = server.apply_delta(str(self.work), 'EDP-001', -10**4, -10**4)
        self.assertTrue(result['ok'], result)
        node = self.layout()['nodes']['EDP-001']
        self.assertEqual(node['x'], 40)
        self.assertEqual(node['y'], 50)

    def test_right_edge_clamps_inside_drawable_without_double_margin(self):
        # 右缘/下缘越界：夹到 drawable 右缘 1650-80=1570（margin 已在
        # 契约内不二次扣→1540；也不回退 canvas 口径 1680-80=1600）。
        result = server.apply_delta(str(self.work), 'EDP-001', 10**4, 10**4)
        self.assertTrue(result['ok'], result)
        node = self.layout()['nodes']['EDP-001']
        self.assertEqual(node['x'], 1570)
        self.assertEqual(node['y'], 1310)
        self.assertIn('EDP-001', self.layout()['revision_log'][-1])

    def test_rot90_and_rot270_swap_occupied_width_height_for_clamp(self):
        # TANK-001 218×564：rot 90/270 后占位 564×218——右缘夹到
        # 1650-564=1086、下缘 1390-218=1172；rot 0 对照 1650-218=1432。
        for rot in (90, 270):
            with self.subTest(rot=rot):
                self.restore()
                result = server.apply_delta(str(self.work), 'TANK-001', 10**4, 0, rot)
                self.assertTrue(result['ok'], result)
                node = self.layout()['nodes']['TANK-001']
                self.assertEqual(node['rot'], rot)
                self.assertEqual(node['x'], 1086)
                self.assertEqual(node['y'], 120)
        self.restore()
        result = server.apply_delta(str(self.work), 'TANK-001', 0, 10**4, 90)
        self.assertTrue(result['ok'], result)
        node = self.layout()['nodes']['TANK-001']
        self.assertEqual(node['y'], 1172)
        self.assertEqual(node['x'], 90)
        self.restore()
        result = server.apply_delta(str(self.work), 'TANK-001', 10**4, 0, 0)
        self.assertTrue(result['ok'], result)
        node = self.layout()['nodes']['TANK-001']
        self.assertEqual(node['x'], 1432)
        self.assertNotIn('rot', node)

    def test_rotated_oversize_rejects_before_write(self):
        # 旋转后放不下（占位 > drawable 边长）：整事务写盘前拒绝。
        self.edit_node('EDP-001', h=1700)  # rot90 后 ew=1700 > 1650
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'EDP-001', 10, 0, 90)
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'delta')
        self.assertIn('放不下', result['error'])
        self.assert_transaction_unchanged(before)
        self.assertEqual(self.calls, [])
        self.restore()
        self.edit_node('EDP-001', w=2000)  # 不旋转也放不下（ew=2000 > 1650）
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'EDP-001', 10, 0)
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'delta')
        self.assert_transaction_unchanged(before)
        self.restore()
        self.edit_node('EDP-001', h=1500)  # eh=1500 > 1390：dy 方向同样拒绝
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'EDP-001', 0, 10)
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'delta')
        self.assert_transaction_unchanged(before)

    def test_invalid_size_rejects_before_write(self):
        # 占位尺寸必须为正的有限数：0/负数/NaN/Inf 都无效，写盘前拒绝。
        for fields in ({'w': 0}, {'w': -5}, {'w': float('nan')},
                       {'h': float('nan')}, {'w': float('inf')}):
            with self.subTest(fields=fields):
                self.restore()
                self.edit_node('EDP-001', **fields)
                before = (self.work / LAYOUT_NAME).read_bytes()
                result = server.apply_delta(str(self.work), 'EDP-001', 10, 0)
                self.assertFalse(result['ok'])
                self.assertEqual(result['stage'], 'delta')
                self.assert_transaction_unchanged(before)
                self.assertEqual(self.calls, [])

    def test_nonfinite_stored_coordinates_reject_before_write(self):
        # 存量坐标非有限（坏档）：不静默夹取，写盘前拒绝。
        for fields in ({'x': float('nan')}, {'y': float('inf')},
                       {'x': float('-inf')}):
            with self.subTest(fields=fields):
                self.restore()
                self.edit_node('EDP-001', **fields)
                before = (self.work / LAYOUT_NAME).read_bytes()
                result = server.apply_delta(str(self.work), 'EDP-001', 10, 0)
                self.assertFalse(result['ok'])
                self.assertEqual(result['stage'], 'delta')
                self.assert_transaction_unchanged(before)
                self.assertEqual(self.calls, [])

    def test_nonfinite_delta_rejects_before_write(self):
        # NaN/±Inf 位移：入口按有限数校验拒绝，字节不动，不触发渲染链。
        for dx, dy in ((float('nan'), 0), (0, float('nan')),
                       (float('inf'), 0), (0, float('-inf'))):
            with self.subTest(dx=dx, dy=dy):
                self.restore()
                before = (self.work / LAYOUT_NAME).read_bytes()
                result = server.apply_delta(str(self.work), 'EDP-001', dx, dy)
                self.assertFalse(result['ok'])
                self.assertEqual(result['stage'], 'delta')
                self.assertIn('finite', result['error'])
                self.assert_transaction_unchanged(before)
                self.assertEqual(self.calls, [])

    def test_bad_contract_rejects_before_write(self):
        # 缺 drawable/edge_margin/coordinate_system 的坏契约：不静默回退
        # canvas 夹取，写盘前整事务拒绝。
        layout = self.layout()
        for key in ('drawable', 'edge_margin', 'coordinate_system'):
            layout.pop(key, None)
        self.rewrite_layout(layout)
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'EDP-001', 10, 0)
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'delta')
        self.assertIn('drawable', result['error'])
        self.assert_transaction_unchanged(before)
        self.assertEqual(self.calls, [])

    # -- HTTP 回归 ------------------------------------------------------

    def test_api_layout_exposes_drawable_bounds_array(self):
        port = self._serve()
        with urllib.request.urlopen(
                'http://127.0.0.1:%d/api/layout' % port, timeout=30) as response:
            self.assertEqual(response.status, 200)
            body = json.load(response)
        self.assertEqual(body['drawable_bounds'], SEED_DRAWABLE_BOUNDS)
        self.assertIn('EDP-001', body['nodes'])
        self.assertEqual(body['canvas']['width'], 1680)
        self.assertIn('conns', body)

    def test_api_layout_bad_contract_returns_http_400(self):
        layout = self.layout()
        for key in ('drawable', 'edge_margin', 'coordinate_system'):
            layout.pop(key, None)
        self.rewrite_layout(layout)
        port = self._serve()
        try:
            urllib.request.urlopen(
                'http://127.0.0.1:%d/api/layout' % port, timeout=30)
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 400)
            self.assertIn('drawable', json.load(error)['error'])
        else:
            self.fail('坏契约必须 HTTP 400')

    def test_api_layout_non_dict_top_level_returns_http_400_without_write(self):
        # layout 顶层 null/数组/标量：drawable_bounds 首个成员测试会对
        # None/标量抛 TypeError——必须同契约坏档回 400 JSON，不得异常
        # 冒出 do_GET 断连（RemoteDisconnected）；字节不动。
        port = self._serve()
        lp = self.work / LAYOUT_NAME
        for raw in ('null', '[1, 2]', '42', '"seed"'):
            with self.subTest(raw=raw):
                lp.write_text(raw, encoding='utf-8')
                before = lp.read_bytes()
                try:
                    urllib.request.urlopen(
                        'http://127.0.0.1:%d/api/layout' % port, timeout=30)
                except urllib.error.HTTPError as error:
                    self.assertEqual(error.code, 400)
                    self.assertIn('error', json.load(error))
                else:
                    self.fail('顶层非对象 layout 必须 HTTP 400（%r）' % raw)
                self.assertEqual(lp.read_bytes(), before)

    def test_api_layout_null_intent_returns_json_500_without_write(self):
        # intent 内容为 null：load_yaml 不抛、_connection_counts 对 None
        # 取 .get 抛 AttributeError——组装异常必须回 JSON 500 结构化错误
        # （不发明空 conns 伪装成功、不断连），layout 字节不动。
        (self.work / '1#系统.intent.yaml').write_text('null\n', encoding='utf-8')
        before = (self.work / LAYOUT_NAME).read_bytes()
        port = self._serve()
        try:
            urllib.request.urlopen(
                'http://127.0.0.1:%d/api/layout' % port, timeout=30)
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 500)
            self.assertIn('error', json.load(error))
        else:
            self.fail('intent 坏档组装异常必须 JSON 500')
        self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)

    def test_http_delta_clamps_right_edge_and_writes_layout(self):
        port = self._serve()
        req = urllib.request.Request(
            'http://127.0.0.1:%d/api/delta' % port,
            data=json.dumps({'node': 'EDP-001', 'dx': 10**4}).encode(),
            headers={'Content-Type': 'application/json'})
        result = json.load(urllib.request.urlopen(req, timeout=60))
        self.assertTrue(result['ok'], result)
        node = self.layout()['nodes']['EDP-001']
        self.assertEqual(node['x'], 1570)
        self.assertEqual(self.layout()['layout_version'], '1.1')
        self.assertIn('render_l0_sheet.py', self.calls)

    def test_http_delta_nan_displacement_rejected_without_write(self):
        port = self._serve()
        req = urllib.request.Request(
            'http://127.0.0.1:%d/api/delta' % port,
            data=json.dumps({'node': 'EDP-001', 'dx': float('nan')}).encode(),
            headers={'Content-Type': 'application/json'})
        result = json.load(urllib.request.urlopen(req, timeout=60))
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'delta')
        self.assert_transaction_unchanged(self.baseline)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
