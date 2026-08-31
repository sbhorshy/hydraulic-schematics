# -*- coding: utf-8 -*-
"""从 skill 模板 render_l0_sheet.py 生成 1#系统原理图/render.py 副本。

补丁内容:
  1. 路径常量全部指向本工作目录(intent/layout/catalog/输出)。
  2. PRESSURE_CLASS 增 sense 级(气侧支路,1.0T);CSS 增 .ln-sense。
  3. Sheet.wire_taps():taps 端口到端口专线(预检处方"气侧走 taps 或专线")。
  4. dangling():taps 两端端口记为已使用。
  5. main():wire 后接 wire_taps;结构自检;追溯清单 write_manifest。
  6. 图例增气侧支路行;图签改本系统口径。
"""
import io
import os

SRC = r'D:/File/COMAC/组件库/.agents/skills/hydraulic-schematic/scripts/render_l0_sheet.py'
DST = r'D:/File/COMAC/组件库/1#系统原理图/render.py'

s = io.open(SRC, encoding='utf-8').read()

# ---- 1. 路径常量 ----
s = s.replace(
    "    src = os.path.join(HERE, '..', 'system-1.intent.yaml')",
    "    src = os.path.join(HERE, '1#系统.intent.yaml')")
s = s.replace(
    "    with io.open(os.path.join(HERE, '..', 'component-catalog.json'),",
    "    with io.open(os.path.join(HERE, 'component-catalog.json'),")

# ---- 2. sense 线型 + CSS ----
s = s.replace(
    "PRESSURE_CLASS = {\n    'pressure': 'high',",
    "PRESSURE_CLASS = {\n    'sense': 'low',        # 气侧支路(充气活门/压力表):1.0 T 实线,归低压级\n    'pressure': 'high',")
s = s.replace(
    "  .ln-case_drain { stroke-width: %(lo).2f; }\n  .suc-mark",
    "  .ln-case_drain { stroke-width: %(lo).2f; }\n"
    "  .ln-sense      { stroke-width: %(lo).2f; }\n  .suc-mark")

# ---- 3. wire_taps 方法(插在 groups() 之前) ----
wire_taps = '''
    # ---------- taps 气侧/测量支路(L0 规范 11.1;本副本增量) ----------
    def wire_taps(self):
        """渲染 taps:传感器端口到被测端口的气侧专线。返回空三通表。

        预检处方:气侧端口(medium=pneumatic)不得串入液压 paths,经 taps
        声明、此处画专线。接入点恰为元件端口(符号自带红点),不另画三通;
        线型归 sense(1.0 T)。起自 sensor 端口锚点方向,末端直接进 at 端口。
        """
        juncs = []
        for t in self.i.get('taps') or []:
            stok, atok = t['sensor'], t['at']
            sinst, spid = stok.split('.', 1)
            ainst, apid = atok.split('.', 1)
            pa = self.port(stok)
            pb = self.port(atok)
            aa = self.abs[(sinst, spid)][2]
            self.port_lt[(sinst, spid)] = 'sense'
            S = 18.0
            stub = {'left': (-S, 0), 'right': (S, 0),
                    'up': (0, -S), 'down': (0, S)}[aa]
            a1 = (pa[0] + stub[0], pa[1] + stub[1])
            cands = []
            if abs(a1[0] - pb[0]) < 0.5 or abs(a1[1] - pb[1]) < 0.5:
                cands.append([a1, pb])
            # 先按 sensor 锚点出线,再一折进入 at 端口;两种折向择优。
            cands.append([a1, (a1[0], pb[1]), pb])
            cands.append([a1, (pb[0], a1[1]), pb])
            obs = self.obstacles(exclude=(sinst, ainst))
            best, bad = None, None
            for c in cands:
                pts = self.dedup([pa] + c)
                if len(pts) < 2:
                    continue
                h = self.hits(pts, obs, skip_ends=True)
                ov = self.overlap(pts, self.drawn)
                tx = self.hits(pts, self.textboxes, tol=0.0)
                cr = self.crossings(pts, self.drawn)
                ln = sum(abs(pts[k + 1][0] - pts[k][0])
                         + abs(pts[k + 1][1] - pts[k][1])
                         for k in range(len(pts) - 1))
                sc = (h * 10000 + ov * 3000 + tx * 900
                      + cr * 120 + ln + len(pts) * 5)
                if bad is None or sc < bad:
                    bad, best = sc, pts
            for k in range(len(best) - 1):
                self.drawn.append((best[k], best[k + 1]))
            self.polys.append(('sense', best))
        return juncs

    # ---------- 分组虚线框(技术规范 10.7) ----------'''
