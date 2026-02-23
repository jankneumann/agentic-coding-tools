# Architecture Report

Generated: 2026-02-23T22:32:24.064107+00:00  
Git SHA: `b7452a1f92a8495f5e4705d6d977341350ca401e`

## System Overview

*Data sources: [architecture.graph.json](architecture.graph.json), [architecture.summary.json](architecture.summary.json), [python_analysis.json](python_analysis.json)*

This is a **Python MCP server** with 20 modules exposing **46 MCP endpoints** (37 tools, 7 resources, 2 prompts), backed by **20 Postgres tables**. The codebase contains 240 functions (111 async) and 75 classes.

| Metric | Count |
|--------|-------|
| Total nodes | 626 |
| Total edges | 224 |
| Python modules | 20 |
| Functions | 240 (111 async) |
| Classes | 75 |
| Mcp Endpoints | 46 |
| DB tables | 20 |
| Python nodes | 335 |
| Sql nodes | 291 |

## Module Responsibility Map

*Data sources: [python_analysis.json](python_analysis.json), [architecture.graph.json](architecture.graph.json)*

| Module | Layer | Role | In / Out |
|--------|-------|------|----------|
| `assurance` | Service | — | 0 / 0 |
| `audit` | Foundation | Get the global audit service instance. | 28 / 4 |
| `config` | Foundation | Get the global configuration instance. | 46 / 0 |
| `coordination_api` | Entry | Verify the API key for write operations. | 0 / 35 |
| `coordination_mcp` | Entry | Get the current agent ID from config. | 0 / 44 |
| `db` | Foundation | Factory: returns the appropriate DatabaseClient based on config. | 23 / 4 |
| `db_postgres` | Service | Coerce a PostgREST filter string value to the appropriate Python type. | 1 / 1 |
| `discovery` | Service | Get the global discovery service instance. | 6 / 8 |
| `github_coordination` | Service | Get the global GitHub coordination service instance. | 0 / 4 |
| `guardrails` | Foundation | Get the global guardrails service instance. | 10 / 7 |
| `handoffs` | Service | Get the global handoff service instance. | 4 / 9 |
| `locks` | Service | Get the global lock service instance. | 10 / 11 |
| `memory` | Service | Get the global memory service instance. | 8 / 8 |
| `network_policies` | Service | Get the global network policy service instance. | 2 / 4 |
| `policy_engine` | Foundation | Get the global policy engine based on configuration. | 17 / 15 |
| `port_allocator` | Service | Return the global ``PortAllocatorService`` singleton. | 9 / 1 |
| `profiles` | Foundation | Get the global profiles service instance. | 11 / 7 |
| `teams` | Service | Get the global teams configuration. | 0 / 0 |
| `work_queue` | Service | Get the global work queue service instance. | 10 / 23 |

**Layers**: Entry = exposes MCP endpoints; Service = domain logic; Foundation = imported by 3+ modules (config, db, audit).

## Dependency Layers

*Data source: [python_analysis.json](python_analysis.json)*

```
┌─────────────────────────────────────────────────┐
│  ENTRY       coordination_api, coordination_mcp  │
│             ↓ imports ↓                          │
│  SERVICE     assurance, db_postgres, discovery, github_coordination│
│              handoffs, locks, memory, network_policies│
│              port_allocator, teams, work_queue   │
│             ↓ imports ↓                          │
│  FOUNDATION  audit, config, db, guardrails, policy_engine, profiles│
└─────────────────────────────────────────────────┘
```

**Single points of failure** — changes to these modules ripple widely:

- `config` — imported by 16 modules
- `db` — imported by 11 modules
- `audit` — imported by 10 modules
- `policy_engine` — imported by 6 modules
- `profiles` — imported by 4 modules
- `guardrails` — imported by 3 modules

## Entry Points

*Data sources: [architecture.graph.json](architecture.graph.json), [python_analysis.json](python_analysis.json)*

### Tools (22)

