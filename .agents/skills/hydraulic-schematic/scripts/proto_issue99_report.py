"""Generate the single-file issue #99 prototype artifact from measured evidence."""
import base64, io, json
from pathlib import Path
from PIL import Image

ROOT = Path('/root/orca/workspaces/组件库/issue-99')
EV = ROOT / '.artifacts/issue99'
DATA = json.loads((EV / 'final/results.json').read_text())
OUT = EV / 'targeted-optimizer-prototype.html'

IMAGES = {
    'clean_seed': EV / 'clean/sheet-readback.png',
    'clean_budgeted': EV / 'final/clean-budgeted/sheet-readback.png',
    'clean_focused': EV / 'final/clean-focused/sheet-readback.png',
    'v13_seed': EV / 'screen2/fsov-rot90/sheet-readback.png',
    'v13_budgeted': EV / 'final/v13-fsov-budgeted/sheet-readback.png',
    'v13_focused': EV / 'final/v13-fsov-focused/sheet-readback.png',
    'b1_seed': EV / 'screen2/rf-rot0/sheet-readback.png',
    'b1_budgeted': EV / 'final/b1-rf-budgeted/sheet-readback.png',
    'b1_focused': EV / 'final/b1-rf-focused/sheet-readback.png',
}


def uri(path, width=760):
    im = Image.open(path).convert('RGB')
    if im.width > width:
        im.thumbnail((width, int(im.height * width / im.width)))
    buf = io.BytesIO()
    im.save(buf, format='PNG', optimize=True)
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')


IMG = {k: uri(v) for k, v in IMAGES.items()}

CASES = [
    dict(id='clean', key='clean', label='1# 原图（无失败项）', short='正常出图对照',
         finding='首轮校核 fail 0 / warn 6，B3=1.312。这是“首轮即可用”的对照图。',
         objective='无失败项 → 不启动寻优',
         focus='—', moves=0, seed='clean_seed',
         story='定向策略只做一次种子评估就出图；原预算策略仍跑满 200 次，把 B3 从 1.312 推到 1.370，并新增 V10/V19 两项 fail。'),
    dict(id='v13', key='v13-fsov', label='注入①：防火墙关断活门旋转 90°', short='V13 共线重叠',
         finding='V13：管线共线重叠 268 单位，坐标 (308,686)→(590,686) 与 (308,686)→(576,686)。',
         objective='V13 → 消除非豁免共线重叠',
         focus='EMP-001、FSOV-001、PRV-002、TANK-001、CASE 母线、竖廊 320',
         moves=27, seed='v13_seed',
         story='失败项有坐标，可把邻域缩到 270 个动作中的 27 个；但局部挪位 69 次评估后停在局部最小，V13 仍在。原预算策略耗 200 次还新增 V10/V19。这类缺陷需要改规则布局/走线，不能指望邻域微调。'),
    dict(id='b1', key='b1-rf', label='注入②：回油滤旋转 0°', short='B1 交叉超限',
         finding='V19：构图预算 B1 交叉 2 处，放行 1 处。报告没有交叉坐标，原型从同一份几何里取回交叉点。',
         objective='B1 → 交叉数回到放行 1 处',
         focus='CDF-001、PF-001、RF-001、MANIFOLD/PRESS/RET 母线',
         moves=24, seed='b1_seed',
         story='从失败几何恢复交叉点后，邻域缩到 24 个动作；29 次评估、2 步就清掉 B1，官方校核 fail 0，B3 保持在 1.312。原预算策略耗 200 次仍留 V19。'),
]

for c in CASES:
    c['budgeted'] = DATA['cases'][c['key']]['strategies']['budgeted']
    c['focused'] = DATA['cases'][c['key']]['strategies']['focused']

