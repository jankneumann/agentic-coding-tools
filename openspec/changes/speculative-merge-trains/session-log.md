# Session Log: Speculative Merge Trains

---

## Phase: Plan (2026-04-09)

**Agent**: claude-code (opus) | **Session**: monorepo-scaling-practices

### Decisions
1. **Full Train in Coordinator** — Speculative merge train logic extends merge_queue.py rather than being a standalone skill. Rationale: single source of truth for merge ordering, reuses existing feature registry resource claims, ACID transactional guarantees for train state transitions.
2. **Full Stacked Diffs** — Work packages land directly on main behind feature flags, not collected on feature branches. Rationale: maximum merge train throughput by reducing merge unit from feature to package; requires feature flag infrastructure.
3. **Priority Eject Recovery** — Failed train entries are ejected and re-queued at lower priority; independent successors continue without re-speculation. Rationale: fastest recovery, avoids O(N) re-speculation cost of full bisect model.
4. **Incremental Build Graph** — Test analysis ships in three phases: import-level (P1) → transitive closure (P2) → fixture-aware (P3). Rationale: ship value early, iterate based on false-positive/negative rates.
5. **Lightweight Feature Flags** — Environment variable override with flags.yaml fallback. Rationale: minimal infrastructure, sufficient for gating incomplete features. No runtime flag service needed initially.

### Alternatives Considered
- Skill-Orchestrated Train: rejected because state split between coordinator and skill reduces transactional safety and complicates audit trail
- Partition-Only Parallelism: rejected because it doesn't address the CI wait-time bottleneck within partitions; leaves the highest-impact optimization (speculative testing) unused
- Stacked within feature branch: rejected because it doesn't reduce branch lifetime or conflict surface for the merge train
- Contract-gated only (no feature flags): rejected because contracts don't gate runtime behavior of partially-landed features
- Bisect-and-rebuild on failure: rejected because CI cost scales with failure position — prohibitively expensive at 50+ entries

### Trade-offs
- Accepted coordinator complexity increase (~800 new lines) over clean separation because transactional safety and unified audit trail are worth the coupling
- Accepted git operations in coordinator (via adapter pattern) over git-agnostic purity because speculative branches are a core train requirement
- Accepted feature flag maintenance overhead over no-flag simplicity because stacked diffs to main require behavior gating for safety

### Open Questions
- [ ] How should the train composition be triggered — periodically (cron), on enqueue, or both?
- [ ] Should speculative refs be pushed to remote (for remote CI) or kept local-only?
- [ ] What is the right priority decrement for ejected entries — fixed (-10) or adaptive?
- [ ] Should the build graph staleness threshold (24h) be configurable per-project?

### Context
The planning session began with a comprehensive discussion of monorepo scaling practices from Google, Meta, Shopify, and GitLab, and how they apply to the agentic coding coordination system at 50–1000 agent scale. The proposal synthesizes three complementary techniques: speculative merge trains (parallel CI), stacked diffs (reduced merge unit), and build graph analysis (affected-test selection). The architecture extends the existing coordinator rather than introducing new services, leveraging PostgreSQL JSONB metadata, lock key namespaces, and the architecture refresh pipeline.

---

## Phase: Plan Iteration 1 (2026-04-09)

**Agent**: claude-code (opus) | **Session**: monorepo-scaling-practices

### Decisions
1. **D8: Post-speculation claim validation** — After speculative ref creation, validate actual file changes match declared resource claims. Prevents unsafe partition assignment from dishonest or incorrect agent claims.
2. **D9: BLOCKED entry recovery lifecycle** — BLOCKED entries can be manually re-enqueued or auto-re-evaluated after 1 hour. Prevents accumulation of permanently stuck entries.
3. **D10: Affected-test traversal bounds** — BFS capped at 10K nodes with fallback to full test suite. Ensures predictable query latency on large graphs.
4. **D11: Train operation authorization** — compose_train requires trust level 3+, eject requires ownership or level 3+. Prevents unauthorized train manipulation.
5. **Scope separation: merge_train_types.py** — Extracted shared data types from merge_queue.py into merge_train_types.py to resolve write-scope overlap between wp-contracts and wp-train-engine.
6. **Fail-closed feature flags** — Reject any FF_* env var not declared in flags.yaml, preventing injection of undeclared flags.
7. **Git adapter injection prevention** — Ref name regex validation + shell=False exclusively. Prevents command injection via branch names.

