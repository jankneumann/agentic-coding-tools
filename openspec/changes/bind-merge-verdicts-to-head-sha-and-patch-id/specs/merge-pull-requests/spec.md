## MODIFIED Requirements

### Requirement: Durable Merge Plan Artifact

The skill SHALL emit a durable merge plan from every default analysis round so
triage state survives a context clear and can seed fresh-context execution. The
plan SHALL be written as machine-readable `merge-plan.json` conforming to
schema version `1.2` of `contracts/merge-plan.schema.json`, accompanied by a
rendered human-readable `merge-plan.md` projection. For each PR node the plan
SHALL record: PR number, origin classification, `kind`, `change_id` when known,
`remediation_skill`, staleness, CI/gate state, CI-failure class when CI is
failing, unresolved-comment count, merge strategy, an `auto_executable` flag,
optional `gate` markers, dependency edges to other nodes, optional
`inserted_reason` on operator-inserted edges, and a mutable `outcome`
(`pending`, `in_progress`, `merged`, `closed`, `deferred`, or `failed`).
Node state SHALL additionally carry the bound `vendor_verdict` (including its
verdict binding) and an optional `review_waiver`; it SHALL NOT carry
`iterate_consensus_path`. Loading a plan whose `schema_version` is not `1.2`
SHALL fail with a message instructing the operator to rebuild the plan.
The Markdown projection SHALL surface each node's current CI state, kind,
remediation skill, staleness, unresolved-comment count and summary, and
blocking reason. JSON and Markdown persistence SHALL be atomic as a unit or
recoverably consistent: if a write is interrupted, the authoritative JSON SHALL
be sufficient to repair the projection.

#### Scenario: Analysis round emits a durable plan

- **WHEN** the operator runs the default analysis round
- **THEN** the skill SHALL write `merge-plan.json` validating against schema version 1.2
- **AND** SHALL render a `merge-plan.md` projection of the same state
- **AND** each open PR SHALL appear as a node with `outcome` initialised to `pending` and a populated `kind`

#### Scenario: Dependency edges are derived from file overlap and base branch

- **WHEN** two PR nodes modify one or more of the same files, or one targets the other's branch
- **THEN** the plan SHALL record a dependency edge between them
- **AND** the rendered `merge-plan.md` SHALL surface conflicting-pair edges to the operator

<!-- Scenario ID: merge-pull-requests.plan-1-1-rejected -->
#### Scenario: A schema 1.1 plan is rejected rather than migrated

- **WHEN** execution loads a `merge-plan.json` whose `schema_version` is `1.1`
- **THEN** loading SHALL fail before any live-state call or side effect
- **AND** the error SHALL instruct the operator to rebuild the plan with the analysis round

### Requirement: Plan-Driven Single-PR Execution

The skill SHALL support executing a single PR from a plan with fresh context,
decoupled from the analysis round. Invoked as `--execute <plan> --pr <n>`,
execution SHALL re-check live PR and CI state (never trusting the snapshot
alone), including the live head SHA, refresh the branch if stale, skip
merge-time `vendor_review.py` when the node's stored `vendor_verdict` has
currency `current` or `rebased` against the live PR, otherwise run vendor
review, merge using the node's strategy subject to gate rules, and write the
resulting `outcome` back to the plan. After a successful merge, execution SHALL
mark every downstream node depending on the merged node for re-validation
before it is executed.
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
NOT permanently block the refreshed PR. Every path to the merge operation,
including the skip path, SHALL pass through the same total review predicate:
the merge SHALL be blocked unless the node carries a bound, current-or-rebased,
independent consensus verdict with zero blocking findings, or a recorded
`review_waiver`. Dispatch failure, the absence of a consensus verdict, an
ineligible review without a waiver, a stale verdict, and a non-independent
verdict SHALL each block the merge. Execution SHALL NOT check out, commit, or
push to the PR branch.

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

- **WHEN** a node is eligible for vendor review, its stored verdict is absent or `stale`, and dispatch errors or returns no consensus verdict
- **THEN** execution SHALL keep the node pending with the blocking reason recorded
- **AND** SHALL NOT invoke the merge operation

<!-- Scenario ID: merge-pull-requests.skip-pr-diff-review-after-iterate -->
#### Scenario: A current or rebased stored verdict skips merge-time PR-diff review

