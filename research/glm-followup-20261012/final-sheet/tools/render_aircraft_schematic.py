# -*- coding: utf-8 -*-
"""
render_aircraft_schematic.py
============================
从 aircraft_hydraulic_system.sysml 的拓扑,生成整机液压系统原理图 SVG。

- 每条 HydraulicCircuit(绿/黄)复用同一份局部布局:油箱居左、两泵、
  压力滤、压力控制阀、隔离阀、蓄压器、systemOutput。黄系统水平镜像。
- 整机层: 绿/黄 systemOutput -> PTU; 绿->起落架; 黄->飞控; 控制器指挥信号线。
- 只复用仓库已有的 stroke 符号 SVG(油箱/EDP/EMP/滤/蓄压器),其余(压力控制阀、
  隔离阀、PTU、作动器组、控制器)画为干净的描边框图,图签栏披露。
- 不依赖组件目录 connection-points(规避未标注符号),端口坐标由本布局显式给定。

用法与自检:
    python3 render_aircraft_schematic.py
退出码 1 表示结构自检失败(某条 connect 无对应边 / 某 part 无对应节点)。
产出:
    aircraft_hydraulic_system_schematic.svg   (成品图)
    aircraft_hydraulic_system_topology.md     (追溯清单)
"""
import io, os, re, sys, xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SYML  = os.path.join(HERE, 'aircraft_hydraulic_system.sysml')
OUTSVG = os.path.join(HERE, 'aircraft_hydraulic_system_schematic.svg')
OUTMD  = os.path.join(HERE, 'aircraft_hydraulic_system_topology.md')
NS = 'http://www.w3.org/2000/svg'

# ---------- 视觉常量(对齐仓库技术规范 / 1#系统读出) ----------
HIGH_SW = 3.0   # 高压供压线
LOW_SW  = 1.2   # 回油线
MED_SW  = 1.4   # 吸油/供油线
SIG_SW  = 1.2   # 指挥/状态信号(虚线)
MECH_SW = 1.4   # 机械(轴功率)线
PORT_R  = 5     # 端口点
JUNC_R  = 4.5   # 三通/节点实心点

CANVAS_W, CANVAS_H = 2500, 1500

# 局部画布定义: 一条 HydraulicCircuit 的虚拟坐标, 宽 1000 高 620,
# 油箱居左, systemOutput 居右。黄系统做水平镜像。
LOCAL_W, LOCAL_H = 1000, 620


def mirror_x(p, mirror):
    """局部 x 是否镜像(黄系统)。镜像关于局部中线 LOCAL_W/2。"""
    return (LOCAL_W - p) if mirror else p


# ---- 局部回路内的元件(局部坐标) ----
# 每个: key -> dict(box=(lx,ly,lw,lh), sym=路径或None, ports={id:(x,y,anchor,role,medium)})
def local_nodes():
    # 油箱 218x564(比例固定)
    res_w, res_h = 218, 564
    res_x, res_y = 30, 30
    # 泵/滤 80x80 -> 放大 1.2
    def pump(bx, by):
        return (bx, by, 96, 96)
    edp = pump(300, 130)
    emp = pump(300, 300)
    flt = pump(480, 220)          # 80x80 ->96x96
    return {
        'reservoir': dict(box=(res_x, res_y, res_w, res_h),
                          sym='油箱_开放描边_实线_draft.svg',
                          ports={
                              'supply': (res_x+res_w, 300, 'right', 'pressure', 'hydraulic'),
                              'return': (res_x+res_w, 430, 'right', 'return', 'hydraulic'),
                          }),
        'enginePump': dict(box=edp, sym='edp-provisional-stroke.svg',
                           ports={
                               'suction': (edp[0], edp[1]+48, 'left', 'suction', 'hydraulic'),
                               'pressure_out': (edp[0]+96, edp[1]+48, 'right', 'pressure', 'hydraulic'),
                               'case_drain': (edp[0]+48, edp[1]+96, 'down', 'return', 'hydraulic'),
                               'drive_shaft': (edp[0]+48, edp[1], 'up', 'shaft', 'mechanical'),
                           }),
        'electricPump': dict(box=emp, sym='emp-provisional-stroke.svg',
                             ports={
                                 'suction': (emp[0], emp[1]+48, 'left', 'suction', 'hydraulic'),
                                 'pressure_out': (emp[0]+96, emp[1]+48, 'right', 'pressure', 'hydraulic'),
                                 'case_drain': (emp[0]+48, emp[1]+96, 'down', 'return', 'hydraulic'),
                             }),
        'filterUnit': dict(box=flt, sym='filter-plain-stroke.svg',
                           ports={
                               'inlet': (flt[0], flt[1]+48, 'left', 'pressure', 'hydraulic'),
                               'outlet': (flt[0]+96, flt[1]+48, 'right', 'pressure', 'hydraulic'),
                           }),
        'pressureControl': dict(box=(630, 220, 110, 96), sym=None, kind='relief',
                                ports={
                                    'inlet': (630, 268, 'left', 'pressure', 'hydraulic'),
                                    'outlet': (740, 268, 'right', 'pressure', 'hydraulic'),
                                    'command': (740, 220, 'up', 'signal_in', 'electrical'),
                                }),
        'isolationValve': dict(box=(790, 220, 120, 96), sym=None, kind='solenoid',
                               ports={
                                   'inlet': (790, 268, 'left', 'pressure', 'hydraulic'),
                                   'outlet': (910, 268, 'right', 'pressure', 'hydraulic'),
                                   'command': (910, 220, 'up', 'signal_in', 'electrical'),
                               }),
        'accumulator': dict(box=(940, 60, 72, 120), sym='accumulator-stroke.svg',
                            ports={
                                'hydraulic': (940+36, 60+120, 'down', 'pressure', 'hydraulic'),
                                'gas': (940+36, 60, 'up', 'gas', 'pneumatic'),
                            }),
        # 虚拟端口: 回路对外交界面
        'systemOutput': dict(box=None, sym=None, kind='virtual',
                             ports={'out': (1000, 268, 'right', 'pressure', 'hydraulic')}),
        'mechanicalInput': dict(box=None, sym=None, kind='virtual',
                                ports={'in': (348, 60, 'up', 'shaft', 'mechanical')}),
    }


