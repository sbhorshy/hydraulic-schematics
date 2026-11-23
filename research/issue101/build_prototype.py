# -*- coding: utf-8 -*-
"""#101 一次性：把两轮挖掘结果拼成单文件决策页（不进 main）。

读 .artifacts/issue101/ 下官方链出过的图，挑出盲投对比对、同类图取值离散度、
优化器排序用的图池，连同剥过 <style>/<metadata> 的图面 SVG 一起填进
research/issue101/prototype_shell.html，输出 readability-prototype.html。

用法（仓库根目录）: python3 research/issue101/build_prototype.py
"""
from __future__ import print_function

import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.agents/skills/hydraulic-schematic/scripts'))
sys.path.insert(0, str(ROOT / 'research/issue101'))
import flat_metrics as F  # noqa: E402
import proto_issue101_readability as R  # noqa: E402

ART = ROOT / '.artifacts/issue101'
SHELL = ROOT / 'research/issue101/prototype_shell.html'
HTML = ROOT / 'research/issue101/readability-prototype.html'
DETAILS = ART / 'details.json'
BASE_KEY = 'base'
L = 'label'

TASKS = [
    dict(id='follow', name='1 · 跟读主线',
         intro='从泵的出口顺着管线一路读到用户或油箱。先自己看，再判断哪张更容易一直跟下去、不被带偏。'
              '「标出要看的部分」只描出该主线的走向和起讫点，不标折点。'),
    dict(id='label', name='2 · 标签找主',
         intro='看到一个标签，先找它的主人。哪张更容易把名字对上元件？「标出要看的部分」只框出要找的标签（一个或两个），'
              '不画元件框，也不画它到元件的连线。'),
    dict(id='joint', name='3 · 三通与跨线桥',
         intro='三通点挤在一起、跨线桥贴着别的节点，都会让「这里到底通不通」难以判断。'
              '「标出要看的部分」投票前只圈出要看的范围，不标间距；揭晓后才加粗那两条走线。'),
    dict(id='parallel', name='4 · 并行走线',
         intro='不同管网的两条线贴着走，容易被读成一条。「标出要看的部分」只加粗那两条走线，不标间距。'),
]

# id, task, metric, 变体 key, 原图是否更好, 标题, 任务说明, 测量名, 高亮, 缩放, 焦点, 圈选半径
PAIRS = [
    ('m1-hook', 'follow', 'm1', 'r2:bus_move-MANIFOLD--100', True,
     '压力线：直着走，还是绕一个回钩',
     '从 EDP-001 的压力出口，经 PF-001、PRV-001 跟到 USER-005。哪张图更容易一路跟下去？',
     '压力 EDP→USER-005 主线', {'type': 'line', 'name': '压力 EDP→USER-005'}, 0.85, [1250, 400], None),
    ('m1-press', 'follow', 'm1', 'r2:node_move-PRV-001--20--40', True,
     '压力线：PRV-001 左移 20 px、上移 40 px',
     '同样从 EDP-001 压力出口跟到 USER-005。两张图 fail 都是 0，B1–B7 状态相同。',
     '压力 EDP→USER-005 主线', {'type': 'line', 'name': '压力 EDP→USER-005'}, 0.9, [1280, 350], None),
    ('m1-boot', 'follow', 'm1', 'r2:node_move-ACC-001-0-20', True,
     '自增压线：ACC-001 下移 20 px',
     '从 @PRESS 经 PRV-002 分出去油箱的自增压支路和去 ACC-001 的蓄压支路。哪张更容易跟？',
     '自增压 @PRESS→油箱 主线', {'type': 'line', 'name': '自增压 @PRESS→油箱'}, 0.62, [620, 600], None),
    ('m1-return', 'follow', 'm1', 'r2:node_move-CV-002--20--80', True,
     '回油线：CV-002 左上移',
     '从 USER-003 经 RF-001 回油箱。注意回油滤与 CV-002 之间那一段。',
     '回油 USER-003→油箱 主线', {'type': 'line', 'name': '回油 USER-003→油箱'}, 0.78, [1440, 1010], None),
    ('m3-far', 'label', 'm3', 'r1:label_below_TANK-001_0', False,
     'TANK-001 的标签：远 108 px / 近 8 px',
     '找到「TANK-001 自增压油箱」。哪个标签更容易一眼对上油箱？',
     'TANK-001 标签', {'type': 'label', 'owner': 'TANK-001'}, 0.55, [250, 700], None),
    ('m3-amb', 'label', 'm3', 'r1:label_above_ACC-001_140', True,
     'ACC-001 的标签：夹在两名之间 / 抬到别处',
     '找到「ACC-001 系统蓄压器」。两张图的标签位置不同，哪个更容易对上真正的蓄压器？',
     'ACC-001 标签', {'type': 'label', 'owner': 'ACC-001'}, 0.7, [700, 720], None),
    ('m3-policy', 'label', 'm3', 'r2x:lab_TANK-001_below_0__lab_EMP-001_below_0', False,
     'TANK-001 与 EMP-001 的标签：108 / 28 px 对 8 / 8 px',
     '一张图里 TANK-001 的标签离油箱 108 px；另一张把它和 EMP-001 的标签都贴回元件旁。整体看，哪张图更容易把标签配到主人？',
     'TANK-001 与 EMP-001 标签', {'type': 'label', 'owners': ['TANK-001', 'EMP-001']}, 0.62, [400, 580], None),
    ('m6-junction', 'joint', 'm6', 'r1:node_move-PRV-001-0-20', False,
     '@USR 母线：两个三通点相隔 22.2 / 42.2 px',
     'PRV-001 的出口支路和 USER-002 的支路都接到 @USR 母线。哪张更容易分清哪条线接在何处？',
     '最近的两个三通点', {'type': 'junction'}, 1.5, [1450, 330], 150),
    ('m6-bridge', 'joint', 'm6', 'r1:node_move-CDF-001-0--20', True,
     '跨线桥：离最近节点 44 / 24 px',
     '竖直的 @PRESS 母线在 CDF-001 出油线上跨过一次。哪张更容易看出「跨过去，没有接通」？',
     '跨线桥到最近的三通点 / 转角', {'type': 'junction'}, 1.8, [905, 405], 130),
    ('m6-corner', 'joint', 'm6', 'r1:node_move-CV-002-0-20', False,
     '三通旁那一小段走线：18 px / 38 px',
     '@USERR 母线底部，回油汇入点旁边那一小段短线。哪张更容易看清线的走向？',
     '三通旁最短线段', {'type': 'junction'}, 1.8, [1560, 1095], 130),
    ('m4-case', 'parallel', 'm4', 'r2:bus_move-CASE--100', True,
     '吸油线与 @CASE 母线并行 10 px',
     '看 FSOV-001 到 EDP-001 的吸油线，和旁边的 @CASE 母线。哪张更容易分清两条线？',
     '16 px 阅读带内的异网并行', {'type': 'corridor'}, 1.3, [640, 390], 190),
    ('m4-merge', 'parallel', 'm4', 'r2:node_move-PF-001--20-40', True,
     '压力线与壳体回油线并行 4 px',
     'PF-001 入口的压力线（粗）与 CDF-001 的壳体回油线（细）。哪张更容易分清？',
     '16 px 阅读带内的异网并行', {'type': 'corridor'}, 1.4, [1000, 390], 170),
]

