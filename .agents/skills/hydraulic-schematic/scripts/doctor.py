# -*- coding: utf-8 -*-
"""Environment doctor: report every missing dependency in one pass.

Checks the Python packages declared in ../requirements.txt and a local
rasterizer (Inkscape or Chrome). Exit 0 = required items present, 1 = a
required item is missing. Optional packages that are absent, and installed
versions that differ from the pins, are reported but do not fail the check.
Only the standard library is imported at module level, so it still runs
when the packages it checks for are absent.
"""
import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from collections import namedtuple

REQUIREMENTS = Path(__file__).resolve().parent.parent / 'requirements.txt'

Pkg = namedtuple('Pkg', 'module dist why optional')
PACKAGES = (
    Pkg('ruamel.yaml', 'ruamel.yaml', 'L0 intent 读写', False),
    Pkg('kiwisolver', 'kiwisolver', '布局守门', False),
    Pkg('PIL', 'Pillow', '回读与像素校核', False),
    Pkg('numpy', 'numpy', '回读与像素校核', False),
    # preflight.py 缺失时降级为 W-SHAPE-DEP WARN，不阻断出图
    Pkg('jsonschema', 'jsonschema', '预检形状层（缺失时预检降级为 WARN）', True),
)
_BY_MODULE = {p.module: p for p in PACKAGES}

_WINDOWS_INKSCAPE = (r'D:\Program Files\Inkscape\bin\inkscape.exe',
                     r'C:\Program Files\Inkscape\bin\inkscape.exe')
_CHROME_NAMES = ('google-chrome', 'chromium', 'chromium-browser', 'chrome')


def dist_name(module):
    return _BY_MODULE[module].dist


def module_present(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False  # parent package absent, e.g. ruamel for ruamel.yaml


def installed_version(dist):
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return None


def _fallback_rasterizer():
    """Same search order as rasterize_sheet.renderer(), stdlib only."""
    for name in _CHROME_NAMES:
        exe = shutil.which(name)
        if exe:
            return 'chrome', exe
    exe = shutil.which('inkscape')
    if not exe and os.name == 'nt':
        exe = next((p for p in _WINDOWS_INKSCAPE if os.path.isfile(p)), None)
    if exe:
        return 'inkscape', exe
    raise RuntimeError('缺少可用的本机 Inkscape/Chrome')


def find_rasterizer():
    """Return (kind, path); raise RuntimeError when neither tool exists.

    Prefer the real renderer() so doctor agrees with what the scripts will use;
    fall back to a stdlib copy when importing it fails for any reason.
    """
    try:
        from rasterize_sheet import renderer
    except Exception:  # rasterize_sheet imports optional packages at module level
        return _fallback_rasterizer()
    return renderer()


def read_requirements(path=REQUIREMENTS):
    pins = {}
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        line = line.split('#', 1)[0].strip()
        if not line:
            continue
        for op in ('==', '>=', '<=', '~=', '>', '<'):
            if op in line:
                name, ver = line.split(op, 1)
                pins[name.strip()] = op + ver.strip()
                break
        else:
            pins[line] = ''
    return pins


def check():
    pins = read_requirements()
    present, missing, optional_missing, mismatch = [], [], [], []
    for pkg in PACKAGES:
        if not module_present(pkg.module):
            entry = {'module': pkg.module, 'install': pkg.dist, 'needed_for': pkg.why}
            (optional_missing if pkg.optional else missing).append(entry)
            continue
        have = installed_version(pkg.dist)
        present.append({'module': pkg.module, 'install': pkg.dist, 'version': have})
        pin = pins.get(pkg.dist, '')
        if have and pin.startswith('==') and have != pin[2:]:
            mismatch.append({'module': pkg.module, 'installed': have, 'pinned': pin[2:]})
    try:
        kind, exe = find_rasterizer()
        present.append({'module': 'rasterizer', 'kind': kind, 'path': exe})
    except RuntimeError as exc:
        missing.append({'module': 'rasterizer', 'needed_for': '1:1 PNG 回读',
                        'install': '安装 Inkscape 或 Chrome（%s）' % exc})
    return {'ok': not missing, 'present': present, 'missing': missing,
            'optional_missing': optional_missing, 'version_mismatch': mismatch}


def install_command():
    return '"%s" -m pip install -r "%s"' % (sys.executable, REQUIREMENTS)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--json', action='store_true', help='输出机器可读结果')
    args = parser.parse_args(argv)
    report = check()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    for item in report['present']:
        detail = item.get('path') or '%s %s' % (item['install'], item.get('version') or '')
        print(' OK   %-12s %s' % (item['module'], detail.strip()))
    for item in report['optional_missing']:
        print(' 可选缺失 %-12s %s（用途：%s）' % (item['module'], item['install'], item['needed_for']))
    for item in report['version_mismatch']:
        print(' 版本不同 %-12s 已装 %s，requirements.txt 固定 %s（不阻断）'
              % (item['module'], item['installed'], item['pinned']))
    for item in report['missing']:
        print(' 缺失 %-12s %s（用途：%s）' % (item['module'], item['install'], item['needed_for']))
    if report['ok']:
        print('结论: 环境齐备')
        return 0
    print('结论: 缺 %d 项必需依赖' % len(report['missing']))
    if any(i['module'] != 'rasterizer' for i in report['missing']):
        print('安装全部固定版本的 Python 依赖: %s' % install_command())
    if any(i['module'] == 'rasterizer' for i in report['missing']):
        print('光栅化工具: 安装 Inkscape 或 Chrome 任一即可')
    return 1


if __name__ == '__main__':
    sys.exit(main())
