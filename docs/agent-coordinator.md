# Agent Coordinator

A multi-agent coordination system that enables AI coding agents — Claude Code, Codex, Gemini, and others — to collaborate safely on shared codebases.

## Problem

When multiple AI agents work on the same codebase simultaneously, they face merge conflicts from concurrent edits, context loss between sessions, no shared task tracking, and safety risks from autonomous destructive operations. The agent coordinator solves these by providing shared infrastructure for locking, queuing, discovery, and verification.

## Core Capabilities

| Capability | Description |
|------------|-------------|
| **File Locking** | Exclusive locks with TTL and auto-expiration prevent concurrent edits. Supports both file paths and logical lock keys (`api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:` namespaces) |
| **Work Queue** | Task assignment with priorities, dependencies, and atomic claiming prevents double-work. Includes `get_task` by ID and orchestrator cancellation convention |
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
| **Feature Registry** | Cross-feature resource claim management with conflict analysis and parallel feasibility assessment (`FULL`/`PARTIAL`/`SEQUENTIAL`) |
| **Merge Queue** | Priority-ordered merge queue with pre-merge conflict re-validation for cross-feature coordination |

## Skill Integration Patterns

Workflow skills integrate coordinator features through a transport-aware capability model.

### Transport Model

- **CLI runtimes (Claude Codex CLI, Codex CLI, Gemini CLI)**: use MCP tools directly.
- **Web/Cloud runtimes (Claude Web, Codex Cloud/Web, Gemini Web/Cloud)**: use HTTP detection/operations via `scripts/coordination_bridge.py`.
- **Fallback**: when neither transport is available, skills run in standalone mode.

All integrated skills set:

