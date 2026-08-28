# -*- coding: utf-8 -*-
"""方案 A 原型：独立预检工具（渲染器外挂）。

用法:
    python precheck_a.py <intent.yaml> [--catalog <component-catalog.json>] [--json]
退出码: 0 过 / 1 有 ERROR（与 selftest/渲染器同一约定）。

形态特征:
  - 两个独立工件：结构契约 l0-input-contract.schema.json + 本语义脚本。
    不进渲染器，忘记跑 = 不设防；CI/钩子可以挂。
  - 结构层由 jsonschema 报告 JSON 指针（无 YAML 行号——声明式契约天然不感知行号）；
    语义层自带一个轻量行号扫描器，能报 YAML 行。
  - schema 与语义规则、渲染器的解析逻辑各自独立演进，可能漂移。
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA = os.path.join(HERE, 'l0-input-contract.schema.json')

RULE = {
    'UND': '引用一致性', 'CAT': '目录一致性', 'SENS': 'role 兼容',
    'BARE': 'main_path 裸实例', 'PORT': '端口存在性', 'MED': 'medium 兼容',
}


# ---------- 行号扫描（语义层用；schema 层拿不到行号） ----------

def line_map(text):
    """parts 键 / extern 键 / paths 各条目 的 YAML 行号。"""
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


def parse_intent(path):
    from ruamel.yaml import YAML
    with open(path, encoding='utf-8') as f:
        text = f.read()
    data = YAML(typ='safe').load(text)
    return data, text


# ---------- 结构层：JSON Schema ----------
def shape_findings(data, errors):
    out = []
    for e in errors:
        out.append(dict(id='E-SCH', level='ERROR', rule='contract-schema',
                        yamlline=None, object=e.json_path,
                        message='结构契约: %s' % e.message,
                        remedy='按 references/rendering-rules.md 的 intent 章节修正形状'))
    return out


# ---------- 语义层 ----------
def semantic_findings(data, catalog_path, lm):
    cat = json.load(open(catalog_path, encoding='utf-8'))
    types = {c['component_type']: c for c in cat['components']}
    findings = []
    parts = data.get('parts') or {}
    externs = set(data.get('extern') or {})
    path_lines = lm['paths']

    def where(inst):
        return (lm['parts'].get(inst), '%s(%s)' % (inst, parts[inst]))

    n_error = 0

    def add(fid, level, line, obj, msg, remedy):
        nonlocal n_error
        findings.append(dict(id=fid, level=level, rule=fid.rsplit('-', 1)[0],
                             yamlline=line, object=obj, message=msg, remedy=remedy))
        if level == 'ERROR':
            n_error += 1

    # 1) 目录一致性：声明的每个类型都受控；顺带校验 catalog 字符串
    for inst, typ in sorted(parts.items()):
        if typ not in types:
            add('E-CAT-%s' % inst, 'ERROR', lm['parts'].get(inst), '%s:%s' % (inst, typ),
                "类型 %s 不在目录 %s 内，其端口集合无从谈起" % (typ, data.get('catalog')),
                "改用目录内类型，或先把类型登记进 component-catalog.json 再引用")
    m = re.match(r'^(.+)@(.+)$', str(data.get('catalog') or ''))
    if not m or m.group(1) != cat.get('catalog_id') or m.group(2) != str(cat.get('catalog_revision')):
        add('E-CAT-ID', 'WARN', None, data.get('catalog'),
            'catalog 字符串与所载目录不一致（id@revision）', '核对 catalog 版本引用')

    # 2) 引用一致性与逐 token 核对
    seen_token_err = set()
    for pi, path in enumerate(data.get('paths') or []):
        line = path_lines[pi] if pi < len(path_lines) else None
        # @BUS 是母线网名，不是实例
        tokens = [t for t in path if not str(t).startswith('@')]
        for ti, tok in enumerate(tokens):
            inst, _, pid = str(tok).partition('.')
            if inst in externs:
                continue
            if inst not in parts:
                add('E-UND-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    '实例 %s 未在 parts/extern 中声明' % inst,
                    '先在 parts 里声明实例与类型，或改为已声明的边界标记')
                continue
            ct = types.get(parts[inst])
            if ct is None:
                continue  # E-CAT 已报，不再衍生
            ports = {p['id']: p for p in ct.get('ports', [])}
            bare = not pid
            if bare:
                mp = ct.get('main_path')
                if mp is None:
                    add('E-BARE-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                        "%s 的 main_path=null（%d 个端口），裸实例无法填充串接端口" %
                        (parts[inst], len(ports)),
                        "写显式端口，如 %s.%s" % (inst, sorted(ports)[0]))
                    pid = None
                else:
                    pid = mp.get('in' if ti == 0 else 'out')
            if pid is not None and pid not in ports:
                key = ('PORT', inst, pid)
                if key not in seen_token_err:
                    seen_token_err.add(key)
                    add('E-PORT-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                        "端口存在性: 类型 %s 无端口 %s（可用: %s）" %
                        (parts[inst], pid, ', '.join(sorted(ports))),
                        "改成列出的真实端口 id")
            elif pid is not None:
                med = ports[pid].get('medium')
                if med != 'hydraulic':
                    add('E-MED-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                        "medium 兼容: paths 属液压主路，%s 的 medium=%s" % (tok, med),
                        "该端口属电气/气侧，走 taps 或专线，不入 paths")
            if ct.get('connection_role') == 'sensing_only':
                add('E-SENS-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    "role 兼容: %s 为 sensing_only，不得串入 paths" % parts[inst],
                    "从 paths 移除，改写为 taps 条目并指明测点位置")

    findings.sort(key=lambda f: (f['yamlline'] is None, f['yamlline'] or 0))
    return findings


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = {a for a in sys.argv[1:] if a.startswith('--')}
    if not args:
        print(__doc__)
        return 2
    src = os.path.abspath(args[0])
    root = os.path.normpath(os.path.join(HERE, '..', '..',
                                         '.agents', 'skills', 'hydraulic-schematic',
                                         'assets', 'component-library', 'component-catalog.json'))
    catp = os.path.abspath(root)
    for i, a in enumerate(sys.argv[1:]):
        if a == '--catalog':
            catp = os.path.abspath(sys.argv[i + 2])

    import jsonschema
    data, text = parse_intent(src)
    lm = line_map(text)
    validator = jsonschema.Draft7Validator(json.load(open(SCHEMA, encoding='utf-8')))
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    report = dict(tool=os.path.basename(__file__), form='A 独立工具',
                  source=os.path.basename(src),
                  status='failed' if errors else 'unchecked-shape-ok',
                  findings=shape_findings(data, errors))
    sem = semantic_findings(data, catp, lm)
    report['findings'] += sem
    errs = [f for f in report['findings'] if f['level'] == 'ERROR']
    report['status'] = 'failed' if errs else ('passed_with_warnings'
                                              if any(f['level'] == 'WARN' for f in report['findings'])
                                              else 'passed')
    if '--json' in flags:
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0
    print('[form A] %s -> %s（结构 %d 项 / 语义 %d 项）'
          % (report['source'], report['status'],
             len(report['findings']) - len(sem), len(sem)))
    for f in report['findings']:
        loc = ('YAML 第 %d 行' % f['yamlline']) if f['yamlline'] else '位置: %s' % f['object']
        print('  %-14s %-5s %s\n               %s | %s\n               处方: %s'
              % (f['id'], f['level'], f['object'], loc, f['message'], f['remedy']))
    return 0 if report['status'] in ('passed', 'passed_with_warnings') else 1


if __name__ == '__main__':
    sys.exit(main())
