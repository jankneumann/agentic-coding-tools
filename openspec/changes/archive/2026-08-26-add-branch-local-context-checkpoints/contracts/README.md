# Contracts — add-branch-local-context-checkpoints

## Applicable

- **`context-checkpoint.schema.json`** — the branch-local checkpoint report. This is the
  coordination boundary of the change: `checkpoint.py` writes it, `implement-feature`
  records it, reviewers read it in the PR diff, and ri-10's drift gate will consume it.

  It `$ref`s `./context-refresh-types.schema.json#/$defs/{GitRevision,ProducerResult,SemanticIndexReference}`,
  matching how `context-refresh-manifest.schema.json` already composes the shared ri-06
  type definitions. Those refs resolve once this schema is installed alongside the
  existing context-refresh schemas in `openspec/schemas/`.

## Evaluated and not applicable

| Sub-type | Verdict |
|---|---|
| OpenAPI | No HTTP endpoints are added or modified. The checkpoint is a local CLI invocation, not a service call. |
| Database | No schema change. Semantic index tables are created by the existing code-search runtime from the namespace identity; this change supplies a namespace value, it does not define storage. |
| Events | No events are emitted or consumed. The trigger is a direct in-process call from the implementation workflow at a package boundary. |
| Type generation | No cross-language boundary. Producers and consumers are both Python; the schema is validated at runtime rather than code-generated. |

## Promotion note

Per repository convention, this directory must be copied to
`openspec/contracts/project-context-refresh/schemas/` **before** the change is archived —
`openspec/contracts/` is the durable system representation alongside `openspec/specs/`,
and archiving without promoting loses the contract.
