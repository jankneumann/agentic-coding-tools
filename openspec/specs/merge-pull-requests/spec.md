# merge-pull-requests Specification

## Purpose
TBD - created by archiving change add-merge-pull-requests-skill. Update Purpose after archive.
## Requirements
### Requirement: PR Discovery and Classification

The skill SHALL discover all open pull requests in the current repository and classify each by origin: OpenSpec, Jules/Sentinel, Jules/Bolt, Jules/Palette, Codex, Dependabot, Renovate, or other. Its discovery entry point and classifier SHALL be runnable from the installed consumer payload without importing coordinator source code.

#### Scenario: Discover open PRs
- **WHEN** the skill is invoked in a consumer repository with open PRs
- **THEN** it SHALL list all open PRs with their number, title, author, origin classification, branch name, creation date, and labels
- **AND** discovery SHALL not require `agent-coordinator/src`

#### Scenario: Import discovery without coordinator checkout
- **WHEN** `discover_prs.py --help` is executed from an rsynced `.claude/skills/merge-pull-requests` or `.agents/skills/merge-pull-requests` directory
- **AND** the consumer contains no `agent-coordinator` package
- **THEN** the command SHALL exit successfully
- **AND** classification helpers SHALL resolve from the installed payload

#### Scenario: No open PRs
- **WHEN** the skill is invoked in a repository with no open PRs
- **THEN** it SHALL report that no open PRs were found and exit gracefully
- **AND** SHALL preserve the same classification result schema as the coordinator PR-card adapter

### Requirement: Staleness Detection
The skill SHALL detect whether a PR's changes are still relevant by comparing its diff against changes made to main since the PR was created.

#### Scenario: Fresh PR
- **WHEN** no files modified by the PR have been changed on main since the PR was created
- **THEN** the PR SHALL be classified as `fresh`

#### Scenario: Stale PR with overlapping changes
- **WHEN** files modified by the PR have also been changed on main since the PR was created
- **THEN** the PR SHALL be classified as `stale` with the list of overlapping files

#### Scenario: Obsolete Jules automation PR
- **WHEN** a Jules automation PR fixes a code pattern that no longer exists on main
- **THEN** the PR SHALL be classified as `obsolete` with an explanation of why the fix is no longer needed

### Requirement: Review Comment Analysis
The skill SHALL fetch and summarize unresolved review comments for PRs that have pending feedback.

#### Scenario: PR with unresolved comments
- **WHEN** a PR has unresolved review comment threads
- **THEN** the skill SHALL present each thread with: file path, line number, reviewer, and comment summary

#### Scenario: PR with no comments
- **WHEN** a PR has no review comments or all comments are resolved
- **THEN** the skill SHALL indicate the PR has no pending review feedback

### Requirement: Interactive Merge Workflow
The skill SHALL present an interactive workflow where the operator decides the action for each PR: merge, skip, close, or address-comments.

#### Scenario: Merge a fresh approved PR
- **WHEN** the operator chooses to merge a PR that is fresh and has CI passing
- **THEN** the skill SHALL merge the PR using the chosen strategy (squash by default) and delete the remote branch

#### Scenario: Close an obsolete PR
- **WHEN** the operator chooses to close an obsolete PR
- **THEN** the skill SHALL close the PR with a comment explaining why it is obsolete

#### Scenario: Address comments on an OpenSpec PR
- **WHEN** the operator chooses to address comments on an OpenSpec PR
- **THEN** the skill SHALL present the unresolved comments and guide the operator through resolving them

#### Scenario: Skip a PR
- **WHEN** the operator chooses to skip a PR
- **THEN** the skill SHALL move to the next PR without taking any action

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

### Requirement: Batch Close Obsolete PRs
The skill SHALL offer to batch-close all PRs classified as obsolete after the staleness detection phase.

#### Scenario: Batch close offered
- **WHEN** one or more PRs are classified as obsolete
- **THEN** the skill SHALL present the list and offer to close all of them in one step with explanatory comments

#### Scenario: No obsolete PRs
- **WHEN** no PRs are classified as obsolete
- **THEN** the skill SHALL skip the batch-close step and proceed to interactive review

### Requirement: Dry-Run Mode
The skill SHALL support a `--dry-run` argument that produces a full report without performing any merge or close actions.

#### Scenario: Dry-run invocation
- **WHEN** the skill is invoked with `--dry-run`
- **THEN** it SHALL run discovery, classification, staleness detection, and comment analysis, then output a summary report and exit without offering merge/close actions

