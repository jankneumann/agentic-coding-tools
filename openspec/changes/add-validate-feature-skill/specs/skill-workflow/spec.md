## ADDED Requirements

### Requirement: Feature Validation Skill

The system SHALL provide a `validate-feature` skill that deploys the feature locally, runs behavioral tests against the live system, checks CI/CD status, and verifies OpenSpec spec compliance. The skill operates between `/iterate-on-implementation` and `/cleanup-feature` in the workflow.

The skill SHALL accept the following arguments:
- Change-id (required; or detected from current branch name `openspec/<change-id>`)
- `--skip-e2e` (optional; skip Playwright E2E phase)
- `--skip-playwright` (optional; alias for `--skip-e2e`)
- `--skip-ci` (optional; skip CI/CD status check)
- `--phase <name>[,<name>]` (optional; run only specified phases, e.g., `--phase smoke,e2e`)

#### Scenario: Full validation run
- **WHEN** the user invokes `/validate-feature <change-id>`
- **THEN** the skill SHALL execute validation in five sequential phases: Deploy, Smoke, E2E, Spec Compliance, Log Analysis
- **AND** check CI/CD status via GitHub CLI
- **AND** produce a structured validation report with pass/fail per phase
- **AND** persist the report to `openspec/changes/<change-id>/validation-report.md`
- **AND** post the report as a PR comment via `gh pr comment` if a PR exists
- **AND** teardown deployed services after validation completes

#### Scenario: Selective phase execution
- **WHEN** the user invokes `/validate-feature <change-id> --phase smoke,e2e`
- **THEN** the skill SHALL run only the specified phases (Smoke and E2E in this example)
- **AND** skip Deploy if not included (assumes services are already running)
- **AND** skip Teardown if Deploy was not run
- **AND** still produce a validation report covering only the executed phases

#### Scenario: Deploy phase starts services with DEBUG logging
- **WHEN** the Deploy phase begins
- **THEN** the skill SHALL start services via docker-compose with `LOG_LEVEL=DEBUG` environment variable
- **AND** redirect service stdout/stderr to a log file for later analysis
- **AND** wait for health checks to confirm all services are ready
- **AND** fail fast with a clear message if Docker is not available

#### Scenario: Smoke phase verifies basic service health
- **WHEN** the Smoke phase begins and services are running
- **THEN** the skill SHALL verify the API is reachable (HTTP health check)
- **AND** verify the MCP server responds to a basic tool call (if applicable)
- **AND** verify database migrations have been applied
- **AND** report which health checks passed or failed

#### Scenario: E2E phase runs Playwright tests
- **WHEN** the E2E phase begins and pytest-playwright is installed
- **THEN** the skill SHALL run Playwright E2E tests from the `tests/e2e/` directory
- **AND** report test results with failure details

#### Scenario: E2E phase skipped gracefully
- **WHEN** the E2E phase begins and either pytest-playwright is not installed, no `tests/e2e/` directory exists, or `--skip-e2e` flag was provided
- **THEN** the skill SHALL skip the E2E phase with an informational message
- **AND** NOT treat the skip as a failure

#### Scenario: Spec compliance phase verifies OpenSpec scenarios
- **WHEN** the Spec Compliance phase begins
- **THEN** the skill SHALL read all OpenSpec spec deltas for the change-id
- **AND** for each scenario, verify the expected behavior against the live system (via API calls, MCP tool invocations, or database queries)
- **AND** report pass/fail per scenario with details on mismatches

#### Scenario: Log analysis phase scans for warning signs
- **WHEN** the Log Analysis phase begins
- **THEN** the skill SHALL scan the collected log file for WARNING, ERROR, and CRITICAL entries
- **AND** flag deprecation notices, unhandled exceptions, and stack traces
- **AND** categorize findings by severity
- **AND** report findings with line numbers and context

#### Scenario: CI/CD status check
- **WHEN** the CI/CD Status phase begins and a GitHub remote is configured
- **THEN** the skill SHALL check CI/CD pipeline status via `gh run list` or `gh pr checks`
- **AND** report which checks passed, failed, or are still running
- **AND** skip gracefully with an informational message if no CI/CD workflow exists

#### Scenario: Critical phase failure stops validation
- **WHEN** the Deploy or Smoke phase fails
- **THEN** the skill SHALL stop validation immediately
- **AND** report the failure with diagnostic details
- **AND** still attempt teardown of any started services

