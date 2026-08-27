# Pipeline Arrow Removal and Suction-S Parameterization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove renderer-added pipeline flow arrows while preserving component-internal directional symbols, and derive all suction slash geometry from `layout.style.suction_marker_S = 8`.

**Architecture:** Pipeline direction arrows disappear at the renderer data-flow boundary: `wire()` no longer creates arrow markup and `main()` no longer emits an `arrows` layer. Suction styling remains a continuous 1.0T baseline plus independent five-slash groups; one `S` parameter controls slash size and spacing, and the same geometry helper serves sheet marks and the legend.

**Tech Stack:** Python 3, `unittest`, SVG/XML (`xml.etree.ElementTree`), JSON layout, Chrome headless PNG readback.

## Global Constraints

- Preserve all symbol-internal direction graphics, including `TANK-001__motion-arrow-up` and pump/check-valve direction features.
- Remove only renderer-added pipeline direction arrows (`.arw` and the generated `arrows` layer).
- `suction_marker_S` defaults to `8.0` only for backward compatibility; the checked-in layout must declare `8` explicitly.
- Derive slash total height as `2S`, angle as `60°`, intra-group spacing as `1.25S`, group pitch as `12.5S`, and end clearance as `4S`.
- Every suction marker group contains exactly five slashes over a continuous 1.0T baseline.
- Neither baseline nor slash marks may use `vector-effect: non-scaling-stroke`.
- Slash groups must avoid components, text, flow-independent symbol graphics, junctions, bridges, group borders, legend, and title block.
- Do not change `intent.yaml` topology or symbol-internal geometry.
- Keep existing unrelated V12/V13 full-sheet failures visible; do not report the entire sheet as passed.
- The workspace is not a git repository, so commit steps are intentionally omitted.

---

## File Map

- Modify `1#系统原理图/render.py`: remove pipeline-arrow generation and parameterize suction marks.
- Modify `1#系统原理图/test_suction_markers.py`: TDD coverage for arrow removal and all S-derived dimensions.
- Modify `1#系统原理图/validate_sheet.py`: deterministic checks for no generated arrows and declared S geometry.
- Modify `1#系统原理图/1#系统.layout.json`: add `style.suction_marker_S: 8`.
- Modify `液压原理图组件与JSON生成技术规范.md`: formalize S derivation and arrow policy.
- Regenerate `1#系统原理图/1#系统原理图.svg` and `validation-report.json`.

### Task 1: Remove Renderer-Added Pipeline Arrows

**Files:**
- Modify: `1#系统原理图/render.py:486-496, 540-665, 1030-1070`
- Modify: `1#系统原理图/test_suction_markers.py`
- Modify: `1#系统原理图/validate_sheet.py`

**Interfaces:**
- Consumes: `Sheet.wire() -> (segments, junctions, bus_hits, polylines)` after this task.
- Produces: generated SVG with no `.arw` class and no `id="arrows"` layer.
- Preserves: any `<path>`, `<polygon>`, or `<line>` embedded inside component instances, regardless of directional appearance.

- [ ] **Step 1: Write the failing test**

Add to `test_suction_markers.py`:

```python
def test_sheet_has_no_renderer_pipeline_arrows(self):
    r.main()
    raw = open(os.path.join(HERE, '1#系统原理图.svg'), encoding='utf-8').read()
    root = ET.fromstring(raw.encode('utf-8'))
    ns = '{http://www.w3.org/2000/svg}'
    self.assertFalse(any(e.get('class') == 'arw' for e in root.iter()))
    self.assertFalse(any(e.get('id') == 'arrows' for e in root.iter(ns + 'g')))
    self.assertIn('EDP-001__symbol', raw)
    self.assertIn('EMP-001__symbol', raw)
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
cd "1#系统原理图"
python3 -m unittest -v \
  test_suction_markers.SuctionMarkerTest.test_sheet_has_no_renderer_pipeline_arrows
```

Expected: FAIL because the rendered sheet still contains `<path class="arw">` and `<g id="arrows">`.

- [ ] **Step 3: Remove arrow production at the source**

In `render.py`:

1. Delete `Sheet.arrow()`.
2. Change `wire()` from collecting `arrows` to returning only:

```python
return segs, junctions, bus_hits, self.polys
```

3. Remove both `arrows.append(...)` sites.
4. In `main()` consume four return values:

```python
_segs, junc, bus, polys = s.wire()
```

5. Delete:

```python
body.append('<g id="arrows">%s</g>' % '\n'.join(arrows))
```

6. Delete `.arw` CSS.
7. Remove arrow boxes from suction-marker `blocked`; they no longer exist as renderer output.

Do not search-and-delete symbol paths containing arrows. The scope is the renderer-owned `.arw` class only.

- [ ] **Step 4: Add deterministic validation**

Add V18 in `validate_sheet.py`:

