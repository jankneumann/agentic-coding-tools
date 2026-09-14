# merge-pull-requests Specification

## Purpose
Plan-then-execute conductor for merging open pull requests: analyze merge order,
discuss and persist a durable merge plan, remediate plan-only OpenSpec PRs via
`/iterate-on-plan` and implementation PRs via `/iterate-on-implementation` (both
with multi-vendor review), then merge through the fail-closed execute kernel.
The interactive per-PR menu remains available as `--interactive`.
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

The skill SHALL present an interactive per-PR action menu (merge, skip, close,
address-comments) only when invoked with `--interactive`. The default path is
the plan-then-execute conductor specified under Plan-Then-Execute Default Path.

#### Scenario: Merge a fresh approved PR

- **WHEN** the operator chooses to merge a PR that is fresh and has CI passing in `--interactive` mode
- **THEN** the skill SHALL merge the PR using the chosen strategy and delete the remote branch

#### Scenario: Close an obsolete PR

- **WHEN** the operator chooses to close an obsolete PR in `--interactive` mode
- **THEN** the skill SHALL close the PR with a comment explaining why it is obsolete

#### Scenario: Address comments on an OpenSpec PR

- **WHEN** the operator chooses to address comments on an OpenSpec PR in `--interactive` mode
- **THEN** the skill SHALL present the unresolved comments and guide the operator through resolving them

#### Scenario: Skip a PR

- **WHEN** the operator chooses to skip a PR in `--interactive` mode
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

The skill SHALL offer to close PRs classified as obsolete as part of the plan
discussion, recorded as planned `outcome=closed` nodes, rather than as a
pre-loop step before interactive review.

#### Scenario: Batch close offered

- **WHEN** one or more PRs are classified as obsolete
- **THEN** the skill SHALL present them in the plan discussion and offer to close them with explanatory comments as planned node outcomes

#### Scenario: No obsolete PRs

- **WHEN** no PRs are classified as obsolete
- **THEN** the skill SHALL not add close nodes for obsolescence and SHALL proceed with the rest of the plan discussion

### Requirement: Dry-Run Mode

The skill SHALL support a `--dry-run` argument that runs analysis and emits a
plan without merge, close, iterate, refresh, or convergence side effects.

#### Scenario: Dry-run invocation

- **WHEN** the skill is invoked with `--dry-run`
- **THEN** it SHALL run discovery, classification, staleness detection, comment analysis, and kind classification, write the plan artifact, and exit without executing nodes

#### Scenario: Dry-run output format

- **WHEN** dry-run mode is active
- **THEN** the report SHALL include per-PR: number, title, origin, kind, remediation_skill, staleness, unresolved comment count, and CI-failure class when CI is failing

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

The skill SHALL emit a durable merge plan from every default analysis round so
triage state survives a context clear and can seed fresh-context execution. The
plan SHALL be written as machine-readable `merge-plan.json` conforming to
schema version `1.1` of `contracts/merge-plan.schema.json`, accompanied by a
rendered human-readable `merge-plan.md` projection. For each PR node the plan
SHALL record: PR number, origin classification, `kind`, `change_id` when known,
`remediation_skill`, staleness, CI/gate state, CI-failure class when CI is
failing, unresolved-comment count, merge strategy, an `auto_executable` flag,
optional `gate` markers, dependency edges to other nodes, optional
`inserted_reason` on operator-inserted edges, and a mutable `outcome`
(`pending`, `in_progress`, `merged`, `closed`, `deferred`, or `failed`).
The Markdown projection SHALL surface each node's current CI state, kind,
remediation skill, staleness, unresolved-comment count and summary, and
blocking reason. JSON and Markdown persistence SHALL be atomic as a unit or
recoverably consistent: if a write is interrupted, the authoritative JSON SHALL
be sufficient to repair the projection.

#### Scenario: Analysis round emits a durable plan