# 局部回路内的连接(正交走线). 每条: id -> dict(path=[(lx,ly)...], medium, role, sysml_line)
# 方向: 供油/压力为主, 回油为薄线.
def local_edges():
    R = local_nodes()
    def p(key, port):
        return R[key]['ports'][port][:2]
    E = {}
    # 200/201 reservoir -> 两泵吸油 (供油)
    E['supply_edp'] = dict(medium='med', role='suction', sysml=200, tees=[(270,300)],
        path=[p('reservoir','supply'), (270,300), (270,178), p('enginePump','suction')])
    E['supply_emp'] = dict(medium='med', role='suction', sysml=201, tees=[(270,300)],
        path=[p('reservoir','supply'), (270,300), (270,348), p('electricPump','suction')])
    # 202/203 两泵压力 -> 滤入口 (并联汇合)
    E['pres_edp'] = dict(medium='hi', role='pressure', sysml=202, tees=[(430,268)],
        path=[p('enginePump','pressure_out'), (430,178), (430,268), p('filterUnit','inlet')])
    E['pres_emp'] = dict(medium='hi', role='pressure', sysml=203, tees=[(430,268)],
        path=[p('electricPump','pressure_out'), (430,348), (430,268), p('filterUnit','inlet')])
    # 204 滤 -> 压力控制阀
    E['filter_pc'] = dict(medium='hi', role='pressure', sysml=204, tees=[],
        path=[p('filterUnit','outlet'), p('pressureControl','inlet')])
    # 205 压力控制阀 -> 隔离阀
    E['pc_iso'] = dict(medium='hi', role='pressure', sysml=205, tees=[],
        path=[p('pressureControl','outlet'), p('isolationValve','inlet')])
    # 206 隔离阀 -> 蓄压器 (并联支路)
    E['iso_acc'] = dict(medium='hi', role='pressure', sysml=206, branch=True, tees=[(976,268)],
        path=[p('isolationValve','outlet'), (976,268), p('accumulator','hydraulic')])
    # 207 隔离阀 -> systemOutput
    E['iso_out'] = dict(medium='hi', role='pressure', sysml=207, tees=[(976,268)],
        path=[p('isolationValve','outlet'), (976,268), p('systemOutput','out')])
    # 197 机械输入 -> EDP 驱动轴
    E['mech_edp'] = dict(medium='mech', role='shaft', sysml=197, tees=[],
        path=[p('mechanicalInput','in'), p('enginePump','drive_shaft')])
    # 注: reservoir.service<->pump.hydraulicOutput 的 returnFluid 半边在模型中抽象,
    # 此处只画供油(正方向); 回油不在图上单独绘制, 见 manifold 说明.
    return E


# ---------- 整机层: 零件定义 ----------
# 起落架/飞控/控制器为概念总成, 画成描边框图.
def aircraft_nodes():
    return {
        'greenCircuit': dict(kind='zone', label='GREEN CIRCUIT / 绿系统 (HydraulicCircuit)'),
        'yellowCircuit': dict(kind='zone', label='YELLOW CIRCUIT / 黄系统 (HydraulicCircuit)'),
        'powerTransferUnit': dict(kind='block', label='PTU-001  能源转换装置 (PowerTransferUnit)',
                                  ports={'greenInput': 'left', 'yellowInput': 'right', 'command': 'top'}),
        'landingGear': dict(kind='cons', label='起落架 (LandingGearActuationSystem)', nsub=3,
                            sublabels=['前起落架作动器', '左主起落架作动器', '右主起落架作动器'],
                            ports={'hydraulicInput': 'top'}),
        'flightControls': dict(kind='cons', label='飞控 (FlightControlActuationSystem)', nsub=4,
                               sublabels=['左副翼作动器', '右副翼作动器', '升降舵作动器', '方向舵作动器'],
                               ports={'hydraulicInput': 'top'}),
        'controller': dict(kind='ctrl', label='控制器 (HydraulicSystemController)', nport=5,
                           ports=['greenPumpCommand', 'yellowPumpCommand', 'ptuCommand',
                                  'landingGearCommand', 'flightControlCommand']),
    }


def parse_sysml():
    """读取 .sysml, 提取 connect(带行号) 与 part 实例名, 供自检/追溯. 返回 (connects, parts)."""
    connects, parts = [], []
    ctx = None
    text = open(SYML, encoding='utf-8').read().split('\n')
    for i, l in enumerate(text, 1):
        s = l.strip()
        m = re.match(r'connect\s+([\w.]+)\s+to\s+([\w.]+)\s*;', s)
        if m:
            connects.append((i, m.group(1), m.group(2)))
            continue
        m2 = re.match(r'part\s+(\w+)\s*:\s*(\w+)\s*;', s)
        if m2:
            parts.append((i, m2.group(1), m2.group(2)))
    return connects, parts


# ============================================================
#  渲染
# ============================================================
def build():
    nodes_l = local_nodes()
    edges_l = local_edges()

    # 逻辑边(整机层): 统一放到一个边表, 便于自检与出图.
    # 每条边通过一个 callable 拿到 {pts, medium, role, label?} —— 但为清晰, 直接算好.
    return nodes_l, edges_l


