# Implementation Findings

## Iteration 1

<!-- Date: 2026-09-01 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | bug | critical | Delegated marker/state paths assumed the checkout `.git` entry was a directory, so linked managed worktrees could not dispatch or recover correctly. | Moved generation markers to the worktree-owned `.supervised-dispatch/<change-id>/` directory, ignored that runtime directory, and added linked-worktree regression coverage. |
| 2 | bug | high | Independent acknowledge/heartbeat/checkpoint mutations could overwrite each other under concurrent host threads. | Serialized checkpoint transitions with an OS file lock and added concurrent mutation coverage. |
| 3 | edge-case | high | A hard termination between marker creation and claimed-checkpoint persistence could leave an orphan exclusive marker. | Persisted the claim before marker creation, made marker persistence durable, and rolled back the claim on creation failure. |
| 4 | edge-case | high | Re-entry after a callback crash or after terminal persistence could replay the callback or its roadmap side effects. | Added a durable result/application journal with ordered callback, terminal, and effect states, plus crash-recovery tests. |
| 5 | bug | high | Authorized parked continuation metadata was discarded before a stale-generation takeover could inherit it. | Preserved continuation through active generations and removed it only on terminal completion. |
| 6 | workflow | high | One isolation-resolver failure aborted preparation for every otherwise valid peer in the ready batch. | Converted each independent resolution failure into a bounded correlated result while continuing to prepare valid peers. |
| 7 | bug | high | Scheduler scope inputs accepted traversal, absolute, backslash, drive-prefixed, and internally overlapping package declarations. | Canonicalized and fail-closed scope/lock inputs; validated package IDs, dependencies, cycles, and internal scope conflicts before concurrency admission. |
| 8 | bug | high | Success and parked results could reference arbitrary or stale loop-state files without proving the child commit or state semantics. | Required the canonical per-change loop-state path, exact worktree commit, SHA-256 digest, and outcome-consistent semantic state before apply. |
| 9 | edge-case | high | Branch/path isolation was checked during preparation but could drift before child entry or result application. | Revalidated containment, exact branch, and commit at entry and apply boundaries. |
| 10 | edge-case | medium | Unbounded or malformed owner nonces could expand checkpoint state and weaken correlation validation. | Restricted owner nonces to the bounded launch-token alphabet and length. |
| 11 | workflow | medium | Additive router context could overwrite orchestrator-owned dispatch identity fields. | Rejected reserved dispatch keys in additive context while preserving non-reserved router fields unchanged. |
| 12 | bug | medium | Runtime checkpoint validation accepted unknown attempt fields and insufficiently bounded nested context. | Enforced a frozen strict attempt schema in runtime and both published checkpoint schema copies. |
| 13 | workflow | medium | The design/spec text claimed an `execute_roadmap()` opt-in flag although the implementation exposes separate prepare/apply entry points. | Corrected the proposal, D1, rollback, and supervise delta to describe the actual additive API without changing legacy execution. |
| 14 | edge-case | medium | Checkpoint writes were not crash-durable and could replace valid state with a partial write. | Switched to same-directory temporary writes, file and directory fsync, and atomic `os.replace`; added replacement-failure preservation coverage. |
| 15 | edge-case | medium | Required launched-state fields set explicitly to null passed the initial runtime shape check and later raised `AttributeError` instead of a bounded validation error. | Added a RED null launch-state regression, rejected any present non-mapping generation field, and narrowed validated mappings for deterministic errors. |

### TDD Evidence

- Host/concurrency RED: 2 failures; GREEN: 2 passed.
- Host hardening RED: 6 failures; independent GREEN: 4 passed, with marker-dependent cases assigned to the orchestrator lane.
- Checkpoint RED: 2 failures; GREEN: 13 passed; final type-diagnostic RED: 1 failure; GREEN: 14 passed.
- Scheduler RED/GREEN: 10 failures then 10 passed; one additional internal-scope failure then pass; final 26 passed.
- Documentation contract RED: 1 failure; GREEN: 8 passed.
- Orchestrator focused RED: 6 failures; GREEN: 6 focused, 29 supervised-dispatch, and 14 neighboring orchestrator tests passed.

### Review Availability

- Independent in-repository concurrency and spec reviewers completed.
- External vendor review was attempted during the original implementation review but did not produce usable findings: Pi authentication expired, Antigravity returned invalid JSON, and Grok/Claude timed out.
- The coordinated final re-attempt dispatched Antigravity, Claude Code, Grok, and Pi independently; each timed out after 30 seconds. The four manifests and `external-vendor-status.md` record 0/4 success, and consensus explicitly remains below quorum.

### Spec Drift

The public contract remains a separate two-stage delegated API. OpenSpec prose was corrected to remove the inaccurate claim that legacy `execute_roadmap()` gained an option. Canonical committed loop-state evidence and worktree-owned marker paths are now documented explicitly.

### Quality Checks

- Focused integrated matrix: pass — 145 passed.
- Broad roadmap-runtime, autopilot-roadmap, and supervise suites: pass — 370 passed.
- Ruff over every changed Python implementation/test: pass.
- Mypy: unavailable in the skills venv. A cross-environment diagnostic exposed and drove the null-state fix; afterward only six missing-stub or unchanged-dependency diagnostics remained, so no repository type-check verdict is claimed.
- Strict OpenSpec, work-package schema/DAG/locks/overlap, parallel zones, runtime mirrors, and `git diff --check`: pass.

---

## Summary

- Total iterations: 1
- Total findings addressed: 15
- Remaining findings: none at or above the medium threshold; external review unavailable (0/4)
- Termination reason: threshold met; vendor quorum unavailable and explicitly recorded