- **WHEN** the operator runs the default analysis round
- **THEN** the skill SHALL write `merge-plan.json` validating against schema version 1.1
- **AND** SHALL render a `merge-plan.md` projection of the same state
- **AND** each open PR SHALL appear as a node with `outcome` initialised to `pending` and a populated `kind`

#### Scenario: Dependency edges are derived from file overlap and base branch

- **WHEN** two PR nodes modify one or more of the same files, or one targets the other's branch
- **THEN** the plan SHALL record a dependency edge between them
- **AND** the rendered `merge-plan.md` SHALL surface conflicting-pair edges to the operator

### Requirement: Plan-Driven Single-PR Execution

The skill SHALL support executing a single PR from a plan with fresh context,
decoupled from the analysis round. Invoked as `--execute <plan> --pr <n>`,
execution SHALL re-check live PR and CI state (never trusting the snapshot
alone), refresh the branch if stale, skip merge-time `vendor_review.py` when
the node completed iterate with a consensus artifact whose HEAD matches the
PR head, otherwise run vendor review when eligible, merge using the node's
strategy subject to gate rules, and write the resulting `outcome` back to the
plan. After a successful merge, execution SHALL mark every downstream node
depending on the merged node for re-validation before it is executed.
Execution SHALL invoke helper scripts via canonical `skills/...` paths and
SHALL NOT rely on `.agents/skills`, `.claude/skills`, or other runtime mirrors.
File-tier execution SHALL run the skill's active-agent sync-point guard before
any refresh or merge side effect. It SHALL atomically persist an `in_progress`
claim before those side effects, serialize every same-host file-tier mutation
under the same lock, reject writes based on a stale plan revision or expected
node outcome, reject an unowned replay, and reconcile a claimed node from live
terminal GitHub state before prerequisite, human, or sync-point gates so a
crash after the remote merge cannot cause a duplicate merge or require the
prior approval to be supplied again. Every execution attempt SHALL recompute
live staleness even when the snapshot says `fresh`. After refreshing a
historically-overlapping PR, execution SHALL require a current CI merge base,
fresh passing CI, and a live mergeable state; historical overlap alone SHALL
NOT permanently block the refreshed PR. When vendor review is eligible and
iterate consensus is absent or stale versus HEAD, dispatch failure or the
absence of a consensus verdict SHALL block the merge. Execution SHALL NOT
check out, commit, or push to the PR branch.

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

- **WHEN** a node is eligible for vendor review, iterate consensus is absent or stale versus HEAD, and dispatch errors or returns no consensus verdict
- **THEN** execution SHALL keep the node pending with the blocking reason recorded
- **AND** SHALL NOT invoke the merge operation

<!-- Scenario ID: merge-pull-requests.skip-pr-diff-review-after-iterate -->
#### Scenario: Current iterate consensus skips merge-time PR-diff review

- **WHEN** a node completed iterate with `reviews/consensus-plan.json` or `reviews/consensus-impl.json` whose recorded HEAD matches the live PR head
- **THEN** `--execute` SHALL skip `vendor_review.py` for that node
- **AND** SHALL still enforce `proposal_acceptance`, security-check, and `can_merge` gates

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

When plan-driven execution encounters unresolved review comments on a node, it
SHALL record them on the node. The conductor SHALL remediate OpenSpec `plan`
nodes via `/iterate-on-plan` and OpenSpec `implementation` nodes via
`/iterate-on-implementation`, both with `--vendor-review`. Non-OpenSpec nodes
SHALL receive a `quick-task` hand-off. Automated code-writing remains forbidden
inside `execute_plan.py`.

#### Scenario: Unresolved comments produce a delegation hand-off

- **WHEN** execution finds unresolved review comments on the node being executed
- **THEN** the skill SHALL record the unresolved-comment summary on the node
- **AND** SHALL offer to delegate resolution to `/iterate-on-plan`, `/iterate-on-implementation`, or `quick-task` according to the node's `remediation_skill`
- **AND** SHALL NOT modify the PR branch's code automatically

#### Scenario: Unresolved comments on an implementation node invoke iterate-on-implementation

