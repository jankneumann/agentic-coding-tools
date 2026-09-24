# Security Review Report

## Run Context

- Change ID: `derive-agent-identity-from-registry`
- Commit SHA: 472f112d5088235840a7d30140c5bc4823634c62
- Timestamp: 2026-08-15T12:12:48.679503+00:00
- Profile: `mixed`
- Confidence: `high`

## Gate Summary

- Decision: **PASS**
- Fail threshold: `high`
- Triggered findings: `0`

## Scanner Results

| Scanner | Status | Notes |
|---|---|---|
| dependency-check | unavailable | dependency-check unavailable (missing binary and container runtime access) |
| zap | unavailable | DAST profile requires --zap-target for ZAP execution |

## Severity Summary

- Total findings: `0`
- Critical: `0`
- High: `0`
- Medium: `0`
- Low: `0`
- Info: `0`

## Gate Reasons

- Degraded execution allowed by policy; no threshold findings detected

## Top Findings

- No findings
