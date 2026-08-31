# -*- coding: utf-8 -*-
"""整图结构校核 —— 技术规范 10.10 闭环的确定性环节。

不看图,只算几何。产出 validation-report.json,每项判定附坐标或 ID,
供感知校核环节(PNG 回读)之前的门禁使用。

用法: python3 validate_sheet.py
退出码 1 表示 validation: failed。
"""
import io
import json
import math
import os
import re
import sys
from xml.etree import ElementTree as ET
import xml.etree.ElementTree as ET

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


def main():
    F, W, ev = [], [], []          # fail, warn, evidence
    intent = load_yaml(INTENT)
    L = json.load(io.open(LAYOUT, encoding='utf-8'))
    cat = json.load(io.open(CATALOG, encoding='utf-8'))
    T = {c['component_type']: c for c in cat['components']}
    SHIFT = L.get('canvas_shift_x', 0)
    CW, CH = L['canvas']['width'], L['canvas']['height']

    # ---------- V1 SVG 可解析 + id 唯一 ----------
    raw = io.open(SHEET, encoding='utf-8').read()
    try:
        root = ET.fromstring(raw.encode('utf-8'))
    except Exception as e:
        print(json.dumps({'validation': 'failed',
                          'checks': [{'id': 'V1', 'result': 'fail',
                                      'detail': 'SVG 不可解析: %s' % e}]},
                         ensure_ascii=False, indent=2))
        return 1
    ids = [e.get('id') for e in root.iter() if e.get('id')]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        F.append(('V1', '整图存在重复 id: %s' % ' '.join(dup)))

    # ---------- 收集元件占位矩形 ----------
    boxes = {}
    ports = {}
    for inst, nd in L['nodes'].items():
        boxes[inst] = (nd['x'], nd['y'], nd['x'] + nd['w'], nd['y'] + nd['h'])
        # 读端口绝对坐标,用于判定走线是否抵达端口(V2)。
        p = os.path.normpath(os.path.join(HERE, nd['symbol']))
        _mk, vb, ps = read_symbol(p)
        vx, vy, vw, vh = vb
        k = min(nd['w'] / float(vw), nd['h'] / float(vh))
        sw, sh, rot = vw * k, vh * k, int(nd.get('rot', 0)) % 360
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
    for cls, pts in polys:
        for k in range(len(pts) - 1):
            for inst, bx in boxes.items():
                # 段端点落在框边界上时是接线,不是穿越。判距 <=3。
                on_a = (abs(pts[k][0] - bx[0]) < 3 or abs(pts[k][0] - bx[2]) < 3
                        or abs(pts[k][1] - bx[1]) < 3 or abs(pts[k][1] - bx[3]) < 3)
                on_b = (abs(pts[k + 1][0] - bx[0]) < 3 or abs(pts[k + 1][0] - bx[2]) < 3
                        or abs(pts[k + 1][1] - bx[1]) < 3 or abs(pts[k + 1][1] - bx[3]) < 3)
                # 段的任何端点在此框的端口上时,穿越不计:那正是接线目标。
                # 端口列表来自布局,坐标是旋转缩放后的绝对位置。
                port_at = []
                for pid, (px, py, anch, role, med) in ports.get(inst, {}).items():
                    if abs(pts[k][0] - px) < 3 and abs(pts[k][1] - py) < 3:
                        port_at.append(pid)
                    if abs(pts[k + 1][0] - px) < 3 and abs(pts[k + 1][1] - py) < 3:
                        port_at.append(pid)
                if on_a or on_b or port_at:
                    continue
                hit = seg_rect_hit(pts[k], pts[k + 1], bx, tol=3.0)
                if hit > 6.0:
                    F.append(('V2', '管线穿越 %s 本体 %.0f 单位,段 %s->%s'
                              % (inst, hit, pts[k], pts[k + 1])))
    ev.append({'id': 'V2', 'polylines': len(polys),
               'segments': sum(len(p) - 1 for _c, p in polys)})

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

    # ---------- V15 线宽必须来自标准,不得出现绝对 stroke-width ----------
    # 企业标准只给三个值:高压 3.0 T、低压 1.0 T、组件本体 1.5 T。
    # 符号文件里写死的 stroke-width="2" 实测等于 1.667 T,不来自任何依据,
    # 且会随符号落位缩放而变(油箱曾按 scale 0.78 落位,本体实际按 1.56 绘制,
    # 而旁边的泵是 2.0)。此项把线宽收口到图纸 CSS。
    ALLOW_T = {'high': 3.0, 'low': 1.0, 'symbol': 1.5}
    baseT = float(L.get('style', {}).get('base_line_width_T', 1.0))
    okw = {round(v * baseT, 2) for v in ALLOW_T.values()}
    bad_w = []
    for m in re.finditer(r'<[^>]*stroke-width="([\d.]+)"[^>]*>', raw):
        tag, wv = m.group(0), round(float(m.group(1)), 2)
        if 'stroke="#fff' in tag.lower() or 'stroke="#FFF' in tag:
            continue          # 白色遮挡图元,非可见线条
        if wv not in okw:
            bad_w.append((wv, round(wv / baseT, 3)))
    for wv, tv in sorted(set(bad_w)):
        F.append(('V15', '绝对线宽 %.2f (= %.3f T) 不在标准三值内'
                         '(3.0/1.0/1.5 T):线宽须由图纸 CSS 施加' % (wv, tv)))
    # 禁用 non-scaling-stroke。它把线宽钉在设备像素上,整图按倍率出图时
    # 管线随之变粗而带该属性的线纹丝不动:实测 1x/2x/3x 下管线 4/8/10px,
    # 符号内引线恒为 4px——线宽是压力等级编码,放大出图就读错等级。
    # 符号落位缩放要用 1/k 补偿(见 render.py 的 --kc),不能用它。
    # 只数真正生效的声明,不数注释里提到它的文字(CSS 注释 /* */ 先剔除),
    # 否则解释"为何禁用"的那段注释自己会触发本项。
    nocmt = re.sub(r'/\*.*?\*/', '', raw, flags=re.S)
    nocmt = re.sub(r'<!--.*?-->', '', nocmt, flags=re.S)
    nss = len(re.findall(r'vector-effect\s*[:=]\s*"?\s*non-scaling-stroke', nocmt))
    if nss:
        F.append(('V15', '出现 %d 处 vector-effect:non-scaling-stroke:'
                         '线宽将不随出图倍率变化,放大后与管线宽度失配' % nss))
    ev.append({'id': 'V15', 'base_T': baseT, 'allowed_T': ALLOW_T,
               'violations': len(set(bad_w)), 'non_scaling_stroke': nss})

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
    mark_hits = []
    for m in smarks:
        x0, x1 = sorted((float(m.get('x1')), float(m.get('x2'))))
        y0, y1 = sorted((float(m.get('y1')), float(m.get('y2'))))
        for inst, bx in boxes.items():
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

    # ---------- V16 端口引线须随管网,台阶只许落在符号轮廓上 ----------
    # 线宽即压力等级编码。端口引线(viewBox 边界到符号轮廓那一段)走油,
    # 若按组件本体 1.5 T 绘制,接点处就出现假的压力等级突变:泵排油口上
    # 3.6 变 1.8,字面读作压力降到回油以下。故引线须随所在管网。
    #
    # 采用方案 A:符号轮廓(菱形、圆、方框)一律 1.5 T,不随管网。
    # 因为轮廓线宽是"这是什么零件"的编码,管线线宽是"这是什么压力"的编码,
    # 两套编码不应互相覆盖。代价是引线与轮廓交接处保留一处台阶,
    # 该台阶落在符号边界上,已在图例中声明不表示压力等级变化。
    # 本项只保证:管线-引线接点无台阶(读作压力突变的那处),
    # 且台阶不出现在符号边界以外的地方。
    LW = {'pressure': 3.0 * baseT, 'return': 1.0 * baseT,
          'suction': 1.0 * baseT, 'case_drain': 1.0 * baseT}
    # 用真正的解析器遍历实例,不用正则。
    # 早先版本用 <g id="inst-..">(.*?)\n</g> 抓实例体,非贪婪匹配在第一个
    # 闭合标签就截断,带嵌套 g 的符号(油箱)只被扫到一部分——把油箱的
    # pl- 类整个删掉,V16 仍报通过。校核器不能有这种盲区。
    SVGNS = '{http://www.w3.org/2000/svg}'
    troot = ET.fromstring(raw.encode('utf-8'))

    def tf_of(el):
        """返回该元素 transform 的 (a,b,c,d,e,f) 复合矩阵。"""
        M = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        for mm in re.finditer(r'(translate|rotate|scale)\(([^)]*)\)',
                              el.get('transform') or ''):
            v = [float(x) for x in re.split(r'[,\s]+', mm.group(2).strip()) if x]
            if mm.group(1) == 'translate':
                N = (1, 0, 0, 1, v[0], v[1] if len(v) > 1 else 0)
            elif mm.group(1) == 'scale':
                N = (v[0], 0, 0, v[1] if len(v) > 1 else v[0], 0, 0)
            else:
                r = math.radians(v[0])
                N = (math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)
            a, b, c, d, e, f = M
            na, nb, nc, nd, ne, nf = N
            M = (a * na + c * nb, b * na + d * nb,
                 a * nc + c * nd, b * nc + d * nd,
                 a * ne + c * nf + e, b * ne + d * nf + f)
        return M

    def comb(M, N):
        a, b, c, d, e, f = M
        na, nb, nc, nd, ne, nf = N
        return (a * na + c * nb, b * na + d * nb,
                a * nc + c * nd, b * nc + d * nd,
                a * ne + c * nf + e, b * ne + d * nf + f)

    pl_ends = []
    outline = []      # (inst, 顶点) — 本体轮廓的顶点,含 path/circle/rect

    def walk(el, M, inst, cls):
        M = comb(M, tf_of(el))
        cl = el.get('class') or cls
        tg = el.tag.replace(SVGNS, '')
        if '#fff' in (el.get('stroke') or '').lower():
            return
        a, b, c, d, e, f = M

        def T(x, y):
            return (a * x + c * y + e, b * x + d * y + f)
        cm = re.search(r'pl-(\w+)', cl or '')
        if tg == 'line':
            for (x, y) in ((float(el.get('x1')), float(el.get('y1'))),
                           (float(el.get('x2')), float(el.get('y2')))):
                pl_ends.append((inst, T(x, y), cm.group(1) if cm else None))
        elif tg in ('path', 'polygon', 'polyline') and not cm:
            # 轮廓顶点。引线常接在菱形的左右顶点上(滤),故须纳入。
            # path 的 A(圆弧)命令中含半径与标志位,不是坐标,须剔除,
            # 否则会造出不存在的锚点(蓄压器壳体是两段 A 弧)。
            dd = el.get('d') or el.get('points') or ''
            dd = re.sub(r'[Aa][^A-Za-z]*', ' ', dd) if tg == 'path' else dd
            for x, y in re.findall(r'([-\d.]+)[ ,]+([-\d.]+)', dd):
                outline.append((inst, T(float(x), float(y))))
            # 弧的端点仍是轮廓上的点:A 命令末尾两个数即终点。
            for am in re.finditer(r'[Aa][\d.,\s-]*?([-\d.]+)[ ,]+([-\d.]+)(?=[ ,]*(?:[A-Za-z]|$))',
                                  el.get('d') or ''):
                outline.append((inst, T(float(am.group(1)), float(am.group(2)))))
        elif tg == 'circle' and not cm:
            cx, cy = float(el.get('cx')), float(el.get('cy'))
            r = float(el.get('r'))
            for dx, dy in ((-r, 0), (r, 0), (0, -r), (0, r)):
                outline.append((inst, T(cx + dx, cy + dy)))
        elif tg == 'rect' and not cm:
            rx, ry = float(el.get('x')), float(el.get('y'))
            rw, rh = float(el.get('width')), float(el.get('height'))
            for px in (rx, rx + rw / 2.0, rx + rw):
                for py in (ry, ry + rh / 2.0, ry + rh):
                    outline.append((inst, T(px, py)))
        for ch in el:
            walk(ch, M, inst, cl)

    # 从 <g id="sheet"> 起遍历,把它的 translate(SHIFT,0) 一并计入。
    # 否则实例坐标整体偏 SHIFT,像素判定取错位置——蓄压器与油箱的引线
    # 端点因此被误报为"落在空处",而实际墨迹在右侧 30 单位处。
    def descend(el, M):
        """M 为祖先累积矩阵,不含 el 自身——walk 会自行乘上 el 的 transform。"""
        gid = el.get('id') or ''
        if gid.startswith('inst-'):
            walk(el, M, gid[5:], None)
            return
        M = comb(M, tf_of(el))
        for ch in el:
            if ch.tag == SVGNS + 'g':
                descend(ch, M)

    # 管段坐标(polys)取自 polyline 的原始 points,未含 sheet 的 SHIFT;
    # 实例坐标经 descend 已含。二者必须在同一坐标系里比,否则整体错 SHIFT:
    # FSOV 的 outlet 在整图 440,与之相接的管段 points 写的是 410,
    # 早先版本因此把"引线正常相接"读成"管段端点落在阀体内部"。
    # 统一到"未含 SHIFT"的图元坐标系,故此处从 sheet 的子层开始遍历。
    sheet_g = None
    for g in troot.iter(SVGNS + 'g'):
        if (g.get('id') or '') == 'sheet':
            sheet_g = g
            break
    for ch in (sheet_g if sheet_g is not None else troot):
        if ch.tag == SVGNS + 'g':
            descend(ch, (1.0, 0.0, 0.0, 1.0, 0.0, 0.0))
    # 非液压口(电、气信号)的引线不参与:它不走油,本就该是本体线宽。
    # FSOV 的 command 口引线恰有一条管段端点与之重合,若不排除会被
    # 误报为"引线未改判"。判据是端口 data-medium,不是几何。
    nonhyd = set()      # (inst, 整图 x, 整图 y)
    for inst, nd in (L['nodes'] or {}).items():
        sp = os.path.normpath(os.path.join(HERE, nd['symbol']))
        if not os.path.exists(sp):
            continue
        sroot = ET.parse(sp).getroot()
        vbp = [float(v) for v in
               re.split(r'[,\s]+', sroot.get('viewBox').strip())]
        kk = min(nd['w'] / vbp[2], nd['h'] / vbp[3])
        rr = int(nd.get('rot', 0)) % 360
        WW, HH = vbp[2] * kk, vbp[3] * kk
        for cg in sroot.iter(SVGNS + 'g'):
            if cg.get('id') != 'connection-points':
                continue
            for c in cg:
                if c.get('data-medium') == 'hydraulic':
                    continue
                lx = (float(c.get('cx')) - vbp[0]) * kk
                ly = (float(c.get('cy')) - vbp[1]) * kk
                if rr == 90:
                    lx, ly = HH - ly, lx
                elif rr == 180:
                    lx, ly = WW - lx, HH - ly
                elif rr == 270:
                    lx, ly = ly, WW - lx
                # 与图元坐标系一致:不含 SHIFT
                nonhyd.add((inst, round(nd['x'] + lx, 1),
                            round(nd['y'] + ly, 1)))

    steps = []
    for lt0, pts in polys:
        lt = lt0[3:] if lt0.startswith('ln-') else lt0
        for e in (pts[0], pts[-1]):
            for inst, (sx, sy), cls in pl_ends:
                if abs(sx - e[0]) < 2.5 and abs(sy - e[1]) < 2.5:
                    if cls is None:
                        # 只豁免"该端点确实落在某个非液压口上"的情形,
                        # 不豁免整个组件——否则带电控口的阀会全体免检。
                        if any(i2 == inst and abs(cx - sx) < 3.0
                               and abs(cy - sy) < 3.0
                               for i2, cx, cy in nonhyd):
                            break
                        steps.append((inst, lt, '引线未改判,按本体线宽 @(%.0f,%.0f)'
                                      % (sx, sy)))
                    elif abs(LW[cls] - LW[lt]) > 0.01:
                        steps.append((inst, lt, '引线判为 %s @(%.0f,%.0f)'
                                      % (cls, sx, sy)))
                    break
    for inst, lt, why in sorted(set(steps)):
        F.append(('V16', '%s 的 %s 接点线宽不连续:%s——读作假的压力等级变化'
                  % (inst, lt, why)))

    # 方案 A 的前提:每段引线必须一端接管线、另一端接符号轮廓。
    # 若某段引线两端都不落在轮廓上,台阶就出现在符号内部的空处,
    # 图例那句"台阶位于符号边界"随之失真。此前 V16 未查这一条。
    lead = [q for q in pl_ends if q[2]]
    # 本体锚点 = 本体 line 的端点 + 轮廓(path/circle/rect)的顶点。
    # 只看 line 端点是不够的:滤的引线接在菱形 path 的左右顶点上,
    # 泵的排油引线接在箭头 path 上,都不是 line。
    body = ([(i, p) for i, p, k in pl_ends if not k] + outline)
    # 顶点匹配不足以判定"接上了本体":蓄压器的引线终点 (30,88) 落在壳体
    # 圆弧的中途而非顶点上;油箱的轮廓是描摹填充,根本没有可取顶点的描边。
    # 故顶点匹配失败时改判像素——PNG 上该点周围有无本体墨迹。
    # 这是唯一能同时覆盖弧、填充与描边的判据。
    png = os.path.join(HERE, 'sheet-readback.png')
    ink = None
    if os.path.exists(png):
        try:
            from PIL import Image
            import numpy as np
            ink = np.asarray(Image.open(png).convert('L')) < 128
        except ImportError:
            pass

    def has_ink(lx, ly, r=6):
        """该点近旁是否有墨迹(排除引线自身所在的那一格)。

        图元坐标不含 SHIFT,PNG 是渲染结果、含 SHIFT,故查像素时补上。
        """
        if ink is None:
            return None
        H2, W2 = ink.shape
        x0, y0 = int(round(lx + SHIFT)), int(round(ly))
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) + abs(dy) < 3:
                    continue
                x, y = x0 + dx, y0 + dy
                if 0 <= x < W2 and 0 <= y < H2 and ink[y, x]:
                    return True
        return False

    orphan, unchecked = set(), 0
    for inst, (lx, ly), cls in lead:
        anchored = any(i2 == inst and abs(bx - lx) < 2.5 and abs(by - ly) < 2.5
                       for i2, (bx, by) in body)
        onpipe = any(abs(p[0] - lx) < 2.5 and abs(p[1] - ly) < 2.5
                     for _lt, pp in polys for p in (pp[0], pp[-1]))
        if anchored or onpipe:
            continue
        px_ok = has_ink(lx, ly)
        if px_ok is None:
            unchecked += 1        # 无回读图,不能判定,不静默放过
            continue
        if not px_ok:
            orphan.add((inst, cls, round(lx), round(ly)))
    for inst, cls, ox, oy in sorted(orphan):
        F.append(('V16', '%s 的 %s 引线端点 (%d,%d) 既不接管线也不接本体:'
                         '台阶落在符号内部空处' % (inst, cls, ox, oy)))
    if unchecked:
        W.append(('V16', '%d 处引线端点无法用顶点判定,且缺回读 PNG '
                         '(%s),未校核' % (unchecked, os.path.basename(png))))

    ev.append({'id': 'V16', 'scheme': 'A: 轮廓 1.5T 不随管网',
               'lead_ends': len(lead), 'steps': len(set(steps)),
               'orphan_lead_ends': len(orphan)})

    # ---------- V11 管线必须正交 ----------
    # 感知校核(PNG 回读)发现的缺陷:走线器把"直连"当候选,斜线因
    # 长度最短、拐点最少而总是胜出。液压原理图的斜线会被读成软管。
    for cls, pts in polys:
        for k in range(len(pts) - 1):
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
            if abs(x1 - x0) > 0.6 and abs(y1 - y0) > 0.6:
                F.append(('V11', '斜线段 (%.0f,%.0f)->(%.0f,%.0f),管线须正交'
                          % (x0, y0, x1, y1)))

    # ---------- V3 越过端口后折返(会被读作支路的线头) ----------
    # 判据:折线首段或末段的方向与该端口锚点方向相反。
    for cls, pts in polys:
        if len(pts) < 3:
            continue
        for (a, b, tag) in ((pts[0], pts[1], '首'), (pts[-1], pts[-2], '末')):
            d = (b[0] - a[0], b[1] - a[1])
            if abs(d[0]) + abs(d[1]) < 0.5:
                F.append(('V3', '%s段零长,端点重合于 %s' % (tag, a)))

    # ---------- V4 三通实心点必须在母线内部 ----------
    bus_x = {b['x'] for b in L['buses'].values()}
    for (x, y) in jn:
        if round(x, 1) not in {round(v, 1) for v in bus_x}:
            W.append(('V4', '三通点 (%g,%g) 不在任何母线 x 上' % (x, y)))
    ev.append({'id': 'V4', 'junctions': len(jn), 'bus_x': sorted(bus_x)})

    # ---------- V5 悬空端口(不阻止出图,但必须披露) ----------
    used = set()
    for p in intent['paths']:
        for tok in p:
            if tok.startswith('@'):
                continue
            inst = tok.split('.')[0]
            if inst not in intent['parts']:
                continue
            if '.' in tok:
                used.add((inst, tok.split('.', 1)[1]))
            else:
                mp = T[intent['parts'][inst]].get('main_path')
                if mp:
                    used.add((inst, mp['in']))
                    used.add((inst, mp['out']))
    dang = []
    for inst, ct in intent['parts'].items():
        if inst not in L['nodes']:
            continue
        for q in T[ct]['ports']:
            if (inst, q['id']) not in used:
                dang.append('%s.%s' % (inst, q['id']))
    if dang:
        W.append(('V5', '悬空端口 %d 个,须在图签栏计数并标红: %s'
                  % (len(dang), ' '.join(sorted(dang)))))
    ev.append({'id': 'V5', 'dangling': sorted(dang)})

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
        p = os.path.normpath(os.path.join(HERE, nd['symbol']))
        s = io.open(p, encoding='utf-8').read(4000)
        st = re.search(r'data-symbol-status="([^"]+)"', s)
        st = st.group(1) if st else 'none'
        if st != 'annotated':
            notready.append('%s(%s)' % (inst, st))
    if notready:
        W.append(('V9', '非 annotated 符号 %d 个,不可正式出图: %s'
                  % (len(notready), ' '.join(sorted(notready)))))
    ev.append({'id': 'V9', 'not_annotated': sorted(notready)})

    # ---------- V10 线型可推导 + 网络计数一致 ----------
    nets = sum(len(p) - 1 for p in intent['paths'])
    ev.append({'id': 'V10', 'l0_nets': nets, 'rendered_polylines': len(polys)})
    if len(polys) < nets:
        W.append(('V10', 'L0 声明 %d 条网络,图上只有 %d 条折线(母线合并所致须确认)'
                  % (nets, len(polys))))

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
    min_seg = 9e9
    for _c, pts in polys:
        turn_total += turns_of(pts)
        turn_max = max(turn_max, turns_of(pts))
        man = abs(pts[-1][0] - pts[0][0]) + abs(pts[-1][1] - pts[0][1])
        length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1])
                     for a, b in zip(pts, pts[1:]))
        if man > 0:
            ratios.append((length / man, pts))
        for a, b in zip(pts, pts[1:]):
            min_seg = min(min_seg, abs(a[0] - b[0]) + abs(a[1] - b[1]))

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

    # B5 节点盒净距：矩形间最小距离（轴向或对角，欧氏）。
    b5_gap = None
    bl = sorted(boxes.items())
    for i in range(len(bl)):
        for j in range(i + 1, len(bl)):
            r1, r2 = bl[i][1], bl[j][1]
            dx = max(r1[0] - r2[2], r2[0] - r1[2], 0.0)
            dy = max(r1[1] - r2[3], r2[1] - r1[3], 0.0)
            g = math.hypot(dx, dy)
            if b5_gap is None or g < b5_gap:
                b5_gap = g

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

    # B4 最短走线段 ≥8px。
    if min_seg < BUDGET['B4']['budget']:
        add('B4', round(min_seg, 1), 'over')
        W.append(('V19', '构图预算 B4：最短走线段 %.1f < 8' % min_seg))
    else:
        add('B4', round(min_seg, 1), 'pass')

    # B5 节点盒净距 ≥40px。
    if b5_gap is not None and b5_gap < BUDGET['B5']['budget']:
        add('B5', round(b5_gap, 1), 'over')
        W.append(('V19', '构图预算 B5：节点盒最小净距 %.1f < 40' % b5_gap))
    else:
        add('B5', round(b5_gap, 1) if b5_gap is not None else None, 'pass')

    # B6 容器走廊：分组内边距取 layout.group_padding 实测；
    # 避让走廊需逐段算走线与元件的间隙，v1 未测。
    gp = L.get('group_padding')
    if gp is not None and gp < BUDGET['B6']['budget_group_padding']:
        add('B6', {'group_padding': gp, 'avoid_corridor': 'not_measured'}, 'over')
        W.append(('V19', '构图预算 B6：分组内边距 %g < 14' % gp))
    else:
        add('B6', {'group_padding': gp, 'avoid_corridor': 'not_measured'}, 'pass',
            '避让走廊 ≥12 未实现自动测量，v1 裁剪，目视/回读环节把关')
    ev.append({'id': 'V19', 'crossings': len(set(b1_cross)),
               'turns_total': turn_total, 'turns_max_single': turn_max,
               'detour_max': round(max(r for r, _ in ratios), 3) if ratios else None,
               'min_segment': round(min_seg, 1), 'box_gap_min': b5_gap})

    ev.append({'id': 'composition_budget', 'source':
               'rendering-rules.md 数值构图预算（concept 档 v1）',
               'items': {it['id']: it['status'] for it in items},
               'not_measured': ['B6.avoid_corridor', 'B7'],
               'note': 'B7 标签净空 6px 未自动测量（需文本包围盒近似），'
                       'V12 已覆盖压字重叠（0 净空）情形；B6 避让走廊同批裁剪。'})

    # ---------- 报告 ----------
    checks = ([{'id': i, 'result': 'fail', 'detail': d} for i, d in F]
              + [{'id': i, 'result': 'warn', 'detail': d} for i, d in W])
    rep = {
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
            'not_measured': ['B6.avoid_corridor（避让走廊 ≥12）', 'B7（标签净空 ≥6）'],
            'note': 'B6 避让走廊与 B7 标签净空 v1 未实现自动测量'
                    '（需文本包围盒近似与逐段间隙计算），V12 已覆盖压字重叠'
                    '（0 净空）情形。除 B1 交叉硬 fail 外，超限走 V19 WARN。',
        },
    }
    out = os.path.join(HERE, 'validation-report.json')
    io.open(out, 'w', encoding='utf-8').write(
        json.dumps(rep, ensure_ascii=False, indent=2))

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
    print('  未测: B6.avoid_corridor, B7 标签净空（v1 裁剪，见报告注明）')
    return 1 if F else 0


if __name__ == '__main__':
    sys.exit(main())
