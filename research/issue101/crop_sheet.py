# -*- coding: utf-8 -*-
"""#101 一次性：把若干张出好的图的同一区域并排截成 PNG，用来挑对比对（不进 main）。

用法（仓库根目录）:
  python3 research/issue101/crop_sheet.py x y w h out.png [--scale 1.5] <workdir> [<workdir> ...]
"""
import argparse
import io
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def inner(workdir):
    s = io.open(Path(workdir) / '1#系统原理图.svg', encoding='utf-8').read()
    body = s[s.index('</style>') + 8:s.rindex('</svg>')]
    css = s[s.index('<style>') + 7:s.index('</style>')]
    return css, body


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('box', nargs=4, type=float)
    ap.add_argument('out')
    ap.add_argument('workdirs', nargs='+')
    ap.add_argument('--scale', type=float, default=1.0)
    a = ap.parse_args()
    x, y, w, h = a.box
    gap, tag = 24, 26
    css, parts = None, []
    for i, wd in enumerate(a.workdirs):
        css, body = inner(wd)
        left = i * (w + gap)
        parts.append('<svg x="%.1f" y="%d" width="%.1f" height="%.1f" viewBox="%.1f %.1f %.1f %.1f" overflow="hidden">'
                     '<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" fill="#fff" stroke="#bbb"/>%s</svg>'
                     '<text x="%.1f" y="%d" style="font:700 15px sans-serif;fill:#0f6e6e">%s</text>'
                     % (left, tag, w, h, x, y, w, h, x, y, w, h, body, left + 6, tag - 8,
                        chr(65 + i) + ' ' + Path(wd).name[:70]))
    W, H = int(len(a.workdirs) * w + (len(a.workdirs) - 1) * gap), int(h + tag)
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d"><style>%s</style>%s</svg>'
           % (W, H, W, H, css, ''.join(parts)))
    out = Path(a.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix='crop-', dir=str(out.parent)))
    src = tmp / 'crop.svg'
    src.write_text(svg, encoding='utf-8')
    exe = next((shutil.which(n) for n in ('google-chrome', 'chromium', 'chromium-browser', 'chrome') if shutil.which(n)), None)
    png = tmp / 'shot.png'
    cmd = [exe, '--headless', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
           '--force-device-scale-factor=%g' % a.scale, '--window-size=%d,%d' % (W, int(H * a.scale)),
           '--user-data-dir=' + str(tmp / 'profile'), '--screenshot=' + str(png), src.as_uri()]
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        cmd.append('--no-sandbox')
    subprocess.run(cmd, capture_output=True, timeout=60)
    shutil.move(str(png), str(out))
    shutil.rmtree(tmp, ignore_errors=True)
    print(out)


if __name__ == '__main__':
    main()
