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

---

## Iteration 2

<!-- Date: 2026-08-15 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | correctness | critical | An expired checkout could be ordinary-acquired after a crash without proving its preserved state safe. | Required a locked expired-takeover assessment of cleanliness, submodules, remote durability, and process evidence; unsafe or indeterminate entries enter recovery quarantine. |
| 2 | security | critical | Session release could clear ownership while leaving an in-flight or dirty checkout immediately adoptable. | Made session release quarantine every preserved matching checkout before clearing its lease; the hook remains non-destructive and explicit finalization is the only clean-disposal path. |
| 3 | contract mismatch | critical | Fresh v1 heartbeats did not define every required v2 lease field or exact post-migration alias behavior. | Defined deterministic owner/token derivation, all timestamps and metadata, one-hour TTL, v1 canonicalization, and explicit owner/token requirements after v2 conversion. |
| 4 | testability | medium | Registry and phase packages omitted their owned shared-controller tests. | Added `test_worktree_lifecycle.py` and `test_phase_lifecycle.py` to their package gates. |
| 5 | architecture | medium | The coordinator package could not write or run its assigned Docker import-contract test. | Added the test path to package scope and verification. |
| 6 | correctness | medium | Absent release and repeated teardown claimed unverifiable same-owner idempotency. | Defined observable no-op semantics without attesting prior ownership. |

### Review Context

- Codex produced 8 schema-valid findings: 3 critical, 3 nits, and 2 positive observations.
- Antigravity, Claude, and Grok timed out; Pi returned invalid JSON, so external quorum was not met and all findings remained unconfirmed.
- The critical findings were nevertheless concrete contract defects and were fixed before review retry.

---

## Iteration 3

<!-- Date: 2026-08-15 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | architecture | critical | Expired takeover referenced process evidence without defining identity, storage, PID reuse, or cross-host behavior. | Added a versioned process-evidence schema and atomic lease-bound records with PID/start/host/controller identity; live and indeterminate evidence quarantines, while stale same-host evidence permits later safety checks. |
| 2 | contract mismatch | critical | Operator delivery overrides were not bound to the base/head state the operator inspected. | Added required base/head SHAs, ruleset version, and canonical-classification SHA-256 digest; any mismatch restores blocked ambiguous routing. |
| 3 | security | critical | Bulk `release-owner` could clear leases without quarantining preserved checkouts. | Applied quarantine-before-clear semantics and per-entry/quarantine counts to exact-owner recovery release. |
| 4 | correctness | medium | Package disposal did not define which remote ref proves an integrated child HEAD durable. | Required parent-feature push first and exact child-HEAD reachability from that expected parent remote ref. |
| 5 | resilience | medium | A crash between Git removal and registry replacement left an unreconciled live orphan entry. | Made exact owner/lease repeated teardown reconcile the one-sided missing-checkout state and process evidence. |
| 6 | contract mismatch | medium | Explicit recovery adoption did not define its complete schema-v2 lease result. | Defined every manual `RECOVERY` lease field, TTL/timestamps, state clearing, output, and conflict exits. |

### Review Context

- The second retry again had no valid external vendor result; Codex supplied 3 critical blockers, 3 nits, and 2 positive observations.
- All six actionable findings were incorporated before the next convergence attempt.

---

## Iteration 4

<!-- Date: 2026-08-16 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|---|---|---|---|
| 1 | security | critical | Same owner/lease retries did not bind the live controller, allowing two resumed controllers to pass fencing checks concurrently. | Added `controller_instance_id` to automatic leases, exact-triple assertions, same-controller-only retry, parent-only renewal, and a separate resume transition that rejects live or indeterminate prior evidence. |
| 2 | durability | critical | Expired takeover could not identify the authoritative remote ref, especially for package worktrees whose durable boundary is the parent feature ref. | Added entry-level remote/ref identity, canonical remote URL hashing, package-parent targets, refresh-outside-lock plus generation revalidation, and stored-target-only takeover/disposal checks. |
| 3 | security | critical | Process evidence keyed only by client-supplied lease id could collide across registry entries. | Keyed evidence by a versioned length-prefix encoding of entry identity plus lease, added entry identity to the evidence schema, and required exact entry/owner/lease/controller validation before every evidence operation. |
| 4 | correctness | critical | A pre-existing unleased or legacy entry bypassed safety assessment and was acquired immediately. | Added atomic setup-and-acquire publication plus entry generations; every separately visible unleased entry now uses full durability, cleanliness, and prior-process assessment or enters quarantine. |
| 5 | security | critical | Recovery adoption after owner/session release could race a still-running former controller because release discarded its evidence. | Added durable recovery context, preserved matching evidence on quarantine release, required stale same-host proof for normal adoption, and isolated missing/cross-host handling behind an audited force-adopt command. |
| 6 | resilience | critical | Autopilot clean teardown on ESCALATE/exception left no defined way to resume because state lived in the removed checkout. | Moved resumable run state outside disposable worktrees, added finalization-intent and checkout-state reconciliation, and specified verified durable-ref recreation with a new controller-bound lease. |
| 7 | security | critical | Operator disposition could override a clear implementation classification to proposal and bypass implementation gates. | Schema- and command-constrained overrides to the latest ambiguous classification, enforced selected/effective-stage equality, and required live reclassification before disposition and execution. |
| 8 | determinism | high | “Canonical classification digest” did not define a byte-level algorithm. | Defined `pr-delivery-v1+jcs-sha256`: semantic projection excluding only `classified_at`, UTF-8 byte sorting for set arrays, no Unicode normalization, RFC 8785 JCS, lowercase SHA-256, and a fixed Unicode-aware fixture. |
| 9 | testability | high | Oversized tasks and incomplete gates hid controller, install-hook, merge-script, formatting, and external-baseline failures. | Split lifecycle, routing, and resume work into test-first M/S units; added executable ancestry gates, missing suites, Ruff format checks across all changed surfaces, and narrowed integration write scope. |

### Review Context

- Three independent read-only refinement passes converged on the controller,
  durability, recovery, autopilot-resume, override, digest, and gate changes.
- The persisted autopilot loop state intentionally remains `ESCALATE`; this
  refinement resolves the recorded blockers but does not claim a new review
  quorum or authorize implementation.

### Quality Checks

- Strict OpenSpec validation: pass.
- Work-package schema, references, DAG, lock, and scope-overlap checks: pass.
- Architecture parallel-zone validation: pass.
- All change-local Draft 2020-12 schemas self-validate: pass.
- Representative registry, external autopilot recovery, clear-classifier,
  ambiguous-override, and selected-stage-mismatch instances validate with
  cross-file reference resolution and date-time format checking: pass.
- `git diff --check`: pass after session-log normalization.

### Parallelizability Assessment

- Independent roots: 2 (`wp-registry` and baseline-gated `wp-pr-delivery`).
- Sequential chains: 3 (`registry -> phase lifecycle -> autopilot ->
  integration`, `registry + PR delivery -> coordinator -> integration`, and PR
  delivery direct to integration).
- Maximum parallel width: 2 after controller propagation made autopilot depend
  on the phase-lifecycle package.
- Intra-change file and lock overlaps: none; cross-change paths are protected by
  executable recorded-SHA ancestry gates before dispatch.
