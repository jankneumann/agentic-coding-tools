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
The skill SHALL integrate with the existing OpenSpec cleanup workflow for PRs that are OpenSpec-driven.

#### Scenario: Merge OpenSpec PR
- **WHEN** an OpenSpec PR is merged
- **THEN** the skill SHALL note the change-id and recommend running `/cleanup-feature <change-id>` for archival

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

