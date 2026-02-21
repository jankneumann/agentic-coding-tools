# Tasks: add-port-allocator

## 1. Core Service (sequential foundation)

- [ ] 1.1 Add `PortAllocatorConfig` to config module
  **Dependencies**: None
  **Files**: `agent-coordinator/src/config.py`
  **Traces**: Port allocation configuration
  **Details**: Add `PortAllocatorConfig` dataclass with `base_port: int = 10000`, `range_per_session: int = 100`, `ttl_minutes: int = 120`, `max_sessions: int = 20`. Wire into the `Config` aggregate class and `from_env()` factory. Env vars: `PORT_ALLOC_BASE`, `PORT_ALLOC_RANGE`, `PORT_ALLOC_TTL_MINUTES`, `PORT_ALLOC_MAX_SESSIONS`.

- [ ] 1.2 Implement `PortAllocatorService` in `src/port_allocator.py`
  **Dependencies**: 1.1
  **Files**: `agent-coordinator/src/port_allocator.py` (new)
  **Traces**: Port allocation service, Port allocation lease management, Port allocation configuration, Standalone operation
  **Details**: In-memory service with `allocate(session_id) -> PortAllocation`, `release(session_id) -> bool`, `status() -> list[PortAllocation]`, and `_cleanup_expired()`. Each allocation assigns 4 ports at fixed offsets within a block: +0=db, +1=rest, +2=realtime, +3=api. Blocks are spaced by `range_per_session` (default 100). Generate `COMPOSE_PROJECT_NAME` as `ac-<session_id_hash[:8]>`. Return `env_snippet` in `export VAR=value` format (one per line): `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, `AGENT_COORDINATOR_REALTIME_PORT`, `API_PORT`, `COMPOSE_PROJECT_NAME`, `SUPABASE_URL`. No database dependency — pure in-memory dict with timestamps. Thread-safe via `threading.Lock`. Singleton getter `get_port_allocator()`. Validate config at init: `base_port >= 1024`, `range_per_session >= 4`.

- [ ] 1.3 Add unit tests for `PortAllocatorService`
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/tests/test_port_allocator.py` (new)
  **Traces**: All port allocation requirements
  **Details**: Test allocation, duplicate session (returns existing + refreshes TTL), release, idempotent release of unknown session, TTL expiry (mock time), port range exhaustion, env_snippet format, compose_project_name uniqueness, standalone operation without DB config. Pass mypy strict and ruff.

## 2. API Exposure (parallel after 1.2)

- [ ] 2.1 Add `allocate_ports`, `release_ports`, and `ports_status` MCP tools
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/src/coordination_mcp.py`
  **Traces**: MCP tool exposure
  **Details**: Add three `@mcp.tool()` functions in a new "Port Allocation" section. `allocate_ports(session_id: str)` returns `{success, allocation, env_snippet}`. `release_ports(session_id: str)` returns `{success}`. `ports_status()` returns list of active allocations with session IDs, ports, and remaining TTL. No policy engine check required (standalone operation). No audit logging required (lightweight utility).

- [ ] 2.2 Add HTTP endpoints for port allocation
  **Dependencies**: 1.2
  **Files**: `agent-coordinator/src/coordination_api.py`
  **Traces**: HTTP API exposure
  **Details**: Add `POST /ports/allocate` (requires API key), `POST /ports/release` (requires API key), `GET /ports/status` (no auth, read-only). Use same `get_port_allocator()` singleton. Return JSON with allocation details.

- [ ] 2.3 Add API tests for port allocation endpoints
  **Dependencies**: 2.1, 2.2
  **Files**: `agent-coordinator/tests/test_port_allocator_api.py` (new)
  **Traces**: MCP tool exposure, HTTP API exposure
  **Details**: Test HTTP endpoints via FastAPI test client. Test MCP tool responses. Verify standalone operation without DB. Verify idempotent allocation and release.

## 3. Fix Hardcoded Ports (parallel — no overlap with group 1 or 2)

- [ ] 3.1 Fix hardcoded ports in `skills/validate-feature/SKILL.md`
  **Dependencies**: None
  **Files**: `skills/validate-feature/SKILL.md`
  **Traces**: Validate-feature port configuration
  **Details**: Line 181: replace `http://localhost:3000/` with `http://localhost:${AGENT_COORDINATOR_REST_PORT:-3000}/`. Line 345: replace hardcoded `localhost:3000` in example with env-var-driven URL. Update docker-compose invocations to forward port env vars.

- [ ] 3.2 Sync validate-feature SKILL.md fixes to agent-specific copies
  **Dependencies**: 3.1
  **Files**: `.claude/skills/validate-feature/SKILL.md`, `.codex/skills/validate-feature/SKILL.md`, `.gemini/skills/validate-feature/SKILL.md`
  **Traces**: Validate-feature port configuration
  **Details**: Copy the fixed `skills/validate-feature/SKILL.md` content to all three agent-specific copies. Ensure consistency.

- [ ] 3.3 Fix hardcoded `POSTGREST_URL` in integration test conftest
  **Dependencies**: None
  **Files**: `agent-coordinator/tests/integration/conftest.py`
  **Traces**: Integration test port configuration
  **Details**: Change `POSTGREST_URL = "http://localhost:3000"` to read from `os.environ.get("AGENT_COORDINATOR_REST_PORT", "3000")` and construct the URL dynamically: `POSTGREST_URL = f"http://localhost:{rest_port}"`.

## 4. Quality Gates (after all implementation)

- [ ] 4.1 Run full test suite and type checks
  **Dependencies**: 1.3, 2.3, 3.1, 3.3
  **Files**: (read-only verification)
  **Traces**: All requirements
  **Details**: Run `pytest -m "not e2e and not integration"`, `mypy --strict src/`, `ruff check .` from `agent-coordinator/`. All must pass. Run `openspec validate add-port-allocator --strict`.
