# Agent Coordinator System

## OpenSpec v1.0

---

## 1. Project Overview

### 1.1 Purpose

A multi-agent coordination system that enables local agents (Claude Code, Codex CLI, Aider) and cloud agents (Claude API, Codex Cloud) to collaborate safely on shared codebases. The system provides file locking, persistent memory, work queue management, and verification routing.

### 1.2 Problem Statement

When multiple AI coding agents work on the same codebase:
- **Conflicts**: Two agents editing the same file create merge conflicts
- **Context loss**: Each agent session starts from scratch with no memory of past work
- **No orchestration**: No way to assign, track, or verify work across agents
- **Verification gap**: Cloud agents can generate code but struggle to verify it against real environments

### 1.3 Solution

A four-layer architecture with Supabase as the coordination backbone:

```
┌─────────────────────────────────────────────────────────────┐
│  GOVERNANCE LAYER    │ Dashboards, metrics, weekly review  │
├─────────────────────────────────────────────────────────────┤
│  TRUST LAYER         │ Verification Gateway, approval queue│
├─────────────────────────────────────────────────────────────┤
│  COORDINATION LAYER  │ MCP Server + HTTP API → Supabase    │
├─────────────────────────────────────────────────────────────┤
│  EXECUTION LAYER     │ Local agents (MCP) + Cloud agents   │
└─────────────────────────────────────────────────────────────┘
```

### 1.4 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Supabase as backend | Real-time subscriptions, RLS for access control, Postgres functions for atomic operations |
| MCP for local agents | Native tool integration, automatic schema discovery, no SDK needed |
| HTTP API for cloud agents | Cloud environments can't run MCP servers |
| Hybrid read/write pattern | Reads direct to Supabase (fast), writes via API (coordinated) |
| Three-layer memory | Episodic (experiences), Working (active context), Procedural (skills) |

---

## 2. Architecture

### 2.1 System Diagram

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

### 2.2 Component Summary

| Component | Technology | Purpose |
|-----------|------------|---------|
| `coordination_mcp.py` | FastMCP + Python | MCP server for local agents |
| `coordination_api.py` | FastAPI + Python | HTTP API for cloud agents |
| `gateway.py` | FastAPI + Python | Verification routing engine |
| `supabase_schema.sql` | PostgreSQL | Core tables and functions |
| `supabase_memory_schema.sql` | PostgreSQL | Memory system tables |

---

## 3. Component Specifications

### 3.1 Coordination MCP Server

**File:** `coordination_mcp.py`

**Purpose:** Expose coordination capabilities as native MCP tools for local agents.

**Tools:**

| Tool | Parameters | Returns | Description |
|------|------------|---------|-------------|
| `acquire_lock` | `file_path`, `reason?`, `ttl_minutes?` | `{success, action, expires_at?, locked_by?}` | Get exclusive file access |
| `release_lock` | `file_path` | `{success, released}` | Release a held lock |
| `check_locks` | `file_paths?` | `[{file_path, locked_by, expires_at}]` | List active locks |
| `remember` | `event_type`, `summary`, `details?`, `outcome?`, `lessons?`, `tags?` | `{success, memory_id}` | Store episodic memory |
| `recall` | `task_description`, `tags?`, `limit?` | `[{memory_type, content, relevance}]` | Retrieve relevant memories |
| `get_work` | `task_types?` | `{success, task_id?, task_type?, ...}` | Claim task from queue |
| `complete_work` | `task_id`, `success`, `result?`, `error_message?` | `{success, status}` | Mark task completed |
| `submit_work` | `task_type`, `task_description`, `input_data?`, `priority?`, `depends_on?` | `{success, task_id}` | Create new task |

**Resources:**

| URI | Description |
|-----|-------------|
| `locks://current` | All active file locks |
| `work://pending` | Tasks waiting in queue |
| `newsletters://status` | Newsletter processing status |

**Configuration:**

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

---

### 3.2 Coordination HTTP API

**File:** `coordination_api.py`

**Purpose:** HTTP API for cloud agents that can't use MCP.

**Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/locks/acquire` | Acquire file lock |
| `POST` | `/locks/release` | Release file lock |
| `GET` | `/locks/status/{file_path}` | Check lock status |
| `POST` | `/memory/episodic/store` | Store episodic memory |
| `POST` | `/memory/query` | Query relevant memories |
| `POST` | `/memory/working/update` | Update working memory |
| `POST` | `/work/claim` | Claim task from queue |
| `POST` | `/work/complete` | Mark task completed |
| `POST` | `/work/submit` | Submit new task |

**Authentication:** API key via `X-API-Key` header.

**SDK Class:** `AgentCoordinationClient` for easy cloud agent integration.

---

### 3.3 Verification Gateway

**File:** `gateway.py`

**Purpose:** Route agent-generated changes to appropriate verification tier.

**Verification Tiers:**

| Tier | Name | Executor | Use Case |
|------|------|----------|----------|
| 0 | STATIC | Inline | Linting, type checking |
| 1 | UNIT | GitHub Actions | Isolated unit tests |
| 2 | INTEGRATION | Local NTM / E2B | Tests requiring services |
| 3 | SYSTEM | Local NTM | Full environment tests |
| 4 | MANUAL | Human | Security-sensitive changes |

**Policy Structure:**

```python
VerificationPolicy(
    name="policy-name",
    tier=VerificationTier.INTEGRATION,
    executor=Executor.LOCAL_NTM,
    patterns=["src/**/*.py"],           # Files that trigger this policy
    exclude_patterns=["**/test_*.py"],  # Files to exclude
    required_env=["DATABASE_URL"],      # Required environment variables
    timeout_seconds=300,
    requires_approval=False,
)
```

**Webhook Endpoints:**

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/webhook/github` | Handle GitHub push events |
| `POST` | `/webhook/agent` | Handle agent completion notifications |
| `GET` | `/status/{changeset_id}` | Get verification status |

---

### 3.4 Database Schema

**Core Tables:**

| Table | Purpose |
|-------|---------|
| `file_locks` | Active file locks with TTL |
| `changesets` | Records of agent-generated changes |
| `verification_results` | Outcomes of verification runs |
| `verification_policies` | Configurable routing rules |
| `approval_queue` | Human review tracking |
| `agent_sessions` | Agent work sessions |

**Memory Tables:**

| Table | Purpose |
|-------|---------|
| `memory_episodic` | Experiences and their outcomes |
| `memory_working` | Active context for current tasks |
| `memory_procedural` | Learned skills and patterns |
| `work_queue` | Task assignment queue |

**Key Functions:**

| Function | Purpose |
|----------|---------|
| `acquire_file_lock(...)` | Atomic lock acquisition |
| `claim_work(...)` | Atomic task claiming with `SKIP LOCKED` |
| `store_episodic_memory(...)` | Memory storage with deduplication |
| `get_relevant_memories(...)` | Semantic memory retrieval |

---

## 4. File Structure

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

---

## 5. Implementation Plan

### Phase 1: Core Infrastructure (Priority: High)

**Objective:** Get basic coordination working between agents.

| Task | Description | Complexity |
|------|-------------|------------|
| 1.1 | Set up Supabase project and deploy core schema | Low |
| 1.2 | Implement `db.py` shared Supabase client | Low |
| 1.3 | Implement file locking (MCP tools + API endpoints) | Medium |
| 1.4 | Write tests for lock acquisition/release | Medium |
| 1.5 | Test with two Claude Code instances | Low |

**Acceptance Criteria:**
- Two agents can acquire/release locks without conflicts
- Locks auto-expire after TTL
- Lock status visible via MCP resource

---

### Phase 2: Memory System (Priority: High)

**Objective:** Enable agents to learn from past sessions.

| Task | Description | Complexity |
|------|-------------|------------|
| 2.1 | Deploy memory schema to Supabase | Low |
| 2.2 | Implement `remember` and `recall` tools | Medium |
| 2.3 | Add deduplication logic for similar memories | Medium |
| 2.4 | Implement working memory with compression | High |
| 2.5 | Add procedural memory with effectiveness tracking | Medium |

**Acceptance Criteria:**
- Agent can store and retrieve memories
- Duplicate memories are merged, not duplicated
- Memories decay in relevance over time
- Procedural skills track success rate

---

### Phase 3: Work Queue (Priority: Medium)

**Objective:** Enable task assignment and tracking.

| Task | Description | Complexity |
|------|-------------|------------|
| 3.1 | Implement `get_work`, `complete_work`, `submit_work` | Medium |
| 3.2 | Add priority-based task selection | Low |
| 3.3 | Implement dependency tracking | Medium |
| 3.4 | Add Supabase realtime subscription for new tasks | Medium |

