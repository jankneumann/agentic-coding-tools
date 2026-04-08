# Contracts: add-mcp-http-proxy-transport

## Evaluated Contract Sub-types

| Sub-type | Applicable? | Rationale |
|----------|-------------|-----------|
| OpenAPI | No | New HTTP endpoints follow existing patterns in coordination_api.py. The API doesn't have a standalone OpenAPI spec to extend. |
| Database | No | No schema changes — all new endpoints delegate to existing service layer and tables. |
| Event | No | No new event types introduced. |
| Type generation | No | No new shared types that cross package boundaries. |

## Notes

The 15 new HTTP endpoints added in Phase 1 follow the established patterns in `coordination_api.py`:
- Pydantic request models for POST bodies
- X-API-Key authentication for write endpoints
- Service layer delegation (same services used by MCP tools)

The HTTP proxy module (`src/http_proxy.py`) is internal to the agent-coordinator package and doesn't expose a contracted interface to other packages.
