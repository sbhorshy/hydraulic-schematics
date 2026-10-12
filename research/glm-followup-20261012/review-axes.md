# Independent review of 995e963…27d826b

GLM implements changes; Codex owns acceptance. Reviewers inspected a pinned, read-only checkout. Known pending default-B1 diagnostic compatibility and unittest case-report parsing fixes were excluded to avoid duplicate findings.

## Standards

**Documented standard violation — P2:** mirror_policy.py hashes port_kind, but the catalog field is kind. references/symbol-library.md defines ports[].kind (flow/body_tap); rendering-rules.md requires a port-contract change to invalidate registration. Adding kind=body_tap to a registered pump port leaves its digest and permission unchanged. Hash the real field and verify the registrations.

No additional actionable judgement-call smells.

## Spec

**Implemented-looking but incorrect behavior — P2:** the editor releases mutation controls before its asynchronous authoritative layout refresh finishes. During that window layoutIndex is null; M treats missing state as none and sends x after a preceding x or y, contrary to the documented none→x→y→none cycle. Failed refresh leaves this indefinitely. Hold mutation controls until a successful refresh and handle refresh failure explicitly.

No additional core omissions or unrequested scope creep identified.

Standards: 1 finding (P2). Spec: 1 finding (P2). Both findings are resolved: the real kind field now participates in registration, and editor mutations remain disabled until authoritative layout refresh completes. Codex verified both catalogs and ran 15 real Chrome checks including delayed and failed refresh. A subsequent read-only GLM-5.3-Flash review confirmed both fixes with no remaining finding; no source changes were made during that review.