RECOMMENDED = dict(m1='guard', m2='hint', m3='gate', m4='gate', m5='drop', m6='guard')
# 门槛类指标的原图豁免名单：名单内的越线条目不计预算，名单外的一律计入。
EXEMPT = dict(m3=['ACC-001', 'CDF-001', 'EDP-001', 'EMP-001', 'TANK-001'])

FACTS = {
    'm1': dict(
        range='单条主线最多 9–10 个折点；八条合计 43–51',
        support='合法布局里折点只增不减：537 张变体里没有一张哪条主线的折点少于原图；寻优器进程内筛出的候选里折点更少的 6 张，'
                '每张都违反 B2、B4、B5 中至少一项（1 张 B2，4 张 B4——其中 1 张兼犯 B5，1 张 B5）。'
                '壳体回油那条 9 折点在 538 张图里一张没变——寻优器在局部碰不到它。',
        rec='不劣化下限（人工决定）：候选不得新增折点超限的主线，单条上限 6 个。要减少折点得回到布局规划，不是寻优器的事。'),
    'm2': dict(
        range='合计 15–22 次',
        support='折返会单独变化：同类图里有 17 张八条主线的折点与原图逐项相同、折返却变了（13 张合计 15→16，4 张只是换了主线）；'
                '反过来折点变多而折返没变的有 90 张。12 组盲投里没有一组是为它设计的：折返跟着变了的对比有两组——压力线绕回钩'
                '（这条主线折返 2→4，合计 15→21）和吸油线与 @CASE 母线并行（合计 15→16）——前一组主线折点同时也变了，'
                '后一组并行走线同时也变了，都分不清是哪一项起作用；而且这 17 张每一张都还同时变了'
                '三通间距、跨线桥距离或并行走线，现有样本里没有一张只变折返的图。',
        rec='仅回读提示（人工决定）：跟着主线折点一起报，不单设阈值、不进排序。理由不是它与折点冗余，而是还没有单独隔离它的投票；'
            '先另开一张小票补投，再决定要不要升级为不劣化下限。'),
    'm3': dict(
        range='最远净距 70–168 px；离别的元件更近的标签 1–3 个',
        support='原图自己就有 5 条越线：4 个标签离主人超过 40 px（TANK-001 108、ACC-001 70、CDF-001 48、EDP-001 48 px），'
                'EDP-001 和 EMP-001 离别的元件更近。贴回去的代价逐个不同：TANK-001 可以直接贴回（108→8 px，预算不变），'
                'ACC-001 能从 70 降到 46 px；EDP-001、EMP-001 贴回会多出 B7 越线，CDF-001 贴回会把 B4 压到 4.3 px。'
                '而且标签不是想挪就能挪：第一轮 97 次单步标签改动里 23 次走线直接走不通，第二轮 294 个单步标签候选里又有 36 个。',
        rec='预算门槛（40 px），原图的 5 条按名单豁免（人工决定）：名单外的标签越线一律计入预算，名单内的不计；'
            '预算和不劣化都打平时，越线少的优先。另开一张票定「标签靠近主人且不增 B7 越线」的排布规则，规则落地后取消名单。'),
    'm4': dict(
        range='16 px 带内 0–1 处（一出现就是 4 px 或 10 px）',
        support='原图在 16 px 带内是 0 处，离最近的一对异网并行还有 39.4 px 余量（64 px 带内有 3 处：39.4、44、50 px）。'
                '同类图里一旦出现就是 4 px（5 张）或 10 px（1 张），粗压力线和细线几乎粘在一起。',
        rec='预算门槛（16 px 带、并行至少 24 px，人工决定）：原图有余量，门槛只拦贴线。'),
    'm5': dict(
        range='同类图里恒为 18 px',
        support='接近恒定，但不是常量：渲染器引出段默认 20 px（母线支路 18 px），相向端口会取净距的一半。'
                '538 张里有 2 张是 17 px，进程内筛出的 4668 张里有 146 张是 17 px，而且这些图全部同时 B5 超限。',
        rec='不采纳（人工决定）：同类图里量不到差别，差别最大 1 px，又只与 B5 超限重合（那两张的 B4 仍 pass），进能量函数几乎不会改变排序。'),
    'm6': dict(
        range='三通间距 17.8–57.8 px；三通旁线段 8.2–30 px；跨线桥到最近节点 4–70 px',
        support='收窄后的下限只管三通旁那一小段走线：原图 18 px，同类图 8.2–30 px；把 CV-002 下移 20 px 就能把这一处从 18 拉到 38 px。'
                '三通互距（22 与 42 px）、跨线桥距离（44 与 24 px）在盲投里都看不出差别。',
        rec='不劣化下限（30 px），只管三通旁线段（人工决定）：候选不得新增低于 30 px 的三通旁线段。'
            '三通互距与跨线桥距离留在回读清单里，等出现真能察觉的反例再升级。'),
}

