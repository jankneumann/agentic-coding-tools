# Tasks: Merge Queue Scaling

**Change ID**: `merge-queue-scaling`

## Phase 1: Merge Backend Abstraction (wp-contracts)

- [x] 1.1 Write tests for MergeBackend protocol — verify interface contract for merge(), get_queue_status(), supports_train() methods across all three implementations
  **Spec scenarios**: merge-infrastructure.1 (backend detection), merge-infrastructure.1 (solo-dev fallback)
  **Design decisions**: D1 (MergeBackend protocol)
  **Dependencies**: None
  **Size**: S

- [x] 1.2 Create `merge_backend.py` — MergeBackend protocol + CoordinatorTrainBackend, GitHubQueueBackend, DirectMergeBackend implementations + `detect_merge_backend()` factory
  **Dependencies**: 1.1
  **Size**: M

- [x] 1.3 Write tests for merge event schema — validate event structure, serialization, JSONL append
  **Spec scenarios**: merge-infrastructure.5 (metrics event emission)
  **Design decisions**: D6 (metrics schema)
  **Dependencies**: None
  **Size**: XS

- [x] 1.4 Create `merge_events.py` — MergeEvent dataclass, emit_event() to JSONL file, emit_to_coordinator() for audit service
  **Dependencies**: 1.3
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 2: Train Integration (wp-train-bridge)

- [x] 2.1 Write tests for CoordinatorTrainBackend — mock coordinator calls, verify compose_train → poll → merge_partition flow, verify fallback on coordinator unavailability
  **Spec scenarios**: merge-infrastructure.2 (train compose), merge-infrastructure.2 (partition merge)
  **Design decisions**: D1 (backend protocol)
  **Dependencies**: 1.2
  **Size**: M

- [x] 2.2 Implement CoordinatorTrainBackend.merge() — call compose_train via coordination bridge, poll train status, call merge_partition when ready, emit merge event
  **Dependencies**: 2.1
  **Size**: M

- [x] 2.3 Write tests for GitHubQueueBackend — mock gh CLI, verify --merge-queue flag, verify fallback to direct merge
  **Spec scenarios**: merge-infrastructure.1 (GitHub queue path)
  **Dependencies**: 1.2
  **Size**: S

- [x] 2.4 Implement GitHubQueueBackend.merge() — use existing `_try_merge_queue()` logic from merge_pr.py, emit merge event
  **Dependencies**: 2.3
  **Size**: S

- [x] 2.5 Wire merge_backend into merge_pr.py — replace direct `_try_merge()` calls with `backend.merge()`, preserve all existing validation logic (approval, CI checks, draft status, conflicts)
  **Dependencies**: 2.2, 2.4
  **Size**: M

- [x] 2.6 Update SKILL.md — document new merge backend selection, train integration, transport detection
  **Dependencies**: 2.5
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 3: Auto Cascading Rebase (wp-auto-rebase)

- [x] 3.1 Write tests for auto_cascade_rebase() — verify refresh-branch calls for overlapping PRs, verify rate limiting (max 5), verify skip for conflicting overlaps, verify no-op when no overlapping PRs
  **Spec scenarios**: merge-infrastructure.3 (auto rebase non-conflicting), merge-infrastructure.3 (rate limiting), merge-infrastructure.3 (conflicting skip)
  **Design decisions**: D3 (rate limiting)
  **Dependencies**: 1.4
  **Size**: M

- [x] 3.2 Implement auto_cascade_rebase() — after merge, compute overlapping PRs via check_staleness, call refresh_branch for non-conflicting overlaps (up to MAX_AUTO_REBASE_PER_MERGE), log conflicting PRs for operator attention
  **Dependencies**: 3.1
  **Size**: M

- [x] 3.3 Wire auto_cascade_rebase into post-merge pipeline — call after each successful merge in merge_pr.py, emit rebase events for each refreshed PR
  **Dependencies**: 3.2, 2.5
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 4: Auto Rollback (wp-auto-rollback)

- [x] 4.1 Write tests for monitor_ci_for_rollback() — mock CI polling, verify breakage attribution via file overlap, verify auto-revert creation, verify no-revert when no overlap, verify monitoring window timeout
  **Spec scenarios**: merge-infrastructure.4 (breakage detection), merge-infrastructure.4 (auto revert), merge-infrastructure.4 (no false positive), merge-infrastructure.4 (monitoring timeout)
  **Design decisions**: D4 (file overlap attribution)
  **Dependencies**: 1.4
  **Size**: M

- [x] 4.2 Implement monitor_ci_for_rollback() — poll main branch CI for ROLLBACK_MONITOR_MINUTES, on failure check file overlap with merged PR, create revert commit if attributed, push and fast-track merge
  **Dependencies**: 4.1
  **Size**: M