```python
pipeline_arrows = [e for e in root.iter() if e.get('class') == 'arw']
arrow_layers = [e for e in root.iter() if e.get('id') == 'arrows']
if pipeline_arrows or arrow_layers:
    F.append(('V18', '管线方向箭头未取消: arw=%d arrows-layer=%d'
              % (len(pipeline_arrows), len(arrow_layers))))
ev.append({'id': 'V18', 'pipeline_arrows': len(pipeline_arrows),
           'arrow_layers': len(arrow_layers)})
```

- [ ] **Step 5: Verify GREEN and symbol preservation**

Run:

```bash
python3 -m unittest -v test_suction_markers.py
python3 render.py
grep -c 'class="arw"\|id="arrows"' '1#系统原理图.svg'
grep -c 'EDP-001__symbol\|EMP-001__symbol' '1#系统原理图.svg'
```

Expected: tests PASS; first grep returns `0`; second grep returns at least `2`.

### Task 2: Parameterize Suction Geometry from S

**Files:**
- Modify: `1#系统原理图/render.py:50-105, 920-980, 1000-1065`
- Modify: `1#系统原理图/test_suction_markers.py`
- Modify: `1#系统原理图/1#系统.layout.json:22-25`

**Interfaces:**
- Consumes: `layout.style.suction_marker_S: number`.
- Produces: `suction_marker_geometry(S) -> dict` and `suction_markers(pts, blocked=(), S=8.0) -> list[(point, point)]`.
- Geometry keys: `slash_height`, `slash_angle_deg`, `intra_spacing`, `group_pitch`, `end_clearance`, `count`.

- [ ] **Step 1: Write failing geometry tests**

Add:

```python
def test_suction_geometry_is_derived_from_S(self):
    g = r.suction_marker_geometry(8.0)
    self.assertEqual(g['count'], 5)
    self.assertAlmostEqual(g['slash_height'], 16.0)
    self.assertAlmostEqual(g['slash_angle_deg'], 60.0)
    self.assertAlmostEqual(g['intra_spacing'], 10.0)
    self.assertAlmostEqual(g['group_pitch'], 100.0)
    self.assertAlmostEqual(g['end_clearance'], 32.0)

def test_S_scales_every_dimension(self):
    a = r.suction_marker_geometry(8.0)
    b = r.suction_marker_geometry(12.0)
    for key in ('slash_height', 'intra_spacing', 'group_pitch', 'end_clearance'):
        self.assertAlmostEqual(b[key] / a[key], 1.5)
    self.assertEqual(a['slash_angle_deg'], b['slash_angle_deg'])
    self.assertEqual(a['count'], b['count'])
```

Update existing marker tests to call `suction_markers(..., S=8.0)`.

- [ ] **Step 2: Verify RED**

Run:

```bash
python3 -m unittest -v \
  test_suction_markers.SuctionMarkerTest.test_suction_geometry_is_derived_from_S \
  test_suction_markers.SuctionMarkerTest.test_S_scales_every_dimension
```

Expected: ERROR because `suction_marker_geometry` does not exist.

- [ ] **Step 3: Implement the single-source geometry function**

Add:

```python
def suction_marker_geometry(S):
    S = float(S)
    if S <= 0:
        raise ValueError('suction_marker_S 必须 > 0,实际 %g' % S)
    return {
        'count': 5,
        'slash_height': 2.0 * S,
        'slash_angle_deg': 60.0,
        'intra_spacing': 1.25 * S,
        'group_pitch': 12.5 * S,
        'end_clearance': 4.0 * S,
    }
```

In `suction_markers()` compute slash horizontal half-span from the fixed angle measured from the baseline normal:

```python
g = suction_marker_geometry(S)
dy = g['slash_height'] / 2.0
dx = dy / math.tan(math.radians(g['slash_angle_deg']))
```

Use `g['count']`, `g['intra_spacing']`, `g['group_pitch']`, and `g['end_clearance']`; remove the old numeric constants `31`, `5`, `7`, `5`, `8`, `100`.

- [ ] **Step 4: Declare S in layout and thread it through**

Set:

```json
"style": {
  "base_line_width_T": 1.2,
  "symbol_stroke_width": 2,
  "suction_marker_S": 8
}
```

In `main()`:

```python
S = float(layout.get('style', {}).get('suction_marker_S', 8.0))
for a, b in suction_markers(pts, blocked, S=S):
    ...
```

Pass the same `S` to `legend(layout, T)` by reading it from `L['style']` inside `legend()`; do not duplicate geometry arithmetic in the legend.

- [ ] **Step 5: Make legend use the same geometry helper**

Render the legend’s five slashes from `suction_marker_geometry(S)`, scaled only to the 44-unit sample width if necessary. The legend text must include:

```text
Suction Lines 吸油:连续基线 + 周期性五斜杠组 1.0 T (S=8)
```

The baseline remains a separate `suc-sample-base`; five lines remain `suc-sample-mark`.

- [ ] **Step 6: Verify geometry tests and integration**

Run:

```bash
python3 -m unittest -v test_suction_markers.py
```

Expected: all tests PASS with no `ResourceWarning`.

### Task 3: Update V17 and Engineering Specification

**Files:**
- Modify: `1#系统原理图/validate_sheet.py:259-360`
- Modify: `液压原理图组件与JSON生成技术规范.md:743-750`

