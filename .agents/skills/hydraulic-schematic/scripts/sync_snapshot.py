# -*- coding: utf-8 -*-
"""sync_snapshot.py —— 组件库规范源 → skill 快照 的同步守门工具。

仓库规范源(已标注/, 根目录脚本, 范例)是唯一事实来源；本 skill 内的
assets/ 与 scripts/ 只是它的同步快照。盲拷贝会把"符号端口回退""方言
漂移(如 port-anchors 冒充 connection-points)"这类问题带进快照——
油箱事件(TANK-001.suction_out)即由此而来。本工具把那次教训固化成闸门：

  1. 差异审计：逐字节比对三组资产，列出 新增/修改/缺失。
  2. 端口回退闸门：快照里旧版带 <g id="connection-points"> 的符号，
     源头新版本若丢了端口组 → 拒绝拷入该文件(exit 1)，除非 --force。
  3. 端口变化播报：其余变更符号打印端口 id 增删与坐标/属性位移，
     提示走 SKILL.md「随附资产」里对应档位的后续操作。

默认只读(dry run)。加 --apply 才真正写入。退出码：
  0 = 一致或已成功同步   1 = 有文件被闸门拦截   2 = 有待同步差异
"""
import argparse
import filecmp
import glob
import json
import os
import shutil
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)

# 规范源相对组件库仓库根的路径（skill 自身位于 <仓库根>/.agents/skills/<name>/）
REPO = os.path.normpath(os.path.join(SKILL, '..', '..', '..'))

LIB_GROUP = dict(
    name='component-library',
    src=os.path.join(REPO, '已标注'),
    dst=os.path.join(SKILL, 'assets', 'component-library'),
    patterns=['*.svg', 'component-catalog.json'],
    exclude=['test-*', 'stroke-symbol-preview*', 'hydraulic_system_schematic_diagram*',
             'negative-*', '*preview*'],
)
SCRIPTS_GROUP = dict(
    name='scripts',
    src=None,  # 散在两处，单独枚举
    dst=os.path.join(SKILL, 'scripts'),
    pairs=[
        (os.path.join(REPO, 'render_aircraft_schematic.py'), 'render_aircraft_schematic.py'),
        (os.path.join(REPO, '已标注', '1#系统原理图', 'render.py'), 'render_l0_sheet.py'),
        (os.path.join(REPO, '已标注', '1#系统原理图', 'validate_sheet.py'), 'validate_sheet.py'),
        (os.path.join(REPO, '已标注', '1#系统原理图', 'test_suction_markers.py'), 'test_suction_markers.py'),
    ],
)
EXAMPLES_GROUP = dict(
    name='examples',
    src=None,
    dst=os.path.join(SKILL, 'assets', 'examples'),
    pairs=[
        (os.path.join(REPO, 'aircraft_hydraulic_system.sysml'), 'aircraft_hydraulic_system.sysml'),
        (os.path.join(REPO, '已标注', 'system-1.intent.yaml'), 'system-1.intent.yaml'),
        (os.path.join(REPO, '已标注', '1#系统原理图', '1#系统.layout.json'), '1#系统.layout.json'),
        (os.path.join(REPO, '已标注', 'negative-group-in-path.intent.yaml'), 'negative-group-in-path.intent.yaml'),
        (os.path.join(REPO, '已标注', 'negative-group-in-path.expected-report.json'), 'negative-group-in-path.expected-report.json'),
        (os.path.join(REPO, '已标注', 'negative-sensing-in-path.intent.yaml'), 'negative-sensing-in-path.intent.yaml'),
        (os.path.join(REPO, '已标注', 'negative-sensing-in-path.expected-report.json'), 'negative-sensing-in-path.expected-report.json'),
    ],
)


def excluded(name, pats):
    from fnmatch import fnmatch
    return any(fnmatch(name, p) for p in pats)


def group_files(g):
    """返回 [(src_abs, dst_name)]，应用排除规则。"""
    out = []
    if g.get('patterns'):
        for pat in g['patterns']:
            for f in sorted(glob.glob(os.path.join(g['src'], pat))):
                if not os.path.isfile(f):
                    continue
                n = os.path.basename(f)
                if not excluded(n, g.get('exclude', [])):
                    out.append((f, n))
    else:
        for s, d in g['pairs']:
            if os.path.isfile(s):
                out.append((s, d))
            else:
                print('MISSING 规范源缺失: %s' % s)
    return out


def read_ports(path):
    """解析符号 svg 的标准端口组。返回 None=无组(方言缺失), 否则 {pid: attrs}。"""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {}
    cps = [g for g in root.iter() if g.get('id') == 'connection-points']
    if not cps:
        return None
    ports = {}
    for c in cps[0]:
        pid = c.get('data-port-id')
        if not pid:
            continue
        ports[pid] = (c.get('cx'), c.get('cy'), c.get('data-anchor-direction'),
                      c.get('data-port-role'), c.get('data-medium'))
    return ports


