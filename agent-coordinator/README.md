# Agent Coordinator

Multi-agent coordination system for AI coding assistants. Enables Claude Code, Codex, Gemini, and other AI agents to collaborate safely on shared codebases.

## Features

- **File Locking** - Prevent merge conflicts with distributed locks (TTL, auto-expiration)
- **Work Queue** - Task assignment with priorities, dependencies, and atomic claiming
- **Session Handoffs** - Structured handoff documents for cross-session context
- **Agent Discovery** - Registration, heartbeat monitoring, dead agent cleanup
- **Episodic Memory** - Cross-session learning with relevance scoring and time-decay
- **Guardrails Engine** - Deterministic pattern matching to block destructive operations
- **Agent Profiles** - Trust levels (0-4), operation restrictions, resource limits
- **Audit Trail** - Immutable append-only logging for all operations
- **Network Policies** - Domain allow/block lists for outbound access control
- **Cedar Policy Engine** - Optional AWS Cedar-based authorization (alternative to native profiles)
- **GitHub Coordination** - Branch tracking, label locks, webhook-driven sync
- **MCP Server** - Native integration with Claude Code and other MCP clients

## Quick Start

### 1. Set Up the Database

The coordinator supports two PostgreSQL backends, selected via `DB_BACKEND`:

#### Option A: Docker Compose with ParadeDB (Recommended for Local Development)

Spins up a self-hosted PostgreSQL (ParadeDB) container with all migrations applied automatically on first start.

```bash
# Defaults: DB=54322
docker compose -f docker-compose.yml up -d

# If port 54322 is already in use, remap:
AGENT_COORDINATOR_DB_PORT=55432 docker compose -f docker-compose.yml up -d
```

After startup, set in `.env`:

```bash
DB_BACKEND=postgres
POSTGRES_DSN=postgresql://postgres:postgres@localhost:54322/postgres
```

For e2e tests on a remapped REST port:

```bash
BASE_URL=http://localhost:13000 uv run pytest -q tests/e2e
```

#### Option B: Supabase (Cloud-Managed Alternative)

