# Proposal: Merge Queue Scaling — Train Integration, Auto-Rebase, Auto-Rollback, Metrics

**Change ID**: `merge-queue-scaling`
**Status**: Draft
**Created**: 2026-06-05

## Why

The coordinator already has a fully implemented speculative merge train engine (`merge_train.py`, `merge_train_service.py`) with partition-aware parallelism, build graph analysis, and feature flags. But the `merge-pull-requests` skill — the operator-facing merge workflow — doesn't use any of it. PRs are still merged one at a time through `gh pr merge`, with manual staleness checks and manual conflict resolution between merges.

Three additional capabilities are missing entirely:

1. **No auto cascading rebase**: When a PR merges, queued PRs that overlap go stale. The operator must manually run `refresh-branch` for each one. At 50+ PRs/day, this creates a cascade where every merge invalidates N other PRs.
2. **No auto rollback**: If a merged PR breaks main CI, the operator must manually create a revert PR. During this time, every other PR in the queue is blocked by a red trunk.
3. **No merge throughput metrics**: No visibility into queue depth, wait times, eject rates, or CI time per merge. Without metrics, bottlenecks are invisible until they become crises.

The primary success criterion is **zero broken main** — the main branch CI should never stay red for more than 10 minutes, because auto-revert catches breakage immediately.

## What Changes

### Feature 1: Train-Aware Merge Orchestration (Skill ↔ Coordinator Bridge)

Wire the `merge-pull-requests` skill to use the coordinator's merge train when available, with GitHub's native merge queue as fallback:

- **Coordinator path**: Skill calls `compose_train` → train creates speculative branches → CI runs affected tests → `merge_partition` fast-forwards to main. Full speculative parallelism with partition-aware sub-trains.
- **GitHub path**: Skill uses `gh pr merge --merge-queue` to leverage GitHub's built-in merge groups with `merge_group` CI events. Less control but works without coordinator.
- **Solo-dev path**: Direct `gh pr merge` with no train or queue. Existing behavior preserved.
- **Transport detection**: Reuses existing coordinator detection (`check_coordinator.py`). Skill auto-selects: coordinator available → coordinator train; coordinator unavailable but GitHub merge queue enabled → GitHub path; neither → direct merge.

### Feature 2: Auto Cascading Rebase

After each successful merge (whether via train or direct), automatically refresh all queued PRs whose files overlap with the just-merged PR:

- **Non-conflicting overlap**: Call GitHub's Update Branch API (`refresh-branch`) to merge base into PR branch. This triggers fresh CI automatically.
- **Conflicting overlap**: Flag the PR for operator attention — auto-rebase would create merge conflicts.
- **Staleness re-check**: Re-run `check_staleness.py` for the next PR in the queue before presenting it.
- **Train integration**: When using coordinator train, auto-rebase is handled by train recomposition on merge — entries behind a merged entry re-speculate automatically.

### Feature 3: Auto Rollback

Monitor main branch CI after each merge and auto-revert if the merge broke the build:

- **Post-merge monitoring**: After a PR merges, poll main branch CI for up to N minutes (configurable, default 15).
- **Attribution**: If main CI fails and the failing files overlap with the just-merged PR's changed files, attribute the breakage to that PR.
- **Auto-revert**: Create a revert commit (`git revert <merge-sha>`), push it, and fast-track through the merge queue. Notify the original author/operator.
- **Train integration**: When using coordinator train, the speculative testing should catch most breakage before merge. Auto-rollback is the safety net for failures the speculative tests missed (environment-dependent, timing-dependent, etc.).

### Feature 4: Merge Throughput Metrics

Instrument the merge workflow with structured events and surface queue health:

- **Event emission**: Every merge/close/rebase/revert action emits a structured JSON event to a local log file and (when coordinator available) to the coordinator's audit service.
- **Metrics tracked**: Queue depth over time, median time-in-queue, merge success/failure/revert rates, CI time per PR, train composition size, partition count, eject rate.
- **Summary report**: At the end of each `/merge-pull-requests` invocation, append a metrics summary to the merge log.
- **Coordinator dashboard**: When coordinator is available, metrics are queryable via a new `/merge-train/metrics` endpoint. Compatible with the `kanban-viz` dashboard.

