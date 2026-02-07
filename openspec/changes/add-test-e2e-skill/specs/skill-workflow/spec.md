## ADDED Requirements
### Requirement: End-to-End Test Skill
The system SHALL provide a `/test-e2e` skill that validates feature behavior end-to-end against both local and production deployments.

#### Scenario: Local Docker deployment with DEBUG logging
- **WHEN** the user invokes `/test-e2e <change-id>`
- **THEN** the skill SHALL start a local Docker-based test deployment with required services (Postgres, Neo4j, Opik, frontend, backend)
- **AND** use a dev-profile variant with DEBUG logging enabled
- **AND** wait for all services to report healthy before running verification steps

#### Scenario: Local CLI and Playwright verification
- **WHEN** the local deployment is healthy
- **THEN** the skill SHALL run the feature verification via CLI commands
- **AND** run Playwright E2E tests against the local deployment
- **AND** report any failures with the relevant logs and test output

#### Scenario: Production deployment verification
- **WHEN** local verification succeeds
- **THEN** the skill SHALL trigger a production-profile deployment (Railway)
- **AND** verify `/health` and feature-relevant endpoints return responses without errors
- **AND** report the verification results with the deployment identifier and endpoint checks

#### Scenario: Failure handling
- **WHEN** any deployment or verification step fails
- **THEN** the skill SHALL stop the workflow
- **AND** report which step failed with actionable troubleshooting details

### Requirement: Execution Location Guidance
The system SHALL document which `/test-e2e` steps are expected to run locally versus in CI (GitHub Actions), including any required credentials or environment constraints.

#### Scenario: Production checks require CI credentials
- **WHEN** production deployment verification requires credentials or network access not available locally
- **THEN** the skill SHALL direct the user to run the production verification portion via GitHub Actions (or other CI) with the required secrets configured
