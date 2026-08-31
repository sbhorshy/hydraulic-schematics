# -*- coding: utf-8 -*-
"""L0 intent.yaml + layout.json -> 原理图 SVG。

不做自动布局。坐标全部来自 layout.json,连线按端口实测坐标正交走线。
端口坐标从各符号 SVG 的 connection-points 组实读,不硬编码。
"""
import io, json, math, os, re, sys, xml.etree.ElementTree as ET

import preflight  # 同目录 L0 输入预检器（规范源与 skill 快照同名同源）

HERE = os.path.dirname(os.path.abspath(__file__))
NS = 'http://www.w3.org/2000/svg'


def load_yaml(path):
    from ruamel.yaml import YAML
    y = YAML(typ='safe', pure=True)
    y.version = (1, 2)
    with io.open(path, encoding='utf-8') as f:
        return y.load(f)


def read_symbol(path):
    """返回 (inner_svg_markup, viewbox, {port_id: (x, y, anchor, role, medium)})。

    viewbox 为四元组 (vx, vy, vw, vh)。原点不一定是 0,0——油箱符号是
    "20 10 218 564"。端口坐标是 viewBox 用户坐标,须减去原点再乘缩放。
    """
    tree = ET.parse(path)
    root = tree.getroot()
    vb = [float(v) for v in root.get('viewBox').replace(',', ' ').split()]
    ports = {}
    body = []
    for child in root:
        tag = child.tag.split('}')[-1]
        if child.get('id') == 'connection-points':
            for c in child:
                pid = c.get('data-port-id')
                if not pid:
                    continue
                ports[pid] = (
                    float(c.get('cx')), float(c.get('cy')),
                    c.get('data-anchor-direction'),
                    c.get('data-port-role'), c.get('data-medium'),
                )
            continue
        if tag in ('g', 'path', 'circle', 'line', 'rect', 'polyline', 'polygon'):
            body.append(ET.tostring(child, encoding='unicode'))
    markup = '\n'.join(body).replace('ns0:', '').replace(' xmlns:ns0="%s"' % NS, '')
    return markup, (vb[0], vb[1], vb[2], vb[3]), ports


def path_line_type(tokens):
    """识别完整 path 的路径级线型；当前只定义吸油路径传播规则。

    吸油路径从油箱吸油口(或油箱内吸油过滤器入口)至泵 suction 口。
    中间串联组件不终止该语义。其他路径返回 None,仍按端口 role 逐 net 推导。
    """
    if len(tokens) < 2 or tokens[0].startswith('@') or tokens[-1].startswith('@'):
        return None
    first = tokens[0].split('.', 1)[1] if '.' in tokens[0] else ''
    last = tokens[-1].split('.', 1)[1] if '.' in tokens[-1] else ''
    if first in ('suction_out', 'suction_filter_in') and last == 'suction':
        return 'suction'
    return None


def suction_marker_geometry(S):
    """由企业图样的 Dimension S 推导吸油标记全部几何。

    角度定义为斜杠与管线基线的锐角。S 属于图纸样式,不进入系统意图。
    """
    S = float(S)
    if S <= 0:
        raise ValueError('suction_marker_S 必须 > 0,实际 %g' % S)
    return {
        'count': 5,
        'slash_height': 2.0 * S,
        'slash_angle_deg': 60.0,
        'intra_spacing': 1.25 * S,
        'group_pitch': 12.5 * S,
        'end_clearance': 4.0 * S,
    }