- **WHEN** execution finds unresolved review comments on an OpenSpec `implementation` node
- **THEN** the skill SHALL record the unresolved-comment summary on the node
- **AND** the conductor SHALL invoke `/iterate-on-implementation <change-id> --vendor-review` in a worktree
- **AND** `execute_plan.py` SHALL NOT modify the PR branch's code automatically

#### Scenario: Unresolved comments on a plan node invoke iterate-on-plan

- **WHEN** execution finds unresolved review comments on an OpenSpec `plan` node
- **THEN** the conductor SHALL invoke `/iterate-on-plan <change-id> --vendor-review` in a worktree
- **AND** SHALL NOT invoke `/iterate-on-implementation` for that node

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

### Requirement: Plan-Then-Execute Default Path

The default invocation of the skill SHALL be a two-phase conductor: (1) analyze
the open-PR cohort, discuss the resulting merge plan with the operator, and
persist `merge-plan.json` plus its `merge-plan.md` projection; (2) execute ready
nodes one at a time from that plan. The per-PR action menu (merge / skip / close
/ address-comments) SHALL NOT be the default path.

<!-- Scenario ID: merge-pull-requests.default-is-plan-then-execute -->
#### Scenario: Default invocation does not open the per-PR action menu

- **WHEN** the operator invokes `/merge-pull-requests` without `--interactive`
- **THEN** the skill SHALL run analysis, present the plan for operator discussion,
  persist the approved plan, and then execute ready nodes
- **AND** SHALL NOT present the per-PR merge/skip/close/address-comments menu

<!-- Scenario ID: merge-pull-requests.interactive-opt-in -->
#### Scenario: Interactive path remains available as an opt-in

- **WHEN** the operator invokes `/merge-pull-requests --interactive`
- **THEN** the skill SHALL present the existing per-PR action menu
- **AND** SHALL still be able to emit a durable plan from the analysis round

### Requirement: Node Kind Classification

Analysis SHALL classify each node as `plan`, `implementation`, or `automation`
and SHALL record `kind`, `change_id` (when an OpenSpec change-id is known), and
`remediation_skill` on the node definition. The default heuristic SHALL mark a
node `plan` when every changed file is under `openspec/changes/<change-id>/`.
Any other OpenSpec or product-code diff SHALL be `implementation`. Origins
`dependabot`, `renovate`, `sentinel`, `bolt`, `palette`, and `jules` SHALL be
`automation` unless the operator overrides. The operator MAY override `kind`
and `remediation_skill` during the plan discussion; the persisted plan SHALL
record the override.

`remediation_skill` SHALL be `iterate-on-plan` for `plan`,
`iterate-on-implementation` for `implementation`, and `none` for cheap-path
`automation`. Non-OpenSpec `other` nodes with unresolved comments SHALL use
`quick-task` unless the operator overrides.

<!-- Scenario ID: merge-pull-requests.heuristic-plan-only -->
#### Scenario: Planning-artifact-only OpenSpec PR is classified plan

- **WHEN** an OpenSpec PR's changed files are all under `openspec/changes/<change-id>/`
- **THEN** `build_plan` SHALL set `kind` to `plan` and `remediation_skill` to `iterate-on-plan`
- **AND** SHALL record `change_id`

<!-- Scenario ID: merge-pull-requests.heuristic-implementation -->
#### Scenario: OpenSpec PR that touches product code is classified implementation

- **WHEN** an OpenSpec PR changes any file outside `openspec/changes/<change-id>/`
- **THEN** `build_plan` SHALL set `kind` to `implementation` and `remediation_skill` to `iterate-on-implementation`

<!-- Scenario ID: merge-pull-requests.operator-kind-override -->
#### Scenario: Operator override is persisted

- **WHEN** the operator changes a node's `kind` during the plan discussion
- **THEN** the persisted plan SHALL store the overridden `kind` and matching `remediation_skill`
- **AND** later execution SHALL use the persisted values, not re-run the heuristic as authority

### Requirement: Operator Plan Discussion

