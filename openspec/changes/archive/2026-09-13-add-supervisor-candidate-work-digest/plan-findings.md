# Plan Findings

## Iteration 1

<!-- Date: 2026-09-10 -->

### Findings

| # | Type | Criticality | Description | Resolution |
|---|------|-------------|-------------|------------|
| 1 | consistency | critical | Decision metadata was rejected by canonical supervisor-record schemas and stripped by `cycle_state`, while package scope forbade the required edits. | Fixed: own both schema extensions, sanitizer changes, round-trip tests, locks, and scopes. |
| 2 | feasibility | critical | Candidate/cache/digest outputs participated in the cycle fingerprint and could invalidate their own cache forever. | Fixed: exclude only derived supervisor artifacts and require a two-cycle output-only cache-hit proof. |
| 3 | testability | high | `generated_at`, persisted reuse/cache flags, and wall-clock staleness contradicted byte-identical output. | Fixed: evidence-time generation/staleness, stdout-only diagnostics, and qualified byte reuse. |
| 4 | consistency | high | The candidate artifact risked replacing established gate, ready, blocked, and degraded five-section semantics. | Fixed: candidate-only composable sections; host operational rendering remains authoritative. |
| 5 | completeness | high | Fresh pending ranks were never synchronized into `back_edge`, so rehydration could not satisfy the spec. | Fixed: rank-to-record synchronization and rehydrate round-trip tasks/scenario. |
| 6 | testability | high | Weights, risk direction, exact score coverage, and tie-breaking were unspecified. | Fixed: 3/3/2/1/1 weights, capped staleness, explicit buckets, strict exact-set validation, and `stub_key` tie-break. |
| 7 | correctness | high | Dependency mapping degraded unresolved/cross-roadmap prerequisites to prose and preview/apply had no behavioral test. | Fixed: typed local/external/satisfied resolution, fail-closed unknowns, real apply and stale-SHA tests. |
| 8 | completeness | high | Retained pending/deferred backlog and due deferrals conflicted with dedupe and unchanged early exit. | Fixed: retained-plus-fresh union and pre-fingerprint maintenance/cache-only wake path. |
| 9 | security | high | Provenance excerpts and batches were unbounded and allowed URI, symlink, traversal, secret, and prompt-injection risks. | Fixed: contained UTF-8 regular files only, 2 KiB/64 KiB/20-stub limits, redaction, delimiters, and negative tests. |
| 10 | compatibility | high | Runtime schemas existed only under the archivable change directory. | Fixed: stable runtime schema installation is an explicit contract task and package scope. |
| 11 | consistency | medium | Proposal commands named `cycle_state.py` while the selected design assigned them to `digest.py`; dependency status was stale. | Fixed throughout proposal/design/spec; ri-05/ri-16 recorded complete. |
| 12 | parallelizability | medium | Task/package scopes omitted required state/schema files and the fixture/test order was not executable TDD. | Fixed: revision-2 DAG, contract-first RED/GREEN tasks, exact scopes, and two isolated parallel packages. |

### Quality Checks

- Baseline `openspec validate add-supervisor-candidate-work-digest --strict`: PASS.
- Final strict and work-package checks are recorded after the refinements below.

### Parallelizability Assessment

- Independent package roots: 1 (`wp-contracts`)
- Sequential chains: 2 (`contracts → digest → docs → integration`; `contracts → prompt → docs → integration`)
- Max parallel width: 2 (`wp-digest-module` and `wp-rubric-prompt`)
- File overlap conflicts: none; shared contract and docs packages are explicit synchronization points.

---

## Summary

- Total iterations: 1
- Total findings addressed: 12
- Remaining findings below threshold: none
- Termination reason: threshold met

## Review Fix Revision 4

<!-- Date: 2026-09-10 -->

| Round-2 consensus | Resolution |
|---|---|
| Terminal-only prune could leave a stale digest | Every lifecycle mutation now bypasses unchanged reuse, rebuilds before SENSE, and frees capacity immediately. |
| Staleness source timestamp was undefined | Use the last Git commit timestamp only when tracked artifact bytes match HEAD; otherwise null/degraded; never mtime. |
| Refiner priority contract conflicted | Removed renumbering claim; explicit priority and insertion position are independent. |
| 64 KiB covered evidence but not whole prompt | Bound the complete canonical manifest and fail before dispatch with `oversized:<stub_key>`. |
| Multi-batch and ready-frontier instructions remained | Require one manifest and a strict all-status roadmap/active/archive index. |
| Cached `scored_at` conflicted with maintenance `as_of` | Preserve `generated_at` for cache validation and add `state_updated_at` for lifecycle rebuilds. |
| Multi-file publication and failure retry were underspecified | Add a durable roll-forward journal, digest-last commit marker, startup recovery, and no successful-ledger advance on failure. |
| Digest omitted parts of ranking policy | Emit the penalty cap, risk direction, bucket orders, and tie-breaker in `weights`. |
| Adjacent round-2 ambiguities | Define maintenance-before-overflow precedence, dry-run reporting, archived-completed source, and nullable `suggested_change_id` for `prov:` keys. |

## Manual Review Fix Revision 5

<!-- Date: 2026-09-10 -->

| Round-3 blocker | Resolution |
|---|---|
| Future-dated Git commit could produce negative staleness | Emit null staleness plus `clock_skew:<source_artifact>` degradation; no negative value reaches the formula. |
| Replacement-only journal omitted lifecycle deletions | Journal typed replace/delete operations together; terminal stub/cache deletions, mirror, and digest share one recoverable transaction with per-parent fsync and digest last. |

The two deterministic blockers are fixed in the plan. Automatic PLAN_REVIEW exhausted its configured three-round limit, so resumption remains subject to the recorded escalation gate.