### Alternatives Considered
- New merge_trains database table (instead of JSONB metadata): rejected to avoid migration complexity, but noted that BTREE indexes on JSONB paths are needed for performance
- Auto-compute resource claims from git diff at enqueue time: rejected because it couples coordinator to code-to-lock-key mapping

### Trade-offs
- Accepted 10K-node traversal bound over unlimited BFS because predictable latency is critical for merge train CI selection; fallback to full suite is safe
- Accepted mandatory claim validation after speculation over trust-based approach because partition safety is a security boundary, not just a convenience

### Open Questions
- [ ] How should the train composition be triggered — periodically (cron), on enqueue, or both?
- [ ] Should speculative refs be pushed to remote (for remote CI) or kept local-only?
- [x] ~~What is the right priority decrement for ejected entries — fixed (-10) or adaptive?~~ Fixed at -10 for simplicity.
- [ ] Should the build graph staleness threshold (24h) be configurable per-project?

### Context
Iteration 1 addressed 15 findings from a structured self-review across security, performance, parallelizability, and assumptions dimensions. Key fixes: added 7 new spec requirements (authorization, ref security, claim validation, BLOCKED recovery, performance bounds), extracted merge_train_types.py to resolve wp-contracts/wp-train-engine scope overlap, added 6 new tasks (2.5-2.6 claim validation, 2.9-2.10 BLOCKED recovery, 2.13-2.14 crash recovery, 4.6 static analysis, 5.8 graph freshness trigger), and upgraded JSONB indexing strategy from GIN-only to GIN+BTREE.

---

## Phase: Plan Iteration 2 (2026-04-09)

**Agent**: claude-code (opus) | **Session**: monorepo-scaling-practices

### Decisions
1. **Requirement ID index (R1-R13)** — Added explicit requirement IDs and cross-reference index to agent-coordinator spec. Prevents task/spec mismatch as plan evolves.
2. **R12: Automatic Flag Creation** — Added spec requirement for auto-creating feature flags when first stacked-diff package is enqueued. Closes the gap between proposal Feature 4 and the spec.
3. **Scope boundaries documented** — Added explicit "In scope (Phase 1)" vs "Deferred (Phase 2)" section to proposal. DAG scheduling integration explicitly deferred.
4. **Impact section added** — Proposal now has quantified impact claims mapped to success criteria.
5. **Missing failure/edge scenarios** — Added 8 new scenarios across both specs: invalid ref names, empty test files, non-standard test locations, missing modules, relative imports, merge conflicts during speculation, invalid decomposition values, state transition triggers.

### Trade-offs
- Accepted that Phase 1 uses manual merge_priority ordering (not DAG-enforced) for stacked diffs, deferring full DAG integration to Phase 2. This is safe because coordinators already set merge_priority at planning time.
- Accepted fixture-aware test analysis as out-of-scope for Phase 1, documenting that affected-test selection may over-select (run extra tests) for fixture-dependent test patterns.

### Open Questions
- [ ] How should the train composition be triggered — periodically (cron), on enqueue, or both?
- [ ] Should speculative refs be pushed to remote (for remote CI) or kept local-only?

### Context
Iteration 2 addressed 20 findings from a completeness/clarity/consistency/testability review. Key fixes: added requirement ID index for unambiguous cross-referencing, added R12 (automatic flag creation), added Impact and Scope Boundaries sections to proposal, added 8 failure/edge scenarios to specs, clarified state transition triggers, and added invalid decomposition rejection scenario.

---

## Phase: Plan Iteration 3 (2026-04-09)

**Agent**: claude-code (opus) | **Session**: monorepo-scaling-practices

