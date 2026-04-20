# Tasks: migrate-fastmcp-3x

## Phase 1: Dependency Update and Server Migration

- [ ] 1.1 Write smoke test verifying server starts with fastmcp 3.x
  **Spec scenarios**: agent-coordinator.1 (dependency resolves to 3.x)
  **Dependencies**: None

- [ ] 1.2 Update `agent-coordinator/pyproject.toml` — change `fastmcp>=0.3.0` to `fastmcp>=3.2.3,<4.0`
  **Spec scenarios**: agent-coordinator.1 (dependency resolves to 3.x)
  **Dependencies**: 1.1

- [ ] 1.3 Run `uv sync` and verify resolution, update `uv.lock`
  **Spec scenarios**: agent-coordinator.1 (dependency resolves to 3.x)
  **Dependencies**: 1.2

## Phase 2: Server Code Migration

- [ ] 2.1 Write tests verifying all 28 tools are registered and callable after migration
  **Spec scenarios**: agent-coordinator.3 (tools use bare decorator), agent-coordinator.4 (resources accessible)
  **Dependencies**: 1.3

- [ ] 2.2 Update `coordination_mcp.py` — change `@mcp.tool()` to `@mcp.tool` (28 occurrences)
  **Spec scenarios**: agent-coordinator.3 (tools use bare decorator)
  **Dependencies**: 2.1

- [ ] 2.3 Update `coordination_mcp.py` — replace `mcp.run(transport="sse", port=port)` with `mcp.run(transport="http", host="0.0.0.0", port=port)`
  **Spec scenarios**: agent-coordinator.2 (HTTP transport), agent-coordinator.2 (SSE not offered)
  **Dependencies**: 2.1

- [ ] 2.4 Update `FastMCP()` constructor if needed — verify `version` and `instructions` kwargs are still supported in 3.x
  **Spec scenarios**: agent-coordinator.2 (stdio transport)
  **Dependencies**: 2.1

- [ ] 2.5 Verify resource decorators work unchanged — `@mcp.resource(uri)` pattern
  **Spec scenarios**: agent-coordinator.4 (resources accessible)
  **Dependencies**: 2.2

## Phase 3: Client Migration

- [ ] 3.1 Write test verifying client connects and calls a tool with 3.x API
  **Spec scenarios**: agent-coordinator.5 (client connects and calls tools), agent-coordinator.6 (connection lifecycle)
  **Dependencies**: 1.3

- [ ] 3.2 Update `mcp_client.py` — replace manual `__aenter__()` with proper `async with Client(url)` context manager
  **Spec scenarios**: agent-coordinator.6 (connection lifecycle)
  **Dependencies**: 3.1

- [ ] 3.3 Update `mcp_client.py` — adapt response parsing for 3.x `CallToolResult` (use `result.data` or `result.content`)
  **Spec scenarios**: agent-coordinator.5 (structured data accessible)
  **Dependencies**: 3.1

## Phase 4: Integration Verification

- [ ] 4.1 Run full test suite (`pytest`) — all existing tests must pass
  **Spec scenarios**: All
  **Dependencies**: 2.2, 2.3, 2.4, 2.5, 3.2, 3.3

- [ ] 4.2 Run `ruff check` and `mypy --strict` — no new lint/type errors
  **Spec scenarios**: All
  **Dependencies**: 4.1

- [ ] 4.3 Verify `make claude-mcp-setup` still registers correctly (stdio transport unchanged)
  **Spec scenarios**: agent-coordinator.2 (stdio transport for local agents)
  **Dependencies**: 4.1

- [ ] 4.4 Run gen-eval scenarios against the migrated server to verify end-to-end tool invocation
  **Spec scenarios**: agent-coordinator.5 (client connects and calls tools)
  **Dependencies**: 4.1
