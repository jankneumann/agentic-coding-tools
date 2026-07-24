# Fail-closed semantic code-search contracts

`openapi/v2.yaml` is the normative wire contract for:

- `POST /search/code`
- `GET /search/code/status`
- the direct MCP `search_code` tool
- the HTTP-proxy MCP forwarding shape

The HTTP and MCP surfaces use the same request and successful operational
envelope. HTTP 422 is reserved for malformed requests. Expected resource,
freshness, and scope outcomes remain HTTP 200 with a discriminated non-ready
state and mandatory exact-search fallback.

No database migration is introduced. The reader consumes migrations 029 and
030 and MUST address final chunk tables only from a validated v2
`code_search_indexes.storage_key`. Legacy repo-slug tables are explicitly
outside the query contract.

Capability discovery parses the status response body. Route or tool presence
alone is not a capability proof.
