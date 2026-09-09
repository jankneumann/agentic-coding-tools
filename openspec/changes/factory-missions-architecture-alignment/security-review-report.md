# Security Review Report

## Run Context

- Change ID: `factory-missions-architecture-alignment`
- Commit SHA: f5daa3453944a2e7647027dbb48d80504b2ba81c
- Timestamp: 2026-09-09T01:01:13.803288+00:00
- Profile: `mixed`
- Confidence: `high`

## Gate Summary

- Decision: **PASS**
- Fail threshold: `high`
- Triggered findings: `0`

## Scanner Results

| Scanner | Status | Notes |
|---|---|---|
| dependency-check | error | podman dependency-check failed (exit 125) |
| zap | error | zap baseline scan failed via podman (exit 3) |

## Severity Summary

- Total findings: `0`
- Critical: `0`
- High: `0`
- Medium: `0`
- Low: `0`
- Info: `0`

## Gate Reasons

- DEGRADED — dependency-check, zap NOT CHECKED (scanner unavailable or errored); degraded execution allowed by policy (--allow-degraded-pass) and no threshold findings were detected by the scanners that did run

## Top Findings

- No findings
