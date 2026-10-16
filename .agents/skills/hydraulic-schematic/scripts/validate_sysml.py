# -*- coding: utf-8 -*-
"""validate_sysml.py —— #52 窄版 SysML→L0 校核链路薄入口（部分实现/实验入口）。

状态披露：这是 #52 的**可独立部分**，不是全量 SysML 链路。#51/#52 的完整
验收（含真实 1# 模型转换）仍处于阻塞状态：完整 1# 模型比手写 intent 多出
ECO/接通位 QD/刹车支路，ECO 与接通位 QD 尚无目录类型、EMP overflow 不存在
——blocked-project.sysml 必须被准确拒绝（本入口在任何布局/渲染前退出），
而不是删除节点、假造目录或拿手写 intent 冒充转换成功。约定与状态见
references/sysml-l0.md；本入口不与整机 SysML 模板（render_aircraft_
schematic.py）混称通用 SysML 支持。

职责边界（薄入口，不复制任何校验/布局/渲染规则）：

  转换    复用 sysml_to_intent.convert_file（唯一转换实现，含同源 preflight
          与行号追溯 sidecar）；转换失败不发布任何 intent。
  校核    复用 validate_driver.py 子进程（preflight 门禁 → 布局 → 渲染 →
          校核 → 有界收敛，含模板门禁与种子符号实读，同一实现零漂移）。
  追溯    合并「SysML 源哈希+声明/connect 行号 → 转换 intent 哈希+输入锚点
          → 既有 SVG 拓扑 manifest」的可验证链，写 <workdir>/sysml-trace.json，
          并在本轮主流程内**执行并采纳**核验结论（不只提供独立 --verify）：
          驱动器即使返回 0/4，追溯链不成立（缺失/错配/哈希不同一/映射覆盖
          不全/处方改写输入）时本轮也不得按成功报告——退出码改 3，顶层
          ok=False、delivery.ready=False 并给出结构化原因；驱动器自身失败
          码（1/2/3）原样保留。
          当前映射口径（披露）：SVG 元件携带 intent 锚点（data-node /
          data-port / data-edge / data-input-anchor），**不携带
          data-sysml-line**；源行映射只存在于本报告与转换 sidecar，且只绑定
          其登记 intent_sha256 的转换产物。

安全纪律：

  - 工作目录先过与 validate_driver 同源的隔离检查（isolated_workspace），
    skill 源目录树、其祖先与 symlink 别名一律拒绝；未传 --workdir 时新建
    独立临时目录（独立 workdir 纪律不变）。
  - **输入先于一切清理/写入受保护**：SysML/catalog/布局 seed/--ref/受控
    模板的 realpath 与工作目录重叠（含 symlink 别名，如把 seed 放进受管
    工作区再 --keep 复用）时明确拒绝（退出码 5，输入字节不动）；不依赖
    驱动器晚一步的输入快照来保护。--ref 的 none/- 为"无参照"特殊值
    （与驱动器同口径），不入路径检查。独立输出子目录不包含输入的正常
    用法不受影响。
  - 转换失败在任何布局/渲染前退出；驱动器受管工作区中上一轮的
    SVG/PNG/报告按 validate_driver 的失效清单清理（只 unlink 固定产物名，
    绝不递归、绝不触碰受保护输入与 skill 源），旧成功产物不得冒充本轮
    结果；sysml-trace.json 只清理能核验为本工具产物的实例。
  - 受控清单模板从 **SysML 源同目录**发现（唯一 *受控模板.yaml），随转换
    intent 进入驱动器输入暂存目录——模板门禁与源目录同强度，不因临时目录
    绕过；签认等治理字段按模板内容原样生效，不由文件名推断成已签认。
  - extern 边界只认原生边界写法：系统 part 内 `port 'NAME';` 实体声明 +
    输入注释 `extern: NAME=PORT` 补充 L0 角色，缺省 extern={}，不从文件名/
    布局推断（见 sysml_to_intent）。
  - 输入 SysML、catalog、布局 seed 只读；转换 intent 落在临时暂存目录
    （输入，非产物）；本轮产物只在驱动器工作区。

CLI（冻结）：

    python validate_sysml.py --sysml IN.sysml [--catalog CATALOG.json]
                             [--layout-seed SEED.json] [--workdir DIR]
                             [--rounds N] [--ref R.json] [--optimize]
                             [--keep] [--max-evals N] [--max-steps N]
                             [--max-seconds S] [--polish-steps N]
                             [--readback-w W] [--json]
    python validate_sysml.py --verify WORKDIR    # 核验 sysml-trace.json 链

退出码：0 交付证据齐备（delivery.ready）/ 1 轮次耗尽仍有 fail /
        2 转换被诊断拦截或 preflight 残差（--json stage 区分 conversion /
        driver；转换失败发生在任何布局/渲染前）/ 3 工具链故障（含驱动器
        0/4 但追溯链核验不成立）/ 4 已执行校核零失败且追溯链成立但交付
        证据未齐备（如感知签认缺，delivery.ready 保持 false）/ 5 用法、
        IO 或路径安全拒绝（含 argparse 用法错误、输入与工作目录重叠）。
        --verify 模式独立计码：0 链 current / 1 链不成立或与当前产物不符。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import sysml_to_intent as sti          # noqa: E402  转换唯一实现
import validate_driver as vd           # noqa: E402  隔离判定/失效清单同源
import topology_reconciliation as tr   # noqa: E402  manifest 对账同源

GENERATOR = 'validate_sysml'
SCHEMA_VERSION = 2
TRACE_NAME = 'sysml-trace.json'
MANIFEST_NAME = '1#系统原理图-topology.json'
VALIDATION_REPORT = 'validation-report.json'

USAGE_EXIT = 5
CONVERSION_EXIT = 2
TOOL_EXIT = 3
DELIVERABLE_EXITS = (0, 4)

# 追溯链必需记录：缺任一即链不成立，不以部分记录冒充完整证据。
CHAIN_SECTIONS = ('source', 'template', 'conversion', 'driver', 'sheet')
SOURCE_FIELDS = ('path', 'sha256', 'hash_scope', 'declared')
CONVERSION_FIELDS = ('generator', 'status', 'catalog', 'intent_sha256',
                     'intent_yaml', 'hubs', 'externs', 'parts', 'edges',
                     'taps', 'unknown')
DRIVER_FIELDS = ('exit_code', 'converged', 'delivery', 'prescriptions',
                 'final_intent_sha256', 'input_modified_by_prescription',
                 'validation_report')


class UsageError(Exception):
    """用法/IO/路径安全问题：退出码 5。"""


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with open(path, 'rb') as fh:
        return sha256_bytes(fh.read())


def _realpath(path):
    return os.path.realpath(os.path.abspath(str(path)))


# ---------------------------------------------------------------------------
# 工作区：隔离判定、输入保护与上一轮产物失效
# ---------------------------------------------------------------------------

def resolve_workdir(raw):
    """解析并隔离检查 --workdir；未给定时新建独立临时目录。

    返回 (workdir, created_here)；created_here 标记的目录在转换失败且驱动器
    尚未接管时由调用方清理。"""
    if not raw:
        return tempfile.mkdtemp(prefix='hydraulic-sysml-'), True
    path = Path(raw)
    if path.exists() and not path.is_dir():
        raise UsageError('--workdir 已存在且不是目录: %s' % path)
    try:
        return vd.isolated_workspace(str(path)), False
    except ValueError as exc:
        raise UsageError(str(exc))


def ref_input_path(raw):
    """--ref 的有效路径；none/- 为"无参照"特殊值（与 validate_driver 同
    口径，大小写不敏感），不是路径，不入输入保护也不做文件检查。"""
    if not raw or raw.lower() in ('none', '-'):
        return None
    return raw


def protected_input_paths(args, template_src):
    """本轮全部输入的 realpath（SysML/catalog/布局 seed/--ref/受控模板）。

    在任何清理或写入之前先固定下来；与工作目录重叠即拒绝。--ref 指向的
    参照布局同样是本轮输入：放进（受管）工作区再 --keep 复用时，上一轮
    产物失效清单会删掉同名的 1#系统.layout.json——必须先拒绝而不是
    事后补救。"""
    return {_realpath(p) for p in (args.sysml, args.catalog,
                                   args.layout_seed,
                                   ref_input_path(args.ref), template_src)
            if p}


def input_overlaps_workdir(protected, workdir):
    """输入与工作目录重叠（含 symlink 别名）的清单；非空即路径安全拒绝。"""
    wd = Path(workdir)
    return sorted(p for p in protected
                  if p == str(wd) or wd in Path(p).parents)


def managed_workspace(workdir):
    """是否为驱动器受管工作区（隔离检查通过的既有沙箱）。"""
    wd = Path(workdir)
    if not wd.is_dir() or not (wd / vd.MANAGED_FILES).is_file():
        return False
    try:
        vd.isolated_workspace(str(wd))
    except ValueError:
        return False
    return True


def owned_trace(path):
    """sysml-trace.json 是否能核验为本工具产物（generator 标记）。"""
    try:
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return False
    return isinstance(data, dict) and data.get('generator') == GENERATOR


def invalidate_stale_products(workdir, protected=()):
    """清掉上一轮成功产物：只 unlink 驱动器失效清单内的固定产物名与本工具
    的 sysml-trace.json（文件/符号链接，绝不递归）。仅处理隔离检查通过的
    受管工作区；受保护输入、skill 源与非受管目录一律不触碰（调用前已拒绝
    输入与工作目录重叠，此处再按 realpath 兜底）。"""
    removed = []
    if not managed_workspace(workdir):
        return removed
    wd = Path(workdir)
    for name in list(vd.GENERATED) + [TRACE_NAME]:
        path = wd / name
        if not (path.is_file() or path.is_symlink()):
            continue
        if _realpath(path) in protected:
            continue
        if name == TRACE_NAME and not owned_trace(path):
            continue    # 别家的同名文件不是本工具产物，保持字节不变
        try:
            path.unlink()
            removed.append(name)
        except OSError:
            pass
    return removed


# ---------------------------------------------------------------------------
# 转换与驱动器输入暂存（模板门禁随源目录进入暂存，不因临时目录绕过）
# ---------------------------------------------------------------------------

def discover_source_template(sysml_path):
    """受控清单模板从 SysML 源同目录发现（与驱动器同一条发现规则）。"""
    return vd.discover_template(sysml_path)


def stage_driver_inputs(result, staging_dir, template_src):
    """转换 intent（trace 绑定哈希的确切字节）+ 源目录受控模板 → 暂存目录。

    暂存目录是本轮驱动器的输入目录：intent 固定命名为驱动器入口约定，
    模板同目录放置后由驱动器随沙箱复制并启用 preflight 门禁。"""
    staging = Path(staging_dir)
    staging.mkdir(parents=True, exist_ok=True)
    intent_yaml = (result.trace.get('output') or {}).get('yaml') \
        or sti.dump_intent_yaml(result.intent)
    intent_path = staging / vd.INTENT_NAME
    intent_path.write_bytes(intent_yaml.encode('utf-8'))
    if template_src:
        shutil.copy2(template_src, staging / Path(template_src).name)
    return intent_path


def run_driver(staged_intent, workdir, args):
    """子进程调用现有 validate_driver（同一实现：preflight 门禁/布局/渲染/
    校核/收敛/模板门禁/种子符号实读全部零复制）。"""
    cmd = [sys.executable, os.path.join(HERE, 'validate_driver.py'),
           '--intent', str(staged_intent), '--workdir', str(workdir)]
    if args.catalog:
        cmd += ['--catalog', str(args.catalog)]
    if args.layout_seed:
        cmd += ['--layout-seed', str(args.layout_seed)]
    if args.rounds is not None:
        cmd += ['--rounds', str(args.rounds)]
    if args.ref:
        cmd += ['--ref', str(args.ref)]
    if args.optimize:
        cmd.append('--optimize')
    if args.keep:
        cmd.append('--keep')
    if args.readback_w is not None:
        cmd += ['--readback-w', str(args.readback_w)]
    for flag, key in (('--max-evals', 'max_evals'),
                      ('--max-steps', 'max_steps'),
                      ('--max-seconds', 'max_seconds'),
                      ('--polish-steps', 'polish_steps')):
        value = getattr(args, key)
        if value is not None:
            cmd += [flag, str(value)]
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    if args.json:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                              encoding='utf-8', errors='replace')
        sys.stderr.write(proc.stdout or '')
        sys.stderr.write(proc.stderr or '')
        return proc.returncode
    return subprocess.run(cmd, env=env).returncode


# ---------------------------------------------------------------------------
# 追溯链：源哈希+行号 → intent 哈希+锚点 → SVG 拓扑 manifest
# ---------------------------------------------------------------------------

def _manifest_mismatches(manifest, intent, catalog):
    """manifest 与 declared_topology(intent) 的投影对账（id/锚点/端点）。"""
    expected = tr.declared_topology(intent, catalog)
    mismatch = []
    exp_nodes = {n['id']: n['type'] for n in expected['nodes']}
    got_nodes = {n['id']: n['type'] for n in manifest.get('nodes', [])}
    if exp_nodes != got_nodes:
        mismatch.append('nodes: declared=%s manifest=%s'
                        % (sorted(exp_nodes), sorted(got_nodes)))

    def edge_set(items):
        return sorted((e['anchor'], tuple(e['endpoints']))
                      for e in items if e.get('kind') in ('path', 'tap'))

    exp_edges, got_edges = edge_set(expected['edges']), \
        edge_set(manifest.get('edges', []))
    if exp_edges != got_edges:
        mismatch.append('edges: 仅 declared=%s / 仅 manifest=%s'
                        % ([e for e in exp_edges if e not in got_edges],
                           [e for e in got_edges if e not in exp_edges]))
    exp_ext = sorted(e['id'] for e in expected['externs'])
    got_ext = sorted(e['id'] for e in manifest.get('externs', []))
    if exp_ext != got_ext:
        mismatch.append('externs: declared=%s manifest=%s'
                        % (exp_ext, got_ext))
    return mismatch


def _load_workdir_catalog(workdir, recorded_path):
    local = Path(workdir) / vd.CATALOG
    if local.is_file():
        with open(local, encoding='utf-8') as fh:
            return json.load(fh)
    if recorded_path and os.path.isfile(recorded_path):
        with open(recorded_path, encoding='utf-8') as fh:
            return json.load(fh)
    return None


def build_trace_report(result, workdir, exit_code, args, template_src,
                       driver_report=None):
    """合并链报告：只登记当轮实际产物的哈希；未产出的部分如实缺席。"""
    trace = result.trace
    workdir = str(workdir)
    report = {
        'generator': GENERATOR,
        'schema_version': SCHEMA_VERSION,
        'status': 'driver_completed',
        'source': {
            'path': trace['input'].get('path'),
            'sha256': trace['input'].get('sha256'),
            'hash_scope': trace['input'].get('hash_scope'),
            'declared': result.declared,
        },
        'template': {
            'discovered': bool(template_src),
            'name': os.path.basename(template_src) if template_src else None,
            'sha256': sha256_file(template_src) if template_src else None,
            'note': '受控模板发现于 SysML 源同目录并随沙箱启用 preflight 门禁；'
                    '签认状态按模板内容生效，不由文件名推断',
        },
        'conversion': {
            'generator': sti.GENERATOR,
            'trace_schema_version': trace.get('schema_version'),
            'status': trace.get('status'),
            'catalog': trace.get('catalog'),
            'intent_sha256': (trace.get('output') or {}).get('intent_sha256'),
            'intent_yaml': (trace.get('output') or {}).get('yaml'),
            'hubs': trace.get('hubs', []),
            'externs': trace.get('externs', []),
            'parts': trace.get('parts', {}),
            'edges': trace.get('edges', []),
            'taps': trace.get('taps', []),
            'unknown': trace.get('unknown', []),
            'note': '源行映射（sysml_line/声明行号）只绑定本条 intent_sha256 '
                    '的转换产物；不套用到哈希不符的 intent 或 SVG',
        },
        'layout_seed': None,
        'driver': {
            'exit_code': exit_code,
            'report': 'convergence-report.json',
            'converged': None, 'delivery': None, 'prescriptions': None,
            'final_intent_sha256': None,
            'input_modified_by_prescription': None,
            'validation_report': None,
        },
        'sheet': {},
        'disclosures': {
            'svg_data_sysml_line': False,
            'note': 'SVG 元件携带 intent 锚点（data-node/data-port/data-edge/'
                    'data-input-anchor），不携带 data-sysml-line；源行追溯'
                    '仅存于本报告与转换 sidecar',
        },
        'exit_code': exit_code,
    }
    if args.layout_seed:
        report['layout_seed'] = {
            'path': _realpath(args.layout_seed),
            'sha256': sha256_file(args.layout_seed)
            if os.path.isfile(args.layout_seed) else None,
            'note': '本地符号实读与来源登记见 convergence-report.'
                    'local_symbol_sources',
        }

    wd = Path(workdir)
    intent_path = wd / vd.INTENT_NAME
    driver = report['driver']
    if intent_path.is_file():
        driver['final_intent_sha256'] = sha256_file(intent_path)
        driver['input_modified_by_prescription'] = \
            driver['final_intent_sha256'] != \
            report['conversion']['intent_sha256']
    if driver_report is not None:
        driver['converged'] = driver_report.get('converged')
        driver['delivery'] = driver_report.get('delivery')
        driver['prescriptions'] = driver_report.get('prescriptions')

    report_path = wd / VALIDATION_REPORT
    if report_path.is_file():
        entry = {'name': VALIDATION_REPORT,
                 'sha256': sha256_file(report_path)}
        try:
            parsed = json.loads(report_path.read_text(encoding='utf-8'))
            entry['artifacts_fingerprint'] = \
                (parsed.get('artifacts') or {}).get('fingerprint')
            entry['report_schema'] = parsed.get('report_schema')
            bound_input = ((parsed.get('artifacts') or {})
                           .get('files') or {}).get('input', {})
            entry['bound_intent_sha256'] = bound_input.get('sha256')
        except (ValueError, OSError):
            entry['parse_error'] = True
        driver['validation_report'] = entry

    svg_path = wd / vd.SVG_NAME
    manifest_path = wd / MANIFEST_NAME
    if svg_path.is_file():
        report['sheet']['svg'] = {'name': vd.SVG_NAME,
                                  'sha256': sha256_file(svg_path)}
    if manifest_path.is_file():
        report['sheet']['topology_manifest'] = {
            'name': MANIFEST_NAME, 'sha256': sha256_file(manifest_path)}
        mismatch = None
        catalog = _load_workdir_catalog(
            workdir, (trace.get('catalog') or {}).get('path'))
        if catalog is None:
            mismatch = ['catalog 不可读，无法对账 manifest']
        elif intent_path.is_file():
            try:
                from ruamel.yaml import YAML
                with open(intent_path, encoding='utf-8') as fh:
                    final_intent = YAML(typ='safe', pure=True).load(fh)
                mismatch = _manifest_mismatches(
                    json.loads(manifest_path.read_text(encoding='utf-8')),
                    final_intent, catalog)
            except (ValueError, OSError) as exc:
                mismatch = ['manifest 对账失败: %s' % exc]
        report['sheet']['manifest_matches_final_intent'] = not mismatch
        report['sheet']['manifest_mismatch'] = mismatch or []
    if not (svg_path.is_file() and manifest_path.is_file()):
        report['status'] = 'driver_incomplete_sheet'
    return report


def _declared_edge_endpoints(record, conv, catalog):
    """源行映射边端点按 tr.declared_topology 同一 main_path 语义展开。

    manifest 生成时把路径相邻对的首端点展开为 main_path 出口、末端点展开
    为 main_path 入口，且只展开裸实例 token；桥接边的源行记录保留 intent
    原始 token（如裸 PF-001）。直接比较两种表示会把合法桥接误判为缺映射
    ——比对前按同一位置语义规范化（首=out/末=in）；目录快照不可用时保持
    原样（fail-closed，不会把错配放行）。"""
    parts = {inst: rec.get('type')
             for inst, rec in (conv.get('parts') or {}).items()
             if isinstance(rec, dict)}
    types = {c.get('component_type'): c
             for c in (catalog or {}).get('components', [])}

    def expand(token, want):
        inst, dot, _ = str(token).partition('.')
        if not dot and inst in parts:
            main_path = (types.get(parts[inst]) or {}).get('main_path') or {}
            port = main_path.get(want)
            if port:
                return '%s.%s' % (inst, port)
        return token

    endpoints = record.get('endpoints') or []
    if len(endpoints) != 2:
        return list(endpoints)
    return [expand(endpoints[0], 'out'), expand(endpoints[1], 'in')]


def _edge_mapping_matches(record, edge, conv, catalog):
    """manifest 边是否与对应源行映射记录一致（规范化后比对；缺记录即否）。"""
    if not isinstance(record, dict):
        return False
    if edge.get('kind') == 'tap':
        # tap 端点在 intent/manifest 两侧同为原始 token，无展开语义。
        return [record.get('sensor'), record.get('at')] \
            == edge.get('endpoints')
    return _declared_edge_endpoints(record, conv, catalog) \
        == edge.get('endpoints')


def verify_chain(workdir, report):
    """核验 sysml-trace.json 与当前工作区互证；任何不完整/错配即 invalidated。

    必须全部成立才判 current：
      1. 必需记录/字段/状态齐备（source/template/conversion/driver/sheet）；
      2. 源文件仍在登记路径且哈希一致；
      3. 确定性重转换（复用纯转换接口）用**工作区 catalog 快照**（先核对其
         canonical SHA 与登记 conversion.catalog.sha256 一致，缺失/不符/
         回退默认目录均不成立）逐项复现登记的 intent 哈希/正文、declared、
         catalog 哈希与 hubs/externs/parts/edges/taps/unknown 源行映射——
         登记记录不得张冠李戴到别的模型或别的转换结果上；
      4. 转换 intent_sha256 与驱动器实际输入 final_intent_sha256 **同一**；
         处方改写过输入（input_modified_by_prescription）即不成立，不是仅
         披露后仍通过；
      5. manifest 的每个节点/边/边界都有对应源行映射记录（端点一致，双向
         覆盖），缺映射不能通过；桥接/裸实例边的源行记录保留 intent 原始
         token，比对前按 tr.declared_topology 同一 main_path 位置语义
         规范化——规范化不改源行记录，端点被改仍必报；
      6. SVG/manifest/校验报告与登记哈希一致，校验报告按 proofreading_
         evidence 口径 current，manifest 与最终 intent 对账一致。
    后处理改过已验证 SVG/报告的，旧链不得自称 current。"""
    reasons = []
    wd = Path(workdir)
    for key in CHAIN_SECTIONS:
        value = report.get(key)
        if not isinstance(value, dict) or not value:
            reasons.append('链缺必需记录: %s' % key)
    if reasons:
        return {'status': 'invalidated', 'reasons': reasons}
    src, conv, drv, sheet = (report['source'], report['conversion'],
                             report['driver'], report['sheet'])
    for field in SOURCE_FIELDS:
        if field not in src:
            reasons.append('source 缺字段: %s' % field)
    for field in CONVERSION_FIELDS:
        if field not in conv:
            reasons.append('conversion 缺字段: %s' % field)
    for field in DRIVER_FIELDS:
        if field not in drv:
            reasons.append('driver 缺字段: %s' % field)
    for key in ('svg', 'topology_manifest'):
        rec = sheet.get(key)
        if not isinstance(rec, dict) or not rec.get('sha256'):
            reasons.append('sheet 缺 %s 产物记录' % key)
    if 'discovered' not in report['template']:
        reasons.append('template 缺 discovered 记录')
    if conv.get('generator') != sti.GENERATOR or \
            conv.get('status') != 'converted':
        reasons.append('conversion 不是成功转换记录（generator=%r status=%r）'
                       % (conv.get('generator'), conv.get('status')))
    if src.get('hash_scope') != 'file-bytes':
        reasons.append('source 哈希口径不是 file-bytes: %r'
                       % src.get('hash_scope'))
    if reasons:
        return {'status': 'invalidated', 'reasons': reasons}

    # ---- intent 正文自洽（不依赖源文件在场的独立检查） ----
    if sha256_bytes((conv.get('intent_yaml') or '').encode('utf-8')) \
            != conv.get('intent_sha256'):
        reasons.append('intent_yaml 哈希与登记 intent_sha256 不符')

    # ---- 工作区 catalog 快照：重放与 manifest 端点规范化同用这一份 ----
    # --catalog 选定的目录由驱动器随沙箱复制为工作区 component-catalog.json
    # （未传 --catalog 时即规范源副本）。登记 conversion.catalog 只记
    # canonical SHA 不记 path，重放必须锚定**本轮实际使用的目录快照**并
    # 核对 canonical SHA 一致——回退默认目录会让任何显式 catalog 链被
    # 误判，跳过哈希检查则让调包后的快照冒充原目录。
    catalog_snapshot = None
    snapshot_path = wd / vd.CATALOG
    if snapshot_path.is_file():
        try:
            catalog_snapshot = json.loads(
                snapshot_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            reasons.append('工作区 catalog 快照不可读: %s' % exc)
    else:
        reasons.append('工作区 catalog 快照缺失，无法按本轮选定目录重转换')
    if catalog_snapshot is not None and \
            sti.catalog_canonical_sha256(catalog_snapshot) != \
            (conv.get('catalog') or {}).get('sha256'):
        reasons.append('工作区 catalog 快照与登记 conversion.catalog.sha256 '
                       '不符')

    # ---- 源文件与确定性重转换（用本轮选定目录的快照，不回退默认目录） ----
    source_path = src.get('path')
    if not source_path or not os.path.isfile(source_path):
        reasons.append('SysML 源文件不在登记路径: %s' % source_path)
    elif sha256_file(source_path) != src.get('sha256'):
        reasons.append('SysML 源文件内容与登记哈希不符')
    elif catalog_snapshot is None:
        pass    # 快照缺失/不可读已登记；无法按本轮目录重放，不回退默认目录
    else:
        try:
            fresh = sti.convert_file(source_path,
                                     catalog_path=str(snapshot_path))
        except (ValueError, FileNotFoundError) as exc:
            fresh = None
            reasons.append('确定性重转换失败: %s' % exc)
        if fresh is not None:
            if not fresh.ok:
                reasons.append('确定性重转换不再通过（当前源/目录状态下转换'
                               '被拦截）')
            else:
                ftrace = fresh.trace
                if ftrace['output'].get('intent_sha256') \
                        != conv.get('intent_sha256') \
                        or (ftrace['output'].get('yaml') or '') \
                        != conv.get('intent_yaml'):
                    reasons.append('登记 intent（哈希/正文）与源文件确定性'
                                   '重转换不符')
                if (ftrace.get('catalog') or {}).get('sha256') \
                        != (conv.get('catalog') or {}).get('sha256'):
                    reasons.append('catalog 哈希与登记 conversion.catalog.'
                                   'sha256 不符')
                if fresh.declared != src.get('declared'):
                    reasons.append('declared 与源文件重解析不符')
                for section in ('hubs', 'externs', 'parts', 'edges', 'taps',
                                'unknown'):
                    if ftrace.get(section) != conv.get(section):
                        reasons.append('源行映射 %s 与重转换不符（登记记录'
                                       '不得张冠李戴）' % section)

    # ---- 转换 intent 与驱动器实际输入同一（硬性等号，不只披露） ----
    if conv.get('intent_sha256') != drv.get('final_intent_sha256'):
        reasons.append('转换 intent_sha256 ≠ 驱动器实际输入 '
                       'final_intent_sha256（%s ≠ %s）：源行映射不得关联到'
                       '该图' % (str(conv.get('intent_sha256'))[:12],
                                 str(drv.get('final_intent_sha256'))[:12]))
    if drv.get('input_modified_by_prescription'):
        reasons.append('驱动器处方修改了沙箱输入：渲染 intent 与转换产物不同'
                       '一，源行映射对本轮图不成立')
    intent_path = wd / vd.INTENT_NAME
    if not intent_path.is_file():
        reasons.append('沙箱 intent 缺失')
    elif drv.get('final_intent_sha256') and \
            sha256_file(intent_path) != drv['final_intent_sha256']:
        reasons.append('沙箱 intent 已变更（与登记 final_intent_sha256 不符）')

    # ---- 源行映射覆盖：manifest 每个节点/边/边界都要有对应转换记录 ----
    manifest_path = wd / MANIFEST_NAME
    if not manifest_path.is_file():
        reasons.append('拓扑 manifest 缺失，映射覆盖无法核对')
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            manifest = None
            reasons.append('manifest 不可读: %s' % exc)
        if manifest is not None:
            for node in manifest.get('nodes', []):
                part = (conv.get('parts') or {}).get(node.get('id'))
                if not isinstance(part, dict) \
                        or not isinstance(part.get('sysml_line'), int):
                    reasons.append('节点 %s 缺源行映射记录（parts.%s.sysml_line）'
                                   % (node.get('id'), node.get('id')))
                elif part.get('type') != node.get('type'):
                    reasons.append('节点 %s 类型与转换记录不符' % node.get('id'))
            conv_edges = {e.get('anchor'): e
                          for e in conv.get('edges') or [] if isinstance(e, dict)}
            conv_taps = {t.get('anchor'): t
                         for t in conv.get('taps') or [] if isinstance(t, dict)}
            manifest_anchors = set()
            for edge in manifest.get('edges', []):
                anchor = edge.get('anchor')
                manifest_anchors.add(anchor)
                record = conv_taps.get(anchor) \
                    if edge.get('kind') == 'tap' \
                    else conv_edges.get(anchor)
                if not _edge_mapping_matches(record, edge, conv,
                                             catalog_snapshot):
                    reasons.append('manifest 边 %s 缺对应源行映射记录或端点'
                                   '不符' % anchor)
            for anchor in sorted(conv_edges):
                if anchor not in manifest_anchors:
                    reasons.append('转换边 %s 未落在 manifest（映射覆盖不全）'
                                   % anchor)
            for anchor in sorted(conv_taps):
                if anchor not in manifest_anchors:
                    reasons.append('转换 tap %s 未落在 manifest' % anchor)
            extern_names = {e.get('name')
                            for e in conv.get('externs') or []}
            for ext in manifest.get('externs', []):
                if ext.get('id') not in extern_names:
                    reasons.append('边界 %s 缺 extern 声明记录' % ext.get('id'))

    # ---- 产物哈希与校验报告 current ----
    for key, fallback in (('svg', vd.SVG_NAME),
                          ('topology_manifest', MANIFEST_NAME)):
        rec = sheet.get(key) or {}
        if not rec.get('sha256'):
            continue
        path = wd / rec.get('name', fallback)
        if not path.is_file():
            reasons.append('%s 缺失，链不完整' % rec.get('name', fallback))
        elif sha256_file(path) != rec['sha256']:
            reasons.append('%s 已变更，旧指纹不得冒充当前产物'
                           % rec.get('name', fallback))
    if sheet.get('manifest_matches_final_intent') is not True:
        reasons.append('登记的 manifest 对账结论不是一致: %s'
                       % (sheet.get('manifest_mismatch')))
    report_path = wd / VALIDATION_REPORT
    if not report_path.is_file():
        reasons.append('validation-report.json 缺失（本轮无已验证 SVG）')
    else:
        entry = drv.get('validation_report') or {}
        if not entry.get('sha256'):
            reasons.append('driver.validation_report 缺哈希登记')
        elif sha256_file(report_path) != entry['sha256']:
            reasons.append('validation-report.json 已变更')
        from proofreading_evidence import verify_report
        vr = verify_report(str(wd))
        if vr.get('status') != 'current':
            reasons.append('校验证据已失效: %s'
                           % (vr.get('detail') or vr.get('changed')))

    return {'status': 'current' if not reasons else 'invalidated',
            'reasons': reasons}


def write_trace_report(workdir, report):
    """落盘合并链报告（原子写）；拒绝覆盖非本工具产物的同名文件。"""
    path = Path(workdir) / TRACE_NAME
    if path.exists() and not owned_trace(path):
        raise UsageError('拒绝覆盖: %s 已存在且不是本工具产物（用户文件保护）'
                         % path)
    payload = (json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True)
               + '\n').encode('utf-8')
    tmp = '%s.tmp-%d' % (path, os.getpid())
    with open(tmp, 'wb') as fh:
        fh.write(payload)
    os.replace(tmp, path)
    return str(path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        sys.stderr.write('validate_sysml: %s\n' % message)
        raise SystemExit(USAGE_EXIT)


def build_parser():
    parser = _Parser(
        prog='validate_sysml.py',
        description='#52 窄版 SysML→L0 校核链路薄入口（转换→preflight→'
                    'validate_driver→追溯合并；见 references/sysml-l0.md）')
    parser.add_argument('--sysml', help='输入 .sysml（窄文法；唯一转换来源）')
    parser.add_argument('--catalog', default=None,
                        help='component-catalog.json（缺省锚定 skill 规范源；'
                             '转换与驱动器同用一份）')
    parser.add_argument('--layout-seed', default=None,
                        help='可复用布局 seed（来源登记进 convergence-report）')
    parser.add_argument('--workdir', default=None,
                        help='独立工作目录；缺省新建临时目录')
    parser.add_argument('--rounds', type=int, default=None)
    parser.add_argument('--ref', default=None,
                        help='参照布局（原样转发 validate_driver；none/- 表'
                             '示无参照，作为本轮输入纳入重叠保护）')
    parser.add_argument('--optimize', action='store_true')
    parser.add_argument('--keep', action='store_true')
    parser.add_argument('--max-evals', type=int, default=None)
    parser.add_argument('--max-steps', type=int, default=None)
    parser.add_argument('--max-seconds', type=float, default=None)
    parser.add_argument('--polish-steps', type=int, default=None)
    parser.add_argument('--readback-w', type=int, default=None)
    parser.add_argument('--json', action='store_true', help='机器可读输出')
    parser.add_argument('--verify', metavar='WORKDIR', default=None,
                        help='核验该工作区的 sysml-trace.json 链后退出'
                             '（0 current / 1 不成立）')
    return parser


def _emit_json(payload):
    print(json.dumps(payload, ensure_ascii=False, indent=1))


def main(argv=None):
    sys.dont_write_bytecode = True
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    if args.verify:
        path = Path(args.verify) / TRACE_NAME
        if not path.is_file():
            print('sysml-trace.json 不存在: %s' % path, file=sys.stderr)
            return 1
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            print('sysml-trace.json 不可读: %s' % exc, file=sys.stderr)
            return 1
        verdict = verify_chain(args.verify, report)
        _emit_json(verdict)
        return 0 if verdict['status'] == 'current' else 1

    if not args.sysml:
        build_parser().error('--sysml 必填（或用 --verify 核验既有链）')
    if not os.path.isfile(args.sysml):
        print('输入文件不存在: %s' % args.sysml, file=sys.stderr)
        return USAGE_EXIT
    if args.catalog and not os.path.isfile(args.catalog):
        print('catalog 文件不存在: %s' % args.catalog, file=sys.stderr)
        return USAGE_EXIT
    if args.layout_seed and not os.path.isfile(args.layout_seed):
        print('布局 seed 不存在: %s' % args.layout_seed, file=sys.stderr)
        return USAGE_EXIT
    ref_path = ref_input_path(args.ref)
    if ref_path and not os.path.isfile(ref_path):
        print('--ref 文件不存在: %s' % ref_path, file=sys.stderr)
        return USAGE_EXIT
    try:
        workdir, created_here = resolve_workdir(args.workdir)
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return USAGE_EXIT

    def cleanup_created():
        if created_here:
            try:
                os.rmdir(workdir)
            except OSError:
                pass

    # 输入先于一切清理/写入受保护：与工作目录重叠（含 symlink 别名）即
    # 路径安全拒绝，输入字节不动（不依赖驱动器晚一步的输入快照）。
    template_src = discover_source_template(args.sysml)
    protected = protected_input_paths(args, template_src)
    overlaps = input_overlaps_workdir(protected, workdir)
    if overlaps:
        print('[validate_sysml] 拒绝：输入位于工作目录内，任何清理都会威胁'
              '输入（realpath 重叠: %s）；请另选 --workdir'
              % ', '.join(overlaps), file=sys.stderr)
        cleanup_created()
        return USAGE_EXIT

    try:
        result = sti.convert_file(args.sysml, catalog_path=args.catalog)
    except (ValueError, FileNotFoundError) as exc:
        print('转换入口失败: %s' % exc, file=sys.stderr)
        cleanup_created()
        return USAGE_EXIT

    if not result.ok:
        removed = invalidate_stale_products(workdir, protected)
        failure = {
            'generator': GENERATOR, 'schema_version': SCHEMA_VERSION,
            'status': 'conversion_blocked',
            'source': {'path': result.source_name,
                       'sha256': result.trace['input'].get('sha256'),
                       'hash_scope': result.trace['input'].get('hash_scope'),
                       'declared': result.declared},
            'diagnostics': result.diagnostics,
            'cleaned_stale_products': removed,
            'note': '转换在任何布局/渲染前被拦截；上一轮成功产物已失效，'
                    '不构成本轮产物',
            'exit_code': CONVERSION_EXIT,
        }
        if managed_workspace(workdir):
            try:
                write_trace_report(workdir, failure)
            except UsageError as exc:
                print('注意: %s' % exc, file=sys.stderr)
        if args.json:
            _emit_json({'tool': GENERATOR, 'stage': 'conversion',
                        'ok': False, 'exit_code': CONVERSION_EXIT,
                        'workdir': workdir, 'source': failure['source'],
                        'diagnostics': result.diagnostics,
                        'cleaned_stale_products': removed,
                        'intent': None, 'delivery': None})
        else:
            print('[validate_sysml] 转换被拦截（%d 条 ERROR），任何布局/渲染'
                  '均未启动' % len(result.error_ids()))
            for name in removed:
                print('  已失效上一轮产物: %s' % name)
            for d in result.diagnostics:
                if d['level'] == 'ERROR':
                    print('  %-32s %-5s %s'
                          % (d['id'], d['line'] if d['line'] else '--',
                             d['message']))
        cleanup_created()
        return CONVERSION_EXIT

    staging = tempfile.mkdtemp(prefix='hydraulic-sysml-input-')
    try:
        staged_intent = stage_driver_inputs(result, staging, template_src)
        invalidate_stale_products(workdir, protected)   # 旧链先行失效
        exit_code = run_driver(staged_intent, workdir, args)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # ---- 追溯链合并 + 本轮主流程内执行/采纳核验（不只独立 --verify） ----
    driver_report = None
    trace_report = None
    trace_path = None
    verdict = None
    if managed_workspace(workdir):
        report_path = Path(workdir) / 'convergence-report.json'
        if report_path.is_file():
            try:
                driver_report = json.loads(
                    report_path.read_text(encoding='utf-8'))
            except ValueError:
                driver_report = None
        try:
            trace_report = build_trace_report(result, workdir, exit_code,
                                              args, template_src,
                                              driver_report)
            verdict = verify_chain(workdir, trace_report)
            trace_report['verification'] = verdict
            trace_path = write_trace_report(workdir, trace_report)
        except UsageError as exc:
            print('[validate_sysml] %s' % exc, file=sys.stderr)
            return USAGE_EXIT
    else:
        # 驱动器未接管工作区（如沙箱建立失败）：不向用户目录写任何链报告。
        print('[validate_sysml] 工作区未被驱动器接管，未写 %s（仅上报）'
              % TRACE_NAME, file=sys.stderr)

    delivery = (driver_report or {}).get('delivery')
    chain_ok = bool(verdict) and verdict['status'] == 'current'
    if exit_code in DELIVERABLE_EXITS and not chain_ok:
        # 驱动器即使 0/4：追溯缺失/错配不能按成功报告，原因明确记录。
        for reason in (verdict or {}).get('reasons', []):
            print('[validate_sysml] 追溯链不成立: %s' % reason,
                  file=sys.stderr)
        print('[validate_sysml] 追溯链核验失败，驱动器退出码 %d 不作为本轮'
              '成功结论' % exit_code, file=sys.stderr)
        exit_code = TOOL_EXIT
    ok = exit_code in DELIVERABLE_EXITS and chain_ok
    if not ok and isinstance(delivery, dict) and delivery.get('ready'):
        delivery = dict(delivery, ready=False, status='incomplete',
                        blocking_checks=sorted(
                            set(delivery.get('blocking_checks') or [])
                            | {'SYSML_TRACE'}))

    if args.json:
        _emit_json({'tool': GENERATOR, 'stage': 'driver',
                    'ok': ok, 'exit_code': exit_code, 'workdir': workdir,
                    'source': {'path': result.source_name,
                               'sha256': result.trace['input']['sha256']},
                    'conversion': {'ok': True,
                                   'intent_sha256':
                                       (result.trace.get('output') or {})
                                       .get('intent_sha256'),
                                   'externs': result.trace.get('externs', [])},
                    'converged': (driver_report or {}).get('converged'),
                    'delivery': delivery,
                    'verification': verdict,
                    'template': (trace_report or {}).get('template'),
                    'sheet': (trace_report or {}).get('sheet'),
                    'trace': trace_path})
    else:
        print('[validate_sysml] %s -> 驱动器完成（退出码 %d，追溯链: %s）'
              % (os.path.basename(args.sysml), exit_code,
                 (verdict or {}).get('status', 'not_run')))
        if trace_path:
            print('  追溯链: %s' % trace_path)
        for reason in (verdict or {}).get('reasons', []):
            print('  追溯链不成立: %s' % reason)
        if trace_report and trace_report['sheet'].get('svg'):
            print('  本轮产物: %s（manifest 对账: %s）'
                  % (vd.SVG_NAME,
                     '一致' if trace_report['sheet']
                     .get('manifest_matches_final_intent') else '不符'))
        if delivery is not None:
            print('  delivery.ready=%s%s' % (delivery.get('ready'),
                  '' if delivery.get('ready') else
                  '（缺: %s）' % ', '.join(delivery.get('blocking_checks', []))))
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
