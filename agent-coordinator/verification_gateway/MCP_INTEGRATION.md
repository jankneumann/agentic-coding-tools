# MCP Integration Guide

## Overview

The Coordination MCP Server exposes multi-agent coordination as native tools that local agents (Claude Code, Codex CLI, Aider) can use directly.

**Before MCP:**
```python
# Agent needs custom SDK and HTTP knowledge
from coordination_api import AgentCoordinationClient
client = AgentCoordinationClient(api_url="...", api_key="...")
result = await client.acquire_lock("src/main.py", reason="refactoring")
```

**After MCP:**
```
# Agent just calls the tool naturally
acquire_lock(file_path="src/main.py", reason="refactoring")
```

---

## Setup for Claude Code

### 1. Configure MCP Server

Add to `~/.claude/mcp.json`:

```json
{
  "servers": {
    "coordination": {
      "command": "python",
      "args": ["/path/to/coordination_mcp.py"],
      "env": {
        "SUPABASE_URL": "https://your-project.supabase.co",
        "SUPABASE_SERVICE_KEY": "your-service-key",
        "AGENT_TYPE": "claude_code"
      }
    }
  }
}
```

### 2. Per-Session Configuration (with NTM)

When NTM spawns agents, inject session-specific identity:

```bash
# NTM spawn script sets environment per agent
export AGENT_ID="claude-code-${PANE_ID}"
export SESSION_ID="${NTM_SESSION}"
export AGENT_TYPE="claude_code"

claude  # Starts with coordination tools available
```

NTM configuration (`~/.config/ntm/config.toml`):

```toml
[agents.claude_code]
command = "claude"
env_template = """
AGENT_ID=cc-{pane_id}
SESSION_ID={session_name}
AGENT_TYPE=claude_code
"""

[mcp.coordination]
command = "python"
args = ["/opt/coordination/coordination_mcp.py"]
# Env inherited from agent
```

---

## Available Tools

### File Locks

| Tool | Description |
|------|-------------|
| `acquire_lock(file_path, reason?, ttl_minutes?)` | Get exclusive access to a file |
| `release_lock(file_path)` | Release a lock you hold |
| `check_locks(file_paths?)` | See what's currently locked |

**Usage Pattern:**
```
# Before editing a shared file
result = acquire_lock("src/api/client.py", reason="adding retry logic")

if result.success:
    # Edit the file...
    
    # Always release when done
    release_lock("src/api/client.py")
else:
    # File is locked by: {result.locked_by}
    # Try a different task or wait
```

### Memory

| Tool | Description |
|------|-------------|
| `remember(event_type, summary, ...)` | Store a memory |
| `recall(task_description, tags?, limit?)` | Retrieve relevant memories |

**Usage Pattern:**
```
# At start of task, check for relevant experience
memories = recall(
    task_description="implement caching for API responses",
    tags=["caching", "api"]
)

# After learning something useful
remember(
    event_type="pattern_found",
    summary="Redis WATCH prevents race conditions in read-modify-write",
    outcome="success",
    lessons=["Always use WATCH when multiple clients might update same key"],
    tags=["redis", "concurrency", "caching"]
)
```

### Work Queue

| Tool | Description |
|------|-------------|
| `get_work(task_types?)` | Claim a task from the queue |
| `complete_work(task_id, success, result?, error?)` | Mark task done |
| `submit_work(task_type, description, ...)` | Create a new task |

**Usage Pattern:**
```
# Claim available work
work = get_work(task_types=["refactor", "test"])

if work.success:
    # Do the task...
    
    # Report completion
    complete_work(
        task_id=work.task_id,
        success=True,
        result={"files_changed": ["src/cache.py"]}
    )
```

### Newsletter-Specific

| Tool | Description |
|------|-------------|
| `get_pending_newsletters(limit?)` | Get newsletters needing summarization |
| `record_newsletter_summary(newsletter_id, summary, tokens)` | Record completed summary |

---

## Available Resources

Resources provide read-only context that agents can reference:

| Resource URI | Description |
|--------------|-------------|
| `locks://current` | All active file locks |
| `work://pending` | Tasks waiting in the queue |
| `newsletters://status` | Newsletter processing status |

**Usage:**
```
# Agent can read resources for context
# Claude Code: "Show me the current locks"
# -> Reads locks://current resource
```

---

