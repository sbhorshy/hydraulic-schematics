# -*- coding: utf-8 -*-
"""拓扑确认单生成器（#12 机制二）。

intent + 受控清单模板 → 人类可读的分段拓扑确认单（markdown）：
  ① 分段拓扑逐行签认（供压/回油/气侧导览，每行 ☐ 由工程师核对）；
  ② 三向机器对账（fail-closed）：实例集、连接背书、追问登记——
     intent 不得发明清单模板之外的连接，模板不得漏背书 intent 的连接；
  ③ 清单对账表（18 行 ↔ 22 实例，含一拆二与未入图原因）；
  ④ 追问区（intent.unknown 分类：未入图/待确认/悬空/参数）+ 安全件对照 + 签认区。

用法: python topology_confirm.py <intent.yaml> <受控模板.yaml> -o <确认单.md>
退出码: 对账有差异 = 1（确认单仍生成，供工程师看到差异后签认或退回）。

#12 定案（串联组合）：audit() 是三向对账的唯一实现，preflight 模板门禁
与本 CLI 共用，不复制不漂移；签认状态记录在模板 `签认:` 区，由 preflight
按 maturity 分级检查（concept 未签认=WARN，其余未签认=ERROR）。
"""
import io
import os
import re
import sys
from datetime import date

from ruamel.yaml import YAML

HERE = os.path.dirname(os.path.abspath(__file__))
BUS_REV = {}          # "@PRESS" -> 压力汇流（由模板母线词汇填充）
INST_NAME = {}        # inst -> 口语名
INST_ROW = {}         # inst -> 清单序号
INST_TYPE = {}        # inst -> catalog 类型


def canon(tok):
    """token 规范形：裸实例 → 通配 'inst.*'（链路中段端口由词典补全）。"""
    if tok.startswith('@'):
        return tok
    return tok if '.' in tok else tok + '.*'


def tok_match(a, b):
    return (a == b
            or (a.endswith('.*') and b.startswith(a[:-1]))
            or (b.endswith('.*') and a.startswith(b[:-1])))


def pair_match(p, q):
    """无向对匹配，含 'inst.*' 通配（intent 链路中段是裸实例）。"""
    return ((tok_match(p[0], q[0]) and tok_match(p[1], q[1]))
            or (tok_match(p[0], q[1]) and tok_match(p[1], q[0])))



def label(tok):
    if tok.startswith('@'):
        return '%s母线(%s)' % (BUS_REV.get(tok, '?'), tok)
    inst, _, port = tok.partition('.')
    name = INST_NAME.get(inst, inst)
    return '%s(%s).%s' % (name, inst, port)


def section_of(p, gas):
    toks = ' '.join(p)
    if gas:
        return '气侧测量段'
    if 'bootstrap_pressure_in' in toks:
        return '增压段（油箱增压）'
    if 'suction' in toks:
        return '吸油段'
    t = INST_TYPE.get(p[0].split('.')[0], '') + INST_TYPE.get(
        p[1].split('.')[0], '')
    if 'case_drain' in toks or '@CASE' in toks or 'case_drain' in t:
        return '壳体回油段'
    if '@PRESS' in toks or 'pressure_out' in toks:
        return '压力汇流段'
    if '@MANIFOLD' in toks:
        return '分配段'
    ty = INST_TYPE.get(p[0].split('.')[0], '') + INST_TYPE.get(
        p[1].split('.')[0], '')
    if 'return_filter' in ty or '@RET' in toks or 'return_in' in toks:
        return '回油段'
    if '@USR' in toks or 'pressure_in' in toks:
        return '用户供压段'
    if '@USERR' in toks or 'return_out' in toks:
        return '用户回油段'
    return '未归类（须人工看）'


def parse_unknown_block(raw):
    """从 intent 原文抓 unknown 块的 slug+注释（注释是工程师话，机器不译）。"""
    lines = raw.splitlines()
    out, inside = [], False
    for ln in lines:
        if re.match(r'^unknown:\s*$', ln):
            inside = True
            continue
        if inside:
            if re.match(r'^\S', ln):
                break
            m = re.match(r'\s*-\s+(\S+)\s*(?:#\s*(.*))?\s*$', ln)
            if m:
                out.append((m.group(1), (m.group(2) or '').strip()))
    return out


