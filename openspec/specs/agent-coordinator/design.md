# Agent Coordinator - Design

## Context

This system coordinates multiple AI coding agents working on shared codebases. The architecture must handle:
- Local agents (Claude Code, Codex CLI, Aider) connecting via MCP
- Cloud agents (Claude API, Codex Cloud) connecting via HTTP
- Real-time coordination without conflicts
- Persistent memory across sessions
- Automated verification routing

## Goals / Non-Goals

### Goals
- Prevent file conflicts between concurrent agents
- Enable agents to learn from past sessions
- Provide task orchestration across agent types
- Route changes to appropriate verification tier

### Non-Goals
- Replace version control (Git remains source of truth)
- Provide IDE integration (agents handle their own interfaces)
- Implement the verification execution (delegates to GitHub Actions, NTM, E2B)

## Architecture

```
LOCAL AGENTS                           CLOUD AGENTS
(Claude Code, Codex CLI)               (Claude API, Codex Cloud)
         │                                      │
         │ MCP (stdio)                          │ HTTP + API Key
         ▼                                      ▼
┌─────────────────┐                   ┌─────────────────┐
│ COORDINATION    │                   │ COORDINATION    │
│ MCP SERVER      │                   │ HTTP API        │
│ (FastMCP)       │                   │ (FastAPI)       │
└────────┬────────┘                   └────────┬────────┘
         │                                      │
         └──────────────┬───────────────────────┘
                        ▼
              ┌─────────────────┐
              │    SUPABASE     │
              │                 │
              │ • file_locks    │
              │ • memory_*      │
              │ • work_queue    │
              │ • changesets    │
              │ • verification  │
              └─────────────────┘
                        │
                        ▼
              ┌─────────────────┐
              │  VERIFICATION   │
              │  GATEWAY        │
              │                 │
              │ Routes changes  │
              │ to appropriate  │
              │ verification    │
              │ tier            │
              └─────────────────┘
```

## Decisions

### Decision: Supabase as Backend
**Rationale**: Real-time subscriptions, RLS for access control, Postgres functions for atomic operations. Single service handles persistence, real-time, and auth.

**Alternatives considered**:
- Redis: Fast but lacks structured queries and real-time subscriptions
- Custom PostgreSQL: More ops overhead, no built-in real-time

### Decision: MCP for Local Agents
**Rationale**: Native tool integration, automatic schema discovery, no SDK needed. Local agents like Claude Code have built-in MCP support.

**Alternatives considered**:
- HTTP API only: Would work but MCP provides better integration experience
- Custom protocol: Unnecessary complexity

### Decision: HTTP API for Cloud Agents
**Rationale**: Cloud environments can't run MCP servers (no stdio access). HTTP is universally accessible.

### Decision: Hybrid Read/Write Pattern
**Rationale**: Reads direct to Supabase (fast), writes via API (coordinated). Allows optimistic reads while maintaining coordination on writes.

### Decision: Three-Layer Memory
**Rationale**: Mirrors human cognitive architecture. Episodic for experiences, Working for active context, Procedural for learned skills. Each serves different retrieval patterns.

## Component Details

### File: `coordination_mcp.py`
- **Technology**: FastMCP + Python
- **Purpose**: MCP server for local agents
- **Tools**: `acquire_lock`, `release_lock`, `check_locks`, `remember`, `recall`, `get_work`, `complete_work`, `submit_work`
- **Resources**: `locks://current`, `work://pending`, `newsletters://status`

### File: `coordination_api.py`
- **Technology**: FastAPI + Python
- **Purpose**: HTTP API for cloud agents
- **SDK**: `AgentCoordinationClient` class for easy integration

### File: `gateway.py`
- **Technology**: FastAPI + Python
- **Purpose**: Verification routing engine
- **Webhooks**: `/webhook/github`, `/webhook/agent`

## Verification Tiers

| Tier | Name | Executor | Use Case |
|------|------|----------|----------|
| 0 | STATIC | Inline | Linting, type checking |
| 1 | UNIT | GitHub Actions | Isolated unit tests |
| 2 | INTEGRATION | Local NTM / E2B | Tests requiring services |
| 3 | SYSTEM | Local NTM | Full environment tests |
| 4 | MANUAL | Human | Security-sensitive changes |

