#!/usr/bin/env python3
"""一次性原型（issue 102）：从 1# 活动输入派生带回读页的工作目录。

每张图 = 基线输入 + 一处或几处显式注入的布局改动，然后走官方链
render → rasterize → validate → readback generate。运行产物只写被忽略的
`.artifacts/issue102/cases/<名字>/`，不随分支走；`build_prototype.py` 再把
产物打包进单文件原型页。

用法（仓库根目录）：python3 research/issue102/make_cases.py [名字 ...]

样本来源：对基线布局逐个元件做单点扰动（旋转 ±90/180、平移 ±60/±120、
母线 ±30/±60）共 231 次的扫描结果；其中 106 次被硬性走线门槛挡住、
125 次出图、3 次零失败。这里按“主要失败类别”分层取图，每层 4 张，
另有基线、遮挡样本和多因混合样本供自由浏览。
"""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / '.agents' / 'skills' / 'hydraulic-schematic' / 'scripts'
SRC = ROOT / '1#系统原理图'
OUT = ROOT / '.artifacts' / 'issue102' / 'cases'

# 名字 -> (注入改动, 分层, 一句话). 前五张沿用按失败项定向布局优化（#99）的
# 五图套件，便于和该票的 fail 计数对账。
CASES = {
    'base': ({}, '基线', '未改动；fail 0 / warn 6'),
    # ---- 试验池：每层 4 张 ----
    'label': (
        {('nodes', 'RF-001', 'y'): 612}, '标签重叠',
        'RF-001 上移 400：两个标签压在 RF-001 符号上，另有 1 处新增交叉'),
    'label-acv': ({('nodes', 'ACV-001', 'y'): 879}, '标签重叠', 'ACV-001 上移 60'),
    'label-qdr': ({('nodes', 'QDR-001', 'y'): 960}, '标签重叠', 'QDR-001 下移 60'),
    'label-pg': ({('nodes', 'PG-001', 'y'): 892}, '标签重叠', 'PG-001 下移 60'),
    'overlap': (
        {('nodes', 'FSOV-001', 'rot'): 90}, '连接语义',
        'FSOV-001 转 180°：两条线共线重叠 268 单位，一条走线折返 4 次'),
    'overlap-prv': (
        {('nodes', 'PRV-002', 'rot'): 90}, '连接语义',
        'PRV-002 转 270°：共线重叠 90 单位，新增交叉，绕行比 1.916'),
    'overlap-emp': ({('nodes', 'EMP-001', 'rot'): 90}, '连接语义', 'EMP-001 转 90°：共线重叠'),
    'overlap-acv': ({('nodes', 'ACV-001', 'rot'): 0}, '连接语义', 'ACV-001 转 180°：共线重叠、缺接点、新增交叉'),
    'topology': (
        {('nodes', 'TANK-001', 'rot'): 180}, '连接语义',
        'TANK-001 转 180°：多连 / 错连、桥断口、缺接点，新增交叉'),
    'topology-fsov': ({('nodes', 'FSOV-001', 'y'): 343.7}, '连接语义', 'FSOV-001 下移 60：连错管网、假接点，新增交叉'),
    'topology-acc': ({('nodes', 'ACC-001', 'rot'): 90}, '连接语义', 'ACC-001 转 90°：管网多出闭环，新增交叉'),
    'topology-pf': ({('nodes', 'PF-001', 'rot'): 180}, '连接语义', 'PF-001 转 180°：管网多出闭环，新增交叉'),
    'crossing': ({('nodes', 'RF-001', 'rot'): 0}, '版式与预算', 'RF-001 转 180°：新增 1 处交叉'),
    'crossing-pf': ({('nodes', 'PF-001', 'y'): 314}, '版式与预算', 'PF-001 下移 60：新增 1 处交叉'),
    'crossing-cdf': ({('nodes', 'CDF-001', 'y'): 370}, '版式与预算', 'CDF-001 上移 60：新增 1 处交叉'),
    'crossing-prv': ({('nodes', 'PRV-002', 'y'): 850}, '版式与预算', 'PRV-002 下移 120：新增 1 处交叉'),
    # ---- 只供自由浏览 ----
    'occlusion-user': ({('nodes', 'USER-001', 'x'): 1588}, '遮挡', 'USER-001 右移 60：符号出了可绘制范围'),
    'multi-bus': ({('buses', 'USR', 'x'): 1470}, '连接语义', 'USR 母线左移 30：25 条共线重叠、多出 4 个闭环'),
    'mix-3': (
        {('nodes', 'FSOV-001', 'rot'): 90, ('nodes', 'RF-001', 'y'): 612, ('buses', 'USR', 'x'): 1470}, '多因混合',
        '三处独立改动：FSOV-001 转 180°、RF-001 上移 400、USR 母线左移 30'),
    'mix-3b': (
        {('nodes', 'TANK-001', 'rot'): 180, ('nodes', 'ACV-001', 'y'): 879, ('nodes', 'PF-001', 'y'): 314}, '多因混合',
        '三处独立改动：TANK-001 转 180°、ACV-001 上移 60、PF-001 下移 60'),
}
TRIALS = ('label', 'label-acv', 'label-qdr', 'label-pg',
          'overlap', 'overlap-prv', 'overlap-emp', 'overlap-acv',
          'topology', 'topology-fsov', 'topology-acc', 'topology-pf',
          'crossing', 'crossing-pf', 'crossing-cdf', 'crossing-prv')