1. Create a project at [supabase.com](https://supabase.com)
2. Go to Project Settings > Database > Connection string
3. Copy your project URL and service role key
4. Run the migrations via the SQL Editor (paste each file in `database/migrations/` in order)

Then set in `.env`:

```bash
DB_BACKEND=supabase
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=<your-service-role-key>
```

### 2. Install Dependencies

```bash
cd agent-coordinator
uv sync --all-extras
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your database credentials (POSTGRES_DSN for ParadeDB,
# or SUPABASE_URL + SUPABASE_SERVICE_KEY for Supabase)
```

### 4. Register MCP Server with CLI Agents

```bash
# Register with all agents (Claude Code, Codex CLI, Gemini CLI)
make mcp-setup

# Or individually:
make claude-mcp-setup   # Claude Code
make codex-mcp-setup    # Codex CLI
make gemini-mcp-setup   # Gemini CLI
```

This registers the coordination MCP server at user scope. Restart the CLI to activate.

### 5. Install Lifecycle Hooks (Notifications & Status Reporting)

```bash
# Install hooks/wrappers for all agents
make hooks-setup

# Or individually:
make claude-hooks-setup      # ~/.claude/settings.json
make codex-hooks-setup       # ~/.codex/hooks.json
make gemini-wrapper-install  # ~/.local/bin/gemini-coord
```

Hooks provide:
- **SessionStart**: Auto-register agent with coordinator
- **Stop**: Report status and heartbeat after each turn (Claude Code, Codex)
- **SessionEnd**: Write final handoff and deregister agent where the CLI exposes a session-end hook

Claude and Codex hook commands inherit `COORDINATION_API_URL` and
`COORDINATION_API_KEY` from the active run environment. When the key is bound in
the coordinator config, the coordinator resolves `agent_id` / `agent_type` from
that key instead of requiring hooks to set provider-specific identity variables.
Codex installs to `~/.codex/hooks.json` and currently wires `SessionStart` and `Stop`.

Gemini CLI has no hooks, so a wrapper script (`gemini-coord`) is installed instead:
```bash
gemini-coord "your prompt"   # Wraps gemini with register/report/deregister
```

### 6. Configure Notifications (Optional)

To receive push notifications for approvals, escalations, and stale agents:

```bash
# Add to .env or export:
export NOTIFICATION_CHANNELS=gmail          # gmail, telegram, webhook (comma-separated)
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USER=you@gmail.com
export SMTP_PASSWORD=your-app-password      # Gmail App Password
export NOTIFICATION_RECIPIENT_EMAIL=you@gmail.com
export NOTIFICATION_ALLOWED_SENDERS=you@gmail.com
```

Reply to notification emails to approve/deny requests, unblock escalations, or inject guidance — all from your phone.

### 7. Test the Integration

Restart your CLI agent, then try:

```
# Check available locks
Use check_locks to see current file locks

# Acquire a lock
Use acquire_lock on src/main.py with reason "testing coordination"

# Release the lock
Use release_lock on src/main.py
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `acquire_lock` | Get exclusive access to a file before editing |
| `release_lock` | Release a lock when done editing |
| `check_locks` | See which files are currently locked |
| `get_work` | Claim a task from the work queue |
| `complete_work` | Mark a claimed task as completed/failed |
| `submit_work` | Add a new task to the work queue |
| `write_handoff` | Create a structured session handoff |
| `read_handoff` | Read the latest handoff document |
| `discover_agents` | Find other active agents |
| `register_session` | Register this agent for discovery |
| `heartbeat` | Send a heartbeat signal |
| `remember` | Store an episodic memory |
| `recall` | Retrieve relevant memories |
| `check_guardrails` | Scan text for destructive patterns |
| `get_my_profile` | Get this agent's profile and trust level |
| `query_audit` | Query the audit trail |
| `check_policy` | Check operation authorization (Cedar/native) |
| `validate_cedar_policy` | Validate Cedar policy syntax |
| `report_status` | Report agent phase/status (heartbeat side effect) |

## MCP Resources

| Resource | Description |
|----------|-------------|
| `locks://current` | All active file locks |
| `work://pending` | Pending tasks in the queue |
| `handoffs://recent` | Recent session handoffs |
| `memories://recent` | Recent episodic memories |
| `guardrails://patterns` | Active guardrail patterns |
| `profiles://current` | Current agent's profile |
| `audit://recent` | Recent audit log entries |

## Cedar Policy Engine

An optional alternative to native profile-based authorization using [AWS Cedar](https://www.cedarpolicy.com/).

```bash
# Enable Cedar (requires cedarpy)
export POLICY_ENGINE=cedar

# Default is native profile-based authorization
export POLICY_ENGINE=native
```

Cedar provides declarative policies using the PARC model (Principal/Action/Resource/Context). Default policies are equivalent to native engine behavior.

## Cloud API Runtime

- Primary production cloud write API path: `src/coordination_api.py`
- Entry point: `python -m src.coordination_api`
- Legacy `verification_gateway/` is retired and not part of the runtime path.

## Colima (macOS Docker Alternative)

On macOS, [Colima](https://github.com/abiosoft/colima) provides a free, open-source Docker-compatible runtime. The coordinator auto-detects and manages Colima when no Docker daemon is available.

### Install

```bash
brew install colima docker
```

### How It Works

When `docker info` fails on macOS, the coordinator automatically:
1. Checks if Colima is installed (`which colima`)
2. Starts the VM with configured resources (`colima start --cpu 2 --memory 4 --disk 30`)
3. On Apple Silicon, uses the Virtualization framework with Rosetta (`--vm-type=vz --vz-rosetta`)
4. Verifies the Docker socket is accessible

No configuration needed — the defaults in `profiles/base.yaml` work out of the box.

### Configuration

Override Colima resource defaults in your profile's `docker.colima` block:

```yaml
docker:
  container_runtime: auto  # or "colima" to force Colima
  colima:
    cpu: 4
    memory: 8
    disk: 60
    apple_virt: true    # Use Apple Virtualization framework (Apple Silicon)
    auto_start: true    # Auto-start VM when Docker unavailable
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `colima start` hangs | Run `colima delete` then retry; check `colima status` |
| Docker socket not found | Verify `docker context ls` shows colima context |
| Rosetta errors on Intel Mac | Set `apple_virt: false` or leave default (auto-detected) |
| Want Docker Desktop instead | Set `container_runtime: docker` — Colima is only used when Docker isn't available |

## Development

```bash
# Run tests
pytest

# Run MCP server standalone (for testing)
python -m src.coordination_mcp --transport=sse --port=8082

# Lint and type check
ruff check src tests
mypy src
```

## File Structure

```
agent-coordinator/
├── src/
│   ├── __init__.py
│   ├── config.py              # Environment configuration
│   ├── db.py                  # Database abstraction (selects backend via DB_BACKEND)
│   ├── db_postgres.py         # Direct PostgreSQL backend (asyncpg) — default
│   ├── locks.py               # File locking service
│   ├── work_queue.py          # Task queue service
│   ├── handoffs.py            # Session handoff service
│   ├── discovery.py           # Agent discovery + heartbeat
│   ├── memory.py              # Episodic memory service
│   ├── guardrails.py          # Destructive operation detection
│   ├── profiles.py            # Agent profiles + trust levels
│   ├── audit.py               # Immutable audit trail
│   ├── network_policies.py    # Domain-level network controls
│   ├── policy_engine.py       # Cedar + Native policy engines
│   ├── github_coordination.py # GitHub webhook coordination
│   ├── coordination_api.py    # HTTP API for cloud agents
│   └── coordination_mcp.py    # MCP server
├── cedar/
│   ├── schema.cedarschema     # Cedar entity type definitions
│   └── default_policies.cedar # Default authorization policies
├── database/
│   └── migrations/
│       ├── 001_core_schema.sql          # Locks, work queue, sessions
│       ├── 002_handoff_documents.sql    # Session handoffs
│       ├── 003_agent_discovery.sql      # Agent discovery
│       ├── 004_memory_tables.sql        # Episodic memory
│       ├── 005_verification_tables.sql  # Verification data model
│       ├── 006_guardrails_tables.sql    # Operation guardrails
│       ├── 007_agent_profiles.sql       # Agent profiles
│       ├── 008_audit_log.sql            # Audit trail
│       ├── 009_network_policies.sql     # Network policies
│       └── 010_cedar_policy_store.sql   # Cedar policy storage
├── evaluation/
│   ├── config.py              # Evaluation harness config
│   ├── metrics.py             # Safety + coordination metrics
│   └── tasks/                 # Evaluation task definitions
├── tests/
│   ├── conftest.py
│   ├── test_locks.py
│   ├── test_work_queue.py
│   ├── test_handoffs.py
│   ├── test_discovery.py
│   ├── test_memory.py
│   ├── test_guardrails.py
│   ├── test_profiles.py
│   ├── test_audit.py
│   ├── test_network_policies.py
│   ├── test_policy_engine.py
│   ├── test_cedar_policy_engine.py
│   └── test_github_coordination.py
├── pyproject.toml
├── docker-compose.yml
└── .env.example
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Claude Code CLI / MCP Client                               │
└─────────────────────┬───────────────────────────────────────┘
                      │ MCP (stdio)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  coordination_mcp.py                                        │
│  - Locks, Work Queue, Handoffs, Discovery, Memory           │
│  - Guardrails, Profiles, Audit, Network Policies            │
│  - Cedar Policy Engine (optional)                           │
└─────────────────────┬───────────────────────────────────────┘
                      │ DatabaseClient Protocol
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  PostgreSQL via asyncpg (ParadeDB by default; Supabase opt) │
│  - file_locks, work_queue, agent_sessions                   │
│  - episodic_memories, operation_guardrails, agent_profiles  │
│  - audit_log, network_domains, cedar_policies               │
│  - PL/pgSQL functions (atomic operations)                   │
└─────────────────────────────────────────────────────────────┘
```

## Syncing Local <-> Cloud Supabase (Supabase Backend Only)

> Skip this section if you are using the default ParadeDB backend — migrations are applied automatically by the Docker entrypoint on container start.

If you are using Supabase as your backend, you can sync schema between local and cloud:

```bash
# Link to your cloud project
supabase link --project-ref your-project-ref

# Push local migrations to cloud
supabase db push

# Or pull cloud schema to local
supabase db pull
```

## Deployment

### Docker Build Context (repo root — D8 Strategy A)

The gen-eval framework was extracted to a sibling package at `packages/gen-eval/`
(see [OpenSpec change extract-gen-eval-package](../openspec/changes/extract-gen-eval-package/proposal.md)).
The `Dockerfile` now uses a **repo-root build context** so it can `COPY` both
`agent-coordinator/` and `packages/gen-eval/` in a single build:

```bash
# Local build (from the repo root, not from agent-coordinator/):
docker build -f agent-coordinator/Dockerfile -t agent-coordinator:latest .
```

**Railway dashboard (one-time prerequisite):**

Before deploying this version, update the Railway dashboard for the
Coordination API service:

| Setting | Old value | New value |
|---------|-----------|-----------|
| Settings → Source → Root Directory | `agent-coordinator` | `/` (repo root) |
| Settings → Build → Dockerfile Path | `Dockerfile` | `agent-coordinator/Dockerfile` |

The dashboard's *Source > Root Directory* takes precedence over `railway.toml`;
only the dashboard change makes the repo-root build context effective.

**Rationale:** `packages/gen-eval/` is a sibling of `agent-coordinator/`, so
the Dockerfile must see both trees.  With `context: agent-coordinator` the
`COPY packages/gen-eval/` step would fail at build time.

**Rollback:** If the dashboard change cannot be made, revert the commit on the
deployed branch that introduced the Dockerfile Strategy A pivot.  The reverted
Dockerfile uses the old `agent-coordinator/` build context and does not require
`packages/gen-eval/` to be in-context.

## License

MIT