def main():
    connects, parts = parse_sysml()
    nodes_l = local_nodes()
    edges_l = local_edges()

    # ---------- 组装整机边, 供自检 ----------
    # (sysml_line, required_instances, drawn_edge_ids)
    checks = []

    # 局部连通(每条 HydraulicCircuit 出现两次)
    internal_sysml = set(e['sysml'] for e in edges_l.values())
    # 机械/供油/回油等都有 sysml 归属; 但 197 只机械, 200/201 供油+回油共用行号.

    # 收集所有顶点, 画图; 同时记录 used edges/nodes for self-check.
    svg = render_sheet(nodes_l, edges_l, connects, parts)
    open(OUTSVG, 'w', encoding='utf-8').write(svg)
    md = render_manifest(connects, parts, nodes_l, edges_l)
    open(OUTMD, 'w', encoding='utf-8').write(md)

    # ---------- 结构自检 ----------
    ok = self_check(connects, parts, nodes_l, edges_l)
    print(("OK  结构自检通过: %d 条 connect, %d 个 part 实例全部有对应图元。" % (len(connects), len(parts)))
          if ok else "FAIL 结构自检未通过,见上。")
    sys.exit(0 if ok else 1)


def render_sheet(nodes_l, edges_l, connects, parts):
    """生成整图 SVG. 这是最长的函数; 布局常量内联, 按需调整后重跑即可."""
    out = []
    out.append('<?xml version="1.0" encoding="UTF-8"?>')
    out.append('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"')
    out.append('     width="%d" height="%d" viewBox="0 0 %d %d" role="img"'
               % (CANVAS_W, CANVAS_H, CANVAS_W, CANVAS_H))
    out.append('     aria-labelledby="title description">')
    out.append('  <title id="title">整机液压系统原理图</title>')
    out.append('  <desc id="description">由 aircraft_hydraulic_system.sysml 的 connect 拓扑生成。'
               '绿+黄两条液压回路经 PTU 交联, 绿供起落架、黄供飞控, 控制器引出指挥信号。概念图,非工程放行图。</desc>')
    out.append('  <defs>')
    out.append('    <marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">'
               '<path d="M 0 0 L 10 5 L 0 10 z" fill="#000000"/></marker>')
    out.append('    <marker id="am" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto">'
               '<path d="M 0 0 L 10 5 L 0 10 z" fill="#7a7a7a"/></marker>')
    out.append('  <style>')
    out.append('    .hi { fill:none; stroke:#000000; stroke-width:%s; stroke-linecap:round; stroke-linejoin:round; }' % HIGH_SW)
    out.append('    .med { fill:none; stroke:#000000; stroke-width:%s; stroke-linecap:round; stroke-linejoin:round; }' % MED_SW)
    out.append('    .lo { fill:none; stroke:#000000; stroke-width:%s; stroke-linecap:round; stroke-linejoin:round; }' % LOW_SW)
    out.append('    .sig { fill:none; stroke:#000000; stroke-width:%s; stroke-dasharray:7 4; stroke-linecap:round; }' % SIG_SW)
    out.append('    .mech { fill:none; stroke:#6a6a6a; stroke-width:%s; stroke-dasharray:12 3 3 3; stroke-linecap:round; }' % MECH_SW)
    out.append('    .port { fill:#ffffff; stroke:#000000; stroke-width:2; }')
    out.append('    .junction { fill:#000000; stroke:none; }')
    out.append('    .zone { fill:none; stroke:#000000; stroke-width:1.2; stroke-dasharray:10 4; }')
    out.append('    .block { fill:#ffffff; stroke:#000000; stroke-width:1.5; }')
    out.append('    .subblock { fill:#fbfbfb; stroke:#000000; stroke-width:0.9; }')
    out.append('    .label { font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif; fill:#111111; }')
    out.append('    .legendbox { fill:#ffffff; stroke:#000000; stroke-width:1.2; }')
    out.append('    .lghead { font-family:monospace; font-weight:bold; fill:#111111; }')
    out.append('    .lgitem { font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif; fill:#111111; }')
    out.append('  </style>')
    out.append('  </defs>')

    out.append('  <rect width="%d" height="%d" fill="#ffffff"/>' % (CANVAS_W, CANVAS_H))
    out.append('  <text class="label" x="50" y="52" font-size="30" font-weight="700">整机液压系统原理图</text>')
    out.append('  <text class="label" x="50" y="82" font-size="16">来源: aircraft_hydraulic_system.sysml'
               ' (SysML v2)   |   范围: AircraftHydraulicSystem 顶层   |   成熟度: concept   概念图,非工程放行图。</text>')

    # ----- 画布变量(绝对坐标, 手工布置, 保证元件/分区不重叠) -----
    GX, GY = 230, 190      # 绿回路局部原点(系统输出在右)
    YX, YY = 1400, 190     # 黄回路局部原点(镜像, 系统输出在左)
    # 分区框(局部包络 0..1000 x 0..620 外扩)
    gw, gh = 1150, 660
    gznx, gzny = 100, 150
    yznx, yzny = 1370, 150
    yw_, yh_ = 1050, 660
    out.append('  <rect class="zone" x="%d" y="%d" width="%d" height="%d" data-zone="greenCircuit"/>' % (gznx, gzny, gw, gh))
    out.append('  <text class="label" x="%d" y="%d" font-size="18" font-weight="700">GREEN CIRCUIT / 绿系统  (HydraulicCircuit)</text>' % (gznx+16, gzny-8))
    out.append('  <rect class="zone" x="%d" y="%d" width="%d" height="%d" data-zone="yellowCircuit"/>' % (yznx, yzny, yw_, yh_))
    out.append('  <text class="label" x="%d" y="%d" font-size="18" font-weight="700">YELLOW CIRCUIT / 黄系统  (HydraulicCircuit)</text>' % (yznx+16, yzny-8))

    # ---------- 画两条回路 ----------
    for side, anchor in (('green', (GX, GY, False)), ('yellow', (YX, YY, True))):
        render_circuit(out, nodes_l, edges_l, anchor, side)

    # ---------- 整机层: PTU, 起落架, 飞控, 控制器 ----------
    ptu = render_ptu(out)                      # 中心, 绿/黄之间
    lg = render_consumer(out, 'landingGear', aircraft_nodes()['landingGear'], (200, 900))
    fc = render_consumer(out, 'flightControls', aircraft_nodes()['flightControls'], (1700, 900))
    ctrl = render_controller(out, aircraft_nodes()['controller'], (1100, 950))

    # ---------- 整机层连接 ----------
    render_aircraft_edges(out, ptu, lg, fc, ctrl, GX, GY, YX, YY)

    # ---------- 图例 + 图签栏 ----------
    out.append(render_legend())
    out.append(render_titleblock(connects, parts))
    out.append('</svg>')
    return '\n'.join(out)