s = s.replace('''
    # ---------- 分组虚线框(技术规范 10.7) ----------''', wire_taps, 1)

# ---- 4. dangling():taps 两端计为已使用 ----
s = s.replace(
    """                if '.' in tok:
                    used.add((inst, tok.split('.', 1)[1]))
                else:
                    mp = self.types[self.i['parts'][inst]]['main_path']
                    if mp:
                        used.add((inst, mp['in']))
                        used.add((inst, mp['out']))
        marks, names = [], []""",
    """                if '.' in tok:
                    used.add((inst, tok.split('.', 1)[1]))
                else:
                    mp = self.types[self.i['parts'][inst]]['main_path']
                    if mp:
                        used.add((inst, mp['in']))
                        used.add((inst, mp['out']))
        for t in self.i.get('taps') or []:
            sinst, spid = t['sensor'].split('.', 1)
            used.add((sinst, spid))
            ainst, apid = t['at'].split('.', 1)
            if ainst in self.i['parts']:
                used.add((ainst, apid))
        marks, names = [], []""")

# ---- 5. main():wire 后接 taps、自检、清单 ----
s = s.replace(
    """    s = Sheet(intent, layout, catalog)
    s.place()
    s.build_textboxes()
    _segs, junc, bus, polys = s.wire()

    # 先求交叉,再把跨越线打断,最后出图元。顺序不能反:
    # 打断后的折线不能再用来求交叉(断口处已无线段)。
    cross = s.find_crossings(junc, polys)
    segs = []
    for lt, pts in polys:""",
    """    s = Sheet(intent, layout, catalog)
    s.place()
    s.build_textboxes()
    _segs, junc, bus, polys = s.wire()

    # taps 气侧支路:在 path 折线之后追加,一并求交叉/避让。
    path_polys = list(s.polys)
    npath_polys = len(path_polys)
    tap_junc = s.wire_taps()
    tap_polys = s.polys[npath_polys:]
    junc = junc + tap_junc

    # 先求交叉,再把跨越线打断,最后出图元。顺序不能反:
    # 打断后的折线不能再用来求交叉(断口处已无线段)。
    cross = s.find_crossings(junc, s.polys)
    segs = []
    for lt, pts in s.polys:""")

# 自检 + 清单:插在写 SVG 之前/之后
s = s.replace(
    """    W, H = layout['canvas']['width'], layout['canvas']['height']
    P = []""",
    """    self_check(intent, layout, s, path_polys, tap_polys)

    W, H = layout['canvas']['width'], layout['canvas']['height']
    P = []""")

s = s.replace(
    """    outp = os.path.join(HERE, '1#系统原理图.svg')
    with io.open(outp, 'w', encoding='utf-8') as f:
        f.write('\\n'.join(P))
    print('wrote', outp)""",
    """    outp = os.path.join(HERE, '1#系统原理图.svg')
    with io.open(outp, 'w', encoding='utf-8') as f:
        f.write('\\n'.join(P))
    print('wrote', outp)
    write_manifest(os.path.join(HERE, '1#系统_topology.md'),
                   intent, layout, s, path_polys, tap_polys, dnames)""")

