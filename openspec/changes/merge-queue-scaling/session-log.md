# Session Log: merge-queue-scaling

## Plan — 2026-06-05 (claude_code)

### Summary

Planned the merge-queue-scaling feature: wiring the existing coordinator merge train engine into the merge-pull-requests skill, plus adding auto cascading rebase, auto rollback, and merge throughput metrics. Selected Approach 1 (Skill-Side Orchestration with Coordinator Assist) based on the need for graceful degradation across coordinator/GitHub/solo-dev environments.

### Decisions

- **MergeBackend protocol** — Transport-agnostic merge orchestration via protocol pattern (coordinator train → GitHub queue → direct merge). Mirrors existing db.py and git_adapter.py patterns. Capability: `merge-infrastructure`.
- **Auto-revert immediately** — When main CI breaks, create and merge the revert PR automatically without operator approval. Prioritizes trunk stability over caution. Capability: `merge-infrastructure`.
- **Hybrid execution model** — Sync-point skill for interactive triage + background watcher for auto-rebase/rollback. Watcher runs as coordinator background task with /loop fallback. Capability: `merge-infrastructure`.
- **Post-merge hooks are composable** — Metrics, auto-rebase, and auto-rollback run independently. A failure in one doesn't block the others. Capability: `merge-infrastructure`.
- **Auto-rebase rate limit: 5 PRs per merge** — Prevents CI storms when a widely-overlapping file merges. Capability: `merge-infrastructure`.
- **Rollback attribution via file overlap** — Conservative heuristic to avoid false-positive reverts. No overlap = no auto-revert. Capability: `merge-infrastructure`.

### Alternatives Considered

- **Coordinator-Only Merge Train** (Approach 2) — Rejected because it breaks solo-dev workflow without coordinator. Heavy coupling.
- **GitHub-First with Coordinator Enhancement** (Approach 3) — Rejected because it loses partition-aware parallelism from the existing train engine. GitHub's merge groups don't support lock-key-based partitioning.

### Trade-offs

- **Auto-revert speed vs safety** — Accepted immediate auto-revert over manual approval. Risk: may revert a good PR if a flaky test coincidentally fails in overlapping files. Mitigation: file overlap check reduces false positive risk.
- **Rate-limited rebase vs full rebase** — Accepted refreshing max 5 PRs per merge over all overlapping PRs. Risk: some PRs stay stale longer. Mitigation: background watcher picks up remaining PRs in next tick.

### Open Questions

- Is the existing merge train engine's API stable enough to wire into without modifications?
- Will GitHub's Update Branch API rate limits hold at 50+ PRs/day auto-rebase volume?
- Should the metrics JSONL file be rotated daily or grow unbounded?

### Next Steps

- Run /implement-feature merge-queue-scaling to begin implementation
- Phase 1 (MergeBackend protocol) is the foundation — all other phases depend on it

### Relevant Files

- `openspec/changes/merge-queue-scaling/proposal.md` — Approved proposal
- `openspec/changes/merge-queue-scaling/design.md` — Architecture and design decisions
- `openspec/changes/merge-queue-scaling/tasks.md` — 32 tasks across 7 phases
- `openspec/changes/merge-queue-scaling/specs/merge-infrastructure/spec.md` — Requirements
- `openspec/changes/merge-queue-scaling/work-packages.yaml` — Sequential wp-main package

### Key Discovery

The speculative merge train engine is already fully implemented in the coordinator (archived proposal `2026-04-22-speculative-merge-trains`). All source files exist: `merge_train.py`, `merge_train_types.py`, `git_adapter.py`, `feature_flags.py`, `test_linker.py`, `affected_tests.py`. The gap is purely the skill ↔ coordinator bridge + the three missing capabilities (auto-rebase, auto-rollback, metrics).