Before any merge, refresh, or iterate side effect, the skill SHALL present the
plan (merge order, dependency edges including operator-inserted runtime
prerequisites, kind, cheap-path vs remediate, deferrals, obsolete closes) and
SHALL wait for operator approval of that plan revision.

<!-- Scenario ID: merge-pull-requests.plan-approval-before-side-effects -->
#### Scenario: Unapproved plan is not executed

- **WHEN** analysis has written a plan but the operator has not approved it
- **THEN** the skill SHALL NOT invoke `--execute`, iterate skills, `refresh_branch`, or merge
- **AND** SHALL persist the unapproved revision so a later session can resume the discussion

### Requirement: Orchestrated Iterate Remediation

For a ready node whose `remediation_skill` is `iterate-on-plan` or
`iterate-on-implementation`, the conductor SHALL invoke that skill against the
node's `change_id` in a managed worktree, passing `--vendor-review`. Iterate
SHALL own every commit on the PR branch. The merge kernel (`execute_plan.py`)
SHALL NOT check out, commit, or push to the PR branch.

`/iterate-on-plan` SHALL run only while the proposal is unapproved.
`/iterate-on-implementation` SHALL run only when the proposal is already
approved. A node that violates that precondition SHALL halt with a blocking
reason rather than invoking the wrong iterate skill.

After iterate converges (findings below threshold, or max iterations plus one
vendor-review remediation cycle), the conductor SHALL re-enter `--execute --pr`
for that node. Vendor disagreement on a blocking finding SHALL leave the node
`pending` and SHALL NOT merge. Unanimous vendor agreement SHALL NOT by itself
release `proposal_acceptance` or any other human gate.

<!-- Scenario ID: merge-pull-requests.plan-node-invokes-iterate-on-plan -->
#### Scenario: Plan-only node is remediated via iterate-on-plan

- **WHEN** a ready node has `remediation_skill=iterate-on-plan` and an unapproved proposal
- **THEN** the conductor SHALL invoke `/iterate-on-plan <change-id> --vendor-review` in a managed worktree
- **AND** SHALL NOT invoke `/iterate-on-implementation` for that node
- **AND** `execute_plan.py` SHALL NOT modify the PR branch's code

<!-- Scenario ID: merge-pull-requests.impl-node-invokes-iterate-on-implementation -->
#### Scenario: Implementation node is remediated via iterate-on-implementation

- **WHEN** a ready node has `remediation_skill=iterate-on-implementation` and an approved proposal
- **THEN** the conductor SHALL invoke `/iterate-on-implementation <change-id> --vendor-review` in a managed worktree
- **AND** SHALL NOT invoke `/iterate-on-plan` for that node

<!-- Scenario ID: merge-pull-requests.wrong-iterate-precondition-halts -->
#### Scenario: Wrong iterate precondition halts

- **WHEN** a `plan` node has an already-approved proposal, or an `implementation` node has an unapproved proposal
- **THEN** the conductor SHALL leave the node `pending` with a blocking reason
- **AND** SHALL NOT invoke either iterate skill

<!-- Scenario ID: merge-pull-requests.disagreement-does-not-merge -->
#### Scenario: Vendor disagreement blocks merge

- **WHEN** iterate vendor review reports a disagreement on a finding at or above the remediation threshold
- **THEN** the node `outcome` SHALL remain `pending`
- **AND** the merge operation SHALL NOT be invoked

### Requirement: Cheap Path for Scoped Automation

Nodes with `kind=automation` SHALL skip iterate and skip merge-time vendor
review when live CI is green and unresolved comment count is zero. They SHALL
merge with the existing origin strategy subject to the live `can_merge` and
security-check backstops. Unresolved comments or failing CI SHALL drop the node
out of the cheap path.

<!-- Scenario ID: merge-pull-requests.cheap-path-merges -->
#### Scenario: Green Dependabot node merges without iterate

- **WHEN** a `dependabot` node has green CI and zero unresolved comments
- **THEN** execution SHALL merge it with the origin squash strategy
- **AND** SHALL NOT invoke iterate skills
- **AND** SHALL NOT dispatch `vendor_review.py`

