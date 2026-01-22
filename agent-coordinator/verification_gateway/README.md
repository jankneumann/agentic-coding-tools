# Agent Coordinator

Multi-agent coordination system for AI coding assistants. Enables Claude Code, Codex, Gemini, and other AI agents to collaborate safely on shared codebases.

## Features

- **🔒 File Locking** - Prevent merge conflicts with distributed locks
- **🧠 Persistent Memory** - Three-layer cognitive architecture across sessions
- **📋 Work Queue** - Task assignment with priorities and dependencies
- **✅ Verification Gateway** - Automatic routing to appropriate test environments

## Quick Start

```bash
# Clone and install
git clone https://github.com/yourorg/agent-coordinator
cd agent-coordinator
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your Supabase credentials

# Deploy database
supabase db push

# Run the services
python src/coordination_api.py &   # HTTP API on :8081
python src/gateway.py &            # Verification on :8080
```

## For Local Agents (Claude Code, Codex CLI)

Add to `~/.claude/mcp.json`:

```json
{
  "servers": {
    "coordination": {
      "command": "python",
      "args": ["/path/to/agent-coordinator/src/coordination_mcp.py"],
      "env": {
        "SUPABASE_URL": "https://xxx.supabase.co",
        "SUPABASE_SERVICE_KEY": "your-key"
      }
    }
  }
}
```

Then use coordination tools naturally:

```
# Acquire lock before editing
acquire_lock(file_path="src/main.py", reason="refactoring")

# Store what you learned
remember(
    event_type="pattern_found",
    summary="Use Redis WATCH for atomic updates",
    tags=["redis", "concurrency"]
)

# Release when done
release_lock(file_path="src/main.py")
```

## For Cloud Agents (Claude API)

Use the HTTP API:

```python
from coordination_api import AgentCoordinationClient

client = AgentCoordinationClient(
    api_url="https://your-coordinator.com",
    api_key="your-api-key",
    agent_id="claude-api-1",
    agent_type="claude_api",
)

# Same operations via HTTP
await client.acquire_lock("src/main.py")
await client.store_memory(event_type="task_completed", summary="...")
await client.release_lock("src/main.py")
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  GOVERNANCE       │ Dashboards, metrics, weekly review     │
├─────────────────────────────────────────────────────────────┤
│  TRUST            │ Verification Gateway, approval queue   │
├─────────────────────────────────────────────────────────────┤
│  COORDINATION     │ MCP Server + HTTP API → Supabase       │
├─────────────────────────────────────────────────────────────┤
│  EXECUTION        │ Local agents (MCP) + Cloud agents      │
└─────────────────────────────────────────────────────────────┘
```

## Documentation

- [OPENSPEC.md](./OPENSPEC.md) - Full system specification
- [ARCHITECTURE.md](./docs/ARCHITECTURE.md) - Detailed design
- [MCP_INTEGRATION.md](./docs/MCP_INTEGRATION.md) - MCP setup guide
- [CLAUDE.md](./CLAUDE.md) - Context for AI agents working on this repo

## Inspired By

- [Emanuel's Agentic Coding Flywheel](https://jeffreyemanuel.com/tldr)
- [MCP Protocol](https://github.com/anthropics/mcp)
- [FastMCP](https://github.com/jlowin/fastmcp)

## License

MIT
