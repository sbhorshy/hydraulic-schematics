# -*- coding: utf-8 -*-
"""sysml_to_intent.py —— #51 窄版 SysML→L0 intent 转换器（部分实现/实验入口）。

状态披露：这是 #51 的**局部实现**，不是全量 SysML 链路。支持范围、窄文法
约定、折叠映射与证据边界以 references/sysml-l0.md 为准；#51/#52 的完整
验收（含真实 1# 模型转换）仍处于阻塞状态，blocked-project.sysml（1#系统
.sysml 的逐字节冻结副本）必须被本工具准确拒绝，而不是删除节点/连接、
假造目录或拿手写 intent 冒充转换成功。#52 的 validate_sysml.py 薄入口
（转换→preflight→validate_driver→追溯合并）复用本模块做链路接入，本模块
仍是唯一转换实现。

语法层零重复：词法/语法一律复用同目录 sysml_parser.parse（GLM 实现、
Codex 审核集成），本模块只做拓扑转换、preflight 与追溯。

公开 API（冻结，勿改名——references/sysml-l0.md 已记录本契约）：

    convert_text(text, catalog=None, source_name=None, source_sha256=None)
        -> ConversionResult
        纯转换：不写任何文件。catalog 为已载入 dict（缺省实读 skill 自带
        component-catalog.json）。result.ok=True 当且仅当转换无 ERROR 且
        真实同源 preflight（preflight.preflight，与渲染器/CLI 同一函数）
        无 ERROR；此时 result.intent 为可发布的 intent dict；否则
        result.intent=None（不发布失败 intent），诊断与已解析声明披露在
        result.diagnostics / result.declared / result.trace。
        source_sha256：文件入口传入**源文件原始字节**哈希（hash_scope=
        'file-bytes'）；缺省对 text 参数哈希（hash_scope='text'，换行等
        规范化后的文本，不冒称源文件哈希）。
    convert_file(sysml_path, catalog_path=None) -> ConversionResult
        convert_text 的文件入口：按**原始字节**计算源哈希（LF/CRLF/BOM
        均与磁盘文件一致），utf-8-sig 解码供 parser（1-based 行号不受
        影响），路径按给定值解析（不依赖 repo cwd）。
    publish(result, output_path, trace_path=None, protected_paths=()) -> dict
        把成功结果写为 intent + 追溯 sidecar（缺省 <output>.trace.json，
        也可显式指定）。两个目标都先做安全预检：目录拒绝；已存在但无法
        核验为本文工具产物的文件拒绝覆盖（intent 的所有权按**调用指定的
        trace 或缺省 sidecar** 的 generator 标记+intent 哈希绑定核验）；
        既有 trace 目标还须**绑定当前输出**（output.path 一致）——本工具
        生成但归属其他输出的 sidecar 保持字节不变并明确拒绝，"本工具曾
        生成"不等于"属于本次输出"；输入/catalog/参照等 protected_paths
        与目标相撞或别名即拒绝；trace 写失败回滚 intent（恢复旧字节或
        删除新写）；转换失败时只清理能核验为**当前输出**所有的陈旧成功
        产物，绝不删除用户无关文件。
    topology_diff(converted_intent, reference_intent, catalog) -> dict
        两个成功 intent 的拓扑对账：节点/边按无向端点对多重集归一化
        （裸实例按 topology_reconciliation 同一 main_path 语义展开），
        缺失与新增分列。失败转换不得调用本函数宣称一致。

CLI（冻结）：

    python sysml_to_intent.py IN.sysml [-o OUT.intent.yaml]
                                        [--catalog CATALOG.json]
                                        [--trace TRACE.json]
                                        [--diff REF.intent.yaml]
                                        [--json]
    缺省 -o = 输入同目录 <stem>.intent.yaml；缺省 --trace = <output>.trace.json；
    --catalog 缺省锚定 skill 规范源（assets/component-library/component-catalog.json）。
    输入/catalog/--diff 参照与输出目标相撞一律拒绝。
    退出码：0 转换并发布成功（--diff 差异只披露不拦截）；
            1 转换被诊断拦截（含 --diff 时同样不发布并清理本工具陈旧成功
            输出，不宣称与手写 intent 一致）；
            2 用法/IO/发布安全拒绝。

转换语义（详见 references/sysml-l0.md）：
  - 只接受唯一 system part；part def 名称跨作用域重复即拒（遮蔽歧义）；
    系统成员必须是 typed 实例；未引用的 def 不生成实例。
  - 实例类型 = 同名 part def；def 有内部结构时必须逐字匹配冻结折叠模板
    （filter_line_shutoff_dp / _return / _case_drain 本体结构、return_filter），
    端点段数、成员/边界端口存在性、内部连接多重集任一偏差即拒，不按类型名
    无条件丢弃内部连接；catalog 已登记类型携带不可核内部结构同样拒绝
    （case_drain_filter 装配+串联单向阀形态目录无对应符号 → 拒绝，见文档）。
  - def 声明端口必须 ⊆ catalog 该类型端口（EMP-001.overflow 因此被点名拒绝）。
  - 母线还原只认输入注释中的枢纽声明 @NAME=INST[.port]（NAME 全大写），
    不写死任何 1# 实例映射；无枢纽声明且全显式端口的模型直接转换。
    每个已声明的端口枢纽都补回到真实端口的连接（spoke），唯一例外是
    main_path 进出口各绑一条母线、且只经母线接线时以一条
    [bus(in), INST, bus(out)] 桥接路径**等价合并**（不吞边）。
  - 元件枢纽（@NAME=INST）仅在目录类型恰好一个非 sensing_only 液压端口时
    可用（枢纽=该端口的汇流抽象，唯一绑定）；多端口/传感元件枢纽无法唯一
    绑定真实端口，一律 ERROR 拒绝——bare 辐条不允许绕过元件。
  - SysML connect 的 to 不是液流方向：裸 inline 实例仅在 main_path 端口
    可由对端介质等已声明约束**唯一**确定时转换，否则点名诊断拒绝，不按
    出现顺序猜。
  - sensing_only 组件的连接按 P1 语义归 taps；taps 两端介质必须同质且属
    {hydraulic, pneumatic}，机械/电气端口与混介质一律 ERROR（不因
    sensing_only 绕过，不以 WARN 放行）；paths 内出现非 hydraulic 端口
    一律拒绝；一口压力表不会伪造第二个贯通口。
  - maturity 恒为 concept；catalog 标识实读目录；extern 边界采用本仓库
    原生边界写法（#52 窄约定）：系统 part 内声明 `port 'NAME';` 作 SysML
    实体，connect 直接引用该端口；注释 `extern: NAME=PORT` 只补充 L0 边界
    角色（端口值受 L0 契约 schema 枚举约束）。**仅有注释而无系统端口声明
    一律拒绝**（注释不替代 SysML 实体）；缺省 extern={}，绝不从文件名/
    布局推断；未引用的已声明边界按未连接端口披露进 intent unknown（来源
    与真实行号记入 sidecar），绝不借 unknown 删除真实连线。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import sysml_parser as sp          # noqa: E402  语法层唯一来源
import preflight as pf             # noqa: E402  真实同源预检

L0_VERSION = '1.1'
GENERATOR = 'sysml_to_intent'
TRACE_SCHEMA_VERSION = 2
DEFAULT_CATALOG_CANDIDATES = (
    os.path.join(HERE, '..', 'assets', 'component-library', 'component-catalog.json'),
    os.path.join(HERE, 'component-catalog.json'),
)

INST_NAME_RE = re.compile(r'^[A-Z][A-Za-z0-9_-]*$')
HUB_DECL_RE = re.compile(r'@([A-Z][A-Z0-9_]*)\s*=\s*([A-Za-z0-9_.\-]+)')
UNKNOWN_MARK_RE = re.compile(r'unknown:\s*([A-Za-z0-9][A-Za-z0-9\-_.]*)')
# extern 边界（#52 窄约定，原生边界写法）：系统 part 内 `port 'NAME';` 是
# SysML 实体声明，注释行 `extern: NAME=PORT` 只补充 L0 边界角色（PORT 为
# 该边界的端口标签，L0 契约 schema 枚举 inlet/outlet/return 兜底校验）。
# 只认输入注释，不从文件名或布局推断；仅有注释而无对应系统端口声明一律
# 拒绝（E-SYSML-EXTERN-UNDECLARED）；未声明 extern 的名字按普通实例解析
# 照常报 E-SYSML-REF。
EXTERN_DECL_RE = re.compile(
    r'\bextern:\s*([A-Za-z][A-Za-z0-9_.\-]*)\s*=\s*([A-Za-z0-9_\-]+)')
# 文档化待决标记（references/sysml-l0.md §6）：注释行命中即按待决项搬运，
# 保留原文与真实源行；与 unknown: 标记同行的以结构化 slug 为准，不重复记。
PENDING_MARKERS = ('待工程确认', '待确认', '待定', '待同步',
                   '去向未声明', '未声明', '悬空', '未建模')


# ---------------------------------------------------------------------------
# 冻结折叠模板（既有约定：RF 折叠为已登记叶类型；改内部拓扑即拒）。
# members: 成员名 -> 成员类型名；edges: 无序端点对多重集（端点 = 边界口名
# 或 (成员名, 端口名)）；boundary: def 边界口（须与声明端口集合完全一致）；
# 带内部结构的成员类型必须能按同名模板递归核验；核验含端点段数、成员/
# 边界端口存在性与连接多重性，不去重不截断。
# 依据（披露）：1# 手写 intent 的 RF-001 = filter_line_shutoff_dp_return_bypass
# （旁通符号 100x194），故 return_filter 按旁通结构折叠；CDF-001 =
# filter_line_shutoff_dp_case_drain（带压差指示符号 filter-line-shutoff-dp.svg），
# 目录旧叶类型 case_drain_filter 是无压差符号（filter-line-shutoff-stroke.svg），
# 且"本体+串联单向阀"装配形态目录无对应符号——该形态拒绝折叠（fail-closed），
# CDF 直用本体类型 filter_line_shutoff_dp_case_drain（恒等复合核验）。
# ---------------------------------------------------------------------------

class FoldTemplate:
    def __init__(self, target, boundary, members, edges):
        self.target = target
        self.boundary = tuple(sorted(boundary))
        self.members = dict(members)
        self.edges = tuple(edges)


def _dp_body_edges():
    return (
        ('inlet', ('element', 'inlet')),
        (('element', 'outlet'), 'outlet'),
        (('sensor', 'sense_a'), ('element', 'inlet')),
        (('sensor', 'sense_b'), ('element', 'outlet')),
    )


FOLD_TEMPLATES = {
    'filter_line_shutoff_dp': FoldTemplate(
        target='filter_line_shutoff_dp', boundary=('inlet', 'outlet'),
        members={'element': 'filter_element', 'sensor': 'dp_sensor'},
        edges=_dp_body_edges()),
    'filter_line_shutoff_dp_return': FoldTemplate(
        target='filter_line_shutoff_dp_return', boundary=('inlet', 'outlet'),
        members={'element': 'filter_element', 'sensor': 'dp_sensor'},
        edges=_dp_body_edges()),
    'filter_line_shutoff_dp_case_drain': FoldTemplate(
        target='filter_line_shutoff_dp_case_drain', boundary=('inlet', 'outlet'),
        members={'element': 'filter_element', 'sensor': 'dp_sensor'},
        edges=_dp_body_edges()),
    'return_filter': FoldTemplate(
        target='filter_line_shutoff_dp_return_bypass', boundary=('inlet', 'outlet'),
        members={'body': 'filter_line_shutoff_dp_return', 'cv': 'check_valve_spring'},
        edges=(
            ('inlet', ('body', 'inlet')),
            ('inlet', ('cv', 'inlet')),
            (('body', 'outlet'), 'outlet'),
            (('cv', 'outlet'), 'outlet'),
        )),
}


# ---------------------------------------------------------------------------
# 结果与工具
# ---------------------------------------------------------------------------

class ConversionResult:
    """convert_* 的出口。ok=True 才有 intent；trace 恒存在（含失败诊断）。"""

    def __init__(self, ok, intent, diagnostics, trace, declared, source_name,
                 catalog_meta):
        self.ok = ok
        self.intent = intent
        self.diagnostics = diagnostics
        self.trace = trace
        self.declared = declared
        self.source_name = source_name
        self.catalog_meta = catalog_meta

    def error_ids(self):
        return [d['id'] for d in self.diagnostics if d['level'] == 'ERROR']

    def mentions(self, needle):
        return any(needle in json.dumps(d, ensure_ascii=False)
                   for d in self.diagnostics)


def _diag(diagnostics, did, level, line, obj, message, remedy=None, extra=None):
    item = dict(id=did, level=level, line=line, object=obj, message=message)
    if remedy:
        item['remedy'] = remedy
    if extra:
        item.update(extra)
    diagnostics.append(item)


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def default_catalog_path():
    for p in DEFAULT_CATALOG_CANDIDATES:
        if os.path.isfile(p):
            return os.path.normpath(p)
    return None


def load_catalog(path=None):
    path = path or default_catalog_path()
    if not path or not os.path.isfile(path):
        raise FileNotFoundError('component-catalog.json 未找到: %r' % (path,))
    with io.open(path, encoding='utf-8') as fh:
        catalog = json.load(fh)
    if not isinstance(catalog, dict) or 'components' not in catalog:
        raise ValueError('catalog 文件结构非法（缺 components）: %s' % path)
    return catalog, path


def catalog_canonical_sha256(catalog):
    """catalog 规范化 SHA-256（sort_keys JSON 字节）。

    转换登记（trace.catalog.sha256）与链核验（工作区目录快照核对）必须
    用同一口径；哈希绑定的是目录内容，不是文件字节排布。"""
    return _sha256_bytes(json.dumps(catalog, sort_keys=True,
                                    ensure_ascii=False).encode('utf-8'))


def _catalog_types(catalog):
    return {c['component_type']: c for c in catalog.get('components', [])}


def _normpath(path):
    return os.path.normpath(os.path.abspath(path))


def _realpath(path):
    return os.path.realpath(os.path.abspath(path))


# ---------------------------------------------------------------------------
# 模型收集
# ---------------------------------------------------------------------------

def _iter_containers(model):
    yield model
    stack = list(model.packages)
    while stack:
        pkg = stack.pop()
        yield pkg
        stack.extend(pkg.packages)


def _collect_defs(model, diagnostics):
    """跨作用域收集 part def；重名即遮蔽歧义，拒绝（同名不同 scope 也不放行）。"""
    defs = {}
    for container in _iter_containers(model):
        for part in container.parts:
            if part.kind != 'def':
                continue
            if part.name in defs:
                _diag(diagnostics, 'E-SYSML-DEF-SHADOW', 'ERROR', part.line,
                      part.name,
                      "part def %r 在不同作用域重复定义（遮蔽歧义，先定义于第 %d 行）"
                      % (part.name, defs[part.name].line),
                      '全局重命名其一，或并入同一作用域')
            else:
                defs[part.name] = part
    return defs


def _find_systems(model):
    systems = []
    for container in _iter_containers(model):
        for part in container.parts:
            if part.kind == 'system':
                systems.append(part)
    return systems


def _has_internals(defn):
    return bool(defn.parts or defn.connects)


# ---------------------------------------------------------------------------
# 折叠核验（严格：端点段数、成员/边界端口存在性、多重集，不去重不截断）
# ---------------------------------------------------------------------------

class _TemplateMismatch(Exception):
    pass


def _match_template(defn, template, defs_by_name, depth=0):
    """def 的内部结构是否与模板逐字一致（成员名/类型/边界口/内部连接多重集）。"""
    if depth > 8:
        return False
    if tuple(sorted(p.name for p in defn.ports)) != template.boundary:
        return False
    actual_members = {}
    for child in defn.parts:
        if child.kind != 'instance' or len(child.type_ref or []) != 1:
            return False
        actual_members[child.name] = child
    if set(actual_members) != set(template.members):
        return False
    member_defs = {}
    boundary_ports = {p.name for p in defn.ports}
    for mname, mtype in template.members.items():
        if actual_members[mname].type_ref != [mtype]:
            return False
        mdef = defs_by_name.get(mtype)
        if mdef is None:
            return False
        member_defs[mname] = mdef
        if _has_internals(mdef):
            mtpl = FOLD_TEMPLATES.get(mtype)
            if mtpl is None or not _match_template(mdef, mtpl, defs_by_name,
                                                   depth + 1):
                return False

    def key_of(endpoint):
        segs = tuple(endpoint.segments)
        if len(segs) == 1:
            if segs[0] not in boundary_ports:
                raise _TemplateMismatch(segs)
            return segs[0]
        if len(segs) != 2:
            raise _TemplateMismatch(segs)   # >2 段：深入未声明层级，拒绝
        mname, port = segs
        if mname not in member_defs:
            raise _TemplateMismatch(segs)
        if port not in {p.name for p in member_defs[mname].ports}:
            raise _TemplateMismatch(segs)   # 成员定义无此端口，拒绝
        return (mname, port)

    actual = Counter()
    for conn in defn.connects:
        try:
            a, b = key_of(conn.source), key_of(conn.target)
        except _TemplateMismatch:
            return False
        actual[frozenset({a, b})] += 1       # 多重集：重复内部连接不会被去重
    expected = Counter()
    for a, b in template.edges:
        expected[frozenset({_tpl_key(a), _tpl_key(b)})] += 1
    return actual == expected


def _tpl_key(x):
    return (x[0], x[1]) if isinstance(x, tuple) else x


# ---------------------------------------------------------------------------
# 转换主体
# ---------------------------------------------------------------------------

def convert_text(text, catalog=None, source_name=None, source_sha256=None):
    """窄文法 SysML → L0 intent 的纯转换（不写任何文件）。见模块 docstring。"""
    if catalog is None:
        catalog, catalog_path = load_catalog()
    else:
        catalog_path = None
    types = _catalog_types(catalog)
    catalog_meta = {
        'path': catalog_path,
        'catalog_id': catalog.get('catalog_id'),
        'catalog_revision': str(catalog.get('catalog_revision')),
        'sha256': catalog_canonical_sha256(catalog),
    }
    diagnostics = []
    trace = {
        'generator': GENERATOR,
        'schema_version': TRACE_SCHEMA_VERSION,
        'status': 'blocked',
        # hash_scope: file-bytes=源文件原始字节（文件入口）；text=text 参数
        # （纯接口入口，换行规范化后的文本，不冒称源文件哈希）。
        'input': {'name': source_name, 'path': source_name,
                  'sha256': source_sha256 or _sha256_bytes(text.encode('utf-8')),
                  'hash_scope': 'file-bytes' if source_sha256 else 'text'},
        'catalog': catalog_meta,
        'hubs': [], 'externs': [], 'parts': {}, 'edges': [], 'taps': [],
        'unknown': [], 'declared': None, 'diagnostics': diagnostics,
    }
    declared = {'packages': 0, 'part_defs': [], 'instances': [],
                'externs': [], 'connects': 0, 'system': None}

    def finish(ok, intent=None, yaml_text=None):
        trace['declared'] = declared
        if ok and intent is not None:
            trace['status'] = 'converted'
            trace['output'] = {'intent_sha256': _sha256_bytes(
                (yaml_text or dump_intent_yaml(intent)).encode('utf-8')),
                'yaml': yaml_text or dump_intent_yaml(intent)}
        return ConversionResult(ok, intent if ok else None, diagnostics, trace,
                                declared, source_name, catalog_meta)

    # ---- 语法层：复用 sysml_parser，禁止第二套解析 ----
    try:
        model = sp.parse(text)
    except sp.SysmlParseError as exc:
        _diag(diagnostics, 'E-SYSML-SYNTAX', 'ERROR', exc.line, 'parse',
              '窄文法解析失败: %s' % exc,
              '按 sysml_parser 窄文法修正该行（不支持语法明确失败，不做部分转换）')
        return finish(False)

    declared['packages'] = 1 + sum(len(p.packages) for p in model.packages) \
        if model.packages else 0
    defs = _collect_defs(model, diagnostics)
    declared['part_defs'] = sorted(defs)
    systems = _find_systems(model)

    if len(systems) != 1:
        _diag(diagnostics, 'E-SYSML-SYSTEM-COUNT', 'ERROR', None, '<model>',
              '需要恰好 1 个 system part（part NAME { ... }），实得 %d 个'
              % len(systems),
              '保留唯一系统实例，其余合并或删除')
        return finish(False)
    system = systems[0]
    declared['system'] = system.name
    declared['connects'] = len(system.connects)

    # ---- 实例与类型解析（系统实例与 part def 内部成员严格分离） ----
    instances = {}

    def effective_type_of(defn, inst_name, inst_line):
        """返回 (目录类型, fold_info)；失败返回 (None, None)（已报错）。"""
        if not INST_NAME_RE.match(inst_name):
            _diag(diagnostics, 'E-SYSML-INST-NAME', 'ERROR', inst_line,
                  inst_name,
                  "实例名 %r 不符合 intent 契约（大写字母开头，仅字母/数字/"
                  "下划线/连字符）" % inst_name,
                  '按 L0 契约重命名实例')
            return None, None
        if defn.name not in types and defn.name not in FOLD_TEMPLATES:
            extra = '（该 def 含内部结构，无法按目录类型折叠）' \
                if _has_internals(defn) else ''
            _diag(diagnostics, 'E-SYSML-CAT-TYPE', 'ERROR', defn.line,
                  '%s:%s' % (inst_name, defn.name),
                  "类型 %s 不在目录 %s 内，实例 %s 无从建立端口语义%s"
                  % (defn.name, catalog_meta['catalog_id'], inst_name, extra),
                  '改用目录内类型，或先登记目录/折叠约定再引用')
            return None, None
        cat_ports = {p['id'] for p in types.get(defn.name, {}).get('ports', [])}
        if not _has_internals(defn):
            for port in defn.ports:
                if port.name not in cat_ports:
                    _diag(diagnostics, 'E-SYSML-PORT-NOTINCAT', 'ERROR',
                          port.line, '%s.%s' % (defn.name, port.name),
                          "类型 def %s 声明的端口 %s 不在目录该类型的端口清单内"
                          "（引用处实例 %s）" % (defn.name, port.name, inst_name),
                          '改用目录已登记端口 id，或先修订目录登记')
            return defn.name, None
        template = FOLD_TEMPLATES.get(defn.name)
        if template is None:
            _diag(diagnostics, 'E-SYSML-FOLD', 'ERROR', defn.line, defn.name,
                  "类型 %s 已在目录登记，但其 def 携带无冻结模板可核的内部结构"
                  "（如装配+串联单向阀形态目录无对应符号），不可按类型名丢弃"
                  "内部连接" % defn.name,
                  '按冻结折叠约定恢复结构，或显式修订折叠约定并同步文档')
            return None, None
        if tuple(sorted(p.name for p in defn.ports)) != template.boundary \
                or not _match_template(defn, template, defs):
            _diag(diagnostics, 'E-SYSML-FOLD', 'ERROR', defn.line, defn.name,
                  "类型 %s 的内部结构与冻结折叠模板不一致（成员/边界口/端点"
                  "段数/成员端口/内部连接多重集任一偏差即拒）" % defn.name,
                  '恢复 %s 的约定内部结构；结构改变必须显式修订折叠约定'
                  % defn.name)
            return None, None
        target_ports = {p['id'] for p in
                        types.get(template.target, {}).get('ports', [])}
        for port in defn.ports:
            if port.name not in target_ports:
                _diag(diagnostics, 'E-SYSML-PORT-NOTINCAT', 'ERROR', port.line,
                      '%s.%s' % (template.target, port.name),
                      "折叠目标类型 %s 无端口 %s（边界口须登记在目录）"
                      % (template.target, port.name),
                      '改用目录已登记端口 id，或先修订目录登记')
        internal = [{'anchor': 'internal:%s:%d' % (defn.name, c.line),
                     'sysml_line': c.line,
                     'endpoints': ['.'.join(c.source.segments),
                                   '.'.join(c.target.segments)]}
                    for c in defn.connects]
        fold = {
            'target': template.target,
            'boundary_ports': list(template.boundary),
            'members': dict(template.members),
            'internal_edges': internal,
            'def_line': defn.line,
        }
        return template.target, fold

    for child in system.parts:
        if child.kind == 'system':
            _diag(diagnostics, 'E-SYSML-NESTED-SYSTEM', 'ERROR', child.line,
                  child.name, '系统内不允许嵌套 system part（多系统歧义）',
                  '扁平化或拆分模型')
            continue
        if child.kind != 'instance':
            _diag(diagnostics, 'E-SYSML-INST-KIND', 'ERROR', child.line,
                  child.name,
                  '系统成员必须是带类型的实例 part（part NAME : TYPE;）',
                  '改为 typed part 声明')
            continue
        if len(child.type_ref or []) != 1:
            _diag(diagnostics, 'E-SYSML-DEF-DOTTED', 'ERROR', child.line,
                  child.name,
                  '实例 %s 的类型引用必须是单段名（窄文法不支持点分类型）'
                  % child.name,
                  '直接引用本模型声明的 part def 名')
            continue
        defn = defs.get(child.type_ref[0])
        if defn is None:
            _diag(diagnostics, 'E-SYSML-TYPE-UNKNOWN', 'ERROR', child.line,
                  '%s:%s' % (child.name, child.type_ref[0]),
                  "实例 %s 的类型 %s 未在任何作用域声明为 part def"
                  % (child.name, child.type_ref[0]),
                  '先声明类型，或修正类型名')
            continue
        etype, fold = effective_type_of(defn, child.name, child.line)
        instances[child.name] = {'line': child.line, 'def': defn,
                                 'effective_type': etype, 'fold': fold}
        declared['instances'].append(child.name)

    for inst_name in sorted(instances):
        info = instances[inst_name]
        trace['parts'][inst_name] = {
            'sysml_line': info['line'],
            'type': info['effective_type'],
            'def_line': info['def'].line,
            'fold': info['fold'],
        }

    # ---- 枢纽声明：只认注释 @NAME=INST[.port]，不写死任何实例映射 ----
    # 块注释内的声明按注释内换行折算真实 1-based 行号，不伪造。
    hubs = {}
    for comment in model.comments:
        for m in HUB_DECL_RE.finditer(comment.text):
            name, target = m.group(1), m.group(2)
            decl_line = comment.line + comment.text[:m.start()].count('\n')
            if name in hubs:
                if hubs[name]['target'] != target:
                    _diag(diagnostics, 'E-SYSML-HUB-DUP', 'ERROR', decl_line,
                          name, "枢纽 @%s 重复声明且指向冲突（%s / %s）"
                          % (name, hubs[name]['target'], target),
                          '每条母线只声明一次')
                continue
            hubs[name] = {'name': name, 'target': target, 'line': decl_line,
                          'kind': None, 'inst': None, 'port': None,
                          'usable': False}
    hub_by_target = {}
    for name in sorted(hubs):
        hub = hubs[name]
        segs = hub['target'].split('.')
        if len(segs) > 2:
            _diag(diagnostics, 'E-SYSML-HUB-TARGET', 'ERROR', hub['line'], name,
                  "枢纽 @%s 目标 %r 超过两段（实例[.端口]）" % (name, hub['target']),
                  '改为 实例 或 实例.端口')
            continue
        inst = instances.get(segs[0])
        if inst is None or inst['effective_type'] is None:
            _diag(diagnostics, 'E-SYSML-HUB-TARGET', 'ERROR', hub['line'], name,
                  "枢纽 @%s 指向未声明/未解析实例 %r" % (name, hub['target']),
                  '指向系统实例或其已登记端口')
            continue
        hub['inst'] = segs[0]
        ctype = types.get(inst['effective_type'], {})
        cat_ports = {p['id']: p for p in ctype.get('ports', [])}
        if len(segs) == 1:
            # 元件枢纽：只有唯一目录端口且非传感、液压，才可能唯一绑定真实
            # 端口；否则裸辐条会绕过元件（连接全挂母线、元件本体被架空）。
            hub['kind'] = 'component'
            if ctype.get('connection_role') == 'sensing_only':
                _diag(diagnostics, 'E-SYSML-HUB-COMPONENT-UNBOUND', 'ERROR',
                      hub['line'], name,
                      "元件枢纽 @%s（%s）为 sensing_only，不能作母线枢纽"
                      % (name, inst['effective_type']),
                      '传感件端口按 taps 接被测网络显式端口')
                continue
            if len(cat_ports) != 1:
                _diag(diagnostics, 'E-SYSML-HUB-COMPONENT-UNBOUND', 'ERROR',
                      hub['line'], name,
                      "元件枢纽 @%s（%s，%d 个目录端口）无法唯一绑定真实端口，"
                      "裸辐条会把其他元件直挂母线、绕过本元件"
                      % (name, inst['effective_type'], len(cat_ports)),
                      '改为端口枢纽（@%s=%s.<端口>）并显式连接该端口'
                      % (name, hub['inst']))
                continue
            only_port = next(iter(cat_ports.values()))
            if only_port.get('medium') != 'hydraulic':
                _diag(diagnostics, 'E-SYSML-HUB-MEDIUM', 'ERROR', hub['line'],
                      name, "元件枢纽 @%s 的唯一端口 %s.%s medium=%s，无法承载"
                            "液压母线" % (name, hub['inst'], only_port['id'],
                                          only_port.get('medium')),
                      '母线枢纽须是纯液压端口；气侧母线约定未支持')
                continue
            hub['port'] = only_port['id']
            prev = hub_by_target.get((hub['inst'], hub['port']))
            if prev is not None:
                _diag(diagnostics, 'E-SYSML-HUB-PORT', 'ERROR', hub['line'],
                      name, "端口 %s.%s 同时被 @%s 与 @%s 绑定为母线"
                            "（一口双母线歧义）"
                            % (hub['inst'], hub['port'], prev, name),
                      '一条母线绑定一个枢纽')
                continue
            hub_by_target[(hub['inst'], hub['port'])] = name
        else:
            port = segs[1]
            hub['kind'] = 'port'
            hub['port'] = port
            if port not in cat_ports:
                _diag(diagnostics, 'E-SYSML-HUB-PORT', 'ERROR', hub['line'],
                      name, "枢纽 @%s 的端口 %s.%s 不在目录类型 %s 内"
                      % (name, hub['inst'], port, inst['effective_type']),
                      '改为目录已登记端口')
                continue
            if cat_ports[port].get('medium') != 'hydraulic':
                _diag(diagnostics, 'E-SYSML-HUB-MEDIUM', 'ERROR', hub['line'],
                      name, "枢纽 @%s 绑定非 hydraulic 端口 %s.%s（paths 属液压"
                            "主路）" % (name, hub['inst'], port),
                      '母线枢纽须绑 hydraulic 端口；气侧母线约定未支持')
                continue
            prev = hub_by_target.get((hub['inst'], port))
            if prev is not None:
                _diag(diagnostics, 'E-SYSML-HUB-PORT', 'ERROR', hub['line'],
                      name, "端口 %s.%s 同时被 @%s 与 @%s 绑定为母线"
                            "（一口双母线歧义）" % (hub['inst'], port, prev, name),
                      '一条母线绑定一个枢纽')
                continue
            hub_by_target[(hub['inst'], port)] = name
        hub['usable'] = True
    trace['hubs'] = [dict(hubs[k]) for k in sorted(hubs)]

    # ---- extern 边界（原生边界写法）：系统端口是 SysML 实体，注释补 L0 角色 ----
    externs = {}
    for comment in model.comments:
        for m in EXTERN_DECL_RE.finditer(comment.text):
            name, port = m.group(1), m.group(2)
            decl_line = comment.line + comment.text[:m.start()].count('\n')
            if not INST_NAME_RE.match(name):
                _diag(diagnostics, 'E-SYSML-EXTERN-NAME', 'ERROR', decl_line,
                      name, "extern 边界名 %r 不符合 intent 契约（大写字母开头，"
                            "仅字母/数字/下划线/连字符）" % name,
                      '按 L0 契约重命名边界')
                continue
            if name in externs:
                if externs[name]['port'] != port:
                    _diag(diagnostics, 'E-SYSML-EXTERN-DUP', 'ERROR', decl_line,
                          name, "extern 边界 %s 重复声明且端口冲突（%s / %s）"
                                % (name, externs[name]['port'], port),
                          '每个边界只声明一次')
                continue
            externs[name] = {'name': name, 'port': port, 'line': decl_line}
    system_ports = {p.name: p.line for p in system.ports}
    for name in sorted(externs):
        if name in instances:
            _diag(diagnostics, 'E-SYSML-EXTERN-CLASH', 'ERROR',
                  externs[name]['line'], name,
                  "extern 边界 %s 与系统实例同名（端点解析歧义，边界的连接会"
                  "被当成实例）" % name,
                  '边界与实例使用不同名字')
            continue
        # 注释只补充 L0 边界角色，不替代 SysML 实体声明：对应系统端口必须
        # 真实声明，否则该"边界"在模型里没有实体，拒绝（不静默放行）。
        if name not in system_ports:
            _diag(diagnostics, 'E-SYSML-EXTERN-UNDECLARED', 'ERROR',
                  externs[name]['line'], name,
                  "extern 注释声明 %s 没有对应系统端口声明（系统 part 内缺 "
                  "port '%s';）——仅有注释不构成边界实体" % (name, name),
                  "在系统 part 内声明 port '%s'; 并用 connect 引用" % name)
            continue
        externs[name]['port_line'] = system_ports[name]
    trace['externs'] = [dict(externs[k]) for k in sorted(externs)]
    declared['externs'] = sorted(externs)

    port_hub_of = {(h['inst'], h['port']): name for name, h in hubs.items()
                   if h['usable'] and h['kind'] == 'port'}
    component_hub_of = {h['inst']: name for name, h in hubs.items()
                        if h['usable'] and h['kind'] == 'component'}

    def cat_ports_of(inst_name):
        info = instances.get(inst_name)
        if not info or not info['effective_type']:
            return {}
        return {p['id']: p for p in
                types.get(info['effective_type'], {}).get('ports', [])}

    def main_path_of(inst_name):
        info = instances.get(inst_name)
        if not info or not info['effective_type']:
            return None
        return types.get(info['effective_type'], {}).get('main_path')

    # ---- 端点解析 ----
    def resolve_endpoint(endpoint):
        segs = endpoint.segments
        line = endpoint.line
        if len(segs) > 2:
            _diag(diagnostics, 'E-SYSML-ENDPOINT-DEEP', 'ERROR', line,
                  '.'.join(segs),
                  '连接端点 %r 深入组件内部（>2 段）；折叠后的组件对系统不透明'
                  % '.'.join(segs),
                  '只连实例边界端口；内部结构属折叠证据')
            return None
        inst_name = segs[0]
        if inst_name in externs:
            # 原生边界写法：边界是系统端口，connect 直接引用端口名；L0 端口
            # 角色由注释 extern: NAME=PORT 给出，不写进连接端点。
            if len(segs) != 1:
                _diag(diagnostics, 'E-SYSML-EXTERN-PORT', 'ERROR', line,
                      '.'.join(segs),
                      "边界 %s 是系统端口，connect 直接写 '%s'（其 L0 端口角色"
                      "由注释 extern: %s=%s 声明，不写在连接端点上）"
                      % (inst_name, inst_name, inst_name,
                         externs[inst_name]['port']),
                      "改成 connect ... to '%s'" % inst_name)
                return None
            return dict(kind='extern', token=inst_name, inst=inst_name,
                        port=None, line=line, bare=False)
        if inst_name not in instances:
            _diag(diagnostics, 'E-SYSML-REF', 'ERROR', line, inst_name,
                  "连接端点引用 %s：不是本系统声明的实例" % inst_name,
                  '改为系统实例（或其端口）')
            return None
        if instances[inst_name]['effective_type'] is None:
            return None  # 类型级错误已报（未知目录类型/折叠失败），不级联
        if len(segs) == 2:
            port = segs[1]
            defn = instances[inst_name]['def']
            if port not in {p.name for p in defn.ports}:
                _diag(diagnostics, 'E-SYSML-PORT-UNDECLARED', 'ERROR', line,
                      '%s.%s' % (inst_name, port),
                      "端口存在性: %s.%s 未在类型 def %s 中声明"
                      % (inst_name, port, defn.name),
                      '在类型 def 声明该端口（带行号证据），或修正端口名')
                return None
            if port not in cat_ports_of(inst_name):
                _diag(diagnostics, 'E-SYSML-PORT', 'ERROR', line,
                      '%s.%s' % (inst_name, port),
                      "端口存在性: 目录类型 %s 无端口 %s.%s（可用: %s）"
                      % (instances[inst_name]['effective_type'], inst_name,
                         port, ', '.join(sorted(cat_ports_of(inst_name)))),
                      '改用目录已登记端口 id')
                return None
            bus = port_hub_of.get((inst_name, port))
            if bus:
                return dict(kind='bus', token='@' + bus, inst=inst_name,
                            port=port, line=line, bare=False)
            return dict(kind='port', token='%s.%s' % (inst_name, port),
                        inst=inst_name, port=port, line=line, bare=False)
        bus = component_hub_of.get(inst_name)
        if bus:
            return dict(kind='bus', token='@' + bus, inst=inst_name,
                        port=None, line=line, bare=True)
        return dict(kind='bare', token=inst_name, inst=inst_name, port=None,
                    line=line, bare=True)

    resolved = []
    for conn in system.connects:
        a = resolve_endpoint(conn.source)
        b = resolve_endpoint(conn.target)
        if a is None or b is None:
            continue
        if a['inst'] == b['inst']:
            _diag(diagnostics, 'E-SYSML-SELFLOOP', 'ERROR', conn.line,
                  _conn_text(conn), '同一实例的自环连接不在窄版支持范围',
                  '拆分或删除该连接')
            continue
        resolved.append((conn, a, b))

    # ---- 裸 inline 端口的 main_path 唯一化（不按出现顺序猜方向） ----
    bare_failed = False
    for conn, a, b in resolved:
        for ep in (a, b):
            if ep['kind'] != 'bare':
                continue
            inst_name = ep['inst']
            mp = main_path_of(inst_name) or {}
            cands = [c for c in (mp.get('in'), mp.get('out')) if c]
            cat_ports = cat_ports_of(inst_name)
            if not cands:
                _diag(diagnostics, 'E-SYSML-BARE-NOMP', 'ERROR', ep['line'],
                      inst_name,
                      "裸实例 %s（类型 %s）无 main_path，无法填充串接端口"
                      % (inst_name, instances[inst_name]['effective_type']),
                      '写显式端口，如 %s.%s'
                      % (inst_name, sorted(cat_ports)[0] if cat_ports else 'port'))
                ep['failed'] = True
                bare_failed = True
                continue
            other = b if a is ep else a
            other_medium = None
            if other['port']:
                other_medium = cat_ports_of(other['inst']).get(
                    other['port'], {}).get('medium')
            viable = [c for c in cands
                      if other_medium is None
                      or cat_ports.get(c, {}).get('medium') == other_medium]
            if len(viable) == 1:
                ep['port'] = viable[0]
                ep['kind'] = 'port'
                ep['token'] = '%s.%s' % (inst_name, viable[0])
            else:
                if viable:
                    why = ('候选口 %s 无法唯一选择（SysML connect 的 to 不是'
                           '液流方向，不按出现顺序猜）' % '/'.join(sorted(cands)))
                else:
                    why = '候选口 %s 与对端介质 %s 均不符' % (
                        '/'.join(sorted(cands)), other_medium)
                _diag(diagnostics, 'E-SYSML-BARE-AMBIGUOUS', 'ERROR', ep['line'],
                      inst_name,
                      "裸实例 %s 的 main_path 端口无法唯一确定: %s"
                      % (inst_name, why),
                      '写显式端口（.%s / .%s），或把该实例声明为母线枢纽'
                      % (mp.get('in'), mp.get('out')))
                ep['failed'] = True
                bare_failed = True
    if bare_failed:
        return finish(False)

    # ---- 连接分类：taps（sensing_only，P1 语义）与 paths（液压主路） ----
    def is_sensing(inst_name):
        info = instances.get(inst_name)
        if not info or not info['effective_type']:
            return False
        return types.get(info['effective_type'], {}).get(
            'connection_role') == 'sensing_only'

    def port_medium(ep):
        if ep['port']:
            return cat_ports_of(ep['inst']).get(ep['port'], {}).get('medium')
        return 'hydraulic'  # 元件枢纽唯一端口已在声明处核过 hydraulic

    TAP_MEDIA = {'hydraulic', 'pneumatic'}

    paths, taps, edge_trace = [], [], []
    seen_connects = {}
    medium_rejected = False

    for conn, a, b in resolved:
        key = frozenset({a['token'], b['token']})
        if key in seen_connects:
            _diag(diagnostics, 'E-SYSML-DUP-CONNECT', 'ERROR', conn.line,
                  _conn_text(conn),
                  '与第 %d 行连接重复（同端点对重复声明）' % seen_connects[key],
                  '删除重复连接')
            continue
        seen_connects[key] = conn.line

        sensing = [ep for ep in (a, b) if is_sensing(ep['inst'])]
        solid = [ep for ep in (a, b) if not is_sensing(ep['inst'])]
        if len(sensing) == 2:
            _diag(diagnostics, 'E-SYSML-TAP-TAP', 'ERROR', conn.line,
                  _conn_text(conn),
                  '两端都是 sensing_only 组件的连接无法确定测点方向',
                  '改为一端传感、一端被测网络')
            continue
        if sensing:
            sen, other = sensing[0], solid[0]
            if other['kind'] == 'extern':
                _diag(diagnostics, 'E-SYSML-TAP-EXTERN', 'ERROR', conn.line,
                      _conn_text(conn),
                      'taps 不能锚定边界终点 %s（传感支路两端须是实例端口）'
                      % other['token'],
                      '改接被测元件的显式端口')
                continue
            if other['kind'] == 'bus':
                _diag(diagnostics, 'E-SYSML-TAP-BUS', 'ERROR', conn.line,
                      _conn_text(conn),
                      'taps 不能锚定母线 %s（当前 intent 契约 taps 两端须是'
                      '实例端口）' % other['token'],
                      '改接被测元件的显式端口；气侧母线 taps 约定未决')
                continue
            sen_m, other_m = port_medium(sen), port_medium(other)
            # 介质越界：机械/电气端口与混介质一律 ERROR，sensing_only 不豁免
            if sen_m not in TAP_MEDIA or other_m not in TAP_MEDIA:
                _diag(diagnostics, 'E-SYSML-MEDIUM', 'ERROR', conn.line,
                      _conn_text(conn),
                      "taps 不支持 %s 介质端口（%s=%s, %s=%s）；"
                      "电气/机械连接不在窄版支持范围"
                      % ('/'.join(sorted(TAP_MEDIA)), sen['token'], sen_m,
                         other['token'], other_m),
                      '该连接不入 intent（如需披露写 unknown），或扩展约定')
                medium_rejected = True
                continue
            if sen_m != other_m:
                _diag(diagnostics, 'E-SYSML-MEDIUM', 'ERROR', conn.line,
                      _conn_text(conn),
                      "taps 两端介质必须同质: %s(%s) ↔ %s(%s)，混介质拒绝"
                      % (sen['token'], sen_m, other['token'], other_m),
                      '接同介质端口；不同介质的测量链路约定未决')
                medium_rejected = True
                continue
            taps.append({'sensor': sen['token'], 'at': other['token']})
            edge_trace.append({'anchor': 'taps[%d]' % (len(taps) - 1),
                               'sysml_line': conn.line, 'kind': 'tap',
                               'endpoints': [sen['token'], other['token']]})
            continue
        bad_medium = [ep for ep in (a, b) if port_medium(ep) != 'hydraulic']
        if bad_medium:
            ep = bad_medium[0]
            _diag(diagnostics, 'E-SYSML-MEDIUM', 'ERROR', conn.line,
                  _conn_text(conn),
                  "paths 属液压主路，端点 %s 的 medium=%s（电气/机械/气侧连接"
                  "不在窄版支持范围，不得伪造贯通口）"
                  % (ep['token'], port_medium(ep)),
                  '该连接不入 intent（如需披露写 unknown），或扩展约定')
            medium_rejected = True
            continue
        paths.append([a['token'], b['token']])
        edge_trace.append({'anchor': 'paths[%d][0->1]' % (len(paths) - 1),
                           'sysml_line': conn.line, 'kind': 'connect',
                           'endpoints': [a['token'], b['token']]})

    trace['edges'] = edge_trace
    tap_lines = {e['anchor']: e['sysml_line'] for e in edge_trace
                 if e['kind'] == 'tap'}
    trace['taps'] = [dict(t, anchor='taps[%d]' % i,
                          sysml_line=tap_lines.get('taps[%d]' % i))
                     for i, t in enumerate(taps)]

    if medium_rejected or any(d['level'] == 'ERROR' for d in diagnostics):
        return finish(False)

    # ---- 母线 spoke 补回：任何已声明端口枢纽都必须连回真实端口。
    # 唯一等价合并：main_path 进出口各绑一条母线、且只经母线接线的实例，
    # 以 [bus(in), INST, bus(out)] 桥接路径同时表达两口（不吞边）。----
    hub_bindings = {}
    touches_non_hub = set()
    for conn, a, b in resolved:
        for ep in (a, b):
            if ep['kind'] == 'bus' and ep['port']:
                hub_bindings.setdefault(ep['inst'], {})[ep['port']] = \
                    ep['token'][1:]
            elif ep['kind'] != 'bus':
                touches_non_hub.add(ep['inst'])
    bridge_covered = set()
    for inst_name in sorted(hub_bindings):
        if inst_name in touches_non_hub:
            continue
        bindings = hub_bindings[inst_name]
        mp = main_path_of(inst_name) or {}
        if not mp.get('in') or not mp.get('out'):
            continue
        bus_in, bus_out = bindings.get(mp['in']), bindings.get(mp['out'])
        if not bus_in or not bus_out:
            continue
        if bus_in == bus_out:
            _diag(diagnostics, 'E-SYSML-BRIDGE-LOOP', 'ERROR',
                  instances[inst_name]['line'], inst_name,
                  "实例 %s 的 main_path 进出两端绑定同一条母线 @%s，桥接路径"
                  "无法表示" % (inst_name, bus_in),
                  '核对枢纽声明')
            continue
        paths.append(['@' + bus_in, inst_name, '@' + bus_out])
        evidence = sorted({hubs[bus_in]['line'], hubs[bus_out]['line'],
                           instances[inst_name]['def'].line})
        for k, (ta, tb) in enumerate([('@' + bus_in, inst_name),
                                      (inst_name, '@' + bus_out)]):
            edge_trace.append({
                'anchor': 'paths[%d][%d->%d]' % (len(paths) - 1, k, k + 1),
                'sysml_line': instances[inst_name]['def'].line,
                'kind': 'bridge', 'endpoints': [ta, tb],
                'evidence_lines': evidence,
                'evidence': 'spoke补回(等价合并): main_path(%s→%s) 两口各绑'
                            '母线 @%s/@%s，内部折叠证据见 parts.%s.fold'
                            % (mp['in'], mp['out'], bus_in, bus_out, inst_name),
            })
        bridge_covered.add((inst_name, mp['in']))
        bridge_covered.add((inst_name, mp['out']))
    for (inst_name, port), bus in sorted(port_hub_of.items()):
        if (inst_name, port) in bridge_covered:
            continue  # 已由桥接路径等价合并，不重复
        token = '%s.%s' % (inst_name, port)
        paths.append(['@' + bus, token])
        evidence = sorted({hubs[bus]['line'], instances[inst_name]['line']})
        edge_trace.append({
            'anchor': 'paths[%d][0->1]' % (len(paths) - 1),
            'sysml_line': hubs[bus]['line'],
            'kind': 'spoke', 'endpoints': ['@' + bus, token],
            'evidence_lines': evidence,
            'evidence': '端口枢纽辐条补回: @%s=%s，母线必须连回真实端口'
                        % (bus, hubs[bus]['target']),
        })

    # ---- unknown 披露：unknown: 标记 + 文档化待决注释 + 未连接目录端口 ----
    unknown_entries = []
    for comment in model.comments:
        for m in UNKNOWN_MARK_RE.finditer(comment.text):
            unknown_entries.append({
                'entry': m.group(1), 'source': 'comment',
                'line': comment.line + comment.text[:m.start()].count('\n')})
        for offset, line_text in enumerate(comment.text.split('\n')):
            if UNKNOWN_MARK_RE.search(line_text):
                continue  # 该行已按 unknown: 结构化，不重复记待决
            hit = next((mk for mk in PENDING_MARKERS if mk in line_text), None)
            if not hit:
                continue
            excerpt = line_text.strip()
            if not excerpt:
                continue
            real_line = comment.line + offset
            unknown_entries.append({
                'entry': 'sysml-pending-l%d:%s' % (real_line, excerpt[:48]),
                'source': 'pending-comment', 'line': real_line,
                'text': excerpt})
    referenced = set()
    for conn, a, b in resolved:
        for ep in (a, b):
            if ep['port']:
                referenced.add((ep['inst'], ep['port']))
    for name, hub in hubs.items():
        if hub['usable'] and hub['inst'] and hub['port']:
            referenced.add((hub['inst'], hub['port']))
    for inst_name in sorted(instances):
        info = instances[inst_name]
        if not info['effective_type']:
            continue
        for pid, port in sorted(cat_ports_of(inst_name).items()):
            if port.get('kind') == 'body_tap':
                continue
            if (inst_name, pid) not in referenced:
                unknown_entries.append({
                    'entry': '%s.%s-unconnected' % (inst_name, pid),
                    'source': 'unconnected-port', 'line': info['line']})
    referenced_externs = {ep['inst'] for conn, a, b in resolved
                          for ep in (a, b) if ep['kind'] == 'extern'}
    for name in sorted(externs):
        if name not in referenced_externs:
            unknown_entries.append({
                'entry': '%s-unconnected' % name,
                'source': 'unconnected-extern', 'line': externs[name]['line']})
    trace['unknown'] = unknown_entries

    # ---- 组装 intent（确定性排序；未引用 def 不生成实例） ----
    intent = {
        'l0_version': L0_VERSION,
        'system': system.name,
        'catalog': '%s@%s' % (catalog_meta['catalog_id'],
                              catalog_meta['catalog_revision']),
        'maturity': 'concept',
        'extern': {name: externs[name]['port'] for name in sorted(externs)},
        'parts': {name: instances[name]['effective_type']
                  for name in sorted(instances)},
        'paths': paths,
    }
    if taps:
        intent['taps'] = taps
    if unknown_entries:
        intent['unknown'] = sorted({u['entry'] for u in unknown_entries})

    # ---- 真实同源 preflight（与渲染器/CLI 同一函数，不复制不漂移） ----
    yaml_text = dump_intent_yaml(intent)
    rep = pf.preflight(intent, catalog, source_text=yaml_text)
    for f in rep['findings']:
        _diag(diagnostics, 'L0-' + f['id'], f['level'], None, f.get('object'),
              'preflight: %s' % f['message'], f.get('remedy'),
              extra={'yaml_line': f.get('yamlline')})
    ok = not any(d['level'] == 'ERROR' for d in diagnostics)
    if not ok:
        return finish(False)
    return finish(True, intent, yaml_text)


def _conn_text(conn):
    return 'connect %s to %s' % ('.'.join(conn.source.segments),
                                 '.'.join(conn.target.segments))


def dump_intent_yaml(intent):
    """确定性 YAML 文本（键排序、不折行），供 preflight 行号定位与发布。"""
    from ruamel.yaml import YAML
    yaml = YAML(typ='safe', pure=True)
    yaml.default_flow_style = False
    yaml.allow_unicode = True
    yaml.width = 4096
    buf = io.StringIO()
    yaml.dump(_sort_plain(intent), buf)
    return buf.getvalue()


def _sort_plain(obj):
    if isinstance(obj, dict):
        return {k: _sort_plain(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_sort_plain(v) for v in obj]
    return obj


def convert_file(sysml_path, catalog_path=None):
    """文件入口：按原始字节绑定源哈希（LF/CRLF/BOM 与磁盘一致）。

    utf-8-sig 解码仅去 BOM 供 parser 使用，1-based 行号不受影响；
    非 UTF-8 文件明确报错，不做部分转换。
    """
    catalog, _ = load_catalog(catalog_path)
    with open(sysml_path, 'rb') as fh:
        raw = fh.read()
    try:
        text = raw.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('源文件不是有效 UTF-8（不做部分转换）: %s (%s)'
                         % (sysml_path, exc))
    result = convert_text(text, catalog=catalog,
                          source_name=_normpath(sysml_path),
                          source_sha256=_sha256_bytes(raw))
    result.trace['input']['path'] = _normpath(sysml_path)
    return result


# ---------------------------------------------------------------------------
# 发布：写 intent + sidecar；失败清理本工具产物；绝不碰用户文件
# ---------------------------------------------------------------------------

def _file_sha256(path):
    with open(path, 'rb') as fh:
        return _sha256_bytes(fh.read())


def _sidecar_binds(trace_path, intent_path):
    """<trace_path> 是否为本文工具产物且绑定 <intent_path> 当前内容。"""
    if not os.path.isfile(trace_path) or not os.path.isfile(intent_path):
        return False
    try:
        with io.open(trace_path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return False
    if not isinstance(data, dict) or data.get('generator') != GENERATOR:
        return False
    out = data.get('output') or {}
    return (out.get('path') == _normpath(intent_path)
            and out.get('intent_sha256') == _file_sha256(intent_path))


def _is_our_json(path):
    """已废弃语义保留名：仅 generator 判断不足以认定归属，见
    _sidecar_targets_output。本工具内部不再使用 generator-only 判断做
    覆盖/删除决定。"""
    try:
        with io.open(path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return False
    return isinstance(data, dict) and data.get('generator') == GENERATOR


def _sidecar_targets_output(trace_path, output_path):
    """trace 是本文工具产物**且**其绑定的 output 就是当前输出。

    "本工具曾生成"不等于"属于本次输出"：generator-only 判断会让 A 输出
    的发布/清理覆盖或删除 B 输出的 sidecar。覆盖既有 trace 目标前必须
    通过本核验（intent 哈希可旧，output.path 必须一致）。
    """
    if not os.path.isfile(trace_path):
        return False
    try:
        with io.open(trace_path, encoding='utf-8') as fh:
            data = json.load(fh)
    except (ValueError, OSError):
        return False
    if not isinstance(data, dict) or data.get('generator') != GENERATOR:
        return False
    return (data.get('output') or {}).get('path') == _normpath(output_path)


def publish(result, output_path, trace_path=None, protected_paths=()):
    """把成功结果落盘；失败/被拒不遗留可误认的陈旧成功输出。返回 report。

    两个目标（intent 与 trace，含调用指定的 trace）都先做安全预检；所有权
    按「调用指定的 trace 或缺省 sidecar」双通道核验；protected_paths
    （输入/catalog/--diff 参照等）与目标相撞或别名即拒绝。
    """
    report = {'published': False, 'output': None, 'trace': None,
              'cleaned': [], 'refused': []}
    output_path = _normpath(output_path)
    trace_path = _normpath(trace_path or (output_path + '.trace.json'))
    default_trace = output_path + '.trace.json'

    protected = {_realpath(p) for p in
                 ([result.source_name] if result.source_name else [])
                 + list(protected_paths) if p}
    targets = {_realpath(output_path), _realpath(trace_path)}
    clash = sorted(protected & targets)
    if clash:
        report['refused'].append('输出路径与受保护路径（输入/catalog/参照）'
                                 '相撞或别名: %s' % ', '.join(clash))
        return report
    if _realpath(output_path) == _realpath(trace_path):
        report['refused'].append('intent 输出与追溯 sidecar 路径相同: %s'
                                 % output_path)
        return report

    def intent_owned():
        return (_sidecar_binds(trace_path, output_path)
                or (default_trace != trace_path
                    and _sidecar_binds(default_trace, output_path)))

    def cleanup_owned():
        """只清理能被 sidecar 哈希绑定核验为本工具产物的 intent+sidecar。"""
        if not os.path.isfile(output_path):
            return
        binding = None
        for tp in dict.fromkeys((trace_path, default_trace)):
            if _sidecar_binds(tp, output_path):
                binding = tp
                break
        if binding is None:
            report['refused'].append(
                '存在无法核验为 %s 产物的输出 %s（缺绑定 sidecar 或哈希不符），'
                '未清理' % (GENERATOR, output_path))
            return
        removals = [output_path, binding]
        other = default_trace if binding == trace_path else trace_path
        # 只删属于当前输出的 sidecar：generator 相同但绑定其他 output 的
        # sidecar 是别家产物的追溯，保持字节不变。
        if os.path.isfile(other) and _sidecar_binds(other, output_path):
            removals.append(other)
        for p in removals:
            try:
                os.remove(p)
                report['cleaned'].append(p)
            except OSError as exc:
                report['refused'].append('清理陈旧输出失败 %s: %s' % (p, exc))

    # 失败路径先行：只清理属于当前输出的产物，不做任何写入
    if not result.ok:
        cleanup_owned()
        report['refused'].append('转换未通过（%d 条 ERROR），不发布 intent'
                                 % len(result.error_ids()))
        return report

    # 写入预检（成功路径）：目录拒绝；既有目标必须可核验为本工具对当前
    # 输出的产物（"本工具曾生成"≠"属于本次输出"）
    for target in (output_path, trace_path):
        if os.path.isdir(target):
            report['refused'].append(
                '拒绝写入: %s 是现有目录' % target)
            return report
    if os.path.isfile(output_path) and not intent_owned():
        report['refused'].append(
            '拒绝覆盖: %s 已存在且无本文工具的绑定 sidecar（用户文件保护），'
            '请另选 -o 路径' % output_path)
        return report
    if os.path.isfile(trace_path) and not _sidecar_targets_output(trace_path,
                                                                  output_path):
        if _is_our_json(trace_path):
            report['refused'].append(
                '拒绝覆盖: %s 是本文工具产物，但绑定的是其他输出（output.path '
                '≠ %s），其追溯保持字节不变' % (trace_path, output_path))
        else:
            report['refused'].append(
                '拒绝覆盖: %s 已存在且不是本文工具产物（用户文件保护）'
                % trace_path)
        return report

    intent_yaml = (result.trace.get('output') or {}).get('yaml') \
        or dump_intent_yaml(result.intent)
    intent_bytes = intent_yaml.encode('utf-8')
    sidecar = dict(result.trace)
    sidecar.pop('output', None)  # sidecar 不携带 yaml 原文，只绑哈希
    sidecar['output'] = {'path': output_path,
                         'intent_sha256': _sha256_bytes(intent_bytes)}
    sidecar_bytes = (json.dumps(sidecar, ensure_ascii=False, indent=1,
                                sort_keys=True) + '\n').encode('utf-8')

    backup = None
    if os.path.isfile(output_path):
        with open(output_path, 'rb') as fh:
            backup = fh.read()
    try:
        _atomic_write(output_path, intent_bytes)
    except OSError as exc:
        report['refused'].append('写入失败: %s' % exc)
        return report
    try:
        _atomic_write(trace_path, sidecar_bytes)
    except OSError as exc:
        # 回滚：intent 不允许以"无有效 sidecar 绑定"的状态残留
        try:
            if backup is not None:
                with open(output_path, 'wb') as fh:
                    fh.write(backup)
                report['cleaned'].append(output_path + '（恢复原内容）')
            else:
                os.remove(output_path)
                report['cleaned'].append(output_path)
        except OSError as exc2:
            report['refused'].append('回滚 intent 失败: %s' % exc2)
        report['refused'].append('写入失败: %s' % exc)
        return report
    report.update(published=True, output=output_path, trace=trace_path)
    return report


def _atomic_write(path, data):
    tmp = '%s.tmp-%d' % (path, os.getpid())
    with open(tmp, 'wb') as fh:
        fh.write(data)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# 拓扑对账（成功 intent ↔ 手写 intent）
# ---------------------------------------------------------------------------

def topology_diff(converted_intent, reference_intent, catalog):
    """节点/边逐项比较：无向端点对多重集归一化，缺失与新增分列。

    裸实例端口按 topology_reconciliation.declared_topology 的同一 main_path
    语义展开；母线 token 原样比较；paths 与 taps 分类比较。只对双方都是
    合法 intent 的情形有意义——失败转换不得调用本函数宣称一致。
    """
    import topology_reconciliation as tr
    left = tr.declared_topology(converted_intent, catalog)
    right = tr.declared_topology(reference_intent, catalog)

    ln = {n['id']: n['type'] for n in left['nodes']}
    rn = {n['id']: n['type'] for n in right['nodes']}
    nodes = {
        'matched': sorted(set(ln) & set(rn)),
        'missing_in_converted': sorted(set(rn) - set(ln)),
        'extra_in_converted': sorted(set(ln) - set(rn)),
        'type_mismatch': [{'instance': k, 'converted_type': ln[k],
                           'reference_type': rn[k]}
                          for k in sorted(set(ln) & set(rn)) if ln[k] != rn[k]],
    }

    def edge_mult(manifest):
        out = {}
        for e in manifest['edges']:
            if e['kind'] != 'path':
                continue
            key = tuple(sorted(e['endpoints']))
            out[key] = out.get(key, 0) + 1
        return out

    def anchors_of(manifest, key):
        return [e['anchor'] for e in manifest['edges']
                if e['kind'] == 'path' and tuple(sorted(e['endpoints'])) == key]

    lm, rm = edge_mult(left), edge_mult(right)
    missing, extra, matched = [], [], 0
    for key in sorted(set(lm) | set(rm)):
        a, b = lm.get(key, 0), rm.get(key, 0)
        matched += min(a, b)
        if b > a:
            missing.append({'endpoints': list(key), 'count': b - a,
                            'reference_anchors': anchors_of(right, key)})
        if a > b:
            extra.append({'endpoints': list(key), 'count': a - b,
                          'converted_anchors': anchors_of(left, key)})
    edges = {'matched': matched, 'missing_in_converted': missing,
             'extra_in_converted': extra}

    tl = Counter(tuple(sorted([t['sensor'], t['at']]))
                 for t in (converted_intent.get('taps') or []))
    tr_ = Counter(tuple(sorted([t['sensor'], t['at']]))
                  for t in (reference_intent.get('taps') or []))
    taps = {
        'matched': sum((tl & tr_).values()),
        'missing_in_converted': [{'endpoints': list(k), 'count': v}
                                 for k, v in sorted((tr_ - tl).items())],
        'extra_in_converted': [{'endpoints': list(k), 'count': v}
                               for k, v in sorted((tl - tr_).items())],
    }
    return {
        'schema_version': 1,
        'normalization': '无向端点对多重集；裸实例按 declared_topology 的 '
                         'main_path 语义展开；母线 token 原样比较；paths 与 '
                         'taps 分类比较',
        'nodes': nodes, 'edges': edges, 'taps': taps,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(
        prog='sysml_to_intent.py',
        description='#51 窄版 SysML→L0 intent 转换器（部分实现/实验入口，'
                    '见 references/sysml-l0.md）')
    parser.add_argument('input', help='输入 .sysml（窄文法）')
    parser.add_argument('-o', '--output', default=None,
                        help='输出 intent.yaml（缺省：输入同目录 <stem>.intent.yaml）')
    parser.add_argument('--catalog', default=None,
                        help='component-catalog.json（缺省锚定 skill 规范源）')
    parser.add_argument('--trace', default=None,
                        help='追溯 sidecar JSON（缺省：<output>.trace.json）')
    parser.add_argument('--diff', default=None,
                        help='与手写 intent 做拓扑对账（只披露，不拦截）')
    parser.add_argument('--json', action='store_true', help='机器可读输出')
    args = parser.parse_args(argv)

    if not os.path.isfile(args.input):
        print('输入文件不存在: %s' % args.input, file=sys.stderr)
        return 2
    try:
        catalog, catalog_path = load_catalog(args.catalog)
    except (FileNotFoundError, ValueError) as exc:
        print('目录载入失败: %s' % exc, file=sys.stderr)
        return 2

    output_path = args.output or os.path.join(
        os.path.dirname(os.path.abspath(args.input)),
        os.path.splitext(os.path.basename(args.input))[0] + '.intent.yaml')
    trace_path = args.trace or (output_path + '.trace.json')
    protected = [p for p in (args.input, catalog_path, args.diff) if p]

    try:
        result = convert_file(args.input, catalog_path=catalog_path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not result.ok:
        # 所有转换失败路径（含 --diff）走同一失效处理：不发布 + 清理陈旧
        report = publish(result, output_path, trace_path,
                         protected_paths=protected)
        if args.json:
            print(json.dumps({'ok': False, 'published': False,
                              'cleaned': report['cleaned'],
                              'refused': report['refused'],
                              'declared': result.declared,
                              'diagnostics': result.diagnostics,
                              'intent': None, 'diff': None},
                             ensure_ascii=False, indent=1))
        else:
            print('[sysml_to_intent] 转换被拦截（%d 条 ERROR），未发布 intent%s'
                  % (len(result.error_ids()),
                     '，跳过 --diff 对账（不宣称与手写 intent 一致）'
                     if args.diff else ''))
            for cleaned in report['cleaned']:
                print('  已清理本工具陈旧成功输出: %s' % cleaned)
            for msg in report['refused']:
                print('  注意: %s' % msg)
            for d in result.diagnostics:
                if d['level'] == 'ERROR':
                    print('  %-32s %-5s %s'
                          % (d['id'], d['line'] if d['line'] else '--',
                             d['message']))
            print('  已解析声明: %s' % json.dumps(result.declared,
                                                 ensure_ascii=False))
        return 1

    diff_report = None
    if args.diff:
        try:
            from ruamel.yaml import YAML
            with io.open(args.diff, encoding='utf-8') as fh:
                reference = YAML(typ='safe', pure=True).load(fh)
            diff_report = topology_diff(result.intent, reference, catalog)
        except (KeyError, TypeError, ValueError) as exc:
            print('对账失败（双方须为可解析 intent，类型须在目录内）: %s' % exc,
                  file=sys.stderr)
            return 2

    report = publish(result, output_path, trace_path,
                     protected_paths=protected)
    if not report['published']:
        for msg in report['refused']:
            print('[sysml_to_intent] %s' % msg, file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({'ok': True, 'published': True,
                          'output': report['output'], 'trace': report['trace'],
                          'cleaned': report['cleaned'],
                          'diagnostics': result.diagnostics,
                          'declared': result.declared,
                          'intent': result.intent, 'diff': diff_report},
                         ensure_ascii=False, indent=1))
    else:
        print('[sysml_to_intent] %s -> %s（preflight 通过，maturity=concept，'
              'extern={}）' % (os.path.basename(args.input),
                              os.path.basename(report['output'])))
        print('  追溯 sidecar: %s' % report['trace'])
        print('  parts=%d paths=%d taps=%d unknown=%d'
              % (len(result.intent['parts']), len(result.intent['paths']),
                 len(result.intent.get('taps', [])),
                 len(result.intent.get('unknown', []))))
        for d in result.diagnostics:
            if d['level'] == 'WARN':
                print('  %-26s L%-5s %s'
                      % (d['id'], d['line'] if d['line'] else '--', d['message']))
        if diff_report:
            print('  拓扑对账(vs %s): 节点 matched=%d missing=%d extra=%d; '
                  '边 matched=%d missing=%d extra=%d; taps matched=%d '
                  'missing=%d extra=%d'
                  % (os.path.basename(args.diff),
                     len(diff_report['nodes']['matched']),
                     len(diff_report['nodes']['missing_in_converted']),
                     len(diff_report['nodes']['extra_in_converted']),
                     diff_report['edges']['matched'],
                     len(diff_report['edges']['missing_in_converted']),
                     len(diff_report['edges']['extra_in_converted']),
                     diff_report['taps']['matched'],
                     len(diff_report['taps']['missing_in_converted']),
                     len(diff_report['taps']['extra_in_converted'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
