# -*- coding: utf-8 -*-
"""selftest.py —— hydraulic-schematic skill 金样回归自测试 v1。

一句话：改动符号 / catalog / 模板脚本后，一条命令知道出图能力是否被打破。

    python .agents/skills/hydraulic-schematic/scripts/selftest.py
    python .agents/skills/hydraulic-schematic/scripts/selftest.py --update-golden   # 重录金样

覆盖面（含真实浏览器显示与局部回读证据）：

  A. SysML 链路端到端：按 SKILL.md 运行纪律复刻真实用法——把 skill 快照的
     render_aircraft_schematic.py 与范例 .sysml 复制进临时工作目录再运行；
     要求退出码 0、结构自检通过，产出 SVG 与追溯清单经换行归一化(CRLF/CR→LF)
     后与 assets/fixtures/sysml-render/ 下金样逐字节一致。
  B. check_library 结构闸门（#20 单源化承接口）：自带库必须默认过闸（含
     L3 硬档 catalog 交叉校验）；沙箱中剥掉任一符号的 connection-points
     → 必须被 L2 拦截（exit 1）。
  C. L0 预检器（#8）：负例 negative-mixed-violations（七类违规混样）必须被拦截
     （exit 1，且报出端口存在性 E-PORT / role 兼容 E-SENS / 结构契约 E-SHAPE-* 等
     具体 finding id、一次报齐）；正例 positive-preflight-cleared 必须放行（exit 0）。
     与渲染器、CLI 同源调用 scripts/preflight.py。
  D. 布局引擎烟测：随 skill 打包的当前 23 部件输入上规则+守门出全量布局（exit 0，
     nodes/buses 非空、guard 带裁决字段）；未覆盖形态（范例系统的收集链
     普通滤型）必须 fail-closed——exit 1 且报「未布元件」，绝不静默出图。
  E. preflight 模板门禁（#22 沉淀批）：intent 同目录空背书受控模板 →
     对账 E-RECON 必须拦截（exit 1）且 concept 未签认 W-SIGN-UNSIGNED 披露。
  F. L0 入口、有界寻优、驱动器、路线剪枝、光栅化适配器的专项 unittest。
     入口测试含小型 seed 的预检→渲染→几何全链回归；当前 23 部件 seed 的
     已知几何缺陷仍须被拦截。主自检包含真实 Chrome 栅格化/显示测量，
     并用 Pillow 验证 PNG、局部裁图和图像版本绑定的正反例；适配器异常路径另有桩测试。

全部输入来自 skill 随附资产，不依赖仓库外层的历史 frozen 目录。
自动测试验证出图、显示及证据协议，不等于已完成实际图纸的感知回读签认；
整图与逐项回读仍须明确记录，不能把测试通过宣称为图纸已获确认。

失败出口：与渲染器同一退出码约定 0 过 / 1 断，供 CI 或钩子直接调用。
守门基础设施，在仓库根原位运行，不复制到工作目录。
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
RENDERER = os.path.join(HERE, 'render_aircraft_schematic.py')
SYMSOURCE = os.path.join(SKILL, 'assets', 'examples', 'aircraft_hydraulic_system.sysml')
FIXTURES = os.path.join(SKILL, 'assets', 'fixtures', 'sysml-render')

GOLDEN_SVG = os.path.join(FIXTURES, 'aircraft_hydraulic_system_schematic.golden.svg')
GOLDEN_MD = os.path.join(FIXTURES, 'aircraft_hydraulic_system_topology.golden.md')
FIXTURE_NAMES = [('SVG', GOLDEN_SVG), ('追溯清单', GOLDEN_MD)]

# 渲染器固定输出文件名（以自身位置为根）
PROD_SVG_NAME = 'aircraft_hydraulic_system_schematic.svg'
PROD_MD_NAME = 'aircraft_hydraulic_system_topology.md'

# 子进程统一 UTF-8 输出，避免 Windows 控制台代码页干扰解码
CHILD_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1',
                 PYTHONDONTWRITEBYTECODE='1')


class Fail(Exception):
    pass


def norm(b):
    return b.replace(b'\r\n', b'\n').replace(b'\r', b'\n')


def readb(path):
    with open(path, 'rb') as f:
        return f.read()


def writeb(path, b):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(b)


def run_py(args, expect_zero=True):
    r = subprocess.run([sys.executable] + args, capture_output=True,
                       env=CHILD_ENV, cwd=os.path.dirname(os.path.abspath(args[0])))
    out = (r.stdout or b'').decode('utf-8', 'replace') + (r.stderr or b'').decode('utf-8', 'replace')
    if expect_zero and r.returncode != 0:
        raise Fail('命令 %s 退出码 %d（期望 0）。输出尾部：\n%s' % (' '.join(args), r.returncode, out[-1200:]))
    return r.returncode, out


# ---------- A. SysML 链路 ----------

def render_in_tmp():
    """复刻运行纪律：复制渲染模板+输入到临时目录，原样跑一遍。返回 (工作目录, 产物路径表)。"""
    ws = tempfile.mkdtemp(prefix='selftest-sysml-')
    script = os.path.join(ws, os.path.basename(RENDERER))
    shutil.copy2(RENDERER, script)
    shutil.copy2(SYMSOURCE, os.path.join(ws, os.path.basename(SYMSOURCE)))
    _, out = run_py([script])
    if not out.lstrip().startswith('OK'):
        raise Fail('渲染器退出码 0 但结构自检未报 OK。输出尾部：\n%s' % out[-800:])
    return ws, {n: os.path.join(ws, n) for n in (PROD_SVG_NAME, PROD_MD_NAME)}


def check_sysml_golden():
    for label, golden in FIXTURE_NAMES:
        if not os.path.isfile(golden):
            raise Fail('金样缺失：%s（先跑 --update-golden 建立基线）' % golden)
    ws, prod = render_in_tmp()
    try:
        for label, golden in FIXTURE_NAMES:
            name = os.path.basename(golden).replace('.golden.', '.')
            want = norm(readb(golden))
            got = norm(readb(prod[name]))
            if want != got:
                i = next((k for k in range(min(len(want), len(got))) if want[k] != got[k]),
                         min(len(want), len(got)))
                raise Fail('%s 与金样不一致：首个差异在第 %d 字节'
                           '（金样 %d 字节 / 本次 %d 字节）。若为本意改动，跑 --update-golden 重录。'
                           % (label, i, len(want), len(got)))
    finally:
        shutil.rmtree(ws, ignore_errors=True)


def update_golden():
    ws, prod = render_in_tmp()
    payloads = [(golden, norm(readb(prod[os.path.basename(golden).replace('.golden.', '.')])))
                for _, golden in FIXTURE_NAMES]
    shutil.rmtree(ws, ignore_errors=True)
    for golden, data in payloads:
        writeb(golden, data)
        print('  金样已更新 <- %s' % golden)


# ---------- B. check_library 结构闸门（#20/#21 单源化承接口） ----------

CHECKER = os.path.join(HERE, 'check_library.py')
WHITELISTED = ('quick-disconnect-coupling.svg', '_template.svg')


def strip_connection_points(svg_bytes):
    root = ET.fromstring(svg_bytes)
    parents = {c: p for p in root.iter() for c in list(p)}
    n = 0
    for el, par in list(parents.items()):
        if el.get('id') == 'connection-points':
            par.remove(el)
            n += 1
    return ET.tostring(root, encoding='utf-8'), n


def check_library_gate():
    # 自带库默认过闸（L1/L2/L3 硬档一起）
    rc, out = run_py([CHECKER], expect_zero=False)
    if rc != 0:
        raise Fail('自带库未过结构闸门（退出码 %d）。输出：\n%s' % (rc, out[-800:]))
    if '结论: 通过' not in out:
        raise Fail('退出码 0 但缺「结论: 通过」标记。输出：\n%s' % out[-400:])
    # 沙箱里剥掉一只白名单外符号的端口组 → L2 必须拦截
    lib = tempfile.mkdtemp(prefix='selftest-lib-')
    try:
        src = os.path.join(SKILL, 'assets', 'component-library')
        for f in os.listdir(src):
            if f.endswith(('.svg', '.json')):
                shutil.copy2(os.path.join(src, f), os.path.join(lib, f))
        target = None
        for f in sorted(os.listdir(lib)):
            if f.endswith('.svg') and f not in WHITELISTED:
                root = ET.parse(os.path.join(lib, f)).getroot()
                if any(g.get('id') == 'connection-points' for g in root.iter()):
                    target = f
                    break
        if not target:
            raise Fail('沙箱中找不到带端口组的白名单外符号')
        p = os.path.join(lib, target)
        stripped, n = strip_connection_points(readb(p))
        if not n:
            raise Fail('剥离 connection-points 失败: %s' % target)
        writeb(p, stripped)
        rc, out = run_py([CHECKER, '--lib', lib,
                          '--catalog', os.path.join(lib, 'component-catalog.json')],
                         expect_zero=False)
        if rc != 1:
            raise Fail('白名单外缺端口组未被拦截（退出码 %d，期望 1）。输出：\n%s'
                       % (rc, out[-600:]))
        if '无 connection-points 端口组' not in out:
            raise Fail('退出码 1 但缺 L2 缺端口组报文。输出：\n%s' % out[-600:])
    finally:
        shutil.rmtree(lib, ignore_errors=True)


# ---------- C. L0 输入预检器 ----------

PREFLIGHT = os.path.join(HERE, 'preflight.py')
EX_NEG = os.path.join(SKILL, 'assets', 'examples', 'negative-mixed-violations.intent.yaml')
EX_POS = os.path.join(SKILL, 'assets', 'examples', 'positive-preflight-cleared.intent.yaml')


def check_preflight():
    rc, out = run_py([PREFLIGHT, EX_NEG], expect_zero=False)
    if rc != 1:
        raise Fail('负例七类违规混样未被拦截（退出码 %d，期望 1）。输出：\n%s' % (rc, out[-800:]))
    for fid in ('E-PORT', 'E-SENS', 'E-BARE', 'E-UND', 'E-MED', 'E-CAT-XPU-001', 'E-SHAPE-'):
        if fid not in out:
            raise Fail('负例报告缺 finding id %s（首错不停一次报齐被破坏）。输出：\n%s' % (fid, out[-800:]))
    if 'blocked_pre_layout' not in out:
        raise Fail('负例报告缺 blocked_pre_layout 状态标记。输出：\n%s' % out[-400:])
    rc, out = run_py([PREFLIGHT, EX_POS], expect_zero=False)
    if rc != 0:
        raise Fail('正例被误杀（退出码 %d，期望 0 放行）。输出：\n%s' % (rc, out[-800:]))
    if 'cleared_for_layout' not in out:
        raise Fail('正例输出缺 cleared_for_layout 状态标记。输出：\n%s' % out[-400:])


# ---------- D. 布局引擎烟测（#22 沉淀批） ----------

ENGINE = os.path.join(HERE, 'layout_engine.py')
EX_INTENT = os.path.join(SKILL, 'assets', 'examples', 'system-1.intent.yaml')
EX_LAYOUT = os.path.join(SKILL, 'assets', 'examples', '1#系统.layout.json')
SKILL_CATALOG = os.path.join(SKILL, 'assets', 'component-library',
                             'component-catalog.json')
CURRENT_FIXTURE = os.path.join(SKILL, 'assets', 'fixtures', 'l0-current')
CURRENT_INTENT = os.path.join(CURRENT_FIXTURE, '1#系统.intent.yaml')
CURRENT_LAYOUT = os.path.join(CURRENT_FIXTURE, '1#系统.layout.json')


def check_layout_engine():
    """正例：自包含当前输入上规则+守门出全量布局（exit 0、nodes/buses 非空、
    guard 带 zero_drift/drifted 裁决）。负例：未覆盖形态（收集链普通滤型）
    必须 fail-closed——exit 1 且报「未布元件」清单，绝不静默出图。"""
    ws = tempfile.mkdtemp(prefix='selftest-engine-')
    try:
        out_layout = os.path.join(ws, 'engine.layout.json')
        guard = os.path.join(ws, 'guard.json')
        rc, out = run_py([ENGINE, CURRENT_INTENT, SKILL_CATALOG,
                          CURRENT_LAYOUT, '-o', out_layout,
                          '--guard-report', guard], expect_zero=False)
        if rc != 0:
            raise Fail('布局引擎退出码 %d（期望 0）。输出尾部：\n%s'
                       % (rc, out[-800:]))
        with open(out_layout, encoding='utf-8') as f:
            layout = json.load(f)
        if not layout.get('nodes') or not layout.get('buses'):
            raise Fail('引擎布局缺 nodes/buses')
        with open(guard, encoding='utf-8') as f:
            g = json.load(f)
        if 'zero_drift' not in g or 'drifted' not in g:
            raise Fail('guard 报告缺 zero_drift/drifted 裁决字段')
        rc, out = run_py([ENGINE, EX_INTENT, SKILL_CATALOG, EX_LAYOUT,
                          '-o', os.path.join(ws, 'neg.layout.json')],
                         expect_zero=False)
        if rc != 1 or '未布元件' not in out:
            raise Fail('未覆盖形态未 fail-closed（rc=%d，期望 1 + 未布元件'
                       '报告）。输出：\n%s' % (rc, out[-600:]))
    finally:
        shutil.rmtree(ws, ignore_errors=True)


# ---------- E. preflight 模板门禁（#22 沉淀批：三向对账+签认分级） ----------

def check_template_gate():
    """intent 同目录放一份空背书受控模板 → 对账 E-RECON 必须拦截（exit 1），
    concept 未签认 → W-SIGN-UNSIGNED 披露。干净模板的放行侧由 C 项正例
    （无模板不启用门禁）与驱动器到站演练覆盖。"""
    ws = tempfile.mkdtemp(prefix='selftest-tpl-')
    try:
        intent_copy = os.path.join(ws, '1#系统.intent.yaml')
        shutil.copy2(EX_POS, intent_copy)
        writeb(os.path.join(ws, '1#清单受控模板.yaml'), '行: []\n'.encode('utf-8'))
        rc, out = run_py([PREFLIGHT, intent_copy], expect_zero=False)
        if rc != 1:
            raise Fail('空背书模板未被对账拦截（退出码 %d，期望 1）。输出：\n%s'
                       % (rc, out[-800:]))
        for fid in ('E-RECON', 'W-SIGN-UNSIGNED'):
            if fid not in out:
                raise Fail('模板门禁输出缺 %s（对账/签认分级被破坏）。输出：\n%s'
                           % (fid, out[-800:]))
    finally:
        shutil.rmtree(ws, ignore_errors=True)


# ---------- F. 性能、入口与证据专项回归（证据用例启动本机 Chrome） ----------

def check_l0_regressions():
    # End-to-end browser suites share this aggregate hang guard; it is not a performance assertion.
    suites = ('test_assemblies', 'test_entrypoints', 'test_optimizer_budget', 'test_driver', 'test_proofreading_evidence',
              'test_route_pruning', 'test_rasterize_sheet', 'test_priority_valve_leads', 'test_display_widths', 'test_paint_evidence',
              'test_route_terminals', 'test_dangling_ports', 'test_port_geometry', 'test_topology_reconciliation', 'test_text_display', 'test_layout_clearance', 'test_junction_semantics', 'test_sheet_diff', 'test_readback_review')
    try:
        result = subprocess.run([sys.executable, '-m', 'unittest', *suites],
                                cwd=HERE, env=CHILD_ENV, capture_output=True,
                                timeout=900)
    except subprocess.TimeoutExpired as exc:
        raise Fail('L0 专项测试超过 900 秒进程保护上限，未通过') from exc
    output = ((result.stdout or b'') + (result.stderr or b'')).decode('utf-8', 'replace')
    if result.returncode:
        raise Fail('L0 专项测试退出码 %d。输出尾部：\n%s'
                   % (result.returncode, output[-5000:]))
    lines = output.strip().splitlines()
    summary = next((i for i, line in enumerate(lines) if line.startswith('Ran ')), None)
    if summary is not None:
        print('\n'.join(lines[summary:]))


CHECKS = [
    ('A. SysML 链路金样比对（渲染退出码/结构自检/SVG+清单逐字节）', check_sysml_golden),
    ('B. check_library 结构闸门（自带库默认过闸 / 沙箱缺端口组拦截）', check_library_gate),
    ('C. L0 预检器：负例七类违规拦截报齐 / 正例放行', check_preflight),
    ('D. 布局引擎烟测（自包含当前输入出全量布局 / 未覆盖形态拦截）', check_layout_engine),
    ('E. preflight 模板门禁（空背书对账拦截 / concept 未签认披露，#22）', check_template_gate),
    ('F. L0 入口 / 寻优预算 / 驱动器 / 路由剪枝 / PNG 适配器专项测试', check_l0_regressions),
]


def main():
    sys.dont_write_bytecode = True
    sys.path.insert(0, HERE)

    update = '--update-golden' in sys.argv[1:]
    if update:
        print('== 重录金样（从当前快照渲染器重新生成） ==')
        update_golden()
        print('selftest: 金样重录完成，随后再跑一次确认 0 过。')
        return 0

    failed = []
    for name, fn in CHECKS:
        try:
            fn()
            print('[PASS] %s' % name)
        except Fail as e:
            failed.append(name)
            print('[FAIL] %s\n       %s' % (name, e))

    print('\n---- selftest 小结 ----')
    if failed:
        print('FAIL %d/%d：\n  - %s' % (len(failed), len(CHECKS), '\n  - '.join(failed)))
        return 1
    print('PASS %d/%d 出图能力完好。' % (len(CHECKS), len(CHECKS)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
