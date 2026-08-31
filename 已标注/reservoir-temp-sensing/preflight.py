# -*- coding: utf-8 -*-
"""L0 输入预检器（#4 定案混合形态的正式实现，转正自 prototype-precheck）。

两层检查、一次合并出口，首错不停一次报齐：

  形状层  l0-input-contract.schema.json（JSON Schema 契约）冻结 intent 结构子集，
          违规报 JSON 路径。schema 是数据资产，与 catalog 同层放在 skill 的
          assets/contracts/ 下；本模块按候选路径自动定位，规范源与快照两侧同源。
  语义层  目录一致性 / 端口存在性 / main_path 裸实例 / role 兼容 / medium 兼容 /
          引用一致性 / terminal 端点合法性（#9 定档：terminal 以显式端口出现在
          path 端点合法，中间串接违规）。

出口契约：统一 findings（id/level/rule/yamlline/object/message/remedy）；
任何 ERROR → 扣留 layout/svg/topology，退出码 1；WARN 不拦截。
渲染器在 load_yaml 之后、place()/wire() 之前强制调用（约 3 行钩子）；
外部 CLI 与渲染器同源调用本模块，不复制不漂移。

CLI：
    python preflight.py <intent.yaml> [--catalog <catalog.json>] [--json]
退出码: 0 过 / 1 拦截。
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SCHEMA_NAME = 'l0-input-contract.schema.json'
REQUIRED_SECTIONS = ('l0_version', 'system', 'catalog', 'maturity',
                     'extern', 'parts', 'paths')


def default_schema_path():
    cands = (
        os.path.join(HERE, '..', 'assets', 'contracts', SCHEMA_NAME),          # skill 快照侧
        os.path.join(HERE, '..', '..', '.agents', 'skills', 'hydraulic-schematic',
                     'assets', 'contracts', SCHEMA_NAME),                      # 规范源侧
    )
    for p in cands:
        if os.path.isfile(p):
            return os.path.normpath(p)
    return None


def default_catalog_path():
    cands = (
        os.path.join(HERE, '..', 'component-catalog.json'),                    # 规范源侧
        os.path.join(HERE, '..', 'assets', 'component-library',
                     'component-catalog.json'),                                # skill 快照侧
    )
    for p in cands:
        if os.path.isfile(p):
            return os.path.normpath(p)
    return None


# ---------- 行号定位：与渲染器共享同一份 YAML 文本，不需额外工具 ----------

def line_map(text):
    lm = {'parts': {}, 'extern': {}, 'paths': []}
    section = None
    for i, raw in enumerate(text.splitlines(), 1):
        if re.match(r'^\S', raw):
            section = raw.split(':')[0].strip()
            continue
        if section in ('parts', 'extern'):
            m = re.match(r'^\s+([A-Za-z][\w-]*):', raw)
            if m and m.group(1) not in lm[section]:
                lm[section][m.group(1)] = i
        elif section == 'paths' and re.match(r'^\s*-\s*\[', raw):
            lm['paths'].append(i)
    return lm


# ---------- 形状层：声明式契约 ----------

def schema_findings(intent):
    """跑 JSON Schema 契约。jsonschema 缺席时降级为 WARN，语义层照跑不拦路。"""
    out = []
    schema_path = default_schema_path()
    if schema_path is None:
        out.append(dict(id='W-SHAPE-NOFILE', level='WARN', rule='l0-input-contract',
                        yamlline=None, object='schema',
                        message='契约文件 %s 未找到，形状层跳过' % SCHEMA_NAME,
                        remedy='核对 skill assets/contracts/ 是否完整'))
        return out
    try:
        import jsonschema
    except ImportError:
        out.append(dict(id='W-SHAPE-DEP', level='WARN', rule='l0-input-contract',
                        yamlline=None, object='jsonschema',
                        message='jsonschema 未安装，形状层跳过（依赖提示见 SKILL.md）',
                        remedy='pip install jsonschema'))
        return out
    with io.open(schema_path, encoding='utf-8') as f:
        schema = json.load(f)
    for err in sorted(jsonschema.Draft7Validator(schema).iter_errors(intent or {}),
                      key=lambda e: list(e.absolute_path)):
        loc = ''.join('[%r]' % k if isinstance(k, int) else '.%s' % k
                      for k in err.absolute_path).lstrip('.')
        out.append(dict(id='E-SHAPE-%s' % (re.sub(r'[^A-Za-z0-9]+', '-',
                                                     loc or 'root').strip('-').upper()[:40]),
                        level='ERROR', rule='l0-input-contract',
                        yamlline=None, object=loc or '<root>',
                        message='结构契约: %s' % err.message,
                        remedy='按契约 %s 修正该位置的形状' % SCHEMA_NAME))
    return out


# ---------- 语义层 ----------

def semantic_findings(intent, catalog, source_text):
    types = {c['component_type']: c for c in catalog['components']}
    parts = intent.get('parts') or {}
    externs = set(intent.get('extern') or {})
    lm = line_map(source_text) if source_text else {'parts': {}, 'extern': {}, 'paths': []}
    findings = []

    def add(fid, level, line, obj, msg, remedy):
        findings.append(dict(id=fid, level=level, rule=fid.rsplit('-', 1)[0],
                             yamlline=line, object=obj, message=msg, remedy=remedy))

    # 骨架断言保留作双保险（与 schema 必备章节表重叠 ~10 行，#4 定案保留）
    for key in REQUIRED_SECTIONS:
        if key not in (intent or {}):
            add('E-SKELETON-' + key, 'ERROR', None, key,
                'intent 缺必备章节 %s' % key, '按 L0 规范补全后再跑')

    # 目录一致性：catalog 字符串 id@revision 与所载目录比对（WARN，#4 附带发现保留项）
    m = re.match(r'^(.+)@(.+)$', str(intent.get('catalog') or ''))
    if not m or m.group(1) != catalog.get('catalog_id') \
            or m.group(2) != str(catalog.get('catalog_revision')):
        add('E-CAT-ID', 'WARN', None, intent.get('catalog'),
            'catalog 字符串与所载目录不一致（id@revision）', '核对 catalog 版本引用')
    for inst, typ in sorted(parts.items()):
        if typ not in types:
            add('E-CAT-%s' % inst, 'ERROR', lm['parts'].get(inst), '%s:%s' % (inst, typ),
                "类型 %s 不在目录 %s 内，其端口集合无从谈起" % (typ, intent.get('catalog')),
                "改用目录内类型，或先把类型登记进 component-catalog.json 再引用")

    # 逐 path 核对：引用 / 裸实例 / 端口存在性 / medium / role / terminal 端点合法性
    for pi, path in enumerate(intent.get('paths') or []):
        line = lm['paths'][pi] if pi < len(lm['paths']) else None
        tokens = [t for t in path if not str(t).startswith('@')]
        last = len(tokens) - 1
        for ti, tok in enumerate(tokens):
            inst, _, pid = str(tok).partition('.')
            if inst in externs:
                continue
            if inst not in parts:
                add('E-UND-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    '引用一致性: 实例 %s 未在 parts/extern 中声明' % inst,
                    '先在 parts 里声明实例与类型，或改为已声明的边界标记')
                continue
            ct = types.get(parts[inst])
            if ct is None:
                continue
            ports = {p['id']: p for p in ct.get('ports', [])}
            role = ct.get('connection_role')
            if role == 'sensing_only':
                add('E-SENS-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    "role 兼容: %s 为 sensing_only，不得串入 paths" % parts[inst],
                    "从 paths 移除，改写为 taps 条目并指明测点位置")
            elif role == 'terminal' and 0 < ti < last:
                add('E-TERM-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    "role 兼容: %s 为 terminal，只能在 path 端点出现，"
                    "不得中间串接" % parts[inst],
                    "把 %s 移到该 path 的首或尾，或拆分路径" % inst)
            bare = not pid
            if bare:
                mp = ct.get('main_path')
                if mp is None:
                    add('E-BARE-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                        "%s 的 main_path=null（%d 个端口），裸实例无法填充串接端口" %
                        (parts[inst], len(ports)),
                        "写显式端口，如 %s.%s" % (inst, sorted(ports)[0]))
                    continue
                pid = mp.get('in' if ti == 0 else 'out')
            if pid not in ports:
                add('E-PORT-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    "端口存在性: 类型 %s 无端口 %s（可用: %s）" %
                    (parts[inst], pid, ', '.join(sorted(ports))),
                    "改成列出的真实端口 id")
            elif ports[pid].get('medium') != 'hydraulic':
                add('E-MED-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    "medium 兼容: paths 属液压主路，%s 的 medium=%s"
                    % (tok, ports[pid].get('medium')),
                    "该端口属电气/气侧，走 taps 或专线，不入 paths")
    return findings


# ---------- 合并出口 ----------

def preflight(intent, catalog, source_text=None, skip_schema=False):
    """parse 后、布局前的全量预检。形状层+语义层收齐合并，一次报齐。"""
    findings = [] if skip_schema else schema_findings(intent)
    findings += semantic_findings(intent, catalog, source_text)
    errs = [f for f in findings if f['level'] == 'ERROR']
    return dict(tool='l0-preflight',
                ok=not errs,
                status='blocked_pre_layout' if errs else 'cleared_for_layout',
                products_withheld=['layout', 'svg', 'topology'] if errs else [],
                findings=findings)


def emit_preflight_failure(rep, out=sys.stdout):
    """渲染器与 CLI 共用的人类可读出口。"""
    print('[l0-preflight] 预检拦截于布局之前 -> %s' % rep['status'], file=out)
    print('  扣留产物: %s' % ', '.join(rep['products_withheld']), file=out)
    for f in rep['findings']:
        loc = ('YAML 第 %d 行' % f['yamlline']) if f['yamlline'] else '位置: %s' % f['object']
        print('  %-24s %-5s %s\n               %s | %s\n               处方: %s'
              % (f['id'], f['level'], f['object'], loc, f['message'], f['remedy']),
              file=out)


def load_yaml_text(path):
    from ruamel.yaml import YAML
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    return YAML(typ='safe', pure=True).load(text), text


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    args = [a for a in argv if not a.startswith('--')]
    flags = [a for a in argv if a.startswith('--')]
    if not args:
        print('用法: python preflight.py <intent.yaml> [--catalog <catalog.json>] [--json]')
        return 2
    catp = None
    if '--catalog' in flags:
        i = argv.index('--catalog')
        catp = argv[i + 1] if i + 1 < len(argv) else None
    catp = catp or default_catalog_path()
    intent, text = load_yaml_text(args[0])
    with io.open(catp, encoding='utf-8') as f:
        catalog = json.load(f)
    rep = preflight(intent, catalog, text)
    if '--json' in flags:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    elif rep['ok']:
        print('[l0-preflight] %s -> cleared_for_layout，进入 place()/wire()。'
              % os.path.basename(args[0]))
    else:
        emit_preflight_failure(rep)
    return 0 if rep['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
