# Full F failure diagnosis A (read-only)

Fixed integration `c215799dd606ca2c4c55663c1c6c79eb5d22e95a`, verified clean before/after. Executed exactly once, from canonical scripts:

`python -m unittest test_route_terminals test_dangling_ports test_port_geometry test_topology_reconciliation test_priority_valve_leads test_route_pruning -v`

Complete combined stdout/stderr: `diagnose-full-a.log` (not truncated). Result: **59 tests / 272.964s / exit1 / 6 FAIL / 0 ERROR**. Module totals: route_terminals4pass; dangling_ports19pass; port_geometry6pass+5fail; topology_reconciliation18pass+1fail; priority_valve_leads4pass; route_pruning2pass. Machine summary: diagnose-full-a-summary.json.

All six observed failures are old-coordinate test injection/expectation mismatches after the root-coordinate migration; no production regression is demonstrated by this shard. No source was changed and no test was rerun. No junction/readback or full suite execution.

| Failing method | Exact source locations under `.agents/skills/hydraulic-schematic/scripts/` | Observed failure | Diagnosis / intended unchanged assertion |
| --- | --- | --- | --- |
| `PortGeometryCLI.test_actual_nested_svg_transform_is_used_for_ports_and_pipes` | `test_port_geometry.py:143` injection;147 assertion | actual `[685,523]` vs expected `[655,523]` | Test adds old sheet `translate(30,0)` on top of already-root650, then5. Keep intended nested +5/−7 transform and expected655/523; remove obsolete30 injection. |
| `PortGeometryCLI.test_boundary_coordinate_does_not_exempt_a_body_crossing` | `test_port_geometry.py:78`–79 point string;84 assertion | `finding.anchor=None` vs `paths[1][0->1]` | Injected first/last620/820 no longer touch actual pressure_out650 / PF.inlet850. `endpoint_checks.py:110` recognizes only actual terminal contact, so `:134` has no connected context. Migrate injected x values+30, preserving original root expected segment850→950 at line85 and connected-edge assertion; do not weaken production attribution. |
| `PortGeometryCLI.test_connection_cannot_cross_an_unrelated_reservoir_body` | `test_port_geometry.py:102`–103 points;107 assertion | `finding.anchor=None` | Same endpoint mismatch620/820 vs650/850 disconnects negative-route provenance. Migrate all injected x values+30 so source/target stay connected and reservoir crossing remains the deliberate defect. Keep path anchor, pressure_out and >200 penetration assertions. |
| `PortGeometryCLI.test_six_pixel_foldback_has_v3_connection_location` | `test_port_geometry.py:91` points;97 assertion | actual foldback position `[634,530]` vs `[670,530]` | Current source endpoint650 then injected640→634 creates a different reversal. Intended20-unit departure and6-unit tail use670→664. Keep expected670, not change assertion to634. |
| `PortGeometryCLI.test_visible_endpoint_gap_fails_with_port_and_input_location` | `test_port_geometry.py:53` injected622;62 distance assertion | distance28 vs2 | Actual source port already650. Intended2px gap is652, not622. Keep distance2 and port/anchor assertions. Stale comment explicitly says before canvas shift. |
| `TopologyCLI.test_contiguous_split_and_bridge_fragments_remain_one_connection` | `test_topology_reconciliation.py:142`–143 fragment points;146 arc;150 assertion | V10 actual onlyEDP, unattached620/820 | Split fixture still uses620→735 /745→820 and arc735→745. Physical root endpoints now650/850. Migrate fragments and arc x+30 (650→765 /775→850; M765…775); retain single logical connection /3edges /noV10 assertion. |

Related green tests still contain other legacy literal x injections in these same files (e.g. port_geometry68–69 and topology_reconciliation111,123–124,167,189,208). They did not fail in this run, but implementer should preserve each test's intended physical geometry when auditing migration, rather than rely on a different manufactured failure to satisfy a broad negative assertion. This is a static observation, not an additional confirmed runtime failure.

The successful controls include scaled nonzero-origin symbols in all4rotations, mutated actual instance transforms, real terminal routes, CSS/visibility/port-disclosure gates, current topology controls, priority-valve lead widths and route defaults. Remaining full-F17FAIL/5ERROR outside this shard belong to the other assigned diagnosis; this shard accounts for6FAIL and none of5ERROR.
