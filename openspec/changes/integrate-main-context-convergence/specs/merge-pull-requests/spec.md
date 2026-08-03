# merge-pull-requests Specification Delta

## MODIFIED Requirements

### Requirement: OpenSpec Integration

The skill SHALL invoke `/cleanup-feature <change-id> --post-merge --pr <number>` for every OpenSpec change merged during the pass, before any shared context refresh runs, and SHALL NOT perform task migration, OpenSpec archival, or spec-delta merging itself.

`cleanup-feature` retains sole ownership of those three operations. The merge skill
owns only the ordering and the single convergence that follows.

#### Scenario: Merge OpenSpec PR

- **WHEN** an OpenSpec PR is merged during the pass
- **THEN** the skill SHALL record the change-id, PR number, and branch for the
  post-merge cleanup step
- **AND** it SHALL offer `/cleanup-feature <change-id> --post-merge --pr <number>`
  for operator approval before any refresh runs

#### Scenario: Cleanup precedes refresh

- **WHEN** the operator approves post-merge cleanup for one or more merged OpenSpec changes
- **THEN** the skill SHALL run every approved cleanup command to completion before
  starting the shared context refresh
- **AND** the refresh SHALL observe the tree that includes the archived changes,
  merged spec deltas, and regenerated decision index

#### Scenario: Cleanup declined or failed

- **WHEN** the operator declines cleanup, or a cleanup command fails
- **THEN** the skill SHALL stop the cleanup phase and SHALL NOT run the shared refresh
  over a partially archived tree
- **AND** it SHALL commit and push whatever cleanup output already succeeded rather
  than discarding it
- **AND** it SHALL report the declined or failed change-ids in the summary and merge log

## ADDED Requirements

### Requirement: Single main context convergence per pass

The skill SHALL run exactly one shared context convergence for the main state produced by an invocation that merged one or more pull requests, and SHALL run none when no pull request was merged.

Convergence is keyed on the resulting main state, not on the number of pull
requests that produced it. A batch landed by a merge queue or coordinator train is
one state and therefore one convergence.

<!-- Scenario ID: merge-pull-requests.one-convergence-per-pass -->
#### Scenario: Multiple merges produce one convergence

- **WHEN** an invocation merges three pull requests
- **THEN** the skill SHALL run the deterministic context refresh exactly once, after
  the per-PR loop and after post-merge cleanup have both completed
- **AND** it SHALL produce exactly one convergence commit
- **AND** it SHALL enqueue exactly one semantic indexing request

<!-- Scenario ID: merge-pull-requests.non-openspec-convergence -->
#### Scenario: A non-OpenSpec merge still converges

- **WHEN** an invocation merges only dependency-update or automation pull requests
- **THEN** the skill SHALL skip the OpenSpec cleanup phase
- **AND** it SHALL still run one deterministic context refresh for the resulting main state

<!-- Scenario ID: merge-pull-requests.no-merge-no-convergence -->
#### Scenario: No merges means no convergence

- **WHEN** an invocation merges no pull requests
- **THEN** the skill SHALL NOT run the refresh, SHALL NOT create a convergence commit,
  and SHALL NOT enqueue semantic indexing

<!-- Scenario ID: merge-pull-requests.dry-run-no-convergence -->
#### Scenario: Dry-run performs no convergence

- **WHEN** the skill is invoked with `--dry-run`
- **THEN** it SHALL perform no merge, no refresh, no commit, and no indexing request
- **AND** it SHALL report the operation identity it would derive from the current
  main revision and a read-only drift assessment

### Requirement: One follow-up convergence commit

The skill SHALL commit the deterministic cleanup artifacts, the regenerated refresh artifacts, and a tracked convergence record as a single follow-up commit on main, and SHALL push it exactly once.

The durable refresh manifest remains outside the tracked working tree; the tracked
convergence record pins it by path and content digest.

<!-- Scenario ID: merge-pull-requests.single-convergence-commit -->
#### Scenario: Cleanup and refresh artifacts land together

- **WHEN** the convergence sequence completes for a pass that archived two OpenSpec changes
- **THEN** the archived changes, merged spec deltas, regenerated decision index,
  regenerated deterministic producer outputs, and architecture provenance SHALL all
  appear in one commit
- **AND** that commit SHALL contain a convergence record carrying the operation id,
  the merged main revision, the manifest path, and the manifest content digest
- **AND** the durable manifest file itself SHALL remain untracked

<!-- Scenario ID: merge-pull-requests.commit-trailer-identity -->
#### Scenario: The convergence commit carries its operation identity

