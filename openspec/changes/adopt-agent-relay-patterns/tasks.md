# Tasks: Adopt Agent Relay Patterns

## Task Groups

### 1. Session Continuity Documents
**Dependencies**: None (can start immediately)
**Files**: `agent-coordinator/src/coordination_mcp.py`, `agent-coordinator/supabase/migrations/002_handoff_documents.sql`, `agent-coordinator/src/handoffs.py`

- [ ] 1.1 Create `002_handoff_documents.sql` migration with `handoff_documents` table
- [ ] 1.2 Create `HandoffService` in `agent-coordinator/src/handoffs.py` (following `locks.py` pattern)
- [ ] 1.3 Add `write_handoff` MCP tool to `coordination_mcp.py`
- [ ] 1.4 Add `read_handoff` MCP tool to `coordination_mcp.py`
- [ ] 1.5 Add `handoffs://recent` MCP resource for latest handoff documents
- [ ] 1.6 Write unit tests for `HandoffService`
- [ ] 1.7 Write integration tests for handoff tools

### 2. Agent Discovery
**Dependencies**: None (can run parallel with Task 1)
**Files**: `agent-coordinator/src/coordination_mcp.py`, `agent-coordinator/supabase/migrations/003_agent_discovery.sql`, `agent-coordinator/src/discovery.py`

- [ ] 2.1 Create `003_agent_discovery.sql` migration extending `agent_sessions`
- [ ] 2.2 Create `DiscoveryService` in `agent-coordinator/src/discovery.py`
- [ ] 2.3 Add `discover_agents` MCP tool to `coordination_mcp.py`
- [ ] 2.4 Extend `register_session` to accept capabilities and current task
- [ ] 2.5 Write unit tests for `DiscoveryService`
- [ ] 2.6 Write integration tests for discovery tools

### 3. Declarative Team Composition
**Dependencies**: None (can run parallel with Tasks 1-2)
**Files**: `agent-coordinator/teams.yaml`, `agent-coordinator/src/teams.py`

- [ ] 3.1 Define `teams.yaml` JSON schema
- [ ] 3.2 Create reference `teams.yaml` for this project
- [ ] 3.3 Create `TeamsConfig` loader in `agent-coordinator/src/teams.py`
- [ ] 3.4 Write unit tests for schema validation and config loading

### 4. Lifecycle Hooks
**Dependencies**: Task 1 (needs handoff tools), Task 2 (needs registration)
**Files**: `agent-coordinator/scripts/register_agent.py`, `agent-coordinator/scripts/deregister_agent.py`, `.claude/hooks.json`

- [ ] 4.1 Create `register_agent.py` script (calls register_session + read_handoff)
- [ ] 4.2 Create `deregister_agent.py` script (calls write_handoff + release all locks)
- [ ] 4.3 Create `.claude/hooks.json` with SessionStart/SessionEnd hooks
- [ ] 4.4 Document hook setup in `agent-coordinator/README.md`

### 5. Heartbeat and Dead Agent Detection
**Dependencies**: Task 2 (needs extended agent_sessions)
**Files**: `agent-coordinator/src/coordination_mcp.py`, `agent-coordinator/src/discovery.py`

- [ ] 5.1 Add `heartbeat` MCP tool to `coordination_mcp.py`
- [ ] 5.2 Create `cleanup_dead_agents()` PostgreSQL function in migration 003
- [ ] 5.3 Add `cleanup_dead_agents` MCP tool (or auto-run on `discover_agents`)
- [ ] 5.4 Write unit tests for heartbeat and cleanup
- [ ] 5.5 Write integration tests for dead agent detection

### 6. Update Agent Coordinator Spec
**Dependencies**: Tasks 1-5 (after patterns are implemented)
**Files**: `openspec/specs/agent-coordinator/spec.md`

- [ ] 6.1 Add requirement for session continuity with scenarios
- [ ] 6.2 Add requirement for agent discovery with scenarios
- [ ] 6.3 Add requirement for declarative team composition with scenarios
- [ ] 6.4 Add requirement for lifecycle hooks with scenarios
- [ ] 6.5 Add requirement for heartbeat/dead agent detection with scenarios
- [ ] 6.6 Run `openspec validate --strict` to confirm spec integrity

## Parallelization Summary

| Task | Can Parallelize With |
|------|---------------------|
| 1 (Session Continuity) | 2, 3 |
| 2 (Agent Discovery) | 1, 3 |
| 3 (Team Composition) | 1, 2 |
| 4 (Lifecycle Hooks) | None - depends on 1, 2 |
| 5 (Heartbeat) | None - depends on 2 |
| 6 (Spec Update) | None - depends on 1-5 |

**Maximum parallel width**: 3 (Tasks 1-3 can all run concurrently)