- **WHEN** a node's stored `vendor_verdict` carries a binding whose currency against the live PR is `current` or `rebased`, and the verdict is independent with zero blocking findings
- **THEN** `--execute` SHALL skip `vendor_review.py` for that node
- **AND** the skip SHALL pass through the same total review predicate as a fresh review
- **AND** SHALL still enforce `proposal_acceptance`, security-check, and `can_merge` gates

<!-- Scenario ID: merge-pull-requests.ineligible-without-waiver-blocks -->
#### Scenario: An ineligible review without a waiver blocks

- **WHEN** vendor review eligibility is `draft_pr`, `changes_requested`, missing, or a reason outside the policy-waivable set, and the node has no operator waiver
- **THEN** execution SHALL keep the node pending with a blocking reason naming the eligibility reason
- **AND** SHALL NOT invoke the merge operation

#### Scenario: Execution respects the security-check backstop

- **WHEN** a node would be merged past a failing required security check
- **THEN** execution SHALL defer to the auto-mode classifier and SHALL NOT bypass it automatically
- **AND** the node `outcome` SHALL remain `pending` with the blocking reason recorded

### Requirement: Cheap Path for Scoped Automation

Nodes with `kind=automation` SHALL skip iterate and skip merge-time vendor
review when live CI is green and unresolved comment count is zero. Taking the
cheap path SHALL record a `review_waiver` with `source: policy` and
`eligibility_reason: automation_cheap_path` in node state before the merge, so
the skip is visible in the plan and in `_review_evidence` rather than implicit.
They SHALL merge with the existing origin strategy subject to the live
`can_merge` and security-check backstops. Unresolved comments or failing CI
SHALL drop the node out of the cheap path.

<!-- Scenario ID: merge-pull-requests.cheap-path-merges -->
#### Scenario: Green Dependabot node merges without iterate

- **WHEN** a `dependabot` node has green CI and zero unresolved comments
- **THEN** execution SHALL merge it with the origin squash strategy
- **AND** SHALL NOT invoke iterate skills
- **AND** SHALL NOT dispatch `vendor_review.py`
- **AND** SHALL record `state.review_waiver` with `source: policy` and `eligibility_reason: automation_cheap_path`

<!-- Scenario ID: merge-pull-requests.cheap-path-dropped-on-comments -->
#### Scenario: Automation node with comments leaves the cheap path

- **WHEN** a `jules` node has unresolved review comments
- **THEN** the node SHALL NOT be treated as cheap-path
- **AND** SHALL halt with a recorded comment summary and a `quick-task` delegation
- **AND** SHALL NOT modify the PR branch from `execute_plan.py`

## ADDED Requirements

### Requirement: Verdict Binding and Currency

Every review result that execution stores in `state.vendor_verdict` SHALL carry
a verdict binding recording `head_sha` (the PR head at review time), `patch_id`
(`git patch-id --stable` over the PR diff, read without checking out the PR
branch), `reviewer` (`vendor`, `family`, `model`, `agent_id` per successful
reviewer), `author` (`login`, `vendor`, `session_id`, each `null` when it
cannot be derived), and `bound_at`. A single pure function SHALL classify a
binding against live PR state as `current` when the head SHA is unchanged,
`rebased` when the head SHA differs and the patch-id is identical, and `stale`
otherwise, including when either patch-id cannot be computed. A `stale`
verdict SHALL block the merge with a reason of the form
`stale verdict: reviewed <sha7>, live <sha7>`.

<!-- Scenario ID: merge-pull-requests.verdict-current -->
#### Scenario: Unchanged head is current

- **WHEN** the binding's `head_sha` equals the live PR head SHA
- **THEN** currency SHALL be `current`

<!-- Scenario ID: merge-pull-requests.verdict-rebased -->
#### Scenario: A rebase with an identical diff keeps the verdict

- **WHEN** a branch is rebased onto a moved base so its head SHA changes but its diff is identical
- **THEN** currency SHALL be `rebased`
- **AND** execution SHALL accept the stored verdict without re-dispatching vendor review

<!-- Scenario ID: merge-pull-requests.verdict-stale -->
#### Scenario: A changed diff makes the verdict stale

- **WHEN** a commit that changes the diff is pushed after the verdict was bound
- **THEN** currency SHALL be `stale`
- **AND** the blocking reason SHALL name the reviewed and live short SHAs

<!-- Scenario ID: merge-pull-requests.verdict-unbound-stale -->
#### Scenario: An uncomputable patch-id is stale

- **WHEN** the head SHA differs and either the stored or the live patch-id is missing
- **THEN** currency SHALL be `stale`

### Requirement: Reviewer Independence

