# Contracts — add-skillify-and-resolver-audit

## Sub-types evaluated

- **OpenAPI**: not applicable — no API endpoints.
- **Database**: not applicable — no schema changes.
- **Events**: not applicable — no event emission.
- **JSON Schema**: applicable — `resolver_audit.py --json` output is consumed by `/validate-feature --phase resolver` and (eventually) by CI tooling. See `resolver-finding.schema.json`.
- **Type generation stubs**: not generated — Python audit tool reads/writes JSON via stdlib, no Pydantic/TS layer needed in v1.

## Contract list

- `resolver-finding.schema.json` — JSON Schema for individual findings emitted in the `findings` array of `resolver_audit.py --json` output. Pinned by `resolver-audit` spec scenarios `.8` (JSON valid) and `.9` (JSON metadata).
