# Contracts: work-package context impact

No HTTP API is added. The canonical wire contract is the additive
`context_impact` definition in `openspec/schemas/work-packages.schema.json`.
The normalized downstream output validates against
`context-impact-handoff.schema.json`.

## YAML shape

```yaml
context_impact:
  capabilities:
    disposition: refresh
    targets: [project-context-refresh]
  apis:
    disposition: no-impact
  architecture:
    disposition: refresh
  decisions:
    disposition: no-impact
  documentation:
    disposition: refresh
    targets: [docs/guides/workflow.md]
  semantic_code:
    disposition: refresh
```

If inference conflicts with `no-impact`, that surface requires:

```yaml
exception:
  rationale: "Why the deterministic evidence does not alter this surface"
  approved_by: "github:reviewer"
  approved_at: "2026-07-23T00:00:00Z"
```

## Normalized handoff

`validate_work_packages.py --context-impact-output <path>` writes stable JSON
validated by `context-impact-handoff.schema.json`:

```json
{
  "schema_version": 1,
  "rule_set_version": 1,
  "packages": [
    {
      "package_id": "wp-example",
      "compatibility": "declared",
      "declarations": {},
      "inferred": [],
      "read_scope": {
        "read_allow": ["src/**"],
        "deny": ["src/secrets/**"],
        "semantics": "read_allow_minus_deny"
      }
    }
  ]
}
```

Consumers must not treat this output as new authority. The source
`scope.read_allow` and `scope.deny` values remain canonical.
