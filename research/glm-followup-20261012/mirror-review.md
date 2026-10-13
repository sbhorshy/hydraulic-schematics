# Conditional mirror review (Codex)

GLM implemented; Codex ran the checks independently. Initial review rejected a dimensionless matrix tolerance which accepted doubled scale for a large viewBox, inconsistent SVG mirror metadata, reference-layout mirror loss, and incorrect test fixture keys. Fixed cases now compare transformed source corners, require exact per-instance mirror trace, and reject active mirror references in legacy rule-generated placement.

- Mirror policy/render tests: 68 passed, 33.752 s.
- Scheduler and CLI tests: 20 passed, 19.423 s.
- Entrypoint, coordinate, port, and rotation regressions: 38 passed, 269.962 s.
- This checkpoint predates production registrations, editor integration, and scoped bridge policy. It is not final acceptance of #23/#63.

Temporary full 1# diagnostic: EMP mirror=y, CDF moved to (730,430), CASE x=700; EMP label right, CDF below/drop20. Render and rasterization succeeded; validator retained exactly the old B1=0 failure and removed all false CASE/pressure network contacts. Raw B1=1, B2=24/max3, B3=1.29, B4=10, B5=24. This is a diagnostic, not the final authored seed or delivery claim.
