# Validation Report

<!-- Date: YYYY-MM-DD HH:MM:SS
     Commit: short SHA
     Branch: openspec/<change-id> -->

## Phase Results

<!-- Use these symbols for each phase:
     pass  — Phase passed
     fail  — Phase failed
     warn  — Phase passed with warnings
     skip  — Phase skipped -->

| Phase | Result | Details |
|-------|--------|---------|
| Deploy | <!-- pass/fail/skip --> | <!-- container count, logging level --> |
| Smoke | <!-- pass/fail/skip --> | <!-- health, auth, CORS, error sanitization, security headers --> |
| E2E | <!-- pass/fail/skip --> | <!-- test count passed/failed --> |
| Architecture | <!-- pass/fail/warn/skip --> | <!-- broken flows, orphaned code, warnings --> |
| Spec Compliance | <!-- pass/fail/skip --> | <!-- N/M scenarios verified --> |
| Logs | <!-- pass/warn/skip --> | <!-- error count, warning count, deprecations, stack traces --> |
| CI/CD | <!-- pass/fail/skip --> | <!-- GitHub Actions check status --> |

## Spec Compliance Details

<!-- One row per scenario from the change's spec deltas -->

| Scenario | Result | Notes |
|----------|--------|-------|
|          |        |       |

## Log Analysis

<!-- Error count, warning count, deprecation count, stack trace count.
     Show context for errors and critical entries if any. -->

## Result

<!-- PASS — Ready for /cleanup-feature
     or
     FAIL — Address findings, then re-run /validate-feature or /iterate-on-implementation -->
