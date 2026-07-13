## ADDED Requirements

### Requirement: Opt-in pre-push enforcement gate

The system SHALL provide an opt-in `pre-push` git hook that runs the critical
subset of `validate-feature` and blocks the push when any critical finding is
unresolved. The gate SHALL NOT be enabled by default. Two independent conditions
SHALL both hold for the gate to run, and the opt-in installer SHALL establish both
(and verify them): (a) the `pre-push` hook must actually be wired for the repo —
because `core.hooksPath` is *local* git config not guaranteed on a fresh clone, the
installer SHALL set and verify `core.hooksPath=.githooks` (or install a forwarding
`.git/hooks/pre-push`) so the hook is genuinely invoked; and (b) the gate must be
explicitly enabled via a `validate-gate.enabled` marker. Because the hook may be
present in `.githooks` before opt-in, the checked-in hook SHALL be **inert** — a
no-op that exits 0 — until the marker is set, so it never fires for someone who
happens to have `core.hooksPath=.githooks` without opting in. Enabling the gate is
this installer action, not merely the presence of the hook file.

#### Scenario: Checked-in hook is inert until enabled

- **WHEN** a developer already has `core.hooksPath=.githooks` and pulls the change
  that adds `.githooks/pre-push`, without running the gate opt-in
- **THEN** `git push` SHALL behave exactly as before (the hook exits 0 without
  running any checks)

#### Scenario: Opt-in wires the hook on a fresh clone

- **WHEN** the operator runs the gate opt-in in a fresh clone that has no
  `core.hooksPath` set (hooks resolve to `.git/hooks`)
- **THEN** the installer SHALL set and verify the hook wiring (`core.hooksPath=.githooks`
  or a forwarding `.git/hooks/pre-push`) and set the `validate-gate.enabled` marker
- **AND** a subsequent `git push` SHALL actually invoke the `pre-push` gate and run
  the critical subset — the enforcement SHALL NOT be silently skipped

#### Scenario: Marker without wiring does not silently disable enforcement

- **WHEN** the `validate-gate.enabled` marker is set but the hook is not wired for
  the repo
- **THEN** the opt-in SHALL be considered incomplete and SHALL report the missing
  wiring, rather than leaving the operator believing the gate is active

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
task-checkbox drift gate, and the **static** `security` checks (dependency audit,
secret scan, and any SAST that needs no running service). It SHALL NOT run the
heavyweight deploy / E2E / gen-eval phases, nor the **dynamic** security scan
(e.g. ZAP) that requires a live deployment. As a general rule, because the gate
excludes deploy, any gate check that depends on a live service and cannot actually
exercise it (records a `skip` or `not-run` for lack of services) SHALL be treated
as an unresolved critical result rather than a silent pass — so a green gate always
means every included check genuinely ran.

#### Scenario: Task-drift detected at push time

- **WHEN** the gate runs and `tasks.md` has unchecked boxes while the branch has
  commits since `main`
- **THEN** the gate SHALL produce a critical finding and block the push
- **AND** the message SHALL reference the specific unchecked task IDs

#### Scenario: Heavyweight and live-service phases excluded from the gate

- **WHEN** the `pre-push` gate runs
- **THEN** it SHALL NOT start a Docker deploy, run the E2E / gen-eval phases, or
  run the dynamic (ZAP) security scan that needs a live deployment
- **AND** the `security` check it does run SHALL be limited to the static checks
  (dependency audit, secret scan, service-free SAST)

#### Scenario: A live-service check that cannot run blocks the push

- **WHEN** a gate check that needs a live service (e.g. `smoke`) records a `skip`
  or `not-run` status because no services are available
- **THEN** the gate SHALL treat that as an unresolved critical result and block
  the push with a non-zero exit
- **AND** the message SHALL explain that smoke could not be exercised and list the
  escape hatches, so smoke is never silently bypassed at the gate

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
