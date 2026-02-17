# CLAUDE.md - Agent Coordinator Project Context

## Project Summary

This is a **multi-agent coordination system** that enables AI coding agents (Claude Code, Codex, Gemini) to collaborate safely on shared codebases. It provides:

- **File locking** - Prevent merge conflicts when multiple agents edit files
- **Persistent memory** - Three-layer cognitive architecture (episodic, working, procedural)
- **Work queue** - Task assignment, tracking, and dependency management
- **Guardrails** - Detect and block destructive operations
- **Agent profiles** - Trust levels and operation restrictions
- **Audit trail** - Immutable log of all coordination operations

## Architecture

```
LOCAL AGENTS (Claude Code)     CLOUD AGENTS (Claude API)
         │                              │
         │ MCP (stdio)                  │ HTTP API
         ▼                              ▼
┌─────────────────┐           ┌─────────────────┐
│ coordination_   │           │ coordination_   │
│ mcp.py          │           │ api.py          │
└────────┬────────┘           └────────┬────────┘
         └────────────┬────────────────┘
                      ▼
              ┌───────────────┐
              │ Service Layer │
              │ (locks, memory│
              │  work_queue,  │
              │  guardrails,  │
              │  profiles,    │
              │  audit, ...)  │
              └───────┬───────┘
                      ▼
            ┌─────────────────┐
            │    SUPABASE     │
            │ (file_locks,    │
            │  memory_*,      │
            │  work_queue)    │
            └─────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `src/coordination_mcp.py` | MCP server - tools for local agents |
| `src/coordination_api.py` | HTTP API - endpoints for cloud agents |
| `src/config.py` | Configuration from environment variables |
| `src/locks.py` | File locking service |
| `src/memory.py` | Episodic memory service |
| `src/work_queue.py` | Task queue service |
| `src/guardrails.py` | Destructive operation detection |
| `src/profiles.py` | Agent profiles and trust levels |
| `src/audit.py` | Audit trail service |
| `src/policy_engine.py` | Authorization (native or Cedar) |
| `src/db.py` | Database abstraction (Supabase) |
| `src/db_postgres.py` | Direct PostgreSQL backend |
| `supabase/migrations/*.sql` | Database schema |

## Production Cloud API Path

- Primary production cloud write API runtime is `src/coordination_api.py`.
- Legacy `verification_gateway/` is retired and should not be used for runtime or new integration work.

## Development Commands

```bash
# Install dependencies
uv sync --all-extras

# Run MCP server (for testing)
python -m src.coordination_mcp --transport=sse --port=8082

# Run HTTP API
python -m src.coordination_api  # Runs on :8081

# Run tests
pytest -m "not e2e and not integration"

# Type checking
mypy --strict src/

# Linting
ruff check .
```

## MCP Tools Available

When this MCP server is configured, these tools are available:

- `acquire_lock(file_path, reason?)` - Get exclusive file access
- `release_lock(file_path)` - Release a lock
- `check_locks(file_paths?)` - Check active locks
- `remember(event_type, summary, ...)` - Store a memory
- `recall(tags?, event_type?, limit?)` - Retrieve relevant memories
- `get_work(task_types?)` - Claim task from queue
- `complete_work(task_id, success, result?)` - Mark task done
- `submit_work(task_type, description, ...)` - Create subtask
- `check_guardrails(operation_text, file_paths?)` - Check for destructive patterns
- `get_my_profile()` - View agent profile
- `query_audit(agent_id?, operation?, limit?)` - Query audit trail

## HTTP API Endpoints

All write endpoints require `X-API-Key` header.

| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/locks/acquire` | POST | Yes | Acquire file lock |
| `/locks/release` | POST | Yes | Release file lock |
| `/locks/status/{path}` | GET | No | Check lock status |
| `/memory/store` | POST | Yes | Store episodic memory |
| `/memory/query` | POST | Yes | Query memories |
| `/work/claim` | POST | Yes | Claim task |
| `/work/complete` | POST | Yes | Complete task |
| `/work/submit` | POST | Yes | Submit new task |
| `/guardrails/check` | POST | Yes | Check operation safety |
| `/profiles/me` | GET | Yes | Get agent profile |
| `/audit` | GET | Yes | Query audit trail |
| `/health` | GET | No | Health check |

## Database Tables

**Core:**
- `file_locks` - Active locks with TTL
- `work_queue` - Task assignment

**Memory:**
- `memory_episodic` - Past experiences
- `memory_working` - Current context
- `memory_procedural` - Learned skills

**Security:**
- `operation_guardrails` - Destructive patterns
- `agent_profiles` - Agent trust/permissions
- `audit_log` - Operation audit trail

## Environment Variables

```bash
# Required
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=...

# Agent identity
AGENT_ID=claude-code-1
AGENT_TYPE=claude_code

# HTTP API
API_HOST=0.0.0.0
API_PORT=8081
COORDINATION_API_KEYS=key1,key2
COORDINATION_API_KEY_IDENTITIES={"key1": {"agent_id": "agent-1", "agent_type": "codex"}}
```

## Current Implementation Status

- [x] Core schema designed
- [x] MCP server implemented (Phase 1-3 tools)
- [x] HTTP API implemented (service-layer delegation)
- [x] Service layer (locks, memory, work queue, guardrails, profiles, audit)
- [x] Policy engine (native + Cedar backends)
- [x] Agent discovery and heartbeat
- [x] Session handoff documents
- [x] Tests for coordination API
- [ ] E2E tests against running services
- [ ] Docker deployment
- [ ] Documentation