DISPERSION = [
    ('m1_max', 'M1 主线折点 · 单条最多', '+0.23', '合法布局里只增不减；壳体回油那条 9 折点，没有一张同类图更少'),
    ('m1_sum', 'M1 主线折点 · 八条合计', '+0.21', '合计 43–51，合法布局里没有一张少于原图（合计把两段共享走线各计了两次）'),
    ('m2_rev', 'M2 主线折返 · 合计', '+0.35', '合计 15–22；23 张同类图折返合计变了，其中 13 张八条主线折点与原图逐项相同——M2 量到了 M1 看不到的东西'),
    ('m3_max', 'M3 最远标签净距', '−0.01', '同类图里 70–168 px；B1–B7 没有「标签到主人距离」这一项，但也不是想放多远就多远：第一轮 97 次单步标签改动里 23 次走不通'),
    ('m3_amb', 'M3 离别的元件更近的标签数', '+0.13', '原图已有 2 个；同类图里 1–3 个都保持着与原图相同的 B1–B7 状态'),
    ('m4_n', 'M4 16 px 带内并行处数', '+0.08', '原图 0 处，离最近一对还有 39.4 px；同类图里有 4 px、10 px 的贴线'),
    ('m5_min', 'M5 端口末段 · 最短', None, '同类图里是常量 18 px；全部 538 张里有 2 张是 17 px'),
    ('m6_jg', 'M6 最近的两个三通点', '−0.12', '22 px 挤在一起和 58 px 分开都保持着与原图相同的 B1–B7 状态；盲投里看不出差别'),
    ('m6_jb', 'M6 三通旁最短线段', '+0.33', '18 px 与 30 px 都在预算内；盲投里 18 px 那张更难看清'),
    ('m6_br', 'M6 跨线桥到最近节点', '+0.01', '贴到 4 px 仍是 fail 0、与原图同样的 B1–B7 状态；盲投里看不出差别'),
]

DISPERSION_NOTE = (
    '样本怎么来的：从人工认可的原图出发，只动布局（挪元件、挪母线、改走廊、挪标签），每个变体都走官方 '
    'render → validate，只留下 fail 0、B1–B7 七项状态与原图逐项相同、B7 越线条目也相同的图（原图 B7 本身就有 1 处越线，'
    '所以这是「与原图同状态」，不是「全部通过」）。其中 254 张来自单步邻域（寻优器邻域的每个合法单步和每个标签槽位都出过图；'
    '其中 189 张六项指标与原图完全相同——原图在局部是稳的），190 张来自第二轮为找极值做的定向搜索，另有 1 张后补的标签组合。'
    '所以这张表说的是「同类图里最远能走到哪」，不是常见程度——多数图仍停在原图值；也只覆盖 1# 一份输入。'
    '「与总线长的秩相关」多数接近 0，但折返合计 +0.35、三通旁线段 +0.33、主线折点 +0.23 / +0.21 属弱到中等正相关：'
    '线长排序不能代替这些指标，但也不是全都无关。'
)

# ---------------------------------------------------------------- 数据装载

def load_rows():
    out = {BASE_KEY: dict(wd=ART / 'base', row=None, kind='原图')}
    v1 = json.loads((ART / 'mine/variants.json').read_text(encoding='utf-8'))
    for r in v1['rows']:
        if not r['ok'] or not (ART / 'mine/var' / r['id'] / 'validation-report.json').is_file():
            continue
        out['r1:' + r['id']] = dict(wd=ART / 'mine/var' / r['id'], row=r, kind='r1')
    c2 = json.loads((ART / 'mine2/confirm.json').read_text(encoding='utf-8'))
    for r in c2:
        if not r['ok'] or not (ART / 'mine2/var' / r['id'] / 'validation-report.json').is_file():
            continue
        out['r2:' + r['id']] = dict(wd=ART / 'mine2/var' / r['id'], row=r, kind='r2')
    extra = json.loads((ART / 'mine2/extra.json').read_text(encoding='utf-8'))
    for r in extra:
        if not r['ok'] or not (ART / 'mine2/var' / r['id'] / 'validation-report.json').is_file():
            continue
        out['r2x:' + r['id']] = dict(wd=ART / 'mine2/var' / r['id'], row=r, kind='r2x')
    return out


def flat_of(key, rows, cache=None):
    if key == BASE_KEY:
        if cache is None:
            return F.flat(R.summarize(R.load_report(str(rows[key]['wd'])))[0])
        return cache['base']
    return F.flat(rows[key]['row']['metrics'])