- [x] 4.3 Write tests for create_revert_pr() — verify git revert, verify PR creation with explanatory body, verify fast-track merge, verify notification event emission
  **Spec scenarios**: merge-infrastructure.4 (revert PR creation)
  **Dependencies**: 4.2
  **Size**: S

- [x] 4.4 Implement create_revert_pr() — git revert <merge-sha>, create PR via gh, auto-merge the revert PR (bypasses normal queue to unblock trunk), emit revert event
  **Dependencies**: 4.3
  **Size**: M

- [x] 4.5 Wire auto-rollback into post-merge pipeline — call monitor_ci_for_rollback after each merge, run concurrently with auto-rebase (not blocking)
  **Dependencies**: 4.4, 3.3
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 5: Merge Throughput Metrics (wp-metrics)

- [x] 5.1 Write tests for metrics aggregation — compute queue depth, median wait time, merge/revert rates from JSONL events
  **Spec scenarios**: merge-infrastructure.5 (metrics aggregation)
  **Design decisions**: D6 (metrics schema and storage)
  **Dependencies**: 1.4
  **Size**: S

- [x] 5.2 Implement metrics_summary() — read JSONL events for current session, compute aggregated metrics, format as markdown table for merge log
  **Dependencies**: 5.1
  **Size**: S

- [x] 5.3 Wire metrics summary into SKILL.md Step 12 (Summary) — append metrics table after the PR triage summary
  **Dependencies**: 5.2
  **Size**: XS

- [x] 5.4 Write tests for coordinator metrics endpoint — verify /merge-train/metrics returns aggregated data from audit service
  **Spec scenarios**: merge-infrastructure.5 (coordinator endpoint)
  **Dependencies**: 5.2
  **Size**: S

- [x] 5.5 Implement /merge-train/metrics endpoint in coordination_api.py — query audit log for merge events, compute aggregated metrics, return JSON
  **Dependencies**: 5.4
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 6: Background Merge Watcher (wp-watcher)

- [x] 6.1 Write tests for merge_watcher_tick() — single-pass function that checks queue, composes trains, monitors CI, triggers auto-rebase; verify idempotent behavior, verify no-op when queue is empty
  **Spec scenarios**: merge-infrastructure.6 (watcher tick), merge-infrastructure.6 (idempotent)
  **Dependencies**: 3.2, 4.2
  **Size**: M

- [x] 6.2 Implement merge_watcher_tick() — single-pass entry point that performs one check cycle: compose_train if queued entries, monitor_ci_for_rollback for recent merges, auto_cascade_rebase for stale queued PRs
  **Dependencies**: 6.1
  **Size**: M

- [x] 6.3 Write tests for coordinator watcher task — verify background asyncio task lifecycle, verify graceful shutdown, verify error isolation (single tick failure doesn't crash loop)
  **Spec scenarios**: merge-infrastructure.6 (coordinator background task)
  **Design decisions**: D5 (coordinator background task)
  **Dependencies**: 6.2
  **Size**: S

- [x] 6.4 Implement coordinator merge watcher background task — register in coordinator startup, run merge_watcher_tick() every MERGE_WATCHER_INTERVAL seconds, catch and log exceptions, cancel on shutdown
  **Dependencies**: 6.3
  **Size**: M

- [x] 6.5 Create merge_watcher.py CLI entry point — `python merge_watcher.py tick` for single-pass /loop invocation, `python merge_watcher.py run` for standalone daemon mode
  **Dependencies**: 6.2
  **Size**: S

- [ ] Checkpoint: run tests, review diff, verify scope

## Phase 7: Integration (wp-integration)

- [ ] 7.1 Write integration test — full merge lifecycle: enqueue → compose train → speculate → pass → merge → auto-rebase → monitor CI → metrics summary. Verify with coordinator mock.
  **Spec scenarios**: All merge-infrastructure scenarios
  **Dependencies**: 6.4, 5.3
  **Size**: M

- [ ] 7.2 Write solo-dev backward compatibility test — verify merge-pull-requests works without coordinator, without GitHub merge queue, with direct merge only. Verify all existing test_merge_strategy.py tests still pass.
  **Spec scenarios**: merge-infrastructure.1 (solo-dev fallback)
  **Dependencies**: 7.1
  **Size**: S

- [ ] 7.3 Update docs/parallel-agentic-development.md — add merge queue scaling section covering train integration, auto-rebase, auto-rollback
  **Dependencies**: 7.1
  **Size**: S

- [ ] 7.4 Update docs/lessons-learned.md — add merge queue scaling patterns and rollback best practices
  **Dependencies**: 7.1
  **Size**: XS

- [ ] Checkpoint: run tests, review diff, verify scope