# 头部说明文字
s = s.replace(
    """    P.append('<text class="lbl" x="%d" y="44">1# 液压系统原理图  '
             '(由 system-1.intent.yaml 生成,含 4 个临时符号,不可用于工程放行)</text>' % 40)""",
    """    P.append('<text class="lbl" x="%d" y="44">1# 液压系统原理图  '
             '(由 1#系统.intent.yaml 生成,源清单 1#系统组件.json;'
             ' EDP/EMP/FWSOV provisional,油箱 draft,优先阀/充气活门/压力表 draft,'
             '不可用于工程放行)</text>' % 40)""")

# 图签
s = s.replace(
    """    row2 = ('部件 %d   |   网络 %d   |   未知项 %d   |   临时符号 4 (EDP/EMP/FWSOV/蓄压器)'
            '   |   悬空端口 %d: %s'
            % (len(intent['parts']), nnet, len(intent['unknown']),
               len(dnames), ' '.join(dnames) if dnames else '无'))""",
    """    row2 = ('部件 %d   |   网络 %d   |   气侧支路 %d   |   未知项 %d   '
            '|   临时/草稿符号: EDP EMP FWSOV provisional; 油箱 draft(描摹); '
            '优先阀 充气活门 压力表 draft   |   悬空端口 %d: %s'
            % (len(intent['parts']), nnet, len(intent.get('taps') or []),
               len(intent['unknown']),
               len(dnames), ' '.join(dnames) if dnames else '无'))""")

# 图例增气侧支路行
s = s.replace(
    """        ('Suction Lines  吸油:连续基线 + 周期性五斜杠组  1.0 T (S=%g)' % S,
         ('suction', lo)),""",
    """        ('Gas-side Branch 气侧支路 (充气活门/压力表)          1.0 T', lo),
        ('Suction Lines  吸油:连续基线 + 周期性五斜杠组  1.0 T (S=%g)' % S,
         ('suction', lo)),""")

