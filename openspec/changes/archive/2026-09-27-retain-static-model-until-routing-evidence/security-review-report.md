# Security Review Report

## Run Context

- Change ID: `retain-static-model-until-routing-evidence`
- Commit SHA: dae6bacc771569db0b26595609fa55a5e7120070
- Timestamp: 2026-09-26T01:06:39.403997+00:00
- Profile: `mixed`
- Confidence: `high`

## Gate Summary

- Decision: **PASS**
- Fail threshold: `high`
- Triggered findings: `0`

## Scanner Results

| Scanner | Status | Notes |
|---|---|---|
| dependency-check | error | NVD database at /home/jankneumann/.cache/dependency-check/data is 15 day(s) old, past the 7-day floor. A scan against stale CVE data reports no findings whether or not any exist, so this is NOT CHECKED rather than a pass. Refresh with: make security-seed-nvd |
| zap | ok | Parsed 1 findings |

## Severity Summary

- Total findings: `1`
- Critical: `0`
- High: `0`
- Medium: `0`
- Low: `0`
- Info: `1`

## Gate Reasons

- DEGRADED — dependency-check NOT CHECKED (scanner unavailable or errored); degraded execution allowed by policy (--allow-degraded-pass) and no threshold findings were detected by the scanners that did run

## Top Findings

- `[INFO]` zap :: Storable and Cacheable Content (http://localhost:19831/robots.txt)