def suction_markers(pts, blocked=(), S=8.0,
                    start_terminal=True, end_terminal=True):
    """为正交吸油线生成周期性五斜杠组；基线本身保持连续实线。

    start_terminal/end_terminal 只表示整条吸油流道的真实起止端：油箱侧
    起点与泵吸入口。FSOV 等串联连接部件的边界不是吸油流道终端，
    不重新施加 4S 端部净空。

    水平段上的斜杠为 /；竖直段将同一标记随管线旋转 90°。
    每组整体做碰撞判定，任一斜杠碰障碍则整组不画，避免残缺组。
    """
    out = []
    g = suction_marker_geometry(S)
    end_gap = g['end_clearance']
    count = g['count']
    spacing = g['intra_spacing']
    pitch = g['group_pitch']
    dy = g['slash_height'] / 2.0
    # angle 是斜杠与水平基线的夹角:tan(angle)=总高/总宽。
    dx = dy / math.tan(math.radians(g['slash_angle_deg']))

    # 路由器常把一条直线拆成“端口短段+中段+端口短段”。
    # 线型是视觉路径属性,不能受这种内部切段影响；先合并连续共线点。
    merged = []
    for p in pts:
        if len(merged) < 2:
            merged.append(p)
            continue
        a, b = merged[-2], merged[-1]
        same_h = abs(a[1] - b[1]) < 0.5 and abs(b[1] - p[1]) < 0.5
        same_v = abs(a[0] - b[0]) < 0.5 and abs(b[0] - p[0]) < 0.5
        if same_h or same_v:
            merged[-1] = p
        else:
            merged.append(p)
    pts = merged

    def hits_box(a, b):
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        return any(not (x1 < r[0] or x0 > r[2] or y1 < r[1] or y0 > r[3])
                   for r in blocked)

    nseg = len(pts) - 1
    for si, (p0, p1) in enumerate(zip(pts, pts[1:])):
        horiz = abs(p1[1] - p0[1]) < 0.5
        vert = abs(p1[0] - p0[0]) < 0.5
        if not (horiz or vert):
            continue
        length = abs(p1[0] - p0[0]) + abs(p1[1] - p0[1])
        # 拐角仍保留 4S，防止斜杠跨过折角；只有串联部件把一条吸油
        # 流道拆成多个 net 时，外侧边界不算终端、不施加 4S。
        left_gap = end_gap if (si > 0 or start_terminal) else 0.0
        right_gap = end_gap if (si < nseg - 1 or end_terminal) else 0.0
        group_half = ((count - 1) / 2.0) * spacing + dx
        min_center = left_gap + group_half
        max_center = length - right_gap - group_half
        if min_center > max_center:
            continue
        sign = 1.0 if (p1[0] > p0[0] if horiz else p1[1] > p0[1]) else -1.0
        # 以 pitch 为上限确定组数，再把整列组在可用区间中居中。
        ngroup = int((max_center - min_center) // pitch) + 1
        pos0 = (min_center + max_center - (ngroup - 1) * pitch) / 2.0
        centers = [pos0 + j * pitch for j in range(ngroup)]
        for pos in centers:
            gc = []
            for j in range(count):
                off = (j - (count - 1) / 2.0) * spacing
                if horiz:
                    cx, cy = p0[0] + sign * (pos + off), p0[1]
                    a, b = (cx - dx, cy + dy), (cx + dx, cy - dy)
                else:
                    cx, cy = p0[0], p0[1] + sign * (pos + off)
                    a, b = (cx - dy, cy - dx), (cx + dy, cy + dx)
                gc.append((a, b))
            if not any(hits_box(a, b) for a, b in gc):
                out.extend(gc)
    return out


class Sheet(object):
    def __init__(self, intent, layout, catalog):
        self.i, self.L, self.cat = intent, layout, catalog
        self.types = {c['component_type']: c for c in catalog['components']}
        self.sym = {}      # inst -> (markup, wh, ports)
        self.abs = {}      # (inst, port) -> (x, y, anchor)
        # (inst, port) -> line_type。符号内部那段端口引线是走油的,
        # 线宽须随它所在管网的压力等级,不能按组件本体 1.5 T。
        # 否则接点处出现一个假的压力等级变化(线宽即等级编码)。
        self.port_lt = {}
        self.out = []
        self.warn = []
        self.drawn = []      # 已画线段,供避重叠用
        self.textboxes = []  # 文字包围盒,供避压字用
        self.polys = []      # (line_type, 点串),供求交叉与打断用
        # (点串,start_terminal,end_terminal)。同一 intent path 内的 FSOV 等
        # 串联部件不终止吸油流道,其两侧 net 共享路径级端部语义。
        self.suction_runs = []
        # 母线全长预登记为"已占线",使任何支路都不会沿母线纵走。
        # 母线本体最后才画,若不预登记,先画的支路无从知道那里将有母线。
        self.buslines = []
        for b in (layout.get('buses') or {}).values():
            self.buslines.append(((b['x'], 0.0),
                                  (b['x'], float(layout['canvas']['height']))))

    # ---------- 端口绝对坐标 ----------
    def place(self):
        for inst, nd in self.L['nodes'].items():
            path = os.path.normpath(os.path.join(HERE, nd['symbol']))
            markup, vb, ports = read_symbol(path)
            # 用户框类符号带名槽(data-name-slot):实例名渲染期写入框内,
            # 框外标签随之省略(名字不画两遍)。
            nd['_name_slot'] = 'data-name-slot' in markup
            vx, vy, vw, vh = vb
            # 缩放:布局给的 w/h 是图上占位尺寸,符号 viewBox 可能是任意
            # 尺寸(油箱 218x564,其余 80x80)。等比缩放,取较小的比例。
            k = min(nd['w'] / float(vw), nd['h'] / float(vh))
            W, H = vw * k, vh * k
            rot = int(nd.get('rot', 0)) % 360
            if rot not in (0, 90, 180, 270):
                raise ValueError('%s: rot=%s 不在目录允许的 0/90/180/270' % (inst, rot))
            if nd.get('mirror'):
                raise ValueError(
                    '%s: 已禁用 mirror。规范 6.3.3 要求优先用旋转与重排,'
                    '镜像会互换进出口而读图人先信符号朝向。' % inst)
            nd['_k'], nd['_vx'], nd['_vy'] = k, vx, vy
            nd['_W'], nd['_H'], nd['_rot'] = W, H, rot
            self.sym[inst] = (markup, vb, ports, nd)
            for pid, (px, py, anch, role, med) in ports.items():
                lx, ly = (px - vx) * k, (py - vy) * k
                # 旋转端口坐标与锚点方向。锚点必须同步旋转,否则出线方向
                # 与端口实际位置不符,走线越过端口再折回(规范 6.3.3)。
                if rot == 90:
                    lx, ly = H - ly, lx
                    anch = {'left': 'up', 'up': 'right',
                            'right': 'down', 'down': 'left'}[anch]
                elif rot == 180:
                    lx, ly = W - lx, H - ly
                    anch = {'left': 'right', 'right': 'left',
                            'up': 'down', 'down': 'up'}[anch]
                elif rot == 270:
                    lx, ly = ly, W - lx
                    anch = {'left': 'down', 'down': 'right',
                            'right': 'up', 'up': 'left'}[anch]
                self.abs[(inst, pid)] = (nd['x'] + lx, nd['y'] + ly, anch)

    def resolve(self, token, want=None):
        """token -> (inst, pid)。裸实例名按目录 main_path 补出端口。"""
        if '.' in token:
            inst, pid = token.split('.', 1)
        else:
            inst, pid = token, None
        if inst in self.L['externs']:
            return None, None
        if pid is None:
            mp = self.types[self.i['parts'][inst]]['main_path']
            if mp is None:
                return inst, None
            pid = mp[want]
        return inst, pid

    def mark_port_lt(self, token, want, lt):
        """记下某端口所属管网的压力等级,供端口引线取宽度。"""
        inst, pid = self.resolve(token, want)
        if inst and pid:
            self.port_lt[(inst, pid)] = lt

    def port(self, token, want=None):
        """'EDP-001.pressure_out' 或裸实例名 -> 绝对坐标。"""
        if '.' in token:
            inst, pid = token.split('.', 1)
        else:
            inst, pid = token, None
        if inst in self.L['externs']:
            e = self.L['externs'][inst]
            return (e['x'], e['y'], e['anchor'])
        if pid is None:
            mp = self.types[self.i['parts'][inst]]['main_path']
            if mp is None:
                raise ValueError('%s: main_path=null,须写显式端口' % token)
            pid = mp[want]
        key = (inst, pid)
        if key not in self.abs:
            raise ValueError('端口不存在: %s.%s' % (inst, pid))
        return self.abs[key]

    def role_of(self, token, want=None):
        if '.' in token:
            inst, pid = token.split('.', 1)
        else:
            inst, pid = token, None
        if inst in self.L['externs']:
            return {'suction': 'suction', 'return': 'return',
                    'inlet': 'pressure', 'outlet': 'pressure'}[self.i['extern'][inst]]
        ct = self.types[self.i['parts'][inst]]
        if pid is None:
            pid = ct['main_path'][want]
        for p in ct['ports']:
            if p['id'] == pid:
                return p['role']
        raise ValueError('no role for %s' % token)

    # ---------- 线型推导(L0 §10.4) ----------
    @staticmethod
    def line_type(ra, rb):
        s = {ra, rb}
        if s == {'pressure'}:
            return 'pressure'
        if 'suction' in s:
            return 'suction'
        if 'case_drain' in s:
            return 'case_drain'
        if 'return' in s:
            return 'return'
        return 'ERROR'

    # ---------- 正交走线 ----------
    def obstacles(self, exclude=()):
        out = []
        for inst, nd in self.L['nodes'].items():
            if inst in exclude:
                continue
            out.append((nd['x'], nd['y'], nd['x'] + nd['w'], nd['y'] + nd['h']))
        return out

    @staticmethod
    def hits(pts, obs, tol=4.0, skip_ends=False):
        """折线穿越障碍矩形的总长度。

        skip_ends:跳过首末两段。首段是端口到引出点、末段是引入点到端口,
        二者按构造必然贴着自身元件的边界,不算穿越。中间各段则必须避开
        **全部**元件——包括线要去的那个元件。油箱回油口朝左,而回油自右
        侧来,只有绕到油箱下方才能正确接入;若把目的元件排除在障碍之外,
        走线会直接横穿油箱(校核项 V2 反复报同一处)。
        """
        rng = range(1, len(pts) - 2) if (skip_ends and len(pts) > 3) \
            else range(len(pts) - 1)
        tot = 0.0
        for k in rng:
            (x0, y0), (x1, y1) = pts[k], pts[k + 1]
            for (rx0, ry0, rx1, ry1) in obs:
                a0, b0, a1, b1 = rx0 + tol, ry0 + tol, rx1 - tol, ry1 - tol
                if a1 <= a0 or b1 <= b0:
                    continue
                if abs(y1 - y0) < 0.5 and b0 < y0 < b1:
                    lo, hi = sorted((x0, x1))
                    tot += max(0.0, min(hi, a1) - max(lo, a0))
                elif abs(x1 - x0) < 0.5 and a0 < x0 < a1:
                    lo, hi = sorted((y0, y1))
                    tot += max(0.0, min(hi, b1) - max(lo, b0))
        return tot

    @staticmethod
    def overlap(pts, drawn):
        """与已画线段的共线重叠总长。

        图上两条共线重叠的管路看起来是一条,读图必然误判连通关系。
        三条回油都从 x=40 纵向回油箱时就会叠成一条(校核项 V13)。
        """
        tot = 0.0
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            h = abs(b[1] - a[1]) < 0.6
            for (c, d) in drawn:
                h2 = abs(d[1] - c[1]) < 0.6
                if h != h2:
                    continue
                if h:
                    if abs(a[1] - c[1]) > 1.2:
                        continue
                    lo1, hi1 = sorted((a[0], b[0]))
                    lo2, hi2 = sorted((c[0], d[0]))
                else:
                    if abs(a[0] - c[0]) > 1.2:
                        continue
                    lo1, hi1 = sorted((a[1], b[1]))
                    lo2, hi2 = sorted((c[1], d[1]))
                tot += max(0.0, min(hi1, hi2) - max(lo1, lo2))
        return tot

    @staticmethod
    def crossings(pts, drawn):
        """与已画线段的垂直交叉次数。交叉不违规但需跨线桥,故计入代价。"""
        n = 0
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            h = abs(b[1] - a[1]) < 0.6
            for (c, d) in drawn:
                h2 = abs(d[1] - c[1]) < 0.6
                if h == h2:
                    continue
                if h:
                    lo, hi = sorted((a[0], b[0]))
                    vlo, vhi = sorted((c[1], d[1]))
                    if lo + 1 < c[0] < hi - 1 and vlo + 1 < a[1] < vhi - 1:
                        n += 1
                else:
                    lo, hi = sorted((c[0], d[0]))
                    vlo, vhi = sorted((a[1], b[1]))
                    if lo + 1 < a[0] < hi - 1 and vlo + 1 < c[1] < vhi - 1:
                        n += 1
        return n

    @staticmethod
    def dedup(pts):
        out = [pts[0]]
        for p in pts[1:]:
            if abs(p[0] - out[-1][0]) > 0.3 or abs(p[1] - out[-1][1]) > 0.3:
                out.append(p)
        return out

    def route(self, a, b, exclude=(), lanes=()):
        """正交走线,择优避开元件本体。

        先按锚点出线,再在若干候选走廊中选穿越障碍最少者。
        早先版本只生成一条路径,壳体回油与主回油因此横穿油箱、
        泵与滤的本体(校核项 V2 抓到 9 处)。
        """
        ax, ay, aa = a
        bx, by, ba = b
        S = 20.0
        stub = {'left': (-S, 0), 'right': (S, 0), 'up': (0, -S), 'down': (0, S)}
        a1 = (ax + stub[aa][0], ay + stub[aa][1])
        b1 = (bx + stub[ba][0], by + stub[ba][1])
        obs = self.obstacles(exclude)

        cands = []
        # 直连**仅在共线时**允许。
        # 早先版本无条件加入 [a1,b1]:它长度最短、拐点最少,评分必然最优,
        # 于是只要不撞元件就被选中,画出斜线。液压原理图必须正交,
        # 斜线在图上会被读成软管或示意连接。校核项 V11 现已拦住。
        if abs(a1[0] - b1[0]) < 0.5 or abs(a1[1] - b1[1]) < 0.5:
            cands.append([a1, b1])
        # 单折:先横后纵 / 先纵后横
        cands.append([a1, (b1[0], a1[1]), b1])
        cands.append([a1, (a1[0], b1[1]), b1])
        # 双折:中线分割
        mx = (a1[0] + b1[0]) / 2.0
        my = (a1[1] + b1[1]) / 2.0
        cands.append([a1, (mx, a1[1]), (mx, b1[1]), b1])
        cands.append([a1, (a1[0], my), (b1[0], my), b1])
        # 指定水平走廊(绕开元件带)
        for ly in lanes:
            cands.append([a1, (a1[0], ly), (b1[0], ly), b1])
        # 先横移到竖廊,再沿竖廊纵走,最后横入目标。
        # 只有水平走廊时,自元件下方引出的线仍会沿原 x 纵穿下方的元件。
        for cx in self.L.get('vlanes', []):
            cands.append([a1, (cx, a1[1]), (cx, b1[1]), b1])
            for ly in lanes:
                cands.append([a1, (cx, a1[1]), (cx, ly), (b1[0], ly), b1])
        # 双竖廊:入廊、走廊、出廊,用于起止都在同一侧的绕行。
        for cx in self.L.get('vlanes', []):
            for ly in lanes:
                for cx2 in self.L.get('vlanes', []):
                    if abs(cx2 - cx) < 1:
                        continue
                    cands.append([a1, (cx, a1[1]), (cx, ly),
                                  (cx2, ly), (cx2, b1[1]), b1])

        # 代价权重:穿元件 > 与已画线重叠 > 与文字重叠 > 交叉 > 长度 > 拐点。
        # 前三项是会导致误读的缺陷,必须压过"线短拐点少"的观感偏好。
        best, bad = None, None
        for c in cands:
            pts = self.dedup([(ax, ay)] + c + [(bx, by)])
            if len(pts) < 2:
                continue
            h = self.hits(pts, obs, skip_ends=True)
            ov = self.overlap(pts, self.drawn) + self.overlap(pts, self.buslines)
            tx = self.hits(pts, self.textboxes, skip_ends=False, tol=0.0)
            cr = self.crossings(pts, self.drawn)
            length = sum(abs(pts[k + 1][0] - pts[k][0]) + abs(pts[k + 1][1] - pts[k][1])
                         for k in range(len(pts) - 1))
            score = (h * 10000 + ov * 3000 + tx * 900
                     + cr * 120 + length + len(pts) * 5)
            if bad is None or score < bad:
                bad, best = score, pts
        for k in range(len(best) - 1):
            self.drawn.append((best[k], best[k + 1]))
        return best

    @staticmethod
    def polyline(pts, lt):
        d = ' '.join('%.1f,%.1f' % p for p in pts)
        cls = 'ln-' + lt
        return '<polyline class="%s" points="%s"/>' % (cls, d)

    def find_crossings(self, junc, polys):
        """列出需要跨线桥的非连通交叉点。

        约定:**水平线跨越竖直线**。水平线在交叉处断开并以半圆弧跨过,
        竖直线保持连续。这与"被跨线连续"的读图习惯一致。
        """
        jset = {(round(x, 1), round(y, 1)) for (x, y) in junc}
        allseg = []
        for _c, pts in polys:
            for k in range(len(pts) - 1):
                allseg.append((pts[k], pts[k + 1]))
        vs = [(a, b) for (a, b) in allseg if abs(b[0] - a[0]) < 0.6]
        out = set()
        for _c, pts in polys:
            for k in range(len(pts) - 1):
                a, b = pts[k], pts[k + 1]
                if abs(b[1] - a[1]) >= 0.6:
                    continue
                y = a[1]
                lo, hi = sorted((a[0], b[0]))
                for (va, vb) in vs:
                    x = va[0]
                    vlo, vhi = sorted((va[1], vb[1]))
                    if lo + 1 < x < hi - 1 and vlo + 1 < y < vhi - 1:
                        if (round(x, 1), round(y, 1)) not in jset:
                            out.add((round(x, 1), round(y, 1), _c))
        return sorted(out)

    @staticmethod
    def split_h(pts, cross, R=5.0):
        """把折线的水平段在交叉点处打断,留出弧的宽度。

        *** 为什么不用白色遮罩 ***
        早先版本先画一条白线擦掉跨越处再画弧。白线宽 4.5,它同时擦掉了
        被跨越的那条竖线——而跨线桥的语义是"一条线跨过另一条",被跨线
        必须连续。图上表现为两条线在交叉处都断开,读图人看到四个断头,
        既不是三通也不是跨越。

        改法:只在跨越线自身的几何上开口,不擦任何像素。竖线完好。
        """
        cs = {(x, y) for (x, y, _lt) in cross}
        runs, cur = [], [pts[0]]
        for k in range(len(pts) - 1):
            a, b = pts[k], pts[k + 1]
            if abs(b[1] - a[1]) < 0.6:
                y = round(a[1], 1)
                xs = sorted([x for (x, cy) in cs if abs(cy - y) < 0.6
                             and min(a[0], b[0]) + 1 < x < max(a[0], b[0]) - 1],
                            reverse=(b[0] < a[0]))
                for x in xs:
                    s = 1 if b[0] > a[0] else -1
                    cur.append((x - R * s, y))
                    runs.append(cur)
                    cur = [(x + R * s, y)]
            cur.append(b)
        runs.append(cur)
        return [r for r in runs if len(r) > 1]

    @staticmethod
    def bridge_arcs(cross_lt, R=5.0):
        """半圆弧。上凸,不改变端点、流向与连接拓扑(规范 10.6.2)。

        弧的线宽必须等于**跨越线**的线宽:高压线 3.0T 断开后若补一段
        1.0T 的弧,图上就成了高压管中间接了一截低压管。
        """
        out = []
        for (x, y, lt) in cross_lt:
            cls = 'brg-hi' if PRESSURE_CLASS[lt] == 'high' else 'brg-lo'
            out.append('<path class="%s" d="M%.1f %.1f A%.1f %.1f 0 0 1 %.1f %.1f"/>'
                       % (cls, x - R, y, R, R, x + R, y))
        return out

    def build_textboxes(self):
        """预算文字包围盒。必须在 wire() 之前调用,否则走线器不知道
        哪里有字,画完才发现压住标签(校核项 V12)。"""
        FS = {'below': 11.0, 'above': 11.0, 'right': 11.0}
        for inst, nd in self.L['nodes'].items():
            if nd.get('_name_slot'):
                continue    # 名字已画在框内名槽,不占框外避让包围盒
            lab = self.L['labels'].get(inst, inst)
            pos = self.L['label_pos'].get(inst, 'below')
            fs = FS.get(pos, 11.0)
            lines = lab.split('\n')
            wid = max(sum(fs if ord(c) > 0x2E80 else fs * 0.55 for c in ln)
                      for ln in lines)
            cx = nd['x'] + nd['w'] / 2.0
            lift = self.L.get('label_lift', {}).get(inst, 0)
            drop = self.L.get('label_drop', {}).get(inst, 0)
            if pos == 'below':
                y0 = nd['y'] + nd['h'] + 16 + drop - fs
            elif pos == 'above':
                y0 = nd['y'] - 8 - 13 * (len(lines) - 1) - lift - fs
            else:
                y0 = nd['y'] + 16 - fs
            x0 = (nd['x'] + nd['w'] + 12) if pos == 'right' else (cx - wid / 2.0)
            self.textboxes.append((x0 - 2, y0 - 2, x0 + wid + 2,
                                   y0 + fs + 13 * (len(lines) - 1) + 4))
        for eid, e in self.L.get('externs', {}).items():
            lines = e['label'].split('\n')
            fs = 10.0
            wid = max(sum(fs if ord(c) > 0x2E80 else fs * 0.55 for c in ln)
                      for ln in lines)
            dx = -10 if e['anchor'] == 'right' else 10
            x0 = (e['x'] + dx - wid) if e['anchor'] == 'right' else (e['x'] + dx)
            self.textboxes.append((x0 - 2, e['y'] - fs, x0 + wid + 2,
                                   e['y'] + 4 + 13 * (len(lines) - 1)))
        for key in ('legend', 'title_block'):
            r = self.L.get(key)
            if r:
                sh = self.L.get('canvas_shift_x', 0)
                self.textboxes.append((r['x'] - sh, r['y'],
                                       r['x'] + r['w'] - sh, r['y'] + r['h']))

    # ---------- paths 编译 ----------
    def wire(self):
        """展开 paths;@总线名转为竖直母线。返回 (线段 markup 列表, 节点列表)."""
        segs, junctions, nets = [], [], []
        bus_hits = {}
        for pi, p in enumerate(self.i['paths']):
            nseg = len(p) - 1
            path_lt = path_line_type(p)
            for k in range(nseg):
                a, b = p[k], p[k + 1]
                nets.append((a, b, pi, k, nseg, path_lt))

        for a, b, pi, path_k, path_nseg, path_lt in nets:
            ab, bb = a.startswith('@'), b.startswith('@')
            if ab and bb:
                self.warn.append('总线直连总线,未支持: %s->%s' % (a, b))
                continue
            if ab or bb:
                bus = (a if ab else b)[1:]
                other = b if ab else a
                bx = self.L['buses'][bus]['x']
                want = 'in' if ab else 'out'
                oinst = other.split('.')[0]
                ox, oy, oa = self.port(other, want)
                ro = self.role_of(other, want)
                inferred = self.line_type(ro, 'pressure')
                lt = path_lt or inferred
                if path_lt and inferred not in (path_lt, 'ERROR'):
                    self.warn.append('路径级线型 %s 覆盖端口推导 %s:%s'
                                     % (path_lt, other, inferred))
                self.mark_port_lt(other, want, lt)
                # 从元件端口正交接到母线
                S = 18.0
                stub = {'left': (-S, 0), 'right': (S, 0), 'up': (0, -S), 'down': (0, S)}[oa]
                m = (ox + stub[0], oy + stub[1])
                # 元件到母线也要避障:早先直接横拉,穿过了中间的滤本体。
                cands = [[m, (bx, m[1])]]
                for ly in self.L.get('lanes', []):
                    cands.append([m, (m[0], ly), (bx, ly), (bx, m[1])])
                # 经水平走廊再上/下到母线接入高度。
                # 只有"直接横拉"和"先纵后横"两种候选时,自用户回油横穿
                # 了中间的回油滤本体(校核项 V2)。
                for ly in self.L.get('lanes', []):
                    cands.append([m, (m[0], ly), (bx, ly), (bx, m[1])])
                for cx2 in self.L.get('vlanes', []):
                    if abs(cx2 - bx) < 1:
                        continue        # 竖廊与母线同 x 时会沿母线纵走
                    for ly in self.L.get('lanes', []):
                        cands.append([m, (cx2, m[1]), (cx2, ly),
                                      (bx, ly), (bx, m[1])])
                obs = self.obstacles()
                best, bad = None, None
                for c in cands:
                    cp = self.dedup([(ox, oy)] + c)
                    if len(cp) < 2:
                        continue
                    h = self.hits(cp, obs, skip_ends=True)
                    # 本支路自己要接的这条母线不算(末段必然贴在它上面),
                    # 但其他母线要算。
                    # 全部母线都算,包括自己要接的这条:支路只应**横向**
                    # 抵达母线,不应沿母线纵走。沿母线走 480 单位在图上
                    # 与母线本体完全重合(校核项 V13)。
                    ov = (self.overlap(cp, self.drawn)
                          + self.overlap(cp, self.buslines))
                    tx = self.hits(cp, self.textboxes, tol=0.0)
                    cr = self.crossings(cp, self.drawn)
                    ln = sum(abs(cp[i + 1][0] - cp[i][0]) + abs(cp[i + 1][1] - cp[i][1])
                             for i in range(len(cp) - 1))
                    sc = (h * 10000 + ov * 3000 + tx * 900
                          + cr * 120 + ln + len(cp) * 5)
                    if bad is None or sc < bad:
                        bad, best = sc, cp
                pts = best
                for q in range(len(pts) - 1):
                    self.drawn.append((pts[q], pts[q + 1]))
                self.polys.append((lt, pts))
                if lt == 'suction':
                    self.suction_runs.append((pts, path_k == 0,
                                              path_k == path_nseg - 1))
                bus_hits.setdefault(bus, []).append((m[1], lt))
                continue

            aw, bw = 'out', 'in'
            pa = self.port(a, aw)
            pb = self.port(b, bw)
            ra = self.role_of(a, aw)
            rb = self.role_of(b, bw)
            inferred = self.line_type(ra, rb)
            lt = path_lt or inferred
            if path_lt and inferred not in (path_lt, 'ERROR'):
                self.warn.append('路径级线型 %s 覆盖端口推导 %s-%s:%s'
                                 % (path_lt, a, b, inferred))
            if lt == 'ERROR':
                self.warn.append('线型冲突 %s(%s) - %s(%s)' % (a, ra, b, rb))
                lt = 'pressure'
            self.mark_port_lt(a, aw, lt)
            self.mark_port_lt(b, bw, lt)
            # 两端所属元件不算障碍(线本就要接到它们身上)。
            # 同一条 path 内的相邻元件也要排除:泵.case_drain -> CDF -> 油箱
            # 是一条 path,其首段自泵下方引出时会途经 CDF 的占位框,
            # 但那正是它要去的地方,不是穿越。
            # 只排除本段两端的元件。早先把整条 path 的成员都排除,
            # 导致"CDF -> 油箱"这一段把油箱也当成非障碍,于是直接横穿
            # 油箱本体而不去找下方走廊(校核项 V2 反复报同一处)。
            rp = self.route(pa, pb, exclude=(), lanes=self.L.get('lanes', []))
            self.polys.append((lt, rp))
            if lt == 'suction':
                self.suction_runs.append((rp, path_k == 0,
                                          path_k == path_nseg - 1))

        # 母线本体 + 三通点。
        # 各支路已把自己接到母线 x 上,那些"接入段"若走了母线方向就会与
        # 母线本体共线叠 480 单位(校核项 V13)。故母线只画各接入点之间的
        # 区段,且支路不得沿母线纵走——由 vlanes 不含母线 x 保证。
        for bus, hits in bus_hits.items():
            bx = self.L['buses'][bus]['x']
            ys = sorted(h[0] for h in hits)
            lt = hits[0][1]
            self.polys.append((lt, [(bx, ys[0]), (bx, ys[-1])]))
            for y, _ in hits:
                # 只有母线内部接入点才是三通。两端是拐角,不是节点。
                # 早先版本在此加了 len(hits)>2 的条件,导致蓄压器和压力滤的
                # 端点也画了实心点,读图会误认为那里有第三条支路。
                if ys[0] < y < ys[-1]:
                    junctions.append((bx, y))
        return segs, junctions, bus_hits, self.polys

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
            pa3 = self.port(stok)
            pb3 = self.port(atok)
            pa = (pa3[0], pa3[1])
            pb = (pb3[0], pb3[1])
            aa = self.abs[(sinst, spid)][2]
            ab = self.abs[(ainst, apid)][2]
            self.port_lt[(sinst, spid)] = 'sense'
            S = 18.0
            stub = {'left': (-S, 0), 'right': (S, 0),
                    'up': (0, -S), 'down': (0, S)}[aa]
            a1 = (pa[0] + stub[0], pa[1] + stub[1])
            stubb = {'left': (-S, 0), 'right': (S, 0),
                     'up': (0, -S), 'down': (0, S)}[ab]
            # 终点也按锚向先出桩:最后一段必沿端口锚向进入,逆着锚向
            # 从元件体内反向出线的候选从形状上就不存在了。
            b1 = (pb[0] + stubb[0], pb[1] + stubb[1])
            cands = []
            if abs(a1[0] - b1[0]) < 0.5 or abs(a1[1] - b1[1]) < 0.5:
                cands.append([a1, b1])
            # 先按 sensor 锚点出线,再一折进入 at 端口桩;两种折向择优。
            # 先纵后横的形状不会倒折回端口正上方,排前。
            cands.append([a1, (b1[0], a1[1]), b1])
            cands.append([a1, (a1[0], b1[1]), b1])
            # 评分段自 a1 起算(端口桩只有 18px 且向外,B5≥40 保证桩不碰
            # 邻盒),障碍全量不豁免:回折穿传感器/目标本体的候选由此拿到
            # 应有的代价。早先两端元件盒都豁免且终点不带锚向桩,穿本体
            # 逆锚的候选反而以最短胜出(V2:感温线横穿充气活门本体)。
            obs = self.obstacles()
            best, bad = None, None
            for c in cands:
                pts = self.dedup(c + [pb])
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
            best = self.dedup([pa] + best)      # 绘制/追溯补回端口桩
            for k in range(len(best) - 1):
                self.drawn.append((best[k], best[k + 1]))
            self.polys.append(('sense', best))
        return juncs

    # ---------- 分组虚线框(技术规范 10.7) ----------
    def groups(self):
        out = []
        pad = self.L['group_padding']
        for g in self.i.get('groups') or []:
            box = None
            for m in g['members']:
                nd = self.L['nodes'].get(m)
                if not nd:
                    continue
                x0, y0 = nd['x'], nd['y']
                x1, y1 = x0 + nd['w'], y0 + nd['h']
                box = (x0, y0, x1, y1) if box is None else (
                    min(box[0], x0), min(box[1], y0), max(box[2], x1), max(box[3], y1))
            if box is None:
                self.warn.append('分组无成员落在布局中: %s' % g['id'])
                continue
            gap = self.L.get('group_label_gap', 8)
            out.append(
                '<rect class="grp" x="%.1f" y="%.1f" width="%.1f" height="%.1f"/>'
                '<text class="grp-lbl" x="%.1f" y="%.1f">%s</text>' % (
                    box[0] - pad, box[1] - pad,
                    box[2] - box[0] + 2 * pad, box[3] - box[1] + 2 * pad,
                    box[0] - pad, box[1] - pad - gap, self.esc(g['label'])))
        return out

    # ---------- 悬空端口检测 ----------
    def dangling(self):
        """列出布局中已绘制但未被任何 path 使用的端口。

        原理图最坏的失效模式是悄悄画一个没接线的口:读图人会以为它接好了。
        故凡未接线的端口一律标红圈并计数,不允许静默。
        """
        used = set()
        for p in self.i['paths']:
            for k, tok in enumerate(p):
                if tok.startswith('@'):
                    continue
                inst = tok.split('.')[0]
                if inst not in self.i['parts']:
                    continue
                if '.' in tok:
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
        marks, names = [], []
        for (inst, pid), (x, y, _a) in sorted(self.abs.items()):
            if (inst, pid) in used:
                continue
            marks.append('<circle class="dang" cx="%.1f" cy="%.1f" r="5"/>' % (x, y))
            names.append('%s.%s' % (inst, pid))
        return marks, names

    def esc(self, s):
        return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def texts(self):
        out = []
        for inst, nd in self.L['nodes'].items():
            if nd.get('_name_slot'):
                continue    # 用户框:名字在框内名槽,不再画框外标签
            lab = self.L['labels'].get(inst, inst)
            pos = self.L['label_pos'].get(inst, 'below')
            cx = nd['x'] + nd['w'] / 2.0
            lines = lab.split('\n')
            # 分组虚线框会占据元件上方 pad+gap,故框内元件的 above 标签
            # 必须让位到框外,否则与分组标签重叠(渲染已证实)。
            lift = self.L.get('label_lift', {}).get(inst, 0)
            drop = self.L.get('label_drop', {}).get(inst, 0)
            if pos == 'below':
                y0, anch, cx2 = nd['y'] + nd['h'] + 16 + drop, 'middle', cx
            elif pos == 'above':
                y0, anch, cx2 = nd['y'] - 8 - 13 * (len(lines) - 1) - lift, 'middle', cx
            else:
                y0, anch, cx2 = nd['y'] + 16, 'start', nd['x'] + nd['w'] + 12
            for k, ln in enumerate(lines):
                out.append('<text class="lbl" x="%.1f" y="%.1f" text-anchor="%s">%s</text>'
                           % (cx2, y0 + 13 * k, anch, self.esc(ln)))
        for eid, e in self.L['externs'].items():
            lines = e['label'].split('\n')
            anch = 'end' if e['anchor'] == 'right' else 'start'
            dx = -10 if e['anchor'] == 'right' else 10
            for k, ln in enumerate(lines):
                out.append('<text class="ext" x="%.1f" y="%.1f" text-anchor="%s">%s</text>'
                           % (e['x'] + dx, e['y'] + 4 + 13 * k, anch, self.esc(ln)))
        return out

    def symbols(self):
        out = []
        for inst, (markup, vb, ports, nd) in self.sym.items():
            k, vx, vy = nd['_k'], nd['_vx'], nd['_vy']
            W, H, rot = nd['_W'], nd['_H'], nd['_rot']
            # 先落位,再旋转,最后缩放并归零 viewBox 原点。
            # 旋转后的补偿平移使符号仍占据 (x,y) 起始的正矩形。
            comp = {0: (0, 0), 90: (H, 0), 180: (W, H), 270: (0, W)}[rot]
            tf = ('translate(%g,%g) translate(%g,%g) rotate(%d) scale(%g) '
                  'translate(%g,%g)' % (nd['x'], nd['y'], comp[0], comp[1],
                                        rot, k, -vx, -vy))
            # 先归一本体线宽,再把端口引线改判为管线宽。顺序不能反:
            # norm_stroke 会给带 stroke-width 的父 <g> 挂上 sym-outline,
            # 引线作为子元素继承之,故 pl-* 必须后加且在 CSS 中更具体。
            mk = self.norm_stroke(self.uniq(markup, inst))
            mk = self.portlines(mk, ports, inst)
            if nd.get('_name_slot'):
                mk = self.fill_name_slot(mk, inst)
            # 按 1/k 补偿符号自身的落位缩放:线宽经 scale(k) 后正好
            # 还原为标准值。用 CSS 变量传递,由实例 g 上的内联 style
            # 覆盖——不能写成实例 g 的 stroke-width 属性,那会被后代
            # 元素自己的 class 规则压过(CSS 优先于继承的表现属性),
            # 补偿静默失效。
            comp = ('' if abs(k - 1.0) < 1e-9
                    else ' style="--kc:%.6f"' % (1.0 / k))
            out.append('<g id="inst-%s" transform="%s"%s>\n%s\n</g>'
                       % (inst, tf, comp, mk))
        return out

    @staticmethod
    def uniq(markup, inst):
        """给符号内部 id 加实例前缀。

        每个符号内部都有 id="symbol",直接嵌入整图会产生 9 个重复 id
        (SVG 非法)。校核项 V1 已抓到。
        """
        return re.sub(r'\bid="([^"]+)"', lambda m: 'id="%s__%s"' % (inst, m.group(1)),
                      markup)

    def portlines(self, markup, ports, inst):
        """把符号内部的"端口引线"改判为管线线宽。

        判据是几何,不是文件位置:一端落在某个端口红点上、另一端落在
        本体上的 <line>,就是这个端口的引线——它走油,故按所在管网的
        压力等级取宽(3.0/1.0 T),不按组件本体 1.5 T。
        识别不到所属管网(悬空端口、非液压口如 FSOV.command)时不改,
        保持本体线宽——因为那里确实没有管线。
        """
        px = {}
        for pid, (x, y, _a, _r, med) in ports.items():
            if med != 'hydraulic':
                continue          # 电、气信号口不是管线
            lt = self.port_lt.get((inst, pid))
            if lt:
                px[(round(x, 1), round(y, 1))] = lt

        def sub(m):
            tag = m.group(0)
            g = {k: float(v) for k, v in
                 re.findall(r'\b(x1|y1|x2|y2)="([-\d.]+)"', tag)}
            if len(g) < 4:
                return tag
            e = [(round(g['x1'], 1), round(g['y1'], 1)),
                 (round(g['x2'], 1), round(g['y2'], 1))]
            hit = [px[p] for p in e if p in px]
            if len(hit) != 1:
                return tag        # 两端都是端口或都不是,不是引线
            tag = re.sub(r'\s*stroke-width="[^"]*"', '', tag)
            if 'class="' in tag:
                return re.sub(r'class="([^"]*)"',
                              r'class="\1 pl-%s"' % hit[0], tag)
            return tag[:-2].rstrip() + ' class="pl-%s"/>' % hit[0]

        return re.sub(r'<line [^>]*/>', sub, markup)

    def fill_name_slot(self, markup, inst):
        """把用户框符号的名槽文本替换为实例标签(hydraulic_user)。

        符号文件里的槽位是占位内容"用户";实例名各不相同,只能渲染期
        写入。槽位 x/y 从符号自带属性读,不在此硬编码几何;多行标签以
        单行基线为中心上下展开(行距 13,与图纸标签一致)。
        """
        lines = [ln for ln in self.L['labels'].get(inst, inst).split('\n') if ln]
        if not lines:
            return markup

        def repl(m):
            open_, close = m.group(1), m.group(3)
            mx = re.search(r'\bx="([-\d.]+)"', open_)
            my = re.search(r'\by="([-\d.]+)"', open_)
            x = mx.group(1) if mx else '0'
            y = float(my.group(1)) if my else 0.0
            ys = [y + 13.0 * k - 6.5 * (len(lines) - 1)
                  for k in range(len(lines))]
            inner = ''.join('<tspan x="%s" y="%.1f">%s</tspan>'
                            % (x, yy, self.esc(ln))
                            for yy, ln in zip(ys, lines))
            return open_ + inner + close

        return re.sub(r'(<text[^>]*\bdata-name-slot\b[^>]*>)(.*?)(</text>)',
                      repl, markup, flags=re.S)

    @staticmethod
    def norm_stroke(markup):
        """把符号自带的绝对 stroke-width 换成 class="sym-outline"。

        线宽是图纸级标准(组件本体 1.5 T),不是符号作者的自由度。
        符号文件里写死 stroke-width="2" 会绕过标准:实测过 2.0 = 1.667 T,
        既不是 1.0 也不是 1.5,不来自任何依据。此处统一收口。
        不改 stroke-dasharray(虚线是语义,如滤芯),也不改 fill。
        """
        def sub(m):
            tag = m.group(0)
            if 'stroke-width' not in tag:
                return tag
            # 白色描边是遮挡图元(如油箱的 gauge-clearance),不是可见线条,
            # 套上 1.5 T 会把它变成一条真线。原样放过。
            if re.search(r'stroke="#(?:fff(?:fff)?|FFF(?:FFF)?)"', tag):
                return tag
            tag = re.sub(r'\s*stroke-width="[^"]*"', '', tag)
            if 'class="' in tag:
                return re.sub(r'class="([^"]*)"', r'class="\1 sym-outline"', tag)
            return tag[:-1].rstrip() + ' class="sym-outline">'
        return re.sub(r'<(?!/)[^>]*>', sub, markup)

    def externs_marks(self):
        out = []
        for eid, e in self.L['externs'].items():
            k = self.i['extern'][eid]
            # 边界标记:半开三角,指向系统内/外由类型决定
            if e['anchor'] == 'right':   # 位于左侧,朝右
                d = 'M%.1f %.1f L%.1f %.1f L%.1f %.1f Z' % (
                    e['x'] - 12, e['y'] - 8, e['x'], e['y'], e['x'] - 12, e['y'] + 8)
            else:
                d = 'M%.1f %.1f L%.1f %.1f L%.1f %.1f Z' % (
                    e['x'] + 12, e['y'] - 8, e['x'], e['y'], e['x'] + 12, e['y'] + 8)
            fill = '#ffffff' if k in ('outlet', 'inlet') else '#e8e8e8'
            out.append('<path class="ext-mark" d="%s" fill="%s"/>' % (d, fill))
        return out


# 企业图纸标准的管线宽度约定(工程师提供):
#   High Pressure Lines — 高于回油压力的全部压力级 — 全部 3.0 T
#   Low  Pressure Lines — 全部 1.0 T
# 只按线宽分两级,不用线型。故此前我自拟的 case_drain 虚线必须撤除:
# 它是我编的非标准约定,且与 10.7 的装配虚线边界在图上无法区分。
PRESSURE_CLASS = {
    'sense': 'low',        # 气侧支路(充气活门/压力表):1.0 T 实线,归低压级
    'pressure': 'high',
    'return': 'low',       # 回油压力是分级基准,自身不高于它
    'suction': 'low',      # 低于回油压力
    'case_drain': 'low',
}
WIDTH_T = {'high': 3.0, 'low': 1.0}
SYMBOL_T = 1.5   # 组件本体线宽(企业标准)。介于低压 1.0T 与高压 3.0T 之间。


def css(T):
    """T 为经批准的图纸基准线宽(规范 10.7)。全部线宽由 T 导出。"""
    hi = WIDTH_T['high'] * T
    lo = WIDTH_T['low'] * T
    sy = SYMBOL_T * T
    return """
  text { font-family: "Noto Sans CJK SC","Microsoft YaHei",sans-serif; }
  .lbl  { font-size: 11px; fill: #000; }
  .ext  { font-size: 10px; fill: #333; }
  .grp  { fill: none; stroke: #000; stroke-width: %(gb).2f;
          stroke-dasharray: 8 5; }
  .grp-lbl { font-size: 10.5px; fill: #000; }
  .ext-mark { stroke: #000; stroke-width: %(lo).2f; }
  polyline { fill: none; stroke: #000;
             stroke-linecap: butt; stroke-linejoin: miter; }
  .ln-pressure   { stroke-width: %(hi).2f; }
  .ln-return     { stroke-width: %(lo).2f; }
  .ln-suction    { stroke-width: %(lo).2f; }
  .ln-case_drain { stroke-width: %(lo).2f; }
  .ln-sense      { stroke-width: %(lo).2f; }
  .suc-mark { stroke: #000; stroke-width: %(lo).2f;
              stroke-linecap: butt; }
  .jn { fill: #000; }
  .dang { fill: none; stroke: #d00000; stroke-width: %(sy).2f; }
  .brg-hi { fill: none; stroke: #000; stroke-width: %(hi).2f;
            stroke-linecap: butt; }
  .brg-lo { fill: none; stroke: #000; stroke-width: %(lo).2f;
            stroke-linecap: butt; }
  .banner { font-size: 15px; font-weight: bold; fill: #b00000; }
  .tb  { fill: none; stroke: #000; stroke-width: %(lo).2f; }
  .tb-t{ font-size: 11px; fill: #000; }
  .lg  { fill: #fff; stroke: #000; stroke-width: %(lo).2f; }
  .lg-t{ font-size: 10.5px; fill: #000; }

  /* 组件本体线宽:企业标准 1.5 T,一处定义。
     曾用 vector-effect: non-scaling-stroke 来抵消符号的落位缩放,
     那是错的:该属性把线宽钉在**设备像素**上,于是整图放大出图时
     管线随之变粗、而符号内的线纹丝不动(实测 1x/2x/3x 下管线
     4/8/10px,引线恒为 4px)。改为在实例上按 1/k 补偿,
     线宽随图缩放,同时不受符号自身缩放影响。 */
  :root { --kc: 1; }
  .sym-outline { stroke-width: calc(%(sy).2f * var(--kc)); }

  /* 符号内部的端口引线。它走油,故随管网压力等级,不随组件本体。
     判据是"是否走油",而非"画在哪个文件里"。
     选择器带 line 提高特异性,压过父 g 元素继承来的 sym-outline。
     注:style 内容未包 CDATA,注释里不可出现尖括号,会破坏 XML。 */
  line.pl-pressure   { stroke-width: calc(%(hi).2f * var(--kc)); }
  line.pl-return     { stroke-width: calc(%(lo).2f * var(--kc)); }
  line.pl-suction    { stroke-width: calc(%(lo).2f * var(--kc)); }
  line.pl-case_drain { stroke-width: calc(%(lo).2f * var(--kc)); }
""" % {'hi': hi, 'lo': lo, 'sy': sy, 'gb': 1.5 * T}


def legend(L, T):
    g = L['legend']
    x, y, w, h = g['x'], g['y'], g['w'], g['h']
    hi, lo = WIDTH_T['high'] * T, WIDTH_T['low'] * T
    sy = SYMBOL_T * T
    S = float(L.get('style', {}).get('suction_marker_S', 8.0))
    sg = suction_marker_geometry(S)
    # 只列两级管线 + 组件本体。此前列四行、其中三行渲染结果逐像素相同——
    # 图例承诺的区分并未画出,那是图例在撒谎。现按企业标准如实列出。
    rows = [
        ('High Pressure Lines  高压 (高于回油压力的全部压力级)  3.0 T', hi),
        ('Low Pressure Lines   低压 (回油、壳体回油)             1.0 T', lo),
        ('Gas-side Branch 气侧支路 (充气活门/压力表)          1.0 T', lo),
        ('Suction Lines  吸油:连续基线 + 周期性五斜杠组  1.0 T (S=%g)' % S,
         ('suction', lo)),
        ('组件本体 (符号轮廓、内部机构)                          1.5 T', sy),
        ('  端口引线 (viewBox 边界到符号轮廓) 随管线等级      3.0 / 1.0 T', None),
        ('  ∴ 管线与组件交接处有台阶,位于符号边界,不表示压力等级变化', None),
    ]
    out = ['<rect class="lg" x="%.1f" y="%.1f" width="%.1f" height="%.1f"/>' % (x, y, w, h),
           '<text class="lg-t" x="%.1f" y="%.1f" font-weight="bold">'
           '图例  (T = %.2f)</text>' % (x + 10, y + 18, T)]
    for k, row in enumerate(rows):
        yy = y + 40 + k * 22
        if row[1] is None:
            # 副行:缩进,不画线宽示例
            out.append('<text class="lg-t" x="%.1f" y="%.1f">%s</text>'
                       % (x + 72, yy + 4, row[0]))
        elif isinstance(row[1], tuple) and row[1][0] == 'suction':
            sx0, sx1 = x + 12, x + 56
            scy = yy
            out.append('<line class="suc-sample-base" x1="%.1f" y1="%.1f" '
                       'x2="%.1f" y2="%.1f" stroke="#000" stroke-width="%.2f"/>'
                       % (sx0, scy, sx1, scy, row[1][1]))
            sdy = sg['slash_height'] / 2.0
            sdx = sdy / math.tan(math.radians(sg['slash_angle_deg']))
            group_w = (sg['count'] - 1) * sg['intra_spacing'] + 2 * sdx
            demo_k = min(1.0, (sx1 - sx0) / group_w)
            center = (sx0 + sx1) / 2.0
            for q in range(sg['count']):
                off = (q - (sg['count'] - 1) / 2.0) * sg['intra_spacing'] * demo_k
                cx = center + off
                out.append('<line class="suc-sample-mark" x1="%.1f" y1="%.1f" '
                           'x2="%.1f" y2="%.1f" stroke="#000" stroke-width="%.2f"/>'
                           % (cx - sdx * demo_k, scy + sdy * demo_k,
                              cx + sdx * demo_k, scy - sdy * demo_k, row[1][1]))
            out.append('<text class="lg-t" x="%.1f" y="%.1f">%s</text>'
                       % (x + 64, yy + 4, row[0]))
        else:
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
                       'stroke-width="%.2f"/>' % (x + 12, yy, x + 56, yy, row[1]))
            out.append('<text class="lg-t" x="%.1f" y="%.1f">%s</text>'
                       % (x + 64, yy + 4, row[0]))
    yy = y + 40 + len(rows) * 22
    out.append('<path d="M%.1f %.1f L%.1f %.1f L%.1f %.1f Z" fill="#e8e8e8" stroke="#000" '
               'stroke-width="%.2f"/>' % (x + 12, yy - 7, x + 26, yy, x + 12, yy + 7, sy))
    out.append('<text class="lg-t" x="%.1f" y="%.1f">系统边界接口(用户未建模)</text>'
               % (x + 64, yy + 4))
    yy += 22
    out.append('<path class="brg-lo" d="M%.1f %.1f A5 5 0 0 1 %.1f %.1f"/>'
               % (x + 24, yy, x + 34, yy))
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="%.2f"/>' % (x + 29, yy - 12, x + 29, yy + 8, lo))
    out.append('<text class="lg-t" x="%.1f" y="%.1f">跨线桥:横线跨过竖线,'
               '二者不连通</text>' % (x + 64, yy + 4))
    yy += 22
    out.append('<circle class="jn" cx="%.1f" cy="%.1f" r="3"/>' % (x + 29, yy))
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="#000" '
               'stroke-width="%.2f"/>' % (x + 12, yy, x + 46, yy, hi))
    out.append('<text class="lg-t" x="%.1f" y="%.1f">三通:实心点表示连通</text>'
               % (x + 64, yy + 4))
    yy += 22
    out.append('<circle class="dang" cx="%.1f" cy="%.1f" r="5"/>' % (x + 29, yy))
    out.append('<text class="lg-t" x="%.1f" y="%.1f">悬空端口:未接线,'
               '不得视为已连接</text>' % (x + 64, yy + 4))
    # 内容底边超出图例框即为图例自身溢出,V7 查不到(它只查框与框)。
    need = (yy + 10) - y
    if need > h:
        raise SystemExit('图例内容溢出:需要 h>=%.0f,布局给了 %.0f。'
                         '请改 layout 的 legend.h' % (need, h))
    return out