#### Scenario: Dry-run output format
- **WHEN** dry-run mode is active
- **THEN** the report SHALL include per-PR: number, title, origin classification, staleness status, and unresolved comment count

### Requirement: Python Helper Scripts
The skill SHALL use Python scripts for complex operations (discovery, staleness checking, comment analysis, merge execution) and keep the SKILL.md focused on orchestration workflow.

#### Scenario: Scripts use gh CLI
- **WHEN** a Python script needs GitHub data
- **THEN** it SHALL use the `gh` CLI via `subprocess` rather than direct GitHub API calls

#### Scenario: Scripts output JSON
- **WHEN** a Python script produces structured output
- **THEN** it SHALL output JSON to stdout for consumption by the skill workflow

### Requirement: Vendor Review Artifact Resilience

The vendor review dispatch (Step 9) SHALL handle PRs regardless of whether OpenSpec planning artifacts (contracts, work-packages) exist.

#### Scenario: Vendor review with planning artifacts
- **WHEN** a PR has an associated OpenSpec change directory containing contracts and work-packages
- **THEN** the vendor review prompt SHALL include contract and scope information for richer review context
- **AND** the review dispatch SHALL proceed normally

#### Scenario: Vendor review without planning artifacts
- **WHEN** a PR lacks contracts or work-packages (legacy PR, external contribution, non-OpenSpec PR)
- **THEN** the vendor review SHALL proceed using only the PR diff and metadata as context
- **AND** the review SHALL NOT fail, skip, or produce an error due to missing artifacts
- **AND** the review output SHALL note that artifact-based scoping was unavailable

### Requirement: Durable Merge Plan Artifact

The skill SHALL be able to emit a durable merge plan from the analysis round so triage
state survives a context clear and can seed fresh-context execution. The plan SHALL be
written as machine-readable `merge-plan.json` conforming to
`contracts/schemas/merge-plan.schema.json`, accompanied by a rendered human-readable
`merge-plan.md` projection. For each PR node the plan SHALL record: PR number, origin
classification, staleness, CI/gate state, unresolved-comment count, merge strategy, an
`auto_executable` flag, optional `gate` markers, dependency edges to other nodes, and a
mutable `outcome` (`pending`, `merged`, `closed`, `deferred`, or `failed`).
The Markdown projection SHALL surface each node's current CI state, staleness,
unresolved-comment count and summary, and blocking reason. JSON and Markdown
persistence SHALL be atomic as a unit or recoverably consistent: if a write is
interrupted, the authoritative JSON SHALL be sufficient to repair the projection.

#### Scenario: Analysis round emits a durable plan

- **WHEN** the operator runs the analysis round with plan output enabled
- **THEN** the skill SHALL write `merge-plan.json` validating against the plan schema
- **AND** SHALL render a `merge-plan.md` projection of the same state
- **AND** each open PR SHALL appear as a node with `outcome` initialised to `pending`

#### Scenario: Dependency edges are derived from file overlap and base branch

- **WHEN** two PR nodes modify one or more of the same files, or one targets the other's branch
- **THEN** the plan SHALL record a dependency edge between them
- **AND** the rendered `merge-plan.md` SHALL surface conflicting-pair edges to the operator

### Requirement: Plan-Driven Single-PR Execution

The skill SHALL support executing a single PR from a plan with fresh context, decoupled
from the analysis round. Invoked as `--execute <plan> --pr <n>`, execution SHALL re-check
live PR and CI state (never trusting the snapshot alone), refresh the branch if stale, run
vendor review when eligible, merge using the node's strategy subject to gate rules, and
write the resulting `outcome` back to the plan. After a successful merge, execution SHALL
mark every downstream node depending on the merged node for re-validation before it is
executed. Execution SHALL invoke helper scripts via canonical `skills/...` paths and SHALL
NOT rely on `.agents/skills`, `.claude/skills`, or other runtime mirrors. File-tier
execution SHALL run the skill's active-agent sync-point guard before any refresh or merge
side effect. It SHALL atomically persist an `in_progress` claim before those side effects,
serialize every same-host file-tier mutation under the same lock, reject writes based on
a stale plan revision or expected node outcome, reject an unowned replay, and reconcile a
claimed node from live terminal GitHub state
before prerequisite, human, or sync-point gates so a crash after the remote merge cannot
cause a duplicate merge or require the prior approval to be supplied again. Every
execution attempt SHALL recompute live staleness even when the snapshot says `fresh`.
After refreshing a historically-overlapping PR, execution SHALL require a current CI
merge base, fresh passing CI, and a live mergeable state; historical overlap alone SHALL
NOT permanently block the refreshed PR. When vendor review is eligible, dispatch failure
or the absence of a consensus verdict SHALL block the merge.