| Endpoint | Description |
|----------|-------------|
| `acquire_lock` | Acquire an exclusive lock on a file before modifying it. |
| `allocate_ports` | Allocate a conflict-free port block for a parallel docker-compose stack. |
| `check_guardrails` | Check an operation for destructive patterns. |
| `check_locks` | Check which files are currently locked. |
| `check_policy` | Check if an operation is authorized by the policy engine. |
| `cleanup_dead_agents` | Clean up agents that have stopped responding. |
| `complete_work` | Mark a claimed task as completed. |
| `discover_agents` | Discover other agents working in this coordination system. |
| `get_my_profile` | Get the current agent's profile including trust level and permissions. |
| `get_work` | Claim a task from the work queue. |
| `heartbeat` | Send a heartbeat to indicate this agent is still alive. |
| `ports_status` | List all active port allocations. |
| `query_audit` | Query the audit trail for recent operations. |
| `read_handoff` | Read previous handoff documents for session continuity. |
| `recall` | Recall relevant memories from past sessions. |
| `register_session` | Register this agent session for discovery by other agents. |
| `release_lock` | Release a lock you previously acquired. |
| `release_ports` | Release a previously allocated port block. |
| `remember` | Store an episodic memory for cross-session learning. |
| `submit_work` | Submit a new task to the work queue. |
| `validate_cedar_policy` | Validate Cedar policy text against the schema. |
| `write_handoff` | Write a handoff document to preserve session context. |

### Resources (7)

| Endpoint | Description |
|----------|-------------|
| `audit://recent` | Recent audit log entries. |
| `guardrails://patterns` | Active guardrail patterns for destructive operation detection. |
| `handoffs://recent` | Recent handoff documents from agent sessions. |
| `locks://current` | All currently active file locks. |
| `memories://recent` | Recent episodic memories across all agents. |
| `profiles://current` | Current agent's profile and permissions. |
| `work://pending` | Tasks waiting to be claimed from the work queue. |

### Prompts (2)

| Endpoint | Description |
|----------|-------------|
| `coordinate_file_edit` | Template for safely editing a file with coordination. |
| `start_work_session` | Template for starting a coordinated work session. |

### Other (15)

| Endpoint | Description |
|----------|-------------|
| `/audit` | Query audit trail entries. |
| `/guardrails/check` | Check an operation for destructive patterns. |
| `/health` | Health check endpoint. |
| `/locks/acquire` | Acquire a file lock. Cloud agents call this before modifying files. |
| `/locks/release` | Release a file lock. |
| `/locks/status/{file_path:path}` | Check lock status for a file. Read-only, no API key required. |
| `/memory/query` | Query relevant memories for a task. |
| `/memory/store` | Store an episodic memory. |
| `/ports/allocate` | Allocate a block of ports for a session. |
| `/ports/release` | Release a port allocation for a session. |
| `/ports/status` | List all active port allocations. Read-only, no API key required. |
| `/profiles/me` | Get the calling agent's profile. |
| `/work/claim` | Claim a task from the work queue. |
| `/work/complete` | Mark a task as completed. |
| `/work/submit` | Submit new work to the queue. |

## Architecture Health

*Data source: [architecture.diagnostics.json](architecture.diagnostics.json)*

**680 findings** across 4 categories:

### Orphan — 273

273 symbols are unreachable from any entrypoint — may be dead code or missing wiring.

- '__init__' is unreachable from any entrypoint or test
- 'assurance' is unreachable from any entrypoint or test
- 'audit' is unreachable from any entrypoint or test
- 'config' is unreachable from any entrypoint or test
- 'coordination_api' is unreachable from any entrypoint or test
- ... and 268 more

### Reachability — 46

46 entrypoints have downstream dependencies but no DB writes or side effects.

Breakdown: 43 info, 3 warning.

- Entrypoint 'acquire_lock' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'release_lock' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'check_lock_status' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'store_memory' has downstream dependencies but none touch a DB or produce side effects
- Entrypoint 'query_memories' has downstream dependencies but none touch a DB or produce side effects
- ... and 41 more

### Test Coverage — 315

315 functions lack test references — consider adding tests for critical paths.

- Function 'AuditEntry' has no corresponding test references
- Function 'AuditResult' has no corresponding test references
- Function 'AuditService' has no corresponding test references
- Function 'AuditTimer' has no corresponding test references
- Function 'SupabaseConfig' has no corresponding test references
- ... and 310 more

