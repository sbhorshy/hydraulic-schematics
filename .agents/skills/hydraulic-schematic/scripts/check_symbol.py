# -*- coding: utf-8 -*-
"""组件 SVG 入库门禁:校核技术规范 6.4 第 1-12 条 + C13 信封阀方框基准
(symbol-library.md「方框本体基准」,仅对声明 data-envelope-class
的符号生效)。

规范源归位(#31):本脚本随 skill `scripts/` 携带,与 check_library.py
同款锚定——默认库与 catalog 解析自脚本自身位置
(<skill>/assets/component-library/),任意 cwd 调用结果一致;工作区
旧副本退役为薄兼容入口(1#系统原理图/check_symbol.py 透传本脚本)。

用法: python3 check_symbol.py <file.svg> [...]
      python3 check_symbol.py --all                 # 全量扫默认库(同无参)
      python3 check_symbol.py --lib DIR [--catalog PATH] [...]   # 沙箱/测试
全量扫描跳过非组件文件: _ 前缀基础设施件(如 _template.svg)与
test-*/negative-*/预览/整图类文件名(沿用归档 sync_snapshot.py 的
排除口径,工具已随 #20 规范源归档退役)。
fail-closed: 显式文件不存在、库目录缺失或无 SVG、catalog 缺失或
畸形(不可读/非法 JSON/顶层或 components 结构不符/components 为
空/component_type 缺失·空白·重复/ports 非列表/端口 id 重复)、
未知选项,均不得空转放过(退出码 1/2)。坏 catalog 会让 C4/C5
端口对账静默消失,宁可整门禁拦下。
退出码 1 表示存在 ERROR;WARN(C11/C12 等)只披露不计错,不构成
工程签认。合法 catalog 下类型未登记的存量符号仍按 C3 WARN 披露。
"""
import argparse
import fnmatch
import glob
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
LIB = os.path.join(SKILL, 'assets', 'component-library')
MEDIA = {'hydraulic', 'pneumatic', 'electrical', 'mechanical'}
FLOW = {'in', 'out', 'bidirectional', 'none'}
ANCH = {'left', 'right', 'up', 'down'}
STATUS = {'draft', 'provisional', 'annotated'}
ENVELOPE = 80.0   # 信封阀方框基准边长(viewBox 用户单位)
# 非组件文件口径,沿用归档前 sync_snapshot.py LIB_GROUP.exclude。
NON_COMPONENT = ('_*', 'test-*', 'stroke-symbol-preview*',
                 'hydraulic_system_schematic_diagram*', 'negative-*', '*preview*')


class CatalogError(Exception):
    """catalog 缺失/不可读/结构不合法——门禁必须拦下(fail-closed)。"""


