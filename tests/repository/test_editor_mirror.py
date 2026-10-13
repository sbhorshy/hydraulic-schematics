"""#63 editor-proto mirror plane: real apply_delta/API regressions.

The permission call and the write path are always real: mirror authorization
goes through the production catalog gates (endpoint_usage.mirror_contract on
the workspace's actual catalog/assets/intent) and every accepted delta lands
through server.write_layout_atomic. Only the expensive render/rasterize/
validate subprocess chain is replaced by a bookkeeping executor in the fast
cases; the chain artifacts (SVG/report/PNG) are produced once by a real
render in setUpClass so the post-write code path reads real files. One full
-chain case keeps the real executor and goes over real HTTP (run by Codex).

Audit regressions (2026-10-12 复审): ON/OFF/No 等 YAML 1.1 布尔拼写实例 ID
曾借 PyYAML(1.1) 强转 bool 绕过许可写盘（../editor-permission-review.json）；
选中节点缺失 intent.parts/类型未登记、函数入口与请求层 mirror 类型值域
（False/0/True/容器）均须写盘前拒绝且字节不动。三审修正：layout 存量值域
与 API 请求值域分离——规范单源 mirror_policy.check_mirror 允许已有
layout.mirror=False 表示不镜像（与此前 renderer 兼容），普通移动放行且
原样保留该字段；存量 0/True/容器仍整事务拒绝。
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

spec = importlib.util.spec_from_file_location('editor_server', REPO / 'editor-proto/server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

SMALL = SKILL / 'assets' / 'fixtures' / 'l0-small-seed'
LAYOUT_NAME = '1#系统.layout.json'


class EditorMirror(unittest.TestCase):
    """apply_delta 直调：镜像授权、写入、日志、拒绝无写入（执行器记账）。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='editor-mirror-')
        cls.addClassCleanup(cls.tmp.cleanup)
        # make_render_workspace 自建 root/'run' 子目录：传已存在的 tmp 根，
        # 不要再拼 'run'（否则 run/run 父路径不存在）。
        cls.work = make_render_workspace(Path(cls.tmp.name), SMALL)
        # 真实渲染一次，提供 apply_delta 成功路径读取的真实链产物；
        # 快速用例的记账执行器只跳过重复子进程，许可与写入不替换。
        for script in ('render_l0_sheet.py', 'rasterize_sheet.py', 'validate_sheet.py'):
            if script == 'rasterize_sheet.py':
                # 与 server._run 同形：SVG 位置参数 + -o 读回 PNG。
                # rasterize_sheet.py 不在 make_render_workspace 的拷贝清单内，
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

    def layout(self):
        return json.loads((self.work / LAYOUT_NAME).read_text(encoding='utf-8'))

    def _rename_node_everywhere(self, old, new):
        # 文本级改名（layout JSON 键 + intent YAML 全部出现处），与
        # ../probe-editor-permission.py 的复现手法一致：ON/OFF/No 等
        # YAML 1.1 布尔拼写在 ruamel YAML 1.2（render/许可闸口径）下
        # 仍是字符串实例 ID；PyYAML(1.1) 会把它们解析成 bool。
        lp = self.work / LAYOUT_NAME
        layout = json.loads(lp.read_text(encoding='utf-8'))
        layout['nodes'][new] = layout['nodes'].pop(old)
        lp.write_text(json.dumps(layout, ensure_ascii=False, indent=2),
                      encoding='utf-8')
        ip = self.work / '1#系统.intent.yaml'
        ip.write_text(ip.read_text(encoding='utf-8').replace(old, new),
                      encoding='utf-8')

    def _strip_engine_pump_registration(self):
        # 工作区 catalog 副本上去掉 engine_driven_pump 的镜像登记
        # （不触碰 skill 规范源 catalog；setUp 会恢复基线字节）。
        cp = self.work / 'component-catalog.json'
        catalog = json.loads(cp.read_text(encoding='utf-8'))
        for component in catalog['components']:
            if component['component_type'] == 'engine_driven_pump':
                component.pop('mirror_safe', None)
                component.pop('mirror_registration', None)
                component.get('layout', {}).pop('allow_mirror', None)
        cp.write_text(json.dumps(catalog, ensure_ascii=False, indent=2),
                      encoding='utf-8')

    def test_authorized_mirror_persists_and_logs_before_after_axis(self):
        # EDP-001(engine_driven_pump)在 skill 规范源 catalog 已按 #63 登记
        # axes x/y：真实三道闸放行，mirror=y 落盘，日志记节点 ID 与
        # before/after 轴；节点其余键（端口无关字段）保持不动。
        result = server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'y')
        self.assertTrue(result['ok'], result)
        layout = self.layout()
        node = layout['nodes']['EDP-001']
        self.assertEqual(node['mirror'], 'y')
        self.assertEqual(node['x'], 570.0)
        self.assertEqual(node['y'], 490)
        self.assertEqual(node['symbol'], 'symbols/edp-provisional-stroke.svg')
        entry = layout['revision_log'][-1]
        self.assertIn('EDP-001', entry)
        self.assertIn('mirror none→y', entry)
        # small-seed 版本号非 x.y 格式，bump 回落 '1.1'；断言只是"版本前进"
        self.assertEqual(layout['layout_version'], '1.1')
        # 下游链被调用（执行器记账），渲染先行于校核
        self.assertIn('render_l0_sheet.py', self.calls)
        self.assertIn('validate_sheet.py', self.calls)

    def test_unregistered_component_rejects_whole_transaction_without_write(self):
        # PF-001(pressure_filter)未登记镜像：即便同请求携带移动（dx=30），
        # 整次事务在写盘前被拒——layout_version/revision_log/文件字节不变。
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'PF-001', 30, 0, None, 'x')
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'permission')
        self.assertTrue(result.get('mirror_issues'))
        self.assertIn('PF-001', result['error'])
        self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)
        self.assertEqual(self.calls, [], '拒绝后不得触发渲染链')

    def test_stale_registration_rejects_before_write(self):
        # 登记过期（符号字节在登记后变更）：资产 hash 不符，写盘前拒绝。
        asset = self.work / 'symbols' / 'edp-provisional-stroke.svg'
        original = asset.read_bytes()
        asset.write_bytes(original + b'\n<!-- post-approval edit -->\n')
        try:
            before = (self.work / LAYOUT_NAME).read_bytes()
            result = server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'x')
            self.assertFalse(result['ok'])
            self.assertEqual(result['stage'], 'permission')
            self.assertIn('失效', result['error'])
            self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)
        finally:
            asset.write_bytes(original)

    def test_illegal_axis_rejects_whole_transaction(self):
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'EDP-001', 10, 10, 90, True)
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'delta')  # 布尔不是轴，delta 层即拒
        self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)

    def test_none_removes_mirror_and_logs_axis_pair(self):
        self.assertTrue(server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'y')['ok'])
        result = server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'none')
        self.assertTrue(result['ok'], result)
        node = self.layout()['nodes']['EDP-001']
        self.assertNotIn('mirror', node)
        self.assertIn('mirror y→none', self.layout()['revision_log'][-1])

    def test_mirror_with_move_and_rotation_keeps_all_three(self):
        # 镜像+移动+旋转同请求：三者同时落盘，日志同时记 rot 与 mirror 段。
        result = server.apply_delta(str(self.work), 'EDP-001', 40, 20, 90, 'x')
        self.assertTrue(result['ok'], result)
        node = self.layout()['nodes']['EDP-001']
        self.assertEqual(node['mirror'], 'x')
        self.assertEqual(node['rot'], 90)
        self.assertEqual(node['x'], 610.0)
        self.assertEqual(node['y'], 510)
        entry = self.layout()['revision_log'][-1]
        self.assertIn('EDP-001', entry)
        self.assertIn('rot 0→90', entry)
        self.assertIn('mirror none→x', entry)

    def test_absent_mirror_key_keeps_current_pose_and_rechecks_on_move(self):
        # 缺省=保持姿态：普通移动不新增 mirror 字段。已带合法镜像的实例
        # 再移动（键缺省）仍须过许可：资产漂移后旧镜像的移动被拒。
        self.assertTrue(server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'y')['ok'])
        result = server.apply_delta(str(self.work), 'EDP-001', 25, 0)
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.layout()['nodes']['EDP-001']['mirror'], 'y')

        asset = self.work / 'symbols' / 'edp-provisional-stroke.svg'
        original = asset.read_bytes()
        asset.write_bytes(original + b'\n<!-- post-approval edit -->\n')
        try:
            before = (self.work / LAYOUT_NAME).read_bytes()
            moved = server.apply_delta(str(self.work), 'EDP-001', 25, 0)
            self.assertFalse(moved['ok'])
            self.assertEqual(moved['stage'], 'permission')
            self.assertIn('失效', moved['error'])
            self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)
        finally:
            asset.write_bytes(original)

    def test_same_axis_request_without_other_change_is_zero_displacement(self):
        # 重复请求同一轴且无移动/旋转：仍是零位移（mirror-only 变更才算
        # 操作；重申现状不是）。镜像改变本身不是零位移——见 y 用例。
        result = server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'y')
        self.assertTrue(result['ok'])
        result = server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'y')
        self.assertFalse(result['ok'])
        self.assertEqual(result['stage'], 'delta')
        self.assertIn('零位移', result['error'])

    def test_request_layer_rejects_non_string_mirror_values(self):
        # HTTP 请求层：False/0/true/数字/'z'/容器都不是 none（缺省才是保持姿态）。
        with tempfile.TemporaryDirectory() as directory:
            work = make_render_workspace(Path(directory), SMALL)
            server.Handler.workdir = str(work)
            http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                for bad in (False, 0, True, 1.5, 'z', ['x'], {'axis': 'x'}):
                    with self.subTest(mirror=bad):
                        req = urllib.request.Request(
                            'http://127.0.0.1:%d/api/delta' % http.server_port,
                            data=json.dumps({'node': 'EDP-001', 'mirror': bad}).encode(),
                            headers={'Content-Type': 'application/json'})
                        try:
                            response = urllib.request.urlopen(req, timeout=30)
                        except urllib.error.HTTPError as error:  # 400 拒绝也是正文 JSON
                            response = error
                        result = json.load(response)
                        self.assertFalse(result['ok'])
                        self.assertEqual(result['stage'], 'request')
                        self.assertIn('mirror', result['error'])
                self.assertNotIn('mirror', json.loads(
                    (work / LAYOUT_NAME).read_text(encoding='utf-8'))['nodes']['EDP-001'])
            finally:
                http.shutdown(); http.server_close(); worker.join()

    def test_yaml11_bool_spelling_ids_cannot_bypass_permission(self):
        # 真实复现 ../editor-permission-review.json：许可闸曾用 PyYAML(1.1)
        # 解析 intent，ON/OFF/No 等合法实例 ID 被当 bool，实例"消失"于
        # intent.parts，mirror_contract 跳过导致未登记镜像写盘（同场景的
        # EDP-001 则正确 permission 拒绝）。修复后许可闸与 render 同用
        # ruamel YAML 1.2：拼写 ID 保持字符串、照过三道闸——未登记 +
        # 混合移动整事务拒绝，layout 字节/layout_version/revision_log 均不变。
        self._strip_engine_pump_registration()
        for spelling in ('ON', 'OFF', 'No'):
            with self.subTest(spelling=spelling):
                (self.work / LAYOUT_NAME).write_bytes(self.baseline)
                (self.work / '1#系统.intent.yaml').write_bytes(self.intent_baseline)
                self._rename_node_everywhere('EDP-001', spelling)
                before = (self.work / LAYOUT_NAME).read_bytes()
                result = server.apply_delta(str(self.work), spelling, 30, 0, None, 'x')
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['stage'], 'permission')
                self.assertIn(spelling, result['error'])
                self.assertTrue(result.get('mirror_issues'), result)
                self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)
                before_layout = json.loads(before.decode('utf-8'))
                after_layout = self.layout()
                self.assertEqual(after_layout['layout_version'],
                                 before_layout['layout_version'])
                self.assertEqual(len(after_layout.get('revision_log') or []),
                                 len(before_layout.get('revision_log') or []))

    def test_yaml11_bool_spelling_id_registered_mirror_still_works(self):
        # 拼写 ID 不是禁词：登记在案的类型照常放行（ruamel 1.2 下 ON 就是
        # 字符串实例 ID）——修复不得把合法未加引号 ID 误拒成"bool 冒充"。
        self._rename_node_everywhere('EDP-001', 'ON')
        result = server.apply_delta(str(self.work), 'ON', 0, 0, None, 'y')
        self.assertTrue(result['ok'], result)
        self.assertEqual(self.layout()['nodes']['ON']['mirror'], 'y')
        entry = self.layout()['revision_log'][-1]
        self.assertIn('ON', entry)
        self.assertIn('mirror none→y', entry)

    def test_node_missing_from_intent_parts_rejects_before_write(self):
        # 选中节点缺失于 intent.parts（layout 有、intent 无）：不依赖
        # mirror_contract 对缺失实例的 continue 跳过——写盘前显式拒绝，
        # 字节/版本/日志不动。
        ip = self.work / '1#系统.intent.yaml'
        ip.write_text(ip.read_text(encoding='utf-8').replace(
            '  EDP-001: engine_driven_pump\n', ''), encoding='utf-8')
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'x')
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['stage'], 'permission')
        self.assertIn('intent.parts', result['error'])
        self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)

    def test_instance_type_missing_from_catalog_rejects_before_write(self):
        # 实例类型未在目录登记：与缺失 intent.parts 同口径，写盘前显式
        # 拒绝（不依赖 mirror_contract/check_mirror 的兜底报错形态）。
        ip = self.work / '1#系统.intent.yaml'
        ip.write_text(ip.read_text(encoding='utf-8').replace(
            'EDP-001: engine_driven_pump', 'EDP-001: unregistered_type'),
            encoding='utf-8')
        before = (self.work / LAYOUT_NAME).read_bytes()
        result = server.apply_delta(str(self.work), 'EDP-001', 0, 0, None, 'x')
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['stage'], 'permission')
        self.assertIn('未在目录登记', result['error'])
        self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)

    def test_function_entry_rejects_non_string_mirror_requests(self):
        # apply_delta 本身（不只 HTTP Handler）：False/0/True/容器在函数
        # 入口按类型即拒、无写入——False 不是 none，不得被当"合法无镜像"
        # 处理后 pop 掉镜像字段，绕过 API 声明值域。
        for bad in (False, 0, True, 1.5, ['x'], {'axis': 'x'}, 'z'):
            with self.subTest(mirror=bad):
                before = (self.work / LAYOUT_NAME).read_bytes()
                result = server.apply_delta(str(self.work), 'EDP-001', 30, 0, None, bad)
                self.assertFalse(result['ok'], result)
                self.assertEqual(result['stage'], 'delta')
                self.assertIn('mirror', result['error'])
                self.assertEqual((self.work / LAYOUT_NAME).read_bytes(), before)

    def test_stocked_mirror_false_move_kept_but_false_request_rejected(self):
        # layout 存量值域与 API 请求值域分离：已有 mirror=false 是镜像规范
        # 单源 mirror_policy.check_mirror 允许的"不镜像"声明（与此前
        # renderer 兼容），普通移动放行且原样保留该字段（不 pop、不改写，
        # 版本前进、日志追加）；但 API 请求值域不含 False——mirror=False
        # 请求在 delta 层拒绝，文件字节/layout_version/revision_log 均不变。
        lp = self.work / LAYOUT_NAME
        layout = json.loads(lp.read_text(encoding='utf-8'))
        layout['nodes']['EDP-001']['mirror'] = False
        lp.write_text(json.dumps(layout, ensure_ascii=False, indent=2),
                      encoding='utf-8')
        stocked = lp.read_bytes()
        stocked_layout = json.loads(stocked.decode('utf-8'))

        moved = server.apply_delta(str(self.work), 'EDP-001', 30, 0)
        self.assertTrue(moved['ok'], moved)
        after = self.layout()
        node = after['nodes']['EDP-001']
        self.assertIs(node['mirror'], False)  # 原样保留，不被 pop/改写
        self.assertEqual(node['x'], 600.0)
        self.assertEqual(node['y'], 490)
        self.assertNotEqual(after['layout_version'],
                            stocked_layout['layout_version'])
        self.assertEqual(len(after.get('revision_log') or []),
                         len(stocked_layout.get('revision_log') or []) + 1)

        lp.write_bytes(stocked)
        result = server.apply_delta(str(self.work), 'EDP-001', 30, 0, None, False)
        self.assertFalse(result['ok'], result)
        self.assertEqual(result['stage'], 'delta')
        self.assertIn('mirror', result['error'])
        self.assertEqual(lp.read_bytes(), stocked)
        rejected = self.layout()
        self.assertEqual(rejected['layout_version'],
                         stocked_layout['layout_version'])
        self.assertEqual(len(rejected.get('revision_log') or []),
                         len(stocked_layout.get('revision_log') or []))


