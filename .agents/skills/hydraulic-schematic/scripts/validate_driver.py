# -*- coding: utf-8 -*-
"""校核驱动器（#13）：render → validate → 按处方修 的有界自动收敛
（#22 沉淀进 skill：渲染器改指 skill `render_l0_sheet.py`，与 frozen
proto_render 同源；沙箱脚本清单与符号/catalog 来源改为 skill 单源库）。

把「渲染→校核→按处方表修」的两轮收敛机制从 AI 手工驱动收编为脚本：
复用 preflight.py（L0 输入预检，findings 自带 remedy + 模板门禁）+
layout_engine.py（规则+守门+--optimize 第三阶段）+ render_l0_sheet.py
（渲染+结构自检）+ validate_sheet.py（整图结构校核）。驱动器自己不新增
校核口径，只做三件事：解析 findings、按处方表试修、有界轮次内重跑，
收敛失败带结构化报告退出。

处方表（finding → 机械修法；修不动的立即上报，不烧轮次）：
  R0  E-*   preflight ERROR。P1=纯传感链误入 paths 降级 taps——仅当 path
            恰两个 token、均为显式端口、medium 均非液压；等价 tap 已存在
            则只删误入 path。其余 E-*（端口写错/terminal 中串/类型未登记/
            对账 E-RECON/未签认 E-SIGN）语义不可机械推导，残差上报
            （fail-closed）。
  轮内 V2/V13/V19  几何硬缺陷。P3=引擎从 intent 重推布局并叠加
            --optimize 第三阶段（#19 已并入；V2/V13/B1 在其能量函数内）。
            已叠加仍不绿 → 残差上报。
  轮内 V16  回读 PNG 每轮渲染后强制重出（1:1 viewBox，#19 两次踩坑的
            教训固化为卫生不变量），故 V16 命中即真缺陷，残差上报。
  轮内 V1/V3/V4/V6/V7/V8/V11/V12/V14/V15/V17/V18
       渲染器/走线器/布局参数所有，无输入侧机械修法，残差上报。

卫生不变量：每轮渲染后必重出 sheet-readback.png（Inkscape/Chrome 导出，
宽度默认从 SVG viewBox 推导，像素 1:1，V16 像素探测以此为准）。种子布局
仅在第一轮使用；P3 生效后布局一律由引擎重推，种子即弃。

工作区：所有改动发生在 --workdir 沙箱副本（skill 侧脚本/符号/catalog/
intent 逐份复制，符号从 skill 单源库平铺入沙箱供 catalog 锚定解析），
规范源文件一个不碰。注入演练 --inject a|b|c|d 只改沙箱副本（演练夹具
含 1# 实例名，是 #13/#12 的验收样例，新系统可自行扩展）。

受控清单模板：自动从 intent 同目录发现（唯一 *受控模板.yaml 即随沙箱
复制并启用 preflight 模板门禁；无则门禁未启用，不拦路）。

用法:
    python validate_driver.py --intent SRC.yaml [--workdir DIR] [--rounds N]
                              [--layout-seed SEED.json] [--ref REF.json]
                              [--inject a|b|c|d] [--optimize]
                              [--readback-w W] [--keep]
                              [--max-evals 200] [--max-steps 50]
                              [--max-seconds 30] [--polish-steps 0]
退出码: 0 完整证据通过 / 1 轮次耗尽仍有 fail（残差上报）/
        2 preflight 残差 / 3 工具链故障 / 4 必检证据或感知签认未齐备。
"""
import argparse
import filecmp
import hashlib
import glob
import io
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import threading
import tempfile
from contextlib import contextmanager
from pathlib import Path
from proofreading_evidence import verify_report
from readback_review import generate as generate_readback, verify_bundle

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
LIB = os.path.join(SKILL, 'assets', 'component-library')
CATALOG = 'component-catalog.json'
# 渲染器固定命名约定（工作目录口径，SKILL.md Phase 0）：
INTENT_NAME = '1#系统.intent.yaml'
LAYOUT_NAME = '1#系统.layout.json'
SVG_NAME = '1#系统原理图.svg'
READBACK = 'sheet-readback.png'

