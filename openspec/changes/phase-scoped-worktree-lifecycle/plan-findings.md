# Plan Findings

## Iteration 1

<!-- Date: 2026-08-15 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | consistency | critical | The design required session-scoped release, but the registry schema forbade `session_id`, used a different lifecycle-mode field, and the CLI omitted `release-session`. | Standardized `lifecycle_mode`; added nullable `session_id`, exact session release, exit/output semantics, and contract-fixture tasks. |
| 2 | feasibility | critical | Owner equality did not fence an expired zombie that resumed under the same owner, and release-before-teardown allowed another owner to acquire a worktree that the prior owner could then remove. | Added a single-acquisition `lease_id`, boundary assertions, new-id-on-reacquire, and owner/token-checked disposal holding the registry lock through Git removal. |
| 3 | feasibility | critical | Markdown-only skill edits could not implement the promised background renewal and guaranteed finalization behavior. | Defined portable `worktree_lifecycle.py` plus executable `phase_lifecycle.py` controller boundaries, process-level tests, session-hook reuse, and package scopes. |
| 4 | completeness | high | Failed dirty/non-durable work could become idle and be silently adopted; teardown also treated a pushed-but-unmerged proposal as unsafe. | Added `recovery_required` quarantine and explicit adoption; safety now checks dirtiness/submodules and remote reachability, not merge-to-main status. |
| 5 | consistency | high | Delivery rules disagreed about missing markers and whether implementation plus plan refinements was mixed. | Added an ordered truth table: missing optional marker warns, missing primary evidence blocks, a governing base plan yields implementation, and no base plan plus a new head plan yields mixed. |
| 6 | testability | high | Classifier contracts could not serialize diff completeness, base/head SHAs and state, marker warnings/status, unknown paths, or auditable author-vendor evidence. | Expanded the classification schema and exhaustive fixture/test tasks; unverified vendor claims now take conservative independent-review routing. |
| 7 | consistency | high | The merge-plan definition was declared immutable while live reclassification had nowhere to persist, and operator disposition lacked an interface contract. | Kept the discovery snapshot immutable, added `state.latest_delivery_classification`, and specified actor/stage/rationale/timestamp override plus SHA revalidation. |
| 8 | consistency | high | Added deltas coexisted with active requirements that still required permanent planning pins, proposal-worktree reuse, package pins, and unconditional OpenSpec cleanup. | Replaced those exact active requirements under `MODIFIED Requirements` and retained new concerns only as added requirements. |
| 9 | feasibility | high | The promised shared registry interpreter had no module/package path and would be absent from the coordinator runtime image. | Located it in `skills/shared/worktree_lifecycle.py`, added install/container import contracts, Dockerfile scope, and source/container tests. |
| 10 | parallelizability | high | Two active changes write the same merge and validation paths, but prose coordination did not stop parallel dispatch. | Added mandatory baseline-SHA/rebase no-dispatch gates and package inputs for `add-merge-plan-orchestration` and `validate-feature-findings-gate`. |
| 11 | completeness | high | Fresh-description autopilot could not acquire before PLAN because change-id, branch, and worktree bootstrap were unspecified. | Defined deterministic pre-mutation change-id resolution, continuous implementation-branch setup, persisted fenced identity, and operator escalation on ambiguous IDs. |
| 12 | testability | medium | Schema checks only validated metaschemas, scenario identifiers were overloaded, and integration gates omitted the promised regression/static/diff coverage. | Added representative format/reference fixture tasks, targeted regression/static/mypy/diff gates, semantic requirement names, and an unambiguous legacy-cleanup scenario name. |

### Quality Checks

- `openspec validate phase-scoped-worktree-lifecycle --strict`: pass.
- Work-package schema, references, DAG, and lock-key validation: pass.
- Architecture package scope/lock overlap validation: pass.
- Draft 2020-12 schema self-validation: pass.
- Representative v2 registry, delivery-classification, and cross-file
  merge-plan instances with reference resolution and date-time format checking:
  pass.
- `git diff --check`: pass.
- Every requirement has success and failure/edge coverage; corrupt registry,
  expired writer, disposal race, quarantine, missing marker, incomplete evidence,
  and operator override paths are explicit.
- Task/spec/contract/design traceability was updated for every finding.

### Parallelizability Assessment

- Independent implementation package roots: 2 (`wp-registry`, `wp-pr-delivery`
  after its external baseline gate).
- Sequential chains: 4 (`registry -> phase lifecycle -> integration`, `registry
  -> autopilot -> integration`, `registry + PR delivery -> coordinator ->
  integration`, and `PR delivery -> integration`).
- Max parallel width: 3 (`wp-phase-lifecycle`, `wp-autopilot`, and
  `wp-coordinator-projections` after their prerequisites settle).
- File overlap conflicts: none inside the package DAG; the two cross-change
  overlaps are blocked by explicit pre-dispatch baseline gates.

---

## Summary

- Total iterations: 1
- Total findings addressed: 12
- Remaining findings below threshold: none
- Termination reason: threshold met after semantic contract refinement
- Proposal readiness: strict-valid, contract-aligned, testable, and gated for
  safe parallel implementation after the two recorded external baselines land
