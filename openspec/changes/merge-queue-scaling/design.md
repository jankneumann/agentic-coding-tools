# Design: Merge Queue Scaling

**Change ID**: `merge-queue-scaling`

## Architecture Overview

```
                    ┌─────────────────────────────────┐
                    │   /merge-pull-requests skill     │
                    │   (interactive triage, Gate 1)   │
                    └──────────────┬──────────────────┘
                                   │ detect_merge_backend()
                    ┌──────────────┼──────────────────┐
                    ▼              ▼                    ▼
          ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
          │ Coordinator  │ │ GitHub       │  │ Direct       │
          │ Train        │ │ Merge Queue  │  │ Merge        │
          │              │ │              │  │              │
          │ compose_train│ │ gh pr merge  │  │ gh pr merge  │
          │ partitions   │ │ --merge-queue│  │ --squash     │
          │ affected CI  │ │              │  │              │
          └──────┬───────┘ └──────┬───────┘  └──────┬───────┘
                 └────────────────┼──────────────────┘
                                  ▼
                    ┌─────────────────────────────────┐
                    │       Post-Merge Pipeline        │
                    │                                   │
                    │  1. Emit merge event (metrics)    │
                    │  2. Auto cascading rebase         │
                    │  3. CI monitoring (rollback)      │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────┼──────────────────┐
                    ▼              ▼                    ▼
          ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
          │ Metrics      │ │ Auto Rebase  │  │ Auto Revert  │
          │ Collector    │ │              │  │              │
          │              │ │ refresh PRs  │  │ revert merge │
          │ local log    │ │ w/ overlap   │  │ if CI fails  │
          │ + coordinator│ │              │  │              │
          └──────────────┘ └──────────────┘  └──────────────┘
                                   │
                    ┌──────────────┼──────────────────┐
                    ▼                                   ▼
          ┌──────────────────────┐  ┌──────────────────────┐
          │ Merge Watcher        │  │ Merge Watcher        │
          │ (Coordinator Task)   │  │ (/loop fallback)     │
          │                      │  │                      │
          │ asyncio background   │  │ single-pass script   │
          │ auto-rebase          │  │ invoked periodically  │
          │ auto-rollback        │  │ by Claude /loop       │
          └──────────────────────┘  └──────────────────────┘
```

## Design Decisions

### D1: MergeBackend protocol for transport-agnostic orchestration

**Decision**: Introduce a `MergeBackend` protocol in the merge-pull-requests skill that abstracts the merge execution strategy. Three implementations: `CoordinatorTrainBackend`, `GitHubQueueBackend`, `DirectMergeBackend`. Selection is automatic via `detect_merge_backend()`.

**Rationale**: The skill currently hardcodes `gh pr merge` calls. Adding coordinator train support as another code path would create a tangle of if/else branches. A protocol-based approach keeps each merge strategy isolated and testable. This mirrors the existing pattern in the codebase (e.g., `DatabaseClient` protocol in `db.py`, `GitAdapter` protocol in `git_adapter.py`).

**Detection order**: (1) Coordinator available + `CAN_QUEUE_WORK` → `CoordinatorTrainBackend`; (2) GitHub merge queue enabled (detected via repo settings or prior merge queue response) → `GitHubQueueBackend`; (3) fallback → `DirectMergeBackend`.

**Rejected alternative**: Single implementation with feature flags. Simpler initially but harder to test each path in isolation. The protocol approach pays for itself immediately in test coverage.

### D2: Post-merge pipeline as composable hooks

**Decision**: After each merge, run a pipeline of post-merge hooks: `emit_merge_event()` → `auto_cascade_rebase()` → `monitor_ci_for_rollback()`. Hooks are independent — a failure in auto-rebase doesn't block CI monitoring.

**Rationale**: These three post-merge actions (metrics, rebase, rollback) are logically independent. Making them composable hooks means:
- Each can be tested in isolation
- Each can fail without blocking the others
- New hooks can be added later (e.g., notification, spec sync)
- The watcher reuses the same hooks for background operation

**Rejected alternative**: Monolithic post-merge handler. Simpler but couples three independent concerns. A failure in rebase would skip rollback monitoring.

### D3: Auto-rebase rate limiting

**Decision**: After a merge, auto-rebase at most `MAX_AUTO_REBASE_PER_MERGE` (default 5) PRs. If more PRs need refresh, process the highest-priority ones and log the remainder for the next merge cycle.

