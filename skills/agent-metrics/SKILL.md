---
name: agent-metrics
description: Generate throughput and quality reports from coordinator audit data and episodic memory
category: Git Workflow
tags: [metrics, throughput, dashboard, audit, analysis]
triggers:
  - "agent metrics"
  - "throughput report"
  - "agent dashboard"
  - "failure rates"
---

# Agent Metrics

Generate throughput and quality reports from the coordinator's audit trail and episodic memory. Provides three modes: throughput overview, failure rate analysis, and capability gap frequency.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--time-range <days>` (default: 30)
- `--failures` (show failure rate analysis by agent type, skill, failure_type)
- `--gaps` (show capability gap frequency, cross-referenced with /improve-harness reports)
- `--output <path>` (write report to file; default: stdout)

## Modes

### Default: Throughput Report
Queries the audit trail for operational metrics:
- Tasks completed / failed
- PRs opened
- Review cycles per PR
- Average time-to-merge

### `--failures`: Failure Rate Analysis
Queries episodic memory for failure patterns and computes:
- Failure rates by failure_type (timeout, scope_violation, etc.)
- Failure rates by affected skill
- Trends (increasing/decreasing)

### `--gaps`: Capability Gap Frequency
Queries episodic memory for capability_gap entries and:
- Ranks gaps by frequency
- Cross-references with /improve-harness reports if available

## Prerequisites

- Python 3.11+
- Coordinator running at `COORDINATOR_URL` (default: http://localhost:8000)
- Falls back gracefully with a warning if the coordinator is unreachable

## Steps

### 1. Query Metrics

```bash
python3 <agent-skills-dir>/agent-metrics/scripts/query_metrics.py \
  --time-range ${TIME_RANGE:-30} \
  ${FAILURES:+--failures} \
  ${GAPS:+--gaps} \
  --json
```

### 2. Generate Dashboard

```bash
python3 <agent-skills-dir>/agent-metrics/scripts/generate_dashboard.py \
  --time-range ${TIME_RANGE:-30} \
  ${FAILURES:+--failures} \
  ${GAPS:+--gaps} \
  ${OUTPUT:+--output "$OUTPUT"}
```
