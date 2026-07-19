# Contracts: add-semantic-code-search

Contract sub-types evaluated per plan-feature Step 7:

| Sub-type | Applies | Artifact |
|---|---|---|
| OpenAPI | Yes — new `POST /search/code` endpoint (MCP tool `search_code` wraps the same service and payload) | `openapi/v1.yaml` |
| Database | Yes — `code_search_registry` migration + pipeline-managed chunk-table reference shape and query contract | `db/schema.sql` |
| Events | **No** — the capability is a synchronous read; indexing emits no coordination events in v1 (a post-merge trigger calls `index_repo` directly). Revisit if indexing moves to the work queue. |
| Type generation | Deferred to `wp-contracts` — Pydantic models generated from `openapi/v1.yaml` into `generated/models.py` during implementation (kept out of the draft to avoid hand-maintained duplicates). |

Seed data: none required — `code_search_registry` starts empty; fixture repos are created by
tests (see `tasks.md` 2.1, 3.1).
