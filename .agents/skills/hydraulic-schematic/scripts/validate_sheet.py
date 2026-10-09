# -*- coding: utf-8 -*-
"""整图结构校核 —— 技术规范 10.10 闭环的确定性环节。

不看图,只算几何。产出 validation-report.json,每项判定附坐标或 ID,
供感知校核环节(PNG 回读)之前的门禁使用。

用法: python3 validate_sheet.py [工作目录]
退出码 1 表示 validation: failed。
"""
from endpoint_usage import (endpoint_usage, check_disclosure, symbol_contract,
                            write_contract_failure, resolve_symbol)

import io
import json
import math
import os
import re
import sys
from sheet_geometry import load_geometry
from topology_reconciliation import reconcile_topology
from layout_clearance import measure_runs, nearest_components, measure_corridors, measure_groups
from endpoint_checks import check_endpoints, check_bodies
from xml.etree import ElementTree as ET
import xml.etree.ElementTree as ET
from stroke_checks import check_widths
from proofreading_evidence import assess_png, enrich_report, resolve_catalog, write_report

HERE = os.path.dirname(os.path.abspath(__file__))
SHEET = os.path.join(HERE, '1#系统原理图.svg')
LAYOUT = os.path.join(HERE, '1#系统.layout.json')
INTENT = os.path.join(HERE, '1#系统.intent.yaml')
CATALOG = os.path.join(HERE, 'component-catalog.json')
NS = 'http://www.w3.org/2000/svg'

# ---------- 构图预算（B1–B7）----------
# 与 .agents/skills/hydraulic-schematic/references/rendering-rules.md
# 『数值构图预算（concept 档 v1）』表同源，改动须两处同步。
# 定位是"预算披露 + 超限告警"：除交叉（B1，恒为 0）硬 fail 外，
# 其余超限记 WARN（V19）。composition_budget 状态口径：
#   pass=达标 / over=超限走告警通道 / exempt=表注豁免或存量披露 / fail=B1 专用失败通道。
BUDGET = {
    'B1': {'metric': '线线交叉', 'budget': 0,
           'note': '恒为 0，无桥接豁免——难避免优先改道'},
    'B2': {'metric': '折返次数', 'budget_max_single': 3, 'budget_total': 40},
    'B3': {'metric': '绕行比（路线长÷直角曼哈顿距）', 'budget': 1.5,
           'budget_boundary': 4.0,
           'note': '经边界走廊进出边界端子的走线 ≤4 且须披露'},
    'B4': {'metric': '最短走线段(px)', 'budget': 8.0},
    'B5': {'metric': '节点盒最小净距(px)', 'budget': 40.0},
    'B6': {'metric': '容器走廊(px)', 'budget_group_padding': 14.0,
           'budget_avoid_corridor': 12.0},
    'B7': {'metric': '标签净空(px)', 'budget': 6.0},
}
# 边界端子：图幅边缘外部接口。前两个来自 layout.externs（用户供/回油），
# 第三个是油箱侧通道端子，坐标见 1# 图追溯清单披露的边界走廊终点。
BOUNDARY_TERMINALS = [(1480.0, 300.0), (1480.0, 700.0), (60.0, 514.4)]
# 存量披露：1# 系统图为历史版本（rendering-rules 预算表注¹），
# 两条油箱侧通道线单条折返 4、绕行比 ≈1.6/≈4.0 超预算，
# 按"下版改图收敛或显式披露"处理，记 exempt，不作为新出图先例。
LEGACY_DISCLOSURE = ('存量历史版本（rendering-rules 预算表注¹）：'
                     '油箱侧通道线折返 4 次、绕行比 1.571/3.973，'
                     '按下版收敛或显式披露处理')


def read_symbol(path):
    """返回 (markup, (vx,vy,vw,vh), {port_id: (x, y, anchor, role, medium)})."""
    tree = ET.parse(path)
    root = tree.getroot()
    vb = [float(v) for v in root.get('viewBox').replace(',', ' ').split()]
    cp = [g for g in root.iter() if g.get('id') == 'connection-points']
    ports = {}
    for c in (cp[0] if cp else []):
        pid = c.get('data-port-id')
        if not pid:
            continue
        cx, cy = float(c.get('cx')), float(c.get('cy'))
        ports[pid] = (cx, cy, c.get('data-anchor-direction'),
                      c.get('data-port-role'), c.get('data-medium'))
    return '', (vb[0], vb[1], vb[2], vb[3]), ports


def load_yaml(p):
    from ruamel.yaml import YAML
    y = YAML(typ='safe', pure=True)
    y.version = (1, 2)
    with io.open(p, encoding='utf-8') as f:
        return y.load(f)


def symbol_path(ref):
    return resolve_symbol(ref, HERE, os.path.dirname(CATALOG))


def seg_rect_hit(p0, p1, rect, tol=2.0):
    """线段是否穿越矩形内部(仅正交段)。返回穿越长度。"""
    x0, y0 = p0
    x1, y1 = p1
    rx0, ry0, rx1, ry1 = rect
    rx0, ry0, rx1, ry1 = rx0 + tol, ry0 + tol, rx1 - tol, ry1 - tol
    if rx1 <= rx0 or ry1 <= ry0:
        return 0.0
    if abs(y1 - y0) < 0.5:          # 水平段
        if not (ry0 < y0 < ry1):
            return 0.0
        a, b = sorted((x0, x1))
        return max(0.0, min(b, rx1) - max(a, rx0))
    if abs(x1 - x0) < 0.5:          # 垂直段
        if not (rx0 < x0 < rx1):
            return 0.0
        a, b = sorted((y0, y1))
        return max(0.0, min(b, ry1) - max(a, ry0))
    return 0.0