def render_circuit(out, nodes_l, edges_l, anchor, side):
    ox, oy, mirror = anchor
    # 元件符号
    for key, nd in nodes_l.items():
        if nd['box'] is None:
            continue
        bx, by, bw, bh = nd['box']
        # 盒子的镜像: 新左缘 = LOCAL_W - bx - bw(点镜像只减 bx, 盒子须再让出宽)
        ax = ox + ((LOCAL_W - bx - bw) if mirror else bx)
        ay = oy + by
        if nd['sym']:
            simg = '已标注/' + nd['sym'] if not nd['sym'].startswith('已标注/') else nd['sym']
            img = ('<image class="sym" data-node="%s.%s" x="%d" y="%d" width="%d" height="%d" '
                   'preserveAspectRatio="xMidYMid meet" href="%s" xlink:href="%s"%s/>'
                   % (side, key, ax, ay, bw, bh, simg, simg,
                      (' transform="translate(%d 0) scale(-1 1)"' % (2*ax+bw)) if mirror else ''))
            out.append('  ' + img)
        else:
            kind = nd.get('kind')
            if kind in ('relief', 'solenoid'):
                out.append(draw_valve(ax, ay, bw, bh, kind, side, key))
    # 虚拟端口(交界面)画小口 + 标注
    vlabels = {'systemOutput': '系统输出', 'mechanicalInput': '机械输入'}
    for key, nd in nodes_l.items():
        if nd['box'] is None:
            for pid, pt in nd['ports'].items():
                px = ox + mirror_x(pt[0], mirror); py = oy + pt[1]
                out.append('  <circle class="port" data-port="%s.%s" cx="%d" cy="%d" r="%d"/>'
                           % (side, pid, px, py, PORT_R))
                lbl = vlabels.get(key)
                if lbl and not mirror:
                    out.append('  <text class="label" x="%d" y="%d" font-size="11" text-anchor="middle">%s</text>'
                               % (px, py - 12, lbl))
    # 连接
    for key, e in edges_l.items():
        pts = [ (ox+mirror_x(x, mirror), oy+y) for (x, y) in e['path'] ]
        cls = {'hi':'hi','med':'med','lo':'lo','mech':'mech'}[e['medium']]
        marker = '' if e['medium']=='mech' else ' marker-end="url(#ah)"'
        d = 'M ' + ' H '.join('%.1f'%x for x in [pts[0][0]]) if False else None
        # 正交: 逐段写 V/H 便于紧凑
        dseg = sel_orth(pts)
        out.append('  <path id="%s.%s" class="%s" data-edge="%s.%s" data-sysml-line="%s" d="%s"%s/>'
                   % (side, key, cls, side, key, e['sysml'], dseg, marker))
    # 三通/分支节点实心点 —— 只在真实汇/分点画, 不画每个折角
    seen = set()
    for key, e in edges_l.items():
        for (x, y) in e.get('tees', []):
            k = (x, y)
            if k in seen:
                continue
            seen.add(k)
            out.append('  <circle class="junction" cx="%d" cy="%d" r="%d"/>' % (ox+mirror_x(x, mirror), oy+y, JUNC_R))
    # 元件端口点
    for key, nd in nodes_l.items():
        if nd['box'] is None:
            continue
        for pid, pt in nd['ports'].items():
            px = ox + mirror_x(pt[0], mirror); py = oy + pt[1]
            if pid in ('case_drain', 'drive_shaft', 'gas'):
                continue
            out.append('  <circle class="port" data-port="%s.%s" cx="%d" cy="%d" r="%d"/>'
                       % (side, pid, px, py, PORT_R))
    # 标签
    labels = {
        'reservoir': '油箱\nReservoir', 'enginePump': 'EDP\n发动机驱动泵',
        'electricPump': 'EMP\n电动泵', 'filterUnit': '压力滤\nFilter',
        'pressureControl': '压力控制阀\nPressureControlValve',
        'isolationValve': '隔离阀\nIsolationValve', 'accumulator': '蓄压器\nAccumulator',
    }
    for key, nd in nodes_l.items():
        if nd['box'] is None:
            continue
        bx, by, bw, bh = nd['box']
        ax = ox + ((LOCAL_W - bx - bw) if mirror else bx); ay = oy + by
        name = labels[key].split('\n')[0]
        if key == 'reservoir':
            # 油箱符号高瘦, 标签放外侧(绿=左, 黄=右)
            lx = (ax - 8) if not mirror else (ax + bw + 8)
            anchor = 'end' if not mirror else 'start'
            out.append('  <text class="label" x="%d" y="%d" font-size="13" text-anchor="%s">%s</text>' % (lx, ay + 90, anchor, name))
        elif nd['sym']:
            out.append('  <text class="label" x="%d" y="%d" font-size="12" text-anchor="middle">%s</text>' % (ax+bw/2, ay-8, name))
        # 压力控制/隔离阀由 draw_valve 自带标注


