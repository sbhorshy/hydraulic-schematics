# #23 independent acceptance and merge

Reviewer/merger: assembly39, not implementation author. Initial a96039f6ef93e2a6a452e3c0049af5c0705faf1c was independently blocked for an actual-paint false negative, then repaired by original implementer. Accepted frozen candidate819dd59d4c0d22e4527efd4a6452bd7b3c5f646f and merged as **a7f77b7b638c3a1df48dcde28bd095107b06c675** on integration/ready-tickets-20261009. Clean integration; no remote write. Root owns final whole-suite run.

## Contract/scope review

Verified canonical renderer no longer translates sheet; migration adds old shift once to drawing-local coordinates while preserving root panels. Drawable bounds already exclude right edge_margin and consumers do not subtract it twice. System engine/guard, optimizer, R17, validator and driver dependencies share the explicit root contract. Migrated canonical/project/CDF seeds preserve topology and declared source dimensions; right canvas expansion is explicit. Project active render/validate wrappers honor independent workdir. Copied CDF/build entrypoints fail before I/O with canonical replacement instructions. Historical proto/frozen and skill-chain-e2e directories have no diff against pre-ticket integration.

## Independent verification

- Original canonical coordinate CLI suite:5 tests PASS/16.195s; issue-23-independent-core.log.
- Repository active/retired entrypoint suite:2 tests PASS/4.486s; issue-23-independent-entrypoints.log.
- Independently recomputed actual PNG arrays and root geometry from all four before/after artifact sets. Small/assembly/rotation common content pixel-identical; current differs only37pixels, maximum4/255. All pipe point arrays equal exactly; each component footprint and port equal within1e-8. Added right strips white. Failure counts0→0,13→13,0→0,0→0. issue-23-independent-pixel-audit.json. This is not a blanket byte-identical PNG claim.
- Actual project/CDF evidence remains explicitly6FAIL and0FAIL respectively; canonical current13FAIL remains a separate historical regression fixture. Original before-assembly missing-symbol-path2FAIL probe was invalid and has been corrected to0; not used as a legacy defect.

## Blocking finding and fix verification

Initial component_paint_bounds used geometry bbox+stroke radius for polygons/closed paths, missing acute miter ink. Public probe adds to PF(root x850) polygon points80,20 50,10 50,30, stroke20/miterlimit4; drawable.right945. Old report gave right940/no PF V6, but actual PNG pixels x946/y509..511 were black (separate from main pipe at y530). Preserved SVG/layout/report/PNG/crop and finding in issue-23-independent-miter/before-fix and finding.md. Root agreed blocking; no candidate edits by reviewer.

Original implementer fixed closed polygon/path/rect joins, miterlimit/bevel behavior and unsupported-paint not_checked behavior. Independent rerun on the **same preserved SVG/layout** under819dd59 now emits V6 for the probe: measured right961.6227766016838, overflow16.6227766. Evidence issue-23-independent-miter/after-fix-summary.json and after-fix/run/. Exact original reproduction is resolved, not replaced by an easier negative case.

Final repaired coordinate suite: **6 tests PASS/34.763s**, including polygon/closed-path miter and limit3 bevel no-false-positive controls. issue-23-independent-fixed-core.log. Other four normal fixtures retain V6pass/unchecked[] (original implementer fresh normal record issue-23-miter-normal.json). Repair changes only paint checker/tests; rendered SVG/PNG/entrypoint code unchanged, so already independently passed pixel matrix/entry suites were not redundantly rerun.

No remaining merger-blocking issue. Full two-axis review/full selftest still belongs to root; no human engineering/perceptual signoff fabricated. R1 fix branch must now absorb this merge and retain portable coordinate tests plus repository entrypoint tests.
