# -*- coding: utf-8 -*-
"""#60 前端 drawable 夹取：用 Node 实际执行生产脚本做行为测试。

从 editor-proto/index.html 提取 <script>，在 Node vm 上下文（最小 DOM stub）
中原样执行，驱动生产 startDrag/onMove/onUp/refreshLayout；只对
- 实际提交给 POST /api/delta 的 dx/dy（fetch stub 记录请求体），
- 拖动中的预览 transform 与夹取后的 drag.dx/dy，
- 不同 drawable_bounds 下 refreshLayout 后的拖拽状态，
做断言。不做源码字符串断言，不复制实现。node 不在 PATH 时整类 skip
（skip 不等于通过）。
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_HTML = os.path.join(REPO, 'editor-proto', 'index.html')

HARNESS_JS = r''''use strict';
// 行为测试 harness：生产脚本 + 最小 DOM stub + fetch stub。
// /api/sheet 挂起（初始加载链不干扰场景状态）；/api/delta 只记录请求体并
// 回"写盘前拒绝"（stage=delta），避免触发换帧渲染路径。
const fs = require('fs');
const vm = require('vm');

const htmlPath = process.argv[2];
const scenarioName = process.argv[3];
const html = fs.readFileSync(htmlPath, 'utf8');
const s0 = html.indexOf('<script>');
const s1 = html.indexOf('</script>', s0);
if (s0 < 0 || s1 < 0) { console.error('index.html missing <script>'); process.exit(2); }
const src = html.slice(s0 + '<script>'.length, s1);

// ---------- 最小 DOM stub ----------
function makeEl(extra) {
  const el = {
    tagName: 'DIV', id: '', style: {}, checked: false, value: '0',
    disabled: false, textContent: '', innerHTML: '', isConnected: true,
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute() {}, getAttribute() { return null; },
    appendChild() {}, remove() {},
    addEventListener() {}, removeEventListener() {},
    querySelector() { return null; },
    getBoundingClientRect() { return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; },
  };
  return Object.assign(el, extra || {});
}
const elements = {};
function byId(id) { return elements[id] || (elements[id] = makeEl({ id })); }
const documentStub = {
  getElementById: byId,
  createElement: () => makeEl({}),
  createElementNS: () => makeEl({}),
  querySelector() { return null; },
  querySelectorAll() { return []; },
  body: makeEl({ tagName: 'BODY' }),
  activeElement: null,
};
class DOMPoint { // 恒等矩阵：user 坐标 == 事件坐标，便于推演夹取值
  constructor(x, y) { this.x = x; this.y = y; }
  matrixTransform() { return { x: this.x, y: this.y }; }
}
class AbortControllerStub { // 生产 api() 只用 signal/abort()；stub 免除 Node≥15 版本依赖
  constructor() { this.signal = { aborted: false }; }
  abort() { this.signal.aborted = true; }
}
const svgStub = makeEl({ tagName: 'svg' });
svgStub.getScreenCTM = () => ({ inverse() { return this; } });
function makeInst(id) {
  const g = makeEl({ id, ownerSVGElement: svgStub, transforms: [] });
  g.getAttribute = (k) => (k === 'transform' ? 'translate(0,0)' : null);
  g.setAttribute = (k, v) => { if (k === 'transform') g.transforms.push(String(v)); };
  return g;
}

const posted = [];          // POST /api/delta 请求体（生产 postDelta 真实发出）
let routeLayout = null;     // /api/layout 回包（{__fail:true}=读取失败）
let routeSheet = { __hang: true };
function fetchStub(path, opts) {
  if (path === '/api/delta') {
    posted.push(JSON.parse(opts.body));
    return Promise.resolve({ json: () => Promise.resolve({ ok: false, stage: 'delta', error: 'stub' }) });
  }
  if (path === '/api/layout') {
    if (routeLayout && routeLayout.__fail) return Promise.reject(new Error('layout 读取失败（stub）'));
    return Promise.resolve({ json: () => Promise.resolve(routeLayout) });
  }
  if (routeSheet.__hang) return new Promise(() => {});
  return Promise.resolve({ json: () => Promise.resolve(routeSheet) });
}

const ctx = vm.createContext({
  document: documentStub,
  window: { addEventListener() {}, removeEventListener() {} },
  fetch: fetchStub,
  DOMPoint,
  AbortController: AbortControllerStub,
  setTimeout: () => 0, // 不产生真实定时器：微任务排空后进程即退
  clearTimeout: () => {},
  console,
});
vm.runInContext(src, ctx, { filename: 'editor-proto/index.html' });
const bridge = vm.runInContext(`({
  get drag() { return drag; },
  get busy() { return busy; },
  get layoutIndex() { return layoutIndex; },
  set layoutIndex(v) { layoutIndex = v; },
  get drawableBounds() { return drawableBounds; },
  set drawableBounds(v) { drawableBounds = v; },
  el: (id) => document.getElementById(id),
  startDrag, onMove, onUp, refreshLayout,
})`, ctx, { filename: 'harness-bridge' });

// ---------- 场景 ----------
function down(x, y) { return { button: 0, clientX: x, clientY: y, preventDefault() {} }; }

function dragCycle(nodeId, node, bounds, from, to) {
  bridge.layoutIndex = { [nodeId]: Object.assign({}, node) };
  bridge.drawableBounds = bounds;
  const g = makeInst('inst-' + nodeId);
  bridge.startDrag(down(from[0], from[1]), g);
  const started = !!bridge.drag;
  if (started) bridge.onMove({ clientX: to[0], clientY: to[1] });
  return { g, started };
}

async function scenarioNonZeroStart(out) {
  // 非零起点：提交位移必须相对节点自身坐标，而不是把指针绝对值当位移
  const r = dragCycle('P-1', { x: 120, y: 80, w: 60, h: 40, rot: 0 },
    [0, 0, 1000, 800], [120, 80], [150, 90]);
  out.dragStarted = r.started;
  out.transforms = r.g.transforms;
  await bridge.onUp({});
}

async function scenarioGridBottomRight(out) {
  // drawable 1010×810 非栅格 20 倍数：拖到右/下缘（拖动中即被夹到
  // 850/670），栅格吸附会把落点推到 960/780（右/下缘 1020/820 越界），
  // onUp 必须吸附后再次夹取再提交。
  bridge.el('gridSize').value = '20';
  const r = dragCycle('P-1', { x: 100, y: 100, w: 60, h: 40 },
    [0, 0, 1010, 810], [100, 100], [5100, 5100]);
  out.mid = { dx: bridge.drag.dx, dy: bridge.drag.dy };
  out.transforms = r.g.transforms;
  await bridge.onUp({});
}

async function scenarioNonSquareRot(out) {
  // 非方形 200×80：rot 90/270 占位为 80×200，右/下余量按交换后宽高算
  const node = { x: 100, y: 100, w: 200, h: 80 };
  const bounds = [0, 0, 1000, 800];
  const far = [2100, 1600];
  const r90 = dragCycle('P-1', Object.assign({ rot: 90 }, node), bounds, [100, 100], far);
  out.mid90 = { dx: bridge.drag.dx, dy: bridge.drag.dy };
  out.preview90 = r90.g.transforms[0];
  await bridge.onUp({});
  dragCycle('P-1', Object.assign({ rot: 270 }, node), bounds, [100, 100], far);
  out.mid270 = { dx: bridge.drag.dx, dy: bridge.drag.dy };
  await bridge.onUp({});
  dragCycle('P-1', Object.assign({ rot: 90 }, node), bounds, [100, 100], [-1900, -2100]);
  await bridge.onUp({});
}

async function scenarioUnknownBounds(out) {
  const node = { x: 100, y: 100, w: 60, h: 40 };
  const tryDrag = () => {
    bridge.layoutIndex = { 'P-1': Object.assign({}, node) };
    const g = makeInst('inst-P-1');
    bridge.startDrag(down(100, 100), g);
    if (!bridge.drag) return false;
    bridge.onMove({ clientX: 2100, clientY: 2100 });
    return true;
  };
  // 合法契约对照组：拖拽放行且夹取提交
  routeLayout = { nodes: { 'P-1': node }, canvas: { width: 1200, height: 900 },
                  drawable_bounds: [0, 0, 1000, 800], conns: {} };
  const valid = { refreshOk: await bridge.refreshLayout(), bounds: bridge.drawableBounds, dragStarted: tryDrag() };
  if (valid.dragStarted) await bridge.onUp({});
  out.valid = valid;
  // 缺 drawable_bounds：layout 本身有效（refreshLayout true，镜像/旋转不受影响），但拖拽禁用
  routeLayout = { nodes: { 'P-1': node }, canvas: {}, conns: {} };
  out.missing = { refreshOk: await bridge.refreshLayout(), bounds: bridge.drawableBounds, dragStarted: tryDrag() };
  // 非有限元素
  routeLayout = { nodes: { 'P-1': node }, drawable_bounds: [0, 0, null, 800] };
  out.nonfinite = { refreshOk: await bridge.refreshLayout(), bounds: bridge.drawableBounds, dragStarted: tryDrag() };
  // 边缘倒置（xmin>xmax）
  routeLayout = { nodes: { 'P-1': node }, drawable_bounds: [1000, 0, 0, 800] };
  out.reversed = { refreshOk: await bridge.refreshLayout(), bounds: bridge.drawableBounds, dragStarted: tryDrag() };
  // 读取失败：refreshLayout false 且拖拽禁用
  routeLayout = { __fail: true };
  out.fail = { refreshOk: await bridge.refreshLayout(), bounds: bridge.drawableBounds, dragStarted: tryDrag() };
  out.postedTotal = posted.length;
}

const scenarios = {
  nonzero_start: scenarioNonZeroStart,
  grid_bottom_right: scenarioGridBottomRight,
  nonsquare_rot: scenarioNonSquareRot,
  unknown_bounds: scenarioUnknownBounds,
};

(async () => {
  try {
    byId('alignOn').checked = false; // 对齐吸附不在本轮验收口径：统一关闭保证确定性
    byId('gridSize').value = '0';
    const fn = scenarios[scenarioName];
    if (!fn) throw new Error('unknown scenario: ' + scenarioName);
    const out = {};
    await fn(out);
    out.posted = posted;
    process.stdout.write(JSON.stringify(out));
  } catch (err) {
    console.error('[harness] ' + ((err && err.stack) || err));
    process.exit(1);
  }
})();
'''


@unittest.skipUnless(shutil.which('node'), 'node 不在 PATH：无法执行前端行为测试')
class EditorDragDrawableClampTest(unittest.TestCase):
    """每个场景起一个 Node 子进程，执行 index.html 的生产脚本。"""

    def run_harness(self, scenario):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, 'harness.js')
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(HARNESS_JS)
            try:
                proc = subprocess.run(
                    ['node', path, INDEX_HTML, scenario],
                    capture_output=True, text=True, encoding='utf-8',
                    timeout=60, cwd=REPO)
            except subprocess.TimeoutExpired:
                self.fail('node harness(%s) 超时' % scenario)
        if proc.returncode != 0:
            self.fail('node harness(%s) 失败 rc=%s:\n%s\n%s'
                      % (scenario, proc.returncode, proc.stdout, proc.stderr))
        return json.loads(proc.stdout)

    def test_nonzero_start_commit_is_relative_to_node(self):
        out = self.run_harness('nonzero_start')
        self.assertTrue(out['dragStarted'])
        # 起点 (120,80)，指针移到 (150,90)：提交位移 (30,10)，落点 (150,90) 在 drawable 内
        self.assertEqual(out['posted'], [{'node': 'P-1', 'dx': 30, 'dy': 10}])
        self.assertEqual(out['transforms'][0], 'translate(30,10) translate(0,0)')

    def test_grid_snap_at_non_aligned_bottom_right_clamps(self):
        out = self.run_harness('grid_bottom_right')
        # 拖动中即夹取：位移恒 ≤ drawable 右/下缘
        self.assertEqual(out['mid'], {'dx': 850, 'dy': 670})
        # 20 栅格吸附会把落点推到 960/780（右/下缘 1020/820 越界）；提交必须再夹回
        self.assertEqual(out['posted'], [{'node': 'P-1', 'dx': 850, 'dy': 670}])
        self.assertEqual(100 + out['posted'][0]['dx'] + 60, 1010)  # 右缘 == xmax
        self.assertEqual(100 + out['posted'][0]['dy'] + 40, 810)   # 下缘 == ymax

    def test_nonsquare_rot90_270_swaps_placeholder(self):
        out = self.run_harness('nonsquare_rot')
        # rot 90/270 占位 80×200：右缘余量按 ew=80（820 而非 700）、下缘按 eh=200（500 而非 620）
        self.assertEqual(out['mid90'], {'dx': 820, 'dy': 500})
        self.assertEqual(out['mid270'], {'dx': 820, 'dy': 500})
        self.assertEqual(out['preview90'], 'translate(820,500) translate(0,0)')
        self.assertEqual(out['posted'], [
            {'node': 'P-1', 'dx': 820, 'dy': 500},    # rot 90
            {'node': 'P-1', 'dx': 820, 'dy': 500},    # rot 270 同式
            {'node': 'P-1', 'dx': -100, 'dy': -100},  # 反向夹到 drawable 左/上缘
        ])

    def test_unknown_bounds_disable_drag_and_write(self):
        out = self.run_harness('unknown_bounds')
        # 合法契约：refreshLayout 生效、拖拽放行、夹取提交
        self.assertTrue(out['valid']['refreshOk'])
        self.assertEqual(out['valid']['bounds'], [0, 0, 1000, 800])
        self.assertTrue(out['valid']['dragStarted'])
        # 无契约各态：drawableBounds 保持 null，拖拽一律禁用（不写）
        for case in ('missing', 'nonfinite', 'reversed', 'fail'):
            self.assertIsNone(out[case]['bounds'], case)
            self.assertFalse(out[case]['dragStarted'], case)
        # 缺契约 ≠ 布局刷新失败：节点有效时 refreshLayout 仍 true（镜像/旋转不受影响）
        self.assertTrue(out['missing']['refreshOk'])
        # 读取失败仍是刷新失败
        self.assertFalse(out['fail']['refreshOk'])
        # 全程只有合法对照那一笔提交，且带夹取值
        self.assertEqual(out['postedTotal'], 1)
        self.assertEqual(out['posted'][0], {'node': 'P-1', 'dx': 840, 'dy': 660})


if __name__ == '__main__':
    unittest.main()