### Disconnected Flow (expected) — 46

46 MCP routes have no frontend callers — expected for an MCP server (clients are AI agents, not browsers).

- Backend route 'query_audit' has no frontend callers
- Backend route 'release_lock' has no frontend callers
- Backend route 'heartbeat' has no frontend callers
- Backend route 'cleanup_dead_agents' has no frontend callers
- Backend route 'start_work_session' has no frontend callers
- ... and 41 more

## High-Impact Nodes

*Data sources: [high_impact_nodes.json](high_impact_nodes.json), [parallel_zones.json](parallel_zones.json)*

21 nodes with >= 5 transitive dependents. Changes to these ripple through the codebase — test thoroughly.

| Node | Dependents | Risk |
|------|------------|------|
| `config.get_config` | 56 | Critical — affects 56 downstream functions (14 modules affected) |
| `policy_engine.get_policy_engine` | 21 | Critical — affects 21 downstream functions (6 modules affected) |
| `audit.get_audit_service` | 19 | High — test `audit` changes thoroughly (10 modules affected) |
| `config` | 16 | High — test `config` changes thoroughly (16 modules affected) |
| `db_postgres` | 14 | High — test `db_postgres` changes thoroughly (14 modules affected) |
| `db` | 13 | High — test `db` changes thoroughly (13 modules affected) |
| `db.create_db_client` | 13 | High — test `db` changes thoroughly (12 modules affected) |
| `db.get_db` | 12 | High — test `db` changes thoroughly (11 modules affected) |
| `coordination_api.resolve_identity` | 11 | High — test `coordination_api` changes thoroughly (modules: coordination_api) |
| `audit` | 10 | High — test `audit` changes thoroughly |
| `coordination_api.authorize_operation` | 10 | High — test `coordination_api` changes thoroughly |
| `locks.get_lock_service` | 9 | Moderate |
| `profiles.get_profiles_service` | 9 | Moderate |
| `work_queue.get_work_queue_service` | 9 | Moderate |
| `guardrails.get_guardrails_service` | 8 | Moderate |
| `port_allocator.get_port_allocator` | 8 | Moderate |
| `network_policies` | 7 | Moderate |
| `profiles` | 7 | Moderate |
| `memory.get_memory_service` | 7 | Moderate |
| `policy_engine` | 6 | Moderate |
| `db_postgres._validate_identifier` | 6 | Moderate |

## Code Health Indicators

*Data source: [python_analysis.json](python_analysis.json)*

### Quick Stats

| Indicator | Value |
|-----------|-------|
| Async ratio | 111/240 (46%) |
| Docstring coverage | 163/240 (68%) |
| Dead code candidates | 109 |

### Hot Functions

Functions called by the most other functions — changes here have wide blast radius:

| Function | Callers |
|----------|---------|
| `config.get_config` | 30 |
| `audit.get_audit_service` | 18 |
| `db.get_db` | 12 |
| `policy_engine.get_policy_engine` | 11 |
| `coordination_api.resolve_identity` | 10 |
| `coordination_api.authorize_operation` | 9 |
| `locks.get_lock_service` | 8 |
| `work_queue.get_work_queue_service` | 8 |
| `guardrails.get_guardrails_service` | 7 |
| `port_allocator.get_port_allocator` | 7 |

### Dead Code Candidates

109 functions are unreachable from entrypoints via static analysis. Some may be used dynamically (e.g., classmethods, test helpers).

