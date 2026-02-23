## MODIFIED Requirements

### Requirement: Feature Validation Skill

The system SHALL provide a `validate-feature` skill that deploys the feature locally, runs behavioral tests against the live system, **runs security scans against the live deployment**, checks CI/CD status, and verifies OpenSpec spec compliance. The skill operates between `/iterate-on-implementation` and `/cleanup-feature` in the workflow.

The skill SHALL accept the following arguments:
- Change-id (required; or detected from current branch name `openspec/<change-id>`)
- `--skip-e2e` (optional; skip Playwright E2E phase)
- `--skip-playwright` (optional; alias for `--skip-e2e`)
- `--skip-ci` (optional; skip CI/CD status check)
- `--skip-security` (optional; skip the Security Scan phase)
- `--phase <name>[,<name>]` (optional; run only specified phases, e.g., `--phase smoke,security`)

Valid phase names SHALL include: `deploy`, `smoke`, `security`, `e2e`, `architecture`, `spec`, `logs`, `ci`

#### Scenario: Full validation run includes security scanning
- **WHEN** the user invokes `/validate-feature <change-id>`
- **THEN** the skill SHALL execute validation in seven sequential phases: Deploy, Smoke, Security, E2E, Architecture, Spec Compliance, Log Analysis
- **AND** the Security phase SHALL run after Smoke confirms the API is healthy
- **AND** the Security phase SHALL run before E2E
- **AND** produce a structured validation report with pass/fail/skip/degraded per phase
- **AND** include security scan results in the validation report

#### Scenario: Security phase invokes security-review orchestrator
- **WHEN** the Security phase begins and services are confirmed healthy by Smoke
- **THEN** the skill SHALL invoke `security-review/scripts/main.py` with:
  - `--repo` pointing to the repository root
  - `--zap-target` pointing to the live API URL (e.g., `http://localhost:${AGENT_COORDINATOR_REST_PORT}`)
  - `--change` set to the current change-id
  - `--out-dir` set to `docs/security-review`
  - `--allow-degraded-pass` enabled
- **AND** capture the exit code and report output
- **AND** report the gate decision (PASS/FAIL/INCONCLUSIVE) in the phase result

#### Scenario: Security phase is non-critical
- **WHEN** the Security phase fails (exit code 10 = FAIL or exit code 11 = INCONCLUSIVE)
- **THEN** the skill SHALL continue with remaining phases (E2E, Architecture, Spec Compliance, Log Analysis)
- **AND** include the security findings in the final validation report
- **AND** NOT stop validation

#### Scenario: Security phase skipped via flag
- **WHEN** the user invokes `/validate-feature <change-id> --skip-security`
- **THEN** the skill SHALL skip the Security phase entirely
- **AND** report the phase as "skipped" in the validation report
- **AND** NOT treat the skip as a failure

#### Scenario: Security phase degrades gracefully when prerequisites missing
- **WHEN** scanner prerequisites are unavailable (no Java for dependency-check, no container runtime for ZAP)
- **THEN** the Security phase SHALL report degraded coverage (INCONCLUSIVE with `--allow-degraded-pass`)
- **AND** list which scanners were unavailable and why
- **AND** NOT block validation

#### Scenario: Security phase with selective phases
- **WHEN** the user invokes `/validate-feature <change-id> --phase security`
- **THEN** the skill SHALL run only the Security phase (assuming services are already running)
- **AND** NOT run Deploy, Smoke, E2E, or other phases

### Requirement: Validation Prerequisite Checks

The validation skill SHALL verify prerequisites before starting the validation phases.

#### Scenario: Docker not available
- **WHEN** the user invokes `/validate-feature` and Docker/docker-compose is not installed or not running
- **THEN** the skill SHALL fail immediately with a message explaining how to install/start Docker

#### Scenario: No docker-compose.yml found
- **WHEN** the user invokes `/validate-feature` and no docker-compose.yml exists in the project
- **THEN** the skill SHALL skip the Deploy phase and attempt Smoke tests against already-running services
- **AND** inform the user that deployment validation was skipped

#### Scenario: Feature branch verification
- **WHEN** the user invokes `/validate-feature`
- **THEN** the skill SHALL verify the current branch is `openspec/<change-id>`
- **AND** verify implementation commits exist on the branch
- **AND** fail with guidance if no implementation is found

## UNCHANGED Requirements

### Requirement: Standalone Security Review Skill

The `/security-review` skill SHALL continue to operate independently as a standalone skill for ad-hoc scans, CI pipeline integration, and non-feature-workflow use cases. No changes to the security-review skill's scripts, models, parsers, gate logic, or invocation interface.