**Acceptance Criteria:**
- Tasks claimed atomically (no double-claiming)
- Higher priority tasks claimed first
- Dependencies respected (blocked tasks not claimable)
- Agents notified of new relevant tasks

---

### Phase 4: Verification Gateway (Priority: Medium)

**Objective:** Route changes to appropriate verification.

| Task | Description | Complexity |
|------|-------------|------------|
| 4.1 | Implement policy matching engine | Medium |
| 4.2 | Add GitHub webhook handler | Medium |
| 4.3 | Implement inline executor (static analysis) | Low |
| 4.4 | Implement GitHub Actions executor | Medium |
| 4.5 | Implement NTM dispatch executor | High |
| 4.6 | Add E2B sandbox executor | High |

**Acceptance Criteria:**
- Changes automatically routed based on file patterns
- Static analysis runs inline
- Unit tests trigger GitHub Actions
- Integration tests dispatch to local NTM
- Results stored in Supabase

---

### Phase 5: Observability (Priority: Low)

**Objective:** Visibility into system operation.

| Task | Description | Complexity |
|------|-------------|------------|
| 5.1 | Create Supabase dashboard views | Low |
| 5.2 | Add Slack notifications for failures | Medium |
| 5.3 | Implement agent performance metrics | Medium |
| 5.4 | Add cost tracking (tokens used) | Low |

---

## 6. Context Files

### 6.1 Starter Implementation Files

The following files contain working implementations to seed the repository:

| File | Lines | Description |
|------|-------|-------------|
| `coordination_mcp.py` | ~450 | Complete MCP server with all tools |
| `coordination_api.py` | ~400 | Complete HTTP API with SDK |
| `gateway.py` | ~500 | Verification gateway with policies |
| `supabase_schema.sql` | ~200 | Core database schema |
| `supabase_memory_schema.sql` | ~350 | Memory system schema |

### 6.2 Key Patterns

**Atomic Lock Acquisition:**
```sql
-- Uses INSERT ... ON CONFLICT to prevent race conditions
INSERT INTO file_locks (file_path, locked_by, ...)
VALUES (...)
ON CONFLICT (file_path) DO NOTHING
RETURNING TRUE INTO v_acquired;
```

**Atomic Task Claiming:**
```sql
-- Uses FOR UPDATE SKIP LOCKED to prevent double-claiming
SELECT * FROM work_queue
WHERE status = 'pending'
ORDER BY priority
FOR UPDATE SKIP LOCKED
LIMIT 1;
```

**Memory Deduplication:**
```sql
-- Check for similar recent memory before inserting
SELECT id FROM memory_episodic
WHERE agent_id = p_agent_id
  AND event_type = p_event_type
  AND summary = p_summary
  AND created_at > NOW() - INTERVAL '1 hour';
```

### 6.3 Environment Variables

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

---

## 7. Testing Strategy

### 7.1 Unit Tests

- Lock acquisition/release logic
- Memory storage/retrieval
- Work queue claiming
- Policy matching

### 7.2 Integration Tests

- MCP server with mock Supabase
- HTTP API with mock Supabase
- Full flow: lock → work → verify

### 7.3 E2E Tests

- Two Claude Code instances coordinating
- Cloud agent submitting work, local verifying
- Memory persistence across sessions

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Lock conflicts | 0 | Count of failed merges due to conflicts |
| Memory retrieval relevance | >70% useful | Agent feedback on suggested memories |
| Task completion rate | >90% | Completed / Claimed tasks |
| Verification pass rate | >80% | First-pass verification success |
| Mean time to verify | <5 min | From push to verification complete |

---

## 9. Open Questions

1. **Memory embedding model**: Should we use pgvector with embeddings for semantic search, or stick with tag-based retrieval?

2. **Cross-repo coordination**: How to handle agents working on multiple related repositories?

3. **Trust scores**: Should we implement per-agent trust scores that affect verification requirements?

4. **Context compression**: What's the right algorithm for compressing working memory when it exceeds token budget?

---

## 10. References

- [Emanuel's Agentic Coding Flywheel](https://jeffreyemanuel.com/tldr) - Inspiration for multi-agent coordination patterns
- [FastMCP Documentation](https://github.com/jlowin/fastmcp) - MCP server framework
- [Supabase Realtime](https://supabase.com/docs/guides/realtime) - For agent notifications
- [E2B Sandbox](https://e2b.dev/docs) - Cloud verification environments
