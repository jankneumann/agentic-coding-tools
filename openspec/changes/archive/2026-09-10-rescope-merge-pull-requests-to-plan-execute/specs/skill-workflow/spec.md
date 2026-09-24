# skill-workflow — Delta Spec

## ADDED Requirements

### Requirement: Merge Conductor Invokes Iterate Skills

`/merge-pull-requests` in its default plan-then-execute path SHALL be allowed to
invoke `/iterate-on-plan` and `/iterate-on-implementation` as remediations for
open pull requests. Those invocations SHALL run in the iterate skill's managed
feature worktree and SHALL NOT write `main`. The merge skill remains the
user-invoked sync-point for merges into `main`.

<!-- Scenario ID: skill-workflow.merge-invokes-iterate -->
#### Scenario: Merge-triggered iterate writes the feature branch only

- **WHEN** `/merge-pull-requests` invokes `/iterate-on-plan` or `/iterate-on-implementation` for a node
- **THEN** iterate SHALL enter or create the change's managed worktree before any mutation
- **AND** SHALL commit on the feature branch
- **AND** SHALL NOT commit to local `main`

<!-- Scenario ID: skill-workflow.merge-still-sync-point -->
#### Scenario: Merge remains the only main writer in the loop

- **WHEN** iterate returns and the node is mergeable
- **THEN** only `/merge-pull-requests` SHALL merge into `main`
- **AND** iterate SHALL NOT call `gh pr merge` or otherwise land the PR

### Requirement: Iterate Multi-Vendor Review Required When Called From Merge

When `/iterate-on-plan` or `/iterate-on-implementation` is invoked by the merge
conductor, multi-vendor review SHALL run as the iterate exit (the existing
`--vendor-review` path, which is already automatic in the coordinated tier).
The merge conductor SHALL pass `--vendor-review` explicitly so sequential-tier
sessions still dispatch. Disagreement on a finding at or above the remediation
threshold SHALL escalate to a human and SHALL NOT be treated as a merge signal.
Unanimous agreement SHALL NOT by itself prove correctness or release an
OpenSpec `proposal_acceptance` gate.

<!-- Scenario ID: skill-workflow.merge-iterate-always-vendor-review -->
#### Scenario: Merge-triggered iterate always requests vendor review

- **WHEN** the merge conductor invokes iterate for a node
- **THEN** the invocation SHALL include `--vendor-review`
- **AND** iterate SHALL dispatch `/parallel-review-plan` or `/parallel-review-implementation` after the iterate loop (subject to vendor CLI availability)
- **AND** a blocking disagreement SHALL be returned to the merge conductor as a halt, not a merge

## MODIFIED Requirements

### Requirement: Merge Log Artifact

The `/merge-pull-requests` skill SHALL produce a dated merge log capturing
plan-level reasoning (merge order, kind overrides, runtime edges, remediations,
compact/resume), user decisions, and observations.

#### Scenario: Merge log written to dated file
- **WHEN** `/merge-pull-requests` completes a merge session
- **THEN** it SHALL write to `docs/merge-logs/YYYY-MM-DD.md` (using the current date)
- **AND** the entry SHALL contain: session timestamp (HH:MM), agent type, plan revision identity, PR table (PR number, origin, kind, action, rationale), iterate remediations run, vendor review / disagreement outcomes, user decisions, and observations

#### Scenario: Merge log directory auto-creation
- **WHEN** `/merge-pull-requests` attempts to write the merge log and `docs/merge-logs/` does not exist
- **THEN** the skill SHALL create the directory before writing
- **AND** the repository SHALL contain `docs/merge-logs/.gitkeep` to ensure directory persistence after initial setup

#### Scenario: Multiple merge sessions on same day
- **WHEN** multiple merge sessions occur on the same day
- **THEN** each session SHALL append to the existing day's file separated by a horizontal rule
- **AND** each entry SHALL include its own session timestamp

#### Scenario: Merge log captures cross-PR reasoning
- **WHEN** merge plan decisions span multiple PRs
- **THEN** the merge log SHALL capture the reasoning that connects them (order, runtime edges, cheap-path vs remediate)
- **AND** SHALL record user steering decisions (kind overrides, deferrals, close-obsolete)

#### Scenario: Merge log captures vendor review findings
- **WHEN** vendor reviews were dispatched during iterate remediations or residual merge-time review
- **THEN** the merge log SHALL summarize confirmed findings, unconfirmed findings, disagreements, and blocking issues per PR

#### Scenario: Vendor review incomplete or timed out
- **WHEN** vendor reviews were dispatched but one or more vendors did not respond or timed out
- **THEN** the merge log SHALL note which vendors responded and which timed out
- **AND** SHALL record findings from responding vendors only

#### Scenario: PR comments for contributor visibility
- **WHEN** a PR is closed or skipped during the pass
- **THEN** the skill SHALL still post a brief PR comment explaining the action
- **AND** the detailed rationale SHALL be in the merge log, not duplicated in the PR comment

#### Scenario: Merge log sanitization
- **WHEN** a merge-log entry is written
- **THEN** the skill SHALL run `sanitize_session_log.py` on the file before committing
- **AND** the agent SHALL verify the sanitized output using the same criteria as session-log verification

### Requirement: Merge-Time Review Resilience

When `/merge-pull-requests` still dispatches PR-diff vendor review (nodes
without a current iterate consensus artifact), that dispatch SHALL handle PRs
regardless of whether planning artifacts exist. Nodes that completed iterate
with a consensus artifact whose HEAD matches the live PR head SHALL skip this
PR-diff dispatch; iterate's `/parallel-review-*` output is the review of record
for those nodes.

#### Scenario: Vendor review for PR with universal artifacts
- **WHEN** a PR has contracts and work-packages in its change directory and merge-time PR-diff review runs
- **THEN** vendor review SHALL include contract and scope information in the review prompt

#### Scenario: Vendor review for PR without planning artifacts
- **WHEN** a PR lacks contracts or work-packages (legacy, external contribution, non-OpenSpec) and merge-time PR-diff review runs
- **THEN** vendor review SHALL proceed using only the PR diff as context
- **AND** the review SHALL NOT fail or skip due to missing artifacts

#### Scenario: Iterate consensus is the review of record
- **WHEN** a node completed iterate with a consensus artifact matching the live PR head
- **THEN** merge-time PR-diff vendor review SHALL be skipped
- **AND** the merge log SHALL cite the iterate consensus path instead
