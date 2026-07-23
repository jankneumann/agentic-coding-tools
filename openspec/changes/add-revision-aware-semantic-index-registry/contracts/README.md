# Contracts: Revision-aware semantic index registry

This change introduces an internal persistence and record contract. It does not
add or change an HTTP, MCP, or event surface.

- `db/schema.sql` is the canonical Postgres shape and constraint contract.
- `index-record.schema.json` is the serialized record shape consumed by the
  incremental indexer and fail-closed query follow-ups.

Evaluated contract sub-types:

- OpenAPI: not applicable; network surfaces are deferred to
  `expose-fail-closed-semantic-code-search`.
- Database: applicable and defined here.
- Events: not applicable; indexing orchestration is a downstream change.
- Generated language types: not applicable for this internal Python/Postgres
  boundary; the implementation uses a typed dataclass that must conform to the
  JSON Schema.

The contract deliberately retains legacy `code_search_registry` fields while
adding `canonical_index_id`. `code_search_indexes` is authoritative for
revision-specific provenance and lifecycle state.
