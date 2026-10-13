# Formal-review fixes: independent acceptance and merge

Reviewer/merger assembly39, not fix implementer. Accepted final candidate **3116e3e9b976e4e6b7cc83ff2df40775af70f622**, superseding7640016, and merged into integration as **c215799dd606ca2c4c55663c1c6c79eb5d22e95a**. Worker and integration clean. No further integration source changes by this agent; root can freeze this version for full skill and repository suites.

## Standards findings

S1: reviewed mandatory assembly semantic checks independent of optional jsonschema. Public subprocess test without jsonschema rejects invalid/missing/nonblank label and member structure with ERROR, preserving valid auxiliary membership behavior. S2: renderer requires explicit supported coordinate_system; partial-root layout needs intentional --declare-root repair and geometry/margin/source bytes stay unchanged. Valid legacy SHIFT migration remains available.

Independent merger found an additional path through the original7640016 fix: default migration with explicit unknown_space plus SHIFT30 still overwrote the unknown declaration. Reproduction result retained in review-fix-final-independent-unknown-migration.json. Original implementer repaired the common entry check in3116e3e; all four combinations (SHIFT absent/present and --declare-root absent/present) now reject explicit unknown coordinates without modifying input or an existing output. Root's optimizer handcrafted fixture problem was repaired only by adding its legitimate explicit root declaration; numerical budget assertions unchanged.

Final independent command ran5focused public/regression tests: optional-schema invariants, explicit coordinate repair, both unknown-coordinate migration branches, genuine legacy shift migration and real-sheet optimizer budget. **5PASS/3.789s/exit0**; log review-fix-final-independent-final.log. No full suite run; initial wrong test-method loader attempt was corrected and is not counted as a behavioral failure.

## Spec finding: verified blocker remains open

Read formal-review-spec-obstruction.md, independent evidence and public arrival-23 report. Independently reran read-only check_rotation_obstruction.py; fresh result equals recorded rotation-certificate.json field-for-field. Independently checked actual selected EDP/EMP catalog entries permit0/90/180/270 and allow_mirror=false. Certificate has16combinations, eachF1/Euler0; forbidden reversed-order controlF3/Euler2. NetworkX3.3 independently reports abstract graph planar but fixed-order embedding invalid. Fresh certificate retained as review-fix-final-independent-certificate.json.

Evidence accurately distinguishes abstract graph planarity from fixed physical port ordering; no ports, input topology, budgets, source assets or mirror permission changed. Public report keeps #23's fail0/B1=0 arrival acceptance unfulfilled and does not present a fictitious qualified layout. This is a confirmed open constraint blocker, not a resolved Spec finding or human engineering/perceptual approval. Publication should close only39/42/44/46/49/62 and keep23open/partial as root directed.

No remaining blocker to merging these Standards repairs and accurate obstruction evidence. Full integrated selftest + separate repository integration verification remain root's next step at the exact merge hash above.
