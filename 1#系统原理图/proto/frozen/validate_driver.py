# -*- coding: utf-8 -*-
"""校核驱动器（#13）：render → validate → 按处方修 的有界自动收敛。

把「渲染→校核→按处方表修」的两轮收敛机制从 AI 手工驱动收编为脚本：
复用 preflight.py（L0 输入预检，findings 自带 remedy）+ layout_engine.py
（规则+守门+--optimize 第三阶段）+ proto_render.py（渲染+结构自检）+
validate_sheet.py（整图结构校核）。驱动器自己不新增校核口径，只做三件事：
解析 findings、按处方表试修、有界轮次内重跑，收敛失败带结构化报告退出。

处方表（finding → 机械修法；修不动的立即上报，不烧轮次）：
  R0  E-*   preflight ERROR。P1=纯传感链误入 paths 降级 taps——仅当 path
            恰两个 token、均为显式端口、medium 均非液压；等价 tap 已存在
            则只删误入 path。其余 E-*（端口写错/terminal 中串/类型未登记）
            语义不可机械推导，残差上报（fail-closed）。
  轮内 V2/V13/V19(B1)  几何硬缺陷。P3=引擎从 intent 重推布局并叠加
            --optimize 第三阶段（#19 已并入；V2/V13/B1 在其能量函数内）。
            已叠加仍不绿 → 残差上报。
  轮内 V16  回读 PNG 每轮渲染后强制重出（1:1 viewBox，#19 两次踩坑的
            教训固化为卫生不变量），故 V16 命中即真缺陷，残差上报。
  轮内 V1/V3/V4/V6/V7/V8/V11/V12/V14/V15/V17/V18
       渲染器/走线器/布局参数所有，无输入侧机械修法，残差上报。

卫生不变量：每轮渲染后必重出 sheet-readback.png（Inkscape -w 1680 =
viewBox 宽，像素 1:1，V16 像素探测以此为准）。种子布局仅在第一轮使用；
P3 生效后布局一律由引擎重推，种子即弃。

工作区：所有改动发生在 --workdir 沙箱副本（脚本/符号/catalog/intent
逐份复制），规范源文件一个不碰。注入演练 --inject a|b|c 只改沙箱副本。

用法:
    python validate_driver.py [--workdir DIR] [--rounds N]
                              [--intent SRC.yaml] [--layout-seed SEED.json]
                              [--inject a|b|c] [--keep]
退出码: 0 收敛(fail 0) / 1 轮次耗尽仍有 fail（残差上报）/
        2 preflight 残差（输入侧拦截，渲染未启动）/ 3 工具链故障。
"""
import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INTENT = os.path.join(HERE, '1#系统.intent.yaml')
DEFAULT_SEED = os.path.join(HERE, '1#系统丁.layout.json')
DEFAULT_REF = os.path.join(HERE, '1#系统.layout.json')
CATALOG = 'component-catalog.json'
INTENT_NAME = '1#系统.intent.yaml'
LAYOUT_NAME = '1#系统.layout.json'
SVG_NAME = '1#系统原理图.svg'
READBACK = 'sheet-readback.png'
READBACK_W = 1680                      # = viewBox 宽，导出即 1:1

SCRIPTS = ['preflight.py', 'proto_render.py', 'validate_sheet.py',
           'layout_engine.py', 'proto_optimize.py', 'topology_confirm.py']
TPL_NAME = '1#清单受控模板.yaml'     # 随沙箱复制，preflight 模板门禁按同目录解析
PY = sys.executable
INKSCAPE_CANDIDATES = [
    r'D:\Program Files\Inkscape\bin\inkscape.exe',
    r'C:\Program Files\Inkscape\bin\inkscape.exe',
]

# 轮内几何硬缺陷 → P3；其余 fail 全部残差。V19 仅 B1 交叉走 fail 通道。
P3_IDS = {'V2', 'V13', 'V19'}


