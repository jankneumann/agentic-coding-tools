# CLAUDE.md - Agent Coordinator Project Context

## Project Summary

This is a **multi-agent coordination system** that enables AI coding agents (Claude Code, Codex, Gemini) to collaborate safely on shared codebases. It provides:

- **File locking** - Prevent merge conflicts when multiple agents edit files
- **Persistent memory** - Three-layer cognitive architecture (episodic, working, procedural)
- **Work queue** - Task assignment, tracking, and dependency management
- **Verification gateway** - Route changes to appropriate testing tier

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
            ┌─────────────────┐
            │    SUPABASE     │
            │ (file_locks,    │
            │  memory_*,      │
            │  work_queue)    │
            └────────┬────────┘
                     ▼
            ┌─────────────────┐
            │    gateway.py   │
            │ (verification)  │
            └─────────────────┘
```

## Key Files

| File | Purpose |
|------|---------|
| `src/coordination_mcp.py` | MCP server - tools for local agents |
| `src/coordination_api.py` | HTTP API - endpoints for cloud agents |
| `src/gateway.py` | Verification routing engine |
| `supabase/migrations/*.sql` | Database schema |

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run MCP server (for testing)
python src/coordination_mcp.py --transport=sse --port=8082

# Run HTTP API
python src/coordination_api.py  # Runs on :8081

# Run verification gateway
python src/gateway.py  # Runs on :8080

# Deploy Supabase migrations
supabase db push
```

## MCP Tools Available

When this MCP server is configured, these tools are available:

- `acquire_lock(file_path, reason?)` - Get exclusive file access
- `release_lock(file_path)` - Release a lock
- `remember(event_type, summary, ...)` - Store a memory
- `recall(task_description, tags?)` - Retrieve relevant memories
- `get_work(task_types?)` - Claim task from queue
- `complete_work(task_id, success, result?)` - Mark task done

## Database Tables

**Core:**
- `file_locks` - Active locks with TTL
- `changesets` - Agent-generated changes
- `verification_results` - Test outcomes
- `work_queue` - Task assignment

**Memory:**
- `memory_episodic` - Past experiences
- `memory_working` - Current context
- `memory_procedural` - Learned skills

## Conventions

- **Locking**: Always acquire lock before editing shared files
- **Memory**: Store lessons learned after completing tasks
- **Work**: Use work queue for subtasks and delegation
- **Verification**: Changes auto-route to appropriate tier

## Environment Variables

```bash
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_KEY=...
AGENT_ID=claude-code-1
AGENT_TYPE=claude_code
```

## Current Implementation Status

- [x] Core schema designed
- [x] MCP server implemented
- [x] HTTP API implemented
- [x] Verification gateway implemented
- [ ] Tests
- [ ] Docker deployment
- [ ] Supabase migrations formatted
- [ ] Documentation

## Next Steps

1. Split SQL files into numbered migrations
2. Add pytest tests for core functionality
3. Create docker-compose.yml for local development
4. Test MCP integration with Claude Code
5. Add Slack notifications for verification failures