def status_sig_of(key, rows):
    if key == BASE_KEY:
        return F.status_sig(R.summarize(R.load_report(str(rows[key]['wd'])))[2])
    return F.status_sig(rows[key]['row']['budget'])


def statuses_of(key, rows):
    """七项预算状态 + B7 越线条目数（给揭晓文字用）。"""
    panel = (R.summarize(R.load_report(str(rows[key]['wd'])))[2] if key == BASE_KEY
             else rows[key]['row']['budget'])
    b7 = (panel.get('B7') or {}).get('measured') or {}
    return {k: v['status'] for k, v in panel.items()}, int(b7.get('violations') or 0)


def over_budget(key, rows):
    """非 pass 的预算项数 + B7 相对原图多出的越线条目数。"""
    if key == BASE_KEY:
        panel = R.summarize(R.load_report(str(rows[key]['wd'])))[2]
        return sum(1 for v in panel.values() if v['status'] != 'pass')
    r = rows[key]['row']
    over = sum(1 for v in r['budget'].values() if v['status'] != 'pass')
    b7 = (r['budget'].get('B7') or {}).get('measured') or {}
    return over + max(0, int(b7.get('violations') or 0) - 1)


# ---------------------------------------------------------------- 图面细节

def pt(p):
    return [round(float(p[0]), 1), round(float(p[1]), 1)]


def pair_list(points_a, points_b, limit=100):
    out = []
    for a in points_a:
        for b in points_b:
            d = R.pt_dist(a, b)
            if 0.01 < d <= limit:
                out.append([round(d, 1)] + pt(a) + pt(b))
    return sorted(out)


def build_details(wd):
    """官方报告 -> 页面叠加层要用的全量证据 + 紧凑版（供所有同类图统计越线数）。"""
    report = R.load_report(str(wd))
    model = R.build_model(report)
    R.classify_vertices(model)
    lines = R.metric_main_lines(model)
    main_anchors = set(a for ln in lines for a in ln['anchors'])
    labels = R.metric_labels(model)
    events = R.metric_corridor(model, 64.0, 24.0, main_anchors)
    stubs = R.metric_stubs(model)
    joints = R.metric_junctions(model)
    nodes = model['nodes']

    d_lines = {}
    for ln in lines:
        runs = [r for pts in ln['pts'] for r in R.runs_of(pts)]
        back = []
        for i in range(len(runs) - 1):
            d0, d1 = R.dir_of(*runs[i]), R.dir_of(*runs[i + 1])
            if d0 in 'RL' and d1 in 'RL' and d0 != d1:
                back.append(pt(runs[i + 1][0]) + pt(runs[i + 1][1]))
            if d0 in 'UD' and d1 in 'UD' and d0 != d1:
                back.append(pt(runs[i + 1][0]) + pt(runs[i + 1][1]))
        d_lines[ln['name']] = [ln['bends'], ln['reversals'],
                               [[pt(p) for p in hop] for hop in ln['pts']],
                               [pt(p) for p in ln['bend_pts']], back]

    d_labels = {}
    for lab in labels:
        rival_fp = nodes.get(lab['rival'], {}).get('footprint') if lab['rival'] else None
        d_labels[lab['owner']] = [lab['gap'], lab['rival'], lab['rival_gap'],
                                  pt(lab['bbox'][:2]) + pt(lab['bbox'][2:]),
                                  pt(lab['footprint'][:2]) + pt(lab['footprint'][2:]),
                                  pt(rival_fp[:2]) + pt(rival_fp[2:]) if rival_fp else None]

    d_corridor = []
    for e in events:
        ra, rb = e['ra'], e['rb']
        d_corridor.append([e['d'], e['overlap'], bool(e['main'])] + pt(ra[0]) + pt(ra[1]) + pt(rb[0]) + pt(rb[1]))

    d_bridges = []
    for b in joints['bridges']:
        near = None
        if b['other_gap'] is not None:
            cand = [p for p in model['junction'] + model['bend'] if R.pt_dist(p, b['pos']) < b['other_gap'] + 0.6]
            if cand:
                near = pt(min(cand, key=lambda p: R.pt_dist(p, b['pos'])))
        d_bridges.append(pt(b['pos']) + [b['own_gap'], b['other_gap'], near])

    full = dict(
        lines=d_lines, labels=d_labels, corridor=d_corridor,
        jpairs=pair_list(model['junction'], model['junction']),
        jbpairs=pair_list(model['junction'], model['bend']),
        bridges=d_bridges, junctions=[pt(p) for p in model['junction']],
    )
    compact = dict(
        lines={k: [v[0], v[1]] for k, v in d_lines.items()},
        labels={k: [v[0], v[1], v[2]] for k, v in d_labels.items()},
        corridor=[[e[0]] for e in d_corridor], jpairs=[[p[0]] for p in full['jpairs']],
        jbpairs=[[p[0]] for p in full['jbpairs']],
        bridges=[[0, 0, 0, b[3]] for b in d_bridges],
    )
    show = dict(
        m1='折点 ' + ' / '.join(str(ln['bends']) for ln in lines) + '（最多 %d，%s）' % (
            max(ln['bends'] for ln in lines), max(lines, key=lambda ln: ln['bends'])['name']),
        m2='折返 ' + ' / '.join(str(ln['reversals']) for ln in lines) + '（合计 %d）' % sum(ln['reversals'] for ln in lines),
        m3='最远 %g px；离别的元件更近：%s' % (
            max(lab['gap'] for lab in labels),
            '、'.join(r['owner'] for r in R.metric_labels(model) if r['rival_gap'] is not None and r['rival_gap'] < r['gap']) or '无'),
        m4='16 px 带内 %d 处' % sum(1 for e in R.metric_corridor(model, 16.0, 24.0, main_anchors)),
        m5='端口末段最短 %g px' % min(s['length'] for s in stubs),
        m6='三通间距 %s；三通旁线段 %s；跨线桥 %s' % (
            '%g px' % joints['junction_gap']['d'] if joints['junction_gap'] else '—',
            '%g px' % joints['junction_bend']['d'] if joints['junction_bend'] else '—',
            ('%g px' % min(b['other_gap'] for b in joints['bridges'] if b['other_gap'] is not None)) if any(
                b['other_gap'] is not None for b in joints['bridges']) else '—'),
    )
    return dict(full=full, compact=compact, show=show,
                length=round(sum(R.seg_len(s['start'], s['end']) for s in report['topology']['segments']), 1))


