# -*- coding: utf-8 -*-
"""check_library.py —— 组件库结构校验器（#20 单源化后的快照闸门继任者）。

裁决（#20，2026-09-01）：skill 库 = 唯一规范源，sync_snapshot 的
「规范源→快照」镜像流退役。原闸门的核心价值——油箱事件的端口回退
检测——由本工具以单源方式承接：

  L1  每个 *.svg 必须是合法 XML（解析失败即 fail，不静默跳过）。
  L2  必须含 <g id="connection-points"> 且至少 1 个 data-port-id，
      组内 id 唯一。已知方言缺口走白名单（每项必须带理由与跟踪票，
      白名单不是赦免是挂账）。
  L3  catalog 交叉校验（宽容档默认，--strict-catalog 升硬）：
      symbol.asset 能解析到库内文件 → catalog 声明的端口 id 必须全部
      存在于符号端口组；解析不到 → INFO（#21 回登记工作清单）。

CLI:
    python check_library.py                      # 校验自带库
    python check_library.py --lib DIR --catalog PATH   # 沙箱/测试
    python check_library.py --strict-catalog     # L3 升硬
退出码: 0 过 / 1 fail。
"""
import argparse
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
LIB = os.path.join(SKILL, 'assets', 'component-library')

# 已知方言缺口白名单：name -> (理由, 跟踪票)。新增缺口必须登记到此，
# 无名 white-walk 会被 L2 拦下——白名单是挂账不是赦免。
WHITELIST = {
    'bootstrap-type-reservoir.svg': (
        '油箱方言：端口组缺失即 #21 TANK-001.suction_out 崩溃根源，随 T2 修通',
        '#21'),
    'quick-disconnect-coupling.svg': (
        '连接位变体：端口语义待工程确认（unknown: quick-disconnect-port-'
        'semantics-pending）', '#21/#22'),
}


def read_symbol_ports(path):
    """返回 (解析成功?, 端口组存在?, {pid: 1}, 错误信息)。"""
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as e:
        return False, False, {}, 'XML 解析失败: %s' % e
    cps = [g for g in root.iter() if g.get('id') == 'connection-points']
    if not cps:
        return True, False, {}, None
    ports = {}
    for c in cps[0]:
        pid = c.get('data-port-id')
        if not pid:
            continue
        ports[pid] = 1
    return True, True, ports, None


def resolve_asset(asset, lib):
    """catalog 的 symbol.asset 解析到库内文件的路径；解析不到返回 None。"""
    if not asset:
        return None
    base = os.path.basename(asset.replace('\\', '/'))
    p = os.path.join(lib, base)
    return p if os.path.isfile(p) else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--lib', default=LIB, help='库目录（默认 skill 自带）')
    ap.add_argument('--catalog', default=None,
                    help='catalog 路径（默认 <lib>/component-catalog.json）')
    ap.add_argument('--strict-catalog', action='store_true',
                    help='L3 catalog 交叉校验升级为硬失败（#21 回登记后启用）')
    a = ap.parse_args(argv)

    cat_path = a.catalog or os.path.join(a.lib, 'component-catalog.json')
    fails, infos = [], []

    # ---- L1/L2 端口 lint ----
    svgs = sorted(glob.glob(os.path.join(a.lib, '*.svg')))
    if not svgs:
        fails.append('库内无 SVG：%s' % a.lib)
    port_index = {}
    for p in svgs:
        name = os.path.basename(p)
        ok, has_cp, ports, err = read_symbol_ports(p)
        if not ok:
            fails.append('L1 %s %s' % (name, err))
            continue
        if not has_cp:
            if name in WHITELIST:
                why, ref = WHITELIST[name]
                infos.append('L2 豁免 %s —— %s（%s）' % (name, why, ref))
            else:
                fails.append('L2 %s 无 connection-points 端口组'
                             '（白名单外，登记 WHITELIST 或修符号）' % name)
            continue
        port_index[name] = ports
        dup = len(ports) != len(set(ports))
        if dup or not ports:
            fails.append('L2 %s 端口组异常（空或 id 重复）' % name)

    # ---- L3 catalog 交叉校验 ----
    if os.path.isfile(cat_path):
        with open(cat_path, encoding='utf-8') as f:
            cat = json.load(f)
        for c in cat.get('components', []):
            asset = (c.get('symbol') or {}).get('asset')
            target = resolve_asset(asset, a.lib)
            if target is None:
                msg = ('L3 %s 的 symbol.asset 解析不到库内文件: %s'
                       % (c.get('component_type'), asset))
                (fails if a.strict_catalog else infos).append(
                    msg + ('' if a.strict_catalog else '（INFO：#21 回登记清单）'))
                continue
            sym_ports = port_index.get(os.path.basename(target))
            if sym_ports is None:
                continue                     # 符号无端口组，L2 已裁决
            missing = [q['id'] for q in c.get('ports', [])
                       if q['id'] not in sym_ports]
            if missing:
                msg = ('L3 %s catalog 声明端口不在符号端口组: %s'
                       % (c.get('component_type'), sorted(missing)))
                (fails if a.strict_catalog else infos).append(msg)
    else:
        fails.append('catalog 不存在: %s' % cat_path)

    # ---- 出口 ----
    print('== check_library ==')
    print('库: %s（SVG %d，端口组 %d，白名单 %d）'
          % (a.lib, len(svgs), len(port_index), len(WHITELIST)))
    for m in infos:
        print(' INFO', m)
    for m in fails:
        print(' FAIL', m)
    print('结论: %s（INFO %d / FAIL %d）'
          % ('通过' if not fails else '不通过', len(infos), len(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