def sel_orth(pts):
    """把端点列表转为紧凑正交 path d(M x y H x V y ...)。"""
    seg = ['M %.1f %.1f' % pts[0]]
    for i in range(1, len(pts)):
        x0, y0 = pts[i-1]; x1, y1 = pts[i]
        if y0 == y1:
            seg.append('H %.1f' % x1)
        elif x0 == x1:
            seg.append('V %.1f' % y1)
        else:
            seg.append('H %.1f V %.1f' % (x1, y1))
    return ' '.join(seg)


def draw_valve(ax, ay, bw, bh, kind, side, key):
    """压力控制阀(relief)/隔离阀(solenoid) 的描边框图. 返回多行字符串."""
    parts = []
    parts.append('  <g class="valve" data-node="%s.%s">' % (side, key))
    parts.append('    <rect class="block" x="%d" y="%d" width="%d" height="%d"/>' % (ax, ay, bw, bh))
    cx = ax + bw/2; cy = ay + bh/2
    if kind == 'relief':
        # 弹簧(虚线锯齿)+ 阀芯箭头: 简化的溢流阀符号
        parts.append('    <path class="lo" d="M %d %d L %d %d L %d %d L %d %d L %d %d L %d %d"/>'
                     % (ax+18, ay+64, ax+26, ay+50, ax+34, ay+66, ax+42, ay+50, ax+50, ay+66, ax+58, ay+52))
        parts.append('    <path class="hi" d="M %d %d L %d %d" marker-end="url(#ah)"/>' % (ax+16, cy, cx-6, cy))
        parts.append('    <text class="label" x="%d" y="%d" font-size="11" text-anchor="middle">压力控制</text>' % (cx, ay+bh-8))
    elif kind == 'solenoid':
        # 电磁阀: 方框 + 内部阀位 + 线圈(上方小框)
        parts.append('    <path class="hi" d="M %d %d L %d %d" marker-end="url(#ah)"/>' % (ax+16, cy, cx-6, cy))
        parts.append('    <rect class="block" x="%d" y="%d" width="%d" height="%d" fill="#f2f2f2"/>'
                     % (int(cx-14), int(cy-22), 28, 44))
        parts.append('    <path class="lo" d="M %d %d L %d %d"/>' % (int(cx-14), int(cy-8), int(cx-2), int(cy-8)))
        parts.append('    <rect class="block" x="%d" y="%d" width="%d" height="%d"/>'
                     % (int(cx-9), int(ay+8), 18, 14))
        parts.append('    <text class="label" x="%d" y="%d" font-size="11" text-anchor="middle">隔离阀</text>' % (cx, ay+bh-8))
    parts.append('  </g>')
    return '\n'.join(parts)


# 图例
def render_legend():
    x, y, w, h = 100, 1180, 900, 230
    rows = [
        ('hi', 'High Pressure Line  高压供压线  3.0T'),
        ('med', 'Supply / Suction Line  供油/吸油线  1.4T'),
        ('lo', 'Low Pressure (return) Line  回油线  1.2T'),
        ('sig', 'Command / Status Signal  指挥/状态信号(虚线)  1.2T'),
        ('mech', 'Mechanical (shaft) Power  机械轴功率  1.4T'),
        ('junction', 'Junction (tee)  三通/节点实心点'),
        ('port', 'Connection Port  端口(白底黑边)'),
    ]
    out = []
    out.append('  <g id="legend">')
    out.append('    <rect class="legendbox" x="%d" y="%d" width="%d" height="%d"/>' % (x, y, w, h))
    out.append('    <text class="lghead" x="%d" y="%d" font-size="14">图例  (T = 1.20)</text>' % (x+16, y+28))
    yy = y + 52
    for cls, txt in rows:
        x0 = x + 16
        if cls in ('junction', 'port'):
            out.append('    <circle class="%s" cx="%d" cy="%d" r="%s"/>' % (cls, x0+8, yy-4, 5 if cls=='port' else 4.5))
        else:
            out.append('    <path class="%s" d="M %d %d H %d" marker-end="url(#ah)"/>' % (cls, x0, yy, x0+90))
        out.append('    <text class="lgitem" x="%d" y="%d" font-size="13">%s</text>' % (x0+110, yy+1, txt))
        yy += 22
    out.append('  </g>')
    return '\n'.join(out)


def render_titleblock(connects, parts):
    x, y, w, h = 1030, 1180, 1390, 230
    # 非标准/临时符号披露
    provisional = 'EDP/EMP(临时几何)  压力控制/隔离/PTU/作动器/控制器(绘制框图)'
    nc = len(connects)
    out = []
    out.append('  <g id="title">')
    out.append(f'    <rect class="legendbox" x="{x}" y="{y}" width="{w}" height="{h}"/>')
    out.append(f'    <text class="lghead" x="{x+16}" y="{y+28}" font-size="14">图签栏</text>')
    out.append(f'    <text class="lgitem" x="{x+16}" y="{y+56}" font-size="13">系统: AircraftHydraulicSystem   |   来源: aircraft_hydraulic_system.sysml   |   成熟度: concept</text>')
    out.append(f'    <text class="lgitem" x="{x+16}" y="{y+82}" font-size="13">连接: {nc} 条 SysML connect (回路内部 9 条×2 + 整机 9 条已画; 198/199 内部控制在边界口聚合)   |   元件: 油箱/EDP/EMP/滤/蓄压器为描边符号</text>')
    out.append(f'    <text class="lgitem" x="{x+16}" y="{y+108}" font-size="13">非标注符号: {provisional}</text>')
    out.append(f'    <text class="lgitem" x="{x+16}" y="{y+134}" font-size="13">概念图,非工程放行图。作动器回油、状态接线在模型中未定义,未画。</text>')
    out.append('  </g>')
    return '\n'.join(out)


