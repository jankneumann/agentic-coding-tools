# Memory Tag Conventions

Episodic memory tags are arbitrary strings, but capability-gap signals use a shared prefix schema so multiple emitters and consumers interoperate. This document defines the tag schema, source vocabulary, and usage patterns.

## Tag Schema

All capability-gap entries use the `prefix:value` format:

| Prefix | Values | Description |
|--------|--------|-------------|
| `failure_type` | `scope_violation`, `verification_failed`, `lock_unavailable`, `timeout`, `convergence_failed`, `context_exhaustion` | Categorizes the failure mode |
| `capability_gap` | Free text | Describes what capability was missing from the harness |
| `affected_skill` | Skill name (kebab-case) | Which skill was impacted |
| `severity` | `low`, `medium`, `high`, `critical` | Impact severity |
| `source` | `self-reported`, `coordinator-emitted`, `session-log`, `transcript-mined` | Which emitter produced this signal |

### Example Tags

```
failure_type:scope_violation
capability_gap:agent could not detect circular dependency in DAG
affected_skill:implement-feature
severity:high
source:self-reported
```

## Source Vocabulary

Four sources emit capability-gap signals into the shared tag schema:

| Source | Emitter | When |
|--------|---------|------|
| `self-reported` | Agent via `remember` MCP tool | Agent encounters a task failure and self-reports |
| `coordinator-emitted` | Coordinator audit-triage background task | LLM classifier detects struggle patterns in audit batches |
| `session-log` | Session-log skill at phase boundaries | Agent fills `### Capability Gaps Observed` section in session-log |
| `transcript-mined` | `/collect-transcripts` deep-analysis pass | LLM analysis flags struggle patterns in raw transcripts |

Each source has a known bias profile:
- **self-reported** under-reports struggle (agents don't stop to introspect when struggling)
- **coordinator-emitted** misses tool-loop friction (only sees MCP/HTTP boundary)
- **session-log** catches what the agent noticed but may miss timing details
- **transcript-mined** catches everything but is the most expensive to run

Cross-source agreement (same gap surfaced by 2+ sources) is the strongest signal.

## Deduplication

`/improve-harness` deduplicates findings on the tuple `(capability_gap, affected_skill, session_id)`. When the same gap appears from multiple sources, all sources are preserved in a multi-source list. This cross-referencing is itself valuable signal.

## Usage

### Recording a capability gap (agent self-report)

Use the `remember` MCP tool with the shared tag schema:

```
remember(
    event_type="discovery",
    summary="Agent could not detect circular dependency",
    tags=[
        "failure_type:scope_violation",
        "capability_gap:missing circular dependency detection",
        "affected_skill:implement-feature",
        "severity:high",
        "source:self-reported",
    ],
)
```

### Querying capability gaps

Use `recall` with tag filters:

```
recall(tags=["failure_type:scope_violation"], limit=20)
recall(tags=["source:session-log"], limit=50)
recall(tags=["severity:critical"], limit=10)
```

### Adding new tag prefixes

New prefixes can be added without code changes -- the memory API accepts arbitrary strings. Document new prefixes in this file and update the test constants in `skills/session-log/tests/test_memory_tag_conventions.py`.