#### Scenario: Non-critical phase failure continues validation
- **WHEN** the E2E, Spec Compliance, or Log Analysis phase fails
- **THEN** the skill SHALL continue with remaining phases
- **AND** include all failures in the final validation report

#### Scenario: Teardown cleans up resources
- **WHEN** validation completes (whether all phases passed or not)
- **THEN** the skill SHALL stop all docker-compose services started during the Deploy phase
- **AND** preserve the log file for manual inspection if failures occurred
- **AND** remove the log file if all phases passed

### Requirement: Validation Report Persistence and PR Integration

The validation skill SHALL persist results and integrate with the PR workflow.

#### Scenario: Report persisted to change directory
- **WHEN** validation completes
- **THEN** the skill SHALL write the validation report to `openspec/changes/<change-id>/validation-report.md`
- **AND** overwrite any previous report (only the latest run matters)
- **AND** include a timestamp and the git commit SHA at the top of the report

#### Scenario: Report posted as PR comment
- **WHEN** validation completes and a PR exists for the `openspec/<change-id>` branch
- **THEN** the skill SHALL post the validation report as a comment on the PR via `gh pr comment`
- **AND** prefix the comment with a header identifying it as an automated validation report

#### Scenario: No PR exists
- **WHEN** validation completes and no PR exists for the feature branch
- **THEN** the skill SHALL skip the PR comment step with an informational message
- **AND** still persist the report to the file

### Requirement: Validation Report Format

The validation skill SHALL produce a structured validation report at the end of each run that summarizes all phase results.

#### Scenario: All phases pass
- **WHEN** all validation phases pass
- **THEN** the report SHALL show a summary like:
  ```
  Validation Report: <change-id>
  ✓ Deploy: Services started (3 containers, DEBUG logging enabled)
  ✓ Smoke: All health checks passed (API, MCP, database)
  ✓ E2E: 5/5 Playwright tests passed
  ✓ Spec Compliance: 8/8 scenarios verified
  ✓ Log Analysis: No warnings or errors found
  ✓ CI/CD: All checks passing

  Result: PASS — Ready for /cleanup-feature
  ```

#### Scenario: Mixed results
- **WHEN** some phases fail while others pass
- **THEN** the report SHALL show each phase result with failure details:
  ```
  Validation Report: <change-id>
  ✓ Deploy: Services started
  ✓ Smoke: All health checks passed
  ✗ E2E: 3/5 tests passed, 2 failures
    - test_login_flow: TimeoutError on /api/auth
    - test_dashboard_load: Element not found: #stats-panel
  ✗ Spec Compliance: 6/8 scenarios verified, 2 mismatches
    - Agent Discovery > No matching agents: Expected empty array, got 500 error
    - Heartbeat > Stale detection: Agent not marked disconnected after threshold
  ⚠ Log Analysis: 3 warnings found
    - [WARNING] Deprecated function call: old_api_handler (line 142)
  ✓ CI/CD: All checks passing

  Result: FAIL — Address findings, then re-run /validate-feature or proceed to /iterate-on-implementation
  ```

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

## MODIFIED Requirements

### Requirement: Skill Workflow Position

The `iterate-on-implementation` skill SHALL fit into the feature development workflow as an optional step between `/implement-feature` and `/cleanup-feature`. The `validate-feature` skill SHALL fit as an optional step between `/iterate-on-implementation` and `/cleanup-feature`:

```
/plan-feature → /implement-feature → /iterate-on-implementation (optional) → /validate-feature (optional) → /cleanup-feature
```

#### Scenario: Workflow integration
- **WHEN** the user completes `/implement-feature` and has a PR ready for review
- **THEN** they MAY invoke `/iterate-on-implementation` to refine the implementation before requesting review
- **AND** they MAY invoke `/validate-feature` to verify the deployed feature works correctly
- **AND** the skills SHALL operate on the existing feature branch without creating new branches

#### Scenario: Validate after iterate
- **WHEN** the user completes `/iterate-on-implementation`
- **THEN** they MAY invoke `/validate-feature` to verify the refined implementation against live deployment
- **AND** if validation fails, they MAY return to `/iterate-on-implementation` to address findings

#### Scenario: Validate without iterate
- **WHEN** the user completes `/implement-feature` without running `/iterate-on-implementation`
- **THEN** they MAY invoke `/validate-feature` directly
- **AND** the validation skill SHALL work regardless of whether iterate was run
