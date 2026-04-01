# Contract: Smoke Test Section in validation-report.md

The `## Smoke Tests` section is appended to `validation-report.md` by `phase_smoke.py`.
The validation gates in `/implement-feature` (soft) and `/cleanup-feature` (hard) parse this section.

## Format

```markdown
## Smoke Tests

- **Status**: pass | fail | skipped
- **Environment**: docker | neon
- **Timestamp**: <ISO 8601>
- **Duration**: <seconds>s

### Results

| Test | Status | Duration |
|------|--------|----------|
| test_health.py::test_health_endpoint | pass | 0.12s |
| test_health.py::test_ready_endpoint | pass | 0.15s |
| test_auth.py::test_no_credentials_rejected | pass | 0.08s |
| test_auth.py::test_valid_credentials_accepted | pass | 0.11s |
| test_auth.py::test_malformed_credentials_rejected | pass | 0.09s |
| test_cors.py::test_preflight_headers | pass | 0.07s |
| test_cors.py::test_disallowed_origin_rejected | pass | 0.06s |
| test_error_sanitization.py::test_no_path_leaks | pass | 0.21s |
| test_error_sanitization.py::test_no_stacktrace_leaks | pass | 0.18s |

### Failures (if any)

```
<pytest output for failed tests>
```
```

## Gate Logic

**Soft gate** (`/implement-feature`):
- If smoke section exists with `Status: pass` → continue
- If smoke section exists with `Status: skipped` → warn, continue
- If smoke section exists with `Status: fail` → warn, continue
- If smoke section missing → run phase_deploy + phase_smoke; if runtime unavailable, write `Status: skipped`, warn, continue

**Hard gate** (`/cleanup-feature`):
- If smoke section exists with `Status: pass` → continue to merge
- If smoke section exists with `Status: fail` or `Status: skipped` → re-run phase_deploy + phase_smoke
- If re-run fails → HALT with error, do not proceed to merge
- If smoke section missing → run phase_deploy + phase_smoke; if runtime unavailable → HALT with error