## Architecture: MCP + HTTP API

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LOCAL AGENTS                                  │
│              (Claude Code, Codex CLI, Aider)                        │
│                                                                      │
│  MCP Tools Available:                                               │
│  • acquire_lock      • remember       • get_work                    │
│  • release_lock      • recall         • complete_work               │
│  • check_locks       •                • submit_work                 │
│                                                                      │
│  MCP Resources:                                                     │
│  • locks://current   • work://pending  • newsletters://status       │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ MCP Protocol (stdio)
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    COORDINATION MCP SERVER                           │
│                       (FastMCP + Python)                             │
│                                                                      │
│  • Runs as subprocess of each agent                                 │
│  • Stateless - all state in Supabase                                │
│  • Identity from environment (AGENT_ID, SESSION_ID)                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         SUPABASE                                     │
│                                                                      │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │
│  │ file_locks  │ │   memory_*  │ │ work_queue  │ │ newsletter_ │   │
│  │             │ │             │ │             │ │ processing  │   │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘   │
│                                                                      │
│  RPC Functions:                                                     │
│  • acquire_file_lock    • store_episodic_memory                     │
│  • claim_work           • get_relevant_memories                     │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▲
                               │ HTTP API (for cloud agents)
                               │
┌──────────────────────────────┴──────────────────────────────────────┐
│                    COORDINATION HTTP API                             │
│                       (FastAPI + Python)                             │
│                                                                      │
│  POST /locks/acquire    POST /memory/store    POST /work/claim      │
│  POST /locks/release    POST /memory/query    POST /work/complete   │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▲
                               │ HTTP + API Key
                               │
┌──────────────────────────────┴──────────────────────────────────────┐
│                        CLOUD AGENTS                                  │
│              (Claude API, Codex Cloud, E2B)                         │
│                                                                      │
│  Use AgentCoordinationClient SDK:                                   │
│  client.acquire_lock("src/main.py")                                 │
│  client.store_memory(event_type="...", summary="...")               │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Why Both MCP and HTTP?

| Aspect | MCP Server | HTTP API |
|--------|-----------|----------|
| **For** | Local agents | Cloud agents |
| **Auth** | Process isolation | API key |
| **Discovery** | Automatic (MCP protocol) | Manual (docs/SDK) |
| **Latency** | ~1ms (local) | ~50-200ms (network) |
| **State** | From environment | From request |

**Key insight:** Both hit the same Supabase backend. MCP is just a better interface for agents that support it.

---

## NTM Integration

NTM can manage the MCP server lifecycle:

```toml
# ~/.config/ntm/config.toml

[mcp_servers]
# Start coordination server once, shared by all agents
coordination = { 
    command = "python", 
    args = ["/opt/coordination/coordination_mcp.py", "--transport=sse", "--port=8082"],
    shared = true  # One instance for all agents
}

[agents.claude_code]
mcp_connect = ["coordination"]  # Connect to shared server
```

Or run per-agent (simpler, more isolated):

```toml
[agents.claude_code]
mcp_servers = ["coordination"]  # Each agent gets its own server process
```

---

## Testing the MCP Server

```bash
# Run in SSE mode for testing
python coordination_mcp.py --transport=sse --port=8082

# Test with curl
curl -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"method": "tools/list"}'

# Or use MCP Inspector
npx @anthropic/mcp-inspector http://localhost:8082
```

---

## Prompt Templates

The MCP server includes prompt templates for common patterns:

### `coordinate_file_edit`
```
Use: When you need to safely edit a file that others might be working on
Includes: Lock check, acquire, edit, release pattern
```

### `start_work_session`
```
Use: At the beginning of a work session
Includes: Memory recall, work queue check, lock status
```

Agents can invoke these:
```
# In Claude Code
/prompt coordinate_file_edit file_path=src/main.py task="add error handling"
```

---

## Migration from SDK to MCP

If you have agents using the HTTP SDK, migration is straightforward:

**Before (SDK):**
```python
client = AgentCoordinationClient(...)

# Explicit async/await, error handling
try:
    result = await client.acquire_lock("src/main.py")
    if result["success"]:
        # work...
        await client.release_lock("src/main.py")
except Exception as e:
    logger.error(f"Coordination error: {e}")
```

**After (MCP):**
```
# Just call the tool - MCP handles the rest
acquire_lock(file_path="src/main.py", reason="refactoring")
# work...
release_lock(file_path="src/main.py")
```

The agent doesn't need to know about HTTP, async, or error handling - MCP abstracts it away.
