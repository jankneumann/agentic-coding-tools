# agent-coordinator Specification (delta)

## ADDED Requirements

### Requirement: Code Search Dual-Surface Exposure

The coordinator SHALL expose semantic code retrieval on both agent surfaces backed by a single
shared service module (`src/code_search.py`): a `search_code` MCP tool in `coordination_mcp.py`
for local agents and a `POST /search/code` HTTP endpoint in `coordination_api.py` for cloud
agents. Both surfaces SHALL accept `query`, `repo`, `limit`, `offset`, `languages`, `paths`, and
optional `scope`, and SHALL return identical result payloads. The capability SHALL be exposed as
a tool/endpoint only — not as an MCP resource — so it remains available through the HTTP proxy
transport. Query embedding SHALL happen inside the service; callers send text only.

#### Scenario: Both surfaces return identical results

- **WHEN** the same search request is issued via the MCP tool and via `POST /search/code`
  against the same index state
- **THEN** both SHALL return the same ranked chunk list with identical scores

#### Scenario: Search works through the HTTP proxy fallback

- **WHEN** a local agent's MCP server runs in HTTP proxy mode (no local database)
- **THEN** `search_code` SHALL proxy to the coordination API and return results
- **AND** no MCP resource SHALL be required for retrieval

### Requirement: Code Search Is a Direct Read

`search_code` SHALL be classified as a read operation: it SHALL NOT acquire locks, enqueue work,
or mutate any coordination state, and it SHALL NOT trigger indexing. Re-indexing SHALL be
reachable only through the separate `index_repo` entrypoint. When the database is unreachable,
the surfaces SHALL return the coordinator's standard unavailable envelope so agents can fall back
to lexical search.

#### Scenario: Searching never mutates state

- **WHEN** 100 concurrent `search_code` calls execute
- **THEN** `file_locks`, `work_queue`, and audit-relevant coordination tables SHALL be unchanged
- **AND** no chunk table SHALL be created or modified

#### Scenario: Database outage degrades gracefully

- **WHEN** the coordinator database is unreachable and a `search_code` call arrives
- **THEN** the response SHALL be the standard unavailable envelope, not a crash or a hang beyond
  the configured timeout

### Requirement: Code Search Feature Flag

Code-search surface registration SHALL be gated by `CODE_SEARCH_ENABLED` (default off). While
disabled, the MCP tool SHALL NOT be listed, the HTTP route SHALL return 404, and no code-search
database objects beyond the additive registry migration SHALL be touched, preserving all existing
coordinator behavior.

#### Scenario: Disabled flag hides the capability

- **WHEN** `CODE_SEARCH_ENABLED` is unset and the MCP tool list is requested
- **THEN** `search_code` SHALL NOT appear
- **AND** `POST /search/code` SHALL return 404
