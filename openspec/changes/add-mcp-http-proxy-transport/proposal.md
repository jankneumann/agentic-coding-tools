# Proposal: Add HTTP Proxy Transport to Coordination MCP Server

## Change ID
`add-mcp-http-proxy-transport`

## Status
Draft

## Why

The coordination MCP server (`agent-coordinator/src/coordination_mcp.py`) currently requires a direct PostgreSQL connection (`POSTGRES_DSN`) to function. When the local database is unavailable — which is the common case when using the remote Railway deployment at `coord.rotkohl.ai` — all 48 MCP tools fail with connection errors.

Meanwhile, the HTTP API (`coordination_api.py`) running on Railway provides the same functionality through authenticated REST endpoints. Skills already work around this via `coordination_bridge.py` HTTP fallback, but direct MCP tool calls (used by Claude Code for ad-hoc queries like `get_my_profile`, `query_audit`, `issue_list`) have no fallback path.

This creates an inconsistent experience: skills work, direct tool calls don't.

## What Changes

1. **Fill HTTP API gaps**: Add HTTP endpoints for 15 MCP tools that currently lack them (discovery: 4, gen-eval: 4, issues: 3, work: 1, session grants: 1, approvals: 2)
2. **Build HTTP proxy adapter**: New `src/http_proxy.py` module that maps MCP tool calls to HTTP API requests
3. **Startup transport selection**: At MCP server startup, probe both POSTGRES_DSN and COORDINATION_API_URL; select the best available backend
4. **Auth configuration**: Use `COORDINATION_API_KEY` environment variable for HTTP API authentication

### Out of Scope
- Changing the coordination_bridge.py (skill HTTP fallback stays independent)
- Modifying the HTTP API's authentication model
- Adding WebSocket/SSE streaming between MCP and HTTP API

## Approaches Considered

### Approach 1: Tool-level HTTP proxy module (Recommended)

Create a new `src/http_proxy.py` module containing async functions that map each MCP tool's arguments to an HTTP API request and its response back to the expected return dict. At startup, the MCP server probes both backends and sets a module-level flag. Each tool handler routes to either the service layer (DB) or the proxy module (HTTP).

**Pros:**
- Incremental: each tool can be migrated independently, tested in isolation
- Transparent: tool signatures and return types don't change
- Minimal framework coupling: no dependency on FastMCP internals
- Clear separation: `http_proxy.py` is a single file with a predictable pattern per tool

**Cons:**
- Boilerplate: ~48 proxy functions, each with argument mapping and response normalization
- Two code paths to maintain: DB service layer + HTTP proxy

**Effort:** M

### Approach 2: Service-layer backend abstraction

Create an abstract `CoordinationBackend` interface that both the DB service layer and an HTTP proxy implement. At startup, instantiate the appropriate backend. MCP tool handlers call `backend.acquire_lock(...)` instead of `get_lock_service().acquire(...)`.

**Pros:**
- Cleaner OOP design with single dispatch point
- Easier to add new backends (e.g., gRPC) in the future
- Tool handlers become backend-agnostic

**Cons:**
- Large refactor: every service (`locks.py`, `memory.py`, `work_queue.py`, etc.) needs an abstract interface extracted
- Risk of interface drift between DB and HTTP implementations
- Over-engineering for a two-backend system

**Effort:** L

### Approach 3: Generic JSON-over-HTTP proxy with tool registry

Build a tool registry that maps `(tool_name, args_dict)` → `(method, path, body_transform, response_transform)`. A single generic `proxy_call()` function handles all tools using the registry. No per-tool proxy functions.

**Pros:**
- Minimal code: one dispatcher + one registry dict instead of 48 functions
- Easy to maintain: adding a new tool is one registry entry
- Self-documenting: the registry is the complete MCP↔HTTP mapping

**Cons:**
- Harder to handle tools with non-trivial argument transformations (e.g., agent_id injection, response flattening)
- Debugging is less straightforward (generic dispatch vs named functions)
- Type safety is weaker (registry entries are dicts, not typed function signatures)

**Effort:** M

### Selected Approach

**Approach 1: Tool-level HTTP proxy module** — selected because:
- The boilerplate is mechanical and can be generated from the existing tool signatures
- Per-tool functions provide clear stack traces, easy testing, and explicit type handling
- No refactoring of the existing service layer is required
- Approach 3's registry pattern can be adopted later as a simplification if the per-tool pattern proves too verbose

## Key Decisions from Discovery

| Decision | Choice | Rationale |
|----------|--------|-----------|
| DB-only tools (no HTTP endpoint) | Add HTTP endpoints first | Full coverage ensures the proxy is complete; no partial-capability mode |
| Code reuse with coordination_bridge.py | New adapter in MCP server | Clean separation; bridge serves skills, proxy serves MCP |
| Transport detection timing | Startup probe | Single decision point; avoids per-call latency from failed DB attempts |
| HTTP auth | COORDINATION_API_KEY env var | Consistent with existing bridge pattern; no new auth mechanisms |

## Dependencies

- `coordination_api.py` must be updated with new endpoints before the proxy can cover those tools
- Railway deployment must be redeployed with the new endpoints

## Risks

| Risk | Mitigation |
|------|------------|
| HTTP latency vs direct DB | Probe results cached at startup; no per-call detection overhead |
| API key management | Reuse existing COORDINATION_API_KEY env var pattern |
| Response format drift between DB and HTTP paths | Tests assert identical response shapes from both backends |
| Railway deployment downtime during HTTP endpoint additions | New endpoints are additive; no breaking changes to existing endpoints |