def port_delta(old, new):
    """old/new: {pid: attrs} 或 None。返回 (回退?, 人读差异行列表)。"""
    lines = []
    if old is None and new is None:
        return False, []
    if old and new is None:
        return True, ['  !! 端口组消失：源版本不含 <g id="connection-points">（原 %d 端口）' % len(old)]
    if old is None and new:
        lines.append('  + 新增标注：%d 个端口' % len(new))
        return False, lines
    added = set(new) - set(old)
    removed = set(old) - set(new)
    moved = [p for p in set(old) & set(new) if old[p] != new[p]]
    if added:
        lines.append('  + 新增端口: %s' % ', '.join(sorted(added)))
    if removed:
        lines.append('  - 删除端口: %s' % ', '.join(sorted(removed)))
    if moved:
        lines.append('  ~ 属性/坐标变化: %s' % ', '.join(sorted(moved)))
    return False, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--group', choices=['library', 'scripts', 'examples', 'all'], default='all')
    ap.add_argument('--diff-only', action='store_true', help='同默认 dry run，仅审计不写入')
    ap.add_argument('--apply', action='store_true', help='执行拷贝/清理（受闸门约束）')
    ap.add_argument('--force', action='store_true', help='连被闸门拦截的文件也强制覆盖')
    ap.add_argument('--prune', action='store_true', help='从快照删除命中排除规则的遗留文件')
    ap.add_argument('--sandbox', metavar='DIR',
                    help='测试用：把快照目标整体改写到 DIR 下（不影响真实快照）')
    ap.add_argument('--src-root', metavar='DIR',
                    help='测试/异地用：把库规范源根指向 DIR（默认组件库仓库根）')
    a = ap.parse_args()

    if a.src_root:
        LIB_GROUP['src'] = os.path.join(os.path.abspath(a.src_root), '已标注')

    if a.sandbox:
        base = os.path.abspath(a.sandbox)
        for g in (LIB_GROUP, SCRIPTS_GROUP, EXAMPLES_GROUP):
            tail = os.path.relpath(g['dst'], SKILL)          # assets/component-library 等
            g['dst'] = os.path.join(base, tail.replace('..', '_'))

    apply_ = a.apply and not a.diff_only
    groups = {'library': LIB_GROUP, 'scripts': SCRIPTS_GROUP, 'examples': EXAMPLES_GROUP}
    chosen = groups if a.group == 'all' else {a.group: groups[a.group]}

    pending = blocked = copied = pruned = 0

    for gname, g in chosen.items():
        print('\n== 组: %s ==' % gname)
        files = group_files(g)
        if not files:
            print('  (规范源缺文件? 检查路径) %s' % (g.get('src') or [p[0] for p in g['pairs']]))
            continue
        for src, name in files:
            dstpath = os.path.join(g['dst'], name)
            has_dst = os.path.isfile(dstpath)
            same = has_dst and filecmp.cmp(src, dstpath, shallow=False)
            if same:
                continue
            pending += 1
            act = '新增' if not has_dst else '修改'
            print('%s  %s/%s' % (' NEW' if not has_dst else ' MOD', gname, name))
            if gname == 'library' and name.endswith('.svg'):
                src_ports = read_ports(src)
                blocked_delta, lines = port_delta(read_ports(dstpath) if has_dst else None,
                                                  src_ports)
                for l in lines:
                    print(l)
                if not has_dst and src_ports is None:
                    print('  [提醒] 源符号无 <g id="connection-points"> 端口组'
                          '（草稿或方言遗留），渲染器将无法解析其端口')
                if blocked_delta and has_dst and not a.force:
                    blocked += 1
                    print('  [已拦截] 快照现版含端口而源头丢失（疑似回退）。'
                          '确认非误伤后用 --force。')
                    continue
            if apply_:
                shutil.copy2(src, dstpath)
                copied += 1
                print('  -> 已拷贝')

        # 快照侧多余文件（仅 library 组有排除概念）
        if gname == 'library' and os.path.isdir(g['dst']):
            for f in sorted(os.listdir(g['dst'])):
                full = os.path.join(g['dst'], f)
                if not os.path.isfile(full):
                    continue
                if excluded(f, g['exclude']):
                    print('PRUNE %s/%s （命中排除规则）' % (gname, f))
                    if a.prune:
                        os.remove(full)
                        pruned += 1
                        print('  -> 已删除')

    print('\n---- 小结 ----')
    print('待同步差异数: %d | 已拷贝: %d | 闸门拦截: %d | 已清理: %d | 模式: %s'
          % (pending, copied, blocked, pruned, 'APPLY' if apply_ else 'DRY-RUN'))
    if pending:
        print('\n后续操作（详见 SKILL.md「随附资产与快照同步」）:')
        print(' · 涉及端口的 SVG：更新 catalog 对应 ports[] → 重渲染受影响图纸并跑 Phase 4 校验 → 需要时递增 catalog_revision')
        print(' · 仅图形改动：完成本次同步即可')
        print(' · scripts 变更：重跑一次 render_* 结构自检确认模板可运行')

    if blocked:
        sys.exit(1)
    if pending and not apply_:
        sys.exit(2)
    sys.exit(0)


if __name__ == '__main__':
    main()
