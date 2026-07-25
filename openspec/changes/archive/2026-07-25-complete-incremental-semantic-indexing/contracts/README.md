# Contracts: Complete incremental semantic indexing

This change adds internal operation, persistence, and JSON-result contracts. It
does not add or change an HTTP, MCP, or event surface.

- `index-request.schema.json` freezes exact source, namespace, policy, provider,
  and execution inputs. Credentials are referenced by configuration and MUST
  NOT be serialized into the request artifact.
- `index-execution-result.schema.json` is the structured CLI/refresh handoff,
  including durability and terminal outcome.
- `index-record-v2.schema.json` supersedes the strict ri-01 v1 record for new
  rows by adding computation fingerprints and compatible-parent linkage.
- `target-strategy.md` freezes attempt-scoped storage and fenced publication.
- `db/schema.sql` defines the migration-030 additions for fingerprints, file
  manifests, attempt fencing, parent selection, and lease renewal.

Contract applicability:

| Contract type | Applies | Boundary |
|---|---:|---|
| OpenAPI | No | Query and coordinator surfaces remain `ri-03`. |
| Database | Yes | Additive/revision-aware Postgres lifecycle and manifests. |
| JSON Schema | Yes | Internal request and execution result. |
| Events | No | The later refresh orchestrator owns durable producer events. |
| Generated types | No | Typed Python dataclasses conform to the JSON Schemas. |

The `ri-01` v1 record remains accepted for legacy decoding only. New
serialization uses v2. `ri-03` SHALL accept v2 and MUST NOT treat a v1
legacy-fingerprint row as a compatible current index. Neither record exposes
credentials or file contents in manifests or errors.
