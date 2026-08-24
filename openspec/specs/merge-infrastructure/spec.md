# merge-infrastructure Specification

## Purpose
TBD - created by archiving change merge-queue-scaling. Update Purpose after archive.
## Requirements
### Requirement: Merge Backend Abstraction

The merge-pull-requests skill SHALL support three merge backends selected automatically based on environment capabilities.

#### Scenario: Backend detection with coordinator available

WHEN the coordinator is reachable AND CAN_QUEUE_WORK is true
THEN the skill SHALL select the CoordinatorTrainBackend
AND compose a merge train for speculative parallel testing

#### Scenario: Backend detection with GitHub merge queue

WHEN the coordinator is not reachable AND the repository has merge queue enabled
THEN the skill SHALL select the GitHubQueueBackend
AND use `gh pr merge --merge-queue` for batched merging

#### Scenario: Solo-dev fallback

WHEN neither coordinator nor GitHub merge queue is available
THEN the skill SHALL select the DirectMergeBackend
AND merge PRs one at a time via `gh pr merge` with the origin-based strategy
AND all existing merge behavior (validation, approval, staleness) MUST be preserved

### Requirement: Train Integration

The CoordinatorTrainBackend SHALL bridge the merge-pull-requests skill to the coordinator's merge train engine.

#### Scenario: Train composition on merge request

WHEN an operator selects "Merge" for a PR AND CoordinatorTrainBackend is active
THEN the backend SHALL call compose_train to add the PR to the speculative train
AND poll train status until the entry reaches SPEC_PASSED or is EJECTED

#### Scenario: Partition-aware merge execution

WHEN all entries in a train partition reach SPEC_PASSED
THEN the backend SHALL call merge_partition to fast-forward main
AND emit a merge event with train_id and partition_count

### Requirement: Auto Cascading Rebase

After each successful merge, the system SHALL automatically refresh queued PRs that have file overlap with the merged PR.

#### Scenario: Auto rebase for non-conflicting overlap

WHEN a PR is merged AND other queued PRs have file overlap with the merged PR's changed files AND the overlap does not produce merge conflicts
THEN the system SHALL call the GitHub Update Branch API for each overlapping PR (up to MAX_AUTO_REBASE_PER_MERGE, default 5)
AND emit a rebase event for each refreshed PR

#### Scenario: Rate limiting

WHEN more than MAX_AUTO_REBASE_PER_MERGE PRs have overlap with the merged PR
THEN the system SHALL refresh only the highest-priority PRs up to the limit
AND log the remaining PRs for the next merge cycle

#### Scenario: Conflicting overlap skip

WHEN a queued PR has file overlap with the merged PR AND the overlap would produce merge conflicts
THEN the system SHALL NOT attempt to rebase that PR
AND SHALL flag it for operator attention in the merge summary

### Requirement: Auto Rollback

After each successful merge, the system SHALL monitor main branch CI and auto-revert if the merge broke the build.

#### Scenario: Breakage detection and attribution

WHEN main branch CI fails within ROLLBACK_MONITOR_MINUTES (default 15) of a merge AND the failing test files overlap with the merged PR's changed files
THEN the system SHALL attribute the breakage to the merged PR

#### Scenario: Auto revert creation

WHEN breakage is attributed to a merged PR
THEN the system SHALL create a revert commit via `git revert <merge-sha>`
AND create a PR for the revert with an explanatory body referencing the original PR
AND auto-merge the revert PR (bypassing normal queue to unblock trunk)
AND emit a revert event with the original PR number and revert PR number

#### Scenario: No false positive revert

WHEN main branch CI fails after a merge BUT no failing files overlap with the merged PR's changed files
THEN the system SHALL NOT auto-revert
AND SHALL log the failure for operator investigation

#### Scenario: Monitoring window timeout

WHEN ROLLBACK_MONITOR_MINUTES elapse after a merge AND main CI is passing
THEN the system SHALL consider the merge stable
AND stop monitoring

### Requirement: Merge Throughput Metrics

The merge workflow SHALL emit structured events and produce aggregated metrics.

#### Scenario: Merge event emission

WHEN any merge action occurs (merge, revert, rebase, eject, train_compose)
THEN the system SHALL emit a structured JSON event to docs/merge-logs/metrics.jsonl
AND when coordinator is available, also emit to the coordinator audit service

#### Scenario: Metrics aggregation and summary

WHEN a merge-pull-requests session completes
THEN the system SHALL compute aggregated metrics (queue depth, median wait time, merge/revert rates)
AND append a metrics summary table to the merge log

#### Scenario: Coordinator metrics endpoint

WHEN the coordinator is available
THEN a GET /merge-train/metrics endpoint SHALL return aggregated merge metrics from the audit service

### Requirement: Background Merge Watcher

A background process SHALL handle auto-rebase and auto-rollback without operator invocation.

#### Scenario: Coordinator background task

WHEN the coordinator starts AND the merge watcher is enabled
THEN a background asyncio task SHALL run merge_watcher_tick() every MERGE_WATCHER_INTERVAL seconds
AND catch and log exceptions without crashing the task
AND cancel gracefully on coordinator shutdown

#### Scenario: Single-pass fallback for /loop

WHEN the coordinator is not available
THEN the merge watcher SHALL expose a single-pass entry point (merge_watcher_tick)
THAT can be invoked by Claude's /loop command or any external scheduler

#### Scenario: Watcher idempotency

WHEN merge_watcher_tick() is called AND the queue is empty AND no recent merges need monitoring
THEN the tick SHALL be a no-op (emit heartbeat event only)
AND return within 1 second

### Requirement: Merge Plan Persistence and Projection

Merge plan storage SHALL select a tier using the existing merge-backend detection so the
coordinator is never a hard dependency. In the absence of an available coordinator, the
local `merge-plan.json` file SHALL be the authoritative store of plan state. The
human-readable `merge-plan.md` SHALL always be a faithful projection of the authoritative
`merge-plan.json` — rendering it SHALL NOT change plan state, and every node present in the
JSON SHALL appear in the projection.

#### Scenario: File tier is authoritative when no coordinator is available

- **WHEN** plan storage is initialised and no coordinator is available
- **THEN** the local `merge-plan.json` SHALL be treated as the authoritative store
- **AND** reads and writes of plan state SHALL operate on that file

#### Scenario: Rendered projection matches the authoritative JSON

- **WHEN** `merge-plan.md` is rendered from `merge-plan.json`
- **THEN** every node in the JSON SHALL appear in the projection with its current `outcome`
- **AND** rendering SHALL NOT mutate the authoritative plan state

#### Scenario: Plan state is separated into definition and live fields

- **WHEN** a plan is persisted
- **THEN** definition fields (PR set, dependency edges, strategy, gate rules) SHALL be
  distinguishable from live-state fields (`outcome`, in-flight claim, vendor verdict, inserted blockers)
- **AND** a live-state update SHALL NOT require rewriting the definition fields

