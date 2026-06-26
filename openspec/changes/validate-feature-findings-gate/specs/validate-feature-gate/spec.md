## ADDED Requirements

### Requirement: Opt-in pre-push enforcement gate

The system SHALL provide an opt-in `pre-push` git hook that runs the critical
subset of `validate-feature` and blocks the push when any critical finding is
unresolved. The gate SHALL NOT be installed or enabled by default.

#### Scenario: Gate installed on request

- **WHEN** the operator runs the gate installer
- **THEN** a `pre-push` hook SHALL be installed alongside the existing
  `.githooks/pre-commit` and `post-merge` hooks
- **AND** absent that explicit installation, `git push` behavior SHALL be
  unchanged

#### Scenario: Critical finding blocks the push

- **WHEN** the `pre-push` gate runs and the critical subset produces an
  unresolved finding
- **THEN** the push SHALL be blocked with a non-zero exit
- **AND** the block message SHALL list the unresolved critical findings and the
  documented escape hatches

#### Scenario: Green critical subset allows the push

- **WHEN** the `pre-push` gate runs and every critical check passes
- **THEN** the push SHALL proceed normally

### Requirement: Critical subset definition

The gate SHALL run only the critical checks: the `smoke` phase, the spec
task-checkbox drift gate, and the `security` threshold check. It SHALL NOT run
the heavyweight deploy / E2E / gen-eval phases.

#### Scenario: Task-drift detected at push time

- **WHEN** the gate runs and `tasks.md` has unchecked boxes while the branch has
  commits since `main`
- **THEN** the gate SHALL produce a critical finding and block the push
- **AND** the message SHALL reference the specific unchecked task IDs

#### Scenario: Heavyweight phases excluded from the gate

- **WHEN** the `pre-push` gate runs
- **THEN** it SHALL NOT start a Docker deploy or run the E2E / gen-eval phases

### Requirement: Kill-switch and escape hatch

The gate SHALL honor a `VALIDATE_GATE=0` kill-switch and the standard
`git push --no-verify` escape hatch, and SHALL document both at the point of a
block.

#### Scenario: Kill-switch disables the gate

- **WHEN** `VALIDATE_GATE=0` is set in the environment
- **THEN** the `pre-push` gate SHALL skip all checks and allow the push

#### Scenario: No-verify bypass

- **WHEN** the operator pushes with `git push --no-verify`
- **THEN** the gate SHALL not run, per standard git hook semantics