SCRIPTS = ['preflight.py', 'render_l0_sheet.py', 'validate_sheet.py', 'proofreading_evidence.py', 'browser_evidence.py', 'lead_geometry.py', 'stroke_checks.py', 'text_checks.py',
           'layout_engine.py', 'proto_optimize.py', 'topology_confirm.py',
           'rasterize_sheet.py', 'endpoint_usage.py', 'sheet_geometry.py', 'endpoint_checks.py', 'topology_reconciliation.py', 'layout_clearance.py', 'junction_semantics.py',
           'sheet_version.py', 'sheet_diff.py', 'readback_review.py']
PY = sys.executable
# 轮内几何硬缺陷 → P3；其余 fail 全部残差。
P3_IDS = {'V2', 'V13', 'V19'}


def progress(message):
    print('[driver] ' + message, file=sys.stderr, flush=True)


@contextmanager
def stage(stages, name):
    started = time.monotonic()
    item = {'stage': name, 'status': 'running'}
    stages.append(item)
    progress(name + ' started')
    try:
        yield item
    except Exception:
        item['status'] = 'failed'
        raise
    else:
        item['status'] = 'failed' if item.get('failure') else 'completed'
    finally:
        item['elapsed_s'] = round(time.monotonic() - started, 6)
        progress('%s %s %.3fs' % (name, item['status'], item['elapsed_s']))


def terminate_process_tree(proc):
    """终止本次工具的整个进程组，防孙进程继续持有输出管道。"""
    if os.name == 'posix':
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif os.name == 'nt':
        try:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                           capture_output=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            pass
        if proc.poll() is None:
            proc.kill()
    elif proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass


