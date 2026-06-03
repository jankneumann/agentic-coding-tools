## ADDED Requirements

### Requirement: Shared refine-core module

The system SHALL provide a reusable `refine-core` module that exposes the
iterate → synthesize → fix → validate primitives currently embedded in
`convergence_loop.py`, so that multiple callers can consume them without editing
the convergence loop directly.

#### Scenario: Convergence loop delegates to refine-core

- **WHEN** the autopilot convergence loop runs after `refine-core` is extracted
- **THEN** `convergence_loop.converge()` SHALL delegate its iterate/synthesize/
  fix/validate steps to `refine-core`
- **AND** existing convergence behavior and outputs SHALL be unchanged
  (the extraction is behavior-preserving)

#### Scenario: Independent caller consumes refine-core

- **WHEN** a caller other than the autopilot loop needs review-fix iteration
- **THEN** it SHALL import `refine-core` primitives directly
- **AND** it SHALL NOT need to import or modify `convergence_loop.py`

### Requirement: Standalone refine entry point

The system SHALL provide a low-ceremony "fix until clean" entry point built on
`refine-core` that operates on an arbitrary branch or commit range without
requiring an OpenSpec change, work-packages, or the full autopilot pipeline.

#### Scenario: Refine a commit range without OpenSpec ceremony

- **WHEN** the operator invokes the standalone refine entry point against a
  branch or commit range
- **THEN** it SHALL run review → fix → re-review iterations over that range
  using `refine-core`
- **AND** it SHALL NOT require an `openspec/changes/<id>/` directory or
  `work-packages.yaml` to exist

#### Scenario: Refine terminates on clean or max iterations

- **WHEN** the standalone refine loop runs
- **THEN** it SHALL terminate when no blocking findings remain (clean) or when a
  configured maximum iteration count is reached
- **AND** it SHALL report the terminal status and remaining findings to the
  ledger