Vendor review dispatch SHALL exclude both `claude_code` and the PR author's
vendor when it is known. Independently of dispatch, the review predicate SHALL
reject a verdict when any successful reviewer's `(vendor, agent_id)` equals the
author's `(vendor, session_id)`, and SHALL reject it when a successful
reviewer's vendor equals the author's vendor while the author session is
unknown. A reviewer in the same model family as the author but with a different
identity SHALL be accepted and recorded as `same_family: true`. The
author SHALL be derived from the PR author login and the head commits'
`Co-Authored-By:` and `*-Session:` trailers.

<!-- Scenario ID: merge-pull-requests.self-review-rejected -->
#### Scenario: A self-review is rejected

- **WHEN** a successful reviewer's `(vendor, agent_id)` equals the author's `(vendor, session_id)`
- **THEN** the predicate SHALL block the merge with a reason naming the independence violation

<!-- Scenario ID: merge-pull-requests.unknown-author-same-vendor-rejected -->
#### Scenario: Same vendor with unknown author session is rejected

- **WHEN** a successful reviewer's vendor equals the author's vendor and the author `session_id` is `null`
- **THEN** the predicate SHALL block the merge because independence cannot be shown

<!-- Scenario ID: merge-pull-requests.same-family-recorded -->
#### Scenario: A same-family reviewer is accepted and recorded

- **WHEN** a successful reviewer shares the author's model family but not its identity
- **THEN** the predicate SHALL NOT block on independence
- **AND** the binding SHALL record `same_family: true`

### Requirement: Recorded Review Waivers

A merge without a bound consensus verdict SHALL be permitted only when node
state carries a `review_waiver` with `reason`, `source` (`policy` or
`operator`), `approver`, `recorded_at`, and `eligibility_reason`. Execution
SHALL record a `policy` waiver only when the live ineligibility reason is in
the closed set `skip_origin`, `small_pr`, `has_approval`, `low_risk_judged`,
or `automation_cheap_path`. An operator SHALL be able to record an `operator`
waiver with `--waive-review "<reason>"` alongside `--execute <plan> --pr <n>`;
an empty or whitespace-only reason SHALL be rejected with exit code 2 before
any side effect. Every waiver SHALL appear in the merged result's
`vendor_review` evidence and in the merge event log.

<!-- Scenario ID: merge-pull-requests.policy-waiver-recorded -->
#### Scenario: A policy-waivable ineligibility records a waiver

- **WHEN** live eligibility is ineligible with reason `small_pr`
- **THEN** execution SHALL record `state.review_waiver` with `source: policy` and `eligibility_reason: small_pr` before merging
- **AND** the merged result's `vendor_review` evidence SHALL include the waiver

<!-- Scenario ID: merge-pull-requests.operator-waiver-recorded -->
#### Scenario: An operator waiver unblocks a review-blocked node

- **WHEN** the operator runs `--execute <plan> --pr <n> --waive-review "hotfix approved in incident channel"` for a node otherwise blocked by review
- **THEN** execution SHALL record `state.review_waiver` with `source: operator` and the given reason
- **AND** the merge event log SHALL contain the waiver reason

<!-- Scenario ID: merge-pull-requests.operator-waiver-empty-rejected -->
#### Scenario: An empty operator waiver reason is rejected

- **WHEN** the operator passes `--waive-review ""` or a whitespace-only reason
- **THEN** the command SHALL exit with code 2
- **AND** SHALL NOT claim, refresh, or merge the node

### Requirement: Head-Pinned Merge

The merge operation SHALL pass the live head SHA that the review predicate
evaluated to GitHub as `--match-head-commit <sha>`, on both the direct
`gh pr merge` path and the merge-queue path, so a push between the check and
the merge makes the merge fail instead of landing unreviewed code. Live PR
status SHALL include the head SHA (`headRefOid`).

<!-- Scenario ID: merge-pull-requests.merge-pinned -->
#### Scenario: The merge command is pinned to the checked head

- **WHEN** execution invokes the merge for a node whose live head SHA is `abc1234…`
- **THEN** the `gh pr merge` arguments SHALL include `--match-head-commit abc1234…`
- **AND** the merge-queue path SHALL pass the same SHA

<!-- Scenario ID: merge-pull-requests.merge-push-race-fails -->
#### Scenario: A push after the check fails the merge

- **WHEN** GitHub rejects the merge because the head no longer matches the pinned SHA
- **THEN** execution SHALL keep the node pending with a blocking reason naming the head mismatch
- **AND** SHALL NOT record `outcome: merged`