def load_details(rows):
    if DETAILS.is_file():
        cached = json.loads(DETAILS.read_text(encoding='utf-8'))
        for d in cached.values():  # 旧缓存里的两处措辞已更正
            d['show']['m5'] = d['show']['m5'].replace('（渲染器常量）', '')
            d['show']['m6'] = d['show']['m6'].replace('三通到转角', '三通旁线段')
        return cached
    out = {}
    for i, key in enumerate(sorted(rows)):
        out[key] = build_details(rows[key]['wd'])
        if i % 70 == 0:
            print('details %d/%d' % (i, len(rows)), flush=True)
    DETAILS.write_text(json.dumps(out, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    return out


# ---------------------------------------------------------------- 操作描述

def describe_ops(key, rows):
    if key == BASE_KEY:
        return '人工认可的原图'
    if key.startswith('r2x:'):
        ops = rows[key]['row']['moves']
    elif key.startswith('r2:'):
        ops = rows[key]['row'].get('ops') or rows[key]['row'].get('moves')
    else:
        import ast
        mv = rows[key]['row']['moves'][0] if rows[key]['row']['moves'] else ''
        if mv.startswith("('"):
            ops = [ast.literal_eval(mv)]
        elif '->' in mv:
            left, right = mv.split('->')
            inst = left.strip().split('.')[0]
            dest = right.strip().split()
            ops = [('label', inst, dest[0], int(dest[1]) if len(dest) > 1 else 0)]
        else:
            return mv
    parts = []
    for op in ops:
        o = list(op)
        if o[0] == 'node_move':
            ds = []
            if o[2]:
                ds.append(('右移' if o[2] > 0 else '左移') + ' %d px' % abs(o[2]))
            if o[3]:
                ds.append(('下移' if o[3] > 0 else '上移') + ' %d px' % abs(o[3]))
            parts.append('%s %s' % (o[1], '、'.join(ds)))
        elif o[0] == 'bus_move':
            parts.append('@%s 母线%s %d px' % (o[1], '右移' if o[2] > 0 else '左移', abs(o[2])))
        elif o[0] == 'label':
            slot = {'below': '下方', 'above': '上方', 'right': '右侧'}.get(o[2], o[2])
            parts.append('%s 标签移到%s%s' % (o[1], slot, '、偏移 %d px' % o[3] if o[3] else '（紧贴）'))
        elif o[0] in ('lane_move', 'lane_del', 'lane_add', 'vlane_move', 'vlane_del', 'vlane_add'):
            axis = '水平走廊' if o[0].startswith('lane') else '竖向走廊'
            if o[0].endswith('_move'):
                parts.append('%s %d %s %d px' % (axis, o[1], '下移/右移' if o[2] > 0 else '上移/左移', abs(o[2])))
            elif o[0].endswith('_del'):
                parts.append('删掉%s %d' % (axis, o[1]))
            else:
                parts.append('新增%s y/x=%g' % (axis, o[1]))
        else:
            parts.append(str(op))
    return '；'.join(parts)


# ---------------------------------------------------------------- SVG

def sheet_css():
    src = re.search(r'<style>([\s\S]*?)</style>',
                    io.open(str(ART / 'base' / '1#系统原理图.svg'), encoding='utf-8').read()).group(1)

    def scope(line):
        s = line.strip()
        if not s or s.startswith('/*') or s.startswith('*') or s.startswith('*/'):
            return '  ' + s
        if s.startswith(':root'):
            s = '.sheet' + s[6:]
        elif not s.startswith('.sheet'):
            s = '.sheet ' + s
        return '  ' + s

    return '\n'.join(scope(line) for line in src.splitlines())


def sheet_inner(wd):
    s = io.open(str(wd / '1#系统原理图.svg'), encoding='utf-8').read()
    s = re.sub(r'<style[\s\S]*?</style>', '', s)
    s = re.sub(r'<metadata[^>]*/>', '', s)
    s = re.sub(r'\s+id="[^"]*"', '', s)
    s = re.sub(r'\s+data-[a-z-]+="[^"]*"', '', s)
    s = re.sub(r'<\?xml[^>]*\?>', '', s)
    s = re.sub(r'<svg[^>]*>', '', s, count=1)
    s = re.sub(r'</svg>\s*$', '', s)
    return s.strip()


# ---------------------------------------------------------------- 组装

def b7_violations(key, rows):
    panel = rows[key]['row']['budget'] if key != BASE_KEY else R.summarize(R.load_report(str(rows[key]['wd'])))[2]
    return int(((panel.get('B7') or {}).get('measured') or {}).get('violations') or 0)


def rows_for_show(pair, a_key, b_key, details, rows):
    metric, overlay = pair[2], pair[8]
    out = []
    if metric == 'm1':
        name = overlay['name']
        out.append(('这条主线折点', str(details[a_key]['full']['lines'][name][0]), str(details[b_key]['full']['lines'][name][0])))
        out.append(('这条主线折返', str(details[a_key]['full']['lines'][name][1]), str(details[b_key]['full']['lines'][name][1])))
        out.append(('八条主线折点合计', str(flat_of(a_key, rows)['m1_sum']), str(flat_of(b_key, rows)['m1_sum'])))
    elif metric == 'm3':
        owners = overlay.get('owners') or [overlay.get('owner')]
        for owner in owners:
            for label, field in (('净距', 0), ('离别的元件更近', 2)):
                va, vb = details[a_key]['full']['labels'][owner], details[b_key]['full']['labels'][owner]
                if field == 0:
                    out.append(('%s 到所属元件净距' % owner, '%g px' % va[0], '%g px' % vb[0]))
                else:
                    out.append(('%s 离别的元件更近' % owner,
                                ('%s %g px' % (va[1], va[2])) if va[2] is not None and va[2] < va[0] else '否',
                                ('%s %g px' % (vb[1], vb[2])) if vb[2] is not None and vb[2] < vb[0] else '否'))
        out.append(('超过 40 px 的标签数', str(flat_of(a_key, rows)['m3_far']), str(flat_of(b_key, rows)['m3_far'])))
        out.append(('B7 越线条目', str(b7_violations(a_key, rows)), str(b7_violations(b_key, rows))))
    elif metric == 'm6':
        fa, fb = flat_of(a_key, rows), flat_of(b_key, rows)
        focus, radius = pair[10], pair[11]
        if pair[0] == 'm6-corner':
            def local(k):
                ps = [p for p in details[k]['full']['jbpairs']
                      if R.pt_dist(p[1:3], focus) <= radius and R.pt_dist(p[3:5], focus) <= radius]
                return min(ps, key=lambda p: p[0]) if ps else None
            la, lb = local(a_key), local(b_key)
            if la and lb:
                out.append(('所问位置的三通旁线段', '%g px' % la[0], '%g px' % lb[0]))
        if pair[0] == 'm6-bridge':
            def near(k):
                bs = [b for b in details[k]['full']['bridges'] if R.pt_dist(b[:2], focus) <= radius and b[3] is not None]
                return min(bs, key=lambda b: b[3]) if bs else None
            la, lb = near(a_key), near(b_key)
            if la and lb:
                out.append(('所问位置的跨线桥到最近节点', '%g px' % la[3], '%g px' % lb[3]))
        for field, name in (('m6_jg', '最近两三通点'), ('m6_jb', '全图最短的三通旁线段'), ('m6_br', '跨线桥到最近节点')):
            va, vb = fa[field], fb[field]
            out.append((name, '%g px' % va if va is not None else '—', '%g px' % vb if vb is not None else '—'))
    else:
        fa, fb = flat_of(a_key, rows), flat_of(b_key, rows)
        out.append(('16 px 带内并行处数', str(fa['m4_n']), str(fb['m4_n'])))
        out.append(('并行总长', '%g px' % fa['m4_len'], '%g px' % fb['m4_len']))
    return out


FLAT_NAMES = dict(m1_max='单条折点', m1_sum='折点合计', m2_rev='折返合计', m2_back='逆向占比',
                  m3_max='最远标签', m3_mean='标签平均', m3_far='远离标签数', m3_amb='归属不明数',
                  m4_n='并行处数', m4_len='并行长度', m6_jg='三通间距', m6_jb='三通旁线段', m6_br='跨线桥间距')
OWN_KEYS = dict(m1=('m1_max', 'm1_sum'), m2=('m2_rev',), m3=('m3_max', 'm3_amb'), m4=('m4_n', 'm4_len'), m6=('m6_jg', 'm6_jb', 'm6_br'))


def confounds(pair, a, b, rows, details):
    """两张图之间除了本对指标之外还变了什么：标量、别的主线、B7 越线数、总线长。"""
    fa, fb = flat_of(a, rows), flat_of(b, rows)
    out = []
    for k, name in FLAT_NAMES.items():
        if k in OWN_KEYS[pair[2]]:
            continue
        if fa[k] != fb[k]:
            out.append('%s %g → %g' % (name, fa[k], fb[k]))
    la, lb = details[a]['full']['lines'], details[b]['full']['lines']
    shown = pair[8].get('name')
    for name in la:
        if name == shown or name not in lb or la[name][:2] == lb[name][:2]:
            continue
        out.append('%s 折点/折返 %d/%d → %d/%d' % (name, la[name][0], la[name][1], lb[name][0], lb[name][1]))
    if fa['m2_rev'] == fb['m2_rev'] and any(la[n][1] != lb[n][1] for n in la if n in lb and n != shown):
        out.append('折返换了主线')
    b7a, b7b = b7_violations(a, rows), b7_violations(b, rows)
    if b7a != b7b:
        out.append('B7 越线条目 %d → %d' % (b7a, b7b))
    if details[a]['length'] != details[b]['length']:
        out.append('总线长 %g → %g px' % (details[a]['length'], details[b]['length']))
    return ('这张图还同时变了：' + '、'.join(out) + '。') if out else '除本对指标外，标量上没有别的变化。'


def class_reason(a, b, rows, cls_set):
    """两张图的类别关系：same = 同类图；count = 七项状态逐项相同、只是 B7 越线条目不同；status = 状态不同。"""
    if (a == BASE_KEY or a in cls_set) and (b == BASE_KEY or b in cls_set):
        return 'same'
    return 'count' if statuses_of(a, rows)[0] == statuses_of(b, rows)[0] else 'status'


def pick_extreme(keys, field, want, rows, avoid=()):
    pool = [k for k in keys if k not in avoid and flat_of(k, rows)[field] is not None]
    if not pool:
        return None
    return sorted(pool, key=lambda k: flat_of(k, rows)[field], reverse=(want == 'max'))[0]


def build():
    rows = load_rows()
    base_sig = status_sig_of(BASE_KEY, rows)
    cls = [k for k in sorted(rows) if k != BASE_KEY and rows[k]['row'] and not rows[k]['row']['fail']
           and status_sig_of(k, rows) == base_sig]
    print('sheets %d, class %d' % (len(rows), len(cls)), flush=True)
    details = load_details(rows)
    base = details[BASE_KEY]
    flat_cache = {'base': F.flat(R.summarize(R.load_report(str(rows[BASE_KEY]['wd'])))[0])}

    cls_set = set(cls)
    pairs = []
    for i, spec in enumerate(PAIRS):
        pid, task, metric, variant, base_better = spec[:5]
        a_is_base = (i % 2 == 0)
        a, b = (BASE_KEY, variant) if a_is_base else (variant, BASE_KEY)
        better = 'a' if a_is_base == base_better else 'b'
        overlay = dict(spec[8])
        pairs.append(dict(id=pid, task=task,
                          taskName=next(t['name'] for t in TASKS if t['id']==task),
                          metric=metric, title=spec[5], prompt=spec[6],
                          measure=spec[7], a=a, b=b, better=better, overlay=overlay,
                          zoom=spec[9], focus=spec[10], radius=spec[11],
                          show_rows=rows_for_show(spec, a, b, details, rows),
                          note=confounds(spec, a, b, rows, details),
                          b7=[statuses_of(a, rows)[1], statuses_of(b, rows)[1]],
                          cls=class_reason(a, b, rows, cls_set)))
        print('pair %-10s %-48s %s vs %s better %s %s' % (pid, variant[:48], a, b, better, pairs[-1]['note']), flush=True)

    needed = {BASE_KEY}
    for p in pairs:
        needed.update((p['a'], p['b']))
    all_ok = sorted(rows)
    extreme_keys = []
    for field, want in (('m1_sum', 'max'), ('m2_rev', 'max'), ('m3_max', 'min'), ('m3_max', 'max'),
                        ('m4_n', 'max'), ('m6_jg', 'min'), ('m6_jg', 'max'), ('m6_br', 'min')):
        k = pick_extreme(cls, field, want, rows)
        if k:
            extreme_keys.append(k)
            needed.add(k)

    pool_keys = [BASE_KEY] + sorted(needed - {BASE_KEY})
    for k in ('r1:label_above_ACC-001_140', 'r1:label_above_ACC-001_100', 'r2:node_move-PRV-001--20--80',
              'r2:bus_move-MANIFOLD--100', 'r2:node_move-PF-001-80--20', 'r1:node_move-CDF-001-0-20'):
        if k in rows:
            pool_keys.append(k)
    for k in sorted(rows):
        if k in pool_keys or k in cls:
            continue
        r = rows[k]['row']
        if not r['fail'] and over_budget(k, rows) == 2 and len(pool_keys) < 24:
            pool_keys.append(k)
    for k in sorted(rows):
        if k in pool_keys or not rows[k]['row']['fail']:
            continue
        r = rows[k]['row']
        if r['fail'] <= 3 and len([x for x in pool_keys if rows[x]['row'] and rows[x]['row']['fail']]) < 5:
            pool_keys.append(k)
    pool_keys = list(dict.fromkeys([k for k in pool_keys if k in rows]))
    needed.update(pool_keys)

    def kind_of(k):
        if k == BASE_KEY:
            return '原图'
        if rows[k]['row']['fail']:
            return '硬缺陷'
        if k in cls:
            return '同类图'
        return '预算变差'

    sheets = {}
    for k in sorted(needed):
        sheets[k] = dict(desc=describe_ops(k, rows), kind=kind_of(k),
                         fail=int(rows[k]['row']['fail']) if k != BASE_KEY else 0,
                         over=over_budget(k, rows), length=details[k]['length'],
                         d=dict(details[k]['full'], show=details[k]['show']))

    gallery = []
    def gal(metric, tag, key, text, overlay, zoom=1.8, value=None):
        if key is None:
            return
        d = details[key]['full']
        focus = [855, 695]
        if overlay['type'] == 'label':
            v = d['labels'].get(overlay['owner'])
            if v:
                focus = [(v[3][0] + v[4][0]) / 2, (v[3][1] + v[4][1]) / 2]
        elif overlay['type'] == 'junction':
            p = d['jpairs'][0] if d['jpairs'] else (d['bridges'][0] if d['bridges'] else None)
            if p:
                focus = [(p[1] + p[3]) / 2, (p[2] + p[4]) / 2]
        elif overlay['type'] == 'corridor':
            e = d['corridor'][0]
            if e:
                focus = [(e[3] + e[7]) / 2, (e[4] + e[8]) / 2]
        gallery.append(dict(metric=metric, tag=tag, key=key, text=text, value=value, overlay=overlay,
                            zoom=zoom, focus=[round(x) for x in focus]))

    EXTREMES = [
        ('m1_sum', 'M1 主线折点', '折点最多', 'max', '八条主线折点合计', {'type': 'line', 'name': '压力 EDP→USER-005'}, 0.8, None),
        ('m2_rev', 'M2 主线折返', '折返最多', 'max', '折返合计', {'type': 'line', 'name': '压力 EDP→USER-005'}, 0.6,
         '折返合计 22 次（原图 15 次）；多出的 7 次都在两条压力线：压力 EDP→USER-005 2→5 次、压力 EMP→USER-001 0→4 次'),
        ('m3_max', 'M3 标签归属', '最远标签最近', 'min', '最远标签净距', {'type': 'label', 'owner': None}, 1.0, None),
        ('m3_max', 'M3 标签归属', '标签最远', 'max', '最远标签净距', {'type': 'label', 'owner': None}, 1.0, None),
        ('m6_jg', 'M6 三通与跨线桥', '三通最挤', 'min', '最近两三通点', {'type': 'junction'}, 2.0, None),
        ('m6_jg', 'M6 三通与跨线桥', '三通最开', 'max', '最近两三通点', {'type': 'junction'}, 2.0, None),
        ('m6_br', 'M6 三通与跨线桥', '桥最挤', 'min', '跨线桥到最近节点', {'type': 'junction'}, 2.0, None),
    ]
    seen_ext = set()
    for field, metric, tag, want, desc, overlay, zoom, text in EXTREMES:
        k = pick_extreme(cls, field, want, rows, avoid=seen_ext)
        if not k:
            continue
        seen_ext.add(k)
        ov = dict(overlay)
        if field == 'm3_max':
            owner = max(details[k]['full']['labels'].items(), key=lambda kv: kv[1][0])[0]
            ov['owner'] = owner
        v = flat_of(k, rows)[field]
        unit = ' 个' if field.startswith('m1_') else ' 次' if field.startswith('m2_') else ' px'
        gal(metric, tag, k, text or '%s %g%s（原图 %g%s）' % (desc, v, unit, flat_cache['base'][field], unit),
            ov, zoom, '%g%s' % (v, unit))
    gal('M1 主线折点', '折点最少', BASE_KEY, '原图已经是八条主线折点合计的下限（43），合法布局里没有一张更少',
        {'type': 'line', 'name': '壳体回油 EDP→油箱'}, 0.6)
    gal('M2 主线折返', '折返最少', BASE_KEY, '原图已经是同类图里折返合计的下限（15 次，422 / 445 张并列）',
        {'type': 'line', 'name': '回油 USER-003→油箱'}, 0.75)
    gal('M3 标签归属', '标签最近', 'r1:label_below_TANK-001_0' if 'r1:label_below_TANK-001_0' in rows else None,
        'TANK-001 标签从 108 px 贴近到 8 px，B1–B7 状态与原图相同', {'type': 'label', 'owner': 'TANK-001'}, 0.75)
    gal('M4 并行走线', '贴得最近', 'r2:node_move-PF-001--20-40' if 'r2:node_move-PF-001--20-40' in rows else None,
        'PF-001 入口的压力线与壳体回油线并行 4 px（长 70 px）', {'type': 'corridor'}, 1.5)
    gal('M4 并行走线', '16 px 带内最干净', BASE_KEY,
        '16 px 带内 0 处异网并行，与 439 / 445 张同类图并列；64 px 带内有 3 处（最近 39.4 px）', {'type': 'corridor'}, 1.3)
    gal('M5 端口末段', '接近恒定', BASE_KEY, '538 张官方出图里 536 张最短 18 px、2 张 17 px',
        {'type': 'line', 'name': '吸油 油箱→EMP'}, 0.9)
    gal('M6 三通与跨线桥', '单步里桥最远', 'r1:node_move-CDF-001-0-20' if 'r1:node_move-CDF-001-0-20' in rows else None,
        '跨线桥到最近节点 64 px（单步变体里最远；同类图最远 70 px）', {'type': 'junction'}, 2.0)

    dispersion = []
    for field, label, rho, meaning in DISPERSION:
        vals = [flat_of(k, rows)[field] for k in cls]
        vals = [v for v in vals if v is not None]
        dispersion.append(dict(label=label, base=flat_cache['base'][field], min=min(vals), max=max(vals),
                               nval=len(set(vals)), n=len(cls), rho=rho, meaning=meaning))

    data = dict(
        base=BASE_KEY, recommended=RECOMMENDED, exempt=EXEMPT,
        meta=dict(sheets=len(rows), cls=len(cls), moves='挪元件 / 挪母线 / 改走廊 / 挪标签；两轮挖掘：单步邻域 + 定向极值',
                  pool=len(pool_keys)),
        tasks=TASKS, pairs=pairs, sheets=sheets,
        clsOff={k: details[k]['compact'] for k in cls}, classList=cls,
        gallery=gallery, pool=pool_keys,
        dispersion=dispersion, dispersion_note=DISPERSION_NOTE, facts=FACTS,
    )
    html = SHELL.read_text(encoding='utf-8')
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')
    html = html.replace('__SHEET_CSS__', sheet_css()).replace('__SHEET_TEMPLATES__', '\n'.join(
        '<template class="sheet-tpl" data-key="%s"><svg viewBox="0 0 1710 1390"><g class="art">%s</g></svg></template>'
        % (k.replace('&', '&amp;').replace('"', '&quot;'), sheet_inner(rows[k]['wd']))
        for k in sorted(needed)))
    html = html.replace('__DATA_JSON__', payload)
    HTML.write_text(html, encoding='utf-8')
    print('written %s (%.1f MB), sheets embedded %d, gallery %d, pool %d' % (
        HTML, len(html.encode('utf-8')) / 1e6, len(needed), len(gallery), len(pool_keys)), flush=True)
    print('gallery:', [(g['metric'], g['tag'], g['key']) for g in gallery], flush=True)


if __name__ == '__main__':
    build()
