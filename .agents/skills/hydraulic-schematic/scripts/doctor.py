# -*- coding: utf-8 -*-
"""Environment doctor: report every missing dependency in one pass.

Checks the Python packages declared in ../requirements.txt and a local
rasterizer (Inkscape or Chrome). Exit 0 = ready, 1 = something is missing.
Only the standard library is imported at module level, so it still runs
when the packages it checks for are absent.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

REQUIREMENTS = Path(__file__).resolve().parent.parent / 'requirements.txt'

# (import name, pip distribution name, why it is needed)
PACKAGES = (
    ('ruamel.yaml', 'ruamel.yaml', 'L0 intent 读写'),
    ('jsonschema', 'jsonschema', '预检形状层'),
    ('kiwisolver', 'kiwisolver', '布局守门'),
    ('PIL', 'Pillow', '像素检查'),
    ('numpy', 'numpy', '像素检查'),
)
_DIST = {m: d for m, d, _ in PACKAGES}
_WHY = {m: w for m, _, w in PACKAGES}
PACKAGES = tuple((m, d) for m, d, _ in PACKAGES)


def dist_name(module):
    return _DIST[module]


def module_present(name):
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False  # parent package absent, e.g. ruamel for ruamel.yaml


def find_rasterizer():
    """Return (kind, path); raise RuntimeError when neither tool exists."""
    try:
        from rasterize_sheet import renderer
    except ImportError:  # rasterize_sheet pulls in optional packages
        for name in ('google-chrome', 'chromium', 'chromium-browser', 'chrome', 'inkscape'):
            exe = shutil.which(name)
            if exe:
                return ('inkscape' if name == 'inkscape' else 'chrome'), exe
        raise RuntimeError('缺少可用的本机 Inkscape/Chrome')
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
    present, missing = [], []
    for module, dist in PACKAGES:
        if module_present(module):
            present.append({'module': module, 'install': dist})
        else:
            missing.append({'module': module, 'install': dist,
                            'needed_for': _WHY.get(module, '')})
    try:
        kind, exe = find_rasterizer()
        present.append({'module': 'rasterizer', 'kind': kind, 'path': exe})
    except RuntimeError as exc:
        missing.append({'module': 'rasterizer', 'needed_for': '1:1 PNG 回读',
                        'install': '安装 Inkscape 或 Chrome（%s）' % exc})
    return {'ok': not missing, 'present': present, 'missing': missing}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--json', action='store_true', help='输出机器可读结果')
    args = parser.parse_args(argv)
    report = check()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['ok'] else 1
    for item in report['present']:
        detail = item.get('path') or item['install']
        print(' OK   %-12s %s' % (item['module'], detail))
    for item in report['missing']:
        print(' 缺失 %-12s %s（用途：%s）' % (item['module'], item['install'], item['needed_for']))
    if report['ok']:
        print('结论: 环境齐备')
        return 0
    pkgs = [i for i in report['missing'] if i['module'] != 'rasterizer']
    print('结论: 缺 %d 项' % len(report['missing']))
    if pkgs:
        print('安装 Python 依赖: pip install -r %s' % REQUIREMENTS)
    if any(i['module'] == 'rasterizer' for i in report['missing']):
        print('光栅化工具: 安装 Inkscape 或 Chrome 任一即可')
    return 1


if __name__ == '__main__':
    sys.exit(main())