# ---- 6. 追加 near_pt / self_check / write_manifest ----
s += '''

# ---------- 结构自检(rendering-rules"结构自检";本副本增量) ----------
def near_pt(p, q, tol=1.0):
    return abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol


def self_check(intent, layout, s, path_polys, tap_polys):
    """渲染成品落盘前核对输入覆盖。缺项打印并以退出码 1 终止。"""
    missing = []
    for inst in intent['parts']:
        if inst not in layout['nodes']:
            missing.append('part 无节点: %s' % inst)
    ends = set()
    for _lt, pts in path_polys:
        ends.add((round(pts[0][0], 1), round(pts[0][1], 1)))
        ends.add((round(pts[-1][0], 1), round(pts[-1][1], 1)))
    nseg = 0
    for p in intent['paths']:
        for k in range(len(p) - 1):
            nseg += 1
            for tok in (p[k], p[k + 1]):
                if tok.startswith('@'):
                    continue
                q = s.port(tok)
                if (round(q[0], 1), round(q[1], 1)) not in ends:
                    missing.append('path 段端点未画出: %s @ (%.1f,%.1f)'
                                   % (tok, q[0], q[1]))
    if len(path_polys) < nseg:
        missing.append('path 段 %d 条,折线仅 %d 条' % (nseg, len(path_polys)))
    if len(tap_polys) != len(intent.get('taps') or []):
        missing.append('taps %d 条,支路仅 %d 条'
                       % (len(intent.get('taps') or []), len(tap_polys)))
    for t, (_lt, pts) in zip(intent.get('taps') or [], tap_polys):
        sinst, spid = t['sensor'].split('.', 1)
        if not near_pt(pts[0], s.abs[(sinst, spid)], 1.0):
            missing.append('tap 支路未起自 sensor 端口: %s' % t['sensor'])
        ainst, apid = t['at'].split('.', 1)
        if not near_pt(pts[-1], s.abs[(ainst, apid)], 1.0):
            missing.append('tap 支路未止于 at 端口: %s' % t['at'])
    if missing:
        print('结构自检失败,扣留成品:')
        for m in missing:
            print('  -', m)
        sys.exit(1)


# ---------- 追溯清单(rendering-rules;本副本增量) ----------
def write_manifest(path, intent, layout, s, path_polys, tap_polys, dnames):
    L = []
    L.append('# %s 追溯清单' % intent['system'])
    L.append('')
    L.append('来源: `1#系统.intent.yaml`(L0 v%s,目录 %s,成熟度 %s),'
             '由工程师手写组件清单 `1#系统组件.json` 落成。'
             % (intent['l0_version'], intent['catalog'], intent['maturity']))
    L.append('图面: `1#系统原理图.svg`,布局 `1#系统.layout.json`。')
    L.append('')
    L.append('## 节点(part)映射')
    L.append('')
    L.append('| intent 行 | 实例 | 类型 | 清单项 | 图上元件 | 符号文件 |')
    L.append('|---|---|---|---|---|---|')
    item_map = [
        ('TANK-001', '清单17 bootstrap-type-reservoir(油箱)'),
        ('FSOV-001', '清单3 firewall-shutoff-valve(FWSOV)'),
        ('EDP-001', '清单1 EDP'),
        ('EMP-001', '清单2 EMP'),
        ('PF-001', '清单5 filter-line-shutoff-dp(压力油滤)'),
        ('CDF-001', '清单6 filter-line-shutoff-dp(壳体回油滤)'),
        ('RF-001', '清单7 filter-line-shutoff-dp(回油滤)'),
        ('PRV-001', '清单9 priority-valve(优先阀)'),
        ('PRV-002', '清单14 priority-valve(自增压优先阀)'),
        ('ACC-001', '清单15 accumulator(系统蓄压器)'),
        ('ACV-001', '清单16 air-charging-valve(充气活门)'),
        ('PG-001', '清单16 pressure-gauge(充气压力表)'),
        ('QDP-001', '清单8 quick-disconnect(地面压力快卸接头)'),
        ('QDR-001', '清单4 quick-disconnect(地面回油快卸接头)'),
    ]
    items = dict(item_map)
    for inst, typ in intent['parts'].items():
        nd = layout['nodes'].get(inst, {})
        L.append('| %d | %s | %s | %s | inst-%s | %s |'
                 % (line_no(intent, 'parts', inst), inst, typ,
                    items.get(inst, ''), inst,
                    os.path.basename(nd.get('symbol', '缺'))))
    for eid, etyp in intent.get('extern', {}).items():
        e = layout['externs'][eid]
        L.append('| %d | %s | extern:%s | 清单18 用户(未建模为组件) | 边界标记 (%d,%d) | — |'
                 % (line_no(intent, 'extern', eid), eid, etyp, e['x'], e['y']))
    L.append('')
    L.append('## 连接(边)映射')
    L.append('')
    L.append('| intent 行 | 语句 | 图上折线(端点) | 线型 | 实例数 |')
    L.append('|---|---|---|---|---|')
    lm = line_map_all(intent)
    for pi, p in enumerate(intent['paths']):
        line = lm['paths'][pi] if pi < len(lm['paths']) else 0
        for k in range(len(p) - 1):
            a, b = p[k], p[k + 1]
            qa = s.port(a, 'out')
            qb = s.port(b, 'in')
            lt = [l for l, pts in path_polys
                  if near_pt(pts[0], qa, 1.0) and near_pt(pts[-1], qb, 1.0)]
            L.append('| %d | `%s -> %s` | (%.0f,%.0f)->(%.0f,%.0f) | %s | 1 |'
                     % (line, a, b, qa[0], qa[1], qb[0], qb[1],
                        lt[0] if lt else '?'))
    L.append('')
    L.append('## 气侧支路(taps,规范 11.1)')
    L.append('')
    L.append('| intent 行 | 语句 | 图上支路(端点) |')
    L.append('|---|---|---|')
    for ti, t in enumerate(intent.get('taps') or []):
        line = lm['taps'][ti] if ti < len(lm['taps']) else 0
        _lt, pts = tap_polys[ti]
        L.append('| %d | `%s` | (%.0f,%.0f)->(%.0f,%.0f) |'
                 % (line, json.dumps(t, ensure_ascii=False),
                    pts[0][0], pts[0][1], pts[-1][0], pts[-1][1]))
    L.append('')
    L.append('## 简化说明(概念级抽象,逐条披露)')
    L.append('')
    L.append('1. 清单 18 项中 4 项未入图:能源转换装置选择阀、能源转换装置'
             '(判读疑似 PTU)、集中加油组件——类型与符号均未登记;地面加油单向阀'
             '——类型受控(check_valve)但加油口拓扑未声明。对应 unknown: '
             'ETP-selector-valve-not-in-catalog / ETP-unit-not-in-catalog / '
             'ground-refuel-assembly-not-in-catalog / '
             'ground-refuel-check-valve-connection-unknown。')
    L.append('2. 壳体回油滤清单只声明 1 只,双泵壳体回油经 @CASE 母线合流入滤'
             '(unknown: TANK-001-return-port-count-unconfirmed 同源问题:'
             '主回油+壳体回油共用油箱 return_in 端口)。')
    L.append('3. FWSOV 装吸油侧沿 system-1 审查卡 D-1 判断;若实际在压力侧须重接'
             '(unknown: FSOV-001-suction-side-placement-assumed)。')
    L.append('4. 气侧件(充气活门/充气压力表)按预检处方走 taps 专线,不入液压 paths;'
             '充气源去向未声明,charge_port 由压力表接入即为末端'
             '(unknown: accumulator-charge-source-not-declared)。')
    L.append('5. 两只地面快卸接头画为断开位:机侧接入母线支路,地面侧开放,'
             '悬空端口红圈是断开位语义而非缺线'
             '(unknown: QD-open-ends-are-disconnected-position)。')
    L.append('6. 悬空端口 %d 个: %s。其中 EDP.drive_shaft、EMP.elec_power、'
             'FSOV.command 为动力源/命令端去向未声明。'
             % (len(dnames), ' '.join(dnames)))
    L.append('7. 目录为本工作目录扩展副本(0.3-draft):基于 skill 快照 0.2-draft '
             '新增 8 个类型(油滤三变体/快卸接头两变体/优先阀/充气活门/充气压力表),'
             '详见 build_catalog.py;这些类型尚未回登记规范源 '
             '已标注/component-catalog.json,冻结前须补。')
    L.append('')
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write('\\n'.join(L))
    print('wrote', path)


def line_no(intent, section, key):
    """预检器行号映射:与 preflight.line_map 同源,惰性调用。"""
    global _LINE_MAP_CACHE
    try:
        return _LINE_MAP_CACHE[section][key]
    except NameError:
        import preflight as _pf
        with io.open(os.path.join(HERE, '1#系统.intent.yaml'),
                     encoding='utf-8') as f:
            _LINE_MAP_CACHE = _pf.line_map(f.read())
        return _LINE_MAP_CACHE[section][key]


def line_map_all(intent):
    import preflight as _pf
    global _LINE_MAP_CACHE
    try:
        _LINE_MAP_CACHE
    except NameError:
        with io.open(os.path.join(HERE, '1#系统.intent.yaml'),
                     encoding='utf-8') as f:
            _LINE_MAP_CACHE = _pf.line_map(f.read())
    lm = dict(_LINE_MAP_CACHE)
    lm['taps'] = _LINE_MAP_CACHE.get('taps', [])
    return lm
'''

io.open(DST, 'w', encoding='utf-8').write(s)
print('render.py 写出: %d 行' % s.count('\n'))
