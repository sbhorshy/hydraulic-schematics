# -*- coding: utf-8 -*-
"""#60 旋转几何缺口：参考线/吸附/选中框与旋转后占位一致。

非方形组件 rot 90/270 的占位宽高互换（与服务端 apply_delta 的 drawableSize
同式）。本模块从 editor-proto/index.html 提取 <script>，在 Node vm（最小
DOM stub）中原样执行生产脚本，驱动 select/drawSel/startDrag/onMove/onUp
真实路径，断言：
- 被拖组件（rot90）按交换后占位的边/中心吸附目标，提交位移随之；
- 吸附目标自身 rot90 时，参考线候选按交换后宽高计算；
- drawHints 参考线与 drawSel 选中框的实际 SVG 属性（行为断言，不做源码
  字符串断言，不复制实现）；
- 吸附/栅格把落点推越 drawable 边界时仍按旋转后占位夹回；
- rot 0/180 对照：占位不交换。
node 不在 PATH 时整类 skip（skip 不等于通过）。
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
// 与 test_editor_drag_frontend 同思路；此处扩展 SVG 元素属性记录，
// 用于 drawHints 参考线 / drawSel 选中框的实际属性断言。
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

// ---------- SVG 元素 stub：记录 setAttribute 写入的实际属性 ----------
function makeSvgNode(tag) {
  const el = {
    tagName: String(tag).toUpperCase(), id: '', attrs: {}, children: [],
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute(k, v) { el.attrs[k] = String(v); },
    getAttribute(k) { return (k in el.attrs) ? el.attrs[k] : null; },
    appendChild(c) { el.children.push(c); return c; },
    remove() {}, addEventListener() {}, removeEventListener() {},
    querySelector() { return null; },
    getBoundingClientRect() { return { left: 0, top: 0, right: 0, bottom: 0, width: 0, height: 0 }; },
  };
  Object.defineProperty(el, 'innerHTML', { // 生产 clearGuides 以 innerHTML='' 清层
    get() { return el.children.length ? '<stub/>' : ''; },
    set(v) { if (v === '') el.children.length = 0; },
  });
  return el;
}

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

const svgChildren = [];
const svgStub = makeSvgNode('svg');
svgStub.getScreenCTM = () => ({ inverse() { return this; } });
svgStub.appendChild = c => { svgChildren.push(c); return c; };
svgStub.querySelector = sel => sel === '#proto-guides'
  ? (svgChildren.find(c => c.id === 'proto-guides') || null) : null;

const documentStub = {
  getElementById: byId,
  createElement: () => makeEl({}),
  createElementNS: (_ns, tag) => makeSvgNode(tag),
  querySelector() { return null; },
  querySelectorAll() { return []; },
  body: makeEl({ tagName: 'BODY' }),
  activeElement: null,
};
byId('stage').querySelector = sel => (sel === 'svg' ? svgStub : null);

class DOMPoint { // 恒等矩阵：user 坐标 == 事件坐标，便于推演吸附值
  constructor(x, y) { this.x = x; this.y = y; }
  matrixTransform() { return { x: this.x, y: this.y }; }
}
class AbortControllerStub {
  constructor() { this.signal = { aborted: false }; }
  abort() { this.signal.aborted = true; }
}

const posted = [];          // POST /api/delta 请求体（生产 postDelta 真实发出）
function fetchStub(path, opts) {
  if (path === '/api/delta') {
    posted.push(JSON.parse(opts.body));
    return Promise.resolve({ json: () => Promise.resolve({ ok: false, stage: 'delta', error: 'stub' }) });
  }
  if (path === '/api/layout') return Promise.resolve({ json: () => Promise.resolve({ nodes: {} }) });
  return new Promise(() => {}); // /api/sheet 挂起
}

const ctx = vm.createContext({
  document: documentStub,
  window: { addEventListener() {}, removeEventListener() {} },
  fetch: fetchStub,
  DOMPoint,
  AbortController: AbortControllerStub,
  setTimeout: () => 0,
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
  startDrag, onMove, onUp, refreshLayout, select, deselect,
})`, ctx, { filename: 'harness-bridge' });

// ---------- 驱动 ----------
function makeInst(id) {
  const g = makeEl({ id, ownerSVGElement: svgStub, transforms: [] });
  g.getAttribute = (k) => (k === 'transform' ? 'translate(0,0)' : null);
  g.setAttribute = (k, v) => { if (k === 'transform') g.transforms.push(String(v)); };
  return g;
}
function down(x, y) { return { button: 0, clientX: x, clientY: y, preventDefault() {} }; }

function snapNode(el) {
  const out = Object.assign({ tag: el.tagName }, el.attrs);
  out.cls = out['class'] || ''; // class 属性统一以 cls 呈现，删除原始键保持快照单形
  delete out['class'];
  return out;
}
function guidesSnapshot() {
  const layer = svgStub.querySelector('#proto-guides');
  return layer ? layer.children.map(snapNode) : [];
}

// 完整一轮：装填布局 → startDrag → onMove（产生拖动中提示线）；不松手
function beginDrag(nodes, draggedId, bounds, from, to) {
  bridge.layoutIndex = JSON.parse(JSON.stringify(nodes));
  bridge.drawableBounds = bounds;
  const g = makeInst('inst-' + draggedId);
  bridge.startDrag(down(from[0], from[1]), g);
  const started = !!bridge.drag;
  if (started) bridge.onMove({ clientX: to[0], clientY: to[1] });
  return { g, started };
}

// ---------- 场景 ----------
// 被拖组件 rot90（200×80 → 占位 80×200）；目标 rot0 100×300 @ (400,100)。
// 右缘吸附目标左缘 400；中心吸附目标中线 450。
async function scenarioHintsSnapRot90Dragged(out) {
  const nodes = {
    'P-1': { x: 100, y: 100, w: 200, h: 80, rot: 90 },
    'T-2': { x: 400, y: 100, w: 100, h: 300, rot: 0 },
  };
  const bounds = [0, 0, 1000, 800];
  // 指针 (325,130)：rot90 右缘 = 100+225+80 = 405，距 400 差 5 → 吸附后 nx=320
  const r = beginDrag(nodes, 'P-1', bounds, [100, 100], [325, 130]);
  out.started = r.started;
  out.hintsEdge = guidesSnapshot();
  await bridge.onUp({});
  out.guidesAfterUpEdge = guidesSnapshot();
  // 指针 (415,130)：rot90 中心 = 100+315+40 = 455，距 450 差 5 → 吸附后 nx=410
  beginDrag(nodes, 'P-1', bounds, [100, 100], [415, 130]);
  out.hintsCenter = guidesSnapshot();
  await bridge.onUp({});
  out.guidesAfterUpCenter = guidesSnapshot();
}

// 吸附目标自身 rot90（200×80 → 占位 80×200 @ (400,100)）：
// 候选 = v 400/440/480、h 100/200/300；被拖组件 rot0 60×40。
async function scenarioSnapTargetRot90(out) {
  const nodes = {
    'P-1': { x: 100, y: 100, w: 60, h: 40, rot: 0 },
    'T-2': { x: 400, y: 100, w: 200, h: 80, rot: 90 },
  };
  beginDrag(nodes, 'P-1', [0, 0, 1000, 800], [100, 100], [475, 205]);
  out.hints = guidesSnapshot();
  await bridge.onUp({});
}

// drawSel 选中框实际 SVG 属性：rot 0/180 不交换、90/270 交换、mirror 不二次翻转。
async function scenarioDrawSel(out) {
  const base = { x: 100, y: 100, w: 200, h: 80 };
  const cases = [
    { rot: 0 }, { rot: 90 }, { rot: 180 }, { rot: 270 },
    { rot: 90, mirror: 'x' }, { rot: 270, mirror: 'y' }, { rot: 0, mirror: 'y' },
  ];
  out.rects = cases.map(c => {
    bridge.layoutIndex = { 'P-1': Object.assign({}, base, c) };
    bridge.select('P-1');
    const layer = svgStub.querySelector('#proto-guides');
    return { rot: c.rot || 0, mirror: c.mirror || 'none',
             rect: snapNode(layer.children[layer.children.length - 1]) };
  });
}

// rot 0/180 对照：占位不交换——左缘吸附同 rot0、中心按 200 宽吸附、
// 夹取余量按未交换宽高（dx≤700、dy≤620）。
async function scenarioRot0Rot180(out) {
  const mk = rot => ({
    'P-1': { x: 100, y: 100, w: 200, h: 80, rot },
    'T-2': { x: 400, y: 100, w: 100, h: 300, rot: 0 },
  });
  const bounds = [0, 0, 1000, 800];
  beginDrag(mk(0), 'P-1', bounds, [100, 100], [405, 130]);   // rot0 左缘 405→400（基线）
  await bridge.onUp({});
  beginDrag(mk(180), 'P-1', bounds, [100, 100], [405, 130]); // rot180 左缘吸附同 rot0
  await bridge.onUp({});
  // rot180 中心（nx+100）距 450 差 5：指针 (345,205) → 吸附 nx=350、ny=210
  beginDrag(mk(180), 'P-1', bounds, [100, 100], [345, 205]);
  await bridge.onUp({});
  // rot180 夹取按未交换 200×80：拖出界 → dx≤700、dy≤620
  beginDrag(mk(180), 'P-1', bounds, [100, 100], [5100, 5100]);
  out.mid180 = { dx: bridge.drag.dx, dy: bridge.drag.dy };
  await bridge.onUp({});
}

// 吸附/栅格把落点推越 drawable 边界：对齐→栅格→drawable 夹取次序兜底，
// 提交值按旋转后占位（80×200）夹回右/下缘。
async function scenarioSnapOverrunClamped(out) {
  bridge.el('gridSize').value = '20';
  const nodes = {
    'P-1': { x: 100, y: 100, w: 200, h: 80, rot: 90 }, // 占位 80×200：dx≤820、dy≤500
    'T-2': { x: 930, y: 610, w: 50, h: 50, rot: 0 },
  };
  // 指针 (925,605)：拖动中先夹到 dx=820/dy=500（nx=920/ny=600），
  // 松手吸附 930/610、栅格推到 940/620，最终 drawable 夹回 820/500。
  beginDrag(nodes, 'P-1', [0, 0, 1000, 800], [100, 100], [925, 605]);
  out.mid = { dx: bridge.drag.dx, dy: bridge.drag.dy };
  await bridge.onUp({});
}

const scenarios = {
  hints_snap_rot90_dragged: scenarioHintsSnapRot90Dragged,
  snap_target_rot90: scenarioSnapTargetRot90,
  drawsel_rects: scenarioDrawSel,
  rot0_rot180_no_swap: scenarioRot0Rot180,
  snap_overrun_clamped: scenarioSnapOverrunClamped,
};

(async () => {
  try {
    byId('alignOn').checked = true; // 本模块专测对齐吸附：全程开启
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

GUIDE_LINE_AT = lambda c: {'tag': 'LINE', 'cls': 'proto-guide',
                           'x1': str(c), 'y1': '0', 'x2': str(c), 'y2': '1000'}


@unittest.skipUnless(shutil.which('node'), 'node 不在 PATH：无法执行前端行为测试')
class EditorRotatedGuidesTest(unittest.TestCase):
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

    def test_rot90_dragged_snaps_edge_and_center_with_swapped_placeholder(self):
        out = self.run_harness('hints_snap_rot90_dragged')
        self.assertTrue(out['started'])
        # 拖动中提示线：rot90 占位右缘 405 距目标左缘 400 差 5 → 提示线画在 400
        # （若仍按未交换 200 宽，边 425/525 距最近候选均 25，无线条）
        self.assertEqual(out['hintsEdge'], [GUIDE_LINE_AT(400)])
        # 松手吸附：右缘 405→400，提交 dx=320-100=220（未交换宽高时无吸附，dx=225）
        self.assertEqual(out['posted'][0], {'node': 'P-1', 'dx': 220, 'dy': 30})
        self.assertEqual(100 + out['posted'][0]['dx'] + 80, 400)  # 旋转后右缘贴合目标左缘
        # 中心吸附：rot90 中心 455→450，提交 dx=310（未交换时中心 515 无吸附，dx=315）
        self.assertEqual(out['hintsCenter'], [GUIDE_LINE_AT(450)])
        self.assertEqual(out['posted'][1], {'node': 'P-1', 'dx': 310, 'dy': 30})
        self.assertEqual(100 + out['posted'][1]['dx'] + 40, 450)  # 旋转后中心对齐目标中线
        # 松手定格参考线落在吸附结果上（提示线 + 定格线各一条）
        self.assertEqual(out['guidesAfterUpEdge'], [GUIDE_LINE_AT(400)] * 2)
        self.assertEqual(out['guidesAfterUpCenter'], [GUIDE_LINE_AT(450)] * 2)

    def test_rot90_target_offers_swapped_edge_candidates(self):
        out = self.run_harness('snap_target_rot90')
        # 提示线：拖动中左/上缘已贴到 rot90 目标的旋转后右缘 480、下缘 200
        self.assertEqual(out['hints'], [
            GUIDE_LINE_AT(480),
            {'tag': 'LINE', 'cls': 'proto-guide',
             'x1': '0', 'y1': '200', 'x2': '1400', 'y2': '200'},
        ])
        # 提交：左缘吸到 480（=400+80 旋转后右缘）、上缘吸到 200（=100+200 旋转后下缘）
        # （未交换候选 400/500/600、100/140/180 时会得到 dx=395/dy=105）
        self.assertEqual(out['posted'], [{'node': 'P-1', 'dx': 380, 'dy': 100}])

    def test_drawsel_rect_uses_rotated_placeholder_without_reoffset(self):
        out = self.run_harness('drawsel_rects')
        expected = {
            (0, 'none'): ('200', '80'), (90, 'none'): ('80', '200'),
            (180, 'none'): ('200', '80'), (270, 'none'): ('80', '200'),
            (90, 'x'): ('80', '200'),   # mirror 不二次翻转尺寸
            (270, 'y'): ('80', '200'),
            (0, 'y'): ('200', '80'),
        }
        self.assertEqual(len(out['rects']), len(expected))
        for r in out['rects']:
            rect = r['rect']
            # x/y = 旋转后框左上：原点不因旋转/镜像再次偏移
            self.assertEqual(rect['x'], '100', r)
            self.assertEqual(rect['y'], '100', r)
            self.assertEqual(rect['cls'], 'proto-sel', r)
            w, h = expected[(r['rot'], r['mirror'])]
            self.assertEqual(rect['width'], w, r)
            self.assertEqual(rect['height'], h, r)

    def test_rot0_and_rot180_keep_unswapped_placeholder(self):
        out = self.run_harness('rot0_rot180_no_swap')
        # rot0 与 rot180 左缘吸附同式（占位 200×80 不交换）
        self.assertEqual(out['posted'][0], {'node': 'P-1', 'dx': 300, 'dy': 30})
        self.assertEqual(out['posted'][1], {'node': 'P-1', 'dx': 300, 'dy': 30})
        # rot180 中心吸附按未交换 200 宽（nx+100 对 450）；交换误判会吸到别处
        self.assertEqual(out['posted'][2], {'node': 'P-1', 'dx': 250, 'dy': 110})
        # rot180 夹取按未交换宽高：dx≤700、dy≤620（交换误判会得到 820/500）
        self.assertEqual(out['mid180'], {'dx': 700, 'dy': 620})
        self.assertEqual(out['posted'][3], {'node': 'P-1', 'dx': 700, 'dy': 620})

    def test_snap_overrun_still_clamped_to_rotated_bounds(self):
        out = self.run_harness('snap_overrun_clamped')
        # 拖动中即按旋转后占位（80×200）夹取
        self.assertEqual(out['mid'], {'dx': 820, 'dy': 500})
        # 吸附 930/610 + 栅格 20 推到 940/620（越界），drawable 夹取最后兜底
        self.assertEqual(out['posted'], [{'node': 'P-1', 'dx': 820, 'dy': 500}])
        self.assertEqual(100 + out['posted'][0]['dx'] + 80, 1000)  # 右缘 == xmax
        self.assertEqual(100 + out['posted'][0]['dy'] + 200, 800)  # 下缘 == ymax


if __name__ == '__main__':
    unittest.main()