- `COORDINATOR_AVAILABLE`
- `COORDINATION_TRANSPORT` (`mcp|http|none`)
- `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

Hooks are capability-gated and best-effort. Coordinator failures are reported informationally and do not hard-stop feature workflow execution.

### Skill-to-Capability Mapping

| Skill | Capability Hooks |
|------|-------------------|
| `/implement-feature` | lock (`CAN_LOCK`), queue (`CAN_QUEUE_WORK`), guardrails (`CAN_GUARDRAILS`), handoff read/write (`CAN_HANDOFF`) |
| `/plan-feature` | handoff read/write (`CAN_HANDOFF`), memory recall (`CAN_MEMORY`) |
| `/iterate-on-plan` | handoff read/write (`CAN_HANDOFF`), memory recall/remember (`CAN_MEMORY`) |
| `/iterate-on-implementation` | handoff read/write (`CAN_HANDOFF`), memory recall/remember (`CAN_MEMORY`) |
| `/validate-feature` | memory recall/remember (`CAN_MEMORY`) |
| `/cleanup-feature` | handoff read/write (`CAN_HANDOFF`), lock cleanup best-effort (`CAN_LOCK`) |
| `/security-review` | guardrail pre-check reporting (`CAN_GUARDRAILS`) |
| `/explore-feature` | memory recall (`CAN_MEMORY`) |
| `/parallel-implement-feature` | lock (`CAN_LOCK`), queue (`CAN_QUEUE_WORK`), guardrails (`CAN_GUARDRAILS`), handoff (`CAN_HANDOFF`), discover (`CAN_DISCOVER`), audit (`CAN_AUDIT`) |
| `/parallel-plan-feature` | handoff (`CAN_HANDOFF`), memory (`CAN_MEMORY`), discover (`CAN_DISCOVER`), policy (`CAN_POLICY`) |
| `/parallel-cleanup-feature` | lock cleanup (`CAN_LOCK`), handoff (`CAN_HANDOFF`), audit (`CAN_AUDIT`), memory (`CAN_MEMORY`) |
| `/parallel-validate-feature` | guardrails (`CAN_GUARDRAILS`), handoff (`CAN_HANDOFF`), memory (`CAN_MEMORY`), audit (`CAN_AUDIT`) |

### Setup Guidance

- CLI MCP setup and verification: `skills/setup-coordinator/SKILL.md`
- Web/Cloud HTTP setup and verification: `skills/setup-coordinator/SKILL.md`
- Shared detection preamble: `docs/coordination-detection-template.md`

For canonical skill parity, author under `skills/` and sync runtime mirrors via:

```bash
skills/install.sh --mode rsync --agents claude,codex,gemini --deps none --python-tools none
```

### Backend Scope Note

Coordinator skill integration is backend-agnostic. Neon adoption as the default cloud Postgres option is tracked in a separate coordinator infrastructure proposal; this integration change should only reference that proposal and not hard-couple skills to a specific Postgres provider.

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

- **Database**: 12 migrations, 12+ tables, 17+ PL/pgSQL functions, DatabaseClient protocol with Supabase and asyncpg backends
- **MCP Server**: 19 tools + 7 resources
- **Services**: Locks (with logical lock key namespaces), Work Queue (with `get_task` and cancellation convention), Handoffs, Discovery, Memory, Guardrails, Profiles, Audit, Network Policies, Policy Engine (Cedar + Native), GitHub Coordination, Feature Registry, Merge Queue
- **Tests**: 300+ unit tests (respx mocks + AsyncMock)

## MCP Tools

| Tool | Description |
|------|-------------|
| `acquire_lock` | Get exclusive access to a file before editing |
| `release_lock` | Release a lock when done editing |
| `check_locks` | See which files are currently locked |
| `get_work` | Claim a task from the work queue |
| `get_task` | Get a specific task by ID (for orchestrator status polling) |
| `complete_work` | Mark a claimed task as completed/failed (with guardrails pre-check). Supports `cancel_task_convention` with `error_code="cancelled_by_orchestrator"` |
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

## Parallel Workflow Coordinator Extensions

### Logical Lock Keys

Beyond file paths, the lock service accepts logical lock keys with namespace prefixes:

| Prefix | Example | Purpose |
|--------|---------|---------|
| `api:` | `api:/auth/login` | API route ownership |
| `db:` | `db:users` | Database table/migration ownership |
| `event:` | `event:user.created` | Event schema ownership |
| `flag:` | `flag:dark-mode` | Feature flag ownership |
| `env:` | `env:DATABASE_URL` | Environment variable ownership |
| `contract:` | `contract:auth-api` | Contract artifact ownership |
| `feature:` | `feature:add-auth:pause` | Feature-level coordination (pause-lock) |

See [`docs/lock-key-namespaces.md`](lock-key-namespaces.md) for the full namespace reference.

### `get_task` API

The `get_task(task_id)` endpoint enables orchestrators to poll task status by ID:

- **MCP**: `get_task` tool
- **HTTP**: `GET /api/v1/tasks/{task_id}`

This is used by the DAG scheduler to monitor package progress during parallel execution.

### Cancellation Convention

The `cancel_task_convention(task_id, reason)` helper standardizes orchestrator-initiated task cancellation:

```python
await work_queue.cancel_task_convention(
    task_id=task_id,
    reason="contract revision bump required"
)
# Calls complete(success=False) with error_code="cancelled_by_orchestrator"
```

### Feature Registry

The feature registry (`src/feature_registry.py`) manages cross-feature resource claims:

- **Register**: declare lock keys a feature will use before implementation
- **Conflict analysis**: detect overlapping claims between active features
- **Feasibility assessment**: classify as `FULL` (no overlaps), `PARTIAL` (some), or `SEQUENTIAL` (too many)
- **Deregister**: free claims when a feature completes or is cancelled

Backed by `feature_registry` table (migration `012_feature_registry.sql`).

### Merge Queue

The merge queue (`src/merge_queue.py`) orders feature merges by priority:

- **Enqueue**: add a feature's PR to the merge queue
- **Pre-merge checks**: re-validate resource conflicts before merging
- **Priority ordering**: features merge in `merge_priority` order (1=highest)
- **Mark merged**: deregister feature and free its resource claims

Uses feature registry metadata for queue state (no separate table).

## Future Capabilities

**Phase 4** enables multi-agent orchestration via the Strands SDK with agents-as-tools, swarm, and graph patterns, backed by AgentCore for runtime isolation and policy enforcement.

## Design Documentation

The agent coordinator is formally specified across three OpenSpec specs:

- [`openspec/specs/agent-coordinator/spec.md`](../openspec/specs/agent-coordinator/spec.md) — 33 requirements covering file locking, memory, work queue, MCP/HTTP interfaces, verification, guardrails, orchestration, and audit
- [`openspec/specs/agent-coordinator/design.md`](../openspec/specs/agent-coordinator/design.md) — Architecture decisions, component details, verification tiers, and key implementation patterns
- [`openspec/specs/evaluation-framework/spec.md`](../openspec/specs/evaluation-framework/spec.md) — Evaluation harness for benchmarking coordination effectiveness

## Getting Started

See [`agent-coordinator/README.md`](../agent-coordinator/README.md) for setup instructions, including Supabase configuration, dependency installation, Claude Code MCP integration, and development commands.

## Local Validation Ports

The local `docker-compose` stack supports host-port remapping so the coordinator can run alongside other services:

- `AGENT_COORDINATOR_DB_PORT` (default `54322`)
- `AGENT_COORDINATOR_REST_PORT` (default `3000`)
- `AGENT_COORDINATOR_REALTIME_PORT` (default `4000`)

Example:

```bash
AGENT_COORDINATOR_DB_PORT=55432 \
AGENT_COORDINATOR_REST_PORT=13000 \
AGENT_COORDINATOR_REALTIME_PORT=14000 \
docker compose -f agent-coordinator/docker-compose.yml up -d
```

When using remapped REST ports, run e2e tests with:

```bash
BASE_URL=http://localhost:13000 uv run pytest -q tests/e2e
```
