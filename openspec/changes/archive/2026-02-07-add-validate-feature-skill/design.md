## Context

The feature development workflow currently goes: plan → implement → iterate (static checks) → cleanup. The "iterate" stage catches code-level issues via pytest/mypy/ruff, but nothing tests the deployed system. The "cleanup" stage assumes CI passes and the PR is approved — but CI/CD doesn't exist yet, and there's no structured behavioral verification against OpenSpec scenarios.

The project has:
- Docker Compose for local Supabase (postgres + PostgREST + Realtime)
- pytest with mock Supabase via respx (unit/integration)
- MCP server (stdio) and HTTP API (FastAPI) — no web UI yet
- Verification tiers defined: Static (0) → Unit (1) → Integration (2) → System (3) → Manual (4)
- No Playwright, no GitHub Actions, no Dockerfile for the app itself

## Goals / Non-Goals

- **Goals:**
  - Add a `/validate-feature` skill that deploys the feature locally and runs behavioral tests
  - Enable DEBUG logging during validation to surface hidden issues early
  - Support both CLI-based testing (MCP tools, HTTP API calls) and Playwright browser tests
  - Check CI/CD pipeline status when available
  - Verify OpenSpec scenarios against the live system (behavioral spec compliance)
  - Produce a structured validation report with pass/fail per validation phase

- **Non-Goals:**
  - Building a full CI/CD pipeline (just a stub + status check)
  - Implementing a staging environment (local-only for now)
  - Auto-fixing validation failures (report only; user decides next step)
  - Replacing existing pytest/mypy/ruff checks (those stay in iterate-on-implementation)

## Decisions

### Decision 1: Skill-as-orchestrator, not a test framework

The `/validate-feature` skill is a SKILL.md instruction document (like all other skills), not a test framework or application code. It tells the AI assistant which validation steps to perform and in what order. The assistant uses existing tools (docker-compose, pytest, curl, Playwright CLI) rather than a custom validation runner.

**Alternatives considered:**
- **Custom validation framework**: Rejected — adds complexity and a runtime dependency; the AI assistant can orchestrate existing tools directly
- **Extend iterate-on-implementation**: Rejected — different concern (static code quality vs. live deployment verification); mixing them would make iterate-on-implementation too heavy

### Decision 2: Five validation phases executed in sequence

Validation runs in five ordered phases. Phases are sequential because each depends on the previous (can't test a service that didn't start):

1. **Deploy** — Start services locally via docker-compose with DEBUG logging
2. **Smoke** — CLI-based health checks and basic API calls
3. **E2E** — Playwright browser tests (skipped when no web UI exists)
4. **Spec Compliance** — Map OpenSpec scenarios to live behavioral checks
5. **Log Analysis** — Scan collected DEBUG logs for warnings, errors, deprecations

Each phase produces a structured result (pass/fail with details). The skill stops and reports if a critical phase fails (Deploy, Smoke) but continues through non-critical failures (E2E, Spec Compliance) to give a complete picture.

**Alternatives considered:**
- **Parallel phases**: Rejected — phases have ordering dependencies (must deploy before smoke testing)
- **Single monolithic check**: Rejected — granular phases allow targeted re-runs and clearer failure diagnosis

### Decision 3: Playwright as optional, pytest-playwright for Python consistency

Since the project is Python-first (no Node.js/TypeScript), use `pytest-playwright` for E2E tests rather than the Node.js Playwright test runner. This keeps tests in the same language and framework as existing tests. E2E tests are skipped when no web UI exists for the feature being validated.

**Alternatives considered:**
- **Node.js Playwright**: Rejected — would introduce Node.js as a project dependency just for E2E tests
- **Selenium/WebDriver**: Rejected — Playwright is more modern, faster, and better maintained
- **Skip E2E entirely**: Rejected — user specifically requested Playwright support for web interfaces

### Decision 4: OpenSpec scenario-to-test mapping via structured prompts

Rather than auto-generating test code from specs, the AI assistant reads the OpenSpec scenarios and manually verifies each one against the live system (e.g., calling an API endpoint and checking the response matches the scenario's THEN clause). This keeps the skill simple and leverages the AI's ability to interpret specs contextually.

**Alternatives considered:**
- **Auto-generated test scaffolds from specs**: Attractive but premature — would require a spec-to-test compiler; can be a follow-up proposal
- **Manual-only verification**: Rejected — too slow and error-prone for repeated validation runs

### Decision 5: Log collection via file redirect, not a logging framework

During validation, services are started with `LOG_LEVEL=DEBUG` environment variable and stdout/stderr redirected to a log file. The AI assistant then scans the log file for patterns (WARNING, ERROR, CRITICAL, deprecation notices, stack traces). No custom log aggregation or structured logging is required.

**Alternatives considered:**
- **Structured JSON logging**: Overkill for local validation; adds configuration complexity
- **Log streaming with real-time analysis**: Rejected — the AI assistant reads the log file after tests complete, which is simpler and sufficient

## Risks / Trade-offs

- **Docker availability**: The skill assumes Docker/docker-compose is installed. Mitigation: the Deploy phase checks for Docker and fails fast with a clear message if unavailable.
- **Port conflicts**: Local services may conflict with other running services. Mitigation: use non-standard ports (already done — docker-compose uses 54322, 3000, 4000) and check port availability before starting.
- **Playwright installation**: pytest-playwright requires browser binaries. Mitigation: the E2E phase checks if Playwright is installed and skips gracefully if not, with a message explaining how to install.
- **Long-running validation**: Full validation (deploy + tests + teardown) can take several minutes. Mitigation: phases are independent enough that the user can choose to skip phases (e.g., `--skip-e2e`, `--skip-playwright`).

## Resolved Questions

- **`--phase` flag**: Yes — the skill supports `--phase <name>` to run only specific phases (e.g., `--phase smoke` to skip deployment if services are already running). Multiple phases can be specified: `--phase smoke,e2e`.
- **Persist validation results**: Yes — results are written to `openspec/changes/<change-id>/validation-report.md` after each run. Previous reports are overwritten (not appended) since only the latest state matters.
- **PR comment**: Yes — when a PR exists for the feature branch, the skill auto-posts the validation report as a PR comment via `gh pr comment`. This gives reviewers visibility into validation status.
