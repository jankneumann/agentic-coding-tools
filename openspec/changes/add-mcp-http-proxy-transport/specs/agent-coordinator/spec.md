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

#### Scenario: Transport is fixed at startup (STARTUP-4)

- WHEN the MCP server has completed its startup probe
- AND selected a transport ("db" or "http")
- THEN the transport SHALL NOT change for the lifetime of the MCP server process
- AND if the selected backend becomes unavailable during runtime, tool calls SHALL fail rather than switch transports

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
- AND the HTTP API returns a 4xx (except 401) or 5xx status code
- THEN the proxy SHALL return a dict with "success": false and an "error" field
- AND the error field SHALL include the HTTP status code and response body

#### Scenario: Proxy handles request timeout (PROXY-4)

- WHEN transport is "http"
- AND the HTTP request exceeds the configured timeout (default 5 seconds)
- THEN the proxy SHALL return a dict with "success": false and "error": "timeout"

#### Scenario: Proxy handles authentication failure (PROXY-5)

- WHEN transport is "http"
- AND the HTTP API returns 401 Unauthorized
- THEN the proxy SHALL return a dict with "success": false and "error": "authentication_failed"
- AND the error message SHALL indicate that COORDINATION_API_KEY may be missing or invalid

#### Scenario: Proxy handles network connectivity errors (PROXY-6)

- WHEN transport is "http"
- AND the HTTP request fails due to connection refused, DNS resolution failure, or other network error
- THEN the proxy SHALL return a dict with "success": false and "error": "connection_error"
- AND the error message SHALL include the underlying network error description

#### Scenario: Proxy validates target URL (PROXY-7)

- WHEN transport is "http"
- THEN the proxy SHALL validate COORDINATION_API_URL against an allowlist of schemes (http, https) and hosts (localhost, COORDINATION_ALLOWED_HOSTS)
- AND the proxy SHALL reject URLs targeting disallowed hosts to prevent SSRF

### Requirement: Complete HTTP API Coverage

The coordination HTTP API SHALL expose endpoints for all MCP tools, enabling full proxy coverage. All write endpoints SHALL require X-API-Key authentication. Read-only endpoints (GET) SHALL NOT require authentication, matching existing API conventions.

#### Scenario: Discovery endpoints available (HTTP-1)

- WHEN the HTTP API is running
- THEN POST /discovery/register SHALL accept agent registration (requires API key)
- AND GET /discovery/agents SHALL return active agents
- AND POST /discovery/heartbeat SHALL update agent heartbeat (requires API key)
- AND POST /discovery/cleanup SHALL remove dead agents (requires API key)

#### Scenario: Discovery endpoint rejects unauthorized access (HTTP-1a)

- WHEN a POST request is made to /discovery/register without X-API-Key header
- THEN the endpoint SHALL return 401 Unauthorized

#### Scenario: Gen-eval endpoints available (HTTP-2)

- WHEN the HTTP API is running
- THEN GET /gen-eval/scenarios SHALL list available scenarios
- AND POST /gen-eval/validate SHALL validate scenario YAML (requires API key)
- AND POST /gen-eval/create SHALL generate scenario scaffolds (requires API key)
- AND POST /gen-eval/run SHALL execute gen-eval test runs (requires API key)

#### Scenario: Issue search and status endpoints available (HTTP-3)

- WHEN the HTTP API is running
- THEN POST /issues/search SHALL search issues by query text and filters (requires API key)
- AND POST /issues/ready SHALL mark an issue as ready (requires API key)
- AND GET /issues/blocked SHALL list blocked issues

#### Scenario: Issue search with no results (HTTP-3a)

- WHEN POST /issues/search is called with a query that matches no issues
- THEN the endpoint SHALL return 200 with an empty list

#### Scenario: Get task by ID endpoint available (HTTP-4)

- WHEN the HTTP API is running
- THEN GET /work/task/{task_id} SHALL return a specific task's details

#### Scenario: Get task with invalid ID (HTTP-4a)

- WHEN GET /work/task/{task_id} is called with a non-existent task_id
- THEN the endpoint SHALL return 404 Not Found

#### Scenario: Permission request endpoint available (HTTP-5)

- WHEN the HTTP API is running
- THEN POST /permissions/request SHALL create a session-scoped permission grant (requires API key)

#### Scenario: Approval submission and check endpoints available (HTTP-6)

- WHEN the HTTP API is running
- THEN POST /approvals/request SHALL submit a new approval request (requires API key)
- AND GET /approvals/{request_id} SHALL return the status of a specific approval request

#### Scenario: Approval check with invalid ID (HTTP-6a)

- WHEN GET /approvals/{request_id} is called with a non-existent request_id
- THEN the endpoint SHALL return 404 Not Found

### Requirement: MCP Resources in Proxy Mode

MCP resources SHALL gracefully handle proxy mode.

#### Scenario: Resources return unavailable message in proxy mode

- WHEN transport is "http"
- AND a resource is accessed (e.g., locks://current)
- THEN the resource SHALL return a human-readable message indicating it is unavailable in proxy mode
- AND the message SHALL suggest using the corresponding tool instead
