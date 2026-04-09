# Contracts: Harness Engineering Features

## Applicability Assessment

| Contract Type | Applicable? | Rationale |
|---------------|-------------|-----------|
| OpenAPI | No | No new HTTP API endpoints; existing coordinator API unchanged |
| Database | Yes | New migration for evaluator profile seed |
| Event | No | No new event types introduced |
| Type Generation | No | No new API schemas requiring generated types |

## Database Contract

### Migration: 017_evaluator_profile.sql

Seeds the `agent_profiles` table with a built-in evaluator profile:

```sql
INSERT INTO agent_profiles (name, agent_type, trust_level, allowed_operations, blocked_operations, max_file_modifications, max_execution_time_seconds, max_api_calls_per_hour, enabled)
VALUES (
  'evaluator',
  'evaluator',
  2,
  ARRAY['read', 'review', 'evaluate'],
  ARRAY['write', 'commit', 'push', 'delete'],
  0,
  600,
  500,
  true
);
```

### Guardrails Extension

The `check_guardrails` function is extended to accept an optional `session_scope` parameter. When provided, file path modifications are validated against the scope's `write_allow` and `deny` patterns in addition to existing guardrail checks.

**Interface contract** (Python function signature):
```python
async def check_guardrails(
    command: str,
    trust_level: int = 2,
    session_scope: dict | None = None,  # NEW: {"write_allow": [...], "deny": [...]}
) -> GuardrailResult:
```

## Episodic Memory Tag Conventions

Failure recording uses structured tag prefixes:

| Tag Prefix | Values | Example |
|------------|--------|---------|
| `failure_type:` | scope_violation, verification_failed, lock_unavailable, timeout, convergence_failed, context_exhaustion | `failure_type:convergence_failed` |
| `capability_gap:` | Free text | `capability_gap:no-auto-fix-for-import-errors` |
| `affected_skill:` | Skill name | `affected_skill:implement-feature` |
| `severity:` | low, medium, high, critical | `severity:high` |

## Linter Output Format

Architecture linters produce findings compatible with `review-findings.schema.json`. The root object is a `Review Findings` document (requires `review_type`, `target`, `findings`); each finding uses the schema's integer `id`, the `architecture` `type`, a `criticality` from `low|medium|high|critical`, a `disposition` from `fix|regenerate|accept|escalate`, and top-level `file_path`/`line_range` rather than a nested `location` object. The human-readable remediation text goes into `resolution`.

```json
{
  "review_type": "implementation",
  "target": "wp-architecture-linters",
  "reviewer_vendor": "structural-linter",
  "findings": [
    {
      "id": 1,
      "type": "architecture",
      "criticality": "high",
      "disposition": "fix",
      "description": "skills/foo/scripts/bar.py imports from agent-coordinator/src/locks.py directly",
      "resolution": "Use coordinator MCP tools or HTTP API instead of direct imports. See docs/guides/skills.md#coordinator-integration",
      "file_path": "skills/foo/scripts/bar.py",
      "line_range": {"start": 5, "end": 5}
    }
  ]
}
```