MEASURED = {
    c['id']: {
        'findings': c['finding'],
        'objective': c['objective'],
        'focus': c['focus'],
        'moves': c['moves'],
        'focusEvals': c['focused']['evals'],
        'budgetEvals': c['budgeted']['evals'],
        'focusStop': c['focused']['stop_reason'] or 'no_findings',
        'budgetStop': c['budgeted']['stop_reason'],
        'focusFails': c['focused']['official']['fails'],
        'budgetFails': c['budgeted']['official']['fails'],
        'focusB3': c['focused']['final_bp']['b3'],
        'budgetB3': c['budgeted']['final_bp']['b3'],
    } for c in CASES
}

DRIVER = DATA['driver_baseline']
driver_rows = ''.join(
    f'<tr><td>{k}</td><td>{v["rounds"]}</td><td>{v["elapsed_s"]:.2f} s</td>'
    f'<td>{v["exit_code"]}</td><td>{"—" if not v["tool_failure"] else "规则引擎未布 ACC-001 / ACV-001 / PG-001，第 2 轮中断"}</td></tr>'
    for k, v in DRIVER.items())

case_tabs = ''.join(
    f'<button class="tab" data-case="{c["id"]}" type="button">{c["short"]}</button>'
    for c in CASES)

def sheet(key, title, note, status):
    cls = {'pass': 'ok', 'fail': 'bad', 'warn': 'warn'}[status]
    return (f'<figure class="sheet"><div class="sheet-head"><span class="chip {cls}">{title}</span>'
            f'<span class="mono">{note}</span></div>'
            f'<img src="{IMG[key]}" alt="{title}：{note}"></figure>')

panels = []
for c in CASES:
    b, f = c['budgeted'], c['focused']
    panels.append(f'''
<section class="panel" data-panel="{c['id']}" {'' if c['id']=='clean' else 'hidden'}>
  <div class="finding"><span class="label">当前失败项</span><p>{c['finding']}</p></div>
  <p class="story">{c['story']}</p>
  <div class="sheets">
    {sheet(c['seed'], '注入/种子', '首轮输入', 'warn')}
    {sheet(c['id']+'_budgeted' if c['id']!='clean' else 'clean_budgeted', '原预算寻优',
           f"{b['evals']} 次评估 · fail {len(b['official']['fails'])}", 'fail' if b['official']['fails'] else 'pass')}
    {sheet(c['id']+'_focused' if c['id']!='clean' else 'clean_focused', '按失败项定向',
           f"{f['evals']} 次评估 · fail {len(f['official']['fails'])}", 'fail' if f['official']['fails'] else 'pass')}
  </div>
  <div class="driver-note">驱动器实测：{c['short']} · 原策略 {b['total_wall_s']:.1f} s 端到端（含一次出图+校核），
    定向原型 {f['total_wall_s']:.1f} s。原驱动器第 2 轮 P3 重推规则布局在此输入上失败，无法完成两轮收敛。</div>
</section>''')

matrix_rows = ''.join(
    f'<tr><td>{c["short"]}</td><td>原预算</td><td class="num">{c["budgeted"]["evals"]}</td>'
    f'<td class="num">{c["budgeted"]["elapsed_s"]:.1f} s</td><td class="num">{c["budgeted"]["total_wall_s"]:.1f} s</td>'
    f'<td>{", ".join(c["budgeted"]["official"]["fails"]) or "0"}</td><td class="num">{c["budgeted"]["final_bp"]["b3"]}</td></tr>'
    f'<tr class="alt"><td>{c["short"]}</td><td>定向</td><td class="num">{c["focused"]["evals"]}</td>'
    f'<td class="num">{c["focused"]["elapsed_s"]:.1f} s</td><td class="num">{c["focused"]["total_wall_s"]:.1f} s</td>'
    f'<td>{", ".join(c["focused"]["official"]["fails"]) or "0"}</td><td class="num">{c["focused"]["final_bp"]["b3"]}</td></tr>'
    for c in CASES)

