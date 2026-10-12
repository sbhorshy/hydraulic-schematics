# -*- coding: utf-8 -*-
"""editor-proto 服务端 —— #60 最小原型（拖拽写回闭环）

口径依据（不在此复述理由，票内有）：
- #58 手调直改 layout.json：手调即真源；单一落盘实现（本文件 write_layout_atomic 是
  原型范围内唯一写 layout 的路径）；revision_log 顶条 + layout_version 递增披露手调批次，
  来源标识 editor-proto。
- #59 编辑器无导出能力：本服务不提供任何成品下载端点；画布每帧=标准链产物
  （规范源 render_l0_sheet.py → 新 PNG → validate_sheet.py，零校验实现）；违规手调允许落盘，
  由 validate 结果如实呈现（红=扣留无成品）。
- #63 镜像操作面（条件解禁）：mirror 为绝对请求 'none'/'x'/'y'，缺省=保持当前姿态
  （False/0/True/容器按类型在请求层与函数入口双拒）。授权复用 skill 单源裁决
  endpoint_usage.mirror_contract（实际 catalog/资产/intent 实例类型，三道闸），
  且必须发生在 write_layout_atomic 之前——未登记/过期 hash/非法轴时整次事务拒绝，
  layout_version/revision_log/文件均不变，同请求携带的移动一并拒绝；
  已有合法镜像的实例移动同样重过许可。许可闸解析 intent 与 render_l0_sheet
  同用 ruamel YAML 1.2 load_yaml（PyYAML/YAML 1.1 会把 ON/OFF/No 等合法实例
  ID 解析成 bool，令实例"消失"于 intent.parts 而绕过登记，真实复现见
  ../editor-permission-review.json）；选中节点缺失于 intent.parts 或实例类型
  未在目录登记，写盘前显式拒绝，不依赖 mirror_contract 对缺失实例的跳过。
  mirror-only 不是零位移；日志记 before/after 轴与节点 ID；本路径只写
  x/y/rot/mirror 四键，不碰端口角色；layout 存量 mirror 值域与 API 请求
  值域不同——镜像规范单源 mirror_policy.check_mirror 允许已有
  layout.mirror=False 表示不镜像（与此前 renderer 兼容），普通移动/旋转
  放行且原样保留该字段；存量 0/True/容器仍是值域外声明，整事务拒绝，
  绝不静默当 none 或借写盘 pop 洗白。

用法：
    python editor-proto/server.py [--workdir "1#系统原理图"] [--port 8763]

workdir 缺省为仓库内 1#系统原理图（项目侧标准链所在目录）。自测请复制沙箱，
勿对脏树试刀。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.abspath(os.path.join(HERE, '..', '.agents', 'skills', 'hydraulic-schematic', 'scripts'))
sys.path.insert(0, SCRIPTS)
from endpoint_usage import mirror_contract
from proofreading_evidence import verify_report
from render_l0_sheet import load_yaml  # canonical ruamel YAML 1.2：许可闸与渲染同一解析口径

LOCK = threading.Lock()
STATE = {'latency': None}  # 最近一次闭环耗时，供 /api/sheet 回显

MIRROR_CHOICES = ('none', 'x', 'y')  # 绝对请求值域；缺省（键不在）=保持姿态


def _load(workdir, name):
    with open(os.path.join(workdir, name), encoding='utf-8') as f:
        return json.load(f)


def write_layout_atomic(workdir, layout):
    """唯一落盘路径：同目录 tmp → os.replace（Tavotto atomicio 纪律的极简版）。"""
    fd, tmp = tempfile.mkstemp(dir=workdir, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(layout, f, ensure_ascii=False, indent=2)
        os.replace(tmp, os.path.join(workdir, '1#系统.layout.json'))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _bump_version(ver):
    m = re.match(r'^(\d+)\.(\d+)$', str(ver))
    if not m:
        return '1.1'
    return '%s.%d' % (m.group(1), int(m.group(2)) + 1)


def _run(workdir, script, timeout=300):
    t0 = time.perf_counter()
    args = [sys.executable, os.path.join(SCRIPTS, script)]
    if script == 'rasterize_sheet.py':
        args += [os.path.join(workdir, '1#系统原理图.svg'), '-o', os.path.join(workdir, 'sheet-readback.png')]
    else:
        args += [workdir]
    p = subprocess.run(args, cwd=workdir,
                       capture_output=True, timeout=timeout)
    ms = int((time.perf_counter() - t0) * 1000)
    out = p.stdout.decode('utf-8', 'replace')
    err = p.stderr.decode('utf-8', 'replace')
    return p.returncode, out, err, ms


def _flatten_issues(report):
    """validation-report.json → 侧栏条目（红黄灰）。只搬运判定，不产生判定。"""
    items = []
    for key in ('checks', 'budgets', 'items'):
        for it in (report.get(key) or []):
            if not isinstance(it, dict):
                continue
            items.append({'id': it.get('id', '?'),
                          'result': str(it.get('result', it.get('level', ''))),
                          'detail': str(it.get('detail', ''))[:220]})
    rank = {'fail': 'red', 'error': 'red', 'warn': 'yellow'}
    for it in items:
        it['sev'] = rank.get(it['result'].lower(), 'gray')
    order = {'red': 0, 'yellow': 1, 'gray': 2}
    items.sort(key=lambda it: order[it['sev']])
    return items


def _node_mirror_axis(nd):
    """布局节点当前 mirror 原值 → None/'x'/'y'（layout 值域与 API 请求
    值域不同：请求只收缺省/None 与 'none'/'x'/'y'，False/0/True 在入口
    即拒；而已有 layout.mirror=False 是镜像规范单源 mirror_policy.
    check_mirror 允许的"不镜像"声明——与此前 renderer 兼容，读取按同一
    契约归一为无镜像，普通移动/旋转不得擅改该字段。0/True/容器仍是
    值域外声明，整事务拒绝——若当 none 处理，随后的写盘会把非法值
    pop 掉，等于洗白）。"""
    value = nd.get('mirror')
    if value is None or value is False:
        return None
    if isinstance(value, str) and value in MIRROR_CHOICES:
        return None if value == 'none' else value
    raise ValueError("不支持的 mirror=%r（当前布局声明在值域外；"
                     "只允许缺省/None/False/'none'/'x'/'y'）" % (value,))


def _mirror_permission_issues(workdir, proposed_nodes, selected=None):
    """#63 镜像授权：按实际 catalog/资产/intent 实例类型逐实例过三道闸。

    复用 endpoint_usage.mirror_contract（render place 与 validate_sheet
    contract 阶段的同一许可单源），编辑器不另造第二套裁决。intent 解析用
    render_l0_sheet.load_yaml（ruamel YAML 1.2），与随后的渲染完全同口径；
    PyYAML safe_load（YAML 1.1）会把 ON/OFF/No 等合法实例 ID 解析成 bool，
    使实例"消失"于 intent.parts、mirror_contract 跳过它而放过未登记镜像
    （真实复现：../editor-permission-review.json + probe-editor-permission.py）。
    selected 为本次操作的节点：缺失于 intent.parts 或实例类型未在目录登记
    都作为 issue 显式拒绝——不依赖 mirror_contract 对缺失实例的 continue
    跳过。返回 issues 列表（空=授权通过）。catalog 解析与 render_l0_sheet
    同序：workdir 本地优先，缺省回落 skill 规范源库。
    """
    catalog_path = os.path.join(workdir, 'component-catalog.json')
    if not os.path.isfile(catalog_path):
        catalog_path = os.path.join(SCRIPTS, '..', 'assets',
                                    'component-library', 'component-catalog.json')
    with open(catalog_path, encoding='utf-8') as f:
        catalog = json.load(f)
    intent = load_yaml(os.path.join(workdir, '1#系统.intent.yaml'))
    parts = intent.get('parts') if isinstance(intent, dict) else None
    if not isinstance(parts, dict):
        parts = {}
    types = {c['component_type']: c for c in catalog['components']}
    issues = []
    if selected is not None:
        if selected not in parts:
            issues.append({'kind': 'mirror_permission', 'component': selected,
                           'endpoint': None, 'symbol': None,
                           'detail': '%s 镜像许可: 实例不在 intent.parts 中'
                                     '（无法核实镜像登记），写盘前拒绝' % selected})
        elif parts[selected] not in types:
            issues.append({'kind': 'mirror_permission', 'component': selected,
                           'endpoint': None, 'symbol': None,
                           'detail': '%s 镜像许可: 实例类型 %r 未在目录登记，'
                                     '写盘前拒绝' % (selected, parts[selected])})
    contract_issues, _axes = mirror_contract(
        intent, types, proposed_nodes, workdir,
        os.path.dirname(os.path.abspath(catalog_path)))
    issues.extend(contract_issues)
    return issues


def apply_delta(workdir, node, dx, dy, rot=None, mirror=None):
    """闭环：读 layout → 直改坐标/旋转/镜像（服务端为权威，含夹取）→ revision_log → 渲染 → 校核。

    rot 为绝对新值（0/90/180/270，渲染器同款校验）；夹取按旋转后占位宽高（墨迹口径）。
    mirror 为绝对请求 'none'/'x'/'y'，None（键缺省）=保持当前姿态；False/0/True/
    容器在函数入口按类型拒绝；已有 layout.mirror=False 是规范单源 check_mirror
    允许的"不镜像"（与此前 renderer 兼容），普通移动/旋转放行且原样保留该字段，
    存量 0/True/容器等值域外声明仍整事务拒绝（不清洗）。
    变更后姿态含镜像（新请求，或实例原有镜像随移动重验）时，必须在
    write_layout_atomic 前通过 mirror_policy 三道闸；拒绝即整次事务失败，
    版本/日志/文件不动。mirror-only 操作不算零位移。本路径只写
    x/y/rot/mirror 四键，端口角色不在此触碰。
    """
    if mirror is not None and (not isinstance(mirror, str)
                               or mirror not in MIRROR_CHOICES):
        # False/0/True/容器不是"无镜像"：缺省（None）才是保持当前姿态；
        # 类型与值域在函数入口即拒，HTTP Handler 同口径，不靠 truthiness。
        return {'ok': False, 'stage': 'delta',
                'error': "mirror 只接受 'none'/'x'/'y'（缺省=保持当前姿态），"
                         '实际 %r' % (mirror,)}
    layout = _load(workdir, '1#系统.layout.json')
    nodes = layout.get('nodes') or {}
    if node not in nodes:
        return {'ok': False, 'stage': 'delta', 'error': '未知节点 %s' % node}
    nd = nodes[node]
    ox, oy = nd.get('x', 0), nd.get('y', 0)
    orot = int(nd.get('rot', 0))
    try:
        before_axis = _node_mirror_axis(nd)
    except ValueError as error:
        return {'ok': False, 'stage': 'delta',
                'error': '当前布局 %s: %s' % (node, error)}
    mirror_requested = mirror is not None
    after_axis = before_axis if not mirror_requested else (
        None if mirror == 'none' else mirror)
    mirror_changed = mirror_requested and after_axis != before_axis
    new_rot = orot
    if rot is not None:
        new_rot = int(rot) % 360
        if new_rot not in (0, 90, 180, 270):
            return {'ok': False, 'stage': 'delta',
                    'error': 'rot=%s 不在允许的 0/90/180/270' % rot}
    canvas = layout.get('canvas') or {}
    w, h = nd.get('w', 0), nd.get('h', 0)
    ew, eh = (h, w) if new_rot % 180 else (w, h)
    nx = min(max(ox + dx, 0), max(canvas.get('width', 10**6) - ew, 0))
    ny = min(max(oy + dy, 0), max(canvas.get('height', 10**6) - eh, 0))
    moved = nx != ox or ny != oy
    if not moved and new_rot == orot and not mirror_changed:
        return {'ok': False, 'stage': 'delta', 'error': '零位移'}

    # #63 授权闸（写盘前）：变更后姿态含镜像才需要登记；已带合法镜像的
    # 实例仅移动同样重验（资产/端口漂移会令旧登记失效）。任何 issue 都
    # 拒绝整次事务——含同请求里的移动，绝不"部分落盘"。
    if after_axis is not None:
        proposed = {key: dict(value) for key, value in nodes.items()}
        proposed[node] = dict(nd)
        proposed[node]['mirror'] = after_axis
        try:
            issues = _mirror_permission_issues(workdir, proposed, selected=node)
        except Exception as error:  # catalog/intent 缺失或坏档：fail-closed
            return {'ok': False, 'stage': 'permission',
                    'error': '镜像许可检查无法执行：%s' % error,
                    'mirror_issues': []}
        if issues:
            return {'ok': False, 'stage': 'permission',
                    'error': '镜像许可未过：%s'
                             % '；'.join(str(i.get('detail')) for i in issues),
                    'mirror_issues': issues}

    ver = _bump_version(layout.get('layout_version', '1.0'))
    layout['layout_version'] = ver
    nd['x'], nd['y'] = nx, ny
    if new_rot != orot:
        if new_rot:
            nd['rot'] = new_rot
        else:
            nd.pop('rot', None)
    if mirror_requested:
        if after_axis:
            nd['mirror'] = after_axis
        else:
            nd.pop('mirror', None)
    log = layout.setdefault('revision_log', [])
    fmt = lambda v: '%g' % round(float(v), 2)  # 日志坐标去浮点噪音，保 diff 可读
    move = '%s (%s,%s)→(%s,%s)' % (node, fmt(ox), fmt(oy), fmt(nx), fmt(ny))
    tags = []
    if new_rot != orot:
        tags.append('rot %d→%d' % (orot, new_rot))
    if mirror_requested:  # 日志记 before/after 轴（none 也显式记）
        tags.append('mirror %s→%s' % (before_axis or 'none', after_axis or 'none'))
    if tags:
        act = '手调' if moved else ('镜像' if mirror_requested else '旋转')
        log.append('%s editor-proto:%s %s %s' % (ver, act, move, ' '.join(tags)))
    else:
        log.append('%s editor-proto:手调 %s' % (ver, move))
    write_layout_atomic(workdir, layout)

    rc_r, _out_r, err_r, ms_r = _run(workdir, 'render_l0_sheet.py')
    if rc_r != 0:
        STATE['latency'] = {'render_ms': ms_r, 'validate_ms': None, 'total_ms': ms_r}
        return {'ok': False, 'stage': 'render', 'render_stderr': err_r[-1500:],
                'latency': STATE['latency'],
                'layout_meta': {'version': ver,
                                'revision_log_tail': log[-5:]},
                'hint': '渲染失败（layout 已按手调即真源落盘，git 可回退）'}

    rc_png, _, err_png, ms_png = _run(workdir, 'rasterize_sheet.py')
    rc_v, out_v, err_v, ms_v = _run(workdir, 'validate_sheet.py')
    ms_v += ms_png
    total = ms_r + ms_v
    STATE['latency'] = {'render_ms': ms_r, 'validate_ms': ms_v, 'total_ms': total}
    try:
        report = _load(workdir, 'validation-report.json')
    except Exception:
        try:
            report = json.loads(out_v)
        except Exception:
            report = {'validation': 'unknown', 'checks': []}

    svg_path = os.path.join(workdir, '1#系统原理图.svg')
    with open(svg_path, encoding='utf-8') as f:
        svg = f.read()

    evidence = verify_report(workdir)
    passed = rc_png == 0 and rc_v == 0 and evidence.get('status') == 'current' and evidence.get('delivery', {}).get('ready', False)
    return {'ok': True, 'passed': passed, 'svg': svg, 'evidence': evidence,
            'issues': _flatten_issues(report)[:40],
            'latency': STATE['latency'],
            'layout_meta': {'version': ver,
                            'revision_log_tail': log[-5:],
                            'raster_exit': rc_png, 'raster_stderr': err_png[-500:],
                            'validate_exit': rc_v, 'validate_stderr': err_v[-500:]}}


def _connection_counts(workdir):
    """从 intent 统计每实例连接数（供编辑器旋转提示）：paths 链上端点记 1 次、
    中间件记 2 次；taps 的 sensor/at 各记 1 次。解析失败返回空表（提示降级）。"""
    try:
        # 与许可闸/渲染同用 ruamel YAML 1.2：ON/OFF 等拼写 ID 保持字符串，
        # 连线计数才不会因 PyYAML 的 bool 强转而张冠李戴。
        intent = load_yaml(os.path.join(workdir, '1#系统.intent.yaml'))
    except Exception:
        return {}
    conns = {}

    def bump(name):
        name = (name or '').strip()
        if name and not name.startswith('@') and not name.startswith('#'):
            conns[name] = conns.get(name, 0) + 1

    for chain in (intent.get('paths') or []):
        toks = chain if isinstance(chain, list) else [chain]
        seq = []
        for tok in toks:
            if not isinstance(tok, str) or tok.startswith('@'):
                continue
            name = tok.split('.')[0].strip()
            if not seq or seq[-1] != name:
                seq.append(name)
        for idx, name in enumerate(seq):
            bump(name)
            if 0 < idx < len(seq) - 1:
                bump(name)  # 链中间件=两向连接
    for t in (intent.get('taps') or []):
        if isinstance(t, dict):
            bump(str(t.get('sensor', '')).split('.')[0])
            at = t.get('at')
            if isinstance(at, dict):
                bump(str(at.get('node') or at.get('net') or '').split('.')[0])
            elif isinstance(at, str):
                bump(at.split('.')[0])
    return conns


class Handler(BaseHTTPRequestHandler):
    workdir = '.'

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            with open(os.path.join(HERE, 'index.html'), encoding='utf-8') as f:
                body = f.read().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == '/api/sheet':
            try:
                svg = open(os.path.join(self.workdir, '1#系统原理图.svg'),
                           encoding='utf-8').read()
                report = _load(self.workdir, 'validation-report.json')
                layout = _load(self.workdir, '1#系统.layout.json')
                evidence = verify_report(self.workdir)
                self._json({'ok': True, 'evidence': evidence,
                            'passed': evidence.get('status') == 'current' and evidence.get('delivery', {}).get('ready', False),
                            'svg': svg, 'issues': _flatten_issues(report)[:40],
                            'latency': STATE['latency'],
                            'layout_meta': {
                                'version': layout.get('layout_version'),
                                'revision_log_tail':
                                    (layout.get('revision_log') or [])[-5:]}})
            except Exception as e:
                self._json({'ok': False, 'error': str(e)}, 500)
        elif self.path == '/api/layout':
            try:
                layout = _load(self.workdir, '1#系统.layout.json')
                self._json({'nodes': layout.get('nodes') or {},
                            'canvas': layout.get('canvas') or {},
                            'conns': _connection_counts(self.workdir)})
            except Exception as e:
                self._json({'error': str(e)}, 500)
        else:
            self._json({'error': 'not found（编辑器无导出端点，#59）'}, 404)

    def do_POST(self):
        if self.path != '/api/delta':
            self._json({'error': 'not found'}, 404)
            return
        try:
            n = int(self.headers.get('Content-Length', 0))
            req = json.loads(self.rfile.read(n).decode('utf-8'))
            node = req['node']
            dx, dy = float(req.get('dx', 0)), float(req.get('dy', 0))
            rot = req.get('rot')
            rot = int(rot) if rot is not None else None
            mirror = req.get('mirror')
            if mirror is not None and (not isinstance(mirror, str)
                                       or mirror not in MIRROR_CHOICES):
                # False/0/True/容器不是"无镜像"：缺省（键不在）才是保持
                # 当前姿态；与 apply_delta 函数入口同一类型口径。
                raise ValueError(
                    "mirror 只接受 'none'/'x'/'y'，实际 %r（缺省=保持当前姿态）"
                    % (mirror,))
        except Exception as e:
            self._json({'ok': False, 'stage': 'request', 'error': str(e)}, 400)
            return
        with LOCK:  # 单用户原型；锁保证读-改-写-链不交叠
            try:
                self._json(apply_delta(self.workdir, node, dx, dy, rot, mirror))
            except subprocess.TimeoutExpired:
                self._json({'ok': False, 'stage': 'render', 'error': '链路超时'}, 500)
            except Exception as e:
                self._json({'ok': False, 'stage': 'server', 'error': str(e)}, 500)

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', default=os.path.join(HERE, '..', '1#系统原理图'))
    ap.add_argument('--port', type=int, default=8763)
    a = ap.parse_args()
    workdir = os.path.abspath(a.workdir)
    for need in ('1#系统.intent.yaml', '1#系统.layout.json'):
        if not os.path.exists(os.path.join(workdir, need)):
            sys.exit('workdir 缺 %s：%s' % (need, workdir))
    Handler.workdir = workdir
    print('editor-proto → %s  http://127.0.0.1:%d/  （Ctrl+C 退出）'
          % (workdir, a.port))
    ThreadingHTTPServer(('127.0.0.1', a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
