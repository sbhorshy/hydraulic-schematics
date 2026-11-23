/* 一次性原型（issue 102）：回读页四个版本的对照页。只为把决定摆到眼前，不做打磨。 */
(function () {
  'use strict';
  const DATA = JSON.parse(document.getElementById('data').textContent);
  const app = document.getElementById('app');
  const L = DATA.labels;
  const HELD = ['disclosure', 'unchecked'];
  const ORDER = ['connection', 'occlusion', 'label', 'layout', 'disclosure', 'unchecked'];
  const RULES = ['class', 'location', 'line', 'impact'];
  const PATHS = ['local', 'route', 'agent', 'disclose', 'recheck'];
  const LEVELS = { finding: '问题点', objects: '对象', route: '走线' };
  const CLASS_LEVEL = { connection: 'route', occlusion: 'objects', label: 'objects', layout: 'route', disclosure: 'objects', unchecked: 'objects' };
  const LEVEL_NOTE = {
    finding: '只框出错的那一点（红），四周各留 24 px。用来确认缺陷是真的。',
    objects: '加上出问题的元件本体（蓝虚线框）和它的标签（紫点线框）。用来知道要动哪个对象。',
    route: '再加上附近的走线（蓝线）。用来决定怎么改：挪、绕，还是恢复朝向。',
  };
  const VARIANTS = [
    { id: 'A', name: '现状', full: 'A · 现状回读页', desc: '官方 readback.html 原样：完整图 → 对象清单 → 局部图。' },
    { id: 'B', name: '按严重度平铺', full: 'B · 按严重度平铺', desc: '只做一件事：把失败条目排到清单最前，逐条列出。不合并、不标新增、不给建议。' },
    { id: 'C', name: '按类别分诊', full: 'C · 按类别分诊', desc: '同处的条目并成一个问题，按 连接语义 → 遮挡 → 标签重叠 → 版式 排；每个问题带原因、嫌疑对象、建议和三级局部图。' },
    { id: 'D', name: '按位置的修图路线', full: 'D · 按位置的修图路线', desc: '全图上打编号，按位置排成一条路线；每站带建议，下面是本轮修图单和差分范围。' },
  ];
  const S = {
    mode: 'browse', browse: 'page', sheet: 'label', ref: 'base', variant: 'C',
    rule: 'class', persisting: 'inline', notes: 'inline',
    level: 'objects', byClass: true, reach: 'normal', hideSuspects: false,
    tab: 'order', preview: null, fixed: {}, tier: {}, cause: true, trialN: 8, trial: null, results: [],
  };
  (function init() {
    const want = (new URLSearchParams(location.search).get('variant') || location.hash.replace(/^#(?:variant=)?/, '')).toUpperCase();
    if (VARIANTS.some(v => v.id === want)) S.variant = want;
  })();

  // ---------- small helpers ----------
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.prototype.slice.call((root || document).querySelectorAll(sel));
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const round = x => Math.round(x);
  const clockText = ms => { const s = Math.max(0, Math.floor(ms / 1000)); return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); };
  const shuffle = a => a.slice().sort(() => Math.random() - 0.5);
  const V = () => VARIANTS.find(v => v.id === S.variant);
  const D = () => DATA.sheets[S.sheet];
  const HELD_TEXT = { disclosure: '输入事实，布局改不了', unchecked: '上游有未决项，修好后自动恢复校核' };

  let itemCache = { sheet: null, map: null };
  function itemById(id) {
    if (itemCache.sheet !== S.sheet) itemCache = { sheet: S.sheet, map: new Map(D().triage.items.map(i => [i.id, i])) };
    return itemCache.map.get(id);
  }
  // What the views show depends on the frozen reference; orders and repair lists always describe the sheet itself.
  function probs() { const d = D(); return S.ref === 'none' ? d.blind.problems : S.sheet === 'base' ? d.behind[S.ref].problems : d.triage.problems; }
  function resolved() { const d = D(); return S.ref === 'none' ? [] : S.sheet === 'base' ? d.behind[S.ref].resolved : d.triage.resolved; }
  function summa() { const d = D(); return S.ref === 'none' ? d.blind.summary : S.sheet === 'base' ? d.behind[S.ref].summary : d.triage.summary; }
  function probById(id) { return probs().find(p => p.id === id); }
  function ordered() {
    const have = new Map(probs().map(p => [p.id, p])), ids = D().triage.orders[S.rule + '|' + S.persisting + '|' + S.notes] || [];
    return ids.map(id => have.get(id)).filter(Boolean);
  }
  function flatItems() {
    const rank = { fail: 0, warn: 1 };
    return D().triage.items.filter(i => !HELD.includes(i.class)).sort((a, b) => (rank[a.result] - rank[b.result]) || a.id.localeCompare(b.id));
  }
  function ctxOf(p, reach) { return p.context_reach ? p.context_reach[reach || S.reach] : p.context; }
  function levelFor(p) {
    const c = ctxOf(p) || {};
    if (S.byClass && c[CLASS_LEVEL[p.class]]) return CLASS_LEVEL[p.class];
    return c[S.level] ? S.level : 'finding';
  }
  // lead_in names what changed since the last version; text is the fix itself.
  function fullText(p) { return (S.hideSuspects ? '' : p.suggestion.lead_in + ' ') + p.suggestion.text; }
  function diffNote() {
    return D().diff_ready ? '<span class="ok">图像差分可用</span>' : '<span class="no">图像差分不可用（拓扑覆盖未通过）→ 先修连接语义</span>';
  }

  // ---------- chips ----------
  const sev = r => '<span class="sev ' + r + '">' + esc(L.severity[r] || r) + '</span>';
  const cls = c => '<span class="cls ' + c + '">' + esc(L.class[c] || c) + '</span>';
  const st = s => s === 'unknown' ? '' : '<span class="state ' + s + '">' + (s === 'moved' ? '仍在 · 随对象移动' : esc(L.state[s])) + '</span>';
  const pathTag = p => { const k = pathOf(p); return '<span class="path ' + k + '">' + ((k === 'local' || k === 'route') ? '结构化 · ' : '') + esc(L.path[k]) + '</span>'; };
  // ---------- fix paths (decision three) ----------
  const WEIGHT = { agent: 4, route: 3, local: 2, recheck: 1, disclose: 0 };
  const SOLO = {};
  DATA.kinds.forEach(r => { SOLO[[r.class, r.kind, r.result].join('|')] = r.path; });
  // One finding on its own, with whatever the visitor changed on the tiers panel.
  function solo(kind) { return S.tier[kind.join('|')] || SOLO[kind.join('|')] || 'agent'; }
  // A problem's path, re-derived the way the module does it: its new failing findings win over the
  // finding the fix aims at, except the label symptoms when the aim is the layout cause.
  function pathOf(p) {
    const s = p.suggestion;
    if (!s.fresh_kinds) return s.fix_path;
    const kinds = !S.cause && s.cause ? s.fresh_kinds.concat(s.symptom_kinds || []) : s.fresh_kinds;
    return kinds.map(solo).sort((a, b) => WEIGHT[b] - WEIGHT[a])[0];
  }
  const chip = x => '<span class="chip">' + esc(x) + '</span>';

  // ---------- problem card (C) ----------
  function why(p, rank) {
    if (HELD.includes(p.class)) return L.why[p.class];
    const lvl = p.severity === 'fail' ? '失败' : '提示';
    const first = ordered().find(q => q.severity === p.severity && q.class === p.class) === p;
    if (pathOf(p) === 'disclose') return '只是提示，不必修；' + (S.notes === 'tail' ? '所以排在最后' : '留在同类里，和别的提示一起看');
    if (S.rule === 'location') return lvl + '里按位置' + (rank > 1 ? '依次往下' : '最靠前') + '（从上到下、从左到右）';
    if (S.rule === 'line') return lvl + '里按所在主线排' + (first ? '在最前' : '在后');
    if (S.rule === 'impact') return lvl + '里一条动作能消掉 ' + p.items.length + ' 条条目' + (rank > 1 ? '，比前一项少' : '，最多');
    return (first ? lvl + ' · ' : '同为' + L.class[p.class] + '，位置靠后 · ') + (first ? L.why[p.class] : L.why[p.class]);
  }
  function levelTabs(p, level, attr, extra) {
    const c = ctxOf(p) || {};
    return Object.keys(LEVELS).map(k => '<button class="seg ' + (k === level ? 'on ' : '') + (extra || '') + '" ' + attr + '="' + k + '" data-pid="' + esc(p.id) + '"' +
      (c[k] ? '' : ' disabled title="这一级没有可看的内容"') + '>' + LEVELS[k] + '</button>').join('');
  }
  function card(p, rank) {
    const level = levelFor(p), items = (p.items || []).map(itemById).filter(Boolean);
    const scope = p.scope.nodes.concat(p.scope.edges);
    return '<article class="card ' + p.severity + '" id="card-' + p.id + '" data-pid="' + p.id + '">' +
      '<header><span class="num">' + rank + '</span>' + sev(p.severity) + st(p.state) + '<span class="zone">' + esc(L.class[p.class]) + ' · ' + esc(p.zone || '全图') + '</span>' +
      (HELD.includes(p.class) ? '' : pathTag(p)) + '</header>' +
      '<h3>' + esc(p.title) + '</h3><div class="why">排在这里：' + esc(why(p, rank)) + '</div>' +
      '<div class="body"><div>' +
      '<div class="levels">' + levelTabs(p, level, 'data-level') + '<span class="sp"></span><button class="mini" data-zoom="' + p.id + '">放大</button><button class="mini" data-map="' + p.id + '">全图定位</button></div>' +
      '<div class="crop" data-crop="p:' + p.id + '" data-view="' + p.id + '"></div><div class="cropnote" data-note="' + p.id + '"></div></div>' +
      '<div class="side">' +
      (S.hideSuspects || !p.suggestion.lead_in ? '' : '<div class="lead">' + esc(p.suggestion.lead_in) + '</div>') +
      (p.suggestion.fix_path === 'disclose' && HELD.includes(p.class) ? '' : '<div class="sugg">' + esc(p.suggestion.text) + '</div>') +
      '<div class="kv"><b>表现为</b>' + (p.symptoms.map(s => esc(s.name) + ' ×' + s.count + (s.result === 'warn' ? '<span class="small">（提示）</span>' : '')).join(' · ') || '<span class="small">—</span>') + '</div>' +
      '<div class="kv"><b>要动的对象</b>' + (scope.length ? scope.slice(0, 8).map(chip).join('') + (scope.length > 8 ? '<span class="small">等 ' + scope.length + ' 个</span>' : '') : '<span class="small">无（不修图）</span>') + '</div>' +
      '<div class="kv"><b>并成的条目</b>' + Object.keys(p.counts).map(k => chip(k + ' ×' + p.counts[k])).join('') +
      (items.length > 1 ? '<details><summary class="small">看报告原文 ' + items.length + ' 条</summary><ul class="small">' + items.map(i => '<li><code>' + i.id + '</code> ' + esc(i.detail) + '</li>').join('') + '</ul></details>' : '') + '</div>' +
      '</div></div></article>';
  }
  function setCardLevel(pid, level) {
    const p = probById(pid), box = $('#card-' + pid + ' .crop'), tabs = $('#card-' + pid + ' .levels');
    if (!p || !box || !tabs) return;
    box.dataset.level = level;
    tabs.innerHTML = levelTabs(p, level, 'data-level') + '<span class="sp"></span><button class="mini" data-zoom="' + pid + '">放大</button><button class="mini" data-map="' + pid + '">全图定位</button>';
    paint(box);
  }

  // ---------- crops ----------
  const images = {};
  function image() {
    const src = D().png;
    return images[src] || (images[src] = new Promise((ok, no) => { const im = new Image(); im.onload = () => ok(im); im.onerror = no; im.src = src; }));
  }
  function cropSpec(key, level) {
    const kind = key.split(':')[0], marks = kind === 'p' ? probById(key.slice(2)) : itemById(key.slice(2));
    if (!marks) return null;
    const ctx = kind === 'p' ? ctxOf(marks) : marks.context;
    const lv = level || (kind === 'p' ? levelFor(marks) : S.level);
    return { kind, marks, ctx: ctx || {}, level: ctx && ctx[lv] ? lv : 'finding' };
  }
  function overlay(box, scale, spec) {
    const u = 1 / scale, show = { finding: 0, objects: 1, route: 2 }[spec.level], out = [], c = spec.ctx;
    const pt = p => p[0].toFixed(1) + ',' + p[1].toFixed(1);
    if (show >= 2) (c.wires || []).forEach(w => out.push('<polyline class="w" points="' + w.map(pt).join(' ') + '"/>'));
    if (show >= 1) {
      Object.keys(c.footprints || {}).forEach(name => { const f = c.footprints[name]; out.push('<rect class="fp" x="' + f[0] + '" y="' + f[1] + '" width="' + (f[2] - f[0]) + '" height="' + (f[3] - f[1]) + '"/><text class="fpn" x="' + (f[0] + 2 * u) + '" y="' + (f[1] + 11 * u) + '" font-size="' + (11 * u).toFixed(2) + '" stroke-width="' + (3 * u).toFixed(2) + '">' + esc(name) + '</text>'); });
      (c.labels || []).forEach(f => out.push('<rect class="lb" x="' + f[0] + '" y="' + f[1] + '" width="' + (f[2] - f[0]) + '" height="' + (f[3] - f[1]) + '"/>'));
    }
    (spec.kind === 'p' ? spec.marks.items.map(itemById) : [spec.marks]).filter(Boolean).forEach(i => {
      if ((i.lines || []).length) i.lines.forEach(l => out.push('<line class="fdl" x1="' + l[0][0] + '" y1="' + l[0][1] + '" x2="' + l[1][0] + '" y2="' + l[1][1] + '"/>'));
      (i.points || []).forEach(p => out.push('<circle class="fdp" cx="' + p[0] + '" cy="' + p[1] + '"/>'));
      if (i.box && !(i.lines || []).length) out.push('<rect class="fd" x="' + i.box[0] + '" y="' + i.box[1] + '" width="' + (i.box[2] - i.box[0]) + '" height="' + (i.box[3] - i.box[1]) + '"/>');
    });
    return '<svg class="ov" viewBox="' + [box[0], box[1], box[2] - box[0], box[3] - box[1]].join(' ') + '" preserveAspectRatio="none">' + out.join('') + '</svg>';
  }
  function paint(el, key, level, maxW) {
    key = key || el.dataset.crop;
    const spec = cropSpec(key, level || el.dataset.level);
    if (!spec) { el.innerHTML = '<div class="nocrop">没有这一项</div>'; return; }
    const box = spec.ctx[spec.level];
    if (!box) { el.innerHTML = '<div class="nocrop">报告里没有可画的坐标</div>'; return; }
    const w = box[2] - box[0], h = box[3] - box[1];
    const limit = Math.min(maxW || +el.dataset.max || 640, Math.max(220, (el.parentElement || el).clientWidth || 640));
    const scale = Math.min(4, Math.max(0.45, Math.min(limit / w, limit * 0.72 / h)));
    const dpr = window.devicePixelRatio || 1;
    image().then(im => {
      const cv = document.createElement('canvas');
      cv.width = Math.round(w * scale * dpr); cv.height = Math.round(h * scale * dpr);
      cv.style.width = Math.round(w * scale) + 'px'; cv.style.height = Math.round(h * scale) + 'px';
      const g = cv.getContext('2d'); g.imageSmoothingEnabled = false;
      g.drawImage(im, box[0], box[1], w, h, 0, 0, cv.width, cv.height);
      el.innerHTML = ''; el.appendChild(cv);
      el.insertAdjacentHTML('beforeend', overlay(box, scale, spec).replace(/class="(w|fp|lb|fd|fdl|fdp)"/g, (m, k) => m + ' stroke-width="' + ({ w: 1.6, fp: 1.1, lb: .9, fd: 1.8, fdl: 3, fdp: 1.8 }[k] / scale).toFixed(2) + '"').replace(/<circle class="fdp"/g, '<circle r="' + (5 / scale).toFixed(2) + '" class="fdp"'));
      const note = { finding: '问题点', objects: '对象', route: '走线' }[spec.level];
      const text = note + '级 · ' + LEVEL_NOTE[spec.level] + ' 范围 (' + round(box[0]) + ', ' + round(box[1]) + ')–(' + round(box[2]) + ', ' + round(box[3]) + ')，' + scale.toFixed(1) + '×';
      const slot = spec.kind === 'p' && $('[data-note="' + spec.marks.id + '"]') || $('#lb-note');
      if (slot) slot.textContent = text;
    }, () => { el.innerHTML = '<div class="nocrop">图像载入失败</div>'; });
  }
  // A crop counts as seen once half of it (at least 200 px for tall crops) has stayed on screen 0.4 s.
  function enough(en) { return en.intersectionRect.height >= Math.min(en.boundingClientRect.height, 400) * 0.5; }
  const io = new IntersectionObserver(entries => entries.forEach(en => {
    clearTimeout(en.target._t);
    if (en.isIntersecting && enough(en)) en.target._t = setTimeout(() => { if (!en.target.dataset.seen) { en.target.dataset.seen = 1; log('view', en.target.dataset.view); } }, 400);
  }), { threshold: [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1] });

  // ---------- maps ----------
  const mapSvg = (inner, cls, sheet, mini) => '<svg class="map ' + (cls || '') + (mini ? ' mini' : '') + '" viewBox="' + DATA.view.join(' ') + '" preserveAspectRatio="xMidYMid meet"><image href="' + DATA.sheets[sheet || S.sheet].png + '" x="0" y="0" width="1710" height="1390"/>' + (inner || '') + '</svg>';
  const pin = (p, n) => { if (!p.center) return ''; return '<g class="pin ' + p.severity + (p.state === 'persisting' ? ' persisting' : '') + (HELD.includes(p.class) ? ' held' : '') + '" data-pin="' + p.id + '" transform="translate(' + p.center[0] + ',' + p.center[1] + ')"><circle/><text' + (n ? '>' + n : ' visibility="hidden">') + '</text></g>'; };
  function sizePins(svg) {
    if (!svg) return;
    const vb = svg.viewBox.baseVal, k = Math.min(svg.clientWidth / vb.width, svg.clientHeight / vb.height), r = 11 / k;
    $$('.pin', svg).forEach(g => {
      const c = g.querySelector('circle'), t = g.querySelector('text'), held = g.classList.contains('held'), dim = g.classList.contains('persisting');
      c.setAttribute('r', held ? 5 / k : r); c.setAttribute('stroke-width', 2 / k); c.setAttribute('opacity', dim ? .55 : 1);
      t.setAttribute('font-size', r * 1.3); t.setAttribute('stroke-width', 3.2 / k); t.setAttribute('opacity', dim ? .7 : 1);
      t.setAttribute('stroke', g.classList.contains('fail') ? '#c62828' : '#ffffff');
    });
  }
  function mountD() {
    const list = ordered();
    $('#d-map').innerHTML = mapSvg(list.map(p => pin(p, !HELD.includes(p.class) ? list.filter(q => !HELD.includes(q.class)).indexOf(p) + 1 : 0)).join(''), 'dmap');
    sizePins($('#d-map svg'));
    $$('#d-map .pin').forEach(g => g.addEventListener('click', () => selectStop(g.dataset.pin)));
  }
  function selectStop(pid) {
    $$('.stop.on').forEach(e => e.classList.remove('on'));
    $$('#d-map .pin.on').forEach(e => e.classList.remove('on'));
    const li = $('#stop-' + pid), g = $('[data-pin="' + pid + '"]');
    if (li) { li.classList.add('on'); li.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); }
    if (g) g.classList.add('on');
  }
  function zoomTo(pid) {
    const svg = $('#d-map svg'), p = probById(pid), box = (ctxOf(p) || {}).objects || (p && p.box);
    if (!svg || !box) return;
    svg.setAttribute('viewBox', [box[0] - 40, box[1] - 40, box[2] - box[0] + 80, box[3] - box[1] + 80].join(' '));
    sizePins(svg); log('locate', pid);
  }

  // ---------- lightbox ----------
  let light = null;
  function closeLightbox() { if (light) { light.el.remove(); light = null; } }
  function openLightbox(key, title) {
    closeLightbox();
    const el = document.createElement('div');
    el.className = 'ovl'; el.id = 'lightbox';
    el.innerHTML = '<div class="dlg"><div class="top"><h3>' + esc(title) + '</h3><span class="levels" id="lb-levels"></span><button id="lb-close">关闭 (Esc)</button></div><div class="crop" id="lb-crop"></div><div class="cropnote" id="lb-note"></div></div>';
    document.body.appendChild(el);
    light = { key, el, level: cropSpec(key).level };
    el.addEventListener('click', e => { if (e.target === el) closeLightbox(); });
    $('#lb-close', el).onclick = closeLightbox;
    drawLightbox();
  }
  function drawLightbox() {
    const spec = cropSpec(light.key, light.level);
    $('#lb-levels', light.el).innerHTML = levelTabs(spec.marks, spec.level, 'data-lb-level');
    paint($('#lb-crop', light.el), light.key, light.level, Math.min(1100, window.innerWidth - 90));
  }
  function openMap(pid) {
    closeLightbox();
    const p = probById(pid), box = p && ((ctxOf(p) || {}).objects || p.box);
    if (!box) return;
    const el = document.createElement('div');
    el.className = 'ovl'; el.id = 'lightbox';
    el.innerHTML = '<div class="dlg picker"><div class="top"><h3>全图定位 · ' + esc(p.title) + '</h3><button id="lb-close">关闭 (Esc)</button></div>' + mapSvg('<rect class="roi" x="' + box[0] + '" y="' + box[1] + '" width="' + (box[2] - box[0]) + '" height="' + (box[3] - box[1]) + '"/>') + '</div>';
    document.body.appendChild(el);
    light = { el };
    el.addEventListener('click', e => { if (e.target === el) closeLightbox(); });
    $('#lb-close', el).onclick = closeLightbox;
    log('locate', pid);
  }

  // ---------- variant views ----------
  const PROBE = '<script>(function(){var send=function(t,id){try{parent.postMessage({rb:1,type:t,id:id||""},"*")}catch(e){}};' +
    'document.addEventListener("click",function(ev){var a=ev.target&&ev.target.closest?ev.target.closest("a[href]"):null;if(!a)return;var h=a.getAttribute("href")||"",m;' +
    'if((m=h.match(/^#(region-\\d+)$/)))send("open",m[1]);else if((m=h.match(/^#loc-(region-\\d+)$/)))send("locate",m[1]);},true);' +
    'var seen={},timers={},io=new IntersectionObserver(function(es){es.forEach(function(en){var id=en.target.parentNode.id;clearTimeout(timers[id]);' +
    'if(en.isIntersecting&&en.intersectionRect.height>=Math.min(en.boundingClientRect.height,400)*0.5)timers[id]=setTimeout(function(){if(!seen[id]){seen[id]=1;send("view",id)}},400)})},{threshold:[0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1]});' +
    'Array.prototype.forEach.call(document.querySelectorAll("section[id^=\\"region-\\"] img"),function(im){io.observe(im)});' +
    'var rows=Array.prototype.filter.call(document.querySelectorAll("table tr"),function(tr){var c=tr.cells&&tr.cells[0];return c&&/^(V\\d+|B\\d) /.test(c.textContent)}),row=false,rio=new IntersectionObserver(function(es){if(!row&&es.some(function(en){return en.isIntersecting})){row=true;send("firstrow",String(rows.length))}},{threshold:.5});' +
    'rows.forEach(function(tr){rio.observe(tr)});})()</scr' + 'ipt>';
  function mountA() { const f = $('#real'); if (f) f.srcdoc = D().page.replace('__PNG__', () => D().png) + PROBE; }
  let lastOpen = { id: '', t: 0 };
  window.addEventListener('message', ev => {
    const d = ev.data; if (!d || !d.rb) return;
    if (d.type === 'open') { const now = performance.now(); if (lastOpen.id === d.id && now - lastOpen.t < 400) return; lastOpen = { id: d.id, t: now }; }
    log(d.type, d.id);
  });

  function summaryStrip() {
    const s = summa();
    return '<div class="sum"><b>' + s.problems + '</b> 个要修的问题：失败 <b class="c-fail">' + s.fail_problems + '</b>' + (s.new ? '，其中新增 ' + s.new : '') + ' · 提示 <b class="c-warn">' + (s.problems - s.fail_problems) + '</b>' + (s.persisting ? '，其中仍在 ' + s.persisting : '') +
      '<span class="sep">｜</span>由 <b>' + s.findings + '</b> 条报告条目并成<span class="sep">｜</span>已消除 <b>' + s.resolved + '</b><span class="sep">｜</span>另有披露 ' + s.disclosures + '、连带未校核 ' + s.unchecked +
      '<span class="sep">｜</span>' + diffNote() + '</div>';
  }
  function resolvedBox() {
    const r = resolved();
    return r.length ? '<div class="resolved"><b>已消除 ' + r.length + ' 项</b>（上一版有、这一版没有）<ul>' + r.map(x => '<li>' + sev(x.severity) + ' ' + esc(x.title) + '（' + x.rows + ' 条）</li>').join('') + '</ul></div>' : '';
  }
  function repairBox() {
    const r = D().triage.repair[S.rule], by = {};
    r.problems.forEach(p => { const k = pathOf(p); by[k] = (by[k] || 0) + 1; });
    return '<div class="box"><h4>本轮修图单（第 ' + r.round + ' 轮 · ' + r.problems.length + ' 项）</h4>' +
      '<div class="small">' + (Object.keys(by).map(k => pathTag({ suggestion: { fix_path: k } }) + ' ' + by[k]).join(' &nbsp; ') || '空') + '</div>' +
      '<div class="small" style="margin-top:4px">差分范围：节点 ' + r.diff_scope.nodes.length + ' 个 · 连线 ' + r.diff_scope.edges.length + ' 条 · 含相邻管线 ' + (r.diff_scope.include_adjacent_edges ? '是' : '否') +
      ' · <span class="' + (r.scope_ok ? 'ok' : 'no') + '">sheet_diff 口径' + (r.scope_ok ? '通过' : '不通过：' + esc(r.scope_error || '')) + '</span>' + (r.problems.length ? '' : ' · <span class="no">空单</span>') + '</div>' +
      '<details><summary class="small">修图单 JSON（给局部自动修正 / 走线层 / agent 的输入）</summary><pre>' + esc(JSON.stringify(r, null, 1)) + '</pre></details>' +
      '<button class="small" data-copy="repair">复制 JSON</button> <button class="small" data-act="panels">到「衔接」里看下一轮</button></div>';
  }
  function viewA() { return '<div class="cap">' + esc(V().full) + '：官方回读页原样，只多一段计时埋点，不改显示。</div><iframe class="real" id="real" title="现状回读页"></iframe>'; }
  function viewB() {
    const items = flatItems(), fails = items.filter(i => i.result === 'fail').length;
    return '<div class="cap">' + esc(V().full) + '：清单按严重度排过，失败在前；文字照抄报告，不合并、不解释。</div>' +
      '<table class="b"><thead><tr><th></th><th>级别</th><th>检查</th><th>报告原文</th><th>局部图</th></tr></thead><tbody>' +
      items.map((i, n) => '<tr class="' + i.result + '"><td class="n">' + (n + 1) + '</td><td>' + sev(i.result) + '</td><td class="mono">' + esc(i.check) + '</td><td>' + esc(i.detail) + '</td><td><button class="lnk" data-open-item="' + esc(i.id) + '">局部图</button></td></tr>').join('') +
      '</tbody></table><div class="footnote">失败 ' + fails + ' 条 · 提示 ' + (items.length - fails) + ' 条。披露和未校核条目没有列。</div>';
  }
  function viewC() {
    const list = ordered(), groups = new Map();
    list.forEach(p => { if (!groups.has(p.class)) groups.set(p.class, []); groups.get(p.class).push(p); });
    return '<div class="cap">' + esc(V().full) + ' · ' + esc(L.rule[S.rule]) + '</div>' + summaryStrip() + resolvedBox() +
      ORDER.filter(c => groups.has(c)).map(c => '<details class="group"' + (HELD.includes(c) ? '' : ' open') + '><summary>' + cls(c) + '<span>' + groups.get(c).length + ' 个</span><span class="why">' + esc(L.why[c]) + '</span></summary><div class="cards">' + groups.get(c).map(p => card(p, list.indexOf(p) + 1)).join('') + '</div></details>').join('');
  }
  function stop(p, n) {
    return '<li class="stop ' + p.severity + '" id="stop-' + p.id + '" data-pid="' + p.id + '"><span class="num">' + n + '</span><div>' +
      '<div class="t">' + sev(p.severity) + ' ' + st(p.state) + ' ' + esc(p.title) + '</div>' +
      '<div class="m">' + esc(L.class[p.class]) + ' · ' + esc(p.zone || '全图') + ' ' + pathTag(p) + '</div>' +
      (p.suggestion.fix_path === 'disclose' ? '' : '<div class="s">' + esc(fullText(p)) + '</div>') +
      '<div class="small">要动：' + (p.scope.nodes.concat(p.scope.edges).slice(0, 5).map(chip).join('') || '无') + '</div></div>' +
      '<div class="btns"><button data-zoom="' + p.id + '">局部图</button><button data-goto="' + p.id + '">地图上放大</button></div></li>';
  }
  function viewD() {
    const list = ordered(), fix = list.filter(p => !HELD.includes(p.class)), held = list.filter(p => HELD.includes(p.class));
    return '<div class="d"><div class="mapcard"><div class="bar"><span>全图 · 编号就是路线顺序</span><span style="flex:1"></span><button id="d-reset">复位缩放</button></div><div id="d-map"></div>' +
      '<div class="legend"><span><i style="background:#c62828;border-color:#7f1414"></i>失败</span><span><i style="background:#fff;border-color:#8a5200"></i>提示</span><span><i style="background:#fff;border-color:#9aa4ae"></i>不进修图单</span><span>半透明 = 仍在（与上一版相同）</span></div></div>' +
      '<div><div class="cap">' + esc(V().full) + ' · ' + esc(L.rule[S.rule]) + '</div>' + summaryStrip() + resolvedBox() +
      '<ol class="route">' + fix.map((p, i) => stop(p, i + 1)).join('') + '</ol>' +
      (held.length ? '<details><summary class="small">不进修图单的 ' + held.length + ' 条</summary>' + held.map(p => '<div class="kv">' + sev(p.severity) + ' ' + esc(p.title) + ' <span class="small">' + esc(HELD_TEXT[p.class]) + '</span></div>').join('') + '</details>' : '') +
      repairBox() + '</div></div>';
  }

  // ---------- browse ----------
  const TABS = [['order', '一 · 优先顺序'], ['context', '二 · 保留什么'], ['tiers', '三 · 哪些给结构化建议'], ['link', '四 · 和自动修正、差分怎么接']];
  function header() {
    return '<header class="top"><div class="wrap"><div class="brand">回读分诊原型<span class="tag">一次性</span></div><nav class="mode">' +
      (S.mode === 'trial' && S.trial ? '<button data-mode="results">提前结束，看已做的 ' + S.results.length + ' 张</button>' :
      '<button data-mode="browse" data-browse="page" class="' + (S.mode === 'browse' && S.browse === 'page' ? 'on' : '') + '">看页面</button>' +
      '<button data-mode="browse" data-browse="panels" class="' + (S.mode === 'browse' && S.browse === 'panels' ? 'on' : '') + '">四个决定</button>' +
      '<button data-mode="trial" class="' + (S.mode === 'trial' ? 'on' : '') + '">对照试验</button>' +
      '<button data-mode="results" class="' + (S.mode === 'results' ? 'on' : '') + '">结果<span class="cnt">' + S.results.length + '</span></button>') + '</nav></div></header>';
  }
  function intro() {
    return '<details class="intro"' + (S.seenIntro ? '' : ' open') + '><summary><b>这是什么 · 怎么用</b></summary><ul>' +
      '<li>要回答的问题：<b>回读页怎样帮助审阅者更快找到问题并开始下一轮修图？</b>同一条出图链、同一批改坏的图，摆出四个回读版本对照。</li>' +
      '<li><b>看页面</b>：选一张图，用底部开关（或 ← →）在四个版本之间切：A 现状（官方回读页原样）· B 按严重度平铺（只排序）· C 按类别分诊（并成问题 + 建议 + 局部图）· D 按位置的修图路线（全图编号 + 修图单）。</li>' +
      '<li><b>对照试验</b>：每张图随机配一个版本，图名和版本名先不显示；记找到第一个主要问题的用时、打开和看到的局部图数、点的位置对不对、建议够不够用。</li>' +
      '<li><b>四个决定</b>：票里要定的四件事，每件都能当场改选项看效果。</li>' +
      '<li><b>口径</b>：图是 1# 基线布局加一处显式改动后走官方链出的（render → rasterize → validate → readback）；「上一版」是冻结的基线图。分诊是原型代码（<code>proto_issue102_readback_triage.py</code>），没有接进 skill。所有状态只在内存里，刷新即清空。</li></ul></details>';
  }
  function sheetSelect() {
    const groups = {};
    Object.keys(DATA.sheets).forEach(n => { (groups[DATA.sheets[n].stratum] = groups[DATA.sheets[n].stratum] || []).push(n); });
    return '<select id="sheet">' + Object.keys(groups).map(g => '<optgroup label="' + esc(g) + '">' + groups[g].map(n => '<option value="' + n + '"' + (n === S.sheet ? ' selected' : '') + '>' + esc(n) + '</option>').join('') + '</optgroup>').join('') + '</select>';
  }
  function refSelect() {
    const base = S.sheet === 'base';
    return '<select id="ref">' + (base ? '' : '<option value="base"' + (S.ref === 'base' ? ' selected' : '') + '>基线图（冻结的上一版）</option>') +
      '<option value="none"' + (S.ref === 'none' ? ' selected' : '') + '>' + (base ? '不比对' : '不比对（全部算未比对）') + '</option>' +
      (base ? Object.keys(DATA.sheets).filter(n => n !== 'base').map(n => '<option value="' + n + '"' + (S.ref === n ? ' selected' : '') + '>反过来：以 ' + esc(n) + ' 为上一版</option>').join('') : '') + '</select>';
  }
  function controls() {
    const cd = S.variant === 'C' || S.variant === 'D';
    return '<div class="controls"><span>图 <strong>' + sheetSelect() + '</strong></span><span>对照的上一版 ' + refSelect() + '</span>' +
      (cd ? '<span class="sep"></span><span>排序 ' + select('rule', RULES.map(r => [r, L.rule[r]])) + '</span><span class="sep"></span><label class="ctl"><input type="checkbox" data-k="byclass"' + (S.byClass ? ' checked' : '') + '>局部图默认按类别选级</label>' +
        (S.byClass ? '' : '<span>默认 ' + select('level', Object.keys(LEVELS).map(k => [k, LEVELS[k]])) + '</span>') +
        '<label class="ctl"><input type="checkbox" data-k="hide"' + (S.hideSuspects ? ' checked' : '') + '>隐藏「上一版之后动过」</label>' : '') + '</div>';
  }
  function select(name, options) {
    return '<select data-' + name + '="' + name + '">' + options.map(o => '<option value="' + o[0] + '"' + (S[name] === o[0] ? ' selected' : '') + '>' + esc(o[1]) + '</option>').join('') + '</select>';
  }
  function info() {
    const d = D(), f = d.facts;
    return '<p class="info small">' + esc(d.stratum) + ' · 改动：' + esc(d.note) + ' · 失败 ' + d.fail + ' / 提示 ' + d.warn +
      ' ｜ 现有回读页：对象清单 ' + f.rows + ' 行，失败 / 提示条目在第 ' + f.first + '–' + f.last + ' 行（没有级别标记），局部图 ' + f.regions + ' 张，其中 ' + f.overview_only + ' 条只链到「全图」。</p>';
  }
  function switcher() {
    return '<nav class="sw">' + VARIANTS.map(v => '<button data-variant="' + v.id + '" class="' + (v.id === S.variant ? 'on' : '') + '" title="' + esc(v.desc) + '">' + v.id + ' ' + esc(v.name) + '</button>').join('') + '<span class="hint">← → 切换</span></nav>';
  }
  function variantView() {
    return { A: viewA, B: viewB, C: viewC, D: viewD }[S.variant]();
  }

  // ---------- panels (the four decisions) ----------
  function namedCell(c) {
    if (!c || c.ok === null || c.ok === undefined) return '<td class="c">—</td>';
    return '<td class="c"><span class="' + (c.ok ? 'hit' : 'miss') + '">' + (c.ok ? '✓' : '✗') + '</span> <span class="small">' + esc((c.title || c.detail || '').slice(0, 26)) + '</span></td>';
  }
  function objective() {
    const head = '<tr><th>图</th><th>改动</th>' + RULES.map(r => '<th>' + esc(L.rule[r].split('：')[0].split('，')[0]) + '</th>').join('') + '<th>平铺第一条（B）</th></tr>';
    return '<table class="res">' + head + DATA.trials.map(n => { const d = DATA.sheets[n]; return '<tr><td class="mono">' + esc(n) + '</td><td class="small">' + esc(d.note.split('：')[0]) + '</td>' + RULES.map(r => namedCell(d.check[r])).join('') + namedCell(d.check.flat) + '</tr>'; }).join('') + '</table>';
  }
  function sameTop() {
    const all = Object.keys(DATA.sheets), same = all.filter(n => { const ids = RULES.map(r => DATA.sheets[n].check[r].id); return ids.every(x => x === ids[0]); }).length;
    return all.length + ' 张图里有 ' + same + ' 张，四种规则选出的第一名是同一个问题';
  }
  function panelOrder() {
    const list = ordered(), orders = D().triage.orders;
    return '<section class="panel"><h2>决定一 · 优先顺序</h2>' +
      '<fieldset><legend>排序规则（都先按严重度：失败在前、提示在后）</legend>' +
      RULES.map(r => '<label class="ctl"><input type="radio" name="rule" data-rule="' + r + '"' + (S.rule === r ? ' checked' : '') + '>' + esc(L.rule[r]) + '</label>').join('') +
      '<div style="height:6px"></div>' +
      '<label class="ctl"><input type="checkbox" data-k="persisting"' + (S.persisting === 'after' ? ' checked' : '') + '>同一级里「新增」排在「仍在」前面</label>' +
      '<label class="ctl"><input type="checkbox" data-k="notes"' + (S.notes === 'tail' ? ' checked' : '') + '>「只是提示、不必修」的条目放到末尾</label>' +
      '<div class="small">固定不变：主线折返这类低信号提示进入官方报告后排在同类最后（B2 折返是预算项，按正常位置排）；披露和连带未校核永远在最后，不进修图单。</div></fieldset>' +
      '<h3>这张图的顺序（' + esc(L.rule[S.rule]) + '）</h3><ol class="olist">' + list.map((p, i) => '<li><span class="num">' + (i + 1) + '</span><div>' + sev(p.severity) + ' ' + cls(p.class) + ' ' + st(p.state) + ' ' + esc(p.title) +
      '<div class="r">' + esc(why(p, i + 1)) + (HELD.includes(p.class) ? '' : ' · ' + esc(L.path[pathOf(p)])) + '</div></div></li>').join('') + '</ol>' +
      '<h3>同图换成别的规则，前三名是</h3><table><tr><th>规则</th><th>第 1</th><th>第 2</th><th>第 3</th></tr>' +
      RULES.map(r => { const have = new Map(probs().map(p => [p.id, p])), top = (orders[r + '|inline|inline'] || []).map(id => have.get(id)).filter(Boolean).slice(0, 3);
        return '<tr><td>' + esc(L.rule[r]) + '</td>' + top.map(p => '<td>' + sev(p.severity) + ' ' + st(p.state) + ' ' + esc(L.class[p.class]) + '<br>' + esc(p.title.slice(0, 40)) + '</td>').join('') + '</tr>'; }).join('') + '</table>' +
      '<p class="small" style="margin:6px 0 0">' + sameTop() + '。要看出规则之间的差别，换一张问题多的图（multi-bus、mix-3、mix-3b）。</p>' +
      '<h3>客观核对：排在第一位的问题，有没有点名被改动的对象</h3>' +
      '<p class="small">建图时每张图只动了一个对象，所以能机器判：第一位问题的「要动的对象」或嫌疑对象里有它，算点名。这是页面的客观底线，和试验里人的用时互补。</p>' + objective() +
      '<h3>现有页面：一个改动散成多少条</h3><table><tr><th>图</th><th>改了什么</th><th>新增的报告条目</th><th>并成几个问题</th><th>在现有清单里的位置</th></tr>' +
      Object.keys(DATA.sheets).filter(n => n !== 'base').map(n => { const d = DATA.sheets[n], f = d.facts, o = d.check.fanout; return '<tr><td class="mono">' + esc(n) + '</td><td class="small">' + esc(d.note) + '</td><td class="c">' + o.rows + '</td><td class="c"><b>' + o.problems + '</b></td><td class="small">第 ' + f.first + '–' + f.last + ' 行 / 共 ' + f.rows + ' 行</td></tr>'; }).join('') + '</table></section>';
  }
  function panelContext() {
    const list = ordered().filter(p => !HELD.includes(p.class));
    // The example prefers a problem that has all three levels, so every level can be compared.
    const p = probById(S.preview) || list.find(q => (ctxOf(q) || {}).route) || list[0];
    if (p) S.preview = p.id;
    const c = p ? ctxOf(p) : {};
    return '<section class="panel"><h2>决定二 · 每个问题保留什么</h2>' +
      '<fieldset><legend>页面默认显示哪一级</legend>' +
      Object.keys(LEVELS).map(k => '<label class="ctl"><input type="radio" name="level" data-level-opt="' + k + '"' + (!S.byClass && S.level === k ? ' checked' : '') + (S.byClass ? ' disabled' : '') + '>' + LEVELS[k] + '</label>').join('') +
      '<span class="sep"></span><label class="ctl"><input type="checkbox" data-k="byclass"' + (S.byClass ? ' checked' : '') + '>按类别选默认级别</label>' +
      '<div style="height:6px"></div><span class="small">上下文范围：</span>' + Object.keys(DATA.reach).map(k => '<label class="ctl"><input type="radio" name="reach" data-reach="' + k + '"' + (S.reach === k ? ' checked' : '') + '>' + ({ tight: '紧（90 px）', normal: '中（170 px）', wide: '松（260 px）' }[k]) + '</label>').join('') + '</fieldset>' +
      (p ? '<h3>三级局部图 · ' + select('preview', list.map(q => [q.id, q.title.slice(0, 30)])) + '</h3><div class="tri">' + Object.keys(LEVELS).map(k => '<figure><div class="crop" data-crop="p:' + p.id + '" data-level="' + k + '" data-max="360"></div><figcaption><b>' + LEVELS[k] + '</b>：' + esc(LEVEL_NOTE[k]) + (c[k] ? '<br>范围 (' + c[k].map(round).join(', ') + ')' : '<br>这一级没有可看的内容') + '</figcaption></figure>').join('') + '</div>' : '<p class="small">这张图没有要修的问题。</p>') +
      '<table style="margin-top:12px"><tr><th>级别</th><th>画什么</th><th>多大</th><th>用来</th></tr>' +
      '<tr><td>问题点</td><td>出错的那一点或那一段（红）</td><td>不小于 150 × 110</td><td>确认缺陷是真的</td></tr>' +
      '<tr><td>对象</td><td>加元件本体（蓝虚线）和标签（紫点线）</td><td>不超过 560 × 440</td><td>知道要动哪个对象</td></tr>' +
      '<tr><td>走线</td><td>再加附近走线（蓝线）</td><td>对象级外扩一个范围；放不下就退回对象级</td><td>决定怎么改</td></tr></table>' +
      '<h3>按类别的默认级别（提议）</h3><table><tr><th>类别</th><th>默认</th><th>理由</th></tr>' +
      '<tr><td>连接语义</td><td>走线</td><td>要知道两条线各从哪来、到哪去，才能判断是挪、绕还是恢复朝向</td></tr>' +
      '<tr><td>遮挡</td><td>对象</td><td>要看清被盖住的是哪个元件的哪一部分</td></tr>' +
      '<tr><td>标签重叠</td><td>对象</td><td>标签属于谁、压在谁身上；走线帮不上</td></tr>' +
      '<tr><td>版式与预算</td><td>走线</td><td>折返、绕行、短线段都得看整段线</td></tr></table>' +
      '<h3>现有页面的局部图</h3><p class="small">按对象裁（端口、元件全貌、交叉点、跨线桥），每图 ' + Math.min.apply(null, Object.keys(DATA.sheets).map(n => DATA.sheets[n].facts.regions)) + '–' + Math.max.apply(null, Object.keys(DATA.sheets).map(n => DATA.sheets[n].facts.regions)) + ' 张，不按问题裁；共线重叠、折返、绕行这些条目只链到「全图」。一张图出 30 多条失败时，清单里是 30 多行，对应局部图分散在各处。</p></section>';
  }
  function panelTiers() {
    const rows = DATA.kinds, sheets = Object.keys(DATA.sheets), all = {};
    const kindBy = {}, itemBy = {}, ledBy = {};
    rows.forEach(r => { const k = solo([r.class, r.kind, r.result]); kindBy[k] = (kindBy[k] || 0) + 1; itemBy[k] = (itemBy[k] || 0) + r.items; });
    sheets.forEach(n => DATA.sheets[n].triage.problems.forEach(p => {
      const k = pathOf(p), key = [p.class, p.kind, p.severity].join('|');
      all[k] = (all[k] || 0) + 1; ledBy[key] = ledBy[key] || {}; ledBy[key][k] = (ledBy[key][k] || 0) + 1;
    }));
    const tags = by => PATHS.filter(k => by[k]).map(k => pathTag({ suggestion: { fix_path: k } }) + ' <b>' + by[k] + '</b>').join(' · ');
    const total = Object.keys(all).reduce((a, k) => a + all[k], 0), lone = Object.values(itemBy).reduce((a, b) => a + b, 0);
    return '<section class="panel"><h2>决定三 · 哪些问题能给结构化建议</h2>' +
      '<p class="small">「结构化」= 有确定的修正动作和要动的对象（节点、连线），能直接交给局部自动修正或走线层；「交 agent」只有方向性的一句话；「披露」不修图；「随上游恢复」不进任何修图单。</p>' +
      '<div class="controls" style="margin:8px 0 10px"><label class="ctl"><input type="checkbox" data-k="cause"' + (S.cause ? ' checked' : '') + '>并成问题时，认出的原因优先（修因不修症）</label><span class="small">表里的「去向」可以点着改；页面上的标签和「决定四」的修图单跟着变（只在本页内）。</span></div>' +
      '<div class="sum">' + sheets.length + ' 张图里出现 <b>' + rows.length + '</b> 种缺陷（类别 × 缺陷 × 级别），共 ' + lone + ' 条。单条看：' + tags(kindBy) + ' 种，按条目算 ' + tags(itemBy) + '。<br>并成 ' + total + ' 个问题之后：' + tags(all) + '。</div>' +
      '<table class="tiers"><tr><th>类别</th><th>缺陷</th><th>级别</th><th>单条时的去向</th><th>动作</th><th>条目</th><th>牵头的问题 → 并成后的去向</th><th>样例</th></tr>' +
      rows.map((r, i) => {
        const k = solo([r.class, r.kind, r.result]), key = [r.class, r.kind, r.result].join('|'), s = r.sample, j = r.joined;
        return '<tr><td>' + cls(r.class) + '</td><td>' + esc(r.name) + '<div class="small mono">' + esc(r.kind) + '</div></td><td>' + sev(r.result) + '</td>' +
          '<td><button class="lnk" data-tier="' + i + '">' + esc(L.path[k]) + '</button></td><td class="mono">' + esc(r.action) + '</td>' +
          '<td class="c">' + r.items + (r.rides ? '<div class="small" style="white-space:normal">其中 ' + r.rides + ' 条并进别处</div>' : '') + '</td>' +
          '<td class="c">' + (r.led ? '<b>' + r.led + '</b><div class="small" style="white-space:normal">' + tags(ledBy[key]) + '</div>' : '—') + '</td>' +
          '<td class="small" style="min-width:300px"><span class="mono">' + esc(s.sheet) + '</span> · ' + esc(s.title) + '<br>' + esc(s.text.slice(0, 150)) + '<br>要动：' + (s.objects.slice(0, 6).join('、') || '无（不修图）') +
          (j ? '<br><b>并进问题后</b>（<span class="mono">' + esc(j.sheet) + '</span> · ' + esc(j.title.slice(0, 44)) + '）：' + esc(j.action) + ' → ' + esc(L.path[j.path]) + '<br>' + esc(j.text.slice(0, 120)) : '') + '</td></tr>';
      }).join('') + '</table>' +
      '<h3>还没进官方报告的条目</h3><p class="small">图面可读性评分那一票定下的指标。它们进了官方报告之后，回读里按下面的位置放；这是提议，等定。</p>' +
      '<table><tr><th>指标</th><th>越线时</th><th>提议的类别</th><th>提议的去向</th></tr>' +
      '<tr><td>单条主线折点 &gt; 6</td><td>不劣化下限</td><td>版式与预算</td><td>结构化 · 交走线 / 规则层；按「沿哪条主线、哪一段」报</td></tr>' +
      '<tr><td>三通旁线段 &lt; 30 px</td><td>不劣化下限</td><td>版式与预算</td><td>结构化 · 交走线 / 规则层</td></tr>' +
      '<tr><td>标签离主人 &gt; 40 px，或离别的元件更近</td><td>预算门槛</td><td>标签重叠</td><td>交 agent（挪标签不是稳定动作）；等标签排布规则定了再议</td></tr>' +
      '<tr><td>异网并行：中心距 ≤ 16 px 且并行 ≥ 24 px</td><td>预算门槛</td><td>版式与预算（也可以算连接语义，待定）</td><td>结构化 · 交走线 / 规则层</td></tr>' +
      '<tr><td>主线折返</td><td>只作回读提示（低信号）</td><td>版式与预算，排最后</td><td>不修图 · 披露</td></tr>' +
      '<tr><td>三通互距、跨线桥到最近节点的距离</td><td>只进回读清单（低信号）</td><td>版式与预算，排最后</td><td>不修图 · 披露</td></tr></table></section>';
  }
  function panelLink() {
    const d = D(), r = d.triage.repair[S.rule], queue = r.problems;
    if (!S.fixed[S.sheet]) S.fixed[S.sheet] = {};
    const fixed = S.fixed[S.sheet];
    queue.forEach(p => { if (!(p.id in fixed)) fixed[p.id] = pathOf(p) === 'local' || pathOf(p) === 'route'; });
    const round2 = queue.filter(p => !fixed[p.id]);
    const noConn = !round2.some(p => p.class === 'connection' && p.severity === 'fail');
    const flow = [['回读页', '问题 + 新增 / 仍在 + 局部图'], ['修图单', '按轮、按顺序；每项带动作和范围'], ['执行', '结构化 → 局部自动修正 / 走线层<br>其余 → agent，每次走官方链'], ['重走官方链', 'render → validate → readback'], ['以上一版为参考', '新增 / 仍在 / 已消除 + 图像差分']];
    return '<section class="panel"><h2>决定四 · 回读建议怎么和局部自动修正、图像差分衔接</h2>' +
      '<div class="flow">' + flow.map((f, i) => (i ? '<span class="ar">→</span>' : '') + '<div class="st' + (i === 1 ? ' hot' : '') + '"><b>' + f[0] + '</b>' + f[1] + '</div>').join('') + '</div>' +
      '<div class="kv"><b>修图单</b>每轮一份，顺序就是修的顺序；每项带 <code>action</code>、<code>fix_path</code>、<code>scope</code>（节点、连线、是否含相邻管线）和三级局部图的坐标。去向是 <code>local</code> / <code>route</code> 的才有 <code>scope</code>，可以自动执行；<code>agent</code> 只拿文字建议；<code>disclose</code> / <code>recheck</code> 不进单。</div>' +
      '<div class="kv"><b>差分范围</b>整轮一份，取自修图单里各项 <code>scope</code> 的并集，按 <code>sheet_diff</code> 收的字段（nodes、edges、include_adjacent_edges、note）。母线锚点并进 edges。</div>' +
      '<div class="kv"><b>两轮</b>修正最多两轮，每轮只修上一轮列出的缺陷。第 ' + r.round + ' 轮修不完的进第 2 轮；第 2 轮后还有，就停手，出未收敛项清单。</div>' +
      '<div class="kv"><b>图像差分</b>现在' + (d.diff_ready ? '<span class="ok">可用</span>' : '<span class="no">不可用</span>：拓扑覆盖' + (d.coverage === 'pass' ? '已通过，但几何或浏览器证据有问题' : '未通过（' + esc(d.coverage) + '）')) + '。<code>sheet_diff._model</code> 另要求浏览器证据当前、渲染器与字体环境一致；页面这里只按前三项算，所以「可用」偏乐观。连接语义失败本身不是差分门禁；它通过 V10 → V4/V14 未校核、B1 不放行挡住交付。</div>' +
      '<h3>这张图的第 ' + r.round + ' 轮修图单（' + esc(L.rule[S.rule]) + '）</h3>' +
      (queue.length ? '<table><tr><th>顺序</th><th>问题</th><th>去向</th><th>第 1 轮修掉了？</th></tr>' + queue.map(p => '<tr><td class="c">' + p.order + '</td><td>' + sev(p.severity) + ' ' + st(p.state) + ' ' + esc(p.title) + '<div class="small">' + esc(fullText(p).slice(0, 140)) + '</div></td><td>' + pathTag(p) + '</td><td class="c"><input type="checkbox" data-fixed="' + p.id + '"' + (fixed[p.id] ? ' checked' : '') + '></td></tr>').join('') + '</table>' : '<p class="small">这张图没有要修的问题，修图单是空的。</p>') +
      '<div class="box"><h4>按上面的勾选，第 2 轮</h4>' +
      (round2.length ? '<div>还剩 ' + round2.length + ' 项：' + round2.map(p => chip(p.title.slice(0, 18))).join('') + '</div><div class="small">第 2 轮的修图单 = 这些，顺序不变，重新编号。第 2 轮修完后还剩的进未收敛项清单（停手，交工程师）。</div>' : '<div class="ok">第 1 轮就清空了。剩下的只有披露和连带未校核，它们不进修图单。</div>') +
      '<div class="small">' + (noConn ? '<span class="ok">连接语义的失败已清，图像差分可用</span>：修完这一轮就能比。' : '<span class="no">连接语义还有失败</span>：图像差分还不能用。') + '</div></div>' +
      '<details><summary class="small">修图单和差分范围（JSON，模块算出来的原样，不含本页临时的改动）</summary><pre>' + esc(JSON.stringify({ repair_order: r }, null, 1)) + '</pre></details>' +
      '<details><summary class="small">不进修图单的 ' + r.not_in_queue.length + ' 条</summary>' + r.not_in_queue.map(x => '<div class="kv">' + sev(x.class === 'unchecked' || x.path === 'recheck' ? 'not_checked' : 'warn') + ' ' + esc(x.title) + ' <span class="small">' + esc(x.reason) + '</span></div>').join('') + '</details>' +
      '<button class="small" data-copy="repair">复制修图单 JSON</button></section>';
  }
  function panelsView() {
    const list = ordered().filter(p => !HELD.includes(p.class)), fails = summa().fail_problems;
    return '<div class="wrap">' + '<div class="sum" style="margin-top:12px">' + esc(S.sheet) + ' · 失败问题 ' + fails + ' 个，要修 ' + list.length + ' 个 · 顺序：' + list.slice(0, 6).map(p => esc(p.title.slice(0, 16))).join(' → ') + (list.length > 6 ? ' …' : '') +
      ' <button data-mode="browse" data-browse="page" class="small">回到页面</button></div>' +
      '<div class="tabs">' + TABS.map(t => '<button data-tab="' + t[0] + '" class="' + (S.tab === t[0] ? 'on' : '') + '">' + t[1] + '</button>').join('') + '</div>' +
      { order: panelOrder, context: panelContext, tiers: panelTiers, link: panelLink }[S.tab]() + '</div>';
  }

  // ---------- trial ----------
  function log(type, id) {
    const T = S.trial;
    if (T && T.phase === 'view' && T.rec) T.rec.events.push({ t: Math.round(performance.now() - T.t0), type: type, id: id || '' });
  }
  function targets() {
    const out = [], tri = D().triage;
    (tri.problems || []).forEach(p => { if (p.state === 'new' && !HELD.includes(p.class) && p.box) out.push({ box: p.box, what: p.title }); });
    Object.keys(tri.changed || {}).forEach(k => { const c = tri.changed[k]; out.push({ box: c.now, what: c.label }); });
    return out;
  }
  function hitTest(x, y) {
    let best = Infinity, inside = '';
    targets().forEach(t => { const b = t.box, dx = Math.max(b[0] - x, 0, x - b[2]), dy = Math.max(b[1] - y, 0, y - b[3]);
      if (!dx && !dy && !inside) inside = t.what; best = Math.min(best, Math.hypot(dx, dy)); });
    return { error_px: Math.round(best), hit: best <= 40, inside: inside };
  }
  function startTrials() {
    const n = S.trialN, strata = ['label', 'overlap', 'topology', 'crossing'];
    let sheets = [];
    for (let r = 0; sheets.length < Math.min(n, DATA.trials.length); r++) strata.forEach(s => { const left = DATA.trials.filter(x => x.indexOf(s) === 0 && sheets.indexOf(x) < 0); if (left.length && sheets.length < n) sheets.push(left[r % left.length]); });
    let vs = []; while (vs.length < n) vs = vs.concat(shuffle(VARIANTS.map(v => v.id)));
    S.mode = 'trial';
    S.trial = { list: sheets.map((s, i) => ({ sheet: s, variant: vs[i] })), i: 0, phase: 'intro', t0: 0, rec: null };
  }
  function beginView() {
    const T = S.trial, item = T.list[T.i];
    S.sheet = item.sheet; S.variant = item.variant; S.ref = S.sheet === 'base' ? 'none' : 'base';
    S.rule = S.variant === 'D' ? 'location' : 'class'; S.persisting = 'inline'; S.notes = 'inline'; S.byClass = true; S.reach = 'normal';
    document.body.classList.add('trial');
    T.phase = 'view'; T.t0 = performance.now(); T.rec = { sheet: item.sheet, variant: item.variant, stratum: D().stratum, events: [] };
    render(); window.scrollTo(0, 0);
  }
  function endView() {
    const T = S.trial, item = T.list[T.i];
    T.rec.time_ms = Math.round(performance.now() - T.t0); T.phase = 'locate';
    const el = document.createElement('div');
    el.className = 'ovl'; el.id = 'picker';
    el.innerHTML = '<div class="dlg picker"><div class="top"><h3>在全图上点出它的位置</h3><span class="small">点一下你认为最该先修的问题在图上的哪里</span><button id="pk-undo">放弃这张</button></div><div id="pk-map"></div></div>';
    document.body.appendChild(el);
    $('#pk-map', el).innerHTML = mapSvg('', 'picker', item.sheet);
    $('#pk-map svg', el).addEventListener('click', ev => {
      const r = ev.currentTarget.getBoundingClientRect(), vb = ev.currentTarget.viewBox.baseVal, k = Math.min(r.width / vb.width, r.height / vb.height);
      const x = (ev.clientX - r.left - (r.width - vb.width * k) / 2) / k, y = (ev.clientY - r.top - (r.height - vb.height * k) / 2) / k;
      T.rec.point = [Math.round(x), Math.round(y)]; Object.assign(T.rec, hitTest(x, y));
      el.remove(); T.phase = 'ask'; showAsk();
    });
    $('#pk-undo', el).onclick = () => { el.remove(); T.rec.abandoned = true; T.rec.events = []; finishTrial(); };
  }
  function showAsk() {
    const rec = S.trial.rec, bcd = S.variant !== 'A', el = document.createElement('div');
    el.className = 'ovl ask'; el.id = 'ask';
    el.innerHTML = '<div class="dlg">' +
      '<div class="q"><b>你对「这是最该先修的问题」有几成把握？</b><div class="row">' + [['sure', '确定'], ['likely', '大致确定'], ['guess', '猜的']].map(o => '<button class="opt" data-conf="' + o[0] + '">' + o[1] + '</button>').join('') + '</div></div>' +
      (bcd ? '<div class="q"><b>页面给的信息和建议，够你定位要改的对象吗？</b><div class="row">' + [['enough', '够：知道改哪个、怎么改'], ['partial', '部分：知道对象，不知道怎么改'], ['lack', '不够']].map(o => '<button class="opt" data-suf="' + o[0] + '">' + o[1] + '</button>').join('') + '</div></div>' : '') +
      '<div class="q"><b>' + (bcd ? '哪里不够（可不填）' : '要在现有页面上动手修图，你还缺什么？（可不填）') + '</b><textarea id="ask-note" placeholder="一句话就行"></textarea></div>' +
      '<div class="q" style="margin-bottom:0"><button class="pri" id="ask-next" disabled>下一张</button> <span class="small" id="ask-hint">先选上面的答案</span></div></div>';
    document.body.appendChild(el);
    $('#ask-note', el).focus();
  }
  function finishTrial() {
    const T = S.trial, rec = T.rec;
    rec.note = ($('#ask-note') || {}).value || '';
    rec.opened = rec.events.filter(e => e.type === 'open').length;
    rec.viewed = unique(rec.events.filter(e => e.type === 'view').map(e => e.id)).length;
    rec.level_switches = rec.events.filter(e => e.type === 'level').length;
    rec.locates = rec.events.filter(e => e.type === 'locate').length;
    rec.first_crop_ms = (rec.events.find(e => e.type === 'open' || e.type === 'view') || {}).t;
    rec.first_row_ms = (rec.events.find(e => e.type === 'firstrow') || {}).t;
    S.results.push(rec);
    $('#ask').remove();
    T.i += 1; T.rec = null;
    if (T.i >= T.list.length) { S.mode = 'results'; S.trial = null; document.body.classList.remove('trial'); }
    else T.phase = 'intro';
    render(); window.scrollTo(0, 0);
  }
  const unique = a => a.filter((x, i) => a.indexOf(x) === i);
  function trialView() {
    const T = S.trial;
    if (!T) return '<div class="stage"><div class="cardx"><h2>对照试验</h2><p>每张图随机配一个版本：现状 / 按严重度平铺 / 按类别分诊 / 按位置的修图路线。图名和版本名先不显示，做完才揭晓。</p><ol>' +
      '<li>像平时一样看这张图的回读，找到「最该先修的一个问题」。计时从页面出现开始，到你按下按钮为止。</li><li>在全图上点出它的位置。</li><li>两三个问题，十秒以内。</li></ol>' +
      '<div class="controls">张数 ' + [4, 8, 16].map(n => '<label class="ctl"><input type="radio" name="tn" value="' + n + '"' + (n === S.trialN ? ' checked' : '') + '>' + n + '</label>').join('') + '<span class="sep"></span><label class="ctl"><input type="checkbox" id="hide-sus"' + (S.hideSuspects ? ' checked' : '') + '>隐藏「上一版之后动过」这句（测它贡献了多少）</label></div>' +
      '<p class="small">记录只在内存里，刷新就没了；做完到「结果」里导出 JSON。一个人做，每个版本 2 张，数字只用来看方向。</p><button class="pri go" id="trial-go">开始</button></div></div>';
    if (T.phase === 'intro') return '<div class="stage"><div class="cardx"><h2>第 ' + (T.i + 1) + ' / ' + T.list.length + ' 张</h2><p>找到「最该先修的一个问题」。你自己判断，通常是会让图读错、或者让这张图不能交付的那个。</p>' +
      '<p class="small">找到后按下面的按钮，再在全图上点出位置。看不下去可以放弃这张。</p><button class="pri go" id="trial-begin">开始看图</button></div></div>';
    return '<div class="bar"><span>第 ' + (T.i + 1) + ' / ' + T.list.length + ' 张</span><span class="clock" id="clock">00:00</span><span class="sp"></span><button id="trial-skip">这张放弃</button><button class="pri" id="trial-found">找到了，指出位置</button></div>' + variantView();
  }

  // ---------- results ----------
  function median(a) { const s = a.slice().sort((x, y) => x - y); return s.length ? s[Math.floor(s.length / 2)] : 0; }
  function viewResults() {
    const rs = S.results;
    if (!rs.length) return '<div class="wrap"><div class="stage" style="margin:20px auto"><div class="cardx"><h2>还没有试验记录</h2><p class="small">记录只在内存里。到「对照试验」做几张，这里会有表。</p><button class="pri" data-mode="trial">去试验</button></div></div></div>';
    const CONF = { sure: '确定', likely: '大致确定', guess: '猜的' }, SUF = { enough: '够', partial: '部分', lack: '不够' };
    const vs = VARIANTS.map(v => { const mine = rs.filter(r => r.variant === v.id && !r.abandoned); return { v, n: mine.length, time: median(mine.map(r => r.time_ms / 1000)), open: avg(mine.map(r => r.opened)), view: avg(mine.map(r => r.viewed)), hit: pct(mine.filter(r => r.hit).length, mine.length), enough: pct(mine.filter(r => r.suf === 'enough').length, mine.filter(r => r.suf).length) }; });
    const head = '<tr><th>#</th><th>版本</th><th>图 · 改动</th><th>找到用时</th><th>点的位置</th><th>打开局部图</th><th>看到局部图</th><th>把握</th><th>建议够不够</th><th>备注</th></tr>';
    return '<div class="wrap"><h2 style="margin:16px 0 4px">试验结果（' + rs.length + ' 张）</h2>' +
      '<p class="small">「打开」= 主动点开一张局部图；「看到」= 有半张局部图在屏幕上停了 0.4 秒以上（包括顺手滚过去的）。「位置」= 点的地方离改动引起的问题 40 px 以内算中。一个人、每版本 2 张，只看方向。</p>' +
      '<table style="margin:10px 0"><tr><th>版本</th><th>张数</th><th>找到用时（中位）</th><th>打开局部图（均）</th><th>看到局部图（均）</th><th>点中</th><th>建议够用</th></tr>' +
      vs.map(x => '<tr><td>' + esc(x.v.full) + '</td><td class="c">' + x.n + '</td><td class="c"><b>' + x.time.toFixed(1) + ' s</b></td><td class="c">' + x.open.toFixed(1) + '</td><td class="c">' + x.view.toFixed(1) + '</td><td class="c">' + x.hit + '</td><td class="c">' + x.enough + '</td></tr>').join('') + '</table>' +
      '<div><button data-act="export">导出 JSON</button> <button data-act="tsv">复制成表格</button> <button data-act="clear">清空</button> <button data-mode="trial">再做一组</button><span id="tsv-out"></span></div>' +
      '<details style="margin-top:10px"><summary>逐张</summary><table class="res">' + head + rs.map((r, i) => '<tr><td>' + (i + 1) + '</td><td>' + esc(VARIANTS.find(v => v.id === r.variant).full) + '</td><td class="small"><span class="mono">' + esc(r.sheet) + '</span><br>' + esc(DATA.sheets[r.sheet].note) + '</td>' +
        (r.abandoned ? '<td class="c" colspan="7">放弃了</td>' : '<td class="c"><b>' + (r.time_ms / 1000).toFixed(1) + ' s</b>' + (r.first_row_ms != null ? '<div class="small">首次看到条目 ' + (r.first_row_ms / 1000).toFixed(1) + ' s</div>' : '') + '</td><td class="c"><span class="' + (r.hit ? 'hit' : 'miss') + '">' + (r.hit ? '中' : '偏 ' + r.error_px + ' px') + '</span> <button class="lnk" data-act="spot" data-i="' + i + '">看</button><span class="spot" id="spot-' + i + '"></span></td>' +
          '<td class="c">' + r.opened + (r.level_switches ? '<div class="small">换级 ' + r.level_switches + '</div>' : '') + '</td><td class="c">' + r.viewed + '</td><td class="c">' + (CONF[r.conf] || '—') + '</td><td class="c">' + (r.variant === 'A' ? '—' : SUF[r.suf] || '—') + '</td><td class="small">' + esc(r.note) + '</td>') + '</tr>').join('') + '</table></details>' +
      '<h3 style="margin:16px 0 4px">客观核对：排在第一位的问题有没有点名被改动的对象</h3>' + objective() + '</div>';
  }
  const avg = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
  const pct = (a, b) => b ? Math.round(100 * a / b) + '%' : '—';
  function exportAll() {
    const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), results: S.results }, null, 1)], { type: 'application/json' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = 'readback-triage-trials.json'; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 3000);
  }
  function copyText(text) {
    const done = () => { const el = $('#tsv-out'); if (el) el.textContent = ' 已复制'; };
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => showText(text));
    else showText(text);
  }
  function showText(text) { const el = $('#tsv-out'); if (el) el.innerHTML = '<pre>' + esc(text) + '</pre>'; else window.prompt('复制：', text); }

  // ---------- render ----------
  function render() {
    document.body.classList.toggle('trial', S.mode === 'trial' && !!S.trial && S.trial.phase !== 'intro');
    if (S.mode === 'trial') app.innerHTML = header() + trialView();
    else if (S.mode === 'results') app.innerHTML = header() + viewResults();
    else if (S.browse === 'panels') app.innerHTML = header() + panelsView();
    else app.innerHTML = header() + '<div class="wrap">' + intro() + controls() + info() + variantView() + '</div>' + switcher();
    after();
  }
  function after() {
    $$('[data-crop]').forEach(el => paint(el));
    $$('[data-view]').forEach(el => io.observe(el));
    if (S.variant === 'A') mountA();
    if ($('#d-map')) mountD();
  }
  setInterval(() => { const c = $('#clock'), T = S.trial; if (c && T && T.phase === 'view') c.textContent = clockText(performance.now() - T.t0); }, 200);
  window.addEventListener('resize', () => sizePins($('#d-map svg')));

  // ---------- events ----------
  document.addEventListener('keydown', ev => {
    if (ev.key === 'Escape' && light) { closeLightbox(); return; }
    if (S.mode !== 'browse' || S.browse !== 'page' || ev.target.closest('input,textarea,select')) return;
    if (ev.key === 'ArrowLeft' || ev.key === 'ArrowRight') {
      const i = VARIANTS.findIndex(v => v.id === S.variant);
      setVariant(VARIANTS[(i + (ev.key === 'ArrowRight' ? 1 : VARIANTS.length - 1)) % VARIANTS.length].id); ev.preventDefault();
    }
  });
  function setVariant(id) {
    // Each variant keeps its own default rule until the user picks one: D is about position, C about class.
    if (id === 'D' && S.rule === 'class') S.rule = 'location';
    else if (id === 'C' && S.rule === 'location') S.rule = 'class';
    S.variant = id; S.mode = 'browse'; S.browse = 'page'; S.seenIntro = true;
    try { history.replaceState(null, '', location.pathname + '?variant=' + id); } catch (e) { /* file:// with odd chars: the page still works */ }
    render(); window.scrollTo(0, 0);
  }
  document.addEventListener('click', ev => {
    const b = ev.target.closest('button'); if (!b) return;
    const d = b.dataset;
    if (d.variant) return setVariant(d.variant);
    if (d.mode) { S.mode = d.mode; if (d.browse) S.browse = d.browse; if (d.mode === 'trial') S.trial = null; closeLightbox(); render(); window.scrollTo(0, 0); return; }
    if (d.tab) { S.tab = d.tab; return render(); }
    if (d.openItem) { log('open', d.openItem); const it = itemById(d.openItem); return openLightbox('i:' + d.openItem, it.check + ' · ' + (it.kind || '')); }
    if (d.zoom) { log('open', d.zoom); const p = probById(d.zoom); return p && openLightbox('p:' + d.zoom, p.title); }
    if (d.map) return openMap(d.map);
    if (d.goto) return zoomTo(d.goto);
    if (d.level) { log('level', d.level); return setCardLevel(d.pid, d.level); }
    if (d.lbLevel) { log('level', d.lbLevel); light.level = d.lbLevel; return drawLightbox(); }
    if (d.conf || d.suf) {
      $$('[data-' + (d.conf ? 'conf' : 'suf') + ']', $('#ask')).forEach(x => x.classList.toggle('on', x === b));
      S.trial.rec[d.conf ? 'conf' : 'suf'] = d.conf || d.suf;
      const need = S.variant !== 'A' && !S.trial.rec.suf;
      $('#ask-next').disabled = !S.trial.rec.conf || need;
      $('#ask-hint').textContent = $('#ask-next').disabled ? (need ? '还差「够不够用」' : '先选把握') : '';
      return;
    }
    if (d.tier !== undefined) { const row = DATA.kinds[+d.tier], key = [row.class, row.kind, row.result].join('|'), now = PATHS.indexOf(solo([row.class, row.kind, row.result]));
      const next = PATHS[(now + 1) % PATHS.length]; if (next === row.path) delete S.tier[key]; else S.tier[key] = next; return render(); }
    if (d.copy === 'repair') { const text = JSON.stringify(D().triage.repair[S.rule], null, 1); if ($('#tsv-out')) copyText(text); else { const s = document.createElement('span'); s.id = 'tsv-out'; b.parentNode.appendChild(s); copyText(text); } return; }
    if (d.act === 'export') return exportAll();
    if (d.act === 'tsv') return copyText(tsv());
    if (d.act === 'clear') { S.results = []; return render(); }
    if (d.act === 'spot') { const slot = $('#spot-' + d.i), r = S.results[+d.i];
      if (slot.firstChild) return slot.removeChild(slot.firstChild);
      const boxes = targetsFor(r.sheet);
      slot.innerHTML = mapSvg(boxes.map(t => '<rect class="mark" x="' + t.box[0] + '" y="' + t.box[1] + '" width="' + (t.box[2] - t.box[0]) + '" height="' + (t.box[3] - t.box[1]) + '"/>').join('') + '<path class="xmark" d="M' + (r.point[0] - 9) + ' ' + (r.point[1] - 9) + 'l18 18m0 -18l-18 18"/>', '', r.sheet, true); return; }
    if (d.act === 'panels') { S.tab = 'link'; S.browse = 'panels'; return render(); }
    if (b.id === 'd-reset') { const svg = $('#d-map svg'); svg.setAttribute('viewBox', DATA.view.join(' ')); return sizePins(svg); }
    if (b.id === 'trial-go') return startTrials(), render();
    if (b.id === 'trial-begin') return beginView();
    if (b.id === 'trial-found') return endView();
    if (b.id === 'trial-skip') { S.trial.rec.abandoned = true; S.trial.rec.time_ms = Math.round(performance.now() - S.trial.t0); S.trial.rec.events = []; return finishTrial(); }
    if (b.id === 'ask-next') return finishTrial();
  });
  function targetsFor(sheet) {
    const out = [], d = DATA.sheets[sheet];
    d.triage.problems.forEach(p => { if (p.state === 'new' && !HELD.includes(p.class) && p.box) out.push({ box: p.box }); });
    Object.keys(d.triage.changed || {}).forEach(k => out.push({ box: d.triage.changed[k].now }));
    return out;
  }
  function tsv() {
    const head = ['#', 'variant', 'sheet', 'stratum', 'time_s', 'hit', 'error_px', 'opened', 'viewed', 'level_switches', 'locates', 'first_crop_s', 'first_row_s', 'confidence', 'sufficiency', 'abandoned', 'note'];
    return [head.join('\t')].concat(S.results.map((r, i) => [i + 1, r.variant, r.sheet, r.stratum, (r.time_ms / 1000).toFixed(1), r.hit ? 1 : 0, r.error_px, r.opened, r.viewed, r.level_switches, r.locates,
      r.first_crop_ms != null ? (r.first_crop_ms / 1000).toFixed(1) : '', r.first_row_ms != null ? (r.first_row_ms / 1000).toFixed(1) : '', r.conf || '', r.suf || '', r.abandoned ? 1 : 0, String(r.note || '').replace(/\s+/g, ' ')].join('\t'))).join('\n');
  }
  document.addEventListener('change', ev => {
    const el = ev.target, d = el.dataset;
    if (el.id === 'sheet') { S.sheet = el.value; S.ref = S.sheet === 'base' ? 'none' : 'base'; S.preview = null; return render(); }
    if (el.id === 'ref') { S.ref = el.value; return render(); }
    if (el.id === 'hide-sus') { S.hideSuspects = el.checked; return; }
    if (el.name === 'tn') { S.trialN = +el.value; return; }
    if (d.rule) { S.rule = d.rule; return render(); }
    if (d.k === 'persisting') { S.persisting = el.checked ? 'after' : 'inline'; return render(); }
    if (d.k === 'notes') { S.notes = el.checked ? 'tail' : 'inline'; return render(); }
    if (d.k === 'byclass') { S.byClass = el.checked; return render(); }
    if (d.k === 'hide') { S.hideSuspects = el.checked; return render(); }
    if (d.k === 'cause') { S.cause = el.checked; return render(); }
    if (d.level) { S.level = d.level; return render(); }
    if (d.levelOpt) { S.level = d.levelOpt; return render(); }
    if (d.reach) { S.reach = d.reach; return render(); }
    if (d.preview) { S.preview = d.preview; return render(); }
    if (d.fixed) { S.fixed[S.sheet][d.fixed] = el.checked; return render(); }
  });

  render();
  window.__rb = { S: S, DATA: DATA, render: render };   // 调试用：控制台里能直接看状态
})();