HTML = r'''
<meta name="claude:viewport-fit-sides" content="cover">
<title>寻优目标选择</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&display=swap">
<style>
/* Design plan: an instrument panel for a layout-optimizer decision — narrow palette,
   tabular numbers, one signal hue; sheet images and failure codes carry the story. */
:root {
  --bg: #f3f6f6; --surface: #ffffff; --surface-alt: #e9eff0; --fg: #16272c;
  --muted: #566d74; --line: #cbd9dc; --accent: #0b6b73; --accent-soft: #dcefee;
  --good: #146c4a; --good-soft: #e1f2e9; --warn: #8a5c00; --warn-soft: #fff2d8;
  --bad: #a02d24; --bad-soft: #fae7e4;
  --font-display: 'Space Grotesk', 'Segoe UI', sans-serif;
  --font-body: 'Inter', 'Segoe UI', sans-serif;
  --font-mono: ui-monospace, 'SFMono-Regular', Consolas, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #101a1e; --surface: #17252a; --surface-alt: #1f3036; --fg: #e8f1f2;
  --muted: #a8bec4; --line: #33505a; --accent: #6fd4d3; --accent-soft: #1d3b3f;
  --good: #78d6a8; --good-soft: #1c3b30; --warn: #e8bb68; --warn-soft: #433720;
  --bad: #ff9c91; --bad-soft: #49302f; color-scheme: dark;
} }
:root[data-theme="dark"] {
  --bg: #101a1e; --surface: #17252a; --surface-alt: #1f3036; --fg: #e8f1f2;
  --muted: #a8bec4; --line: #33505a; --accent: #6fd4d3; --accent-soft: #1d3b3f;
  --good: #78d6a8; --good-soft: #1c3b30; --warn: #e8bb68; --warn-soft: #433720;
  --bad: #ff9c91; --bad-soft: #49302f; color-scheme: dark;
}
body { background: var(--bg); color: var(--fg); font-family: var(--font-body);
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 28px 56px; }
.wrap { max-width: 1160px; margin: 0 auto; }
h1, h2, h3 { font-family: var(--font-display); text-wrap: balance; letter-spacing: -0.02em; margin: 0; }
h1 { font-size: clamp(1.8rem, 4vw, 2.7rem); line-height: 1.1; }
h2 { font-size: 1.18rem; margin-bottom: 0.6rem; }
h3 { font-size: 0.98rem; }
p { line-height: 1.62; margin: 0; }
.eyebrow { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.14em;
  color: var(--accent); text-transform: uppercase; margin-bottom: 0.7rem; }
.lede { color: var(--muted); max-width: 68ch; margin-top: 0.8rem; }
.masthead { padding-bottom: 1.6rem; border-bottom: 1px solid var(--line); }
.strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 0.8rem; margin: 1.5rem 0 2rem; }
.figure { background: var(--surface); border: 1px solid var(--line); border-radius: 10px; padding: 1rem 1.1rem; }
.figure .num { font-family: var(--font-display); font-size: 1.7rem; font-weight: 700; font-variant-numeric: tabular-nums; }
.figure .cap { color: var(--muted); font-size: 0.82rem; margin-top: 0.3rem; }
section.block { margin: 2rem 0; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 10px; background: var(--surface); }
table { border-collapse: collapse; width: 100%; min-width: 640px; font-size: 0.84rem; }
th, td { text-align: left; padding: 0.62rem 0.75rem; border-bottom: 1px solid var(--line); }
th { font-family: var(--font-mono); font-size: 0.7rem; letter-spacing: 0.06em; color: var(--muted); text-transform: uppercase; }
tbody tr:last-child td { border-bottom: 0; }
tr.alt { background: var(--surface-alt); }
td.num { font-variant-numeric: tabular-nums; font-family: var(--font-mono); }
.tabs { display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1rem; }
button { font: inherit; cursor: pointer; border: 1px solid var(--line); background: var(--surface);
  color: var(--fg); border-radius: 7px; padding: 0.5rem 0.8rem; }
button:hover { border-color: var(--accent); }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
button.tab[aria-selected="true"] { background: var(--accent); border-color: var(--accent); color: var(--surface); }
button.action { background: var(--accent-soft); border-color: var(--accent); color: var(--fg); font-size: 0.85rem; }
button.action:disabled { opacity: 0.45; cursor: not-allowed; }
.panel { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 1.2rem; }
.finding { border-left: 3px solid var(--warn); background: var(--warn-soft); padding: 0.8rem 1rem; border-radius: 0 8px 8px 0; }
.label { font-family: var(--font-mono); font-size: 0.68rem; letter-spacing: 0.1em; color: var(--muted); text-transform: uppercase; }
.finding p { margin-top: 0.35rem; font-size: 0.9rem; }
.story { margin: 1rem 0; color: var(--muted); font-size: 0.92rem; max-width: 78ch; }
.sheets { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.8rem; }
.sheet { margin: 0; border: 1px solid var(--line); border-radius: 9px; overflow: hidden; background: var(--surface-alt); min-width: 0; }
.sheet-head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem;
  padding: 0.55rem 0.7rem; font-size: 0.78rem; flex-wrap: wrap; }
.mono { font-family: var(--font-mono); color: var(--muted); font-variant-numeric: tabular-nums; }
.chip { border-radius: 999px; padding: 0.2rem 0.55rem; font-size: 0.72rem; font-weight: 600; }
.chip.ok { background: var(--good-soft); color: var(--good); }
.chip.bad { background: var(--bad-soft); color: var(--bad); }
.chip.warn { background: var(--warn-soft); color: var(--warn); }
.sheet img { display: block; width: 100%; max-width: 100%; background: #fff; }
.driver-note { margin-top: 1rem; font-size: 0.82rem; color: var(--muted); }
.demo { display: grid; grid-template-columns: minmax(240px, 1fr) minmax(260px, 1.1fr); gap: 1rem; }
.state, .controls { border: 1px solid var(--line); border-radius: 10px; padding: 1rem; min-width: 0; background: var(--surface); }
.state dl { display: grid; grid-template-columns: max-content 1fr; gap: 0.45rem 0.8rem; margin: 0.8rem 0 0; font-size: 0.85rem; }
.state dt { color: var(--muted); }
.state dd { margin: 0; font-family: var(--font-mono); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
.changed { margin-top: 0.9rem; font-size: 0.84rem; background: var(--accent-soft); padding: 0.6rem 0.7rem; border-radius: 7px; }
.actions { display: flex; flex-wrap: wrap; gap: 0.45rem; margin-top: 0.8rem; }
.walk { margin-top: 1rem; border-top: 1px solid var(--line); padding-top: 0.9rem; }
.walk ol { padding-left: 1.2rem; margin: 0.6rem 0 0; font-size: 0.84rem; color: var(--muted); }
.walk li { margin-bottom: 0.4rem; }
.walk button { padding: 0.3rem 0.6rem; font-size: 0.8rem; }
.decisions { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 0.8rem; }
.decision { border: 1px solid var(--line); border-left: 3px solid var(--accent); border-radius: 8px; padding: 0.9rem 1rem; background: var(--surface); }
.decision h3 { margin-bottom: 0.35rem; }
.decision p { font-size: 0.86rem; color: var(--muted); }
footer { margin-top: 2.4rem; padding-top: 1rem; border-top: 1px solid var(--line); color: var(--muted); font-size: 0.78rem; }
@media (max-width: 760px) { .demo { grid-template-columns: 1fr; } .panel { padding: 0.9rem; } }
</style>

<div class="wrap">
  <header class="masthead">
    <div class="eyebrow">Wayfinder · 决策原型 · 工单 99</div>
    <h1>寻优目标选择</h1>
    <p class="lede">这份原型回答一个问题：布局寻优是否应该按当前失败项挑目标、只搜索会影响它的局部邻域？下面是用现有 1# 输入和两种人为注入问题跑出的真实耗时、评估次数、渲染轮次与最终图面。</p>
  </header>

  <div class="strip">
    <div class="figure"><div class="num">29 / 200</div><div class="cap">B1 交叉案例：定向策略 29 次评估清掉失败项，原预算策略跑满 200 次仍未清掉。</div></div>
    <div class="figure"><div class="num">0 / 2</div><div class="cap">正常图对照：定向策略零寻优直接出图，原预算策略新增 V10 / V19 两项失败。</div></div>
    <div class="figure"><div class="num">1 / 2</div><div class="cap">驱动器实测轮次：失败项出现后第 2 轮规则重推在 1# 输入上工具链失败，没有完成收敛。</div></div>
  </div>

  <section class="block">
    <h2>三组实测对照</h2>
    <div class="table-wrap"><table>
      <thead><tr><th>场景</th><th>策略</th><th>评估次数</th><th>搜索耗时</th><th>端到端</th><th>官方 fail</th><th>B3</th></tr></thead>
      <tbody>__MATRIX__</tbody>
    </table></div>
    <div class="table-wrap" style="margin-top:0.8rem"><table>
      <thead><tr><th>驱动器基线</th><th>轮次</th><th>总耗时</th><th>退出码</th><th>第 2 轮结果</th></tr></thead>
      <tbody>__DRIVER__</tbody>
    </table></div>
  </section>

  <section class="block">
    <h2>图面与场景</h2>
    <div class="tabs" role="tablist" aria-label="场景">__CASE_TABS__</div>
    __PANELS__
  </section>

  <section class="block">
    <h2>自己推一遍目标选择</h2>
    <p class="lede" style="margin:0 0 1rem">按钮按出图流程命名。左侧状态每次点击后完整刷新；“演练”给出三个固定顺序，点当前步即可推进。</p>
    <div class="tabs" role="tablist" aria-label="演练场景">__WALK_TABS__</div>
    <div class="demo">
      <div class="state">
        <span class="label">当前状态 · <span id="demoCase">正常出图对照</span></span>
        <dl>
          <dt>失败项</dt><dd id="stFindings">尚未读取</dd>
          <dt>优化目标</dt><dd id="stObjective">—</dd>
          <dt>可动对象</dt><dd id="stFocus">—</dd>
          <dt>邻域动作</dt><dd id="stMoves">—</dd>
          <dt>评估次数</dt><dd id="stEvals">0</dd>
          <dt>停止条件</dt><dd id="stStop">—</dd>
          <dt>官方校核</dt><dd id="stResult">—</dd>
        </dl>
        <div class="changed" id="stNote">先选一个场景，再读取失败项。</div>
      </div>
      <div class="controls">
        <h3>自由操作</h3>
        <div class="actions">
          <button class="action" data-act="read" type="button">读取失败项</button>
          <button class="action" data-act="objective" type="button">按失败项选目标</button>
          <button class="action" data-act="focus" type="button">限定局部邻域</button>
          <button class="action" data-act="evaluate" data-strategy="focused" type="button">按失败项评估</button>
          <button class="action" data-act="evaluate" data-strategy="budgeted" type="button">按原预算评估</button>
          <button class="action" data-act="check" type="button">核对已通过指标</button>
          <button class="action" data-act="stop" type="button">停止并出图</button>
        </div>
        <div class="walk">
          <span class="label">演练 · <span id="walkName">无缺陷首轮</span></span>
          <div class="actions" id="walkButtons"></div>
          <ol id="walkList"></ol>
        </div>
      </div>
    </div>
  </section>

  <section class="block">
    <h2>需要你定的三件事</h2>
    <div class="decisions">
      <div class="decision"><h3>目标选择</h3><p>是否把“失败项清零且已通过指标不劣化”作为寻优目标，并保留原 B 面板作下限？V13 案例显示局部邻域修不掉共线重叠，需要明确何时交回规则层。</p></div>
      <div class="decision"><h3>停止条件</h3><p>目标一清就停，还是继续抛光总长度？实测继续抛光让正常图新增 V10/V19，并让 B3 从 1.312 升到 1.370。</p></div>
      <div class="decision"><h3>入口优先顺序</h3><p>实测中 <span class="mono">--optimize</span> 会压过种子布局，且第 1 轮就调用规则引擎并因 ACC-001 / ACV-001 / PG-001 未布而失败。种子、定向寻优、两轮收敛应如何排序？</p></div>
    </div>
  </section>

  <footer>一次性原型 · 数据来自 1# 活动输入、两种注入布局与 skill 脚本实测 · 图面为概念图，自动校核通过不等于工程签认。</footer>
</div>

<script>
/* Pure decision module: no DOM, no storage. The page below is a thin shell. */
const MEASURED = __MEASURED__;
const CASE_LABELS = __CASE_LABELS__;
const WALKS = {
  clean: { name: '无缺陷首轮', steps: [
    ['read', null, '读取首轮校核失败项'], ['evaluate', 'focused', '无失败项，直接出图'],
    ['check', null, '核对已通过指标'], ['stop', null, '停止并交付首轮图'] ] },
  v13: { name: 'V13 修不掉', steps: [
    ['read', null, '读取 V13 坐标'], ['objective', null, '选 V13 为目标'],
    ['focus', null, '限定 27 个邻域动作'], ['evaluate', 'focused', '跑 69 次评估'],
    ['check', null, '发现 V13 仍在'], ['stop', null, '交回规则布局层'] ] },
  b1: { name: 'B1 可局部清', steps: [
    ['read', null, '读取 B1 失败'], ['objective', null, '选 B1 为目标'],
    ['focus', null, '恢复交叉点并限定 24 个动作'], ['evaluate', 'focused', '29 次评估'],
    ['check', null, '确认 B1 清零、B3 未劣化'], ['stop', null, '停止并出图'] ] }
};

function initialState(caseId) {
  return { caseId, phase: 'empty', findings: '尚未读取', objective: '—', focus: '—',
    moves: '—', evals: 0, stop: '—', result: '—', note: '先读取失败项。', walkStep: 0 };
}

function reduce(state, action) {
  const m = MEASURED[state.caseId];
  const next = Object.assign({}, state);
  const kind = action.type;
  if (kind === 'walkStep') { next.walkStep = action.step; next.note = '演练已跳到第 ' + (action.step + 1) + ' 步。'; return next; }
  if (kind === 'read') {
    if (state.phase !== 'empty') { next.note = '失败项已经读过；无需重复读取。'; return next; }
    next.phase = 'read'; next.findings = m.findings; next.note = '读取到当前失败项，目标尚未选择。';
    return next;
  }
  if (kind === 'objective') {
    if (state.phase === 'empty') { next.note = '先读取失败项，才能选目标。'; return next; }
    next.phase = 'objective'; next.objective = m.objective; next.note = '目标已锁定：' + m.objective + '。';
    return next;
  }
  if (kind === 'focus') {
    if (state.phase === 'empty') { next.note = '先读取失败项，才知道要围绕什么限定邻域。'; return next; }
    next.phase = 'focus'; next.focus = m.focus; next.moves = m.moves + ' / 270';
    next.note = m.moves ? '邻域从 270 个动作缩到 ' + m.moves + ' 个。' : '没有失败项，不搜索任何邻域。';
    return next;
  }
  if (kind === 'evaluate') {
    if (state.phase === 'empty') { next.note = '先读取失败项；原图不需要评估。'; return next; }
    const targeted = action.strategy === 'focused';
    next.phase = 'evaluated'; next.evals = targeted ? m.focusEvals : m.budgetEvals;
    next.note = targeted
      ? '按失败项评估 ' + next.evals + ' 次，停止原因：' + m.focusStop + '。'
      : '原预算评估 ' + next.evals + ' 次，停止原因：' + m.budgetStop + '。';
    return next;
  }
  if (kind === 'check') {
    if (state.phase === 'empty') { next.note = '还没有候选图面可核对。'; return next; }
    next.phase = 'checked';
    const fails = m.focusFails;
    next.result = 'fail ' + (fails.length ? fails.join(' / ') : '0') + ' · B3 ' + m.focusB3;
    next.note = '已用官方 validate_sheet 复核，不把快速评估当作通过。';
    return next;
  }
  if (kind === 'stop') {
    if (state.phase !== 'checked' && state.phase !== 'evaluated') {
      next.note = '先评估并核对指标，再停止出图。'; return next;
    }
    next.phase = 'stopped'; next.stop = m.focusStop;
    next.note = '停止原因：' + m.focusStop + '；首轮 PNG 可交付审阅，感知回读仍需人工签认。';
    return next;
  }
  return next;
}

/* Page shell */
let caseId = 'clean', state = initialState(caseId), walkId = 'clean';
const $ = (id) => document.getElementById(id);
function renderState() {
  $('demoCase').textContent = CASE_LABELS[caseId];
  $('stFindings').textContent = state.findings;
  $('stObjective').textContent = state.objective;
  $('stFocus').textContent = state.focus;
  $('stMoves').textContent = state.moves;
  $('stEvals').textContent = state.evals;
  $('stStop').textContent = state.stop;
  $('stResult').textContent = state.result;
  $('stNote').textContent = state.note;
  const steps = WALKS[walkId].steps;
  $('walkName').textContent = WALKS[walkId].name;
  $('walkList').innerHTML = steps.map((s, i) =>
    '<li' + (i === state.walkStep ? ' style="color:var(--accent)"' : '') + '>' + s[2] + '</li>').join('');
  $('walkButtons').innerHTML = '';
  steps.forEach((s, i) => {
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = (i + 1) + ' · ' + s[2];
    b.disabled = i !== state.walkStep;
    b.addEventListener('click', () => {
      state = reduce(state, { type: s[0], strategy: s[1] });
      state.walkStep = Math.min(i + 1, steps.length - 1);
      renderState();
    });
    $('walkButtons').appendChild(b);
  });
}
function setCase(id) {
  caseId = id; walkId = id; state = initialState(id);
  document.querySelectorAll('[data-case]').forEach(b =>
    b.setAttribute('aria-selected', String(b.dataset.case === id)));
  document.querySelectorAll('[data-panel]').forEach(p => { p.hidden = p.dataset.panel !== id; });
  document.querySelectorAll('[data-walk]').forEach(b =>
    b.setAttribute('aria-selected', String(b.dataset.walk === id)));
  renderState();
}
document.querySelectorAll('[data-case]').forEach(b =>
  b.addEventListener('click', () => setCase(b.dataset.case)));
document.querySelectorAll('[data-walk]').forEach(b =>
  b.addEventListener('click', () => { walkId = b.dataset.walk; state = initialState(walkId); renderState(); }));
document.querySelectorAll('[data-act]').forEach(b =>
  b.addEventListener('click', () => { state = reduce(state, { type: b.dataset.act, strategy: b.dataset.strategy }); renderState(); }));
setCase('clean');
</script>
'''

HTML = (HTML.replace('__MATRIX__', matrix_rows)
            .replace('__DRIVER__', driver_rows)
            .replace('__CASE_TABS__', case_tabs)
            .replace('__CASE_TABS__', case_tabs)
            .replace('__WALK_TABS__', ''.join(
                f'<button class="tab" data-walk="{c["id"]}" type="button">{WALK_LABEL}</button>'
                for c, WALK_LABEL in zip(CASES, ['无缺陷首轮', 'V13 修不掉', 'B1 可局部清'])))
            .replace('__PANELS__', ''.join(panels))
            .replace('__MEASURED__', json.dumps(MEASURED, ensure_ascii=False))
            .replace('__CASE_LABELS__', json.dumps({c['id']: c['short'] for c in CASES}, ensure_ascii=False)))
OUT.write_text(HTML, encoding='utf-8')
print(OUT, OUT.stat().st_size, 'bytes')
