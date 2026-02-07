## Context
The `/test-e2e` skill introduces a repeatable deployment-and-verify workflow that spans local Docker environments and production (Railway) deployments. It must coordinate multiple services, ensure DEBUG logging is enabled for local runs, and execute both CLI and Playwright validation. Production verification may require CI/CD integration and access to Railway logs.

## Goals / Non-Goals
- Goals:
  - Provide a deterministic local E2E workflow with Docker + dev-profile variant and DEBUG logging.
  - Provide a production verification path that checks `/health` and feature-relevant endpoints after deployment.
  - Clarify which steps are safe to run locally vs in CI (GitHub Actions).
- Non-Goals:
  - Define the full implementation of service-specific deployment scripts.
  - Replace existing deployment pipelines.

## Decisions
- Decision: Keep `/test-e2e` as a standalone skill invoked after `/implement-feature` and before `/cleanup-feature`.
- Decision: Separate local deployment verification (Docker) from production verification (Railway) but keep both in a single skill flow.
- Decision: Provide hooks or references for Playwright test suites rather than embedding full test suites in the skill.

## Further Improvements
- Add a lightweight smoke-test mode that runs a subset of E2E checks for faster iteration.
- Add a deterministic seed/fixture step to ensure predictable E2E data and reduce flaky Playwright runs.
- Capture and archive logs/artifacts (Docker logs, Playwright traces, screenshots) in CI for post-mortem review.
- Add retry/backoff logic for health checks and service readiness.
- Support environment-specific overrides (ports, service names, base URLs) via a single `.env` template.

## Risks / Trade-offs
- Production verification may require credentials or access not available in local runs.
- Long-running Docker orchestration may be slow in CI without caching.
- Playwright reliability depends on consistent seed data and deterministic environment setup.

## Migration Plan
- Introduce the skill and documentation without changing existing deployment pipelines.
- Adopt in phases: local E2E first, then production verification once credentials/log access are clarified.

## Open Questions
- What is the canonical dev-profile variant name and required environment variables to enable DEBUG logging?
- Which CLI commands are the authoritative feature checks (and where are they defined)?
- How should Railway deployments be triggered from the skill (CLI, API, or GitHub Actions)?
- Is Railway log access required, and if so, should it be fetched via Railway CLI/API or surfaced via GitHub Actions?
- Which feature endpoints are mandatory for the post-deploy verification (per capability), and where should they be defined?
- What is the source of truth for local Docker composition (compose file, task runner, or custom script)?
- Are staging/pre-production environments required before production verification?
- What credentials/secrets are required for production verification, and how will they be provided to local runs vs CI?
