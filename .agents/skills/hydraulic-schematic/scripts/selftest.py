# -*- coding: utf-8 -*-
"""selftest.py —— hydraulic-schematic skill 金样回归自测试 v1。

一句话：改动符号 / catalog / 模板脚本后，一条命令知道出图能力是否被打破。

    python .agents/skills/hydraulic-schematic/scripts/selftest.py
    python .agents/skills/hydraulic-schematic/scripts/selftest.py --update-golden   # 重录金样

覆盖面（v1 裁剪见 GitHub Issues「金样回归 selftest v1」Resolution）：

  A. SysML 链路端到端：按 SKILL.md 运行纪律复刻真实用法——把 skill 快照的
     render_aircraft_schematic.py 与范例 .sysml 复制进临时工作目录再运行；
     要求退出码 0、结构自检通过，产出 SVG 与追溯清单经换行归一化(CRLF/CR→LF)
     后与 assets/fixtures/sysml-render/ 下金样逐字节一致。
  B. 快照审计一致：sync_snapshot 默认 dry-run 退出码 0（规范源与快照无差异，
     即 pre-push 闸门的放行前提）。
  C. 端口回退闸门：沙箱中快照现版符号带 connection-points、源头版本被剥掉
     → 同步工具必须拦截（exit 1 + [已拦截]），且 dry-run 不落盘。
  D. --force 旁路：同一场景加 --force --apply → 文件确实被强制拷入（exit 0）。
  E. prune 计数：沙箱快照放置命中排除规则的文件 → dry-run 只报 PRUNE 不删，
     加 --prune 才删除且计数=1。
  F. L0 预检器（#8）：负例 negative-mixed-violations（七类违规混样）必须被拦截
     （exit 1，且报出端口存在性 E-PORT / role 兼容 E-SENS / 结构契约 E-SHAPE-* 等
     具体 finding id、一次报齐）；正例 positive-preflight-cleared 必须放行（exit 0）。
     与渲染器、CLI 同源调用 scripts/preflight.py。

明确不在 v1 覆盖内：L0 链路金样（L0 规范源断裂，见地图 Out of scope）、
构图度量回归（等「构图预算定档」阈值冻结）、PNG 光栅化比对（属感知层人工回读）。

失败出口：与渲染器同一退出码约定 0 过 / 1 断，供 CI 或钩子直接调用。
守门基础设施，在仓库根原位运行，不复制到工作目录。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
SYNC = os.path.join(HERE, 'sync_snapshot.py')
RENDERER = os.path.join(HERE, 'render_aircraft_schematic.py')
SYMSOURCE = os.path.join(SKILL, 'assets', 'examples', 'aircraft_hydraulic_system.sysml')
FIXTURES = os.path.join(SKILL, 'assets', 'fixtures', 'sysml-render')

GOLDEN_SVG = os.path.join(FIXTURES, 'aircraft_hydraulic_system_schematic.golden.svg')
GOLDEN_MD = os.path.join(FIXTURES, 'aircraft_hydraulic_system_topology.golden.md')
FIXTURE_NAMES = [('SVG', GOLDEN_SVG), ('追溯清单', GOLDEN_MD)]

# 渲染器固定输出文件名（以自身位置为根）
PROD_SVG_NAME = 'aircraft_hydraulic_system_schematic.svg'
PROD_MD_NAME = 'aircraft_hydraulic_system_topology.md'

# 回退闸门测试用的符号候选：必须依次试到第一个真带端口组的
CANDIDATES = ['check-valve-stroke.svg', 'Filter.svg', 'edp-provisional-stroke.svg',
              'accumulator-stroke.svg']
# prune 测试用：必须命中 sync_snapshot 的排除规则（stroke-symbol-preview*）
JUNK = 'stroke-symbol-preview-selftest-junk.svg'

# 子进程统一 UTF-8 输出，避免 Windows 控制台代码页干扰解码
CHILD_ENV = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')


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


# ---------- B/C/D/E. sync_snapshot 审计与闸门 ----------

def snapshot_lib_path(name):
    return os.path.join(SKILL, 'assets', 'component-library', name)


def pick_target():
    """选一个快照现版真带 connection-groups 的符号做闸门测试载体。"""
    for name in CANDIDATES:
        p = snapshot_lib_path(name)
        if os.path.isfile(p):
            ports = ss.read_ports(p)
            if ports:  # 非 None 且非空
                return name, readb(p), p
    raise Fail('候补符号无一含 <g id="connection-points">，请检查 CANDIDATES 列表')


def strip_connection_points(svg_bytes):
    root = ET.fromstring(svg_bytes)
    parents = {c: p for p in root.iter() for c in list(p)}
    n = 0
    for el, par in list(parents.items()):
        if el.get('id') == 'connection-points':
            par.remove(el)
            n += 1
    return ET.tostring(root, encoding='utf-8'), n


def make_gate_env():
    """搭沙箱：base 作为 sync 的 --sandbox 目标区，预置现版快照；source 根提供同名"新源头"。
    返回 (base, source_root, dst_target, src_target)。"""
    name, original, _ = pick_target()
    base = tempfile.mkdtemp(prefix='selftest-gate-')
    src_root = tempfile.mkdtemp(prefix='selftest-src-')
    dst_lib = os.path.join(base, 'assets', 'component-library')   # 与真实快照相对路径一致
    src_lib = os.path.join(src_root, '已标注')
    os.makedirs(dst_lib)
    os.makedirs(src_lib)
    dst_target = os.path.join(dst_lib, name)
    src_target = os.path.join(src_lib, name)
    shutil.copy2(snapshot_lib_path(name), dst_target)
    return base, src_root, dst_target, src_target, name, original


def sync_args(base=None, src_root=None, extra=()):
    a = [SYNC, '--group', 'library']
    if base:
        a += ['--sandbox', base]
    if src_root:
        a += ['--src-root', src_root]
    return a + list(extra)


def check_sync_audit_clean():
    rc, _ = run_py([SYNC])
    if rc != 0:
        raise Fail('当前规范源与 skill 快照存在差异或被闸门拦截（dry-run 退出码 %d）。'
                   '先跑 sync_snapshot.py 看完整报告；待同步则 --apply 后重测。' % rc)


def check_gate_blocks_regression():
    base, src_root, dst_target, src_target, name, original = make_gate_env()
    try:
        stripped, n_removed = strip_connection_points(original)
        if not n_removed:
            raise Fail('剥离 connection-points 失败：%s 结构异常' % name)
        writeb(src_target, stripped)
        rc, out = run_py(sync_args(base, src_root), expect_zero=False)
        if rc != 1:
            raise Fail('端口回退未被拦截（退出码 %d，期望 1）。输出：\n%s' % (rc, out[-600:]))
        if '[已拦截]' not in out:
            raise Fail('退出码 1 但输出缺「[已拦截]」标记，输出：\n%s' % out[-600:])
        if readb(dst_target) != original:
            raise Fail('dry-run 拦截却改写了快照目标文件——闸门不许落盘')
    finally:
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(src_root, ignore_errors=True)


def check_gate_force_bypass():
    base, src_root, dst_target, src_target, name, original = make_gate_env()
    try:
        stripped, _ = strip_connection_points(original)
        writeb(src_target, stripped)
        rc, out = run_py(sync_args(base, src_root, ['--force', '--apply']), expect_zero=False)
        if rc != 0:
            raise Fail('--force --apply 未成功旁路（退出码 %d）。输出：\n%s' % (rc, out[-600:]))
        if readb(dst_target) != stripped:
            raise Fail('--force 后沙箱目标文件内容 ≠ 剥离版源头，强制拷入未生效')
    finally:
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(src_root, ignore_errors=True)


def check_prune_counts():
    base, src_root, dst_target, src_target, name, original = make_gate_env()
    try:
        # 无差异场景：源头与快照同字节，只有垃圾文件命中排除规则
        writeb(src_target, original)
        junk_dst = os.path.join(os.path.dirname(dst_target), JUNK)
        writeb(junk_dst, b'<svg xmlns="http://www.w3.org/2000/svg"/>')
        rc, out = run_py(sync_args(base, src_root))
        if 'PRUNE' not in out:
            raise Fail('排除规则未识别测试垃圾文件 %s（PRUNE 行缺失）' % JUNK)
        if not os.path.isfile(junk_dst):
            raise Fail('dry-run 阶段就删了文件——清理动作只应响应 --prune')
        rc, out = run_py(sync_args(base, src_root, ['--prune']))
        if os.path.isfile(junk_dst):
            raise Fail('--prune 未删除命中文件')
        if '已删除' not in out or '已清理: 1' not in out:
            raise Fail('prune 计数不为 1 或缺删除回执。输出尾部：\n%s' % out[-400:])
    finally:
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(src_root, ignore_errors=True)


# ---------- F. L0 输入预检器 ----------

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


CHECKS = [
    ('A. SysML 链路金样比对（渲染退出码/结构自检/SVG+清单逐字节）', check_sysml_golden),
    ('B. sync_snapshot 当前审计一致（dry-run=0）', check_sync_audit_clean),
    ('C. 端口回退闸门拦截（exit 1 且 dry-run 不落盘）', check_gate_blocks_regression),
    ('D. --force --apply 强制旁路生效', check_gate_force_bypass),
    ('E. 排除规则 prune 计数与实际删除', check_prune_counts),
    ('F. L0 预检器：负例七类违规拦截报齐 / 正例放行', check_preflight),
]


def main():
    global ss
    sys.dont_write_bytecode = True
    sys.path.insert(0, HERE)
    import sync_snapshot as _ss
    ss = _ss

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
