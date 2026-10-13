# #60 drawable boundary follow-up acceptance

Dragging previously clamped to the full canvas. With a 1710×1390 canvas, drawable right/bottom 1657/1317 and an 80×80 node, an extreme drag persisted (1630,1310), outside the allowed maximum (1577,1237). The same real Chrome scenario now persists (1577,1237); the client already sends the bounded delta. Nonzero left/top bounds and grid rounding are also enforced.

The server reuses canonical `drawable_bounds`, preserves the declared edge margin without subtracting it twice, swaps occupied width/height for 90°/270°, and rejects invalid numbers, dimensions and contracts before writing. The frontend clamps during dragging and again after alignment/grid/decimal rounding. Missing bounds disable drag. Manual interference remains writable and visibly red under the existing prototype policy.

## Validation and independent review

- TEAM `team-dc97746c8a834c14809bc0032e641edb`: actual executor model GLM-5.3-Flash; one writer, dependent frontend dispatched only after server integration. Codex reviewed the fixed candidates and submitted structured decisions.
- Server candidate and independent integration: 31 / 31 tests PASS. Final editor candidate and integration: 35 / 35 tests PASS; no skips; source unchanged through checks.
- Codex real Chrome: 6 drag/writeback checks and 15 mirror/refresh race checks PASS. Old implementation fails the same right/bottom test. A root harness expectation for left alignment was corrected: legitimate inward snapping is allowed, so the second leg disables alignment and tests grid/boundary clamping independently. The first leg retains alignment and a real nearby component.
- Review caught GET error handling regressions: null layout / invalid intent disconnected the socket. Fixed candidate independently returns JSON 400 / JSON 500, respectively. Original assertions were retained.
- First frontend test run failed all four new Node cases due to a missing `=>` in the test harness; GLM fixed it and the declared full editor suite was rerun successfully. The failed report is retained.
- Browser execution commit `4468d6cac60ecb6e9fef60ab9ed77bc3c50b2c8c`; accepted frontend candidate `f05a025f22d94c78283e52b876834d288587b6bc`. Exact comparison proves executable HTML/JS and server code unchanged between these versions; only the audited comment differs in HTML. See `evidence/browser-source-binding.json`.

Standards review: allowed files only, canonical coordinate contract reused, original baselines/assets unchanged. Spec review: drag boundaries and write rejection verified against actual file contents and browser requests. No unresolved findings in this bounded follow-up.

## Scope remaining

This is partial progress on #60, which stays open. Rotation alignment guides/selection display retain their prior unrotated-size behavior; human prototype feedback and #61 GUI positioning remain unresolved. No engineering maturity or signoff is inferred. #45/#47 and their dependency chain remain blocked on their existing requirements.

The accepted #23/#63 concept drawing and its 62-crop/110-object readback remain the separately published [drawing acceptance](../glm-followup-20261012/acceptance.md). Editor stress-test screenshots intentionally show invalid manual arrangements and are **not delivery drawings**.

## Reproduction

Controller tests: `python3 -m unittest discover -s tests/repository -p 'test_editor_*.py' -v`.

Browser scripts in `audit/` take a repository directory and an output directory. Run them only on a disposable archive/copy: they intentionally mutate that copy's layout and generated outputs. They use isolated Chrome profiles and dynamically allocated local ports and stop their own processes. Unit/API mocks are disclosed in the test modules; the browser audits use the actual server/render/validation chain.

TEAM integrated commit: `38f890f580123fc9448d1443fe0249afc0e472e7`. Evidence in `evidence/` includes decisions, bound test reports, logs and browser results. Provider usage is not a complete team cost calculation.