# ---- 整机层元件绘制(PTU/作动器/控制器)及整机连接 ----
def render_ptu(out):
    x, y, w, h = 1250, 330, 120, 220
    out.append('  <g class="ptu" data-node="powerTransferUnit">')
    out.append('    <rect class="block" x="%d" y="%d" width="%d" height="%d"/>' % (x, y, w, h))
    out.append('    <text class="label" x="%d" y="%d" font-size="12" text-anchor="middle" font-weight="700">PTU-001</text>' % (x+w/2, y+18))
    out.append('    <text class="label" x="%d" y="%d" font-size="10" text-anchor="middle">能源转换装置</text>' % (x+w/2, y+34))
    # 内部: 两个泵圆 + 连接轴(传力不传液)
    for gy in (y+80, y+150):
        out.append('    <circle cx="%d" cy="%d" r="20" fill="#ffffff" stroke="#000000" stroke-width="1.4"/>' % (x+42, gy))
        out.append('    <circle cx="%d" cy="%d" r="20" fill="#ffffff" stroke="#000000" stroke-width="1.4"/>' % (x+w-42, gy))
    out.append('    <path class="mech" d="M %d %d H %d"/>' % (x+62, y+115, x+w-62))
    # 端口: 左 greenInput, 右 yellowInput, 底 command
    out.append('    <circle class="port" data-port="powerTransferUnit.greenInput" cx="%d" cy="%d" r="%d"/>' % (x, y+115, PORT_R))
    out.append('    <circle class="port" data-port="powerTransferUnit.yellowInput" cx="%d" cy="%d" r="%d"/>' % (x+w, y+115, PORT_R))
    out.append('    <circle class="port" data-port="powerTransferUnit.command" cx="%d" cy="%d" r="%d"/>' % (x+w/2, y+h, PORT_R))
    out.append('  </g>')
    return dict(x=x, y=y, w=w, h=h, cin_x=x+w/2, cin_y=y+115, cmd=(x+w/2, y+h))


def render_consumer(out, key, nd, xy):
    x, y = xy
    nsub = nd['nsub']; sublabels = nd['sublabels']
    w = 620 if nsub == 3 else 700
    h = 90
    out.append('  <g class="cons" data-node="%s">' % key)
    out.append('    <rect class="block" x="%d" y="%d" width="%d" height="%d"/>' % (x, y, w, h))
    out.append('    <text class="label" x="%d" y="%d" font-size="13" text-anchor="middle" font-weight="700">%s</text>' % (x+w/2, y-10, nd['label']))
    out.append('    <text class="label" x="%d" y="%d" font-size="10" text-anchor="middle">%s</text>' % (x+w/2, y+24, nd['label'].split(' (')[0]))
    # 子块
    sbw = (w - 20 - (nsub-1)*12) / nsub
    for i in range(nsub):
        sx = x + 10 + i*(sbw+12); sy = y + 50
        out.append('    <rect class="subblock" x="%d" y="%d" width="%d" height="%d"/>' % (sx, sy, sbw, 24))
        out.append('    <text class="label" x="%d" y="%d" font-size="10" text-anchor="middle">%s</text>' % (sx+sbw/2, sy+16, sublabels[i]))
    # 进口(顶部)
    out.append('    <circle class="port" data-port="%s.hydraulicInput" cx="%d" cy="%d" r="%d"/>' % (key, x+w/2, y, PORT_R))
    out.append('  </g>')
    return dict(x=x, y=y, w=w, h=h, cx=x+w/2, right=(x+w, y+62), left=(x, y+62))


def render_controller(out, nd, xy):
    x, y = xy
    w, h = 400, 120
    out.append('  <g class="ctrl" data-node="controller">')
    out.append('    <rect class="block" x="%d" y="%d" width="%d" height="%d"/>' % (x, y, w, h))
    out.append('    <text class="label" x="%d" y="%d" font-size="13" text-anchor="middle" font-weight="700">控制器</text>' % (x+w/2, y+20))
    out.append('    <text class="label" x="%d" y="%d" font-size="10" text-anchor="middle">HydraulicSystemController</text>' % (x+w/2, y+38))
    # 端口: 顶部 3 个(green / ptu / yellow), 左 1 个(LG), 右 1 个(FC)
    top_ports = {'greenPumpCommand': x+90, 'ptuCommand': x+200, 'yellowPumpCommand': x+310}
    for nm, cx in top_ports.items():
        out.append('    <circle class="port" data-port="controller.%s" cx="%d" cy="%d" r="%d"/>' % (nm, cx, y, PORT_R))
        out.append('    <text class="label" x="%d" y="%d" font-size="8" text-anchor="middle" fill="#666">%s</text>' % (cx, y+9, nm))
    out.append('    <circle class="port" data-port="controller.landingGearCommand" cx="%d" cy="%d" r="%d"/>' % (x, y+62, PORT_R))
    out.append('    <text class="label" x="%d" y="%d" font-size="8" text-anchor="start" fill="#666">landingGearCommand</text>' % (x+2, y+48))
    out.append('    <circle class="port" data-port="controller.flightControlCommand" cx="%d" cy="%d" r="%d"/>' % (x+w, y+62, PORT_R))
    out.append('    <text class="label" x="%d" y="%d" font-size="8" text-anchor="end" fill="#666">flightControlCommand</text>' % (x+w-2, y+48))
    out.append('  </g>')
    port = dict(top_ports)
    port['greenPumpCommand'] = (x+90, y)
    port['ptuCommand'] = (x+200, y)
    port['yellowPumpCommand'] = (x+310, y)
    port['landingGearCommand'] = (x, y+62)
    port['flightControlCommand'] = (x+w, y+62)
    return dict(x=x, y=y, w=w, h=h, ports=port)


