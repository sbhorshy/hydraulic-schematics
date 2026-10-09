# -*- coding: utf-8 -*-
"""装配单行图自适应间距解析器(原型,#38 后续)。

布局引擎 layout_engine.py 是母线驱动的整机/系统布局器(硬性要求油箱等,
R1 规则对无母线装配图直接 StopIteration),装配展开图的间距自适应由本脚本
在原型层补位:渲染器仍不做自动布局(不变式 3),本脚本在渲染前解析 layout,
把链上坐标从语义 knob 推导出来并写回。

自适应规则(全部可经 --param 覆写):
  · 符号足迹(w/h)与端口偏移从符号 SVG 实读(viewBox + connection-points,
    rot 感知)——符号换版(如 v4.2 80x112->80x158)后重跑即自动对齐主路;
  · 链上节点按 intent paths 顺序左->右递进,盒距 = max(B5_MIN, 标签净空所需):
    后一节点带 below 标签时,须使两组件标签文字盒(B7_CLEAR=6 净空,宽按
    validate_sheet V12 同款公式估算)互不侵入;
  · 标签净空所需盒距 > GAP_SOFT_CAP 时,改取 B5_MIN 并把后一节点标签翻到
    above(文字带错层),避免为迁就标签无限拉远组件;
  · 节点 y = RUN_Y - 主路进口端口偏移(rot 感知),主路恒为水平直线;
  · 边界 extern 挂链两端(STUB_IN/STUB_OUT),y = RUN_Y。

用法: python auto_space.py [工作目录] [--param KEY=VAL]
只改 layout.json 的 nodes(x/y/w/h/rot 保留用户 rot)/externs(x/y),
labels/legend/title_block/canvas 等展示键一概不动。
"""
import io
import json
import math
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
NS = '{http://www.w3.org/2000/svg}'
SKILL_LIB = os.path.normpath(os.path.join(HERE, '..', '..', '.agents',
                                          'skills', 'hydraulic-schematic',
                                          'assets', 'component-library'))
KNOBS = dict(
    RUN_Y=300,          # 主路高度(构图选择,不属于链间距)
    STUB_IN=170,        # 左边界->首元件引出段
    STUB_OUT=110,       # 末元件->右边界引出段
    B5_MIN=40,          # 节点盒最小净距(rendering-rules B5 下限)
    GAP_SOFT_CAP=80,    # 盒距软上限:标签净空超过它就翻标签而非拉远
    B7_CLEAR=6,         # 标签文字盒间净空(B7 同口径)
)


def fs_w(txt):
    """文字宽估算,V12 同款公式(CJK=字号,ASCII=0.55 字号),字号 10.5。"""
    return sum(10.5 if ord(ch) > 0x2E80 else 10.5 * 0.55 for ch in txt)


def load_symbol(path):
    """返回 (viewBox[w,h], {port_id: (cx, cy)})。"""
    r = ET.parse(path).getroot()
    vb = [float(v) for v in r.get('viewBox').strip().split()]
    ports = {}
    for g in r.iter(NS + 'g'):
        if (g.get('id') or '') != 'connection-points':
            continue
        for c in g:
            pid = c.get('data-port-id')
            if pid:
                ports[pid] = (float(c.get('cx')), float(c.get('cy')))
    return vb[2:], vb[:2], ports


def port_offset(ports, pid, rot, vw, vh):
    """端口在节点盒内的偏移(rot 感知,与渲染器 place/校验器同一映射)。"""
    lx, ly = ports[pid]
    k = 1.0                                   # 原大:足迹=符号库事实
    lx, ly = (lx - 0) * k, (ly - 0) * k
    W, H = vw * k, vh * k
    rr = int(rot) % 360
    if rr == 90:
        lx, ly = H - ly, lx
    elif rr == 180:
        lx, ly = W - lx, H - ly
    elif rr == 270:
        lx, ly = ly, W - lx
    return lx, ly