#### Scenario: Executing one node updates the plan and flags downstream nodes

- **WHEN** the operator runs `--execute <plan> --pr <n>` and the merge succeeds
- **THEN** the node's `outcome` SHALL be set to `merged` in the plan
- **AND** every node with a dependency edge to `n` SHALL be flagged for re-validation
- **AND** a subsequent execution of a flagged node SHALL recompute its mergeability before merging

#### Scenario: Gated node halts for human decision

- **WHEN** a node is marked `auto_executable: false` or carries a `requires_human_approval` gate
- **THEN** execution SHALL stop before merging and surface the gate to the operator
- **AND** SHALL NOT merge the node without explicit operator approval

#### Scenario: OpenSpec acceptance cannot be bypassed by generic approval

- **WHEN** an OpenSpec node is executed, including with the generic execution approval flag
- **THEN** the node SHALL remain non-auto-executable with a `proposal_acceptance` gate
- **AND** execution SHALL halt for the dedicated proposal-acceptance workflow

#### Scenario: Interrupted execution reconciles instead of replaying the merge

- **WHEN** a node is durably claimed and the process stops after GitHub merges the PR but before the final plan write
- **THEN** a subsequent execution SHALL observe the live merged state and persist `outcome: merged`
- **AND** SHALL NOT invoke the merge operation again

#### Scenario: Historical overlap is safe after current-base revalidation

- **WHEN** the overlap classifier remains `stale` after a successful branch refresh because it measures changes since PR creation
- **THEN** execution SHALL accept the refreshed node only when its CI merge base is current, CI is fresh and passing, and the live PR state is mergeable
- **AND** SHALL NOT require the historical overlap classification itself to become `fresh`

#### Scenario: Stale gate writer cannot overwrite a winning claim

- **WHEN** one file-tier executor reads a pending node and another executor atomically claims it before the first persists a gate result
- **THEN** the stale gate write SHALL be rejected using the current plan revision or expected outcome
- **AND** the winning `in_progress` claim SHALL remain durable

#### Scenario: Eligible vendor review fails closed

- **WHEN** a node is eligible for vendor review but dispatch errors or returns no consensus verdict
- **THEN** execution SHALL keep the node pending with the blocking reason recorded
- **AND** SHALL NOT invoke the merge operation

#### Scenario: Execution respects the security-check backstop

- **WHEN** a node would be merged past a failing required security check
- **THEN** execution SHALL defer to the auto-mode classifier and SHALL NOT bypass it automatically
- **AND** the node `outcome` SHALL remain `pending` with the blocking reason recorded

### Requirement: Merge Plan Living Amendment

Plan-driven execution SHALL be able to amend the plan when it discovers a blocker that must
be resolved before other nodes can proceed. An amendment SHALL insert a new prerequisite
node and add dependency edges from the affected nodes, SHALL carry a human-readable reason,
and SHALL NOT silently remove existing nodes.

#### Scenario: A discovered blocker is inserted as a prerequisite

- **WHEN** execution of a node discovers a blocker that also affects other pending nodes
- **THEN** the skill SHALL insert a new prerequisite node into the plan with a reason
- **AND** SHALL add dependency edges from each affected node to the new prerequisite
- **AND** the affected nodes SHALL become blocked until the prerequisite's `outcome` is `merged`

### Requirement: Merge Plan Comment-Addressing Seam

When plan-driven execution encounters unresolved review comments on a node, it SHALL record
them on the node and SHALL present the operator with a delegation hand-off rather than
writing code itself. Automated code-writing to resolve comments is out of scope for this
capability.

#### Scenario: Unresolved comments produce a delegation hand-off

- **WHEN** execution finds unresolved review comments on the node being executed
- **THEN** the skill SHALL record the unresolved-comment summary on the node
- **AND** SHALL offer to delegate resolution to `iterate-on-implementation` or `quick-task`
- **AND** SHALL NOT modify the PR branch's code automatically

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