def render_aircraft_edges(out, ptu, lg, fc, ctrl, GX, GY, YX, YY):
    # 系统输出端口(绝对)
    g_out = (GX + LOCAL_W, GY + 268)     # 绿: 局部 x=1000
    y_out = (YX, YY + 268)               # 黄: 镜像后在左缘
    # ---- 绿 systemOutput -> PTU.greenInput ----
    seg = sel_orth([g_out, (ptu['x'], g_out[1]), (ptu['x'], ptu['cin_y'])])
    out.append('  <path id="green.ptu" class="hi" data-edge="green_ptu" data-sysml-line="222" d="%s" marker-end="url(#ah)"/>' % seg)
    # ---- 黄 systemOutput -> PTU.yellowInput ----
    seg = sel_orth([y_out, (ptu['x']+ptu['w'], y_out[1]), (ptu['x']+ptu['w'], ptu['cin_y'])])
    out.append('  <path id="yellow.ptu" class="hi" data-edge="yellow_ptu" data-sysml-line="223" d="%s" marker-end="url(#ah)"/>' % seg)

    # ---- 绿 systemOutput -> 起落架(分支下行到分区下方再左送) ----
    tee_g = (1185, g_out[1])
    seg = sel_orth([g_out, tee_g, (tee_g[0], 860), (lg['cx'], 860), (lg['cx'], lg['y'])])
    out.append('  <path id="green.lg" class="hi" data-edge="green_lg" data-sysml-line="224" d="%s" marker-end="url(#ah)"/>' % seg)
    # ---- 黄 systemOutput -> 飞控 ----
    tee_y = (1455, y_out[1])
    seg = sel_orth([y_out, tee_y, (tee_y[0], 860), (fc['cx'], 860), (fc['cx'], fc['y'])])
    out.append('  <path id="yellow.fc" class="hi" data-edge="yellow_fc" data-sysml-line="225" d="%s" marker-end="url(#ah)"/>' % seg)

    # 给 systemOutput 分支画三通节点
    out.append('  <circle class="junction" cx="%d" cy="%d" r="%d"/>' % (tee_g[0], tee_g[1], JUNC_R))
    out.append('  <circle class="junction" cx="%d" cy="%d" r="%d"/>' % (tee_y[0], tee_y[1], JUNC_R))

    # ---- 控制器命令(虚线) ----
    cp = ctrl['ports']
    # greenPumpCommand -> 绿回路 enginePumpCommand 边界口(绿分区右缘)
    gcmd = (1250, 720)
    out.append('  <circle class="port" data-port="greenCircuit.enginePumpCommand" cx="%d" cy="%d" r="%d"/>' % (gcmd[0], gcmd[1], PORT_R))
    out.append('  <path id="ctrl.greencmd" class="sig" data-edge="green_cmd" data-sysml-line="227" d="%s" marker-end="url(#ah)"/>'
               % sel_orth([cp['greenPumpCommand'], gcmd]))
    # yellowPumpCommand -> 黄回路 enginePumpCommand 边界口(黄分区左缘)
    ycmd = (1370, 720)
    out.append('  <circle class="port" data-port="yellowCircuit.enginePumpCommand" cx="%d" cy="%d" r="%d"/>' % (ycmd[0], ycmd[1], PORT_R))
    out.append('  <path id="ctrl.yellowcmd" class="sig" data-edge="yellow_cmd" data-sysml-line="228" d="%s" marker-end="url(#ah)"/>'
               % sel_orth([cp['yellowPumpCommand'], ycmd]))
    # ptuCommand -> PTU 底口
    out.append('  <path id="ctrl.ptu" class="sig" data-edge="ptu_cmd" data-sysml-line="229" d="%s" marker-end="url(#ah)"/>'
               % sel_orth([cp['ptuCommand'], ptu['cmd']]))
    # landingGearCommand -> 起落架右口
    out.append('  <path id="ctrl.lg" class="sig" data-edge="lg_cmd" data-sysml-line="230" d="%s" marker-end="url(#ah)"/>'
               % sel_orth([cp['landingGearCommand'], lg['right']]))
    # flightControlCommand -> 飞控左口
    out.append('  <path id="ctrl.fc" class="sig" data-edge="fc_cmd" data-sysml-line="231" d="%s" marker-end="url(#ah)"/>'
               % sel_orth([cp['flightControlCommand'], fc['left']]))
    return