**Rationale**: A merge that touches `package.json` or `pyproject.toml` could make 50+ PRs stale. Refreshing all of them simultaneously would trigger 50 CI runs, exhausting the GitHub API quota and CI runner pool. The rate limit ensures bounded CI load per merge event.

**Configurable**: Via environment variable `MERGE_AUTO_REBASE_LIMIT`. Set to 0 to disable auto-rebase entirely (operator manual mode).

### D4: Auto-rollback attribution via file overlap

**Decision**: When main CI fails after a merge, attribute the failure to the most recently merged PR whose changed files overlap with the failing test's file paths. If no overlap is found, do NOT auto-revert — flag for operator investigation.

**Rationale**: File overlap is a coarse but safe heuristic. False positives (revert a PR that didn't cause the failure) are worse than false negatives (don't revert, let operator investigate). By requiring file overlap, we avoid reverting PRs that are clearly unrelated to the failure.

**Monitoring window**: Poll main CI for `ROLLBACK_MONITOR_MINUTES` (default 15) after each merge. After the window closes, the merge is considered stable.

**Rejected alternative**: Revert the most recent merge unconditionally. Simpler but dangerous — a flaky test could trigger revert of a perfectly good PR. The file overlap check prevents this.

### D5: Merge watcher as coordinator background task

**Decision**: The background merge watcher is a new asyncio task in the coordinator's startup lifecycle (alongside the existing watchdog task). It runs `compose_train` periodically and monitors post-merge CI for rollback triggers.

**Rationale**: The coordinator already has a background task infrastructure (`watchdog.py`). Adding the merge watcher as another task keeps the architecture consistent. The watcher has access to the coordinator's database, audit trail, and merge queue — no need for external state.

**Fallback**: When no coordinator, the watcher's single-pass logic is exposed as `merge_watcher_tick()` — a function that performs one check cycle and returns. The operator can invoke this via Claude's `/loop` command (e.g., `/loop 5m python3 scripts/merge_watcher.py tick`).

### D6: Metrics schema and storage

**Decision**: Merge events are structured JSON objects stored in two locations: (1) a local JSONL file at `docs/merge-logs/metrics.jsonl` (always available), and (2) the coordinator's audit service (when available). The coordinator exposes aggregated metrics via `/merge-train/metrics`.

**Rationale**: Local JSONL ensures metrics are always captured, even without coordinator. The coordinator provides aggregation and querying. This dual-write pattern matches how the session-log skill stores records (local markdown + coordinator handoff).

**Event schema**:
```json
{
  "timestamp": "ISO 8601",
  "event_type": "merge|revert|rebase|eject|train_compose",
  "pr_number": 42,
  "origin": "openspec",
  "strategy": "rebase",
  "backend": "coordinator_train|github_queue|direct",
  "duration_seconds": 12.5,
  "queue_depth": 7,
  "partition_count": 3,
  "train_id": "abc123",
  "success": true,
  "error": null
}
```

## Data Flow

### Interactive Merge Flow (with Coordinator Train)

```
1. Operator invokes /merge-pull-requests
2. Skill detects coordinator → CoordinatorTrainBackend selected
3. Skill discovers PRs, checks staleness, analyzes comments (existing steps)
4. Operator selects "Merge" for a PR
5. Backend calls compose_train(feature_id) if not already in train
6. Backend polls train status: QUEUED → SPECULATING → SPEC_PASSED
7. Backend calls merge_partition() for the ready partition
8. Post-merge pipeline runs:
   a. emit_merge_event() → JSONL + coordinator audit
   b. auto_cascade_rebase() → refresh up to 5 overlapping PRs
   c. monitor_ci_for_rollback() → poll main CI for 15 min
9. If CI fails: auto-revert → emit revert event → notify operator
10. Skill presents next PR (re-checked for staleness)
```

### Background Watcher Flow

```
Every MERGE_WATCHER_INTERVAL seconds (default 60):
1. Check for queued entries → compose_train() if any
2. Check for recently merged entries → monitor_ci_for_rollback()
3. Check for stale queued PRs → auto_cascade_rebase()
4. Emit watcher heartbeat event
```

## Migration Strategy

### Phase 1: Foundation (this change)
- MergeBackend protocol + 3 implementations
- Post-merge hook pipeline
- Auto cascading rebase
- Auto rollback with CI monitoring
- Merge throughput metrics
- Background merge watcher

### Phase 2: Enhancement (follow-up)
- Kanban-viz dashboard for metrics
- Stacked-diff wiring in merge-pull-requests skill
- Affected-test selection in rollback attribution
- Adaptive rate limiting based on CI capacity
