# Design: MCP HTTP Proxy Transport

## Architecture

```
Claude Code                 Skills
    │                         │
    ▼                         ▼
┌──────────────────┐   ┌──────────────────┐
│ coordination_mcp │   │ coordination_    │
│ (FastMCP stdio)  │   │ bridge.py        │
│                  │   │ (HTTP fallback)  │
│  Startup probe:  │   └────────┬─────────┘
│  ┌─────────────┐ │            │
│  │ DB avail?   │ │            │
│  │ HTTP avail? │ │            │
│  └─────┬───────┘ │            │
│        ▼         │            │
│  ┌───────────┐   │            │
│  │ transport  │   │            │
│  │ = db|http  │   │            │
│  └─────┬─────┘   │            │
│        ▼         │            │
│  ┌───────────────┐│           │
│  │ http_proxy.py ││           │
│  │ (when http)   ││           │
│  │  OR           ││           │
│  │ service layer ││           │
│  │ (when db)     ││           │
│  └───────────────┘│           │
└──────────┬────────┘           │
           │                    │
           ▼                    ▼
    ┌─────────────────────────────┐
    │  coordination_api.py (HTTP) │
    │  (Railway: coord.rotkohl.ai)│
    └──────────────┬──────────────┘
                   ▼
            ┌─────────────┐
            │ PostgreSQL   │
            │ (ParadeDB)   │
            └─────────────┘
```

## D1: Startup Transport Selection

At startup (in `main()`), before registering tools:

1. **Probe POSTGRES_DSN**: Attempt `asyncpg.connect()` with 2s timeout
2. **Probe COORDINATION_API_URL**: HTTP GET to `/health` with 2s timeout
3. **Select transport**:
   - DB available → `transport = "db"` (existing behavior)
   - DB unavailable, HTTP available → `transport = "http"` (proxy mode)
   - Neither available → `transport = "db"` (fail naturally on first tool call, preserving current behavior)

The selected transport is stored as a module-level variable in `coordination_mcp.py`, read by each tool handler.

**Rationale**: Startup probe (vs per-call) avoids latency from failed DB connection attempts on every tool call. The "fail naturally" fallback for neither-available preserves the current error behavior — users see the same PostgreSQL connection error they see today.

## D2: HTTP Proxy Module (`src/http_proxy.py`)

A new module containing:

### Client Configuration

```python
@dataclass
class HttpProxyConfig:
    base_url: str          # from COORDINATION_API_URL
    api_key: str | None    # from COORDINATION_API_KEY
    agent_id: str          # from AGENT_ID
    agent_type: str        # from AGENT_TYPE
    timeout: float = 5.0   # per-request timeout
```

### HTTP Client

Uses `httpx.AsyncClient` (already a project dependency) for async HTTP calls. A single client instance is created at startup and reused across all tool calls. httpx's default connection pooling (max 100 connections, 20 per host) is sufficient for MCP's single-user sequential tool calls.

**Retry strategy**: None — fail fast. The MCP server serves a single Claude Code session; retrying masks transient errors that the user should see. The caller (Claude Code) can retry by calling the tool again.

### SSRF Protection

The proxy MUST validate `COORDINATION_API_URL` before making requests, following the same pattern as `coordination_bridge.py`:
- Only `http` and `https` schemes allowed
- Host must be in the built-in allowlist (`localhost`, `127.0.0.1`, `::1`) or `COORDINATION_ALLOWED_HOSTS` env var
- Wildcard entries (`*.domain.com`) supported for subdomain matching
- Validation happens once at startup when constructing `HttpProxyConfig`

### Per-Tool Proxy Functions

Each MCP tool gets a corresponding async proxy function:

