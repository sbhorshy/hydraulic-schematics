# -*- coding: utf-8 -*-
"""组件 SVG 入库门禁:校核技术规范 6.4 第 1-12 条 + C13 信封阀方框基准
(symbol-library.md「信封阀分类与方框基准」,仅对声明 data-envelope-class
的符号生效)。

用法: python3 check_symbol.py <file.svg> [...]
      python3 check_symbol.py --all
无参时校核当前目录全部 *.svg,跳过非组件文件: _ 前缀基础设施件
(如 _template.svg)与 test-*/negative-*/预览/整图类文件名(与
sync_snapshot.py 的排除规则同一份口径)。
退出码 1 表示存在 ERROR。
"""
import fnmatch
import glob
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(HERE, 'component-catalog.json')
MEDIA = {'hydraulic', 'pneumatic', 'electrical', 'mechanical'}
FLOW = {'in', 'out', 'bidirectional', 'none'}
ANCH = {'left', 'right', 'up', 'down'}
STATUS = {'draft', 'provisional', 'annotated'}
ENVELOPE = 80.0   # 信封阀方框基准边长(viewBox 用户单位)
# 非组件文件口径,与 sync_snapshot.py LIB_GROUP.exclude 保持一致。
NON_COMPONENT = ('_*', 'test-*', 'stroke-symbol-preview*',
                 'hydraulic_system_schematic_diagram*', 'negative-*', '*preview*')


def load_catalog():
    if not os.path.exists(CATALOG):
        return {}
    with io.open(CATALOG, encoding='utf-8') as f:
        d = json.load(f)
    return {c['component_type']: c for c in d.get('components', [])}


def num(s):
    """'80.000000pt' -> (80.0, 'pt');  '80' -> (80.0, '')"""
    if s is None:
        return None, None
    m = re.match(r'^\s*(-?[\d.]+)\s*([a-z%]*)\s*$', s)
    if not m:
        return None, None
    return float(m.group(1)), m.group(2)


PATH_ARITY = {'M': 2, 'L': 2, 'H': 1, 'V': 1, 'C': 6, 'S': 4,
              'Q': 4, 'T': 2, 'A': 7, 'Z': 0}


def path_bbox(d):
    """粗算 path 数据包围盒 (minx, miny, maxx, maxy),不可解析返回 None。

    直线取端点;曲线把全部坐标对(含控制点)计入;A 只计入端点。
    信封方框是纯直线闭合路径,包围盒精确;曲线图元因控制点计入
    会略微胀大,不会误判成正方。
    """
    toks = re.findall(r'[MmLlHhVvCcSsQqTtAaZz]|-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?', d)
    xs, ys = [], []
    cx = cy = sx = sy = 0.0
    cmd = None
    i = 0
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in 'Zz':
                cx, cy = sx, sy
                continue
        up, rel = cmd.upper(), cmd.islower()
        n = PATH_ARITY[up]
        try:
            args = [float(v) for v in toks[i:i + n]]
        except ValueError:
            return None
        if len(args) < n:
            return None
        i += n
        if up == 'H':
            cx = (cx + args[0]) if rel else args[0]
            xs.append(cx)
        elif up == 'V':
            cy = (cy + args[0]) if rel else args[0]
            ys.append(cy)
        elif up == 'A':
            x, y = args[5], args[6]
            if rel:
                x, y = cx + x, cy + y
            xs.append(x)
            ys.append(y)
            cx, cy = x, y
        else:   # M/L/T/C/S/Q 及隐式重复坐标对
            pts = []
            for k in range(0, n, 2):
                x, y = args[k], args[k + 1]
                if rel:
                    x, y = cx + x, cy + y
                pts.append((x, y))
            xs += [p[0] for p in pts]
            ys += [p[1] for p in pts]
            cx, cy = pts[-1]
        if up == 'M':
            sx, sy = cx, cy
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def envelope_rects(root):
    """symbol 组内描边闭合矩形图元的 (w, h) 列表。

    候选判据:有效 fill 为 none(信封是描边;实心箭头等指示件排除)、
    无 dasharray(虚线框是装配/先导界线,不是信封)、闭合(path 以 Z
    收尾 / rect / polygon)、边长 >= 8。不做方形预筛——single 信封
    的"必须是正方"交给尺寸校核报出,报错才带真实尺寸。
    """
    out = []
    for g in [x for x in root.iter() if x.get('id') == 'symbol']:
        stack = [(c, g.get('fill'), g.get('stroke-dasharray')) for c in g]
        while stack:
            el, inh_f, inh_d = stack.pop()
            fill = el.get('fill', inh_f)
            dash = el.get('stroke-dasharray', inh_d)
            tag = el.tag.split('}')[-1]
            if tag == 'g':
                stack += [(c, fill, dash) for c in el]
                continue
            if tag not in ('path', 'rect', 'polygon'):
                continue
            if (fill or 'black').strip().lower() != 'none':
                continue
            if dash:
                continue
            bb, closed = None, tag in ('rect', 'polygon')
            if tag == 'path':
                dd = el.get('d') or ''
                closed = bool(re.search(r'[Zz]\s*$', dd.strip()))
                bb = path_bbox(dd)
            elif tag == 'rect':
                x = float(el.get('x') or 0)
                y = float(el.get('y') or 0)
                bb = (x, y, x + float(el.get('width')), y + float(el.get('height')))
            else:
                v = [float(t) for t in re.findall(
                    r'-?(?:\d+\.?\d*|\.\d+)', el.get('points') or '')]
                if len(v) >= 4:
                    bb = (min(v[0::2]), min(v[1::2]), max(v[0::2]), max(v[1::2]))
            if bb is None or not closed:
                continue
            w, h = bb[2] - bb[0], bb[3] - bb[1]
            if w >= 8 and h >= 8:
                out.append((round(w, 2), round(h, 2)))
    return out


