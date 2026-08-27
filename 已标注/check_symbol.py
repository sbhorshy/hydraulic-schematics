# -*- coding: utf-8 -*-
"""组件 SVG 入库门禁:校核技术规范 6.4 第 1-12 条。

用法: python3 check_symbol.py <file.svg> [...]
      python3 check_symbol.py --all
无参时校核当前目录全部 *.svg。
退出码 1 表示存在 ERROR。
"""
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
            f = (e.get('fill') or '').strip().lower()
            if not f or f == 'none':
                continue
            d = e.get('d') or ''
            # 实心箭头/三角:路径短(<=4 个顶点)且闭合。描摹轮廓远长于此。
            verts = len(re.findall(r'[MLHVmlhv]', d))
            if e.tag.split('}')[-1] == 'path' and verts <= 4 and d.strip().rstrip('Zz') != d.strip():
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
    return E, W


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    if not args:
        args = sorted(glob.glob(os.path.join(HERE, '*.svg')))
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