### Decisions
1. **Refresh-architecture RPC contract (HIGH)** — Created `contracts/internal/refresh-architecture-rpc.yaml` defining `is_graph_stale`, `trigger_refresh`, and `get_refresh_status`. Previously task 5.8 had an implicit cross-service orchestration dependency with no defined contract. Server side lives in wp-build-graph (new task 3.8, new file `skills/refresh-architecture/scripts/rpc_server.py`), client side lives in wp-integration (new task 5.8a, new file `agent-coordinator/src/refresh_rpc_client.py`).
2. **git merge-tree conflict detection method** — Task 2.4 now specifies dual detection (exit code AND stderr parsing), required git 2.38+ version check on adapter startup, and explicit `MergeTreeResult` return shape. Previously the task referenced `git merge-tree` without specifying how to detect conflicts.
3. **Pipeline refactoring scoped for task 3.7** — Task 3.7 now itemizes the 5 sub-steps required to insert `test_linker` into `compile_architecture_graph.py`. The existing pipeline splits at stage 3 (sequential graph mutations) into stages 4-6 (concurrent read-only), so test_linker must go in the sequential phase as stage 3b, NOT as a drop-in insert. Estimated ~50 LOC.
4. **Cross-partition merge ordering pseudo-code** — Added wave-based merge algorithm to design.md D4 and tightened task 2.12 to reference it. The algorithm: build ready-graph → topo-sort → advance in waves where each wave parallel-merges all currently-ready nodes → rebase partition speculative refs after cross-partition merges. Raises `TrainDeadlockError` if a wave is empty while pending remains.
5. **Feature flag missing-file fallback (LOW)** — Explicit failure-mode table added to design.md D7 and task 4.2: missing flags.yaml → empty registry (not crash), malformed flags.yaml → FlagsConfigError at startup (fail loud), orphaned flag reference → returns False (safe removal), undeclared FF_* env var → ignored with warning (fail closed).

### Alternatives Considered
- Single-task 5.8a in wp-integration for the full RPC implementation: rejected because server and client live in different directory trees (skills/refresh-architecture/ vs agent-coordinator/src/), which would create cross-package write scope conflicts. Split into 3.8 (server) and 5.8a (client) instead.
- Define a long-running RPC service for refresh-architecture: rejected in favor of subprocess-style invocation (`python -m rpc_server <method> <json>`). Simpler, no daemon to manage, aligns with the "skills run as scripts" convention. Failure mode is identical from the client's perspective.
- Put cross-partition merge ordering in task 2.12's description only: rejected because the algorithm has three non-obvious invariants (wave emptiness = deadlock, rebase-after-cross-partition, topo-sort over the entry×partition graph) that need visibility during code review. Pseudo-code lives in design.md D4 for reviewer access.

### Trade-offs
- Accepted +2 tasks (3.8, 5.8a) and +1 new file per side (rpc_server.py, refresh_rpc_client.py) over the simpler "coordinator calls refresh_architecture.sh directly" option. The RPC contract is worth the scaffolding because it (a) documents the failure mode, (b) makes staleness-check cheap without running a full refresh, (c) enables idempotent trigger (no thundering herd).
- Accepted that task 3.7 description is now verbose (5 sub-steps instead of 1 sentence) over the simpler "just register it". The pipeline split between sequential and concurrent stages is non-obvious enough that a naive implementer would get it wrong.
- Accepted that the RPC server runs as a subprocess per call rather than a persistent service. Trade-off: ~50ms startup overhead per call, acceptable because compose_train runs once per train composition (not per entry).

### Open Questions
- [x] ~~How should the train composition be triggered — periodically (cron), on enqueue, or both?~~ Resolved for Phase 1: triggered on enqueue and via periodic sweep (already in scope for wp-integration); documented in data flow section.
- [ ] Should speculative refs be pushed to remote (for remote CI) or kept local-only? (Deferred: Phase 2 when GitHub Actions `merge_group` integration lands.)

### Context
Iteration 3 addressed 5 findings from a focused feasibility review: 1 HIGH (missing cross-service RPC contract for task 5.8), 3 MEDIUM (git merge-tree conflict detection ambiguity, test_linker pipeline refactoring unscoped, cross-partition merge ordering algorithm missing), and 1 LOW (flags.yaml missing-file behavior undefined). All findings resolved with new task 3.8, new task 5.8a, new contract file (refresh-architecture-rpc.yaml), tightened tasks 2.4/2.12/3.7/4.2, pseudo-code added to design.md D4, failure modes table added to design.md D7. plan_revision bumped 3 → 4, contracts revision bumped 1 → 2.
