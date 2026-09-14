# Change Context: add-decision-choices-ledger

<!-- 3-phase incremental artifact. Phase 1 (this): matrix skeleton, Files Changed and
     Evidence = "---". Phase 2: Files Changed populated. Phase 3: Evidence filled. -->

## Requirement Traceability Matrix

| Req ID | Spec Source | Description | Contract Ref | Design Decision | Files Changed | Test(s) | Evidence |
|--------|------------|-------------|-------------|----------------|---------------|---------|----------|
| skill-workflow.1 | specs/skill-workflow/spec.md | Choices ledger artifact pair (choices.json source of truth + rendered choices.md, codeviz header, optional artifact) | --- | D1, D4, D8 | --- | test_schema.py::test_ledger_schema_valid, test_schema.py::test_header_required_fields, test_artifact_registration.py | --- |
| skill-workflow.2 | specs/skill-workflow/spec.md | Independent read-only choices audit (writes confined to ledger pair, always exit 0) | --- | D6, D7 | --- | test_readonly_posture.py::test_writes_confined_to_ledger_pair, test_readonly_posture.py::test_exit_zero_on_adverse_verdicts | --- |
| skill-workflow.3 | specs/skill-workflow/spec.md | Choices ledger entry content (choice/scenario/gap/reach/verdict/confidence/provenance, stable_id, cross-ref or self_reported false) | --- | D3, D5 | --- | test_ledger.py::test_stable_id_idempotent, test_cross_reference.py::test_unreported_decision_flagged | --- |
| skill-workflow.4 | specs/skill-workflow/spec.md | Least-confident-first ranking enforced by the renderer | --- | D2 | --- | test_renderer.py::test_ranking_ascending_confidence | --- |
| skill-workflow.5 | specs/skill-workflow/spec.md | Choices audit workflow integration (non-blocking hook, needs-user surfaced at existing gates) | --- | D6 | --- | test_hooks.py::test_hook_non_blocking, test_hooks.py::test_needs_user_surfaced_at_gate | --- |

## Design Decision Trace

| Decision | Rationale | Implementation | Why This Approach |
|----------|-----------|----------------|-------------------|
| D1 | Separate decision-choices schema, not an extension of review-findings | --- | review-findings validator hard-requires axis/severity; decision entries are intent-anchored, not code-anchored |
| D2 | choices.json is source of truth; choices.md rendered from it | --- | Single writer makes ranking and header requirements unit-testable; pure-Python renderer preserves the host-assisted invariant |
| D3 | Content-derived stable_id | --- | Re-audits stay idempotent and entries are stably referenceable from gate presentations |
| D4 | Artifact header copied verbatim from prioritize-proposals module | --- | Shared helper does not exist yet; verbatim copy makes the eventual migration a no-op on the on-disk format |
| D5 | Cross-reference-only linkage; never write back to session-log or docs/decisions | --- | Those files are producer-owned and CI-diff-enforced; writing there breaks the deterministic drift gates and the read-only auditor principle |
| D6 | Non-blocking by construction; needs-user surfaces at existing gates | --- | Audit that can block starts optimizing for a clean report; existing gates already have the deferred-tasks surfacing pattern |
| D7 | Auditor dispatched as read-only sub-agent; harness-side script persists the ledger | --- | Keeps LLM calls out of skill Python (host-assisted invariant) and file writes out of the LLM's hands |
| D8 | Artifact registered optional with requires [tasks] | --- | Matches session-log posture: valuable when present, never load-bearing for validation or archive |

## Coverage Summary

- **Requirements traced**: 5/5
- **Tests mapped**: 5 requirements have at least one test
- **Evidence collected**: 0/5 requirements have pass/fail evidence
- **Gaps identified**: ---
- **Deferred items**: ---
