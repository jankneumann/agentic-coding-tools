# Change: add-cross-roadmap-readiness-resolver

> Parent roadmap: `roadmap-supervisor-orchestration` (item `ri-16`, priority 2, effort S)

## Why

Readiness is currently calculated inside one `autopilot-roadmap` process and discarded, while the supervisor maintains a second roadmap-status-only approximation. The repository therefore has no deterministic, checkpoint-aware answer to “what work is executable across all roadmaps now?” and cannot safely project that answer into a materialized queue.

## What Changes

- Move `_get_ready_items` into `roadmap-runtime` as the sole admission-rule definition used by `autopilot-roadmap` and the repository-wide resolver.
- Add a read-only command that scans active roadmap workspaces, reconciles each valid checkpoint as the terminal-state authority, resolves typed `external_depends_on` edges, and returns one globally ranked JSON list.
- Include a deterministic readiness-source fingerprint plus consistency diagnostics, so later projections can detect staleness without consulting wall-clock time, mtimes, learning entries, handoffs, or coordinator queue state.
- Delegate the supervisor's existing `ready` compatibility view to the shared runtime resolver.
- Add regression tests for checkpoint precedence, the ri-17 typed-edge fixture, deterministic output, fail-closed invalid state, ranking, and the one-definition import invariant.

No breaking behavior is introduced. Existing `autopilot-roadmap` call sites retain their function signature, and the supervisor command retains its grouped compatibility shape while consuming the canonical result.

## Non-Functional Requirements

| Attribute | Metric | Target | Verified by (phase) |
|-----------|--------|--------|---------------------|
| Determinism | Byte comparison and source-fingerprint comparison over unchanged files | 100% byte-identical stdout and identical SHA-256 fingerprint | Unit/validation tests |
| Compatibility | Existing targeted autopilot-roadmap and supervise suites | 0 regressions | Implementation and validation |
| Operability | Invalid/mismatched checkpoint fixtures | 100% emit a bounded diagnostic and withhold that workspace | Unit tests |
| Performance | Repository input traversal | One sorted pass over `openspec/roadmaps/*/roadmap.yaml` and at most one checkpoint read per workspace | Code review |

## Approaches Considered

### Approach 1: Shared runtime resolver (Recommended)

Add a small `roadmap-runtime` readiness module containing the single admission helper and repository-wide resolution logic, plus a thin CLI. Both autopilot and supervise import the runtime surface.

Pros:

- Gives readiness one authority and makes all consumers projections.
- Keeps checkpoint reconciliation beside roadmap/checkpoint models.
- Supports deterministic CLI and direct Python callers without network access.

Cons:

- Requires coordinated import-path care because skill scripts are not an installed package.
- Changes three consumer/test surfaces even though the algorithm is small.

Effort: S

### Approach 2: Extend the supervisor command only

Keep `_get_ready_items` in autopilot-roadmap and teach `cycle_state.py ready` to load checkpoints and rank globally.

Pros:

- Fewer files change initially.
- Reuses an existing command entry point.

Cons:

- Retains two readiness implementations and violates the one-definition/shared-authority outcome.
- Places general roadmap semantics inside a supervisor-specific layer.

Effort: S

### Approach 3: Materialize a ready-queue artifact

Write a tracked queue file whenever roadmap/checkpoint state changes and serve it as the readiness answer.

Pros:

- Very cheap reads for dashboards and scheduling.

Cons:

- Creates a second state authority before a trustworthy projection exists.
- Adds writer ordering, crash recovery, and drift repair outside ri-16's scope.

Effort: M

### Recommended

Approach 1 best matches the roadmap rationale: establish a deterministic resolver first so later queue materialization is explicitly a projection. Its modest import changes buy one reusable authority without adding a writer or another durable artifact.

### Selected Approach

Approach 1 is selected under the already-approved `roadmap-supervisor-orchestration` roadmap decision. The refinement additionally makes checkpoint conflicts fail closed and defines staleness from input consistency rather than time, preserving deterministic output.

## Impact

- Affected architecture layers: Execution and Coordination. Trust/Governance behavior is unchanged.
- Affected spec capability: `roadmap-orchestration` (delta in `specs/roadmap-orchestration/spec.md`).
- Runtime: `skills/roadmap-runtime/scripts/`.
- Consumers: `skills/autopilot-roadmap/scripts/orchestrator.py`, `skills/supervise/scripts/cycle_state.py`.
- Tests: `skills/tests/roadmap-runtime/`, `skills/tests/autopilot-roadmap/`, `skills/tests/supervise/`, and the existing plan-roadmap cross-roadmap import.