def expand_template(tpl):
    """模板侧展开：母线词反查进模块全局（label/分段用），返回
    (连接对, 悬空登记, 追问 slug 集)。供 audit 与确认单渲染共用。"""
    for word, bus in (tpl.get('母线词汇') or {}).items():
        BUS_REV[bus] = word
    busmap = {'@' + w: b for w, b in (tpl.get('母线词汇') or {}).items()}
    tpl_pairs, tpl_dangle, tpl_slugs, seen = [], [], set(), set()
    for row in tpl['行']:
        n = row['序号']
        insts = row.get('展开') or []
        name = row['口语名']
        for i in insts:
            INST_NAME[i] = (row.get('名单') or {}).get(i, name)
            INST_ROW[i] = n
            t = row['类型']
            INST_TYPE[i] = t if isinstance(t, str) else '组合件'
        for slug in row.get('追问') or []:
            tpl_slugs.add(slug)
        for c in row.get('连接') or []:
            portref = c['本件端口']
            ref = c['对端']
            if ref.startswith('unknown:'):
                tpl_dangle.append((n, portref, ref.split(':', 1)[1]))
                tpl_slugs.add(ref.split(':', 1)[1])
                continue
            if '.' in portref:                    # 'PG.pressure_sense' 前缀形
                pre, port = portref.split('.', 1)
                src = ['%s.%s' % (i, port) for i in insts
                       if i.startswith(pre)]
            elif c.get('每实例'):                 # 组合件逐实例
                src = ['%s.%s' % (i, portref) for i in insts]
            else:
                src = ['%s.%s' % (insts[0], portref)]
            dst = [busmap[ref]] if ref.startswith('@') else [ref]
            for a in src:
                for b in dst:
                    key = frozenset((a, b))
                    if key in seen:
                        raise SystemExit('模板重复声明连接: %s | %s' % (a, b))
                    seen.add(key)
                    tpl_pairs.append((a, b))
    return tpl_pairs, tpl_dangle, tpl_slugs


def intent_pairs(intent):
    """intent 侧：paths 相邻对 + taps 对，规范成无向可匹配形。"""
    hyd, gasp = [], []
    for path in intent.get('paths') or []:
        for a, b in zip(path, path[1:]):
            hyd.append((canon(a), canon(b)))
    for t in intent.get('taps') or []:
        gasp.append((canon(t['sensor']), canon(t['at'])))
    return hyd, gasp


def audit(intent, tpl, raw):
    """三向对账（#12 定案的布局门禁断言，串联组合第三环）：
    实例集一致、intent 每条连接有清单背书、清单每条连接有 intent 落地、
    模板追问全部登记 intent.unknown。返回 (差异列表, ctx)；
    ctx 携带配对明细供确认单渲染复用。本函数是 preflight 与本 CLI
    的唯一对账实现，不复制不漂移。"""
    tpl_pairs, tpl_dangle, tpl_slugs = expand_template(tpl)
    hyd, gasp = intent_pairs(intent)
    problems = []
    tp_insts = set(INST_NAME)
    it_insts = set(intent.get('parts') or {})
    if tp_insts != it_insts:
        problems.append('实例集不一致: 模板多[%s] intent多[%s]'
                        % (sorted(tp_insts - it_insts), sorted(it_insts - tp_insts)))
    all_int = hyd + gasp
    display = {}          # intent pair -> 匹配到的模板对（通配端口显形）
    for p in all_int:
        hit = next((q for q in tpl_pairs if pair_match(p, q)), None)
        if hit is None:
            problems.append('intent 连接无清单背书: %s ~ %s'
                            % (label(p[0]), label(p[1])))
        else:
            display[p] = hit
    for q in tpl_pairs:
        if not any(pair_match(q, p) for p in all_int):
            problems.append('清单连接无 intent 落地: %s ~ %s'
                            % (label(q[0]), label(q[1])))
    unk = {s for s, _ in parse_unknown_block(raw)}
    miss = tpl_slugs - unk
    if miss:
        problems.append('模板追问未登记 intent.unknown: %s' % sorted(miss))
    ctx = dict(hyd=hyd, gasp=gasp, display=display, all_int=all_int,
               tpl_pairs=tpl_pairs, tpl_dangle=tpl_dangle,
               inst_count=len(it_insts))
    return problems, ctx


