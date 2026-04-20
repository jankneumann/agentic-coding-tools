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
            │   PostgreSQL    │
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
| `src/http_proxy.py` | HTTP proxy transport for MCP server (fallback when local DB unavailable) |
| `src/config.py` | Configuration from environment variables |
| `src/locks.py` | File locking service |
| `src/memory.py` | Episodic memory service |
| `src/work_queue.py` | Task queue service |
| `src/guardrails.py` | Destructive operation detection |
| `src/profiles.py` | Agent profiles and trust levels |
| `src/audit.py` | Audit trail service |
| `src/policy_engine.py` | Authorization (native or Cedar) |
| `src/db.py` | Database abstraction layer |
| `src/db_postgres.py` | Direct PostgreSQL backend |
| `src/event_bus.py` | Generalized LISTEN/NOTIFY event bus |
| `src/notifications/` | Pluggable notifier (Gmail, Telegram, webhook channels) |
| `src/status.py` | Notification token lifecycle management |
| `src/watchdog.py` | Periodic health monitoring (stale agents, aging approvals) |
| `scripts/report_status.py` | Claude/Codex Stop hook for status reporting |
| `scripts/gemini_wrapper.sh` | Gemini CLI wrapper with lifecycle management |
| `database/migrations/*.sql` | Database schema |

## Production Cloud API Path

- Primary production cloud write API runtime is `src/coordination_api.py`.
- Legacy `verification_gateway/` is retired and should not be used for runtime or new integration work.

## Development Commands

```bash
# Install dependencies
uv sync --all-extras

# Run MCP server (for testing)
python -m src.coordination_mcp --transport=http --port=8082

# Run HTTP API
python -m src.coordination_api  # Runs on :8081

# Run tests
pytest -m "not e2e and not integration"

# Type checking
mypy --strict src/

# Linting
ruff check .

# Verify Dockerfile COPY coverage for src/ imports
# (catches the class of bug where code imports from a local package
# that isn't bundled in the runtime container)
python scripts/check_docker_imports.py --data-dir cedar --data-dir profiles
```

## Dockerfile ↔ src/ Contract

The Dockerfile's selective `COPY` statements are effectively part of the deployment contract:
every local package imported by anything in `src/` must have a matching
`COPY <pkg>/ /app/<pkg>/` in the runtime stage, or the import will succeed in
tests (where the full source tree is mounted) but fail at runtime in production.

Two CI jobs enforce this contract:

1. **`check-docker-imports`** — a static analyzer (`scripts/check_docker_imports.py`)
   that parses every `.py` file under `src/`, collects top-level package names,
   and verifies each is either stdlib, installed in the venv, or COPY'd in the
   Dockerfile. Fast (~1s), catches the specific bug class.
2. **`docker-smoke-import`** — builds the actual Docker image and runs a smoke
   test that imports the critical modules (`src.coordination_api`,
   `src.coordination_mcp`, `src.http_proxy`, `evaluation.gen_eval.mcp_service`)
   inside the built container, then constructs the FastAPI app factory.
   Catches anything the static check misses (system libs, PYTHONPATH issues,
   lazy imports from third-party code).

If you add a new top-level package import in `src/`, add a matching `COPY`
statement to `Dockerfile` **and** update the smoke test's `modules` list.

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
- `report_status(agent_id, change_id, phase, ...)` - Report agent status (heartbeat side effect)

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
| `/handoffs/write` | POST | Yes | Write handoff document |
| `/handoffs/read` | POST | Yes | Read handoff documents |
| `/policy/check` | POST | Yes | Check policy authorization |
| `/policy/validate` | POST | Yes | Validate Cedar policy text |
| `/profiles/me` | GET | Yes | Get agent profile |
| `/audit` | GET | Yes | Query audit trail |
| `/health` | GET | No | Health check |
| `/status/report` | POST | No | Report agent status (heartbeat side effect) |
| `/notifications/test` | POST | Yes | Send test notification to all channels |
| `/notifications/status` | GET | No | Channel health and config status |

## Database Tables

**Core:**
- `file_locks` - Active locks with TTL
- `work_queue` - Task assignment
- `notification_tokens` - Short-lived reply tokens for email/messaging

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

# HTTP proxy transport (optional fallback when local DB unavailable)
# When set, the MCP server probes POSTGRES_DSN at startup; if unreachable,
# it routes tool calls through the HTTP API at COORDINATION_API_URL instead.
COORDINATION_API_URL=https://coord.yourdomain.com
COORDINATION_API_KEY=your-api-key
COORDINATION_ALLOWED_HOSTS=coord.yourdomain.com  # SSRF allowlist for non-localhost

# HTTP API
API_HOST=0.0.0.0
API_PORT=8081
COORDINATION_API_KEYS=key1,key2
COORDINATION_API_KEY_IDENTITIES={"key1": {"agent_id": "agent-1", "agent_type": "codex"}}

# Notifications (optional — omit NOTIFICATION_CHANNELS to disable)
NOTIFICATION_CHANNELS=gmail              # gmail,telegram,webhook (comma-separated)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your-app-password
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=you@gmail.com
IMAP_PASSWORD=your-app-password
NOTIFICATION_SENDER_EMAIL=you@gmail.com
NOTIFICATION_RECIPIENT_EMAIL=you@gmail.com
NOTIFICATION_ALLOWED_SENDERS=you@gmail.com
TELEGRAM_BOT_TOKEN=...                   # Optional: Telegram Bot API token
TELEGRAM_CHAT_ID=...                     # Optional: Telegram chat to notify
WEBHOOK_URL=https://ntfy.sh/my-topic     # Optional: generic webhook endpoint
WATCHDOG_INTERVAL_SECONDS=60             # Watchdog check frequency (default 60)
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
