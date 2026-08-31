# Measure geometry of traced Relief Valve symbol from 3x rendered PNG.
# Prints black-pixel structure: long vertical/horizontal runs, box edges,
# dashed segments, spring zigzag extent. Coordinates: big px and /3 source px.
import numpy as np
from PIL import Image

img = np.array(Image.open('prototype-precheck/rv-big.png').convert('L'))
b = img < 128  # black mask
H, W = b.shape
print(f'image {W}x{H} (3x of 194x243 viewBox)')

# Column/row black-pixel counts to locate long strokes
colcnt = b.sum(axis=0)
rowcnt = b.sum(axis=1)

def runs(mask, min_len):
    out, start = [], None
    for i, v in enumerate(mask):
        if v and start is None:
            start = i
        elif not v and start is not None:
            if i - start >= min_len:
                out.append((start, i - 1))
            start = None
    if start is not None and len(mask) - start >= min_len:
        out.append((start, len(mask) - 1))
    return out

print('\n-- vertical strokes (cols with run>=60) --')
for c in runs(colcnt >= 60, 2):
    xs = c[0]
    ys = np.where(b[:, xs])[0]
    # find contiguous runs in this column
    for r in runs(b[:, xs], 60):
        print(f'col x={xs} ({xs/3:.1f})  y {r[0]}..{r[1]} ({r[0]/3:.1f}..{r[1]/3:.1f}) len={r[1]-r[0]+1}')

print('\n-- horizontal strokes (rows with run>=60) --')
for r in runs(rowcnt >= 60, 2):
    ys = r[0]
    for rr in runs(b[ys, :], 60):
        print(f'row y={ys} ({ys/3:.1f})  x {rr[0]}..{rr[1]} ({rr[0]/3:.1f}..{rr[1]/3:.1f}) len={rr[1]-rr[0]+1}')

# medium-length vertical strokes (dashed verticals & spring diagonals show as short)
print('\n-- short/medium vertical runs per column (len 10..59), sampled dense cols --')
for x in range(W):
    for r in runs(b[:, x], 12):
        if r[1] - r[0] + 1 <= 59:
            print(f'x={x} ({x/3:.1f})  y {r[0]}..{r[1]} ({r[0]/3:.1f}..{r[1]/3:.1f}) len={r[1]-r[0]+1}')
