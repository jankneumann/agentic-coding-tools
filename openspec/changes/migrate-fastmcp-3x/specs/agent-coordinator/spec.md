# Spec Delta: agent-coordinator (migrate-fastmcp-3x)

## MODIFIED Requirements

### Requirement: MCP Server Framework Version

The agent-coordinator MCP server SHALL use fastmcp version 3.2.3 or higher as its MCP protocol framework.

#### Scenario: Dependency resolves to 3.x
WHEN `uv sync` is run in agent-coordinator/
THEN the installed fastmcp version MUST be >= 3.2.3
AND the installed version MUST be < 4.0.0

### Requirement: MCP Server Transport

The coordination MCP server SHALL support stdio and HTTP Streamable transports for client connections.

#### Scenario: Stdio transport for local agents
WHEN the server starts with transport="stdio"
THEN it MUST accept MCP protocol messages over stdin/stdout
AND Claude Code clients MUST be able to invoke all 28 tools

#### Scenario: HTTP transport for network agents
WHEN the server starts with transport="http"
THEN it MUST listen on the configured host and port
AND clients MUST be able to connect via HTTP Streamable protocol
AND the SSE transport option MUST NOT be offered

### Requirement: Tool Decorator Compatibility

All MCP tools SHALL be decorated with the fastmcp 3.x preferred decorator syntax.

#### Scenario: Tools use bare decorator
WHEN coordination_mcp.py is inspected
THEN all tool definitions MUST use `@mcp.tool` (without parentheses)
AND all tools MUST remain callable via the MCP protocol
AND tool metadata (name, description, parameter schema) MUST be preserved

### Requirement: Resource Decorator Compatibility

All MCP resources SHALL continue to function with fastmcp 3.x resource registration.

#### Scenario: Resources remain accessible
WHEN a client requests resource listing
THEN all 10 resources MUST be listed with correct URIs
AND reading any resource MUST return the expected content

### Requirement: MCP Client Compatibility

The gen-eval MCP client SHALL use the fastmcp 3.x Client API correctly.

#### Scenario: Client connects and calls tools
WHEN the MCP client connects to a running coordination server
THEN it MUST use async context manager protocol (`async with Client(url)`)
AND `call_tool(name, arguments)` MUST return results
AND structured data MUST be accessible via `result.data` or content blocks

#### Scenario: Client handles connection lifecycle
WHEN the client is used across multiple tool calls
THEN it MUST properly manage the session lifecycle
AND it MUST NOT leak connections or context managers