def main(argv=None):
    global HERE, SHEET, LAYOUT, INTENT, CATALOG
    args = list(sys.argv[1:] if argv is None else argv)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    HERE = os.path.abspath(args[0]) if args else script_dir
    SHEET = os.path.join(HERE, '1#系统原理图.svg')
    LAYOUT = os.path.join(HERE, '1#系统.layout.json')
    INTENT = os.path.join(HERE, '1#系统.intent.yaml')
    CATALOG = str(resolve_catalog(HERE, tool_dir=script_dir))
    # A failed or interrupted run must not leave the last successful report current.
    for name in ('validation-report.json', 'validation-report.json.sha256'):
        path = os.path.join(HERE, name)
        if os.path.isfile(path):
            os.unlink(path)
    F, W, ev = [], [], []          # fail, warn, evidence
    intent = load_yaml(INTENT)
    L = json.load(io.open(LAYOUT, encoding='utf-8'))
    cat = json.load(io.open(CATALOG, encoding='utf-8'))
    T = {c['component_type']: c for c in cat['components']}
    inventory = endpoint_usage(intent, T, L['nodes'])
    contract_issues = symbol_contract(intent, T, L['nodes'], HERE, os.path.dirname(CATALOG))
    if contract_issues:
        return write_contract_failure(HERE, inventory, contract_issues, intent.get('unknown') or [])
    SHIFT = L.get('canvas_shift_x', 0)
    CW, CH = L['canvas']['width'], L['canvas']['height']

    # ---------- V1 SVG 可解析 + id 唯一 ----------
    raw = io.open(SHEET, encoding='utf-8').read()
    try:
        root = ET.fromstring(raw.encode('utf-8'))
    except Exception as e:
        rep = {'sheet': os.path.basename(SHEET), 'validation': 'failed',
               'fail_count': 1, 'warn_count': 0, 'visual_review': 'pending',
               'checks': [{'id': 'V1', 'result': 'fail', 'detail': 'SVG 不可解析: %s' % e}],
               'evidence': [{'id': 'V%d' % i, 'coverage_status': 'not_checked',
                             'coverage_detail': 'SVG parse failure prevented this check.'}
                            for i in range(2, 20)]}
        enrich_report(rep, HERE, catalog_path=CATALOG)
        write_report(rep, os.path.join(HERE, 'validation-report.json'))
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 1
    ids = [e.get('id') for e in root.iter() if e.get('id')]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        F.append(('V1', '整图存在重复 id: %s' % ' '.join(dup)))

    geometry = load_geometry(root, L, symbol_path)
    endpoint_findings, endpoint_evidence = check_endpoints(geometry, intent, cat)
    endpoint_findings.extend(check_bodies(geometry, endpoint_evidence['terminals']))
    F.extend((c['id'], c['detail']) for c in endpoint_findings)
    ev.append(endpoint_evidence)

    # ---------- 收集元件占位矩形 ----------
    boxes = {}
    ink_boxes = {}    # 旋转后实际墨迹矩形,仅 V2"穿越本体"使用
    ports = {}
    for inst, nd in L['nodes'].items():
        boxes[inst] = (nd['x'], nd['y'], nd['x'] + nd['w'], nd['y'] + nd['h'])
        # 读端口绝对坐标,用于判定走线是否抵达端口(V2)。
        p = symbol_path(nd['symbol'])
        _mk, vb, ps = read_symbol(p)
        vx, vy, vw, vh = vb
        k = min(nd['w'] / float(vw), nd['h'] / float(vh))
        sw, sh, rot = vw * k, vh * k, int(nd.get('rot', 0)) % 360
        # 墨迹矩形与 render.py 落位一致(comp 补偿后仍占 (x,y) 起始正矩形),
        # rot 90/270 时宽高互换。boxes 是未旋转的声明占位,判"本体"会用错:
        # 走线从旋转符号旁经过时被误判穿越(1# 系统 CDF-001 rot=270 实例)。
        ink_boxes[inst] = ((nd['x'], nd['y'], nd['x'] + sh, nd['y'] + sw)
                           if rot in (90, 270)
                           else (nd['x'], nd['y'], nd['x'] + sw, nd['y'] + sh))
        pabs = {}
        for pid, (px, py, anch, role, med) in ps.items():
            lx, ly = (px - vx) * k, (py - vy) * k
            if rot == 90:
                lx, ly = sh - ly, lx
            elif rot == 180:
                lx, ly = sw - lx, sh - ly
            elif rot == 270:
                lx, ly = ly, sw - lx
            pabs[pid] = (nd['x'] + lx, nd['y'] + ly, anch, role, med)
        ports[inst] = pabs

    # ---------- V2 走线穿越符号本体 ----------
    polys = []
    for m in re.finditer(r'<polyline class="(ln-[a-z_]+)" points="([^"]+)"', raw):
        pts = [tuple(float(v) for v in q.split(',')) for q in m.group(2).split()]
        polys.append((m.group(1), pts))
    # 单条管线自身的短折返同样会留下线头，不能套用 V13 的短共线豁免。
    for cls, pts in polys:
        for a, b, c in zip(pts, pts[1:], pts[2:]):
            horizontal = max(a[1], b[1], c[1]) - min(a[1], b[1], c[1]) < 0.1
            vertical = max(a[0], b[0], c[0]) - min(a[0], b[0], c[0]) < 0.1
            if ((horizontal and (b[0] - a[0]) * (c[0] - b[0]) < -0.01)
                    or (vertical and (b[1] - a[1]) * (c[1] - b[1]) < -0.01)):
                F.append(('V13', '管线自身折返形成越界线头: %s %s -> %s -> %s'
                          % (cls, a, b, c)))
    ev.append({'id': 'V2', 'polylines': len(geometry['pipes']),
               'segments': sum(len(p['points']) - 1 for p in geometry['pipes']),
               'coverage_status': 'not_checked' if geometry['issues'] else 'pass',
               'detail': 'Final SVG segments clipped against transformed symbol footprints',
               'coordinate_system': geometry['coordinate_system'],
               'interior_tolerance': endpoint_evidence['endpoint_tolerance']})

    # 三通点先收集,V14 需要它判断交叉是否为连通节点。
    jn = [(float(m.group(1)), float(m.group(2)))
          for m in re.finditer(
              r'<circle class="jn" cx="([\d.]+)" cy="([\d.]+)"', raw)]

    # ---------- V12 管线与文字重合 ----------
    # 文字包围盒按字号估算:CJK 字宽约等于字号,ASCII 约 0.55 倍。
    texts = []
    for m in re.finditer(
            r'<text class="([a-z\-]+)"[^>]*?x="([\-\d.]+)" y="([\-\d.]+)"'
            r'(?:[^>]*?text-anchor="(\w+)")?[^>]*>([^<]*)</text>', raw):
        cls, tx, ty, anch, txt = (m.group(1), float(m.group(2)), float(m.group(3)),
                                  m.group(4) or 'start', m.group(5))
        if not txt.strip():
            continue
        fs = {'lbl': 11.0, 'ext': 10.0, 'grp-lbl': 10.5,
              'lg-t': 10.5, 'tb-t': 11.0, 'banner': 15.0}.get(cls, 11.0)
        wid = sum(fs if ord(ch) > 0x2E80 else fs * 0.55 for ch in txt)
        x0 = {'start': tx, 'middle': tx - wid / 2, 'end': tx - wid}[anch]
        texts.append((cls, txt, x0, ty - fs * 0.80, x0 + wid, ty + fs * 0.22))
    for cls, txt, x0, y0, x1, y1 in texts:
        for pcls, pts in polys:
            for k in range(len(pts) - 1):
                if seg_rect_hit(pts[k], pts[k + 1], (x0, y0, x1, y1), tol=0) > 3:
                    F.append(('V12', '管线压住文字 "%s"(%s),段 %s->%s'
                              % (txt.strip()[:22], cls, pts[k], pts[k + 1])))
                    break
    ev.append({'id': 'V12', 'texts': len(texts)})

    # ---------- V13 管线与管线共线重叠 ----------
    # 两段平行且同线、区间相交 = 图上看不出是两条管路,读图必然误判。
    # 交叉(垂直相交)是另一回事,由 V14 处理。
    segs_all = []
    for pcls, pts in polys:
        for k in range(len(pts) - 1):
            segs_all.append((pcls, pts[k], pts[k + 1]))
    for i in range(len(segs_all)):
        c1, a1, b1 = segs_all[i]
        h1 = abs(b1[1] - a1[1]) < 0.6
        for j in range(i + 1, len(segs_all)):
            c2, a2, b2 = segs_all[j]
            h2 = abs(b2[1] - a2[1]) < 0.6
            if h1 != h2:
                continue
            if h1:
                if abs(a1[1] - a2[1]) > 1.2:
                    continue
                lo1, hi1 = sorted((a1[0], b1[0]))
                lo2, hi2 = sorted((a2[0], b2[0]))
            else:
                if abs(a1[0] - a2[0]) > 1.2:
                    continue
                lo1, hi1 = sorted((a1[1], b1[1]))
                lo2, hi2 = sorted((a2[1], b2[1]))
            ov = min(hi1, hi2) - max(lo1, lo2)
            if ov <= 6:
                continue
            # 多条管路接入同一端口时必然在该端口附近汇合,这是真实连通,
            # 不是重叠缺陷。判据:重叠区间的两端之一落在某个端口上。
            # 豁免必须同时满足:重叠短(仅端口附近的汇合段)+ 端点确在端口上。
            # 早先只判后者,于是一处 480 单位的母线叠线也被豁免成 WARN——
            # 校核器替缺陷背书,比没有校核更坏。
            shared = False
            if ov <= 25:
                for inst, pabs in ports.items():
                    for pid, (px, py, _a, _r, _m) in pabs.items():
                        for (qx, qy) in (a1, b1, a2, b2):
                            if abs(qx - px) < 3 and abs(qy - py) < 3:
                                shared = True
            if shared:
                W.append(('V13', '共线重叠 %.0f 单位但汇于同一端口,'
                                 '按连通处理: %s->%s' % (ov, a1, b1)))
                continue
            F.append(('V13', '管线共线重叠 %.0f 单位:%s->%s 与 %s->%s'
                      % (ov, a1, b1, a2, b2)))
    ev.append({'id': 'V13', 'segments': len(segs_all)})

    # ---------- V14 非连通交叉须有跨线桥(规范 10.6.2) ----------
    jset = {(round(x, 1), round(y, 1)) for (x, y) in jn}
    cross = []
    for i in range(len(segs_all)):
        c1, a1, b1 = segs_all[i]
        if abs(b1[1] - a1[1]) >= 0.6:
            continue
        y = a1[1]
        x1lo, x1hi = sorted((a1[0], b1[0]))
        for j in range(len(segs_all)):
            c2, a2, b2 = segs_all[j]
            if abs(b2[0] - a2[0]) >= 0.6:
                continue
            x = a2[0]
            y2lo, y2hi = sorted((a2[1], b2[1]))
            if x1lo + 1 < x < x1hi - 1 and y2lo + 1 < y < y2hi - 1:
                if (round(x, 1), round(y, 1)) not in jset:
                    cross.append((x, y))
    # 跨线桥圆弧的圆心即交叉点,自 <path class="brg"> 的起点加半径求得。
    brg = set()
    for m in re.finditer(r'<path class="brg" d="M([\-\d.]+) ([\-\d.]+) '
                         r'A([\d.]+)', raw):
        bx0, by0, r0 = float(m.group(1)), float(m.group(2)), float(m.group(3))
        brg.add((round(bx0 + r0, 1), round(by0, 1)))
    nobridge = [(x, y) for (x, y) in sorted(set(cross))
                if (round(x, 1), round(y, 1)) not in brg]
    for (x, y) in nobridge:
        F.append(('V14', '非连通交叉 (%.0f,%.0f) 无三通点也无跨线桥:'
                         '读图无法判断是否连通' % (x, y)))
    ev.append({'id': 'V14', 'crossings': len(set(cross)),
               'bridged': len(brg), 'unbridged': len(nobridge)})

    baseT = float(L.get('style', {}).get('base_line_width_T', 1.0))
    width_failures, width_evidence = check_widths(SHEET, L, geometry, symbol_path)
    F.extend(width_failures)
    ev.extend(width_evidence)

    # ---------- V17 吸油线 = 连续基线 + 周期性五斜杠组 ----------
    # 用户提供的标准图不是虚线:1.0 T 基线连续,其上周期性画五根斜杠。
    # 曾误读为 stroke-dasharray,渲染成覆盖率 15% 的点线,语义与可读性都错。
    style = re.search(r'<style>(.*?)</style>', raw, re.S)
    srule = re.search(r'\.ln-suction\s*\{([^}]*)\}',
                      style.group(1) if style else '')
    if not srule:
        F.append(('V17', '缺少 .ln-suction 样式'))
    elif 'stroke-dasharray' in srule.group(1):
        F.append(('V17', '吸油基线用了 stroke-dasharray:标准要求连续实线基线'))

    smgroups = [g for g in root.iter() if g.get('class') == 'suc-mark-group']
    smarks = []
    for gi, g in enumerate(smgroups):
        q = [e for e in g if e.tag.endswith('line') and e.get('class') == 'suc-mark']
        if len(q) != 5:
            F.append(('V17', '吸油斜杠组 %d 含 %d 根,标准要求完整 5 根' % (gi, len(q))))
        smarks.extend(q)
    if not smgroups:
        F.append(('V17', '吸油线存在但未生成任何五斜杠组'))

    # 标记不得进入组件或文字。用斜杠包围盒与障碍矩形相交判定。
    # 组件本体按旋转后墨迹盒判(boxes 是未旋转声明占位,rot 符号会误杀
    # 墨迹旁的合法斜杠,与 V2 ink_boxes 同理)。
    mark_hits = []
    for m in smarks:
        x0, x1 = sorted((float(m.get('x1')), float(m.get('x2'))))
        y0, y1 = sorted((float(m.get('y1')), float(m.get('y2'))))
        for inst, bx in ink_boxes.items():
            if not (x1 < bx[0] or x0 > bx[2] or y1 < bx[1] or y0 > bx[3]):
                mark_hits.append('组件 %s' % inst)
        for cls, txt, tx0, ty0, tx1, ty1 in texts:
            if not (x1 < tx0 or x0 > tx1 or y1 < ty0 or y0 > ty1):
                mark_hits.append('文字 %s' % txt.strip()[:16])

        # 流向箭头包围盒。斜杠不得切碎箭头。
        for ar in re.finditer(r'<path class="arw" d="([^"]+)"', raw):
            nums = [float(v) for v in re.findall(r'[-\d.]+', ar.group(1))]
            ab = (min(nums[0::2]) - 2, min(nums[1::2]) - 2,
                  max(nums[0::2]) + 2, max(nums[1::2]) + 2)
            if not (x1 < ab[0] or x0 > ab[2] or y1 < ab[1] or y0 > ab[3]):
                mark_hits.append('流向箭头')

        # 装配框四边,不把框内区域整体视为障碍。
        for gr in root.iter():
            if gr.get('class') != 'grp':
                continue
            gx, gy = float(gr.get('x')), float(gr.get('y'))
            gw, gh = float(gr.get('width')), float(gr.get('height'))
            edges = [(gx - 2, gy - 2, gx + gw + 2, gy + 2),
                     (gx - 2, gy + gh - 2, gx + gw + 2, gy + gh + 2),
                     (gx - 2, gy - 2, gx + 2, gy + gh + 2),
                     (gx + gw - 2, gy - 2, gx + gw + 2, gy + gh + 2)]
            if any(not (x1 < e[0] or x0 > e[2] or y1 < e[1] or y0 > e[3])
                   for e in edges):
                mark_hits.append('装配分组边界')
    for hit in sorted(set(mark_hits)):
        F.append(('V17', '吸油斜杠压住%s' % hit))
    Smark = float(L.get('style', {}).get('suction_marker_S', 8.0))
    if Smark <= 0:
        F.append(('V17', 'style.suction_marker_S 必须 > 0,实际 %g' % Smark))
    geom17 = {
        'slash_height': 2.0 * Smark,
        'slash_angle_deg': 60.0,
        'intra_spacing': 1.25 * Smark,
        'group_pitch': 12.5 * Smark,
        'end_clearance': 4.0 * Smark,
    }
    legend_s = re.findall(r'Suction Lines[^<]*\(S=([\d.]+)\)', raw)
    if len(legend_s) != 1 or abs(float(legend_s[0]) - Smark) > 1e-6:
        F.append(('V17', '图例 S 声明与 layout 不一致:legend=%s layout=%g'
                         % (legend_s or 'missing', Smark)))
    legend = [g for g in root.iter() if g.get('id') == 'legend']
    lgbase = []
    lgmarks = []
    if legend:
        lgbase = [e for e in legend[0].iter() if e.get('class') == 'suc-sample-base']
        lgmarks = [e for e in legend[0].iter() if e.get('class') == 'suc-sample-mark']
    if len(lgbase) != 1 or len(lgmarks) != 5:
        F.append(('V17', '图例吸油样例必须为 1 条连续基线+5 根斜杠,实际 %d+%d'
                         % (len(lgbase), len(lgmarks))))

    # 反算主图实际几何,防止 evidence 写 S 公式而图元仍使用旧硬编码。
    actual = []
    seen_geom = set()
    duplicate = 0
    for gi, group in enumerate(smgroups):
        q = [e for e in group if e.get('class') == 'suc-mark']
        centers = []
        for e in q:
            x1, y1 = float(e.get('x1')), float(e.get('y1'))
            x2, y2 = float(e.get('x2')), float(e.get('y2'))
            key = tuple(round(v, 3) for v in (x1, y1, x2, y2))
            duplicate += key in seen_geom
            seen_geom.add(key)
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            horiz_run = dy >= dx
            height = dy if horiz_run else dx
            angle = math.degrees(math.atan2(dy, dx)) if horiz_run \
                else math.degrees(math.atan2(dx, dy))
            centers.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0, horiz_run))
            actual.append((gi, height, angle))
        if len(centers) == 5:
            axis = sorted(c[0] if c[2] else c[1] for c in centers)
            for d in (axis[i + 1] - axis[i] for i in range(4)):
                if abs(d - geom17['intra_spacing']) > 0.15:
                    F.append(('V17', '斜杠组 %d 组内间距 %.2f != 1.25S %.2f'
                                     % (gi, d, geom17['intra_spacing'])))
    for gi, height, angle in actual:
        if abs(height - geom17['slash_height']) > 0.15:
            F.append(('V17', '斜杠组 %d 高度 %.2f != 2S %.2f'
                             % (gi, height, geom17['slash_height'])))
        if abs(angle - geom17['slash_angle_deg']) > 0.3:
            F.append(('V17', '斜杠组 %d 角度 %.2f != 60°' % (gi, angle)))
    if duplicate:
        F.append(('V17', '吸油斜杠存在 %d 个重复几何,会叠画变粗' % duplicate))
    ev.append({'id': 'V17', 'S': Smark,
               'slash_height': geom17['slash_height'],
               'slash_angle_deg': geom17['slash_angle_deg'],
               'intra_spacing': geom17['intra_spacing'],
               'group_pitch': geom17['group_pitch'],
               'end_clearance': geom17['end_clearance'],
               'groups': len(smgroups), 'slashes': len(smarks),
               'duplicate_slashes': duplicate,
               'legend_sample': [len(lgbase), len(lgmarks)],
               'obstacle_hits': len(mark_hits), 'baseline': 'continuous'})

    # ---------- V18 禁止渲染器叠加管线流向箭头 ----------
    # 仅禁止 renderer-owned .arw / arrows layer。组件符号内部的泵箭头、
    # 单向阀三角形、油箱运动箭头属于受控符号几何,不得删除。
    pipeline_arrows = [e for e in root.iter() if e.get('class') == 'arw']
    arrow_layers = [e for e in root.iter() if e.get('id') == 'arrows']
    if pipeline_arrows or arrow_layers:
        F.append(('V18', '管线方向箭头未取消: arw=%d arrows-layer=%d'
                         % (len(pipeline_arrows), len(arrow_layers))))
    ev.append({'id': 'V18', 'pipeline_arrows': len(pipeline_arrows),
               'arrow_layers': len(arrow_layers)})

    # ---------- V11 管线必须正交 ----------
    # 感知校核(PNG 回读)发现的缺陷:走线器把"直连"当候选,斜线因
    # 长度最短、拐点最少而总是胜出。液压原理图的斜线会被读成软管。
    for cls, pts in polys:
        for k in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
            if abs(x1 - x0) > 0.6 and abs(y1 - y0) > 0.6:
                F.append(('V11', '斜线段 (%.0f,%.0f)->(%.0f,%.0f),管线须正交'
                          % (x0, y0, x1, y1)))

    # ---------- V4 三通实心点必须在母线内部 ----------
    bus_x = {b['x'] for b in L['buses'].values()}
    for (x, y) in jn:
        if round(x, 1) not in {round(v, 1) for v in bus_x}:
            W.append(('V4', '三通点 (%g,%g) 不在任何母线 x 上' % (x, y)))
    ev.append({'id': 'V4', 'junctions': len(jn), 'bus_x': sorted(bus_x)})

    # ---------- V5 悬空端口(不阻止出图,但必须披露) ----------
    dang = inventory['dangling']
    if dang:
        W.append(('V5', '悬空端口 %d 个,须在图签栏计数并标红: %s'
                  % (len(dang), ' '.join(sorted(dang)))))
    drawing_issues = check_disclosure(root, inventory, geometry)
    F.extend(('V5', item['detail']) for item in drawing_issues)
    ev.append({'id': 'V5', **inventory, 'drawing_issues': drawing_issues,
               'marker_tolerance': 0.2, 'coordinate_system': geometry['coordinate_system'],
               'contract_issues': contract_issues, 'unknown': intent.get('unknown') or []})

    # ---------- V6 内容越出画布(含 shift 后) ----------
    xs, ys = [], []
    for _c, pts in polys:
        for (x, y) in pts:
            xs.append(x + SHIFT)
            ys.append(y)
    for inst, (x0, y0, x1, y1) in boxes.items():
        xs += [x0 + SHIFT, x1 + SHIFT]
        ys += [y0, y1]
    if xs:
        if min(xs) < 0 or max(xs) > CW:
            F.append(('V6', '图形 x 范围 %.0f..%.0f 越出画布宽 %d'
                      % (min(xs), max(xs), CW)))
        if min(ys) < 0 or max(ys) > CH:
            F.append(('V6', '图形 y 范围 %.0f..%.0f 越出画布高 %d'
                      % (min(ys), max(ys), CH)))
    # 左侧边界说明文字向左伸出约 110,须在 shift 内
    for eid, e in L.get('externs', {}).items():
        if e['anchor'] == 'right' and e['x'] + SHIFT - 110 < 0:
            W.append(('V6', '%s 的说明文字可能被左缘裁切(x=%g, shift=%g)'
                      % (eid, e['x'], SHIFT)))
    ev.append({'id': 'V6', 'canvas': [CW, CH], 'shift_x': SHIFT,
               'content_x': [round(min(xs), 1), round(max(xs), 1)] if xs else None,
               'content_y': [round(min(ys), 1), round(max(ys), 1)] if ys else None})

    # ---------- V7 图例/图签栏遮挡 ----------
    # 图例与图签栏互相重叠。二者都画在 sheet 组之外(不随 shift 平移),
    # 早先只检查它们与元件、与管线,没检查它们**彼此**——于是图例底部
    # 三行文字压在图签栏上,两层文字叠印,全都不可读。
    lg, tb = L.get('legend'), L.get('title_block')
    if lg and tb:
        a = (lg['x'], lg['y'], lg['x'] + lg['w'], lg['y'] + lg['h'])
        b = (tb['x'], tb['y'], tb['x'] + tb['w'], tb['y'] + tb['h'])
        if not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3]):
            F.append(('V7', '图例 y %g..%g 与图签栏 y %g..%g 重叠,文字叠印'
                      % (a[1], a[3], b[1], b[3])))

    for key in ('legend', 'title_block'):
        r = L.get(key)
        if not r:
            continue
        rect = (r['x'] - SHIFT, r['y'], r['x'] + r['w'] - SHIFT, r['y'] + r['h'])
        for inst, bx in boxes.items():
            if not (bx[2] < rect[0] or bx[0] > rect[2]
                    or bx[3] < rect[1] or bx[1] > rect[3]):
                F.append(('V7', '%s 与元件 %s 重叠' % (key, inst)))
        for _c, pts in polys:
            for k in range(len(pts) - 1):
                if seg_rect_hit(pts[k], pts[k + 1], rect, tol=0) > 8:
                    F.append(('V7', '%s 压住管线,段 %s->%s' % (key, pts[k], pts[k + 1])))
                    break

    # ---------- V8 分组框与标签 ----------
    pad = L.get('group_padding', 14)
    for g in intent.get('groups') or []:
        mem = [m for m in g['members'] if m in boxes]
        if not mem:
            continue
        gx0 = min(boxes[m][0] for m in mem) - pad
        gy0 = min(boxes[m][1] for m in mem) - pad
        gx1 = max(boxes[m][2] for m in mem) + pad
        gy1 = max(boxes[m][3] for m in mem) + pad
        for inst, bx in boxes.items():
            if inst in mem:
                continue
            if not (bx[2] < gx0 or bx[0] > gx1 or bx[3] < gy0 or bx[1] > gy1):
                F.append(('V8', '分组 %s 的虚线框圈进了非成员 %s' % (g['id'], inst)))
    ev.append({'id': 'V8', 'groups': len(intent.get('groups') or [])})

    # ---------- V9 符号就绪度 ----------
    notready = []
    for inst, nd in L['nodes'].items():
        p = symbol_path(nd['symbol'])
        s = io.open(p, encoding='utf-8').read(4000)
        st = re.search(r'data-symbol-status="([^"]+)"', s)
        st = st.group(1) if st else 'none'
        if st != 'annotated':
            notready.append('%s(%s)' % (inst, st))
    if notready:
        W.append(('V9', '非 annotated 符号 %d 个,不可正式出图: %s'
                  % (len(notready), ' '.join(sorted(notready)))))
    ev.append({'id': 'V9', 'not_annotated': sorted(notready)})

    # ---------- V10 Independent visible connectivity and input traceability ----------
    try:
        from browser_evidence import collect
        topology_browser = collect(SHEET)
    except ImportError:
        topology_browser = {'status':'not_checked','reason':'Browser display collector unavailable'}
    topology = reconcile_topology(root, geometry, intent, cat, L, topology_browser)
    topology_findings = topology['findings']
    F.extend((c['id'], c['detail']) for c in topology_findings)
    ev.append({'id': 'V10', 'coverage_status': topology['coverage_status'],
               'coverage_detail': ('Input edges reconciled against browser-visible SVG geometry and catalog ports'
                                   if topology['coverage_status'] == 'pass' else
                                   'Display/geometry reconciliation incomplete: ' + str(topology.get('display_evidence'))),
               'expected_edges': len(topology['expected_edges']),
               'actual_edges': len(topology['actual_edges']),
               'endpoint_tolerance': 0.1})

    # ---------- 构图预算面板（B1–B7，V19）----------
    # 折返数：方向变化次数，U 形回折(180°)也算一次（与
    # prototype-precheck/calibrate_profile.py 同一口径）。
    def turns_of(pts):
        dirs = []
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if abs(x1 - x0) >= abs(y1 - y0):
                dirs.append('H' if x1 >= x0 else 'h')
            else:
                dirs.append('V' if y1 >= y0 else 'v')
        return sum(1 for i in range(1, len(dirs))
                   if dirs[i] != dirs[i - 1] or dirs[i][0] != dirs[i - 1][0])

    def near_terminal(p):
        return any(abs(p[0] - t[0]) < 3 and abs(p[1] - t[1]) < 3
                   for t in BOUNDARY_TERMINALS)

    turn_total = 0
    turn_max = 0
    ratios = []
    for _c, pts in polys:
        turn_total += turns_of(pts)
        turn_max = max(turn_max, turns_of(pts))
        man = abs(pts[-1][0] - pts[0][0]) + abs(pts[-1][1] - pts[0][1])
        length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1])
                     for a, b in zip(pts, pts[1:]))
        if man > 0:
            ratios.append((length / man, pts))

    # B1 交叉：正交段几何交点，端点相接（T 型汇入/三通）不算。
    # 预算恒为 0，不承认跨线桥豁免——有桥也是超预算，须改道。
    b1_cross = []
    for i in range(len(segs_all)):
        _c1, a1, b1 = segs_all[i]
        h1 = abs(b1[1] - a1[1]) < 0.6
        for j in range(i + 1, len(segs_all)):
            _c2, a2, b2 = segs_all[j]
            h2 = abs(b2[1] - a2[1]) < 0.6
            if h1 == h2:
                continue
            if h1:
                x, y = a2[0], a1[1]
            else:
                x, y = a1[0], a2[1]
            def on(p, s, e):
                return (min(s[0], e[0]) - 0.5 <= x <= max(s[0], e[0]) + 0.5
                        and min(s[1], e[1]) - 0.5 <= y <= max(s[1], e[1]) + 0.5)
            if not (on((x, y), a1, b1) and on((x, y), a2, b2)):
                continue
            ends = {(round(q[0], 1), round(q[1], 1))
                    for q in (segs_all[i][1], segs_all[i][2],
                              segs_all[j][1], segs_all[j][2])}
            if (round(x, 1), round(y, 1)) in ends:
                continue
            b1_cross.append((x, y))

    # B5 uses the final transformed source footprints, including nested transforms.
    b5_nearest = nearest_components(geometry)
    b5_gap = b5_nearest['distance'] if b5_nearest else None

    items = []
    def add(bid, measured, status, detail=None):
        it = {'id': bid, 'metric': BUDGET[bid]['metric'],
              'measured': measured, 'status': status}
        if detail:
            it['detail'] = detail
        items.append(it)
        return it

    # B1 交叉恒 0，硬 fail（唯一走 fail 通道的预算项）。
    if b1_cross:
        add('B1', len(set(b1_cross)), 'fail',
            '非连通交叉 %d 处，预算恒为 0（含跨线桥也不豁免）' % len(set(b1_cross)))
        F.append(('V19', '构图预算 B1：交叉 %d 处 > 0，须改道消除'
                  % len(set(b1_cross))))
    else:
        add('B1', 0, 'pass')

    # B2 折返：单条 ≤3 且全图 ≤40。超限走 WARN；落在边界端子上的
    # 存量走线按表注¹披露为 exempt。
    over_turn = [n for n in range(len(polys)) if turns_of(polys[n][1]) > 3]
    if turn_max > 3 or turn_total > 40:
        if over_turn and all(near_terminal(polys[n][1][0])
                             or near_terminal(polys[n][1][-1])
                             for n in over_turn):
            add('B2', {'total': turn_total, 'max_single': turn_max},
                'exempt', LEGACY_DISCLOSURE)
            W.append(('V19', '构图预算 B2：单条折返 %d > 3——%s'
                      % (turn_max, LEGACY_DISCLOSURE)))
        else:
            add('B2', {'total': turn_total, 'max_single': turn_max}, 'over')
            W.append(('V19', '构图预算 B2：折返单条 %d > 3 / 全图 %d > 40，超限'
                      % (turn_max, turn_total)))
    else:
        add('B2', {'total': turn_total, 'max_single': turn_max}, 'pass')

    # B3 绕行比：一般 ≤1.5；边界端子走廊 ≤4 且须披露。超限 WARN。
    b3_over = [(r, pts) for r, pts in ratios
               if r > BUDGET['B3']['budget']]
    b3_status, b3_detail = 'pass', None
    for r, pts in b3_over:
        on_edge = (near_terminal(pts[0]) or near_terminal(pts[-1]))
        if r <= BUDGET['B3']['budget_boundary'] and on_edge:
            if b3_status != 'fail':
                b3_status = 'exempt'
            b3_detail = ('超限走线均经边界走廊进出边界端子，绕行比 %s ≤4——%s'
                         % ('/'.join('%.3f' % x for x, _ in b3_over),
                            LEGACY_DISCLOSURE))
        else:
            b3_status = 'over'
            W.append(('V19', '构图预算 B3：绕行比 %.3f > 1.5 且非边界走廊，超限' % r))
    if b3_status == 'exempt':
        W.append(('V19', '构图预算 B3：绕行比 %s > 1.5，边界端子走廊按披露豁免'
                  % ('/'.join('%.3f' % x for x, _ in b3_over))))
    add('B3', {'max': round(max(r for r, _ in ratios), 3) if ratios else 0.0,
               'over_budget': ['%.3f' % r for r, _ in b3_over]},
        b3_status, b3_detail)

    # B4 measures actual turns/interfaces, not arbitrary SVG storage cuts.
    budget_runs = measure_runs(geometry, topology)
    nearest_run = min(budget_runs,key=lambda r:r['length']) if budget_runs else None
    min_seg = nearest_run['length'] if nearest_run else None
    b4_over = min_seg is not None and min_seg < BUDGET['B4']['budget']
    b4_status = ('not_measured' if topology['coverage_status']=='not_checked' else
                 'over' if b4_over else 'pass' if nearest_run else 'not_applicable')
    b4_item = add('B4', round(min_seg,1) if min_seg is not None else None,b4_status)
    if b4_status=='not_measured':
        b4_item['detail'] = 'Visible topology is incomplete; available runs are partial measurements.'
    b4_item['runs'] = budget_runs
    b4_item['nearest_run'] = nearest_run
    if b4_over:
        W.append(('V19','构图预算 B4：%s 最短走线段 %.1f < 8，差额 %.1f，位置 %s → %s'
                  % (nearest_run['anchor'],min_seg,8-min_seg,nearest_run['start'],nearest_run['end'])))

    # B5 节点盒净距 ≥40px。
    if b5_gap is not None and b5_gap < BUDGET['B5']['budget']:
        add('B5', round(b5_gap, 1), 'over')
        W.append(('V19', '构图预算 B5：%s 最小净距 %.1f < 40，差额 %.1f，位置 %s'
                  % (' ↔ '.join(b5_nearest['components']), b5_gap,40-b5_gap,b5_nearest['positions'])))
    else:
        add('B5', round(b5_gap, 1) if b5_gap is not None else None, 'pass')

    if geometry['issues'] or topology.get('display_evidence',{}).get('unchecked'):
        items[-1]['status'] = 'not_measured'
        items[-1]['detail'] = 'Some final component footprints could not be measured; see geometry/display issues.'
    if b5_nearest:
        items[-1]['nearest'] = dict(b5_nearest, deficit=max(0.0,BUDGET['B5']['budget']-b5_gap))

    # B6 pipe-to-footprint clearance; only an actual outward terminal run
    # may occupy its own component's approach corridor.
    corridors = measure_corridors(geometry, topology, budget_runs, BUDGET['B6']['budget_avoid_corridor'], topology_browser)
    corridor_gap = corridors['nearest']['distance'] if corridors['nearest'] else None
    group_measurement = measure_groups(geometry, intent, topology_browser, BUDGET['B6']['budget_group_padding'])
    gp = group_measurement['nearest']['distance'] if group_measurement['nearest'] else None
    b6_over = ((gp is not None and gp < BUDGET['B6']['budget_group_padding'])
               or (corridor_gap is not None and corridor_gap < BUDGET['B6']['budget_avoid_corridor']))
    b6_status = ('over' if b6_over else 'not_measured' if 'not_checked' in (group_measurement['status'],corridors['coverage_status']) else 'pass')
    b6_item = add('B6', {'group_padding':gp,'avoid_corridor':corridor_gap},b6_status)
    b6_item['nearest_group'] = group_measurement['nearest']
    b6_item['group_padding_status'] = group_measurement['status']
    b6_item['groups'] = group_measurement
    b6_item['nearest_corridor'] = corridors['nearest']
    b6_item['corridors'] = corridors
    if gp is not None and gp < BUDGET['B6']['budget_group_padding']:
        W.append(('V19','构图预算 B6：分组 %s 到 %s 内边距 %g < 14，差额 %g，位置 %s'
                  % (group_measurement['nearest']['group'],group_measurement['nearest']['component'],gp,14-gp,group_measurement['nearest']['positions'])))
    if corridors['violations']:
        nearest = corridors['nearest']
        W.append(('V19','构图预算 B6：%s 绕过 %s 的净距 %.1f < 12，差额 %.1f，位置 %s'
                  % (nearest['anchor'],nearest['component'],nearest['distance'],nearest['deficit'],nearest['positions'])))
    ev.append({'id':'B6.avoid_corridor','coverage_status':corridors['coverage_status'],
               'coverage_detail':('Measured straight runs and visible semicircular bridges against transformed component footprints; only own outward terminal runs exempt.'
                                  if corridors['coverage_status']!='not_checked' else
                                  'Clearance measurement incomplete; see geometry/topology issues and unchecked objects.'),
               'budget':BUDGET['B6']['budget_avoid_corridor'],**corridors})
    ev.append({'id': 'V19', 'crossings': len(set(b1_cross)),
               'turns_total': turn_total, 'turns_max_single': turn_max,
               'detour_max': round(max(r for r, _ in ratios), 3) if ratios else None,
               'min_segment': round(min_seg, 1) if min_seg is not None else None, 'box_gap_min': b5_gap})

    ev.append({'id': 'composition_budget', 'source':
               'rendering-rules.md 数值构图预算（concept 档 v1）',
               'items': {it['id']: it['status'] for it in items},
               'not_measured': (['B6.avoid_corridor'] if corridors['coverage_status']=='not_checked' else []) + ['B7'],
               'note': 'B7 标签净空 6px 未自动测量（需文本包围盒近似），'
                       'V12 已覆盖压字重叠（0 净空）情形；B6 避让走廊同批裁剪。'})

    # ---------- 报告 ----------
    checks = ([{'id': i, 'result': 'fail', 'detail': d} for i, d in F]
              + [{'id': i, 'result': 'warn', 'detail': d} for i, d in W])
    for finding in endpoint_findings + topology_findings:
        next(c for c in checks if c['id'] == finding['id'] and c['detail'] == finding['detail'] and 'kind' not in c).update(finding)
    rep = {
        'geometry': geometry,
        'topology': topology,
        'sheet': os.path.basename(SHEET),
        'validation': 'failed' if F else 'passed',
        'visual_review': 'pending',
        'fail_count': len(F),
        'warn_count': len(W),
        'checks': checks,
        'evidence': ev,
        'composition_budget': {
            'source': 'rendering-rules.md 数值构图预算（concept 档 v1）',
            'items': items,
            'not_measured': (['B6.avoid_corridor（部分几何未测）'] if corridors['coverage_status']=='not_checked' else []) + ['B7（标签净空 ≥6）'],
            'note': 'B4/B5/B6 使用本轮归一化走线与足迹；B7 标签净空未测，V12 已覆盖压字重叠'
                    '（0 净空）情形。除 B1 交叉硬 fail 外，超限走 V19 WARN。',
        },
    }
    enrich_report(rep, HERE, catalog_path=CATALOG)
    out = os.path.join(HERE, 'validation-report.json')
    write_report(rep, out)

    print('validation: %s   (fail %d, warn %d)' % (rep['validation'], len(F), len(W)))
    for i, d in F:
        print('  FAIL %s  %s' % (i, d))
    for i, d in W:
        print('  WARN %s  %s' % (i, d))
    print('report ->', out)
    print('构图预算面板（rendering-rules.md concept 档 v1）:')
    mark = {'pass': 'pass ', 'fail': 'FAIL ', 'exempt': 'exempt',
            'not_measured': 'n/a  '}
    for it in items:
        print('  %s %-28s 实测=%-24s 预算=%s'
              % (mark.get(it['status'], '?     '), it['id'] + ' ' + it['metric'],
                 json.dumps(it['measured'], ensure_ascii=False),
                 json.dumps({k: v for k, v in BUDGET[it['id']].items()
                             if k.startswith('budget')}, ensure_ascii=False)))
    print('  未测:', ', '.join(rep['composition_budget']['not_measured']))
    return 1 if F else 0


if __name__ == '__main__':
    sys.exit(main())
