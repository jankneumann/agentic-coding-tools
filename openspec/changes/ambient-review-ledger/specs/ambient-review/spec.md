## ADDED Requirements

### Requirement: Ambient post-commit review trigger

The system SHALL install a `post-commit` git hook that, when ambient review is
enabled, enqueues a fast single-vendor review of the just-created commit without
blocking the commit operation.

#### Scenario: Commit enqueues an ambient review

- **WHEN** a commit is created in a repository where the `post-commit` hook is
  installed and ambient review is enabled
- **THEN** the hook SHALL enqueue a review task for that commit SHA via the
  coordinator work-queue (or the local fallback queue when the coordinator is
  unreachable)
- **AND** the hook SHALL return exit code 0 within 1 second so the commit is
  never blocked or delayed by review work

#### Scenario: Review runs asynchronously and single-vendor

- **WHEN** an ambient review task is processed
- **THEN** the review SHALL dispatch to exactly one vendor resolved from the
  configured ambient archetype (default fast tier), NOT the multi-vendor
  consensus path used at gates
- **AND** the produced findings SHALL validate against
  `openspec/schemas/review-findings.schema.json` with `review_type` set to a
  value reserved for ambient reviews

### Requirement: Ambient review kill-switch

The system SHALL provide a documented mechanism to disable ambient review for a
repository or session, and ambient review SHALL be on by default once the hook
is installed.

#### Scenario: Operator disables ambient review

- **WHEN** the operator sets the ambient-review kill-switch
  (`REVIEW_AMBIENT=0` environment variable or the equivalent config flag)
- **THEN** the `post-commit` hook SHALL no-op and enqueue no review task
- **AND** the hook SHALL exit 0 so commits proceed normally

#### Scenario: Default-on after install

- **WHEN** the hook is installed and no kill-switch is set
- **THEN** ambient review SHALL be active without any further opt-in step

### Requirement: Ambient review is read-only

Ambient review agents SHALL operate with read-only authority and SHALL NOT
modify files or git state.

#### Scenario: Ambient reviewer attempts no writes

- **WHEN** an ambient review task executes against a commit diff
- **THEN** the reviewer SHALL only read repository contents and write findings to
  the ledger
- **AND** the reviewer SHALL NOT apply fixes, create commits, or mutate the
  working tree
