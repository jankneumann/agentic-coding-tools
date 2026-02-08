# Tasks: Adopt Agent Relay Patterns

## Task Groups

### 1. Session Continuity Documents
**Dependencies**: None (can start immediately)
**Files**: `agent-coordinator/src/handoffs.py`, `agent-coordinator/supabase/migrations/002_handoff_documents.sql`, `agent-coordinator/src/coordination_mcp.py`

- [x] 1.1 Create `002_handoff_documents.sql` migration with `handoff_documents` table
- [x] 1.2 Create `HandoffService` in `agent-coordinator/src/handoffs.py` (following `locks.py` pattern)
- [x] 1.3 Add `write_handoff` MCP tool to `coordination_mcp.py`
- [x] 1.4 Add `read_handoff` MCP tool to `coordination_mcp.py`
- [x] 1.5 Add `handoffs://recent` MCP resource for latest handoff documents
- [x] 1.6 Write unit tests for `HandoffService`
- [ ] 1.7 Write integration tests for handoff tools

### 2. Agent Discovery
**Dependencies**: Task 1 (both modify `coordination_mcp.py` — must run sequentially)
**Files**: `agent-coordinator/src/discovery.py`, `agent-coordinator/supabase/migrations/003_agent_discovery.sql`, `agent-coordinator/src/coordination_mcp.py`

- [x] 2.1 Create `003_agent_discovery.sql` migration extending `agent_sessions` with capabilities, status, last_heartbeat, current_task columns
- [x] 2.2 Create `DiscoveryService` in `agent-coordinator/src/discovery.py`
- [x] 2.3 Add `register_session` MCP tool to `coordination_mcp.py` (accepts capabilities, current_task)
- [x] 2.4 Add `discover_agents` MCP tool to `coordination_mcp.py`
- [x] 2.5 Write unit tests for `DiscoveryService`
- [ ] 2.6 Write integration tests for discovery tools

### 3. Declarative Team Composition
**Dependencies**: None (can run parallel with Task 1 or 2 — no shared files)
**Files**: `agent-coordinator/teams.yaml`, `agent-coordinator/src/teams.py`

- [x] 3.1 Define YAML schema for `teams.yaml` (with JSON Schema for programmatic validation)
- [x] 3.2 Create reference `teams.yaml` for this project
- [x] 3.3 Create `TeamsConfig` loader in `agent-coordinator/src/teams.py`
- [x] 3.4 Write unit tests for schema validation and config loading

### 4. Lifecycle Hooks
**Dependencies**: Task 1 (needs handoff tools), Task 2 (needs register_session)
**Files**: `agent-coordinator/scripts/register_agent.py`, `agent-coordinator/scripts/deregister_agent.py`, `.claude/hooks.json`

- [x] 4.1 Validate Claude Code hooks.json support and document expected behavior
- [x] 4.2 Create `register_agent.py` script (calls register_session + read_handoff)
- [x] 4.3 Create `deregister_agent.py` script (calls write_handoff + release all locks)
- [x] 4.4 Create `.claude/hooks.json` with SessionStart/SessionEnd hooks
- [ ] 4.5 Document hook setup in `agent-coordinator/README.md`

### 5. Heartbeat and Dead Agent Detection
**Dependencies**: Task 2 (needs extended agent_sessions and discovery service)
**Files**: `agent-coordinator/src/coordination_mcp.py`, `agent-coordinator/src/discovery.py`

- [x] 5.1 Add `heartbeat` MCP tool to `coordination_mcp.py`
- [x] 5.2 Add `cleanup_dead_agents()` PostgreSQL function to migration 003 (default threshold: 15 minutes)
- [x] 5.3 Add `cleanup_dead_agents` MCP tool (or auto-run on `discover_agents`)
- [x] 5.4 Write unit tests for heartbeat and cleanup
- [ ] 5.5 Write integration tests for dead agent detection

### 6. Review Spec Deltas
**Dependencies**: Tasks 1-5 (after patterns are implemented)
**Files**: `openspec/changes/adopt-agent-relay-patterns/specs/agent-coordinator/spec.md`

- [x] 6.1 Review spec deltas match implementation reality
- [x] 6.2 Run `openspec validate adopt-agent-relay-patterns --strict` to confirm integrity
- [x] 6.3 Ensure all scenarios are testable against implemented code

Note: The consolidated spec at `openspec/specs/agent-coordinator/spec.md` will be updated during `/cleanup-feature` archival, not during implementation.

## Parallelization Summary

| Task | Can Parallelize With |
|------|---------------------|
| 1 (Session Continuity) | 3 |
| 2 (Agent Discovery) | 3 (but sequential after 1 due to shared `coordination_mcp.py`) |
| 3 (Team Composition) | 1, 2 |
| 4 (Lifecycle Hooks) | None - depends on 1, 2 |
| 5 (Heartbeat) | None - depends on 2 |
| 6 (Spec Review) | None - depends on 1-5 |

**Maximum parallel width**: 2 (Task 3 can run alongside Task 1 or Task 2)

**Execution waves**:
- Wave 1: Task 1 + Task 3 (parallel)
- Wave 2: Task 2 (sequential, shares `coordination_mcp.py` with Task 1)
- Wave 3: Task 4 + Task 5 (parallel — no shared files)
- Wave 4: Task 6 (final review)
