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
newly produced or changed `validation-report.md`, `validation-findings.json`,
and `architecture-impact.md` to the change checkout and SHALL record the exact
validated commit and tree in the report and findings artifacts.

#### Scenario: Validation residue is discarded

- **WHEN** an ephemeral run produces reports, logs, scanner output, and deploy residue
- **THEN** only the report, findings, and architecture-impact files SHALL be copied back
- **AND** every other scratch artifact SHALL be discarded with the worktree

#### Scenario: Stale evidence is not restamped

- **WHEN** validation exits before changing a pre-existing report or findings file
- **THEN** that artifact SHALL remain byte-for-byte unchanged

### Requirement: Validation paths fail closed

The system SHALL validate the change identifier, enforce resolved containment
for change, scratch, and artifact paths, reject symlink artifact endpoints, and
atomically replace every copied-back artifact.

#### Scenario: A path attempts to escape its boundary

- **WHEN** a change identifier or resolved symlink path escapes its declared parent
- **THEN** validation SHALL fail before copying or deleting filesystem content

### Requirement: The ephemeral phase boundary is executable

The system SHALL provide concrete prepare and finalize commands that allow the
validation phases through report persistence to run in scratch, copy the durable
allowlist back, remove scratch, and then perform session-log/handoff bookkeeping
in the source checkout.

#### Scenario: A CLI validation run finalizes successfully

- **WHEN** the prepare command creates scratch and the validation phases produce durable artifacts
- **THEN** finalize SHALL copy the allowlist and remove scratch
- **AND** subsequent session-log/handoff writes SHALL target the source checkout

### Requirement: Existing harness isolation is reused

When the shared environment profile reports that isolation is already provided,
the system SHALL run in place, log the downgrade, and SHALL NOT create or remove
a nested worktree.

#### Scenario: Cloud harness downgrades to in-place

- **WHEN** `--ephemeral` is requested under a cloud harness
- **THEN** validation SHALL use the harness checkout
- **AND** the downgrade reason SHALL be logged