def run(cmd, cwd, timeout=600):
    """同时消费双管道，仅透出 stderr；等待父进程及管道均受同一超时约束。"""
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    process_options = ({'start_new_session': True} if os.name == 'posix' else
                       {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
                       if os.name == 'nt' else {})
    deadline = time.monotonic() + timeout
    proc = subprocess.Popen([str(c) for c in cmd], cwd=cwd, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='replace',
                            **process_options)
    output, errors = [], []
    stop_forwarding = threading.Event()

    def consume(pipe, sink, forward=False):
        try:
            for line in iter(pipe.readline, ''):
                sink.append(line)
                if forward and not stop_forwarding.is_set():
                    print(line, end='', file=sys.stderr, flush=True)
        finally:
            pipe.close()

    # 即便第三方主动逃离进程组且持有管道，收尾也不允许卡住驱动器退出。
    readers = [threading.Thread(target=consume, args=(proc.stdout, output), daemon=True),
               threading.Thread(target=consume, args=(proc.stderr, errors, True), daemon=True)]
    for reader in readers:
        reader.start()
    timed_out = False
    try:
        proc.wait(timeout=max(0, deadline - time.monotonic()))
        for reader in readers:
            reader.join(timeout=max(0, deadline - time.monotonic()))
        timed_out = any(reader.is_alive() for reader in readers)
    except subprocess.TimeoutExpired:
        timed_out = True
    finally:
        if timed_out:
            stop_forwarding.set()
            terminate_process_tree(proc)
            cleanup_deadline = time.monotonic() + 0.5
            for reader in readers:
                reader.join(timeout=max(0, cleanup_deadline - time.monotonic()))
    if timed_out:
        errors.append('超时(%gs): %s' % (timeout, ' '.join(map(str, cmd))))
    return (None if timed_out else proc.returncode), ''.join(output), ''.join(errors)


# ---------- 注入演练（只改沙箱副本；1# 验收样例夹具）----------

def inject_a(intent):
    """演练 A：把既有 taps 传感对搬进 paths——preflight 应报 E-MED，
    P1 应原样降级回 taps 后收敛。"""
    taps = intent.get('taps') or []
    hit = [t for t in taps
           if t.get('sensor') == 'PG-001.pressure_sense'
           and t.get('at') == 'ACV-001.charge_port']
    assert hit, '演练 A 需要既有 tap PG-001.pressure_sense@ACV-001.charge_port'
    taps.remove(hit[0])
    intent['taps'] = taps
    intent.setdefault('paths', []).append(
        ['PG-001.pressure_sense', 'ACV-001.charge_port'])
    return {'class': 'A 传感对误入 paths(E-MED×2)',
            'path': ['PG-001.pressure_sense', 'ACV-001.charge_port'],
            'removed_tap': hit[0]}


def inject_b(seed):
    """演练 B：种子布局几何缺陷——把蓄压器 ACC-001 垂直挪进行间走廊，
    让既有走线穿框（预期 V2/V13 类硬缺陷），驱动器应走 P3 引擎重推回绿。"""
    acc = seed['nodes'].get('ACC-001')
    assert acc, '演练 B 需要种子布局含 ACC-001'
    acc['y'] = int(acc['y']) + 170
    return {'class': 'B 种子布局几何缺陷(ACC-001 y+170)',
            'moved': 'ACC-001', 'dy': 170}


def inject_c(intent):
    """演练 C：terminal 实例串入 path 中段——preflight 应报 E-TERM；
    处方表对语义类输入缺陷无机械修法，预期残差上报退出 2。"""
    intent.setdefault('paths', []).append(
        ['USER-001.pressure_in', 'TANK-001', 'USER-002.pressure_in'])
    return {'class': 'C terminal 中串(E-TERM，无处方可修)',
            'path': ['USER-001.pressure_in', 'TANK-001', 'USER-002.pressure_in']}


def inject_d(tpl):
    """演练 D（#12 定案门禁）：模板侧种子错——蓄压器液压口对端从分配母线
    改挂用户供压母线。preflight 对账应双向抓出（intent 无背书 + 清单无落地），
    处方表无机械修法，预期残差上报退出 2。"""
    hit = 0
    for row in tpl.get('行') or []:
        if 'accumulator' in (row.get('口语名') or ''):
            for c in row.get('连接') or []:
                if c.get('对端') == '@分配':
                    c['对端'] = '@用户供压'
                    hit += 1
    assert hit, '演练 D 需要模板中蓄压器挂 @分配 的连接行'
    return {'class': 'D 模板种子错(蓄压器母线归属错，对账双向抓出)',
            'changed': 'ACC 对端 @分配 -> @用户供压'}


# ---------- 处方 P1：纯传感链误入 paths → 降级 taps ----------

def p1_taps_demotion(intent, catalog):
    """fail-closed：仅当 path 恰两 token、均为显式端口、medium 均非液压时，
    把它降级为 taps（sensor=首端, at=尾端）；等价 tap 已存在则只删误入
    path。其余一律不动，交残差上报。返回处方台账。"""
    types = {c['component_type']: c for c in catalog['components']}
    parts = intent.get('parts') or {}
    moved, kept = [], []
    for p in (intent.get('paths') or []):
        toks = [str(t) for t in p if not str(t).startswith('@')]
        ok = len(p) == 2 and len(toks) == 2 and all('.' in t for t in toks)
        if ok:
            for t in toks:
                inst, pid = t.split('.', 1)
                ct = types.get(parts.get(inst))
                ports = {q['id']: q for q in (ct or {}).get('ports', [])}
                if ports.get(pid, {}).get('medium', 'hydraulic') == 'hydraulic':
                    ok = False
                    break
        if not ok:
            kept.append(p)
            continue
        sensor, at = toks
        taps = intent.setdefault('taps', [])
        dup = any(t.get('sensor') == sensor and t.get('at') == at
                  for t in taps)
        if not dup:
            taps.append({'sensor': sensor, 'at': at})
        moved.append({'path': p, 'tap': {'sensor': sensor, 'at': at},
                      'deduped': dup})
    intent['paths'] = kept
    return moved


def dump_intent(intent, path):
    from ruamel.yaml import YAML
    y = YAML()
    y.default_flow_style = False
    y.allow_unicode = True
    y.width = 4096
    with io.open(path, 'w', encoding='utf-8') as f:
        y.dump(intent, f)


def load_yaml(path):
    from ruamel.yaml import YAML
    with io.open(path, encoding='utf-8') as f:
        return YAML(typ='safe', pure=True).load(f)


# ---------- 驱动主流程 ----------

GENERATED = ('readback.html','readback-manifest.json',LAYOUT_NAME, SVG_NAME, READBACK, '1#系统原理图-topology.json', '1#系统原理图-topology.md', 'validation-report.json',
             READBACK + '.evidence.json', 'validation-report.json.sha256',
             'convergence-report.json', 'layout-guard-report.json', 'ref.layout.json')
MANAGED_FILES = '.driver-managed-files.json'


def sync_file(src, dest):
    """内容未变则保留文件（含 mtime）；--keep 不重复复制整套符号。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.isfile(dest) and filecmp.cmp(src, dest, shallow=False):
        return False
    shutil.copy2(src, dest)
    return True


def invalidate_outputs(wd):
    for name in GENERATED:
        path = os.path.join(wd, name)
        if os.path.isfile(path) or os.path.islink(path):
            os.unlink(path)


def workspace_path(wd, name):
    root = Path(wd).resolve()
    dest = root.joinpath(name)
    if root not in dest.resolve().parents:
        raise ValueError('工作区文件路径越界: %s' % name)
    return dest


def setup_workdir(wd, keep=False):
    root, skill_root = Path(wd).resolve(), Path(SKILL).resolve()
    # 包括符号库等所有子目录、祖先及其符号链接，先检查再做任何写入。
    if root == skill_root or root in skill_root.parents or skill_root in root.parents:
        raise ValueError('工作区必须独立于整个 skill 规范源目录树及其父目录')
    wd = str(root)
    manifest = workspace_path(wd, MANAGED_FILES)
    previous = json.loads(manifest.read_text()) if manifest.is_file() else []
    if not isinstance(previous, list) or any(not isinstance(name, str) for name in previous):
        raise ValueError('工作区受管文件清单格式错误')
    for name in previous:
        workspace_path(wd, name)
    if root.is_dir() and not keep:
        if any(root.iterdir()) and not manifest.is_file():
            raise ValueError('拒绝清空非驱动器创建的非空目录；请换工作区或用 --keep 保留已有文件')
        shutil.rmtree(wd)
        previous = []
    root.mkdir(parents=True, exist_ok=True)
    wanted = {s: os.path.join(HERE, s) for s in SCRIPTS}
    for name in os.listdir(LIB):
        if name.endswith('.svg') or name == CATALOG:
            wanted[name] = os.path.join(LIB, name)
            if name.endswith('.svg'):
                wanted[os.path.join('symbols', name)] = os.path.join(LIB, name)
    schema_name = 'l0-input-contract.schema.json'
    schema = os.path.join(SKILL, 'assets', 'contracts', schema_name)
    if os.path.isfile(schema):
        wanted[os.path.join('assets', 'contracts', schema_name)] = schema
    # 校验所有目的路径后再复制，禁止 --keep 中的目录符号链接指向沙箱外。
    destinations = {name: workspace_path(wd, name) for name in wanted}
    for name in previous:
        dest = workspace_path(wd, name)
        if name not in wanted and dest.is_file():
            dest.unlink()
    copied = sum(sync_file(src, str(destinations[name])) for name, src in wanted.items())
    manifest.write_text(json.dumps(sorted(wanted), ensure_ascii=False), encoding='utf-8')
    invalidate_outputs(wd)
    # 本轮模板必须仅来自本轮输入目录；避免旧模板意外启用门禁。
    for path in glob.glob(os.path.join(wd, '*受控模板.yaml')):
        os.unlink(path)
    return {'kept': keep, 'copied_files': copied, 'reused_files': len(wanted) - copied}


def snapshot_inputs(args):
    """重建/失效处理前读取所有输入，允许输入文件本身位于工作区。"""
    files, assets, sources = {}, {}, []
    files[INTENT_NAME] = Path(args.intent).read_bytes()
    tpl_src = discover_template(args.intent)
    if tpl_src:
        files[os.path.basename(tpl_src)] = Path(tpl_src).read_bytes()
    if args.catalog:
        files[CATALOG] = Path(args.catalog).read_bytes()
    if args.layout_seed:
        seed_path = Path(args.layout_seed).resolve()
        seed = json.loads(seed_path.read_text(encoding='utf-8'))
        for node in seed.get('nodes', {}).values():
            ref = node.get('symbol')
            if not isinstance(ref, str):
                continue
            source = Path(ref) if os.path.isabs(ref) else seed_path.parent / ref
            source = source.resolve()
            if not source.is_file():
                continue
            if not os.path.isabs(ref) and seed_path.parent not in source.parents:
                raise ValueError('种子相对符号路径越界: %s' % ref)
            # 所有本地覆盖归入受控目录，不允许写出工作区或覆盖脚本。
            payload = source.read_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            dest = 'symbols/seed-%s/%s' % (digest, source.name)
            node['symbol'] = dest
            assets[dest] = payload
            sources.append({'source': str(source), 'destination': dest,
                            'sha256': hashlib.sha256(payload).hexdigest()})
        files[LAYOUT_NAME] = json.dumps(seed, ensure_ascii=False, indent=2).encode('utf-8')
    if args.ref and args.ref.lower() not in ('none', '-'):
        files['ref.layout.json'] = Path(args.ref).read_bytes()
    return files, assets, sources, tpl_src


def restore_inputs(wd, files, assets):
    for name, payload in {**files, **assets}.items():
        dest = workspace_path(wd, name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)


def discover_template(intent_src):
    """受控清单模板从 intent 同目录发现（唯一 *受控模板.yaml；无则 None）。"""
    hits = sorted(glob.glob(os.path.join(
        os.path.dirname(os.path.abspath(intent_src)), '*受控模板.yaml')))
    return hits[0] if len(hits) == 1 else None


def preflight_run(wd):
    rc, out, err = run([PY, 'preflight.py', INTENT_NAME,
                        '--catalog', CATALOG, '--json'], wd)
    if rc not in (0, 1) or not out.strip():
        raise RuntimeError('preflight 运行失败 rc=%s\n%s' % (rc, err))
    return json.loads(out)


def render_round(wd, use_seed, p3_armed, ref_path, readback_w,
                 budgets=None, step=None):
    """每轮派生物均失效后重建；预算终止仍要渲染并执行正式校验。"""
    step = step if step is not None else {}
    stages = step.setdefault('stages', [])
    for name in (SVG_NAME, READBACK, 'validation-report.json', 'layout-guard-report.json',
                 '1#系统原理图-topology.json', '1#系统原理图-topology.md'):
        path = Path(wd, name)
        if path.exists():
            path.unlink()
    with stage(stages, 'layout'):
        if use_seed:
            step['layout_source'] = 'seed'
        else:
            cmd = [PY, 'layout_engine.py', INTENT_NAME, CATALOG, ref_path,
                   '-o', LAYOUT_NAME, '--guard-report', 'layout-guard-report.json']
            if p3_armed:
                cmd.append('--optimize')
                for name, value in (budgets or {}).items():
                    cmd += ['--' + name.replace('_', '-'), str(value)]
            timeout = (budgets or {}).get('max_seconds', 30.0) + 60 if p3_armed else 60
            rc, out, err = run(cmd, wd, timeout=timeout)
            if rc != 0:
                raise RuntimeError('layout_engine 失败 rc=%s\n%s\n%s' % (rc, out, err))
            step['layout_source'] = 'engine' + ('+optimize' if p3_armed else '')
            guard = Path(wd, 'layout-guard-report.json')
            if guard.is_file():
                info = json.loads(guard.read_text(encoding='utf-8'))
                if 'optimization' in info:
                    step['optimization'] = info['optimization']
    with stage(stages, 'render'):
        rc, out, err = run([PY, 'render_l0_sheet.py', '.'], wd)
        if rc != 0 or not Path(wd, SVG_NAME).is_file():
            raise RuntimeError('render_l0_sheet 失败 rc=%s\n%s\n%s' % (rc, out, err))
        step['rendered'] = SVG_NAME
    with stage(stages, 'readback') as timing:
        cmd = [PY, 'rasterize_sheet.py', SVG_NAME, '-o', READBACK]
        if readback_w is not None:
            cmd += ['--width', str(readback_w)]
        rc, out, err = run(cmd, wd, timeout=120)
        if rc != 0 or not Path(wd, READBACK).is_file():
            step['readback'] = 'missing'
            step['readback_error'] = 'readback 导出失败 rc=%s\n%s' % (rc, err)
            # 保留失败，但仍收集无需像素的几何校验结果。
            timing['failure'] = step['readback_error']
        else:
            step['readback'] = 'regenerated'
            step['rasterization'] = json.loads(out)
    return step


def validate_run(wd):
    rep_path = Path(wd, 'validation-report.json')
    if rep_path.exists():
        rep_path.unlink()
    rc, out, err = run([PY, 'validate_sheet.py', '.'], wd)
    if rc not in (0, 1) or not rep_path.is_file():
        raise RuntimeError('validate 未成功产出本轮报告 rc=%s\n%s\n%s' % (rc, out, err))
    return rc, json.loads(rep_path.read_text(encoding='utf-8'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--intent', required=True, help='输入 intent；自动发现同目录受控模板')
    ap.add_argument('--workdir', help='独立工作目录；默认在系统临时目录新建沙箱')
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--layout-seed')
    ap.add_argument('--catalog', help='显式 catalog 覆盖；默认使用 skill 规范源')
    ap.add_argument('--ref', help='仅承载呈现文案的参照布局；none 表示无参照')
    ap.add_argument('--inject', choices=['a', 'b', 'c', 'd'])
    ap.add_argument('--optimize', action='store_true', help='首轮从规则重推并寻优，优先于种子')
    ap.add_argument('--max-evals', type=int, default=200)
    ap.add_argument('--max-steps', type=int, default=50)
    ap.add_argument('--max-seconds', type=float, default=30.0)
    ap.add_argument('--polish-steps', type=int, default=0)
    ap.add_argument('--readback-w', type=int, default=None,
                    help='回读宽度；默认按 SVG viewBox 推导，显式值必须为1:1')
    ap.add_argument('--keep', action='store_true', help='复用未变脚本/符号，刷新输入及本轮产物')
    ap.add_argument('--compare-against', help='已冻结的旧版 sheet_diff freeze 目录')
    ap.add_argument('--change-scope', help='本轮预期影响范围 JSON；必须与 --compare-against 配对')
    ap.add_argument('--comparison-output', help='新差分目录；缺省新建独立临时目录，禁止覆盖历史差分')
    args = ap.parse_args()
    from proto_optimize import validate_budgets
    budgets = dict(max_evals=args.max_evals, max_steps=args.max_steps,
                   max_seconds=args.max_seconds, polish_steps=args.polish_steps)
    try:
        validate_budgets(**budgets)
        if args.rounds < 1:
            raise ValueError('--rounds 必须 >= 1')
        if args.readback_w is not None and args.readback_w < 1:
            raise ValueError('--readback-w 必须 >= 1')
        if args.inject == 'b' and not args.layout_seed:
            raise ValueError('--inject b 需要 --layout-seed')
        if bool(args.compare_against) != bool(args.change_scope):
            raise ValueError('--compare-against 与 --change-scope 必须一起提供')
        if args.comparison_output and not args.compare_against:
            raise ValueError('--comparison-output 需要 --compare-against')
        if args.compare_against:
            baseline = Path(args.compare_against).resolve()
            if not (baseline / 'version.json').is_file():
                raise ValueError('比较基准必须先通过 sheet_diff freeze 冻结')
            if args.workdir:
                destination = Path(args.workdir).resolve()
                if baseline == destination or baseline in destination.parents or destination in baseline.parents:
                    raise ValueError('冻结基准必须独立于本轮驱动器工作目录')
            args.compare_against = str(baseline)
            args.change_scope = str(Path(args.change_scope).resolve())
            if args.comparison_output:
                args.comparison_output = str(Path(args.comparison_output).resolve())
        files, assets, sources, tpl_src = snapshot_inputs(args)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))

    started = time.monotonic()
    report = {'driver': 'validate-driver-1.2-bounded', 'converged': False,
              'validation_scope': 'automated_structure_geometry_and_pixel_checks',
              'perceptual_review': 'pending', 'stages': [],
              'rounds': [], 'prescriptions': [], 'residuals': [],
              'optimization_budgets': budgets, 'local_symbol_sources': sources,
              'inject': None, 'exit_code': None}
    report['automated_validation'] = {'status': 'not_checked'}
    report['delivery'] = {'ready': False, 'status': 'incomplete',
                          'blocking_checks': ['VALIDATION', 'PERCEPTUAL']}
    wd = str(Path(args.workdir).resolve()) if args.workdir else tempfile.mkdtemp(prefix='hydraulic-driver-')

    def done(code):
        if report.get('artifact_fingerprint') and not report.get('tool_failure'):
            try:
                with stage(report['stages'],'local_readback') as timing:
                    bundle=generate_readback(wd)
                    local=verify_bundle(wd)
                    if local['status']!='current':raise RuntimeError('Local readback evidence is invalidated: '+str(local))
                    report['local_readback']={**local,'elapsed_s':bundle['elapsed_s'],'rasterizations':0}
                    report['delivery']=verify_report(wd)['delivery']
                    timing['object_count']=len(bundle['objects']);timing['crop_count']=len(bundle['regions'])
                if code in (0,4):code=0 if report['delivery']['ready'] else 4
            except (OSError,ValueError,RuntimeError,KeyError) as error:
                report['local_readback']={'status':'invalidated','complete':False,'detail':str(error)}
                report['tool_failure']='Local readback generation failed: '+str(error)
                code=3
        else:
            report['local_readback']={'status':'not_generated','complete':False,'detail':'No verified final PNG/report was produced.'}

        if args.compare_against:
            report['change_comparison'] = {'status': 'not_checked', 'reason': 'Full validation did not produce usable final evidence.'}
            if code in (0, 1, 4) and Path(wd, 'validation-report.json').is_file():
                output = (Path(args.comparison_output) if args.comparison_output else
                          Path(tempfile.mkdtemp(prefix='hydraulic-change-')) / 'comparison')
                with stage(report['stages'], 'change_comparison'):
                    rc, out, err = run([PY, 'sheet_diff.py', 'compare', args.compare_against, wd,
                                        '--scope', args.change_scope, '--output', str(output)], wd, timeout=180)
                try:
                    summary = json.loads(out)
                except ValueError:
                    summary = {'status': 'not_comparable', 'reason': err or out}
                report['change_comparison'] = summary
                if rc not in (0, 1, 2):
                    report['tool_failure'] = '差分工具失败: ' + (err or out)
                    code = 3
                if rc != 0 or summary.get('status') != 'pass':
                    report['delivery'] = {'ready': False, 'status': 'incomplete',
                        'blocking_checks': sorted(set(report['delivery'].get('blocking_checks', [])) | {'CHANGE_SCOPE'})}
                    if code in (0, 4):
                        code = 1 if summary.get('status') == 'fail' else 4
        report['exit_code'] = code
        report['elapsed_s'] = round(time.monotonic() - started, 3)
        finish(report, wd)
        return code

    try:
        with stage(report['stages'], 'setup'):
            report['workspace'] = setup_workdir(wd, keep=args.keep)
            restore_inputs(wd, files, assets)
            intent = load_yaml(os.path.join(wd, INTENT_NAME))
            if args.inject == 'b':
                seed = json.loads(Path(wd, LAYOUT_NAME).read_text(encoding='utf-8'))
                report['inject'] = inject_b(seed)
                Path(wd, LAYOUT_NAME).write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding='utf-8')
            if args.inject in ('a', 'c'):
                report['inject'] = (inject_a(intent) if args.inject == 'a' else inject_c(intent))
                dump_intent(intent, os.path.join(wd, INTENT_NAME))
            elif args.inject == 'd':
                if not tpl_src:
                    raise ValueError('演练 D 需要 intent 同目录存在受控清单模板')
                tpl_path = os.path.join(wd, os.path.basename(tpl_src))
                tpl = load_yaml(tpl_path)
                report['inject'] = inject_d(tpl)
                dump_intent(tpl, tpl_path)
            catalog = json.loads(Path(wd, CATALOG).read_text(encoding='utf-8'))
        p1_used = 0
        while True:
            with stage(report['stages'], 'preflight'):
                rep = preflight_run(wd)
            errs = [finding for finding in rep['findings'] if finding['level'] == 'ERROR']
            report['preflight'] = {'status': rep['status'], 'findings': len(rep['findings'])}
            if not errs:
                break
            fixed = p1_taps_demotion(intent, catalog) if p1_used < 3 else []
            if fixed:
                p1_used += 1
                dump_intent(intent, os.path.join(wd, INTENT_NAME))
                report['prescriptions'].append(
                    {'stage': 'R0', 'id': 'P1', 'round': 0, 'applied': fixed,
                     'triggered_by': ['%s %s' % (f['id'], f['message']) for f in errs]})
                continue
            report['residuals'] = [dict(f, stage='R0', hint='无机械修法，需修正输入后重跑') for f in errs]
            return done(2)
        seed_pending = bool(args.layout_seed)
        p3_armed = args.optimize
        ref_path = 'ref.layout.json' if 'ref.layout.json' in files else '-'
        for r in range(1, args.rounds + 1):
            rnd = {'round': r, 'stages': []}
            report['rounds'].append(rnd)
            render_round(wd, use_seed=seed_pending and not p3_armed,
                         p3_armed=p3_armed, ref_path=ref_path,
                         readback_w=args.readback_w, budgets=budgets, step=rnd)
            seed_pending = False
            with stage(rnd['stages'], 'validate'):
                vrc, vrep = validate_run(wd)
            report['automated_validation'] = vrep.get('phases', {}).get(
                'automated', {'status': 'incomplete', 'detail': 'Legacy report lacks coverage evidence.'})
            report['perceptual_review'] = vrep.get('phases', {}).get('perceptual', {}).get('status', 'pending')
            report['delivery'] = vrep.get('delivery', {
                'ready': False, 'status': 'incomplete', 'blocking_checks': ['COVERAGE', 'PERCEPTUAL']})
            if vrep.get('report_schema') == 'proofreading-evidence-v1':
                verification = verify_report(wd)
                if verification['status'] != 'current':
                    raise RuntimeError('Validation artifact evidence is invalidated: %s' % verification)
            report['artifact_fingerprint'] = vrep.get('artifacts', {}).get('fingerprint')
            rnd['coverage'] = vrep.get('coverage', [])
            fails = [c for c in vrep['checks'] if c['result'] == 'fail']
            warns = [c for c in vrep['checks'] if c['result'] == 'warn']
            if rnd.get('readback_error'):
                fails.append({'id': 'READBACK', 'detail': rnd['readback_error']})
                report['tool_failure'] = rnd['readback_error']
            if vrc != 0 and not fails:
                raise RuntimeError('validate 非零退出但报告无 fail，拒绝收敛')
            rnd['fail_count'], rnd['warn_count'] = len(fails), len(warns)
            rnd['fails'] = [{'id': c['id'], 'detail': c['detail']} for c in fails]
            rnd['budget'] = {it['id']: it['status']
                             for it in vrep.get('composition_budget', {}).get('items', [])}
            if not fails:
                report['converged'] = True
                break
            residual = [c for c in fails if c['id'] not in P3_IDS]
            if residual or p3_armed or r == args.rounds:
                report['residuals'] = [
                    {'stage': 'round%d' % r, 'id': c['id'], 'detail': c['detail'],
                     'hint': P3_HINT if c['id'] in P3_IDS else '无自动修法，需检查残差'}
                    for c in fails]
                break
            report['prescriptions'].append(
                {'stage': 'round', 'id': 'P3', 'round': r,
                 'applied': ['引擎重推布局 + 有界寻优',
                             '触发: ' + '; '.join(c['id'] for c in fails)]})
            p3_armed = True
    except (RuntimeError, ValueError, OSError, AssertionError) as exc:
        report['tool_failure'] = str(exc)
        # 不在非工作区写报告；setup 的目录保护失败时只报告错误。
        if not os.path.isdir(wd) or not report.get('workspace'):
            progress(str(exc))
            return 3
        return done(3)
    return done(3 if report.get('tool_failure') else
                (1 if not report['converged'] else (0 if report['delivery']['ready'] else 4)))


P3_HINT = ('P3 已叠加仍不绿：几何缺陷超出邻域寻优可达域，'
           '需 AI 介入（走廊结构/规则层问题）')


def finish(report, wd):
    path = os.path.join(wd, 'convergence-report.json')
    with io.open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print('==== 校核驱动器 ====')
    print('工作区: %s' % wd)
    if report.get('inject'):
        print('注入: %s' % report['inject']['class'])
    print('preflight: %s' % report.get('preflight', {}).get('status'))
    for rnd in report['rounds']:
        print('  轮%d 布局=%-16s 回读=%s -> fail %d, warn %d'
              % (rnd['round'], rnd.get('layout_source', 'seed'),
                 rnd.get('readback', ''), rnd.get('fail_count', 0), rnd.get('warn_count', 0)))
        for fl in rnd.get('fails', []):
            print('       FAIL %s %s' % (fl['id'], fl['detail'][:80]))
    for p in report['prescriptions']:
        txt = '; '.join(
            x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
            for x in p['applied'])
        print('处方 %s @R%d: %s' % (p['id'], p['round'], txt[:100]))
    for r in report['residuals']:
        print('残差 %s [%s]: %s' % (r['id'], r['stage'],
                                    r.get('detail') or r.get('message', '')[:80]))
    local=report.get('local_readback',{})
    if local.get('status')=='current':
        print('局部回读: %d 个对象 / %d 张局部图，%.3fs -> %s' % (local['object_count'],local['crop_count'],local['elapsed_s'],os.path.join(wd,'readback.html')))
    if report.get('tool_failure'):
        print('工具链故障: %s' % report['tool_failure'])
    print('结论: %s  (%.1fs, 报告 -> %s)'
          % (('交付证据齐备' if report['delivery']['ready'] else
              '已执行校核零失败；交付证据未齐备（%s）' % ', '.join(report['delivery']['blocking_checks']))
             if report['converged'] else
             ('残差上报，需人工/AI 介入' if report['residuals'] else
              ('轮次耗尽仍有 fail' if report['exit_code'] == 1 else '工具链故障')),
             report['elapsed_s'], path))


if __name__ == '__main__':
    sys.exit(main())
