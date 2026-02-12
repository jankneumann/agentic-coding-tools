# Agent Coordinator

Multi-agent coordination system for AI coding assistants. Enables Claude Code, Codex, Gemini, and other AI agents to collaborate safely on shared codebases.

## Features (Phase 1 MVP)

- **File Locking** - Prevent merge conflicts with distributed locks
- **Work Queue** - Task assignment with priorities and dependencies
- **MCP Server** - Native integration with Claude Code and other MCP clients

## Quick Start

### 1. Set Up Supabase

You have two options for the database:

#### Option A: Supabase Cloud (Recommended for MVP)

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to Project Settings → Database → Connection string
3. Copy your project URL and service role key
4. Run the migration via SQL Editor:
   - Open SQL Editor in Supabase dashboard
   - Paste contents of `supabase/migrations/001_core_schema.sql`
   - Click "Run"

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

When the coordination server is configured, these tools are available:

| Tool | Description |
|------|-------------|
| `acquire_lock` | Get exclusive access to a file before editing |
| `release_lock` | Release a lock when done editing |
| `check_locks` | See which files are currently locked |
| `get_work` | Claim a task from the work queue |
| `complete_work` | Mark a claimed task as completed/failed |
| `submit_work` | Add a new task to the work queue |

## MCP Resources

| Resource | Description |
|----------|-------------|
| `locks://current` | All active file locks |
| `work://pending` | Pending tasks in the queue |

## Usage Example

```python
# In Claude Code conversation:
# 1. Check if file is available
result = check_locks(file_paths=["src/auth.py"])
# Returns [] if not locked

# 2. Acquire lock before editing
result = acquire_lock(file_path="src/auth.py", reason="fixing auth bug")
# Returns {"success": true, "action": "acquired", "expires_at": "..."}

# 3. Make your changes...

# 4. Release lock when done
result = release_lock(file_path="src/auth.py")
# Returns {"success": true, "action": "released"}
```

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
│   ├── config.py           # Environment configuration
│   ├── db.py               # Supabase client
│   ├── locks.py            # File locking service
│   ├── work_queue.py       # Task queue service
│   └── coordination_mcp.py # MCP server
├── supabase/
│   └── migrations/
│       └── 001_core_schema.sql
├── tests/
│   ├── conftest.py
│   ├── test_locks.py
│   └── test_work_queue.py
├── pyproject.toml
├── docker-compose.yml      # Local Supabase (alternative)
└── .env.example
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Claude Code CLI                                            │
│  (or other MCP client)                                      │
└─────────────────────┬───────────────────────────────────────┘
                      │ MCP (stdio)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  coordination_mcp.py                                        │
│  - acquire_lock / release_lock / check_locks                │
│  - get_work / complete_work / submit_work                   │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP (PostgREST)
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  Supabase                                                   │
│  - file_locks table                                         │
│  - work_queue table                                         │
│  - agent_sessions table                                     │
│  - PL/pgSQL functions (atomic operations)                   │
└─────────────────────────────────────────────────────────────┘
```

## Syncing Local ↔ Cloud Supabase

If you develop locally and want to sync to cloud:

```bash
# Link to your cloud project
supabase link --project-ref your-project-ref

# Push local migrations to cloud
supabase db push

# Or pull cloud schema to local
supabase db pull
```

## Future Phases

- **Phase 2**: HTTP API for cloud agents, episodic memory, GitHub-mediated coordination
- **Phase 3**: Guardrails engine, verification gateway, approval queues
- **Phase 4**: Multi-agent swarms via Strands SDK

## License

MIT