- **audit** (6): `from_dict`, `db`, `log_operation`, `_insert_audit_entry`, `query`, `timed`
- **config** (1): `reset_config`
- **coordination_api** (2): `verify_api_key`, `main`
- **coordination_mcp** (1): `main`
- **db** (17): `rpc`, `query`, `insert`, `update`, `delete`, `close`, ... (+11)
- **db_postgres** (7): `_get_pool`, `rpc`, `query`, `insert`, `update`, `delete`, ... (+1)
- **discovery** (5): `db`, `register`, `discover`, `heartbeat`, `cleanup_dead_agents`
- **github_coordination** (9): `from_dict`, `db`, `parse_lock_labels`, `parse_branch`, `sync_label_locks`, `sync_branch_tracking`, ... (+3)
- **guardrails** (4): `from_dict`, `db`, `_load_patterns`, `check_operation`
- **handoffs** (4): `db`, `write`, `read`, `get_recent`
- **locks** (6): `db`, `acquire`, `release`, `check`, `extend`, `is_locked`
- **memory** (3): `db`, `remember`, `recall`
- **network_policies** (2): `db`, `check_domain`
- **policy_engine** (18): `db`, `check_operation`, `check_network_access`, `_log_policy_decision`, `db`, `_load_default_policies`, ... (+12)
- **port_allocator** (6): `env_snippet`, `allocate`, `release`, `status`, `_cleanup_expired`, `reset_port_allocator`
- **profiles** (5): `from_dict`, `db`, `get_profile`, `check_operation`, `_log_denial`
- **teams** (5): `from_dict`, `get_agent`, `get_agents_with_capability`, `get_teams_config`, `reset_teams_config`
- **work_queue** (8): `db`, `_resolve_trust_level`, `claim`, `complete`, `submit`, `get_pending`, ... (+2)

## Parallel Modification Zones

*Data source: [parallel_zones.json](parallel_zones.json)*

**497 independent groups** identified. The largest interconnected group has 98 modules; 586 modules are leaf nodes (safe to modify in isolation).

**9 high-impact modules** act as coupling points — parallel changes touching these need coordination.

### Interconnected Groups

**Group 0** (98 members spanning 16 modules): `audit`, `config`, `coordination_api`, `coordination_mcp`, `db`, `discovery`, `github_coordination`, `guardrails`
  ... and 8 more modules

**Group 1** (17 members spanning 17 modules): `audit`, `config`, `coordination_api`, `coordination_mcp`, `db`, `db_postgres`, `discovery`, `github_coordination`
  ... and 9 more modules

**Group 2** (8 members spanning 1 modules): `db_postgres`

**Group 3** (5 members spanning 2 modules): `coordination_mcp`, `discovery`

**Group 4** (3 members spanning 2 modules): `discovery`, `work_queue`

**Group 5** (2 members spanning 2 modules): `network_policies`, `policy_engine`

**Group 6** (2 members spanning 1 modules): `port_allocator`

**Group 7** (2 members spanning 1 modules): `teams`

### Leaf Modules (586)

586 modules have no dependents — changes are fully isolated. 489 of the 497 groups are singletons.

## Architecture Diagrams

*Data source: [architecture.graph.json](architecture.graph.json)*

### Container View

```mermaid
flowchart TB
    Backend["Backend (335 nodes)"]
    Database["Database (291 nodes)"]
```

### Backend Components