class EditorMirrorFullChain(unittest.TestCase):
    """全链正例（真实执行器，HTTP）：由 Codex 实跑。"""

    def test_full_chain_mirror_y_over_http(self):
        with tempfile.TemporaryDirectory() as directory:
            work = make_render_workspace(Path(directory), SMALL)
            server.Handler.workdir = str(work)
            http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
            worker = threading.Thread(target=http.serve_forever, daemon=True)
            worker.start()
            try:
                req = urllib.request.Request(
                    'http://127.0.0.1:%d/api/delta' % http.server_port,
                    data=json.dumps({'node': 'EDP-001', 'mirror': 'y'}).encode(),
                    headers={'Content-Type': 'application/json'})
                result = json.load(urllib.request.urlopen(req, timeout=240))
                self.assertTrue(result['ok'], result)
                self.assertIn('data-mirror="y"', result['svg'])
                layout = json.loads((work / LAYOUT_NAME).read_text(encoding='utf-8'))
                self.assertEqual(layout['nodes']['EDP-001']['mirror'], 'y')
                self.assertIn('mirror none→y', layout['revision_log'][-1])
                self.assertFalse(result['passed'])  # 无感知签认，不冒充过闸
            finally:
                http.shutdown(); http.server_close(); worker.join()


if __name__ == '__main__':
    unittest.main()
