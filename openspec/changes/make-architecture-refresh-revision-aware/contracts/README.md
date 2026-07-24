# Contracts: Revision-Aware Architecture Refresh

This change owns one architecture-specific contract:

- `architecture-provenance.schema.json` — deterministic evidence written beside the
  architecture artifact set.

Shared persistence and result contracts are dependencies, not copies. Implementations
MUST consume the installed schemas/models from
`add-durable-context-refresh-records`:

- `context-refresh-types.schema.json` (`ProducerResult`, validations, remediation,
  fallback, safe errors, repository artifacts);
- `context-refresh-operation.schema.json` (mutable Git-common-dir operation); and
- `context-refresh-manifest.schema.json` (later deterministic project-context
  projection).

No architecture-specific operation schema, lock contract, database, event, or public
OpenAPI surface applies. The subprocess RPC is a compatibility adapter specified by
the architecture spec and canonical ri-06 types.
