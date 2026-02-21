# Change: add-port-allocator

## Why

When multiple coding agents run parallel validation flows (e.g., `/validate-feature` in separate worktrees), each spins up its own docker-compose stack. All stacks compete for the same default host ports (3000, 4000, 54322, 8081), causing bind failures that block parallel execution. Manual port remapping is error-prone and doesn't scale.

The agent-coordinator already parameterizes docker-compose ports via environment variables, but there is no automated allocation mechanism — agents must guess or manually coordinate port ranges. Additionally, several code paths still hardcode `localhost:3000`, silently breaking any remapping attempt. A lightweight, standalone port allocator service would let agents request conflict-free port sets and receive a ready-to-use environment configuration.

## What Changes

- **Add `src/port_allocator.py` service**: In-memory port range allocator with lease-based TTL tracking. Assigns a block of ports (DB, REST, Realtime, API) per session/worktree. Works entirely in-memory — no Supabase or database dependency required.

- **Add `PortAllocatorConfig` to `src/config.py`**: New config dataclass with `PORT_ALLOC_BASE` (default: 10000), `PORT_ALLOC_RANGE` (default: 100), `PORT_ALLOC_TTL_MINUTES` (default: 120), and `PORT_ALLOC_MAX_SESSIONS` (default: 20).

- **Add MCP tools `allocate_ports` and `release_ports`**: Agents call `allocate_ports(session_id)` to get a conflict-free port assignment and env snippet. Call `release_ports(session_id)` to free the allocation.

- **Add HTTP endpoints `POST /ports/allocate` and `POST /ports/release`**: Cloud agent equivalents of the MCP tools.

- **Add `GET /ports/status` endpoint**: Lists active port allocations for debugging.

- **Generate `COMPOSE_PROJECT_NAME` per session**: Each allocation includes a unique project name (`ac-<session-hash>`) so docker-compose stacks don't collide on container names, networks, or volumes.

- **Generate `.env` snippet output**: Each allocation returns a complete env block ready to `source` or write to a `.env` file, containing all port variables plus `COMPOSE_PROJECT_NAME`.

- **Fix hardcoded `localhost:3000` in validate-feature SKILL.md**: Replace hardcoded health check URL (line 181) and spec compliance example (line 345) with env-var-driven equivalents. Apply across all skill copies (`.claude/`, `.codex/`, `.gemini/`, `skills/`).

- **Fix hardcoded `POSTGREST_URL` in integration test conftest.py**: Make `agent-coordinator/tests/integration/conftest.py` read from `AGENT_COORDINATOR_REST_PORT` env var instead of hardcoding `http://localhost:3000`.

- **Forward port env vars in docker-compose invocations**: Update validate-feature SKILL.md docker-compose commands to explicitly pass `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, and `AGENT_COORDINATOR_REALTIME_PORT`.

## Impact

**Affected specs:**
- `agent-coordinator` — New capability: port allocation (delta spec in `specs/agent-coordinator/spec.md`)

**Affected architecture layers:**
- **Coordination** — New port allocator service at service layer
- **Execution** — Updated validation skill and test configuration

**Major code touchpoints:**
- `agent-coordinator/src/port_allocator.py` (new)
- `agent-coordinator/src/config.py` (add `PortAllocatorConfig`)
- `agent-coordinator/src/coordination_mcp.py` (add 2 MCP tools)
- `agent-coordinator/src/coordination_api.py` (add 3 HTTP endpoints)
- `agent-coordinator/tests/test_port_allocator.py` (new)
- `agent-coordinator/tests/integration/conftest.py` (fix hardcoded port)
- `skills/validate-feature/SKILL.md` + `.claude/` + `.codex/` + `.gemini/` copies (fix hardcoded ports, forward env vars)
