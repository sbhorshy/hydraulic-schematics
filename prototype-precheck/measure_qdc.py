# Measure quick-disconnect coupling (disconnected) geometry. 864x495 png, 4.0 px/unit.
import numpy as np
from PIL import Image

S = 4.0
img = np.array(Image.open('prototype-precheck/qdc-big.png').convert('RGB'))
black = (img < 110).all(axis=2)
red = (img[:, :, 0] > 150) & (img[:, :, 1] < 110) & (img[:, :, 2] < 110)
b = black
H, W = b.shape
print(f'image {W}x{H} (4.0 px/unit of 216x124)')

def u(v): return round(v / S, 1)

def runs(mask, min_len=6):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None: start = i
        elif not v and start is not None:
            if i - start >= min_len: out.append((start, i - 1))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask) - 1))
    return out

print('== red pixels bbox ==')
ys, xs = np.where(red)
if len(xs): print(f'red x {u(xs.min())}..{u(xs.max())}  y {u(ys.min())}..{u(ys.max())}')

print('== long rows (>=200px black) ==')
for y0, y1 in runs(b.sum(axis=1) >= 200, 2):
    for r in runs(b[y0, :], 150):
        print(f'y={u(y0)}  x {u(r[0])}..{u(r[1])} (len {u(r[1]-r[0])})')
print('== long cols (>=200px black) ==')
for x0, x1 in runs(b.sum(axis=0) >= 200, 2):
    for r in runs(b[:, x0], 150):
        print(f'x={u(x0)}  y {u(r[0])}..{u(r[1])} (len {u(r[1]-r[0])})')

print('== structure scan: rows every 8px, merged runs (len>=10) ==')
for y in range(0, H, 8):
    seg = runs(b[y, :], 10)
    if seg:
        print(f'y={u(y):>6}  ' + '  '.join(f'{u(a)}..{u(bb)}' for a, bb in seg))
