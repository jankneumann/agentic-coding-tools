# Fail-closed semantic code-search contracts

`openapi/v2.yaml` is the normative v2 wire contract for:

- authenticated HTTP `POST /search/code`;
- HTTP `GET /search/code/status`;
- the direct MCP `search_code` tool; and
- the HTTP-proxy MCP forwarding shape.

This is an intentional replacement of the default-off legacy request shape.
Disabling `CODE_SEARCH_ENABLED` is the rollback path; v2 never falls back to
the legacy reader.

## Exact query boundary

HTTP, direct MCP, and HTTP-proxy MCP carry the same `CodeSearchRequest` fields
and return the same `CodeSearchResponse` envelope. A request always includes a
bounded query, validated repository slug, full 40- or 64-hex source revision,
strict namespace, and exactly one authoritative scope variant. Feature and
work-package namespaces additionally require an exact UUID `index_id`.
Unknown fields, mixed scope variants, abbreviated revisions, and missing
identity are malformed.

The wire-level `SafeGlob` expression is deliberately a coarse first check. All
implementations also apply the shared semantic validator, which rejects
leading `./`, dot segments, repeated or trailing separators, control
characters, backslashes, absolute paths, and other non-normal
repository-relative forms. Caller paths and explicit scope are narrowing
requests; the server-owned principal grant or immutable work-package
declaration remains authoritative, and deny rules win.

HTTP search requires either the bearer or coordinator API-key credential
defined by the OpenAPI security schemes. Direct MCP runs under its configured
local principal. Proxy MCP inherits the HTTP principal; it must not bypass the
HTTP authorization boundary.

## Outcome boundary

Malformed requests use HTTP 422 or the transport's equivalent validation
error. Disabled HTTP search is 404, missing or invalid HTTP credentials are
401, an absent principal grant is 403, and exhausted bounded capacity is 429.
Expected freshness, indexing, configuration, scope, and optional-resource
outcomes are HTTP 200 and use a discriminated operational state:

- only `ready` has `current=true`, an index provenance object, an allowed scope
  disposition, and an optional non-empty result list;
- every non-ready state has `current=false`, zero results, and
  `fallback={required: true, strategy: exact_search, reason: <state>}`;
- `scope_rejected` and `not_indexed` expose no selected index; and
- every result repeats repository slug, source revision, and index ID so copied
  context retains provenance.

Unexpected implementation errors are sanitized to the same `unavailable`
envelope on every transport. Responses and logs must not expose credentials,
DSNs, SQL, provider bodies, query text, source chunks, or scope patterns.

## Status and capability boundary

`CodeSearchStatus` is a closed, body-discriminated union. `available=true` is
valid only with `state=ready`, `reason=ready`, and a positive
`usable_index_count`. Disabled, uninitialized, unconfigured, or unavailable
documents require `available=false` and zero usable indexes.

Capability discovery must parse and validate that body. Route presence, MCP
tool registration, HTTP status alone, malformed or contradictory bodies, and
an unverifiable MCP-only transport all mean `CAN_CODE_SEARCH=false`.

## Storage boundary

No database migration is introduced. The reader consumes migrations 029 and
030 and addresses a final chunk table only from a validated ready v2
`code_search_indexes.storage_key`. Main selection follows the guarded
canonical pointer; non-main selection validates the caller's exact index ID.
Legacy registry metadata and `code_chunks__<repo_slug>` tables are diagnostics
only and are never query-authoritative.

Search and status are direct reads. They do not index, promote, repair, enqueue,
or mutate registry or coordination state.