- **WHEN** the convergence commit is created
- **THEN** its message SHALL carry a trailer naming the durable refresh operation id
- **AND** a later invocation SHALL be able to recognize the convergence from that
  trailer alone, without reading any untracked state

### Requirement: Sync-point locking and idempotent retry

The skill SHALL hold exclusive sync-point access for the whole convergence sequence and SHALL derive a durable operation identity from the merged main revision, so that a retry after any partial failure produces no duplicate commit, no duplicate archival, and no duplicate indexing request.

<!-- Scenario ID: merge-pull-requests.exclusive-sync-point -->
#### Scenario: Convergence refuses to interleave with another main writer

- **WHEN** the convergence sequence is about to write
- **THEN** the skill SHALL verify that no other agent holds an active worktree
- **AND** it SHALL acquire an exclusive sync-point lock when a coordinator is available
- **AND** it SHALL re-verify immediately before pushing that the remote main revision
  still equals the revision the operation was keyed on

<!-- Scenario ID: merge-pull-requests.push-race-aborts -->
#### Scenario: A losing push race aborts without forcing

- **WHEN** the remote main revision has advanced between the refresh and the push
- **THEN** the skill SHALL abort the convergence without force-pushing
- **AND** it SHALL leave the durable operation resumable and report the race

<!-- Scenario ID: merge-pull-requests.retry-is-idempotent -->
#### Scenario: Retry after a crash creates nothing twice

- **WHEN** a convergence is retried for a merged main revision whose durable operation
  is already terminal, or whose convergence commit is already discoverable on main
- **THEN** the skill SHALL reuse the existing operation identity
- **AND** it SHALL NOT create a second convergence commit, re-archive any change, or
  enqueue a second indexing request

### Requirement: Convergence failure never reverses a merge

The skill SHALL treat every merge as terminal, and SHALL NOT revert, close, or reopen any pull request because a context refresh degraded or failed.

A convergence problem is reported alongside the merge result, never in place of it.

<!-- Scenario ID: merge-pull-requests.refresh-failure-preserves-merge -->
#### Scenario: A producer failure leaves the merge intact

- **WHEN** a deterministic producer fails during the convergence refresh
- **THEN** the merged pull requests SHALL remain merged
- **AND** the skill SHALL commit and push the cleanup artifacts that did succeed
- **AND** it SHALL report the failure as a warning and leave the operation resumable

<!-- Scenario ID: merge-pull-requests.degraded-still-commits -->
#### Scenario: A degraded refresh still commits its deterministic output

- **WHEN** the refresh finishes degraded because an optional owner is absent or the
  semantic index was deferred
- **THEN** the skill SHALL still create the convergence commit with the deterministic
  output that was produced
- **AND** it SHALL record the degradation in the convergence record and the summary

<!-- Scenario ID: merge-pull-requests.summary-always-runs -->
#### Scenario: The summary and merge log run regardless of convergence outcome

- **WHEN** the convergence sequence fails for any reason
- **THEN** the skill SHALL still produce the PR triage summary and append the merge log
- **AND** both SHALL record the convergence outcome

### Requirement: Deferred semantic indexing and final handoff

The skill SHALL enqueue semantic indexing for the final pushed main revision without waiting for it, and SHALL report the merged revision, the context-refresh revision, and the semantic-index status in the final handoff.

Semantic indexing SHALL NOT be a blocking dependency of a merge, a cleanup, or the
convergence commit.

<!-- Scenario ID: merge-pull-requests.index-enqueued-for-final-sha -->
#### Scenario: Indexing targets the pushed revision, not the merged one

- **WHEN** the convergence commit has been pushed
- **THEN** the skill SHALL enqueue exactly one semantic indexing request for the
  revision that is now the tip of main
- **AND** the deterministic refresh operation for the merged revision SHALL record the
  semantic index as pending with an exact-search fallback

<!-- Scenario ID: merge-pull-requests.index-unavailable-degrades -->
#### Scenario: An unavailable index degrades but does not block

- **WHEN** the semantic indexing service is unconfigured or unreachable
- **THEN** the skill SHALL record a non-succeeded semantic status with a fallback
- **AND** the convergence commit SHALL still be created and pushed
- **AND** the pass SHALL complete rather than wait or fail

<!-- Scenario ID: merge-pull-requests.handoff-three-revisions -->
#### Scenario: The handoff names all three states

- **WHEN** the pass completes
- **THEN** the reported handoff SHALL name the merged main revision, the revision the
  context refresh ran against, and the convergence commit revision now on main
- **AND** it SHALL name the semantic-index status for that final pushed revision
