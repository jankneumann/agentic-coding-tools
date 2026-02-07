## Context

[Agent Relay](https://docs.agent-relay.com/introduction) is a communication middleware enabling AI coding agents to discover and message each other via a daemon + wrapper architecture. We evaluated it against our Agent Coordinator MCP system to determine whether to incorporate it or adopt specific patterns.

## Goals / Non-Goals

- **Goals:**
  - Fill coordination gaps in session continuity, agent discovery, lifecycle management
  - Adopt battle-tested patterns from Agent Relay without taking on a dependency
  - Extend the Agent Coordinator MCP server with new tools
  - Maintain architectural consistency (MCP + Supabase)

- **Non-Goals:**
  - Replace our MCP architecture with stdout injection
  - Add Agent Relay as a runtime dependency
  - Implement consensus/voting (premature, no use case)
  - Implement shadow agents (Phase 3 guardrails covers this better)
  - Support auto-spawning agents (Phase 4 scope)

## Decisions

### Decision 1: Adopt patterns, not the dependency

Agent Relay's communication layer (stdout injection + Unix domain sockets) is architecturally incompatible with our MCP-native approach. However, five of its coordination patterns fill real gaps in our system. We'll implement these patterns using our existing stack (MCP tools + Supabase tables + PostgreSQL functions).

**Alternatives considered:**
- **Add Agent Relay as dependency**: Rejected — would create parallel coordination channels, in-memory state conflicts with our durable Supabase approach, pricing tier limits on agent count
- **Build everything from scratch**: Rejected — Agent Relay has validated these patterns in production; we should learn from their design rather than reinvent

### Decision 2: Session continuity via database, not files

Agent Relay uses file-based continuity (`/tmp/relay-outbox/.../continuity`). We'll use a `handoff_documents` table in Supabase instead, enabling cross-machine access (important for Phase 2 cloud agents) and queryable history.

**Alternatives considered:**
- **File-based** (like Agent Relay): Rejected — local-only, not accessible to cloud agents
- **Git-based** (handoff docs committed to repo): Rejected — pollutes git history, race conditions on concurrent writes

### Decision 3: Heartbeat over PING/PONG

Agent Relay uses a bidirectional PING/PONG protocol via its daemon. Since we don't have a daemon process, we'll use a unidirectional heartbeat: agents call a `heartbeat` MCP tool periodically, and a cleanup function detects stale agents.

**Alternatives considered:**
- **Daemon-based PING/PONG**: Rejected — requires running a separate process; we want to avoid daemon dependencies
- **TTL-only** (current approach): Insufficient — 2-hour wait for dead agent cleanup is too long

## Risks / Trade-offs

- **Heartbeat reliability**: If an agent is busy with a long-running task (e.g., 10-minute test suite), it won't call heartbeat. Mitigation: 5-minute stale threshold is generous enough for most operations; heartbeat can be called from within Task() orchestration.
- **Handoff document size**: If sessions produce very large handoffs, database storage costs increase. Mitigation: enforce a size limit (e.g., 10KB) and use summarization.
- **Lifecycle hook compatibility**: Claude Code's hook system may change between versions. Mitigation: hooks are a thin wrapper; fallback to manual registration if hooks aren't available.

## Integration Points

### New MCP Tools (added to `coordination_mcp.py`)

| Tool | Parameters | Returns |
|------|-----------|---------|
| `write_handoff` | `summary`, `completed_work`, `in_progress`, `decisions`, `next_steps`, `relevant_files` | `{success, handoff_id}` |
| `read_handoff` | `agent_name` (optional), `limit` (default 1) | `{handoffs: [...]}` |
| `discover_agents` | `capability` (optional), `status` (optional) | `{agents: [...]}` |
| `heartbeat` | (none, uses agent identity) | `{success, session_id}` |

### New Database Migrations

**002_handoff_documents.sql:**
```sql
CREATE TABLE handoff_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_name TEXT NOT NULL,
  session_id UUID REFERENCES agent_sessions(id),
  summary TEXT NOT NULL,
  completed_work JSONB DEFAULT '[]',
  in_progress JSONB DEFAULT '[]',
  decisions JSONB DEFAULT '[]',
  next_steps JSONB DEFAULT '[]',
  relevant_files JSONB DEFAULT '[]',
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_handoff_agent ON handoff_documents(agent_name, created_at DESC);
```

**003_agent_discovery.sql:**
```sql
ALTER TABLE agent_sessions
  ADD COLUMN capabilities TEXT[] DEFAULT '{}',
  ADD COLUMN status TEXT DEFAULT 'active' CHECK (status IN ('active', 'idle', 'disconnected')),
  ADD COLUMN last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
  ADD COLUMN current_task TEXT;

CREATE OR REPLACE FUNCTION cleanup_dead_agents(stale_threshold INTERVAL DEFAULT '5 minutes')
RETURNS INTEGER AS $$
DECLARE
  cleaned INTEGER;
BEGIN
  -- Mark stale agents as disconnected
  UPDATE agent_sessions
  SET status = 'disconnected'
  WHERE status = 'active'
    AND last_heartbeat < NOW() - stale_threshold;
  GET DIAGNOSTICS cleaned = ROW_COUNT;

  -- Release locks held by disconnected agents
  DELETE FROM file_locks
  WHERE agent_id IN (
    SELECT agent_id FROM agent_sessions WHERE status = 'disconnected'
  );

  RETURN cleaned;
END;
$$ LANGUAGE plpgsql;
```

### Claude Code Lifecycle Hooks (`.claude/hooks.json`)

```json
{
  "hooks": {
    "SessionStart": [{
      "command": "python agent-coordinator/scripts/register_agent.py"
    }],
    "SessionEnd": [{
      "command": "python agent-coordinator/scripts/deregister_agent.py"
    }]
  }
}
```

### teams.yaml Schema

```yaml
# teams.yaml - Declarative team composition
team: agentic-coding-tools
agents:
  - name: lead
    role: coordinator
    capabilities: [planning, review, orchestration]
    description: Decomposes tasks and coordinates workers

  - name: implementer
    role: worker
    capabilities: [coding, testing]
    description: Implements features from OpenSpec proposals

  - name: reviewer
    role: worker
    capabilities: [review, security-analysis]
    description: Reviews PRs and checks for security issues
```

## Open Questions

- Should handoff documents have a TTL / auto-cleanup, or be retained indefinitely for historical analysis?
- Should the `teams.yaml` schema support per-agent model selection (e.g., Opus for lead, Sonnet for workers)?
- How should heartbeat interact with Task() subagents — should the orchestrator heartbeat on behalf of its workers?