### Feature 5: Background Merge Watcher

A lightweight background process that handles auto-rebase and auto-rollback without operator invocation:

- **Coordinator mode**: Runs as a new background task in the coordinator (alongside the existing watchdog). Watches the merge queue, auto-composes trains, monitors post-merge CI.
- **Fallback mode**: When no coordinator, the operator can use Claude's `/loop` command to poll at intervals — the watcher exposes a single-pass entry point that `/loop` can invoke.
- **Scope**: The watcher handles auto-rebase and auto-rollback only. It does NOT merge PRs autonomously — that still requires operator invocation via `/merge-pull-requests` or the coordinator train's `compose_train`.

## Approaches Considered

### Approach 1: Skill-Side Orchestration with Coordinator Assist (Recommended)

**Description**: The merge-pull-requests skill remains the primary entry point. It detects coordinator availability and selects the appropriate merge backend (coordinator train → GitHub merge queue → direct merge). Auto-rebase and auto-rollback logic live in the skill scripts, with coordinator providing state persistence and the watcher providing background automation.

**Pros**:
- Preserves the existing operator workflow (interactive triage with `/merge-pull-requests`)
- Graceful degradation at every layer (coordinator → GitHub queue → direct)
- Solo-dev backward compatibility trivially maintained
- Skill scripts are easy to iterate on without coordinator redeployment
- Background watcher is additive — system works without it

**Cons**:
- Some logic duplication between skill (GitHub path) and coordinator (train path)
- Watcher fallback via `/loop` is less robust than a proper daemon
- Metrics split between local log file (no coordinator) and coordinator DB (with coordinator)

**Effort**: L

### Approach 2: Coordinator-Only Merge Train

**Description**: All merge orchestration moves into the coordinator. The skill becomes a thin UI that reads train status and presents it to the operator. Auto-rebase, auto-rollback, and metrics are all coordinator services.

**Pros**:
- Single source of truth for all merge state
- No logic duplication
- Watcher is naturally a coordinator background task
- Full ACID guarantees on state transitions

**Cons**:
- Solo-dev workflow breaks without coordinator
- Requires coordinator to be running for any merge operation
- Heavy coupling between skill and coordinator
- Iterating on merge logic requires coordinator redeployment

**Effort**: L

### Approach 3: GitHub-First with Coordinator Enhancement

**Description**: Lean fully into GitHub's native merge queue. Auto-rebase uses GitHub's auto-merge + branch protection. Auto-rollback uses GitHub Actions workflow. Coordinator provides only metrics and enhanced partition analysis.

**Pros**:
- Simplest implementation — leverages GitHub's existing infrastructure
- No local git operations needed
- Works for any GitHub repo, not just this one
- GitHub handles the speculative testing natively

**Cons**:
- Limited control over partition logic (GitHub groups by conflict, not by lock keys)
- No affected-test selection (GitHub runs full CI for each merge group)
- Loses the existing merge train engine's sophisticated partition-aware parallelism
- Auto-rollback in GitHub Actions is slow (workflow dispatch → CI → merge)

**Effort**: M

### Selected Approach

**Approach 1: Skill-Side Orchestration with Coordinator Assist** — selected by user. The rationale: graceful degradation at every layer (coordinator train → GitHub merge queue → direct merge) ensures the system works for solo-dev repos as well as 1000-agent fleets. The operator workflow stays familiar (interactive triage via `/merge-pull-requests`), while the background watcher handles auto-rebase and auto-rollback autonomously. The coordinator's existing merge train engine delivers partition-aware speculative testing when available — no need to rebuild it.

Key user decisions informing this approach:
- **Hybrid execution model**: Sync-point skill for interactive triage + background watcher for auto-rebase/rollback
- **Auto-revert immediately**: When main CI breaks, create and merge the revert PR automatically. Notify operator after the fact.
- **Zero broken main** is the primary success metric
- **Solo-dev backward compatibility** is a hard constraint

