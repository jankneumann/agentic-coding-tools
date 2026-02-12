# Agent Coordinator

A multi-agent coordination system that enables AI coding agents — Claude Code, Codex, Gemini, and others — to collaborate safely on shared codebases.

## Problem

When multiple AI agents work on the same codebase simultaneously, they face merge conflicts from concurrent edits, context loss between sessions, no shared task tracking, and safety risks from autonomous destructive operations. The agent coordinator solves these by providing shared infrastructure for locking, queuing, discovery, and verification.

## Core Capabilities

| Capability | Description |
|------------|-------------|
| **File Locking** | Exclusive locks with TTL and auto-expiration prevent concurrent edits to the same file |
| **Work Queue** | Task assignment with priorities, dependencies, and atomic claiming prevents double-work |
| **Session Handoffs** | Structured handoff documents preserve context across agent sessions |
| **Agent Discovery** | Agents register capabilities and status, enabling peers to find collaborators |
| **Heartbeat Monitoring** | Periodic heartbeats detect unresponsive agents; stale agents' locks are auto-released |
| **MCP Integration** | Native tool integration with Claude Code and other MCP clients via stdio transport |

## Architecture

```
LOCAL AGENTS (Claude Code)     CLOUD AGENTS (Claude API)
         |                              |
         | MCP (stdio)                  | HTTP API
         v                              v
+-------------------------------------------------+
|  coordination_mcp.py / coordination_api.py      |
|  - acquire_lock / release_lock / check_locks    |
|  - get_work / complete_work / submit_work       |
+-------------------------+-----------------------+
                          | HTTP (PostgREST)
                          v
+-------------------------------------------------+
|  Supabase                                       |
|  - file_locks, work_queue, agent_sessions       |
|  - PL/pgSQL functions (atomic operations)       |
+-------------------------------------------------+
```

Local agents connect via MCP (stdio transport). Cloud agents with restricted network access connect via HTTP API. Both share state through Supabase with PostgreSQL functions ensuring atomic operations for lock acquisition and task claiming.

## Implementation Status

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1 (MVP)** | File locking, work queue, MCP server, Supabase persistence | **Implemented** |
| Phase 2 | HTTP API for cloud agents, episodic memory, GitHub-mediated coordination | Specified |
| Phase 3 | Guardrails engine, verification gateway, agent profiles, approval queues | Specified |
| Phase 4 | Multi-agent orchestration via Strands SDK, AgentCore integration | Specified |

### Phase 1 Details

- **Database**: 3 tables (`file_locks`, `work_queue`, `agent_sessions`) + 5 PL/pgSQL functions
- **MCP Server**: 6 tools + 2 resources
- **Tests**: 31 unit tests (respx mocks) + 29 integration tests (local Supabase via docker-compose)

## MCP Tools (Phase 1)

| Tool | Description |
|------|-------------|
| `acquire_lock` | Get exclusive access to a file before editing |
| `release_lock` | Release a lock when done editing |
| `check_locks` | See which files are currently locked |
| `get_work` | Claim a task from the work queue |
| `complete_work` | Mark a claimed task as completed or failed |
| `submit_work` | Add a new task to the work queue |

## Future Capabilities

**Phase 2** adds an HTTP API for cloud-hosted agents (Claude Code Web, Codex Cloud), episodic memory for cross-session learning, and GitHub-mediated coordination as a fallback for agents with restricted network access.

**Phase 3** introduces a guardrails engine with deterministic pattern matching to prevent destructive operations, a verification gateway that routes changes to appropriate testing tiers, and configurable agent profiles with trust levels.

**Phase 4** enables multi-agent orchestration via the Strands SDK with agents-as-tools, swarm, and graph patterns, backed by AgentCore for runtime isolation and policy enforcement.

## Design Documentation

The agent coordinator is formally specified across three OpenSpec specs:

- [`openspec/specs/agent-coordinator/spec.md`](../openspec/specs/agent-coordinator/spec.md) — 33 requirements covering file locking, memory, work queue, MCP/HTTP interfaces, verification, guardrails, orchestration, and audit
- [`openspec/specs/agent-coordinator/design.md`](../openspec/specs/agent-coordinator/design.md) — Architecture decisions, component details, verification tiers, and key implementation patterns
- [`openspec/specs/evaluation-framework/spec.md`](../openspec/specs/evaluation-framework/spec.md) — Evaluation harness for benchmarking coordination effectiveness

## Getting Started

See [`agent-coordinator/README.md`](../agent-coordinator/README.md) for setup instructions, including Supabase configuration, dependency installation, Claude Code MCP integration, and development commands.
