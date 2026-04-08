# Delta Spec: Agent Coordinator — MCP HTTP Proxy Transport

## ADDED Requirements

### Requirement: HTTP Proxy Transport for MCP Server

The coordination MCP server SHALL support an HTTP proxy transport mode that routes tool calls through the coordinator's HTTP API when the local database is unavailable.

#### Scenario: Startup probe selects DB when available (STARTUP-1)

- WHEN the MCP server starts
- AND POSTGRES_DSN is set and the database is reachable
- AND COORDINATION_API_URL is set and the HTTP API is reachable
- THEN the server SHALL select "db" transport (direct service layer)
- AND all tool calls SHALL use the existing service layer path

#### Scenario: Startup probe falls back to HTTP when DB unavailable (STARTUP-2)

- WHEN the MCP server starts
- AND POSTGRES_DSN is set but the database is not reachable (connection refused or timeout within 2 seconds)
- AND COORDINATION_API_URL is set and the HTTP API responds 200 to GET /health
- THEN the server SHALL select "http" transport (proxy mode)
- AND all tool calls SHALL be routed through the HTTP proxy module

#### Scenario: Startup probe preserves failure when neither available (STARTUP-3)

- WHEN the MCP server starts
- AND the database is not reachable
- AND COORDINATION_API_URL is not set or the HTTP API is not reachable
- THEN the server SHALL default to "db" transport
- AND tool calls SHALL fail with the existing database connection error

### Requirement: HTTP Proxy Tool Coverage

The HTTP proxy module SHALL provide proxy functions for all MCP tools that have corresponding HTTP API endpoints.

#### Scenario: Proxy routes tool call to HTTP API (PROXY-1)

- WHEN transport is "http"
- AND a tool call is made (e.g., acquire_lock)
- THEN the proxy SHALL send the corresponding HTTP request to COORDINATION_API_URL
- AND the proxy SHALL include the X-API-Key header from COORDINATION_API_KEY
- AND the proxy SHALL return a response dict matching the tool's expected return format

#### Scenario: Proxy injects agent identity (PROXY-2)

- WHEN transport is "http"
- AND a tool call is made that implicitly uses agent_id (e.g., acquire_lock, heartbeat)
- THEN the proxy SHALL inject AGENT_ID and AGENT_TYPE from config into the HTTP request body
- AND the injected values MUST match the values from the MCP server's environment config

#### Scenario: Proxy maps HTTP errors to tool responses (PROXY-3)

- WHEN transport is "http"
- AND the HTTP API returns a 4xx or 5xx status code
- THEN the proxy SHALL return a dict with "success": false and an "error" field
- AND the error field SHALL include the HTTP status code and response body

#### Scenario: Proxy handles request timeout (PROXY-4)

- WHEN transport is "http"
- AND the HTTP request exceeds the configured timeout (default 5 seconds)
- THEN the proxy SHALL return a dict with "success": false and "error": "timeout"

### Requirement: Complete HTTP API Coverage

The coordination HTTP API SHALL expose endpoints for all MCP tools, enabling full proxy coverage.

#### Scenario: Discovery endpoints available (HTTP-1)

- WHEN the HTTP API is running
- THEN POST /discovery/register SHALL accept agent registration
- AND GET /discovery/agents SHALL return active agents
- AND POST /discovery/heartbeat SHALL update agent heartbeat
- AND POST /discovery/cleanup SHALL remove dead agents

#### Scenario: Gen-eval endpoints available (HTTP-2)

- WHEN the HTTP API is running
- THEN GET /gen-eval/scenarios SHALL list available scenarios
- AND POST /gen-eval/validate SHALL validate scenario YAML
- AND POST /gen-eval/create SHALL generate scenario scaffolds
- AND POST /gen-eval/run SHALL execute gen-eval test runs

#### Scenario: Issue search and status endpoints available (HTTP-3)

- WHEN the HTTP API is running
- THEN POST /issues/search SHALL search issues by query text and filters
- AND POST /issues/ready SHALL mark an issue as ready
- AND GET /issues/blocked SHALL list blocked issues

#### Scenario: Get task by ID endpoint available (HTTP-4)

- WHEN the HTTP API is running
- THEN GET /work/task/{task_id} SHALL return a specific task's details

#### Scenario: Permission request endpoint available (HTTP-5)

- WHEN the HTTP API is running
- THEN POST /permissions/request SHALL create a session-scoped permission grant

#### Scenario: Approval submission and check endpoints available (HTTP-6)

- WHEN the HTTP API is running
- THEN POST /approvals/request SHALL submit a new approval request
- AND GET /approvals/{request_id} SHALL return the status of a specific approval request

### Requirement: MCP Resources in Proxy Mode

MCP resources SHALL gracefully handle proxy mode.

#### Scenario: Resources return unavailable message in proxy mode

- WHEN transport is "http"
- AND a resource is accessed (e.g., locks://current)
- THEN the resource SHALL return a human-readable message indicating it is unavailable in proxy mode
- AND the message SHALL suggest using the corresponding tool instead
