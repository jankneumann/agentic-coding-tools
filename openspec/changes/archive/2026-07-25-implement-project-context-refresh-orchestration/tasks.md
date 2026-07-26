# Tasks: Implement project context refresh orchestration

> Change ID: `implement-project-context-refresh-orchestration`

Tests precede behavior changes. Sizes use the plan-feature attention budget.
Producers, result/manifest/operation models, and durable storage are reused from
ri-04/ri-05/ri-06 — this change adds coordination only.

## 1. Semantic-index adapter (degradable producer)

- [x] 1.1 (S) Write failing tests for `semantic_adapter`: success maps to a
  `SUCCEEDED` `SemanticIndexReference` (operation_id + registry_record_id +
  indexed_revision == requested_revision); an unavailable DB/service and a runtime
  indexing error each map to a non-succeeded reference carrying a bounded fallback,
  never raising.
  **Spec scenarios**: project-context-refresh-orchestration.semantic-degradation
  **Design decisions**: D4
  **Dependencies**: ri-02, ri-06 landed
- [x] 1.2 (M) Implement `semantic_adapter` over `agent-coordinator/src/code_search.py`,
  importing the ri-06 `SemanticIndexReference`/`Fallback` models. Catch import and
  runtime errors and reduce them to a bounded fallback (reuse `_bounded_safe_error`).
  **Spec scenarios**: project-context-refresh-orchestration.semantic-degradation
  **Design decisions**: D4
  **Dependencies**: 1.1

- [x] Checkpoint: run semantic-adapter tests with and without a DB; verify no raise path

## 2. Outcome-decision core

- [x] 2.1 (S) Write failing tests for the terminal-state decision over synthetic
  `ProducerResult` sets + a semantic reference: any required `failed` → FAILED;
  else any `degraded`/required `not-configured` or non-succeeded semantic → DEGRADED;
  else SUCCEEDED. FAILED carries a `SafeError`; others carry none.
  **Spec scenarios**: project-context-refresh-orchestration.runs-all-configured
  **Design decisions**: D5
  **Dependencies**: ri-06 landed
- [x] 2.2 (S) Implement the pure outcome function returning an `OperationState`
  (+ optional `SafeError`), with no store or IO dependency.
  **Spec scenarios**: project-context-refresh-orchestration.runs-all-configured
  **Design decisions**: D5
  **Dependencies**: 2.1

- [x] Checkpoint: run outcome tests; confirm the function is IO-free and total

## 3. Orchestrator drive loop

- [x] 3.1 (M) Write failing tests: the orchestrator opens/reuses one canonical
  operation, `begin_attempt`, records the four ri-05 deterministic producers via
  `run_producer` and the ri-04 architecture result via `ArchitectureAdapter`, all
  **before** attempting the semantic index; a semantic failure leaves every prior
  result intact and finalizes DEGRADED.
  **Spec scenarios**: project-context-refresh-orchestration.runs-all-configured, project-context-refresh-orchestration.semantic-degradation
  **Design decisions**: D1, D2, D3, D4
  **Dependencies**: 1.2, 2.2
- [x] 3.2 (M) Implement `orchestrator.py`: drive producers in order, record each
  result, record the semantic reference, finalize via the outcome function, then
  `write_manifest` + `record_manifest`. Adapter exceptions become bounded `failed`
  results; the loop never propagates a traceback into the operation.
  **Spec scenarios**: project-context-refresh-orchestration.runs-all-configured
  **Design decisions**: D1, D2, D3, D5, D6
  **Dependencies**: 3.1
- [x] 3.3 (S) Add idempotency + no-diff tests: two runs at a fixed revision reuse the
  operation, reuse/verify the semantic reference, produce byte-identical producer
  outputs, and leave the working tree unchanged (manifest lands under gitignored
  `.git-context/`).
  **Spec scenarios**: project-context-refresh-orchestration.no-diff-on-rerun
  **Design decisions**: D2, D6
  **Dependencies**: 3.2

- [x] Checkpoint: run orchestrator tests; diff the tree after two runs (must be empty)

## 4. CLI, boundary, and ownership surface

- [x] 4.1 (S) Write failing tests: `refresh` / `refresh-check` subcommands and a
  `--producer <id>` filter run exactly one producer and record one owner-identified
  result; the command refuses a shared/bare checkout; manifest never touches the
  tracked tree.
  **Spec scenarios**: project-context-refresh-orchestration.independent-producer, project-context-refresh-orchestration.no-main-write
  **Design decisions**: D7, D8
  **Dependencies**: 3.2
- [x] 4.2 (S) Extend `cli.py` with `refresh`/`refresh-check`/`--producer`, wire
  `checkout_policy` refusal, and add `make refresh-project-context` /
  `make refresh-project-context-check` (exit 0 fresh · 2 drift · 1 failed).
  **Spec scenarios**: project-context-refresh-orchestration.independent-producer, project-context-refresh-orchestration.no-main-write
  **Design decisions**: D7, D8
  **Dependencies**: 4.1
- [x] 4.3 (XS) Assert the manifest preserves each producer's `producer_id` + `owner`
  and that unconfigured producers (e.g. `capability`) are omitted, not fabricated.
  **Spec scenarios**: project-context-refresh-orchestration.independent-producer, project-context-refresh-orchestration.capability-follow-up
  **Design decisions**: D1, D8
  **Dependencies**: 4.2

- [x] Checkpoint: run CLI/boundary tests; confirm capability omission is documented

## 5. Documentation + follow-up

- [x] 5.1 (XS) Update `project-context-refresh/SKILL.md`: it now owns cross-producer
  orchestration + manifest emission; document the `refresh`/`refresh-check` surface.
  **Design decisions**: D1
  **Dependencies**: 4.2
- [x] 5.2 (XS) File the `capability` producer follow-up (roadmap item / issue) and
  link it from the proposal's Out-of-Scope section.
  **Spec scenarios**: project-context-refresh-orchestration.capability-follow-up
  **Dependencies**: 4.3

- [x] Checkpoint: full suite green, openspec validate --strict, ruff + mypy clean