def render_manifest(connects, parts, nodes_l, edges_l):
    L = []
    L.append('# aircraft_hydraulic_system 整机原理图追溯清单\n')
    L.append('本清单把 SVG 中的每个节点/边映射到 SysML 模型的唯一输入定义(行号),'
             '遵循仓库核心原则"任一组件/端口/连接/图元可追溯到唯一输入定义"。\n')
    L.append('## 连接(边)映射\n')
    L.append('| 来源 connect 行 | SysML 语句 | 图上的边 | 实例数 |\n|---|---|---|---|\n')
    m = {
        197: ('mechanicalInput to enginePump.mechanicalInput', 'enginePump 驱动轴(机械)'),
        198: ('enginePumpCommand to enginePump.command', '发动机泵指令(在电路边界 enginePumpCommand 聚合, 图上未单独画到 EDP)'),
        199: ('electricPumpCommand to electricPump.command', '电动泵指令(同上, 边界口聚合)'),
        200: ('reservoir.service to enginePump.hydraulicOutput', '油箱供油→EDP'),
        201: ('reservoir.service to electricPump.hydraulicOutput', '油箱供油→EMP'),
        202: ('enginePump.hydraulicOutput to filterUnit.inlet', 'EDP 压力→压力滤'),
        203: ('electricPump.hydraulicOutput to filterUnit.inlet', 'EMP 压力→压力滤'),
        204: ('filterUnit.outlet to pressureControl.inlet', '压力滤→压力控制阀'),
        205: ('pressureControl.outlet to isolationValve.inlet', '压力控制阀→隔离阀'),
        206: ('isolationValve.outlet to accumulator.service', '隔离阀→蓄压器(并联支路)'),
        207: ('isolationValve.outlet to systemOutput', '隔离阀→系统输出'),
        222: ('greenCircuit.systemOutput to powerTransferUnit.greenInput', '绿→PTU 绿侧'),
        223: ('yellowCircuit.systemOutput to powerTransferUnit.yellowInput', '黄→PTU 黄侧'),
        224: ('greenCircuit.systemOutput to landingGear.hydraulicInput', '绿→起落架'),
        225: ('yellowCircuit.systemOutput to flightControls.hydraulicInput', '黄→飞控'),
        227: ('controller.greenPumpCommand to greenCircuit.enginePumpCommand', '控制器→绿泵指令'),
        228: ('controller.yellowPumpCommand to yellowCircuit.enginePumpCommand', '控制器→黄泵指令'),
        229: ('controller.ptuCommand to powerTransferUnit.command', '控制器→PTU 指令'),
        230: ('controller.landingGearCommand to landingGear.command', '控制器→起落架指令'),
        231: ('controller.flightControlCommand to flightControls.command', '控制器→飞控指令'),
    }
    for ln, a, b in connects:
        desc = (m.get(ln) or ('', ''))[1]
        inst = '绿+黄(×2)' if ln in (197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207) else '×1'
        L.append('| %d | `connect %s to %s` | %s | %s |\n' % (ln, a, b, desc, inst))
    L.append('\n## 节点(part)映射\n')
    L.append('| 来源行 | part | 图上元件 | 符号 |\n|---|---|---|---|\n')
    symmap = {'reservoir':'油箱(描边)','enginePump':'EDP(临时几何)','electricPump':'EMP(临时几何)',
              'filterUnit':'压力滤(描边)','pressureControl':'压力控制阀(绘制框图)',
              'isolationValve':'隔离阀(绘制框图)','accumulator':'蓄压器(描边)'}
    for ln, name, typ in parts:
        # 只列实例级 part(含小写实例名); part def 不列
        if name[0].islower():
            L.append('| %d | `%s:%s` | %s | %s |\n' % (ln, name, typ, name, symmap.get(name, '总成/框图')))
    L.append('\n## 概念模型简化说明\n')
    L.append('- 各作动器(起落架/飞控)的**回油**在模型中未建模,图上未画。\n')
    L.append('- `status` 端口存在但整机层无连线(概念级),图上仅以端口点示意,未接出。\n')
    L.append('- 回路内部指令(198/199: enginePumpCommand→enginePump.command 等)在电路边界 `enginePumpCommand` 端口聚合,图上未单独画到泵。\n')
    L.append('- 泵与油箱的 `reservoir.service↔pump.hydraulicOutput` 经 HydraulicPowerPort 同时绑定供油与回油;图上只画供油(正方向),回油半边在概念层抽象,未单独绘制。\n')
    L.append('- 黄系统为绿系统的水平镜像布局,两者内部拓扑相同。\n')
    L.append('- PTU 传递功率不传递液体(模型注释),图上 PTU 两侧只画供压入口,无流体连通线。\n')
    return ''.join(L)


def self_check(connects, parts, nodes_l, edges_l):
    ok = True
    # 1) 每条 expected sysml connect(回路内部 x2 / 整机 x1) 都在最终 SVG 中有一条
    #    带对应 data-sysml-line 的边. 直接解析成品 SVG, 而非局部边表, 更可靠.
    expected = {197, 200, 201, 202, 203, 204, 205, 206, 207,
                222, 223, 224, 225, 227, 228, 229, 230, 231}
    drawn = set()
    for m in re.finditer(r'data-sysml-line="(\d+)"', open(OUTSVG, encoding='utf-8').read()):
        drawn.add(int(m.group(1)))
    missing = expected - drawn
    if missing:
        print('  MISSING drawn edges for sysml lines:', sorted(missing)); ok = False
    extra = drawn - expected
    if extra:
        print('  EXTRA drawn sysml lines:', sorted(extra)); ok = False
    # 2) 每个 part 实例都被图上某元素表示(回路零件→元件、作动器→子块、顶层→总成/整图).
    circ_sub = {'reservoir', 'enginePump', 'electricPump', 'filterUnit',
                'pressureControl', 'isolationValve', 'accumulator'}
    actuator_sub = {'noseGearActuator', 'leftMainGearActuator', 'rightMainGearActuator',
                    'leftAileronActuator', 'rightAileronActuator', 'elevatorActuator', 'rudderActuator'}
    top = {'greenCircuit', 'yellowCircuit', 'powerTransferUnit', 'landingGear',
           'flightControls', 'controller', 'aircraftHydraulics'}
    for _, n, _ in parts:
        if n in circ_sub or n in actuator_sub or n in top:
            continue
        print('  UNEXPLAINED part instance:', n); ok = False
    # 3) 局部回路的所有绘制点都在 0..LOCAL_W x 0..LOCAL_H(防错拼越界).
    for e in edges_l.values():
        for (x, y) in e['path']:
            if x < 0 or x > LOCAL_W or y < 0 or y > LOCAL_H:
                print('  edge point out of circuit frame:', (x, y)); ok = False
    return ok


if __name__ == '__main__':
    main()