def main():
    argv = sys.argv[1:]
    intent_p, tpl_p = argv[0], argv[1]
    out_p = argv[argv.index('-o') + 1] if '-o' in argv else '拓扑确认单.md'
    yaml = YAML(typ='safe')
    with io.open(intent_p, encoding='utf-8') as f:
        intent = yaml.load(f)
    raw = io.open(intent_p, encoding='utf-8').read()
    with io.open(tpl_p, encoding='utf-8') as f:
        tpl = yaml.load(f)

    problems, ctx = audit(intent, tpl, raw)
    hyd, gasp, display = ctx['hyd'], ctx['gasp'], ctx['display']
    all_int = ctx['all_int']
    it_insts = set(intent.get('parts') or {})

    # ---- 渲染 ----
    o = []
    o.append('# 拓扑确认单 —— %s' % intent.get('system', '?'))
    o.append('')
    o.append('- 生成: %s（topology_confirm.py，#12 机制二样例）' % date.today())
    o.append('- 输入: %s + %s' % (os.path.basename(intent_p),
                                  os.path.basename(tpl_p)))
    o.append('- 规模: 清单 %d 行 → 实例 %d 个、连接 %d 条（液压 %d + 气侧 %d）'
             % (len(tpl['行']), len(it_insts), len(all_int), len(hyd), len(gasp)))
    o.append('- **签认前不进布局**；每行 ☐ 由工程师对照系统实际核对。'
             '分段仅为导览，逐行签认才是机制。')
    o.append('')

    secs = {}
    for p, gas in [(p, False) for p in hyd] + [(p, True) for p in gasp]:
        shown = display.get(p, p)      # 通配端口用模板解析出的具体端口显形
        secs.setdefault(section_of(p, gas), []).append((shown, p))
    order = ['气侧测量段', '增压段（油箱增压）', '吸油段', '壳体回油段',
             '压力汇流段', '分配段', '用户供压段', '用户回油段', '回油段',
             '未归类（须人工看）']
    o.append('## 一、分段拓扑（逐行签认）')
    for s in order:
        if s not in secs:
            continue
        o.append('')
        o.append('### %s（%d 条）' % (s, len(secs[s])))
        o.append('')
        for shown, p in secs[s]:
            o.append('- ☐ %s —— %s' % (label(shown[0]), label(shown[1])))
    o.append('')

    o.append('## 二、清单对账表（%d 行 → %d 实例）' % (len(tpl['行']),
                                                      len(it_insts)))
    o.append('')
    o.append('| 行 | 口语名 | 类型 | 落点 |')
    o.append('|---|---|---|---|')
    for row in tpl['行']:
        insts = row.get('展开') or []
        t = row['类型']
        tn = '+'.join(t) if isinstance(t, list) else (t or '—')
        if insts:
            where = '入图: %s' % ', '.join(insts)
            if len(insts) > 1:
                where += '（一拆%d）' % len(insts)
            st = '✓'
        else:
            where = '未入图——%s' % row.get('未入图原因', '?')
            st = '✗'
        o.append('| %s%s | %s | %s | %s |' % (st, row['序号'],
                                              row['口语名'][:24], tn, where))
    o.append('')

    o.append('## 三、机器对账（fail-closed）')
    o.append('')
    if problems:
        o.append('**对账存在 %d 处差异，签认前必须逐条裁决：**' % len(problems))
        o.append('')
        for pr in problems:
            o.append('- ⚠ %s' % pr)
    else:
        o.append('实例集一致、连接逐条有清单背书、追问全部登记——对账干净。')
    o.append('')

    o.append('## 四、追问区（工程师逐条作答）')
    cats = [('未入图与缺失声明', lambda s: ('not-in-catalog' in s
                                           or 'not-declared' in s)),
            ('悬空端口去向', lambda s: ('destination' in s
                                       or 'ends-are-disconnected' in s)),
            ('待工程确认', lambda s: ('pending' in s or 'assumed' in s
                                     or 'unconfirmed' in s
                                     or 'provisional' in s))]
    unk_block = parse_unknown_block(raw)
    o.append('')
    claimed = set()
    for title, pred in cats:
        rows = [(s, c) for s, c in unk_block if pred(s)]
        claimed |= {s for s, _ in rows}
        if not rows:
            continue
        o.append('### %s（%d）' % (title, len(rows)))
        o.append('')
        for s, c in rows:
            o.append('- ☐ `%s` %s' % (s, ('—— ' + c) if c else ''))
        o.append('')
    rest = [(s, c) for s, c in unk_block if s not in claimed]
    if rest:
        o.append('### 参数与其它（%d）' % len(rest))
        o.append('')
        for s, c in rest:
            o.append('- ☐ `%s` %s' % (s, ('—— ' + c) if c else ''))
        o.append('')

    o.append('## 五、安全件对照（catalog 有而清单未声明）')
    o.append('')
    for a in tpl.get('安全件对照') or []:
        o.append('- ☐ `%s` %s' % (a['类型'], a['提示']))
    o.append('')
    o.append('## 签认')
    o.append('')
    o.append('- 工程师签字：____________　日期：______')
    o.append('- 声明：以上拓扑与系统实际一致；对账差异已逐条裁决；'
             '签认后进入布局，拓扑改动须走确认单换版。')
    o.append('')

    with io.open(out_p, 'w', encoding='utf-8') as f:
        f.write('\n'.join(o))
    print('确认单: %s（差异 %d 处）' % (out_p, len(problems)))
    for pr in problems:
        print('  ⚠', pr)
    return 1 if problems else 0



if __name__ == '__main__':
    sys.exit(main())
