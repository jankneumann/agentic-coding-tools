# Validation Report

<!-- Date: YYYY-MM-DD HH:MM:SS
     Commit: short SHA
     Branch: openspec/<change-id> -->

## Phase Results

<!-- Use these symbols for each phase:
     pass      — Phase passed
     fail      — Phase failed
     warn      — Phase passed with warnings
     skip      — Phase intentionally skipped (phase selector)
     DEGRADED  — Could NOT be checked (checker/scanner/vendor unavailable).
                 This is NOT a pass. Every DEGRADED entry MUST state, in one
                 line, what was not checked and why — e.g.
                 "DEGRADED — OWASP Dependency-Check did not run: no Java runtime".
                 gate_logic.py blocks the pre-merge gate on a DEGRADED required
                 phase unless `--accept-degraded <phase>` is passed, and records
                 the override in the gate summary. -->

| Phase | Result | Details |
|-------|--------|---------|
| Deploy | <!-- pass/fail/skip/DEGRADED --> | <!-- container count, logging level --> |
| Smoke | <!-- pass/fail/skip/DEGRADED --> | <!-- health, auth, CORS, error sanitization, security headers --> |
| E2E | <!-- pass/fail/skip/DEGRADED --> | <!-- test count passed/failed --> |
| Architecture | <!-- pass/fail/warn/skip/DEGRADED --> | <!-- broken flows, orphaned code, warnings --> |
| Spec Compliance | <!-- pass/fail/skip/DEGRADED --> | <!-- N/M scenarios verified --> |
| Logs | <!-- pass/warn/skip/DEGRADED --> | <!-- error count, warning count, deprecations, stack traces --> |
| CI/CD | <!-- pass/fail/skip/DEGRADED --> | <!-- GitHub Actions check status --> |

<!-- Per-phase sections below carry the machine-readable status line that
     gate_logic.py parses:
       - **Status**: pass | fail | skipped | DEGRADED
       - **Not checked**: <what and why>   (REQUIRED when Status is DEGRADED) -->

## Spec Compliance

<!-- Full requirement traceability is in change-context.md.
     Report only summary counts here. -->

See [change-context.md](./change-context.md) for the full requirement traceability matrix.

**Summary**: <!-- N/M requirements verified, N gaps, N deferred -->

## Log Analysis

<!-- Error count, warning count, deprecation count, stack trace count.
     Show context for errors and critical entries if any. -->

## Result

<!-- PASS — Ready for /cleanup-feature
     or
     FAIL — Address findings, then re-run /validate-feature or /iterate-on-implementation
     or
     DEGRADED — One or more phases could not be checked. Name them and what was
     missing. Not merge-ready: re-run once the checker is available, or record an
     explicit `--accept-degraded <phase>` override with a justification. -->