def main():
    wd = sys.argv[1] if not str(sys.argv[1]).startswith('--') else HERE
    for a in sys.argv[1:]:
        if a.startswith('--param'):
            k, v = a.split('=', 1)[0][8:], a.split('=', 1)[1]
            KNOBS[k] = type(KNOBS.get(k, 0))(v)
    lay_p = os.path.join(wd, 'case_drain_filter.layout.json')
    int_p = os.path.join(wd, 'case_drain_filter.intent.yaml')
    L = json.load(io.open(lay_p, encoding='utf-8'))
    from ruamel.yaml import YAML
    intent = YAML(typ='safe', pure=True).load(io.open(int_p, encoding='utf-8'))

    cat = json.load(io.open(os.path.join(SKILL_LIB, 'component-catalog.json'),
                            encoding='utf-8'))
    types = {c['component_type']: c for c in cat['components']}

    def sym_path(ref):
        for p in (os.path.join(wd, ref),
                  os.path.join(SKILL_LIB, os.path.basename(ref))):
            if os.path.isfile(p):
                return p
        raise SystemExit('符号找不到: %s' % ref)

    # 链顺序:取第一条 path 的非边界 token(装配单行图约定单 path)
    toks = [t for t in intent['paths'][0] if not str(t).startswith('@')]
    chain = []
    for t in toks:
        inst = str(t).split('.')[0]
        if inst in intent['parts'] and (not chain or chain[-1] != inst):
            chain.append(inst)
    externs = [e for e in intent['paths'][0]
               if str(e).split('.')[0] in (intent.get('extern') or {})]

    # 逐节点实读足迹与主路进口偏移,推导 y
    foot = {}
    for inst in chain:
        nd = L['nodes'][inst]
        vw, _vo, ports = load_symbol(sym_path(nd['symbol']))
        ct = types[intent['parts'][inst]]
        pid_in = ct['main_path']['in']
        rot = int(nd.get('rot', 0))
        ox_in, oy_in = port_offset(ports, pid_in, rot, vw[0], vw[1])
        foot[inst] = dict(vw=vw, ports=ports, rot=rot,
                          w=vw[0], h=vw[1], oy_in=oy_in)
        nd['w'], nd['h'] = vw[0], vw[1]
        nd['y'] = KNOBS['RUN_Y'] - oy_in

    # x 递进:gap = max(B5_MIN, 标签净空所需);超软上限则翻标签
    RUN_Y = KNOBS['RUN_Y']

    def label_half(inst):
        nd = L['nodes'][inst]
        if L['label_pos'].get(inst, 'below') not in ('below', 'above'):
            return None                      # right 标签不占链向净空
        return max(fs_w(ln) for ln in
                   L['labels'].get(inst, inst).split('\n')) / 2.0

    x = L['externs'][externs[0]]['x'] + KNOBS['STUB_IN'] if externs else 60
    prev = None
    for inst in chain:
        nd = L['nodes'][inst]
        if prev is None:
            nd['x'] = int(math.ceil(x))
        else:
            ha = label_half(prev)
            hb = label_half(inst)
            ax1 = L['nodes'][prev]['x'] + L['nodes'][prev]['w']
            acx = ax1 - L['nodes'][prev]['w'] / 2.0
            gap = KNOBS['B5_MIN']
            if ha is not None and hb is not None:
                need_x0 = acx + ha + KNOBS['B7_CLEAR'] + hb
                gap = max(gap, int(math.ceil(need_x0 - nd['w'] / 2.0 - ax1)))
                if gap > KNOBS['GAP_SOFT_CAP']:
                    gap = KNOBS['B5_MIN']
                    L['label_pos'][inst] = 'above'   # 文字带错层,不为标签拉远
                else:
                    L['label_pos'][inst] = 'below'   # 规则裁决,不继承手工状态
            nd['x'] = L['nodes'][prev]['x'] + L['nodes'][prev]['w'] + gap
        prev = inst

    if externs:
        last = L['nodes'][chain[-1]]
        L['externs'][externs[-1]]['x'] = last['x'] + last['w'] + KNOBS['STUB_OUT']
        L['externs'][externs[-1]]['y'] = RUN_Y
        L['externs'][externs[0]]['y'] = RUN_Y

    io.open(lay_p, 'w', encoding='utf-8', newline='\n').write(
        json.dumps(L, ensure_ascii=False, indent=2) + '\n')
    for inst in chain:
        nd = L['nodes'][inst]
        print('%s x=%s y=%s (%sx%s rot=%s) label=%s' % (
            inst, nd['x'], nd['y'], nd['w'], nd['h'], nd.get('rot', 0),
            L['label_pos'].get(inst, 'below')))
    print('externs:', {k: (v['x'], v['y']) for k, v in L['externs'].items()})


if __name__ == '__main__':
    main()
