# Change: Add /test-e2e skill for local + production verification

## Why
Teams need a repeatable, automated end-to-end verification step that validates feature behavior before cleanup and before declaring success, covering both local dev-profile deployments and production (Railway) deployments.

## What Changes
- Add a new `/test-e2e` skill that spins up a local Docker-based test deployment (Postgres, Neo4j, Opik, frontend, backend) using a dev-profile variant with DEBUG logging enabled.
- Run CLI-based verification and Playwright-based E2E checks against the local deployment.
- Trigger a production-profile deployment (Railway) and verify `/health` and feature-relevant endpoints respond without errors.
- Document where production verification should run (locally vs GitHub Actions) and when to use each path.

## Impact
- Affected specs: `specs/skill-workflow/spec.md`
- Affected code: `skills/` (new `/test-e2e` skill), deployment/testing scripts, CI workflows