## Success Criteria

1. **Zero broken main**: Main branch CI never stays red for more than 10 minutes. Auto-revert catches breakage from merged PRs within the monitoring window. Validated by: merge log shows revert events with timestamps <10 min from merge.
2. **Automatic stale-branch recovery**: After a merge, all queued PRs with file overlap are automatically refreshed (non-conflicting) or flagged (conflicting). Operator never manually runs `refresh-branch`. Validated by: merge log shows auto-rebase events after each merge.
3. **Train integration**: When coordinator is available, `merge-pull-requests` uses `compose_train` for speculative parallel testing. Multiple non-conflicting PRs merge in parallel. Validated by: merge log shows train composition with partition counts.
4. **Solo-dev backward compatibility**: A repo with no coordinator and no GitHub merge queue configured can still run `/merge-pull-requests` with the same behavior as today. Validated by: existing test suite passes without coordinator.
5. **Metrics visibility**: Every merge session produces a metrics summary with queue depth, wait times, and merge/revert rates. Validated by: merge log contains metrics section.

## Impact

- **Merge throughput**: Independent PRs merge in parallel via coordinator train (O(N/K) where K = partitions) or GitHub merge groups. Validated by success criterion #3.
- **Trunk stability**: Auto-revert keeps main green. Reduces manual incident response from hours to seconds. Validated by success criterion #1.
- **Operator toil**: Auto-rebase eliminates the manual refresh-branch cycle. Validated by success criterion #2.
- **Observability**: Metrics surface queue bottlenecks before they become crises. Validated by success criterion #5.
- **Affected capabilities**: `merge-pull-requests` (skill), `agent-coordinator` (merge train integration, watcher, metrics), `merge_queue.py` (train bridge)

## Scope Boundaries

**In scope (this change)**:
- Merge-pull-requests skill wiring to coordinator merge train
- GitHub merge queue fallback path
- Auto cascading rebase via GitHub Update Branch API
- Auto rollback with CI monitoring and auto-revert
- Merge throughput metrics (event emission + summary report)
- Background merge watcher (coordinator task + /loop fallback)
- Coordinator `/merge-train/metrics` endpoint

**Out of scope (deferred)**:
- Kanban-viz dashboard integration for metrics (separate visual change)
- Stacked-diff workflow in merge-pull-requests skill (train already supports it — skill wiring is future work)
- Affected-test selection wiring into auto-rollback attribution (currently uses file overlap heuristic)
- Cross-repo merge train support (multi-repo monorepo patterns)
- Adaptive partition sizing based on historical data

## Dependencies

- Existing merge train engine (`agent-coordinator/src/merge_train.py`, `merge_train_service.py`)
- Existing git adapter (`agent-coordinator/src/git_adapter.py`)
- Existing merge queue (`agent-coordinator/src/merge_queue.py`)
- Existing merge-pull-requests skill (`skills/merge-pull-requests/`)
- Existing staleness detection (`check_staleness.py`)
- Existing branch refresh (`merge_pr.py refresh-branch`)
- GitHub API (merge queue, Update Branch API, CI status)
- Coordinator detection (`check_coordinator.py`)

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Auto-revert on false positive (flaky CI) | High | Only revert when failing files overlap with merged PR's changed files. Flaky test detection via historical pass rate (if available from metrics). Configurable monitoring window. |
| Cascading rebase triggers CI storm | Medium | Rate-limit auto-rebase to N PRs per merge event. Batch refresh-branch calls with short delay between. |
| Train ↔ GitHub queue confusion | Medium | Clear mode indication in merge log. Never use both simultaneously for the same PR. |
| Background watcher consumes GitHub API quota | Medium | Exponential backoff on polling. Respect rate limit headers. Watcher is opt-in, not default. |
| Solo-dev workflow regresses | Low | Dedicated test path that runs without coordinator. CI job validates solo-dev mode. |