OLD_NAMES = {'b1-cross': 'crossing', 'v13-overlap': 'overlap', 'b3-v13-mixed': 'overlap-prv',
             'b7-text': 'label', 'severe-multi': 'multi-bus'}


def run(*args):
    done = subprocess.run([sys.executable, *map(str, args)], cwd='/tmp', capture_output=True, text=True)
    if done.returncode != 0:
        print(done.stdout[-2000:], done.stderr[-2000:])
        raise SystemExit('%s 退出码 %s' % (args[0], done.returncode))
    return done.stdout


def build(name, edits):
    work = OUT / name
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    for item in ('1#系统.intent.yaml', '1#系统组件.json', 'component-catalog.json'):
        shutil.copy2(SRC / item, work / item)
    shutil.copytree(SRC / 'symbols', work / 'symbols')
    layout = json.loads((SRC / '1#系统.layout.json').read_text(encoding='utf-8'))
    for path, value in edits.items():
        here = layout
        for key in path[:-1]:
            here = here[key]
        here[path[-1]] = value
    (work / '1#系统.layout.json').write_text(json.dumps(layout, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    run(SKILL / 'render_l0_sheet.py', work)
    run(SKILL / 'rasterize_sheet.py', work / '1#系统原理图.svg', '-o', work / 'sheet-readback.png')
    done = subprocess.run([sys.executable, str(SKILL / 'validate_sheet.py'), str(work)], cwd='/tmp', capture_output=True, text=True)
    if not (work / 'validation-report.json').exists():
        # 自动校核有 fail 时退出码为 1，是预期结果；没有产出报告才算异常。
        print(done.stdout[-2000:], done.stderr[-2000:])
        raise SystemExit('validate_sheet 异常退出 %s' % done.returncode)
    run(SKILL / 'readback_review.py', 'generate', work)
    report = json.loads((work / 'validation-report.json').read_text(encoding='utf-8'))
    manifest = json.loads((work / 'readback-manifest.json').read_text(encoding='utf-8'))
    fails = sorted({c['id'] for c in report['checks'] if c['result'] == 'fail'})
    print('%-15s fail=%-2d warn=%-2d 失败项=%-20s 对象=%d 局部图=%d' % (
        name, report['fail_count'], report['warn_count'], ','.join(fails), len(manifest['objects']), len(manifest['regions'])), flush=True)
    return {'fail': report['fail_count'], 'warn': report['warn_count']}


if __name__ == '__main__':
    wanted = [OLD_NAMES.get(w, w) for w in (sys.argv[1:] or list(CASES))]
    unknown = [w for w in wanted if w not in CASES]
    if unknown:
        raise SystemExit('未知图名：%s' % unknown)
    for name in wanted:
        build(name, CASES[name][0])
