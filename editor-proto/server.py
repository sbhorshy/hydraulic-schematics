# -*- coding: utf-8 -*-
"""editor-proto 服务端 —— #60 最小原型（拖拽写回闭环）

口径依据（不在此复述理由，票内有）：
- #58 手调直改 layout.json：手调即真源；单一落盘实现（本文件 write_layout_atomic 是
  原型范围内唯一写 layout 的路径）；revision_log 顶条 + layout_version 递增披露手调批次，
  来源标识 editor-proto。
- #59 编辑器无导出能力：本服务不提供任何成品下载端点；画布每帧=标准链产物
  （render.py → validate_sheet.py 原样调起，零校验实现）；违规手调允许落盘，
  由 validate 结果如实呈现（红=扣留无成品）。

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
LOCK = threading.Lock()
STATE = {'latency': None}  # 最近一次闭环耗时，供 /api/sheet 回显


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
    p = subprocess.run([sys.executable, script], cwd=workdir,
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


def apply_delta(workdir, node, dx, dy, rot=None):
    """闭环：读 layout → 直改坐标/旋转（服务端为权威，含夹取）→ revision_log → 渲染 → 校核。

    rot 为绝对新值（0/90/180/270，渲染器同款校验）；夹取按旋转后占位宽高（墨迹口径）。
    """
    layout = _load(workdir, '1#系统.layout.json')
    nodes = layout.get('nodes') or {}
    if node not in nodes:
        return {'ok': False, 'stage': 'delta', 'error': '未知节点 %s' % node}
    nd = nodes[node]
    ox, oy = nd.get('x', 0), nd.get('y', 0)
    orot = int(nd.get('rot', 0))
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
    if nx == ox and ny == oy and new_rot == orot:
        return {'ok': False, 'stage': 'delta', 'error': '零位移'}

    ver = _bump_version(layout.get('layout_version', '1.0'))
    layout['layout_version'] = ver
    nd['x'], nd['y'] = nx, ny
    if new_rot != orot:
        if new_rot:
            nd['rot'] = new_rot
        else:
            nd.pop('rot', None)
    log = layout.setdefault('revision_log', [])
    fmt = lambda v: '%g' % round(float(v), 2)  # 日志坐标去浮点噪音，保 diff 可读
    move = '%s (%s,%s)→(%s,%s)' % (node, fmt(ox), fmt(oy), fmt(nx), fmt(ny))
    if new_rot != orot:
        act = '旋转' if nx == ox and ny == oy else '手调'
        log.append('%s editor-proto:%s %s rot %d→%d' % (ver, act, move, orot, new_rot))
    else:
        log.append('%s editor-proto:手调 %s' % (ver, move))
    write_layout_atomic(workdir, layout)

    rc_r, _out_r, err_r, ms_r = _run(workdir, 'render.py')
    if rc_r != 0:
        STATE['latency'] = {'render_ms': ms_r, 'validate_ms': None, 'total_ms': ms_r}
        return {'ok': False, 'stage': 'render', 'render_stderr': err_r[-1500:],
                'latency': STATE['latency'],
                'hint': '渲染失败（layout 已按手调即真源落盘，git 可回退）'}

    rc_v, out_v, err_v, ms_v = _run(workdir, 'validate_sheet.py')
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

    passed = str(report.get('validation', '')).lower() in ('passed', 'pass', 'ok')
    return {'ok': True, 'passed': passed, 'svg': svg,
            'issues': _flatten_issues(report)[:40],
            'latency': STATE['latency'],
            'layout_meta': {'version': ver,
                            'revision_log_tail': log[-5:],
                            'validate_exit': rc_v, 'validate_stderr': err_v[-500:]}}


def _connection_counts(workdir):
    """从 intent 统计每实例连接数（供编辑器旋转提示）：paths 链上端点记 1 次、
    中间件记 2 次；taps 的 sensor/at 各记 1 次。解析失败返回空表（提示降级）。"""
    try:
        import yaml
        with open(os.path.join(workdir, '1#系统.intent.yaml'), encoding='utf-8') as f:
            intent = yaml.safe_load(f)
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
                self._json({'ok': True,
                            'passed': str(report.get('validation', '')).lower()
                            in ('passed', 'pass', 'ok'),
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
        except Exception as e:
            self._json({'ok': False, 'stage': 'request', 'error': str(e)}, 400)
            return
        with LOCK:  # 单用户原型；锁保证读-改-写-链不交叠
            try:
                self._json(apply_delta(self.workdir, node, dx, dy, rot))
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
    for need in ('render.py', 'validate_sheet.py', '1#系统.layout.json'):
        if not os.path.exists(os.path.join(workdir, need)):
            sys.exit('workdir 缺 %s：%s' % (need, workdir))
    Handler.workdir = workdir
    print('editor-proto → %s  http://127.0.0.1:%d/  （Ctrl+C 退出）'
          % (workdir, a.port))
    ThreadingHTTPServer(('127.0.0.1', a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