def load_catalog(path):
    """读入并做结构层校验;合法返回 {component_type: entry},
    任何缺件/坏件抛 CatalogError(fail-closed 由 main 裁决)。

    只做结构校验(键存在、类型对、id 唯一),不新增水力语义。
    空 components 按坏 catalog 拦:它会让 C4/C5 端口对账静默消失
    (整门禁形同虚设),不是"暂无组件可查"的合法状态。
    """
    if not os.path.exists(path):
        raise CatalogError('catalog 不存在: %s '
                           '(端口对账 C4/C5 无从执行,fail-closed)' % path)
    try:
        with io.open(path, encoding='utf-8') as f:
            d = json.load(f)
    except (IOError, OSError) as ex:
        raise CatalogError('catalog 不可读: %s (%s)' % (path, ex))
    except UnicodeDecodeError as ex:
        raise CatalogError('catalog 非 UTF-8 文本: %s (%s)' % (path, ex))
    except ValueError as ex:
        raise CatalogError('catalog 不是合法 JSON: %s (%s)' % (path, ex))
    if not isinstance(d, dict):
        raise CatalogError('catalog 顶层须为 JSON 对象,实得 %s: %s'
                           % (type(d).__name__, path))
    if 'components' not in d:
        raise CatalogError("catalog 缺 'components' 键(空对象同拦): %s" % path)
    comps = d['components']
    if not isinstance(comps, list):
        raise CatalogError("catalog 'components' 须为列表,实得 %s: %s"
                           % (type(comps).__name__, path))
    if not comps:
        raise CatalogError("catalog 'components' 为空列表: %s\n"
                           '   空目录会让 C4/C5 端口对账静默消失,按坏 catalog 拦截;'
                           '  若 --catalog 指错了文件,改指到真实 catalog 再跑' % path)
    cat = {}
    for i, c in enumerate(comps):
        where = 'components[%d]' % i
        if not isinstance(c, dict):
            raise CatalogError('%s 须为对象,实得 %s: %s'
                               % (where, type(c).__name__, path))
        ct = c.get('component_type')
        if not isinstance(ct, str) or not ct.strip():
            raise CatalogError('%s 的 component_type 缺失或空白: %s'
                               % (where, path))
        if ct in cat:
            raise CatalogError('component_type=%r 重复登记(%s 与前文冲突): %s'
                               % (ct, where, path))
        ports = c.get('ports')
        if not isinstance(ports, list):
            raise CatalogError("%s (%s) 的 'ports' 须为列表,实得 %s: %s"
                               % (where, ct, type(ports).__name__, path))
        seen = set()
        for q in ports:
            if not isinstance(q, dict):
                raise CatalogError('%s (%s) 的 ports 项须为对象,实得 %s: %s'
                                   % (where, ct, type(q).__name__, path))
            pid = q.get('id')
            if not isinstance(pid, str) or not pid.strip():
                raise CatalogError('%s (%s) 的 ports 项缺非空 id: %s'
                                   % (where, ct, path))
            if pid in seen:
                raise CatalogError('%s (%s) 端口 id=%r 重复: %s'
                                   % (where, ct, pid, path))
            seen.add(pid)
        cat[ct] = c
    return cat


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
            if e.tag.split('}')[-1] == 'text':
                continue  # 文字为排版件非描摹轮廓(hydraulic_user 名槽占位文本)
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
    if ctype and cat is not None and ctype in cat:
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
        # assembly=装配级方框,框随内容,不守 80 基准,无方框校核
        # (用户签认 2026-09-29:priority-valve 本体 162x129 native 属此类)。
        if env not in ('single', 'multi', 'assembly'):
            E.append('C13 data-envelope-class=%r 不在枚举 single/multi/assembly' % env)
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
        elif env == 'multi':
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


def scan_library(lib):
    """默认全量:库目录内非组件口径外的全部 *.svg(排序稳定)。"""
    if not os.path.isdir(lib):
        return None
    return sorted(
        f for f in glob.glob(os.path.join(lib, '*.svg'))
        if not any(fnmatch.fnmatch(os.path.basename(f), p) for p in NON_COMPONENT))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description='组件 SVG 入库门禁(技术规范 6.4 第 1-12 条 + C13 方框基准)')
    ap.add_argument('files', nargs='*',
                    help='待检 SVG(缺省与 --all 同:全量扫默认库)')
    ap.add_argument('--all', action='store_true',
                    help='全量扫描默认库(锚定 skill 自带 assets/component-library)')
    ap.add_argument('--lib', default=LIB,
                    help='库目录(默认 skill 自带;沙箱/测试用)')
    ap.add_argument('--catalog', default=None,
                    help='catalog 路径(默认 <lib>/component-catalog.json)')
    a = ap.parse_args(argv)

    if a.all and a.files:
        # 同时给出曾静默丢弃显式文件(--all 分支不看 files),拒绝。
        ap.error('--all 与显式文件互斥:同时给出会静默丢弃显式文件。'
                 '全量扫描只传 --all;查指定文件时不传 --all')

    catalog_path = a.catalog or os.path.join(a.lib, 'component-catalog.json')

    if a.all or not a.files:
        files = scan_library(a.lib)
        if files is None:
            print('[ERROR] 库目录不存在: %s (门禁按脚本自身位置锚定 '
                  '<skill>/assets/component-library/)' % a.lib)
            return 1
        if not files:
            print('[ERROR] 库目录内无可检 SVG(非组件口径过滤后为空): %s' % a.lib)
            return 1
    else:
        files = list(a.files)

    try:
        cat = load_catalog(catalog_path)
    except CatalogError as ex:
        print('[ERROR] %s' % ex)
        return 1

    nerr = nfile = 0
    ready = []
    for f in files:
        if not os.path.isfile(f):
            nfile += 1
            nerr += 1
            print('\n[ERROR] %s\n   x 文件不存在(或不是常规文件): %s'
                  % (os.path.basename(f), f))
            continue
        E, W = check(f, cat)
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
