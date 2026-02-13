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
| **Episodic Memory** | Cross-session learning with relevance scoring and time-decay |
| **Guardrails Engine** | Deterministic pattern matching to detect and block destructive operations |
| **Agent Profiles** | Trust levels (0-4), operation restrictions, resource limits |
| **Audit Trail** | Immutable append-only logging for all coordination operations |
| **Network Policies** | Domain-level allow/block lists for outbound access control |
| **Cedar Policy Engine** | Optional AWS Cedar-based authorization (alternative to native profiles) |
| **GitHub Coordination** | Branch tracking, label locks, webhook-driven sync for restricted-network agents |
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
|  Supabase (PostgREST) / Direct PostgreSQL        |
|  - file_locks, work_queue, agent_sessions       |
|  - episodic_memories, operation_guardrails      |
|  - agent_profiles, audit_log, network_domains   |
|  - cedar_policies, verification_results         |
|  - PL/pgSQL functions (atomic operations)       |
+-------------------------------------------------+
```

Local agents connect via MCP (stdio transport). Cloud agents with restricted network access connect via HTTP API. Both share state through Supabase with PostgreSQL functions ensuring atomic operations for lock acquisition and task claiming.

## Implementation Status

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1 (MVP)** | File locking, work queue, MCP server, Supabase persistence | **Implemented** |
| **Phase 2** | Episodic memory, session handoffs, agent discovery, GitHub coordination, DB factory | **Implemented** |
| **Phase 3** | Guardrails engine, verification gateway, agent profiles, audit trail, network policies, Cedar policy engine | **Implemented** |
| Phase 4 | Multi-agent orchestration via Strands SDK, AgentCore integration | Specified |

### Implementation Details

- **Database**: 10 migrations, 10+ tables, 15+ PL/pgSQL functions, DatabaseClient protocol with Supabase and asyncpg backends
- **MCP Server**: 18 tools + 7 resources
- **Services**: Locks, Work Queue, Handoffs, Discovery, Memory, Guardrails, Profiles, Audit, Network Policies, Policy Engine (Cedar + Native), GitHub Coordination
- **Tests**: 250+ unit tests (respx mocks)

## MCP Tools

| Tool | Description |
|------|-------------|
| `acquire_lock` | Get exclusive access to a file before editing |
| `release_lock` | Release a lock when done editing |
| `check_locks` | See which files are currently locked |
| `get_work` | Claim a task from the work queue |
| `complete_work` | Mark a claimed task as completed/failed (with guardrails pre-check) |
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

## Future Capabilities

**Phase 4** enables multi-agent orchestration via the Strands SDK with agents-as-tools, swarm, and graph patterns, backed by AgentCore for runtime isolation and policy enforcement.

## Design Documentation

The agent coordinator is formally specified across three OpenSpec specs:

- [`openspec/specs/agent-coordinator/spec.md`](../openspec/specs/agent-coordinator/spec.md) — 33 requirements covering file locking, memory, work queue, MCP/HTTP interfaces, verification, guardrails, orchestration, and audit
- [`openspec/specs/agent-coordinator/design.md`](../openspec/specs/agent-coordinator/design.md) — Architecture decisions, component details, verification tiers, and key implementation patterns
- [`openspec/specs/evaluation-framework/spec.md`](../openspec/specs/evaluation-framework/spec.md) — Evaluation harness for benchmarking coordination effectiveness

## Getting Started

See [`agent-coordinator/README.md`](../agent-coordinator/README.md) for setup instructions, including Supabase configuration, dependency installation, Claude Code MCP integration, and development commands.