```mermaid
flowchart TB
    __init__["__init__ (1 symbols)"]
    assurance["assurance (1 symbols)"]
    audit["audit (17 symbols)"]
    config["config (29 symbols)"]
    coordination_api["coordination_api (33 symbols)"]
    coordination_mcp["coordination_mcp (35 symbols)"]
    db["db (23 symbols)"]
    db_postgres["db_postgres (13 symbols)"]
    discovery["discovery (20 symbols)"]
    github_coordination["github_coordination (16 symbols)"]
    guardrails["guardrails (13 symbols)"]
    handoffs["handoffs (14 symbols)"]
    locks["locks (14 symbols)"]
    memory["memory (13 symbols)"]
    network_policies["network_policies (8 symbols)"]
    policy_engine["policy_engine (28 symbols)"]
    port_allocator["port_allocator (12 symbols)"]
    profiles["profiles (14 symbols)"]
    teams["teams (10 symbols)"]
    work_queue["work_queue (21 symbols)"]
    audit -->|"call, import"| config
    audit -->|"call, import"| db
    coordination_api -->|"call, import"| audit
    coordination_api -->|"call, import"| config
    coordination_api -->|"call, import"| guardrails
    coordination_api -->|"call, import"| locks
    coordination_api -->|"call, import"| memory
    coordination_api -->|"call, import"| policy_engine
    coordination_api -->|"call, import"| port_allocator
    coordination_api -->|"call, import"| profiles
    coordination_api -->|"call, import"| work_queue
    coordination_mcp -->|"call, import"| audit
    coordination_mcp -->|"call, import"| config
    coordination_mcp -->|"call, import"| discovery
    coordination_mcp -->|"call, import"| guardrails
    coordination_mcp -->|"call, import"| handoffs
    coordination_mcp -->|"call, import"| locks
    coordination_mcp -->|"call, import"| memory
    coordination_mcp -->|"call, import"| policy_engine
    coordination_mcp -->|"call, import"| port_allocator
    coordination_mcp -->|"call, import"| profiles
    coordination_mcp -->|"call, import"| work_queue
    db -->|"call, import"| config
    db -->|"import"| db_postgres
    db_postgres -->|"import"| config
    discovery -->|"call, import"| audit
    discovery -->|"call, import"| config
    discovery -->|"call, import"| db
    github_coordination -->|"call, import"| config
    github_coordination -->|"call, import"| db
    guardrails -->|"call, import"| audit
    guardrails -->|"call, import"| config
    guardrails -->|"call, import"| db
    handoffs -->|"call, import"| audit
    handoffs -->|"call, import"| config
    handoffs -->|"call, import"| db
    handoffs -->|"call, import"| policy_engine
    locks -->|"call, import"| audit
    locks -->|"call, import"| config
    locks -->|"call, import"| db
    locks -->|"call, import"| policy_engine
    memory -->|"call, import"| audit
    memory -->|"call, import"| config
    memory -->|"call, import"| db
    memory -->|"call, import"| policy_engine
    network_policies -->|"call, import"| config
    network_policies -->|"call, import"| db
    policy_engine -->|"call, import"| audit
    policy_engine -->|"call, import"| config
    policy_engine -->|"call, import"| db
    policy_engine -->|"call, import"| network_policies
    policy_engine -->|"call, import"| profiles
    port_allocator -->|"import"| config
    profiles -->|"call, import"| audit
    profiles -->|"call, import"| config
    profiles -->|"call, import"| db
    work_queue -->|"call, import"| audit
    work_queue -->|"call, import"| config
    work_queue -->|"call, import"| db
    work_queue -->|"call"| discovery
    work_queue -->|"call, import"| guardrails
    work_queue -->|"call, import"| policy_engine
    work_queue -->|"call, import"| profiles
```

### Frontend Components

```mermaid
flowchart TB
    empty["No TypeScript nodes found"]
```

### Database ERD