**Interfaces:**
- Consumes: rendered SVG and `layout.style.suction_marker_S`.
- Produces: V17 evidence containing `S`, derived geometry, group/slash counts, and obstacle collisions.

- [ ] **Step 1: Write failing validator evidence tests**

Add `test_v17_reports_declared_S` to `test_suction_markers.py`:

```python
def test_v17_reports_declared_S(self):
    r.main()
    import subprocess, json
    subprocess.run(['python3', os.path.join(HERE, 'validate_sheet.py')],
                   cwd=HERE, check=False, capture_output=True, text=True)
    with open(os.path.join(HERE, 'validation-report.json'), encoding='utf-8') as f:
        report = json.load(f)
    v17 = next(e for e in report['evidence'] if e['id'] == 'V17')
    self.assertEqual(v17['S'], 8.0)
    self.assertEqual(v17['slash_height'], 16.0)
    self.assertEqual(v17['slash_angle_deg'], 60.0)
    self.assertEqual(v17['intra_spacing'], 10.0)
    self.assertEqual(v17['group_pitch'], 100.0)
    self.assertEqual(v17['end_clearance'], 32.0)
```

This test initially fails because V17 does not yet expose S-derived geometry. Do not mutate the checked-in layout inside a test; `render.main()` reads that file directly and an interrupted test could leave production inputs corrupted.

Expected evidence schema:

```python
{
  'id': 'V17',
  'S': 8.0,
  'slash_height': 16.0,
  'slash_angle_deg': 60.0,
  'intra_spacing': 10.0,
  'group_pitch': 100.0,
  'end_clearance': 32.0,
  'groups': 4,
  'slashes': 20,
  'obstacle_hits': 0,
  'baseline': 'continuous'
}
```

- [ ] **Step 2: Extend V17**

In `validate_sheet.py` derive the expected values from `S` and verify:

1. `S > 0`.
2. `.ln-suction` has no `stroke-dasharray`.
3. Every group contains exactly five slashes.
4. Every slash carries the 1.0T style class.
5. Legend displays exactly one continuous baseline, exactly five slash marks, and the declared S.
6. Slash groups do not overlap components, text, bridges, junctions, group borders, legend, or title block.
7. No duplicate slash geometry exists.

- [ ] **Step 3: Update §10.6.1**

Record the approved derivation verbatim:

```text
S is a drawing-style parameter chosen to suit the output scale.
slash total height = 2S
slash angle = 60°
intra-group center spacing = 1.25S
group-center pitch = 12.5S
end clearance = 4S
count per group = 5
```

Add that renderer-added pipeline flow arrows are prohibited; component-internal directional features remain part of the controlled symbol and are not removed.

- [ ] **Step 4: Verify V17 and V18 evidence**

Run:

```bash
python3 render.py
python3 validate_sheet.py || true
python3 - <<'PY'
import json
d = json.load(open('validation-report.json', encoding='utf-8'))
print([e for e in d['evidence'] if e['id'] in ('V17', 'V18')])
PY
```

Expected: V17 and V18 have no failures. The command may still exit nonzero because the sheet’s existing V12/V13 layout failures are outside this plan.

### Task 4: Regenerate and Perform Perceptual Verification

**Files:**
- Regenerate: `1#系统原理图/1#系统原理图.svg`
- Regenerate: `1#系统原理图/validation-report.json`
- Regenerate: `1#系统原理图/sheet-readback.png`

**Interfaces:**
- Consumes: final renderer, layout, intent, and component catalog.
- Produces: sheet and validation evidence suitable for engineering review.

- [ ] **Step 1: Run all focused tests**

```bash
cd "1#系统原理图"
python3 -m unittest -v test_suction_markers.py
```

Expected: every test passes and output contains no `ResourceWarning`.

- [ ] **Step 2: Regenerate SVG and PNG**

```bash
python3 render.py
cp '1#系统原理图.svg' /tmp/hydraulic-sheet.svg
google-chrome-stable --headless --disable-gpu --no-sandbox --hide-scrollbars \
  --screenshot=sheet-readback.png --window-size=1580,1210 \
  --default-background-color=FFFFFFFF file:///tmp/hydraulic-sheet.svg
```

- [ ] **Step 3: Inspect the PNG**

Verify visually that there are no pipeline arrowheads; pump/valve/reservoir internal directional features remain; all suction runs use a continuous baseline with complete five-slash groups; no slash crosses labels, arrows, symbols, bridges, junctions, or group borders.

- [ ] **Step 4: Run deterministic validation**

```bash
python3 validate_sheet.py || true
```

Report V17/V18 separately from the full-sheet status. Do not call the sheet passed while unrelated V12/V13 failures remain.

- [ ] **Step 5: Verify scaling**

Render at 2× and measure one baseline and one slash. Their pixel dimensions must approximately double; the SVG must contain zero active `non-scaling-stroke` declarations.

- [ ] **Step 6: Report exact outcome**

State focused test counts, V17/V18 evidence, PNG inspection result, scaling evidence, and all remaining full-sheet failures by ID and geometry.
