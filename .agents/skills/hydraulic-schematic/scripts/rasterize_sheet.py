# -*- coding: utf-8 -*-
"""Export an SVG to a fresh 1:1 PNG with Inkscape or headless Chrome.

stdout is one JSON result; diagnostics go to stderr. This produces a readback
image, not a perceptual-review verdict. No network service is needed.
"""
import argparse
import json
import math
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from proofreading_evidence import file_digest, write_png_receipt
from browser_evidence import font_environment


def dimensions(svg, width=None):
    root = ET.parse(svg).getroot()
    box = [float(v) for v in root.get('viewBox', '').replace(',', ' ').split()]
    if (len(box) != 4 or any(not math.isfinite(v) for v in box)
            or box[0] != 0 or box[1] != 0 or box[2] <= 0 or box[3] <= 0):
        raise ValueError('1:1 像素校核需要从 (0,0) 起的有效 viewBox')
    w, h = round(box[2]), round(box[3])
    if abs(w-box[2]) > 1e-6 or abs(h-box[3]) > 1e-6:
        raise ValueError('1:1 回读的 viewBox 宽高必须是整数')
    if width is not None and width != w:
        raise ValueError('回读宽度必须等于 viewBox 宽 %d，收到 %d' % (w, width))
    return w, h


def renderer(backend='auto'):
    if backend in ('auto', 'chrome'):
        for name in ('google-chrome', 'chromium', 'chromium-browser', 'chrome'):
            exe = shutil.which(name)
            if exe:
                return 'chrome', exe
    if backend in ('auto', 'inkscape'):
        exe = shutil.which('inkscape')
        if not exe and os.name == 'nt':
            exe = next((p for p in [r'D:\Program Files\Inkscape\bin\inkscape.exe',
                                    r'C:\Program Files\Inkscape\bin\inkscape.exe']
                        if os.path.isfile(p)), None)
        if exe:
            return 'inkscape', exe
    raise RuntimeError('缺少可用的本机 Inkscape/Chrome，未生成回读图')


def png_dimensions(path):
    with open(path, 'rb') as stream:
        head = stream.read(24)
    if len(head) != 24 or head[:8] != b'\x89PNG\r\n\x1a\n' or head[12:16] != b'IHDR':
        raise RuntimeError('回读结果不是有效 PNG')
    return struct.unpack('>II', head[16:24])


def export(svg, output, width=None, backend='auto', timeout=60):
    svg, output = Path(svg).resolve(), Path(output).resolve()
    if svg == output:
        raise ValueError('PNG 输出不能覆盖输入 SVG')
    started = time.monotonic()
    output.parent.mkdir(parents=True, exist_ok=True)
    # Failed exports never leave an old image looking current.
    output.unlink(missing_ok=True)
    Path(str(output) + '.evidence.json').unlink(missing_ok=True)
    source_digest = file_digest(svg)
    w, h = dimensions(svg, width)
    kind, executable = renderer(backend)
    with tempfile.TemporaryDirectory(prefix='sheet-raster-', dir=output.parent) as tmp:
        temporary = Path(tmp, 'readback.png')
        if kind == 'inkscape':
            cmd = [executable, str(svg), '-o', str(temporary), '-w', str(w)]
        else:
            cmd = [executable, '--headless', '--disable-gpu', '--disable-dev-shm-usage',
                   '--hide-scrollbars', '--force-device-scale-factor=1',
                   '--no-first-run', '--no-default-browser-check',
                   '--user-data-dir=' + str(Path(tmp, 'profile')),
                   '--window-size=%d,%d' % (w, h), '--screenshot=' + str(temporary)]
            if hasattr(os, 'geteuid') and os.geteuid() == 0:
                cmd.append('--no-sandbox')
            cmd.append(svg.as_uri())
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8', errors='replace', timeout=timeout)
        if proc.returncode or not temporary.is_file():
            raise RuntimeError('%s 转换失败 rc=%s: %s' % (kind, proc.returncode, proc.stderr[-1800:]))
        if png_dimensions(temporary) != (w, h):
            raise RuntimeError('PNG 尺寸与 SVG viewBox 不同，拒绝像素校核')
        if source_digest != file_digest(svg):
            raise RuntimeError('SVG changed during rasterization; readback discarded')
        os.replace(temporary, output)
    version = subprocess.run([executable, '--version'], capture_output=True, text=True,
                             timeout=10).stdout.strip()
    write_png_receipt(svg, output, {'backend': kind, 'version': version,
                                  'exporter_sha256': file_digest(__file__), 'font_environment':font_environment(svg),
                                  'width': w, 'height': h})
    return dict(renderer=kind, width=w, height=h, output=str(output),
                elapsed_s=round(time.monotonic() - started, 6))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('svg')
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('--width', type=int)
    parser.add_argument('--backend', choices=('auto', 'inkscape', 'chrome'), default='auto')
    args = parser.parse_args()
    try:
        result = export(args.svg, args.output, args.width, args.backend)
    except (ValueError, OSError, ET.ParseError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
