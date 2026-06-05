---
name: improve-harness
description: Analyze capability-gap failure patterns from episodic memory and generate improvement reports with OpenSpec proposal stubs
category: Git Workflow
tags: [harness, self-improvement, capability-gaps, episodic-memory, analysis]
triggers:
  - "improve harness"
  - "analyze failures"
  - "capability gap report"
  - "harness self-improvement"
---

# Improve Harness

Analyze capability-gap failure patterns recorded in episodic memory and generate structured improvement reports. Supports creating OpenSpec proposal stubs from high-priority findings.

## Arguments

`$ARGUMENTS` - Optional flags:
- `--time-window <days>` (default: 30)
- `--create-proposal` (create an OpenSpec proposal stub from the top finding)
- `--output <path>` (write report to file; default: stdout)

## How It Works

1. Queries the coordinator episodic memory for entries with `capability_gap:*` tags
2. Groups findings by capability_gap value
3. Ranks by (frequency x severity_weight) where severity weights: critical=4, high=3, medium=2, low=1
4. Generates a markdown report with summary stats, ranked findings table, and recommendations
5. Optionally creates an OpenSpec proposal stub from the top finding

## Data Sources

The skill consumes capability-gap signals from four emitters via the shared D4 tag schema:

| Source | Tag | How it gets there |
|--------|-----|-------------------|
| Agent self-report | `source:self-reported` | Agent calls `remember` MCP tool during failure |
| Coordinator audit-triage | `source:coordinator-emitted` | LLM classifier over audit batches |
| Session-log | `source:session-log` | Agent fills `### Capability Gaps Observed` at phase boundary |
| Transcript mining | `source:transcript-mined` | `/collect-transcripts` deep-analysis pass |

The skill also scans `openspec/changes/**/session-log.md` for `### Capability Gaps Observed` sections to catch gaps not yet mirrored to memory.

Deduplication is keyed on `(capability_gap, affected_skill, session_id)`. When the same gap appears from multiple sources, all sources are preserved — cross-source agreement is the strongest signal.

## Prerequisites

- Python 3.11+
- Coordinator running at `COORDINATOR_URL` (default: http://localhost:8000)
- Falls back gracefully with a warning if the coordinator is unreachable

## Steps

### 1. Analyze Failure Patterns

```bash
python3 <agent-skills-dir>/improve-harness/scripts/analyze_failures.py \
  --time-window ${TIME_WINDOW:-30} \
  --json
```

### 2. Generate Report

```bash
python3 <agent-skills-dir>/improve-harness/scripts/generate_report.py \
  --time-window ${TIME_WINDOW:-30} \
  ${CREATE_PROPOSAL:+--create-proposal} \
  ${OUTPUT:+--output "$OUTPUT"}
```

### 3. Review and Act

- Review the ranked findings table
- For high-priority gaps, use `--create-proposal` to generate an OpenSpec proposal stub
- Refine the proposal with human guidance and submit via `/plan-feature`
