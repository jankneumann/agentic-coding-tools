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

### 1. Set Up Supabase

#### Option A: Supabase Cloud (Recommended)

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to Project Settings > Database > Connection string
3. Copy your project URL and service role key
4. Run the migrations via SQL Editor (paste each file in `supabase/migrations/` in order)

#### Option B: Supabase CLI (Local Development)

```bash
# Install Supabase CLI
brew install supabase/tap/supabase

# Initialize and start local Supabase
supabase init
supabase start

# Apply migrations
supabase db push

# Get local credentials (printed after start)
# SUPABASE_URL=http://localhost:54321
# SUPABASE_SERVICE_KEY=<printed service_role key>
```

### 2. Install Dependencies

```bash
cd agent-coordinator
uv sync --all-extras
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Supabase credentials
```

### 4. Configure Claude Code

Add to `~/.claude/mcp.json`:

```json
{
  "servers": {
    "coordination": {
      "command": "python",
      "args": ["-m", "src.coordination_mcp"],
      "cwd": "/path/to/agent-coordinator",
      "env": {
        "SUPABASE_URL": "https://your-project.supabase.co",
        "SUPABASE_SERVICE_KEY": "your-service-role-key",
        "AGENT_ID": "claude-code-1",
        "AGENT_TYPE": "claude_code"
      }
    }
  }
}
```

### 5. Test the Integration

Restart Claude Code, then try:

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
│   ├── db.py                  # Database client (Supabase + Postgres)
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
│   └── coordination_mcp.py    # MCP server
├── cedar/
│   ├── schema.cedarschema     # Cedar entity type definitions
│   └── default_policies.cedar # Default authorization policies
├── supabase/
│   └── migrations/
│       ├── 001_core_schema.sql          # Locks, work queue, sessions
│       ├── 002_handoff_tables.sql       # Session handoffs
│       ├── 003_discovery_functions.sql  # Agent discovery
│       ├── 004_memory_tables.sql        # Episodic memory
│       ├── 005_guardrail_tables.sql     # Operation guardrails
│       ├── 006_profile_tables.sql       # Agent profiles
│       ├── 007_audit_tables.sql         # Audit trail
│       ├── 008_network_policy_tables.sql # Network policies
│       ├── 009_verification_tables.sql  # Verification gateway
│       └── 010_cedar_policy_store.sql   # Cedar policy storage
├── verification_gateway/
│   └── gateway.py             # Verification routing + executors
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
│  Supabase (PostgREST) / Direct PostgreSQL (asyncpg)         │
│  - file_locks, work_queue, agent_sessions                   │
│  - episodic_memories, operation_guardrails, agent_profiles  │
│  - audit_log, network_domains, cedar_policies               │
│  - PL/pgSQL functions (atomic operations)                   │
└─────────────────────────────────────────────────────────────┘
```

## Syncing Local <-> Cloud Supabase

```bash
# Link to your cloud project
supabase link --project-ref your-project-ref

# Push local migrations to cloud
supabase db push

# Or pull cloud schema to local
supabase db pull
```

## License

MIT
