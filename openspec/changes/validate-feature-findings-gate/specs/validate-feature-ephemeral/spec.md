## ADDED Requirements

### Requirement: Ephemeral disposable-worktree mode

The system SHALL accept a `--ephemeral` flag that runs validation against a
throwaway scratch worktree cloned from the current `HEAD`, leaving the branch
under test unmodified. To avoid validating a stale tree, `--ephemeral` SHALL fail
fast with a clear error when the working tree has uncommitted (staged or unstaged)
changes, unless the operator passes `--include-dirty` to materialize the exact
working-tree and index state into the scratch worktree. The commit (or
materialized tree) that was actually validated SHALL be recorded in the findings
file and report.

#### Scenario: Validation runs in a disposable worktree

- **WHEN** `validate-feature <change-id> --ephemeral` is invoked on a clean tree
- **THEN** the system SHALL create a scratch worktree at the current `HEAD`
- **AND** all deploy artifacts, security-scan output, and log files SHALL be
  written inside the scratch worktree
- **AND** the validated commit SHA SHALL be recorded in `validation-findings.json`
  and the report

#### Scenario: Dirty worktree fails fast

- **WHEN** `--ephemeral` is invoked and the working tree has uncommitted changes
- **THEN** the run SHALL abort with an error explaining that `HEAD` would validate
  a stale tree
- **AND** the message SHALL name `--include-dirty` as the opt-in to validate the
  exact working-tree/index state instead

#### Scenario: Scratch worktree discarded on completion

- **WHEN** an `--ephemeral` run finishes (pass or fail)
- **THEN** the scratch worktree SHALL be removed
- **AND** the branch under test SHALL contain no validation residue

### Requirement: Report still lands on the change branch

Even in ephemeral mode, the validation report and findings file SHALL be
persisted to the change branch so results are durable after the scratch worktree
is discarded.

#### Scenario: Report persisted before teardown

- **WHEN** an `--ephemeral` run produces a report and findings file
- **THEN** those artifacts SHALL be copied to
  `openspec/changes/<change-id>/` on the change branch before the scratch
  worktree is removed

### Requirement: Cloud-harness fallback

`--ephemeral` SHALL fall back to the existing in-place validation behavior in a
cloud-harness environment (as detected by the shared environment profile),
rather than creating a worktree.

#### Scenario: Cloud environment skips worktree creation

- **WHEN** `--ephemeral` is requested and `environment_profile.detect()` reports
  a cloud-harness environment
- **THEN** the system SHALL run validation in place
- **AND** SHALL log that ephemeral mode was downgraded for the cloud harness