def find_inkscape():
    p = shutil.which('inkscape')
    if p:
        return p
    for c in INKSCAPE_CANDIDATES:
        if os.path.isfile(c):
            return c
    return None


def run(cmd, cwd, timeout=600):
    """子进程统一出口：UTF-8 抓输出，非零不在这里抛，由调用方裁决。"""
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    try:
        p = subprocess.run([str(c) for c in cmd], cwd=cwd, env=env,
                           capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, '', '超时(%ds): %s' % (timeout, ' '.join(map(str, cmd)))
    out = p.stdout.decode('utf-8', 'replace')
    err = p.stderr.decode('utf-8', 'replace')
    return p.returncode, out, err


# ---------- 注入演练（只改沙箱副本）----------

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

def setup_workdir(wd):
    if os.path.isdir(wd):
        shutil.rmtree(wd)
    os.makedirs(wd)
    for s in SCRIPTS:
        shutil.copy2(os.path.join(HERE, s), os.path.join(wd, s))
    shutil.copytree(os.path.join(HERE, 'symbols'), os.path.join(wd, 'symbols'))
    shutil.copy2(os.path.join(HERE, CATALOG), os.path.join(wd, CATALOG))
    # preflight 的 schema 候选路径之一是 ../assets/contracts/
    pf_schema = os.path.join(wd, '..', 'assets', 'contracts')
    if not os.path.isdir(pf_schema) and \
            os.path.isfile(os.path.join(HERE, 'assets', 'contracts',
                                        'l0-input-contract.schema.json')):
        os.makedirs(pf_schema)
        shutil.copy2(os.path.join(HERE, 'assets', 'contracts',
                                  'l0-input-contract.schema.json'), pf_schema)


def preflight_run(wd):
    rc, out, err = run([PY, 'preflight.py', INTENT_NAME,
                        '--catalog', CATALOG, '--json'], wd)
    if rc not in (0, 1) or not out.strip():
        raise RuntimeError('preflight 运行失败 rc=%s\n%s' % (rc, err))
    return json.loads(out)


def render_round(wd, inkscape, use_seed, p3_armed, ref_path):
    """一轮 = 布局（种子或引擎）→ 渲染 → 回读重出。返回阶段台账。
    ref 只承载呈现文案（labels 等，引擎注释明示文案不是坐标决策）。"""
    step = {}
    if use_seed:
        step['layout_source'] = 'seed'
    else:
        cmd = [PY, 'layout_engine.py', INTENT_NAME, CATALOG, ref_path,
               '-o', LAYOUT_NAME]
        if p3_armed:
            cmd.append('--optimize')
        # P3 是全邻域最陡下降（#19），分钟级是常态，给足上限。
        rc, out, err = run(cmd, wd, timeout=2400)
        if rc != 0:
            raise RuntimeError('layout_engine 失败 rc=%s\n%s\n%s'
                               % (rc, out, err))
        step['layout_source'] = 'engine' + ('+optimize' if p3_armed else '')
    rc, out, err = run([PY, 'proto_render.py', INTENT_NAME, LAYOUT_NAME,
                        SVG_NAME], wd)
    if rc != 0:
        raise RuntimeError('proto_render 失败 rc=%s\n%s\n%s' % (rc, out, err))
    step['rendered'] = SVG_NAME
    # 卫生不变量：回读图必随本轮 SVG 重出（V16 像素探测 1:1 依赖）。
    if inkscape:
        rc, out, err = run([inkscape, SVG_NAME, '-o', READBACK,
                            '-w', str(READBACK_W)], wd, timeout=300)
        if rc != 0:
            raise RuntimeError('readback 导出失败 rc=%s\n%s' % (rc, err))
        step['readback'] = 'regenerated@%dw' % READBACK_W
    else:
        step['readback'] = 'MISSING(inkscape 不可用，V16 像素探测降级)'
    return step


def validate_run(wd):
    rc, out, err = run([PY, 'validate_sheet.py'], wd)
    rep_path = os.path.join(wd, 'validation-report.json')
    if not os.path.isfile(rep_path):
        raise RuntimeError('validate 未产出报告 rc=%s\n%s\n%s' % (rc, out, err))
    with io.open(rep_path, encoding='utf-8') as f:
        return rc, json.load(f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--workdir', default=os.path.join(HERE, 'driver-run'))
    ap.add_argument('--rounds', type=int, default=2)
    ap.add_argument('--intent', default=DEFAULT_INTENT)
    ap.add_argument('--layout-seed', default=None)
    ap.add_argument('--ref', default=DEFAULT_REF,
                    help='引擎参照布局：仅承载 labels 等呈现文案，'
                         '坐标一律重推；传 none 则无参照')
    ap.add_argument('--inject', choices=['a', 'b', 'c', 'd'], default=None)
    ap.add_argument('--optimize', action='store_true',
                    help='首轮即叠加引擎阶段 3 寻优（#14 定案的到站标准链'
                         '：规则+守门+寻优）；不加则首轮为规则+守门')
    ap.add_argument('--keep', action='store_true',
                    help='保留上轮工作区不清理（默认每次重建）')
    args = ap.parse_args()

    t0 = time.time()
    report = {'driver': 'validate-driver-1.0', 'converged': False,
              'rounds': [], 'prescriptions': [], 'residuals': [],
              'inject': None, 'exit_code': None}
    wd = args.workdir

    # ---- 沙箱工作区 ----
    setup_workdir(wd)
    shutil.copy2(args.intent, os.path.join(wd, INTENT_NAME))
    shutil.copy2(os.path.join(HERE, TPL_NAME), os.path.join(wd, TPL_NAME))
    seed = None
    if args.inject == 'b':
        seed = load_yaml(args.layout_seed or DEFAULT_SEED)
        report['inject'] = inject_b(seed)
        with io.open(os.path.join(wd, LAYOUT_NAME), 'w', encoding='utf-8') as f:
            json.dump(seed, f, ensure_ascii=False, indent=2)
    else:
        if args.layout_seed:
            shutil.copy2(args.layout_seed, os.path.join(wd, LAYOUT_NAME))
    intent = load_yaml(os.path.join(wd, INTENT_NAME))
    if args.inject in ('a', 'c'):
        report['inject'] = (inject_a(intent) if args.inject == 'a'
                            else inject_c(intent))
        dump_intent(intent, os.path.join(wd, INTENT_NAME))
    elif args.inject == 'd':
        tpl = load_yaml(os.path.join(wd, TPL_NAME))
        report['inject'] = inject_d(tpl)
        dump_intent(tpl, os.path.join(wd, TPL_NAME))
    with io.open(os.path.join(wd, CATALOG), encoding='utf-8') as f:
        catalog = json.load(f)
    inkscape = find_inkscape()

    # ---- R0 preflight（输入侧门禁 + P1 处方）----
    p1_used = 0
    while True:
        rep = preflight_run(wd)
        errs = [f for f in rep['findings'] if f['level'] == 'ERROR']
        if not errs:
            report['preflight'] = {'status': rep['status'],
                                   'findings': len(rep['findings'])}
            break
        fixed = p1_taps_demotion(intent, catalog)
        if fixed and p1_used < 3:
            p1_used += 1
            dump_intent(intent, os.path.join(wd, INTENT_NAME))
            report['prescriptions'].append(
                {'stage': 'R0', 'id': 'P1', 'round': 0,
                 'applied': fixed,
                 'triggered_by': ['%s %s' % (f['id'], f['message'])
                                  for f in errs]})
            continue
        # 处方修不动的输入缺陷：结构化残差，渲染一行不启动。
        report['preflight'] = {'status': rep['status'],
                               'findings': len(rep['findings'])}
        report['residuals'] = [
            {'stage': 'R0', 'id': f['id'], 'level': f['level'],
             'object': f['object'], 'message': f['message'],
             'remedy': f['remedy'],
             'hint': '处方表无此类的机械修法（语义不可推导），'
                     '需人工改 intent 后重跑驱动器'}
            for f in errs]
        report['exit_code'] = 2
        report['elapsed_s'] = round(time.time() - t0, 1)
        finish(report, wd)
        return 2

    # ---- 有界轮次 ----
    seed_pending = seed is not None or args.layout_seed
    p3_armed = bool(args.optimize)
    if args.ref and args.ref.lower() != 'none' and os.path.isfile(args.ref):
        shutil.copy2(args.ref, os.path.join(wd, 'ref.layout.json'))
        ref_path = 'ref.layout.json'
    else:
        ref_path = '-'
    for r in range(1, max(1, args.rounds) + 1):
        rnd = {'round': r}
        try:
            rnd.update(render_round(wd, inkscape,
                                    use_seed=seed_pending and not p3_armed,
                                    p3_armed=p3_armed, ref_path=ref_path))
        except RuntimeError as e:
            report['tool_failure'] = str(e)
            report['exit_code'] = 3
            report['elapsed_s'] = round(time.time() - t0, 1)
            finish(report, wd)
            return 3
        seed_pending = False
        vrc, vrep = validate_run(wd)
        fails = [c for c in vrep['checks'] if c['result'] == 'fail']
        warns = [c for c in vrep['checks'] if c['result'] == 'warn']
        rnd['fail_count'] = len(fails)
        rnd['warn_count'] = len(warns)
        rnd['fails'] = [{'id': c['id'], 'detail': c['detail']} for c in fails]
        rnd['budget'] = {it['id']: it['status']
                         for it in vrep.get('composition_budget', {}).get('items', [])}
        report['rounds'].append(rnd)
        if not fails:
            report['converged'] = True
            break

        # ---- 处方表裁决：有修不动的同时在场，立即上报不烧轮次 ----
        residual = [c for c in fails if c['id'] not in P3_IDS]
        if residual or p3_armed:
            report['residuals'] = [
                {'stage': 'round%d' % r, 'id': c['id'], 'detail': c['detail'],
                 'hint': (P3_HINT if c['id'] in P3_IDS else
                          '渲染器/走线器/布局参数所有，无输入侧机械修法，需 AI 介入')}
                for c in (residual or fails)]
            break
        report['prescriptions'].append(
            {'stage': 'round', 'id': 'P3', 'round': r,
             'applied': ['引擎重推布局 + --optimize 第三阶段',
                         '触发: ' + '; '.join('%s %s' % (c['id'], c['detail'][:60])
                                              for c in fails)]})
        p3_armed = True

    report['exit_code'] = (0 if report['converged']
                           else (1 if not report['residuals'] else 1))
    report['elapsed_s'] = round(time.time() - t0, 1)
    finish(report, wd)
    return report['exit_code']


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
                 rnd.get('readback', ''), rnd['fail_count'], rnd['warn_count']))
        for fl in rnd['fails']:
            print('       FAIL %s %s' % (fl['id'], fl['detail'][:80]))
    for p in report['prescriptions']:
        txt = '; '.join(
            x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
            for x in p['applied'])
        print('处方 %s @R%d: %s' % (p['id'], p['round'], txt[:100]))
    for r in report['residuals']:
        print('残差 %s [%s]: %s' % (r['id'], r['stage'],
                                    r.get('detail') or r.get('message', '')[:80]))
    print('结论: %s  (%.1fs, 报告 -> %s)'
          % ('收敛 fail 0' if report['converged'] else
             ('残差上报，需人工/AI 介入' if report['residuals'] else
              ('轮次耗尽仍有 fail' if report['exit_code'] == 1 else '工具链故障')),
             report['elapsed_s'], path))


if __name__ == '__main__':
    sys.exit(main())
