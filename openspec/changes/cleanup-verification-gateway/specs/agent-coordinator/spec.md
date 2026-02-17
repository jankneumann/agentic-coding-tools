## MODIFIED Requirements

### Requirement: HTTP API Interface

The system SHALL provide HTTP API for cloud agents that cannot use MCP protocol.

- Authentication SHALL use API key via `X-API-Key` header
- API keys MAY be bound to specific agent identities for spoofing prevention
- All coordination capabilities SHALL have equivalent HTTP endpoints
- The API SHALL delegate to the service layer (locks, memory, work queue, guardrails, profiles, audit) rather than making direct database calls
- The API SHALL be implemented as a FastAPI application with a factory function `create_coordination_api()`
- Configuration SHALL use `ApiConfig` dataclass loaded from environment variables (`API_HOST`, `API_PORT`, `COORDINATION_API_KEYS`, `COORDINATION_API_KEY_IDENTITIES`)

#### Scenario: Cloud agent acquires lock via HTTP
- **WHEN** cloud agent sends `POST /locks/acquire` with valid API key
- **THEN** system delegates to lock service and returns JSON response

#### Scenario: Invalid API key
- **WHEN** request is made without valid `X-API-Key` header
- **THEN** system returns 401 Unauthorized

#### Scenario: Identity-bound API key prevents spoofing
- **WHEN** API key is bound to agent identity `{"agent_id": "agent-1", "agent_type": "codex"}`
- **AND** request specifies a different `agent_id`
- **THEN** system returns 403 Forbidden

#### Scenario: Health check
- **WHEN** client sends `GET /health`
- **THEN** system returns 200 with `{"status": "ok", "version": "..."}` without requiring authentication

#### Scenario: Read-only endpoints skip auth
- **WHEN** client sends `GET /locks/status/{path}` without API key
- **THEN** system returns lock status (200) without requiring authentication