## Key Patterns

### Atomic Lock Acquisition
```sql
-- Uses INSERT ... ON CONFLICT to prevent race conditions
INSERT INTO file_locks (file_path, locked_by, ...)
VALUES (...)
ON CONFLICT (file_path) DO NOTHING
RETURNING TRUE INTO v_acquired;
```

### Atomic Task Claiming
```sql
-- Uses FOR UPDATE SKIP LOCKED to prevent double-claiming
SELECT * FROM work_queue
WHERE status = 'pending'
ORDER BY priority
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

### Memory Deduplication
```sql
-- Check for similar recent memory before inserting
SELECT id FROM memory_episodic
WHERE agent_id = p_agent_id
  AND event_type = p_event_type
  AND summary = p_summary
  AND created_at > NOW() - INTERVAL '1 hour';
```

## File Structure

```
agent-coordinator/
├── README.md
├── requirements.txt
├── docker-compose.yml          # Local development
├── .env.example
│
├── src/
│   ├── __init__.py
│   ├── coordination_mcp.py     # MCP server for local agents
│   ├── coordination_api.py     # HTTP API for cloud agents
│   ├── gateway.py              # Verification routing
│   ├── config.py               # Environment configuration
│   └── db.py                   # Shared Supabase client
│
├── supabase/
│   ├── migrations/
│   │   ├── 001_core_schema.sql
│   │   └── 002_memory_schema.sql
│   └── seed.sql                # Default policies
│
├── tests/
│   ├── test_locks.py
│   ├── test_memory.py
│   ├── test_work_queue.py
│   └── test_gateway.py
│
└── docs/
    ├── ARCHITECTURE.md
    ├── MCP_INTEGRATION.md
    └── API_REFERENCE.md
```

## Configuration

### MCP Server Configuration
```json
// ~/.claude/mcp.json
{
  "servers": {
    "coordination": {
      "command": "python",
      "args": ["/path/to/coordination_mcp.py"],
      "env": {
        "SUPABASE_URL": "https://xxx.supabase.co",
        "SUPABASE_SERVICE_KEY": "...",
        "AGENT_ID": "claude-code-1",
        "AGENT_TYPE": "claude_code"
      }
    }
  }
}
```

### Environment Variables
```bash
# Supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=eyJ...  # Full access for API
SUPABASE_ANON_KEY=eyJ...     # Read-only for agents

# Agent Identity (set per agent instance)
AGENT_ID=claude-code-1
AGENT_TYPE=claude_code
SESSION_ID=session-abc

# API Security
COORDINATION_API_KEYS=key1,key2,key3

# Verification
GITHUB_TOKEN=ghp_...
E2B_API_KEY=...
```

## Risks / Trade-offs

### Risk: Lock Starvation
- **Mitigation**: TTL on all locks ensures automatic release. Monitor for agents that frequently fail to release locks.

### Risk: Memory Storage Growth
- **Mitigation**: Implement retention policies. Archive old episodic memories. Compress procedural memories.

### Risk: Verification Bottleneck
- **Mitigation**: Tier 0 (static) is inline and fast. Higher tiers are async. Monitor queue depth.

### Trade-off: Consistency vs Availability
- Chose consistency for writes (coordinated via Supabase functions)
- Allows eventual consistency for reads (direct Supabase queries)

## Open Questions

1. **Memory embedding model**: Should we use pgvector with embeddings for semantic search, or stick with tag-based retrieval?

2. **Cross-repo coordination**: How to handle agents working on multiple related repositories?

3. **Trust scores**: Should we implement per-agent trust scores that affect verification requirements?

4. **Context compression**: What's the right algorithm for compressing working memory when it exceeds token budget?

## References

- [FastMCP Documentation](https://github.com/jlowin/fastmcp) - MCP server framework
- [Supabase Realtime](https://supabase.com/docs/guides/realtime) - For agent notifications
- [E2B Sandbox](https://e2b.dev/docs) - Cloud verification environments
