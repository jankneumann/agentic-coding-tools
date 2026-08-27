# Contracts: deterministic context producers

This change adds registry and adapter behavior; it does not define another
producer-result wire model.

## Canonical machine contract

All adapter results MUST validate against the ri-06 contract:

```text
openspec/changes/add-durable-context-refresh-records/
  contracts/context-refresh-types.schema.json#/$defs/ProducerResult
```

At runtime, consumers import the matching strict `ProducerResult` model from:

```text
skills/project-context-runtime/scripts/models.py
```

The schema and model are installed by
`add-durable-context-refresh-records`. ri-05 depends on that change and MUST NOT
copy, narrow, or extend the result object locally.

## Invocation

```text
run_producer(
  producer_id: str,
  mode: Literal["generate", "check"],
  repository: Path,
  source_revision: FullGitSha,
) -> project_context_runtime.ProducerResult
```

The request supplies mode and revision; the durable ri-06 operation retains those
fields. The result uses:

- `artifacts` for generated paths or paths that would change in check mode;
- `validations` for deterministic pass/fail/skipped evidence;
- `remediation`, `fallback`, and `error` exactly as conditioned by the schema.

Check-mode drift is `degraded`, with a failed validation, explicit remediation,
and a `custom` fallback explaining that check mode performed no write. A clean
check is `fresh`. A render failure is `failed`.

## Ownership boundary

The shared registry owns dispatch metadata and adapter selection.
Documentation, workflow-contract, decision-index, and OpenSpec adapters call
their canonical domain owners. Durable operations, aggregate manifests, model
definitions, and schema evolution remain owned by ri-06
`project-context-runtime`.
