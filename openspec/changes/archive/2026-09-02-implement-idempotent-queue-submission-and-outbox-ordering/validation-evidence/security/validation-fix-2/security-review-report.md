# Security Review Report

## Run Context

- Change ID: `implement-idempotent-queue-submission-and-outbox-ordering`
- Commit SHA: eb3cb550e0fa90b8aecce70e4116f3fda838cc8b
- Timestamp: 2026-09-02T02:35:04Z
- Profile: `mixed`
- Confidence: `high`

## Gate Summary

- Decision: **PASS**
- Fail threshold: `high`
- Triggered findings: `0`

## Scanner Results

| Scanner | Status | Notes |
|---|---|---|
| zap | ok | ZAP baseline completed with warnings (exit 2): 66 rules passed, 1 informational warning, 0 failures |

## Severity Summary

- Total findings: `1`
- Critical: `0`
- High: `0`
- Medium: `0`
- Low: `0`
- Info: `1`

## Gate Reasons

- No gate reasons provided

## Top Findings

- `[INFO]` zap :: Storable and Cacheable Content (http://host.containers.internal:18091)