def title_block(L, intent, nnet, dnames):
    t = L['title_block']
    x, y, w, h = t['x'], t['y'], t['w'], t['h']
    out = ['<rect class="tb" x="%.1f" y="%.1f" width="%.1f" height="%.1f"/>' % (x, y, w, h)]
    row1 = ('系统 %s   |   L0 %s   |   目录 %s   |   成熟度 %s'
            % (intent['system'], intent['l0_version'], intent['catalog'], intent['maturity']))
    row2 = ('部件 %d   |   网络 %d   |   气侧支路 %d   |   未知项 %d   '
            '|   临时/草稿符号: EDP EMP FWSOV provisional; 油箱 draft(描摹); '
            '优先阀 充气活门 压力表 draft   |   悬空端口 %d: %s'
            % (len(intent['parts']), nnet, len(intent.get('taps') or []),
               len(intent['unknown']),
               len(dnames), ' '.join(dnames) if dnames else '无'))
    out.append('<text class="tb-t" x="%.1f" y="%.1f">%s</text>' % (x + 10, y + 21, row1))
    out.append('<text class="tb-t" x="%.1f" y="%.1f">%s</text>' % (x + 10, y + 40, row2))
    return out


def main():
    import sys as _sys
    argv = _sys.argv[1:]
    src = os.path.join(HERE, argv[0]) if argv else os.path.join(HERE, '1#系统.intent.yaml')
    lay_arg = argv[1] if len(argv) > 1 else '1#系统.layout.json'
    out_arg = argv[2] if len(argv) > 2 else None
    intent = load_yaml(src)
    with io.open(os.path.join(HERE, 'component-catalog.json'),
                 encoding='utf-8') as f:
        catalog = json.load(f)
    # 预检器钩子（#4/#8）：parse 后、布局前强制断言；ERROR 则报齐并退出，布局一行不执行。
    _tplp = preflight.default_template_path(src)
    _tpl = preflight.load_yaml_text(_tplp)[0] if _tplp else None
    rep = preflight.preflight(intent, catalog, io.open(src, encoding='utf-8').read(),
                              template=_tpl)
    if not rep['ok']:
        preflight.emit_preflight_failure(rep)
        sys.exit(1)
    with io.open(os.path.join(HERE, lay_arg), encoding='utf-8') as f:
        layout = json.load(f)
    s = Sheet(intent, layout, catalog)
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
    for lt, pts in s.polys:
        for run in s.split_h(pts, cross):
            segs.append(s.polyline(run, lt))

    # 吸油线型:连续 1.0 T 基线 + 周期性五斜杠组。
    # 不能用 stroke-dasharray——参考图中的基线是连续的,斜杠是独立标记。
    # 标记避开元件、文字、图例/图签及三通/跨线桥邻域。
    blocked = list(s.obstacles()) + list(s.textboxes)
    for key in ('legend', 'title_block'):
        q = layout.get(key)
        if q:
            blocked.append((q['x'] - layout.get('canvas_shift_x', 0), q['y'],
                            q['x'] + q['w'] - layout.get('canvas_shift_x', 0),
                            q['y'] + q['h']))
    blocked += [(x - 9, y - 9, x + 9, y + 9) for x, y in junc]
    blocked += [(x - 11, y - 11, x + 11, y + 11) for x, y, _lt in cross]

    # 装配框只把四条边设为障碍,不封锁框内区域；框内管线仍可标记,
    # 但斜杠不得穿过边界虚线,否则两套斜线语义叠在一起。
    pad = layout.get('group_padding', 14)
    for group in intent.get('groups') or []:
        mem = [layout['nodes'][m] for m in group['members'] if m in layout['nodes']]
        if not mem:
            continue
        gx0 = min(n['x'] for n in mem) - pad
        gy0 = min(n['y'] for n in mem) - pad
        gx1 = max(n['x'] + n['w'] for n in mem) + pad
        gy1 = max(n['y'] + n['h'] for n in mem) + pad
        blocked += [(gx0 - 3, gy0 - 3, gx1 + 3, gy0 + 3),
                    (gx0 - 3, gy1 - 3, gx1 + 3, gy1 + 3),
                    (gx0 - 3, gy0 - 3, gx0 + 3, gy1 + 3),
                    (gx1 - 3, gy0 - 3, gx1 + 3, gy1 + 3)]

    smarks, seen = [], set()
    S = float(layout.get('style', {}).get('suction_marker_S', 8.0))
    for pts, start_terminal, end_terminal in s.suction_runs:
        fresh = []
        for a, b in suction_markers(pts, blocked, S=S,
                                    start_terminal=start_terminal,
                                    end_terminal=end_terminal):
            key = tuple(round(v, 1) for p in (a, b) for v in p)
            if key in seen:
                continue
            seen.add(key)
            fresh.append('<line class="suc-mark" x1="%.1f" y1="%.1f" '
                         'x2="%.1f" y2="%.1f"/>' % (a[0], a[1], b[0], b[1]))
        # suction_markers 的契约是完整五根组；去重若打散组则整组丢弃,
        # 不允许输出 1–4 根的残缺标记。
        for j in range(0, len(fresh), 5):
            group = fresh[j:j + 5]
            if len(group) == 5:
                smarks.append('<g class="suc-mark-group">%s</g>' % ''.join(group))

    self_check(intent, layout, s, path_polys, tap_polys)

    W, H = layout['canvas']['width'], layout['canvas']['height']
    P = []
    P.append('<?xml version="1.0" encoding="UTF-8"?>')
    P.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" '
             'width="%d" height="%d">' % (W, H, W, H))
    T = layout.get('style', {}).get('base_line_width_T', 1.2)
    P.append('<style>%s</style>' % css(T))
    P.append('<rect x="0" y="0" width="%d" height="%d" fill="#ffffff"/>' % (W, H))
    # 左侧边界标记的说明文字向左伸出约 110px(anchor=end),
    # 若 extern.x=60 则文字被裁在画布外。整体右移让位。
    SHIFT = layout.get('canvas_shift_x', 0)
    P.append('<text class="banner" x="%d" y="26">CONCEPT - NOT FOR DESIGN RELEASE</text>' % 40)
    P.append('<text class="lbl" x="%d" y="44">1# 液压系统原理图  '
             '(由 1#系统.intent.yaml 生成,源清单 1#系统组件.json;'
             ' EDP/EMP/FWSOV provisional,油箱 draft,优先阀/充气活门/压力表 draft,'
             '不可用于工程放行)</text>' % 40)
    dmarks, dnames = s.dangling()
    body = []
    body.append('<g id="groups">%s</g>' % '\n'.join(s.groups()))
    body.append('<g id="lines">%s</g>' % '\n'.join(segs))
    body.append('<g id="suction-markers">%s</g>' % '\n'.join(smarks))
    body.append('<g id="bridges">%s</g>' % '\n'.join(s.bridge_arcs(cross)))
    body.append('<g id="junctions">%s</g>' % '\n'.join(
        '<circle class="jn" cx="%.1f" cy="%.1f" r="3"/>' % j for j in junc))
    body.append('<g id="externs">%s</g>' % '\n'.join(s.externs_marks()))
    body.append('<g id="symbols">%s</g>' % '\n'.join(s.symbols()))
    body.append('<g id="dangling">%s</g>' % '\n'.join(dmarks))
    body.append('<g id="labels">%s</g>' % '\n'.join(s.texts()))
    P.append('<g id="sheet" transform="translate(%d,0)">%s</g>' % (SHIFT, '\n'.join(body)))
    P.append('<g id="legend">%s</g>' % '\n'.join(legend(layout, T)))
    nnet = sum(len(p) - 1 for p in intent['paths'])
    P.append('<g id="title">%s</g>' % '\n'.join(title_block(layout, intent, nnet, dnames)))
    P.append('</svg>')

    outp = os.path.join(HERE, out_arg) if out_arg else os.path.join(HERE, '1#系统原理图.svg')
    with io.open(outp, 'w', encoding='utf-8') as f:
        f.write('\n'.join(P))
    print('wrote', outp)
    write_manifest(os.path.join(HERE, out_arg.replace('.svg','-topology.md')) if out_arg else os.path.join(HERE,'1#系统_topology.md'),
                   intent, layout, s, path_polys, tap_polys, dnames)
    print('nets=%d  segments=%d  junctions=%d  buses=%s'
          % (nnet, len(segs), len(junc), {k: len(v) for k, v in bus.items()}))
    for w in s.warn:
        print('WARN', w)




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
            for want, tok in (('out', p[k]), ('in', p[k + 1])):
                if tok.startswith('@'):
                    continue
                q = s.port(tok, want) if '.' not in tok else s.port(tok)
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
            a_bus, b_bus = a.startswith('@'), b.startswith('@')
            qa = bus_point(layout, a) if a_bus else s.port(a, 'out')
            qb = bus_point(layout, b) if b_bus else s.port(b, 'in')
            # 母线段按实端(端口侧)匹配折线取线型;母线侧坐标是占位 (x,0)。
            lt = [l for l, pts in path_polys
                  if (near_pt(pts[0], qa, 1.0) or near_pt(pts[-1], qa, 1.0)
                      or a_bus)
                  and (near_pt(pts[0], qb, 1.0) or near_pt(pts[-1], qb, 1.0)
                       or b_bus)
                  and (near_pt(pts[0], qa, 1.0) or near_pt(pts[0], qb, 1.0)
                       or near_pt(pts[-1], qa, 1.0) or near_pt(pts[-1], qb, 1.0))]
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
    L.append('8. 构图预算披露(validation-report.json):B1 交叉 0、B2 折返/单条 3、'
             'B4/B5/B6 达标;B3 油箱回油线(@RET->TANK.return_in,顶绕走廊 y=100)'
             '绕行比 2.373 > 1.5 走 WARN 通道——根因是油箱单一 return_in 端口'
             '(unknown: TANK-001-return-port-count-unconfirmed),'
             '确认多回油口后本线可拆直。V4 的"三通点不在母线"为图例示例点,非实体三通;'
             'V5 计 9 个悬空端口系校核器未计 taps 连通,图面实际标红 5 个'
             '(EDP-001.drive_shaft、EMP-001.elec_power、FSOV-001.command、'
             'QDP-001.outlet、QDR-001.outlet,后两者为断开位语义)。')
    L.append('')
    with io.open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(L))
    print('wrote', path)


def bus_point(layout, tok):
    x = layout['buses'][tok[1:]]['x']
    return (float(x), 0.0)


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
    # taps 行本地补扫(preflight.line_map 不扫 taps)
    lm['taps'] = []
    section = None
    with io.open(os.path.join(HERE, '1#系统.intent.yaml'),
                 encoding='utf-8') as f:
        for i, raw in enumerate(f.read().splitlines(), 1):
            if re.match(r'^\S', raw):
                section = raw.split(':')[0].strip()
                continue
            if section == 'taps' and re.match(r'^\s*-\s*\{', raw):
                lm['taps'].append(i)
    return lm


if __name__ == '__main__':
    main()