def check(path, cat):
    """返回 (errors, warns)。"""
    E, W = [], []
    raw = io.open(path, encoding='utf-8', errors='replace').read()

    # ---- 1. XML 可解析 ----
    try:
        root = ET.fromstring(raw.encode('utf-8'))
    except Exception as ex:
        return ['C1 XML 不可解析: %s' % ex], []

    # ---- 2. ID 唯一 ----
    ids = [e.get('id') for e in root.iter() if e.get('id')]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        E.append('C2 重复 id: %s (SVG 非法,getElementById 只取到第一个)' % ' '.join(dup))

    # ---- viewBox ----
    vb = root.get('viewBox')
    if not vb:
        E.append('C6 缺 viewBox')
        return E, W
    p = [float(v) for v in vb.replace(',', ' ').split()]
    # viewBox 的原点不一定是 0,0。"20 10 218 564" 的可见范围是
    # x 20..238, y 10..574。早先版本假定原点为零,把合法的偏移
    # viewBox 全判成越界。
    VX, VY, VW, VH = p[0], p[1], p[2], p[3]
    XL, XR, YT, YB = VX, VX + VW, VY, VY + VH

    # ---- 9. width/height 与 viewBox 一致且无单位 ----
    for att, want in (('width', VW), ('height', VH)):
        v, unit = num(root.get(att))
        if v is None:
            W.append('C9 缺 %s (渲染器无法确定缩放)' % att)
        else:
            if unit:
                E.append('C9 %s 带单位 "%s":pt/px 混用会使端口与图形分离' % (att, unit))
            if abs(v - want) > 0.01:
                E.append('C9 %s=%g 与 viewBox 的 %g 不一致' % (att, v, want))

    ctype = root.get('data-component-type')
    if not ctype:
        # 整张原理图/预览页不是组件,不适用本章。判据:根级无
        # data-component-type,但内部存在多个带该属性的子组,或存在
        # 网络/图签一类整图标志。以 SKIP 区分,不计入 ERROR。
        inner = [g for g in root.iter() if g.get('data-component-type')]
        marks = [g.get('id') or '' for g in root.iter()]
        if len(inner) > 1 or any(
                m.startswith(('NET-', 'component-', 'sheet', 'title')) for m in marks):
            return ['SKIP 整图或预览页,非单组件'], []
        E.append('C3 缺 data-component-type')

    # ---- 8. 描边几何 ----
    form = root.get('data-symbol-form')
    if form != 'stroke_geometry':
        E.append('C8 data-symbol-form=%r,须为 stroke_geometry' % form)
    # 只查 symbol 组内。connection-points 的红点是辅助标记,本就该填充。
    # 判据不是"有没有 fill",而是"填充图元是否声明了 stroke=none"——
    # 描摹轮廓的特征恰是 fill=#000000 stroke=none,与实心箭头无法用属性区分。
    # 故实心指示图元必须显式列入白名单,不能靠 stroke=none 免检。
    sym = [g for g in root.iter() if g.get('id') == 'symbol']
    traced = []
    for g in sym:
        for e in g.iter():
            if e.tag.split('}')[-1] == 'text':
                continue    # 文字须填充才可见,不是描摹轮廓(如用户框名槽)
            f = (e.get('fill') or '').strip().lower()
            if not f or f == 'none':
                continue
            d = e.get('d') or ''
            # 实心箭头/三角:路径短(<=4 个顶点)且闭合。描摹轮廓远长于此。
            verts = len(re.findall(r'[MLHVmlhv]', d))
            if e.tag.split('}')[-1] == 'path' and verts <= 4 and d.strip().rstrip('Zz') != d.strip():
                continue
            # polygon 箭头/三角:坐标对<=4 且显式 stroke="none"(§6.4-8
            # "实心箭头、三角等指示性图元除外,须显式 stroke=none"。
            # 描摹轮廓不会是短小 polygon,误放行风险可忽略)。
            if e.tag.split('}')[-1] == 'polygon':
                npts = len(re.findall(r'-?[\d.]+', e.get('points') or '')) // 2
                if npts <= 4 and (e.get('stroke') or '').strip().lower() == 'none':
                    continue
            traced.append('%s(fill=%s, %d 顶点)' % (e.tag.split('}')[-1], f, verts))
    if traced:
        E.append('C8 symbol 组内存在填充图元,疑为描摹轮廓: %s' % ' '.join(traced))

    # ---- 11. status / source-ref ----
    st = root.get('data-symbol-status')
    if st is not None and st not in STATUS:
        E.append('C11 data-symbol-status=%r 不在枚举 %s' % (st, sorted(STATUS)))
    ref = root.get('data-symbol-source-ref') or ''
    if st != 'annotated' or ref.startswith('NONE') or ref.startswith('PENDING'):
        W.append('C11 非正式出图件 (status=%s, source-ref=%s)' % (st, ref or '缺'))

    # ---- 端口组 ----
    cp = [g for g in root.iter() if g.get('id') == 'connection-points']
    if not cp:
        E.append('C4 缺 connection-points 组')
        return E, W
    if len(cp) > 1:
        E.append('C4 connection-points 组不唯一 (%d 个)' % len(cp))

    ports = {}
    for c in cp[0]:
        pid = c.get('data-port-id')
        if not pid:
            E.append('C4 端口缺 data-port-id: id=%s' % c.get('id'))
            continue
        if pid in ports:
            E.append('C4 端口 data-port-id 重复: %s' % pid)
        cx, ux = num(c.get('cx'))
        cy, uy = num(c.get('cy'))
        if cx is None or cy is None:
            E.append('C6 端口 %s 缺 cx/cy' % pid)
            continue
        if ux or uy:
            E.append('C9 端口 %s 坐标带单位' % pid)
        ports[pid] = (cx, cy)

        # ---- 6. 坐标在 viewBox 内 ----
        if not (XL - 0.01 <= cx <= XR + 0.01 and YT - 0.01 <= cy <= YB + 0.01):
            E.append('C6 端口 %s (%g,%g) 超出 viewBox x %g..%g y %g..%g'
                     % (pid, cx, cy, XL, XR, YT, YB))
        # ---- 10. 坐标在边界线上 ----
        elif not (abs(cx - XL) < 0.01 or abs(cx - XR) < 0.01
                  or abs(cy - YT) < 0.01 or abs(cy - YB) < 0.01):
            E.append('C10 端口 %s (%g,%g) 在图形内部,不在 viewBox 边界:'
                     '走线会穿过符号本体' % (pid, cx, cy))

        # ---- 枚举 ----
        for att, allowed in (('data-medium', MEDIA),
                             ('data-flow-capability', FLOW),
                             ('data-anchor-direction', ANCH)):
            v = c.get(att)
            if v is None:
                E.append('C4 端口 %s 缺 %s' % (pid, att))
            elif v not in allowed:
                E.append('C4 端口 %s 的 %s=%r 不在枚举' % (pid, att, v))
        if not c.get('data-port-role'):
            E.append('C4 端口 %s 缺 data-port-role' % pid)

    # ---- 4 / 5. 与目录双向一致 ----
    if ctype and ctype in cat:
        want = {q['id'] for q in cat[ctype]['ports']}
        got = set(ports)
        for m in sorted(want - got):
            E.append('C4 目录声明的端口在 SVG 中缺失: %s' % m)
        for m in sorted(got - want):
            E.append('C5 SVG 存在目录未声明的端口: %s' % m)
        for q in cat[ctype]['ports']:
            sid = q.get('svg_element_id')
            if sid and sid not in ids:
                W.append('C4 目录 svg_element_id=%s 在 SVG 中不存在' % sid)
    elif ctype:
        W.append('C3 data-component-type=%s 不在目录中' % ctype)

    # ---- 12. 未确认项 ----
    if re.search(r'未确认项|PENDING|APPROXIMATE|待确认', raw):
        W.append('C12 注释含未确认项,须在引用它的 L0 文件 unknown 中登记')

    # ---- 13. 方框本体基准(只约束声明了 data-envelope-class 的符号;
    #       豁免清单见 symbol-library.md「方框本体基准」) ----
    env = root.get('data-envelope-class')
    if env:
        if env not in ('single', 'multi'):
            E.append('C13 data-envelope-class=%r 不在枚举 single/multi' % env)
        elif env == 'single':
            rects = envelope_rects(root)
            big = [r for r in rects if r[0] >= 60 or r[1] >= 60]
            body = [r for r in big
                    if abs(r[0] - ENVELOPE) <= 0.5 and abs(r[1] - ENVELOPE) <= 0.5]
            if len(body) != 1:
                E.append('C13 single 本体须恰有一个 %g×%g 闭合方框,实得 %d 个;全部候选: %s'
                         % (ENVELOPE, ENVELOPE, len(body), rects))
            elif len(big) != 1:
                E.append('C13 附件方框达本体级(边>=60),疑第二本体: %s' % big)
        else:
            rects = envelope_rects(root)
            bodies = [r for r in rects if r[0] >= 60 or r[1] >= 60]
            # 两种合规画法:各格独立闭合方框(每格 80x80),或一体包络
            # (短边 80,长边为 80 的整数倍,分隔线自画)。
            for w, h in bodies:
                short, long = min(w, h), max(w, h)
                n = long / ENVELOPE
                if (abs(short - ENVELOPE) > 0.5 or n < 0.99
                        or abs(n - round(n)) > 0.01):
                    E.append('C13 multi 本体方框 %g×%g 不合基准'
                             '(短边须 80,长边须为 80 的整数倍)' % (w, h))
            if not bodies:
                E.append('C13 multi 未检出任何本体级方框: %s' % rects)
    return E, W


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        args = sorted(
            f for f in glob.glob(os.path.join(HERE, '*.svg'))
            if not any(fnmatch.fnmatch(os.path.basename(f), p) for p in NON_COMPONENT))
    cat = load_catalog()
    nerr = nfile = 0
    ready = []
    for f in args:
        r = check(f, cat)
        E, W = r[0], r[1]
        nfile += 1
        name = os.path.basename(f)
        if E and E[0].startswith('SKIP'):
            nfile -= 1
            continue
        if E:
            nerr += 1
            print('\n[ERROR] %s' % name)
            for e in E:
                print('   x %s' % e)
            for w in W:
                print('   ! %s' % w)
        elif W:
            print('\n[WARN ] %s' % name)
            for w in W:
                print('   ! %s' % w)
        else:
            ready.append(name)
            print('\n[PASS ] %s  <- 可正式出图' % name)
    print('\n---- %d 个文件, %d 个有 ERROR, %d 个可正式出图 ----'
          % (nfile, nerr, len(ready)))
    return 1 if nerr else 0


if __name__ == '__main__':
    sys.exit(main())
