# Measure relief-valve geometry, scale-corrected (777px / 194 units = 4.005).
import numpy as np
from PIL import Image

S = 777 / 194.0
img = np.array(Image.open('prototype-precheck/rv-big.png').convert('L'))
b = img < 128
H, W = b.shape

def u(v):  # big px -> viewBox units
    return round(v / S, 1)

def runs(mask, min_len=8):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None: start = i
        elif not v and start is not None:
            if i - start >= min_len: out.append((start, i - 1))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask) - 1))
    return out

# 1) box edges: rows/cols with very long runs (>250 big px)
print('== long rows (>250) ==')
for y0, y1 in runs(b.sum(axis=1) >= 250, 2):
    y = y0
    seg = runs(b[y, :], 200)
    print(f'y_big={y} y={u(y)} segs={[(u(a),u(bb)) for a,bb in seg]}')
print('== long cols (>250) ==')
for x0, x1 in runs(b.sum(axis=0) >= 250, 2):
    x = x0
    seg = runs(b[:, x], 200)
    print(f'x_big={x} x={u(x)} segs={[(u(a),u(bb)) for a,bb in seg]}')

# 2) vertical lines outside box region: top area (y<300) and bottom area (y>800)
print('== vertical strokes in TOP area (y 0..300) ==')
for x in range(W):
    for r in runs(b[:300, x], 25):
        print(f'x={u(x)}  y {u(r[0])}..{u(r[1])}')
print('== vertical strokes in BOTTOM area (y 780..972) ==')
for x in range(W):
    for r in runs(b[780:, x], 25):
        print(f'x={u(x)}  y {u(r[0]+780)}..{u(r[1]+780)} -> {u(r[0]+780)}..{u(r[1]+780)}')

# 3) dashed loop: left region (x<330), list all runs per row band
print('== left region segments (x 0..340) ==')
for y in range(0, H, 4):
    seg = runs(b[y, :340], 6)
    if seg:
        print(f'y={u(y)}  ' + '  '.join(f'x {u(a)}..{u(bb)}' for a, bb in seg))
