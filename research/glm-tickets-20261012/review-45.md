# Codex independent review: #45 (2026-10-12)

## Standards
First draft rejected: tests coupled to FOOTPRINT implementation, invented unknown-based line-style rule, wrong catalog type spelling, repository research pointer inside portable source. GLM revision replaces behavior probes with CLI output/guard report, removes extra rule and typo, and keeps existing symbol bytes and engineering roles unchanged. Both catalogs carry identical spring-valve entries. The changed implementation adds one footprint row only; no routing/budget guard changes.

## Spec
Partial, do not close #45. Refuel support existed in baseline. Spring variant now registered from actual SVG 96x142 and port group facts. ECO lacks symbol/dimensions and EMP overflow port authority; connected QD lacks connection-points and has SysML-vs-catalog port-name conflict. These remain blockers for #47 and descendants; rejected inputs are not equivalent to completed registration. Current project without seed is also rejected for ACC/ACV/PG unplaced after prior #46; old #44 engine success is historical only.

## Actually executed by reviewer
- First draft: 6 tests passed /0.421s.
- Revised public-interface probes: 4 passed /0.829s.
- Same revised tests copied onto isolated baseline skill: 1 FAIL +1 ERROR (missing spring registration), 2 passes /0.449s; exit1. This is an after-the-fact baseline comparison, not a claim of test-first execution.
- Entire test_entrypoints module: 13 passed /25.715s.
- check_library: exit0 (existing connected-QD whitelist INFO retained).
- Actual project CLI: exit1, ACC-001/ACV-001/PG-001 unplaced; no KeyError.
- Both catalog entries exact equality: passed.

Execution split: GLM edited via zcode-bridge; Codex ran tests independently because ZCode Bash permission client absent. This is not engineering/perceptual approval or a full selftest rerun.
