# Proposal: Add OpenTelemetry Observability Metrics

**Change ID**: `add-otel-observability`
**Status**: Draft
**Author**: claude-code-1
**Date**: 2026-03-23

## Summary

Add OpenTelemetry (OTel) instrumentation to the agent coordinator to provide runtime observability into three critical coordination subsystems: lock contention, work queue latency, and policy evaluation performance.

## Motivation

The coordinator currently has **audit logging only** — an immutable append-only log useful for post-hoc investigation but not for real-time operational awareness. There are no metrics for:

- **Lock contention**: How often agents compete for the same resource, how long acquisitions take, which files are hot
- **Queue latency**: How long tasks wait before being claimed, per-priority and per-task-type SLA visibility
- **Policy evaluation**: Decision latency breakdown (trust resolution, Cedar evaluation, cache hit/miss rates)

Without these signals, operators cannot:
1. Detect performance regressions before they cascade
2. Size infrastructure based on actual load patterns
3. Debug multi-agent coordination issues in real time
4. Set and monitor SLAs for critical coordination operations

## Scope

### In Scope

- OpenTelemetry SDK integration with configurable exporters (OTLP, console)
- Metric instruments (counters, histograms, gauges) for locks, queue, and policy
- Tracing spans for end-to-end operation visibility
- Configuration via environment variables (standard OTel conventions)
- Prometheus-compatible `/metrics` endpoint on the HTTP API
- Unit tests for all instrumented code paths

### Out of Scope

- Dashboard creation (Grafana, Datadog, etc.) — left to deployers
- Distributed tracing across agent boundaries (future work)
- Log correlation with OTel (existing Python logging is sufficient)
- Custom OTel collectors or infrastructure provisioning

## Success Criteria

1. All three subsystems emit metrics via OTLP when `OTEL_METRICS_ENABLED=true`
2. Zero performance regression when metrics are disabled (no-op instruments)
3. `/metrics` endpoint serves Prometheus-format metrics
4. Existing test suite passes without modification
5. CI remains green with new `opentelemetry-*` dependencies
