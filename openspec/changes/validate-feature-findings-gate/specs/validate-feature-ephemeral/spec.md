## ADDED Requirements

### Requirement: Validation can run in a disposable worktree

The system SHALL accept a `--ephemeral` validation mode that runs against a
detached scratch worktree at the current `HEAD`, records the validated commit
and tree, and removes the scratch worktree when validation completes or raises.

#### Scenario: Clean validation is isolated and removed

- **WHEN** `validate-feature <change-id> --ephemeral` runs from a clean local checkout
- **THEN** validation SHALL run in a detached scratch worktree at the source `HEAD`
- **AND** the scratch worktree SHALL be removed on pass or failure

### Requirement: Dirty validation input is explicit

The system SHALL refuse ephemeral validation when the source index or working
tree is dirty unless `--include-dirty` is present. With that opt-in, it SHALL
materialize staged, unstaged, and untracked state without mutating the source and
SHALL record the resulting Git tree.

#### Scenario: Dirty source fails closed by default

- **WHEN** ephemeral validation sees uncommitted state without `--include-dirty`
- **THEN** it SHALL fail with guidance naming `--include-dirty`

#### Scenario: Include-dirty reproduces the source state

- **WHEN** `--include-dirty` is passed
- **THEN** staged, unstaged, and untracked files SHALL appear in the scratch worktree
- **AND** the source index and working tree SHALL remain unchanged

### Requirement: Only durable validation artifacts survive

Before scratch teardown, the system SHALL persist only
`validation-report.md` and `validation-findings.json` to the change checkout and
SHALL record the exact validated commit and tree in those artifacts.

#### Scenario: Validation residue is discarded

- **WHEN** an ephemeral run produces reports, logs, scanner output, and deploy residue
- **THEN** only the report and findings file SHALL be copied back
- **AND** every other scratch artifact SHALL be discarded with the worktree

### Requirement: Existing harness isolation is reused

When the shared environment profile reports that isolation is already provided,
the system SHALL run in place, log the downgrade, and SHALL NOT create or remove
a nested worktree.

#### Scenario: Cloud harness downgrades to in-place

- **WHEN** `--ephemeral` is requested under a cloud harness
- **THEN** validation SHALL use the harness checkout
- **AND** the downgrade reason SHALL be logged
