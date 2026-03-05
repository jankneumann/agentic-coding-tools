# skill-workflow Delta: add-ci-skills-tests

## ADDED Requirements

### Requirement: CI Coverage for Skill Test Suites

The CI pipeline SHALL include a dedicated job that runs the test suites for diagnostic skills (bug-scrub and fix-scrub) on every push and pull request.

- **GIVEN** the CI pipeline runs on push to main or on a pull request
- **WHEN** the `test-skills` job executes
- **THEN** it SHALL run all tests in `skills/bug-scrub/tests/` and `skills/fix-scrub/tests/`
- **AND** it SHALL use the agent-coordinator virtual environment for pytest execution
- **AND** it SHALL run from the repository root to preserve cross-skill import path resolution
- **AND** a test failure SHALL block the CI pipeline (non-`continue-on-error`)

#### Scenario: Skills tests pass in CI

- **GIVEN** a push to main with no regressions in skill scripts
- **WHEN** the `test-skills` CI job runs
- **THEN** all bug-scrub and fix-scrub tests SHALL pass
- **AND** the job SHALL report success

#### Scenario: Skills test failure blocks CI

- **GIVEN** a pull request that introduces a regression in a skill script
- **WHEN** the `test-skills` CI job runs
- **THEN** the failing test SHALL be reported
- **AND** the CI pipeline SHALL not pass