<!-- Scenario ID: merge-pull-requests.cheap-path-dropped-on-comments -->
#### Scenario: Automation node with comments leaves the cheap path

- **WHEN** a `jules` node has unresolved review comments
- **THEN** the node SHALL NOT be treated as cheap-path
- **AND** SHALL halt with a recorded comment summary and a `quick-task` delegation
- **AND** SHALL NOT modify the PR branch from `execute_plan.py`

### Requirement: CI Failure Class in Analysis

The analysis round SHALL classify each failing-CI node as `transient`,
`pr_specific`, or `stale_base` and SHALL present that class in the plan
discussion. File-overlap and stacked-base edges remain mechanical. Runtime
prerequisite edges that the overlap deriver cannot see (for example a migration
another PR lands) SHALL be insertable by the operator via `amend_plan()` before
approval.

<!-- Scenario ID: merge-pull-requests.stale-base-class-surfaced -->
#### Scenario: Identical CI failure on files a PR did not touch is stale_base

- **WHEN** the same check fails on three or more unrelated PRs in files those PRs did not modify
- **THEN** analysis SHALL label those nodes `stale_base`
- **AND** SHALL recommend `refresh-branch` after the prerequisite that fixes the base, not `rerun-checks`

<!-- Scenario ID: merge-pull-requests.operator-runtime-edge -->
#### Scenario: Operator inserts a runtime prerequisite edge

- **WHEN** the operator approves a plan that adds a dependency from PR B to PR A for a reason other than file overlap
- **THEN** the plan SHALL persist that edge with an `inserted_reason`
- **AND** execution of B SHALL wait until A's `outcome` is `merged`

### Requirement: Per-Node Agent Compact

After a node is persisted `outcome=merged`, the conductor SHALL request agent
context compact (or equivalent fresh context) and SHALL resume the next ready
node from `merge-plan.json` plus the next PR number. The merge plan SHALL be
the resume artifact. The conductor SHALL NOT write or require autopilot
`loop-state.json`. Main-context convergence SHALL remain exactly once per
invocation that merged one or more pull requests.

<!-- Scenario ID: merge-pull-requests.compact-after-merge -->
#### Scenario: Compact is requested after each successful merge

- **WHEN** `--execute --pr N` persists `outcome=merged`
- **THEN** the conductor SHALL request `/compact` (or equivalent) before executing another node
- **AND** the next execution SHALL load the same plan file rather than re-running analysis from scratch

<!-- Scenario ID: merge-pull-requests.no-autopilot-loop-state -->
#### Scenario: Merge resume does not use autopilot loop-state

- **WHEN** the conductor resumes after compact
- **THEN** it SHALL seed context from `merge-plan.json` and the target PR number
- **AND** SHALL NOT read or write `openspec/changes/<id>/loop-state.json` for merge-pass control

### Requirement: Sync-Point Released Around Remediation

The exclusive main sync-point guard SHALL apply to refresh, merge, close, and
convergence. It SHALL NOT be held across an iterate invocation. After iterate
returns, and before `refresh_branch` or merge, execution SHALL re-run the
active-agent guard. The conductor SHALL NOT auto-pass `--force`.

<!-- Scenario ID: merge-pull-requests.iterate-not-under-sync-point -->
#### Scenario: Iterate worktrees are not created while the merge sync-point is held

- **WHEN** the conductor is about to invoke an iterate skill
- **THEN** it SHALL NOT hold the exclusive main sync-point lock
- **AND** iterate SHALL create its managed feature worktree as that skill already specifies

<!-- Scenario ID: merge-pull-requests.recheck-guard-after-iterate -->
#### Scenario: Merge re-checks the active-agent guard after iterate

- **WHEN** iterate has returned and `--execute --pr N` is about to refresh or merge
- **THEN** execution SHALL run the active-agent sync-point guard
- **AND** if an iterate worktree is still registered as active, execution SHALL block and SHALL NOT auto-force

