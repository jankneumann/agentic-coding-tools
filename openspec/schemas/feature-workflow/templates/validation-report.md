# Validation Report: {{change-id}}

**Date**: {{timestamp}}
**Commit**: {{commit-sha}}
**Branch**: openspec/{{change-id}}

## Phase Results

| Phase | Result | Details |
|-------|--------|---------|
| Deploy | <!-- pass/fail/skip --> | <!-- container count, logging level --> |
| Smoke | <!-- pass/fail/skip --> | <!-- health, auth, CORS, error sanitization, security headers --> |
| E2E | <!-- pass/fail/skip --> | <!-- test count passed/failed --> |
| Architecture | <!-- pass/fail/warn/skip --> | <!-- broken flows, orphaned code, warnings --> |
| Spec Compliance | <!-- pass/fail/skip --> | <!-- N/M scenarios verified --> |
| Logs | <!-- pass/warn/skip --> | <!-- errors, warnings, deprecations, stack traces --> |
| CI/CD | <!-- pass/fail/skip --> | <!-- GitHub Actions status --> |

## Spec Compliance Details

| Scenario | Result | Notes |
|----------|--------|-------|
| <!-- Capability > Scenario name --> | <!-- pass/fail --> | <!-- Details on failure --> |

## Log Analysis

- Errors: <!-- count -->
- Warnings: <!-- count -->
- Deprecations: <!-- count -->
- Stack traces: <!-- count -->

## Result

**<!-- PASS or FAIL -->** — <!-- Guidance: ready for cleanup, or address findings first -->