```mermaid
erDiagram
    public__agent_profile_assignments {
        TEXT agent_id
        TIMESTAMPTZ assigned_at
        TEXT assigned_by
        UUID id
        UUID profile_id
    }
    public__agent_profiles {
        TEXT agent_type
        TEXT__ allowed_operations
        TEXT__ blocked_operations
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        UUID id
        INT max_api_calls_per_hour
        INT max_execution_time_seconds
        INT max_file_modifications
        JSONB metadata
        TEXT name
        JSONB network_policy
        INT trust_level
        TIMESTAMPTZ updated_at
    }
    public__agent_sessions {
        TEXT agent_id
        TEXT agent_type
        TEXT__ capabilities
        TEXT current_task
        TIMESTAMPTZ ended_at
        TEXT__ files_modified
        TEXT id
        TIMESTAMPTZ last_heartbeat
        JSONB metadata
        TIMESTAMPTZ started_at
        TEXT status
        TEXT task_description
        INTEGER tasks_completed
    }
    public__approval_queue {
        UUID changeset_id
        TIMESTAMPTZ created_at
        UUID id
        TEXT reason
        TEXT requested_by
        TEXT review_notes
        TIMESTAMPTZ reviewed_at
        TEXT reviewed_by
        TEXT status
    }
    public__audit_log {
        TEXT agent_id
        TEXT agent_type
        TIMESTAMPTZ created_at
        INT duration_ms
        TEXT error_message
        UUID id
        TEXT operation
        JSONB parameters
        JSONB result
        BOOLEAN success
    }
    public__cedar_entities {
        JSONB attributes
        TIMESTAMPTZ created_at
        TEXT entity_id
        TEXT entity_type
        UUID id
        JSONB parents
        TIMESTAMPTZ updated_at
    }
    public__cedar_policies {
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        UUID id
        TEXT name
        TEXT policy_text
        INTEGER priority
        TIMESTAMPTZ updated_at
    }
    public__changesets {
        TEXT agent_id
        TEXT branch_name
        JSONB changed_files
        TEXT commit_sha
        TIMESTAMPTZ created_at
        TEXT description
        UUID id
        TEXT session_id
        TEXT status
        TIMESTAMPTZ updated_at
    }
    public__file_locks {
        TEXT agent_type
        TIMESTAMPTZ expires_at
        TEXT file_path
        TIMESTAMPTZ locked_at
        TEXT locked_by
        JSONB metadata
        TEXT reason
        TEXT session_id
    }
    public__guardrail_violations {
        TEXT agent_id
        TEXT agent_type
        BOOLEAN blocked
        TEXT category
        JSONB context
        TIMESTAMPTZ created_at
        UUID id
        TEXT matched_text
        TEXT operation_text
        TEXT pattern_name
        INT trust_level
    }
    public__handoff_documents {
        TEXT agent_name
        JSONB completed_work
        TIMESTAMPTZ created_at
        JSONB decisions
        UUID id
        JSONB in_progress
        JSONB next_steps
        JSONB relevant_files
        TEXT session_id
        TEXT summary
    }
    public__memory_episodic {
        TEXT agent_id
        TIMESTAMPTZ created_at
        JSONB details
        TEXT event_type
        UUID id
        TEXT__ lessons
        TEXT outcome
        FLOAT relevance_score
        TEXT session_id
        TEXT summary
        TEXT__ tags
    }
    public__memory_procedural {
        TIMESTAMPTZ created_at
        TEXT description
        INT failure_count
        UUID id
        TIMESTAMPTZ last_used
        TEXT__ prerequisites
        TEXT skill_name
        JSONB steps
        INT success_count
        TIMESTAMPTZ updated_at
    }
    public__memory_working {
        TEXT agent_id
        TIMESTAMPTZ created_at
        TIMESTAMPTZ expires_at
        UUID id
        TEXT key
        TEXT session_id
        TIMESTAMPTZ updated_at
        JSONB value
    }
    public__network_access_log {
        TEXT agent_id
        BOOLEAN allowed
        TIMESTAMPTZ created_at
        TEXT domain
        UUID id
        UUID policy_id
        TEXT reason
    }
    public__network_policies {
        TEXT action
        TIMESTAMPTZ created_at
        TEXT description
        TEXT domain_pattern
        BOOLEAN enabled
        UUID id
        INT priority
        UUID profile_id
    }
    public__operation_guardrails {
        TEXT category
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        UUID id
        INT min_trust_level
        TEXT name
        TEXT pattern
        TEXT severity
    }
    public__verification_policies {
        JSONB config
        TIMESTAMPTZ created_at
        TEXT description
        BOOLEAN enabled
        verification_executor executor
        TEXT file_pattern
        UUID id
        TEXT name
        INT priority
        verification_tier tier
    }
    public__verification_results {
        UUID changeset_id
        TIMESTAMPTZ completed_at
        TIMESTAMPTZ created_at
        INT duration_ms
        TEXT error_message
        verification_executor executor
        UUID id
        JSONB result
        TIMESTAMPTZ started_at
        verification_status status
        verification_tier tier
    }
    public__work_queue {
        INTEGER attempt_count
        TIMESTAMPTZ claimed_at
        TEXT claimed_by
        TIMESTAMPTZ completed_at
        TIMESTAMPTZ created_at
        TIMESTAMPTZ deadline
        UUID__ depends_on
        TEXT description
        TEXT error_message
        UUID id
        JSONB input_data
        INTEGER max_attempts
        INTEGER priority
        JSONB result
        TIMESTAMPTZ started_at
        TEXT status
        TEXT task_type
    }
```