```python
async def proxy_acquire_lock(
    file_path: str,
    reason: str | None = None,
    ttl_minutes: int | None = None,
) -> dict[str, Any]:
    """Proxy acquire_lock to POST /locks/acquire."""
    response = await _client.post("/locks/acquire", json={
        "file_path": file_path,
        "agent_id": _config.agent_id,
        "agent_type": _config.agent_type,
        "reason": reason,
        "ttl_minutes": ttl_minutes or 120,
    })
    return _normalize_response(response)
```

Key patterns:
- **Agent identity injection**: MCP tools get `agent_id` from config implicitly; HTTP endpoints require it explicitly in the request body. The proxy injects it.
- **Response normalization**: HTTP API returns Pydantic model JSON; proxy normalizes to match the dict format MCP tool handlers return.
- **Error handling**: HTTP errors (4xx, 5xx, timeouts) are mapped to `{"success": False, "error": "..."}` dicts matching MCP tool return patterns.

## D3: Tool Handler Routing

Each tool handler gains a transport check:

```python
@mcp.tool()
async def acquire_lock(...) -> dict[str, Any]:
    if _transport == "http":
        return await http_proxy.proxy_acquire_lock(file_path, reason, ttl_minutes)
    # existing DB service layer code
    service = get_lock_service()
    result = await service.acquire(...)
    return {...}
```

**Alternative considered**: Extracting tool handlers to call a generic `dispatch(tool_name, kwargs)` function. Rejected because it would obscure the existing code and make each tool harder to read. The `if _transport == "http"` pattern is explicit and grep-able.

## D4: New HTTP Endpoints

15 MCP tools need HTTP endpoints added to `coordination_api.py`:

| Group | Endpoint | Method | MCP Tool |
|-------|----------|--------|----------|
| Discovery | `/discovery/register` | POST | register_session |
| Discovery | `/discovery/agents` | GET | discover_agents |
| Discovery | `/discovery/heartbeat` | POST | heartbeat |
| Discovery | `/discovery/cleanup` | POST | cleanup_dead_agents |
| Gen-eval | `/gen-eval/scenarios` | GET | list_scenarios |
| Gen-eval | `/gen-eval/validate` | POST | validate_scenario |
| Gen-eval | `/gen-eval/create` | POST | create_scenario |
| Gen-eval | `/gen-eval/run` | POST | run_gen_eval |
| Issues | `/issues/search` | POST | issue_search |
| Issues | `/issues/ready` | POST | issue_ready |
| Issues | `/issues/blocked` | GET | issue_blocked |
| Work | `/work/task/{task_id}` | GET | get_task |
| Session Grants | `/permissions/request` | POST | request_permission |
| Approvals | `/approvals/request` | POST | request_approval |
| Approvals | `/approvals/{request_id}` | GET | check_approval |

These follow existing patterns in `coordination_api.py`: Pydantic request models, API key auth for write endpoints, service layer delegation.

## D5: MCP Config Update

The `~/.claude.json` MCP server env block needs two new variables:

```json
{
  "env": {
    "DB_BACKEND": "postgres",
    "POSTGRES_DSN": "postgresql://postgres:postgres@localhost:54322/postgres",
    "COORDINATION_API_URL": "https://coord.rotkohl.ai",
    "COORDINATION_API_KEY": "<key>",
    "AGENT_ID": "claude-code-1",
    "AGENT_TYPE": "claude_code"
  }
}
```

When both `POSTGRES_DSN` and `COORDINATION_API_URL` are set, the startup probe determines which to use. This allows seamless fallback: if you start the local DB, it takes precedence; if not, HTTP proxy kicks in.

## D6: Resources in Proxy Mode

MCP resources (`locks://current`, `handoffs://recent`, etc.) also need the DB. In proxy mode, resources should either:
- Return a message: "Resource unavailable in HTTP proxy mode. Use the corresponding tool instead."
- Or be proxied similarly (requires new HTTP endpoints for each resource)

Decision: **Return unavailable message** for resources in proxy mode. Resources are convenience features for Claude Code context windows; the tools provide the same data. Adding 10+ resource proxy endpoints is low-value.
