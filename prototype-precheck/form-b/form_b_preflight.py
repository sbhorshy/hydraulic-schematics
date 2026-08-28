# -*- coding: utf-8 -*-
"""方案 B 原型：渲染器内置前置断言层（preflight）。

形态：渲染器 parse 之后、place()/wire() 之前，先跑 preflight(intent, catalog, source_text)。
任何 ERROR → 结构化报告 + exit 1，布局代码一行都不执行。这是"把 TANK-001 事故
拦在走线中段之前"的接入点。

对 render_l0_sheet.py 的实际改动只有 main() 里插三行（其余全在本模块）：

    intent = load_yaml(...)          # 现有
+   rep = preflight(intent, catalog, source_text)
+   if not rep['ok']:
+       emit_preflight_failure(rep)   # 打印报告, 退出码 1

本文件可直接作为 CLI 演示（模拟插入点）：
    python form_b_preflight.py <intent.yaml> [--json]
退出码: 0 过 / 1 拦截。

形态特征:
  - 断言层与渲染器同生命周期：改解析逻辑时顺手改断言层，不会漂移；
    用户想绕都绕不开——不存在"忘了跑"。
  - 全量核对一次报齐（首错不停），行号由带加载器的扫描给出。
  - 契约语义长在渲染器体内：其他工具（审查卡生成器等）无法复用这段逻辑，
    只能整包依赖渲染器。
"""
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- 行号扫描（渲染器内部可以共享同一文本，不需独立工具的额外职责） ----------

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


def preflight(intent, catalog, source_text):
    """parse 后、布局前的全量端口/目录/role-medium 核对。返回结构化报告。"""
    types = {c['component_type']: c for c in catalog['components']}
    parts = intent.get('parts') or {}
    externs = set(intent.get('extern') or {})
    lm = line_map(source_text)
    findings = []

    def add(fid, level, line, obj, msg, remedy):
        findings.append(dict(id=fid, level=level, rule=fid.rsplit('-', 1)[0],
                             yamlline=line, object=obj, message=msg, remedy=remedy))

    # A. 结构骨架先行（B 形态里用最薄的断言而非 schema——契约即代码）
    for key in ('l0_version', 'system', 'catalog', 'maturity', 'extern', 'parts', 'paths'):
        if key not in (intent or {}):
            add('E-SKELETON-' + key, 'ERROR', None, key,
                'intent 缺必备章节 %s' % key, '按 L0 规范补全后再跑')

    # B. 目录一致性
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

    # C. 逐 path 核对：引用 / 裸实例 / 端口存在性 / medium / role
    seen_root = set()
    for pi, path in enumerate(intent.get('paths') or []):
        line = lm['paths'][pi] if pi < len(lm['paths']) else None
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
                continue
            ports = {p['id']: p for p in ct.get('ports', [])}
            root = ('SENS' if ct.get('connection_role') == 'sensing_only'
                    else 'MED' if any(p.get('medium') != 'hydraulic'
                                      and pid and p['id'] == pid for p in ct['ports'])
                    else None)
            # 同一根因只衍生一条 E-BARE/E-PORT 噪声；role 问题单独成条
            if ct.get('connection_role') == 'sensing_only':
                add('E-SENS-p%d.%d' % (pi, ti), 'ERROR', line, tok,
                    "role 兼容: %s 为 sensing_only，不得串入 paths" % parts[inst],
                    "从 paths 移除，改写为 taps 条目并指明测点位置")
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

    errs = [f for f in findings if f['level'] == 'ERROR']
    return dict(form='B 渲染器内置断言层',
                ok=not errs,
                status='blocked_pre_layout' if errs else 'cleared_for_layout',
                products_withheld=['layout', 'svg', 'topology.md'] if errs else [],
                findings=findings)


def emit_preflight_failure(rep):
    """渲染器里真正调用的人类可读出口。"""
    print('[form B] 预检拦截于布局之前 -> %s' % rep['status'])
    print('  扣留产物: %s' % ', '.join(rep['products_withheld']))
    for f in rep['findings']:
        loc = ('YAML 第 %d 行' % f['yamlline']) if f['yamlline'] else '位置: %s' % f['object']
        print('  %-14s %-5s %s\n               %s | %s\n               处方: %s'
              % (f['id'], f['level'], f['object'], loc, f['message'], f['remedy']))


def load_yaml(path):
    from ruamel.yaml import YAML
    with io.open(path, encoding='utf-8') as f:
        text = f.read()
    return YAML(typ='safe').load(text), text


if __name__ == '__main__':
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    src = os.path.abspath(args[0])
    catp = os.path.normpath(os.path.join(
        HERE, '..', '..', '.agents', 'skills', 'hydraulic-schematic',
        'assets', 'component-library', 'component-catalog.json'))
    intent, text = load_yaml(src)
    rep = preflight(intent, json.load(io.open(catp, encoding='utf-8')), text)
    if '--json' in sys.argv[1:]:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    elif rep['ok']:
        print('[form B] %s -> cleared_for_layout，进入 place()/wire()。'
              % os.path.basename(src))
    else:
        emit_preflight_failure(rep)
    sys.exit(0 if rep['ok'] else 1)
