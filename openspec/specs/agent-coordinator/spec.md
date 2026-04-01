# Agent Coordinator System

## Purpose

A multi-agent coordination system that enables local agents (Claude Code CLI, Codex CLI, Aider), cloud agents (Claude Code Web, Codex Cloud), and orchestrated agent swarms (Strands Agents) to collaborate safely on shared codebases.

**Problem Statement**: When multiple AI coding agents work on the same codebase they face conflicts (merge conflicts from concurrent edits), context loss (no memory across sessions), no orchestration (no task tracking), verification gaps (cloud agents can't verify against real environments), and safety risks (autonomous agents executing destructive operations).

## Implementation Status

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1 (MVP)** | File locking, work queue, MCP server, Supabase persistence | **Implemented** |
| **Phase 2** | HTTP API for cloud agents, episodic memory, GitHub-mediated coordination | **Implemented** |
| **Phase 3** | Guardrails engine, agent profiles, network policies, audit trail, Cedar policy engine | **Implemented** |
| Phase 4 | Multi-agent orchestration via Strands SDK, AgentCore integration | Specified |

### Phase 1 Implementation Details

- **Database**: 3 tables (`file_locks`, `work_queue`, `agent_sessions`) + 5 PL/pgSQL functions
- **Bootstrap migration** (`000_bootstrap.sql`): Creates `auth` schema, database roles (`anon`, `authenticated`, `service_role`), `auth.role()` function, and `supabase_realtime` publication for standalone PostgREST deployments
- **MCP server**: 6 tools (`acquire_lock`, `release_lock`, `check_locks`, `get_work`, `complete_work`, `submit_work`) + 2 resources (`locks://current`, `work://pending`)
- **Config**: `rest_prefix` field on `SupabaseConfig` supports both Supabase-hosted (`/rest/v1`) and direct PostgREST (`""`) connections
- **Tests**: 31 unit tests (respx mocks) + 29 integration tests against local Supabase via docker-compose
- **Key pattern**: `acquire_lock` uses `INSERT ON CONFLICT DO NOTHING` then ownership check (prevents PK violation under concurrent access)

## Agent Types

| Type | Platform | Connection | Network Access | Example |
|------|----------|------------|----------------|---------|
| Local | Developer machine | MCP (stdio) | Full | Claude Code CLI, Codex CLI, Aider |
| Cloud-Managed | Vendor infrastructure | HTTP API | Restricted | Claude Code Web, Codex Cloud |
| Orchestrated | AgentCore Runtime | Strands SDK | Configurable | Custom Strands agents |
## Requirements
### Requirement: File Locking

The system SHALL provide exclusive file locking to prevent merge conflicts when multiple agents edit files concurrently. The file locking system SHALL support logical lock key namespaces in addition to repo-relative file paths.

- Locks SHALL be associated with a specific agent ID
- Locks SHALL have a configurable TTL (time-to-live) with auto-expiration
- Lock acquisition SHALL be atomic to prevent race conditions
- The system SHALL support optional reason tracking for locks
- The `file_path` parameter in `acquire_lock`, `release_lock`, and `check_locks` SHALL accept both repo-relative file paths and namespace-prefixed logical keys.
- The following namespace prefixes SHALL be permitted: `api:`, `db:`, `event:`, `flag:`, `env:`, `contract:`, `feature:`.
- Lock key canonicalization rules SHALL be enforced: `api:` keys use uppercase method + single space + normalized path; `db:schema:` keys use lowercase identifiers; `event:` keys use dot-separated lowercase.
- Policy rules SHALL permit the `^(api|db|event|flag|env|contract|feature):.+$` pattern.
- The coordinator SHALL treat lock keys as opaque resource strings without path semantics.

#### Scenario: Agent acquires file lock successfully
- **WHEN** agent requests lock on an unlocked file with `acquire_lock(file_path, reason?, ttl_minutes?)`
- **THEN** system returns `{success: true, action: "acquired", expires_at: timestamp}`
- **AND** other agents attempting to lock the same file SHALL be blocked

#### Scenario: Agent attempts to lock already-locked file
- **WHEN** agent requests lock on a file locked by another agent
- **THEN** system returns `{success: false, action: "blocked", locked_by: agent_id, expires_at: timestamp}`

#### Scenario: Lock expires automatically
- **WHEN** lock TTL expires without renewal
- **THEN** the lock SHALL be automatically released
- **AND** other agents MAY acquire the lock

#### Scenario: Agent releases lock
- **WHEN** agent calls `release_lock(file_path)` on a lock they own
- **THEN** system returns `{success: true, released: true}`
- **AND** the file becomes available for other agents

#### Scenario: Acquire logical lock for API route
- **WHEN** an agent calls `acquire_lock(file_path="api:GET /v1/users")`
- **THEN** the coordinator SHALL acquire the lock using standard lock semantics
- **AND** other agents attempting to lock `api:GET /v1/users` SHALL be blocked

#### Scenario: Acquire pause lock for feature coordination
- **WHEN** an orchestrator calls `acquire_lock(file_path="feature:FEAT-123:pause", reason="contract revision bump")`
- **THEN** the lock SHALL be acquired
- **AND** work package agents checking `check_locks(file_paths=["feature:FEAT-123:pause"])` SHALL see the lock

#### Scenario: Policy permits logical lock key
- **WHEN** an agent attempts to acquire a lock with key `api:POST /v1/users`
- **THEN** the policy engine SHALL permit the operation
- **AND** the lock SHALL be stored in `file_locks.file_path` as-is

#### Scenario: Mixed file and logical locks
- **WHEN** a work package acquires both file locks (`src/api/users.py`) and logical locks (`api:GET /v1/users`)
- **THEN** both lock types SHALL coexist in the `file_locks` table
- **AND** release of one type SHALL NOT affect the other

---

### Requirement: Episodic Memory

The system SHALL store episodic memories (experiences and their outcomes) to enable agents to learn from past sessions.

- Memories SHALL include event_type, summary, details, outcome, and lessons
- Memories SHALL support tagging for categorization
- The system SHALL deduplicate similar recent memories
- Memories SHALL decay in relevance over time

#### Scenario: Agent stores episodic memory
- **WHEN** agent calls `remember(event_type, summary, details?, outcome?, lessons?, tags?)`
- **THEN** system returns `{success: true, memory_id: uuid}`
- **AND** the memory is persisted for future retrieval

#### Scenario: Duplicate memory detection
- **WHEN** agent stores a memory with identical event_type, summary, and agent_id within 1 hour
- **THEN** the system SHALL merge the memories rather than create duplicates

#### Scenario: Agent retrieves relevant memories
- **WHEN** agent calls `recall(task_description, tags?, limit?)`
- **THEN** system returns array of `[{memory_type, content, relevance}]` sorted by relevance

---

### Requirement: Working Memory

The system SHALL maintain active context for current tasks through working memory.

- Working memory SHALL track current task context
- The system SHALL support compression when context exceeds token budget
- Working memory SHALL be session-scoped

#### Scenario: Agent updates working memory
- **WHEN** agent calls working memory update with current context
- **THEN** the context is stored and associated with the current session

#### Scenario: Working memory compression
- **WHEN** working memory exceeds configured token budget
- **THEN** the system SHALL compress older context while preserving recent critical information

---

### Requirement: Procedural Memory

The system SHALL store learned skills and patterns with effectiveness tracking.

- Procedural memories SHALL track success rate
- Skills SHALL be retrievable based on task type

#### Scenario: Procedural skill tracking
- **WHEN** agent completes a task using a specific skill/pattern
- **THEN** the system SHALL update the skill's effectiveness score

---

### Requirement: Work Queue

The system SHALL provide task assignment, tracking, and dependency management through a work queue.

- Tasks SHALL support priority levels
- Task claiming SHALL be atomic (no double-claiming)
- Tasks SHALL support dependencies on other tasks
- Blocked tasks (with unmet dependencies) SHALL NOT be claimable

#### Scenario: Agent claims task from queue
- **WHEN** agent calls `get_work(task_types?)`
- **THEN** system atomically claims the highest-priority pending task
- **AND** returns `{success: true, task_id, task_type, task_description, input_data}`

#### Scenario: No tasks available
- **WHEN** agent calls `get_work()` with no pending tasks matching criteria
- **THEN** system returns `{success: false, reason: "no_tasks_available"}`

#### Scenario: Agent completes task
- **WHEN** agent calls `complete_work(task_id, success, result?, error_message?)`
- **THEN** system returns `{success: true, status: "completed"}`
- **AND** dependent tasks become unblocked if applicable

#### Scenario: Agent submits new task
- **WHEN** agent calls `submit_work(task_type, task_description, input_data?, priority?, depends_on?)`
- **THEN** system returns `{success: true, task_id: uuid}`

#### Scenario: Task with unmet dependencies
- **WHEN** agent attempts to claim a task with pending dependencies
- **THEN** the task SHALL NOT be returned by `get_work()`

---

### Requirement: MCP Server Interface

The system SHALL expose coordination capabilities as native MCP tools for local agents (Claude Code, Codex CLI).

- The server SHALL implement FastMCP protocol
- Connection SHALL be via stdio transport
- All coordination tools SHALL be available as MCP tools

#### Scenario: Local agent connects via MCP
- **WHEN** local agent connects to coordination MCP server
- **THEN** agent discovers available tools: `acquire_lock`, `release_lock`, `check_locks`, `get_work`, `complete_work`, `submit_work`, `write_handoff`, `read_handoff`, `discover_agents`, `register_session`, `heartbeat`
- **AND** (Phase 2) `remember`, `recall` tools when memory is implemented

#### Scenario: MCP resource access
- **WHEN** agent queries MCP resources
- **THEN** agent can access `locks://current`, `work://pending`, `handoffs://recent` resources

### Requirement: HTTP API Interface

The system SHALL provide HTTP API for cloud agents that cannot use MCP protocol.

- Authentication SHALL use API key via `X-API-Key` header
- API keys MAY be bound to specific agent identities for spoofing prevention
- All coordination capabilities SHALL have equivalent HTTP endpoints
- The API SHALL delegate to the service layer (locks, memory, work queue, guardrails, profiles, audit) rather than making direct database calls
- The API SHALL be implemented as a FastAPI application with a factory function `create_coordination_api()`
- Configuration SHALL use `ApiConfig` dataclass loaded from environment variables (`API_HOST`, `API_PORT`, `COORDINATION_API_KEYS`, `COORDINATION_API_KEY_IDENTITIES`)

#### Scenario: Cloud agent acquires lock via HTTP
- **WHEN** cloud agent sends `POST /locks/acquire` with valid API key
- **THEN** system delegates to lock service and returns JSON response

#### Scenario: Invalid API key
- **WHEN** request is made without valid `X-API-Key` header
- **THEN** system returns 401 Unauthorized

#### Scenario: Identity-bound API key prevents spoofing
- **WHEN** API key is bound to agent identity `{"agent_id": "agent-1", "agent_type": "codex"}`
- **AND** request specifies a different `agent_id`
- **THEN** system returns 403 Forbidden

#### Scenario: Health check
- **WHEN** client sends `GET /health`
- **THEN** system returns 200 with `{"status": "ok", "version": "..."}` without requiring authentication

#### Scenario: Read-only endpoints skip auth
- **WHEN** client sends `GET /locks/status/{path}` without API key
- **THEN** system returns lock status (200) without requiring authentication

### Requirement: Verification Gateway

The system SHALL route agent-generated changes to appropriate verification tiers based on configurable policies.

- Policies SHALL match files by glob patterns
- Each tier SHALL have appropriate executor (inline, GitHub Actions, local NTM, E2B, manual)
- Verification results SHALL be stored in database

#### Scenario: Static analysis verification (Tier 0)
- **WHEN** change matches policy for static analysis
- **THEN** system runs linting/type checking inline
- **AND** stores results in verification_results table

#### Scenario: Unit test verification (Tier 1)
- **WHEN** change matches policy for unit tests
- **THEN** system triggers GitHub Actions workflow
- **AND** stores results upon completion

#### Scenario: Integration test verification (Tier 2)
- **WHEN** change matches policy requiring integration tests
- **THEN** system dispatches to Local NTM or E2B sandbox
- **AND** stores results upon completion

#### Scenario: Manual review required (Tier 4)
- **WHEN** change matches policy for security-sensitive files
- **THEN** system adds changeset to approval_queue for human review

#### Scenario: GitHub webhook processing
- **WHEN** GitHub push event received at `/webhook/github`
- **THEN** system identifies affected files and routes to appropriate verification tier

---

### Requirement: Verification Policies

The system SHALL support configurable verification policies that determine routing behavior.

- Policies SHALL specify: name, tier, executor, file patterns, exclude patterns
- Policies SHALL support required environment variables
- Policies SHALL have configurable timeout
- Policies MAY require explicit approval

#### Scenario: Policy creation
- **WHEN** policy is defined with patterns and tier
- **THEN** system uses policy to route matching changesets

#### Scenario: Pattern matching
- **WHEN** changeset contains files matching `patterns` but not `exclude_patterns`
- **THEN** changeset is routed to the policy's specified tier and executor

---

### Requirement: Database Persistence

The system SHALL use Supabase as the coordination backbone with PostgreSQL for persistence.

- All coordination state SHALL be stored in Supabase tables
- Critical operations SHALL use PostgreSQL functions for atomicity
- Row Level Security (RLS) SHALL be used for access control

#### Scenario: Atomic lock acquisition
- **WHEN** lock acquisition is attempted
- **THEN** system uses `INSERT ... ON CONFLICT DO NOTHING RETURNING` pattern

#### Scenario: Atomic task claiming
- **WHEN** task claiming is attempted
- **THEN** system uses `FOR UPDATE SKIP LOCKED` pattern to prevent race conditions

---

### Requirement: Agent Sessions

The system SHALL track agent work sessions for coordination, discovery, and auditing.

- Sessions SHALL be associated with agent_id and agent_type
- Sessions SHALL track start/end times
- Sessions SHALL track capabilities (array of strings) for discovery
- Sessions SHALL track real-time status (active, idle, disconnected)
- Sessions SHALL track last heartbeat timestamp for liveness detection
- Sessions SHALL track current task description
- Changesets SHALL be associated with sessions

#### Scenario: Session tracking
- **WHEN** agent begins work
- **THEN** system creates or updates agent_sessions record

#### Scenario: Session with capabilities and status
- **WHEN** agent registers with capabilities and current task
- **THEN** system stores capabilities array, sets status to active, and records initial heartbeat
- **AND** the agent becomes discoverable via `discover_agents`

### Requirement: Agent Profiles

The system SHALL support configurable agent profiles that define capabilities, trust levels, and operational constraints.

- Profiles SHALL specify allowed operations and tools
- Profiles SHALL define trust level (0-4)
- Profiles SHALL configure resource limits (max files, execution time, API calls)
- Profiles SHALL be assignable per agent_id or agent_type
- Default profiles SHALL exist for each agent type

#### Scenario: Agent with restricted profile
- **WHEN** agent with "reviewer" profile attempts file modification
- **THEN** system checks if "write_file" is in profile's allowed_operations
- **AND** rejects operation if not permitted with `{success: false, error: "operation_not_permitted"}`

#### Scenario: Resource limit enforcement
- **WHEN** agent exceeds profile's max_file_modifications limit
- **THEN** system blocks further modifications
- **AND** returns `{success: false, error: "resource_limit_exceeded", limit: "max_file_modifications"}`

#### Scenario: Trust level verification
- **WHEN** agent attempts operation requiring trust_level >= 3
- **AND** agent's profile has trust_level < 3
- **THEN** system rejects with `{success: false, error: "insufficient_trust_level"}`

#### Profile Trust Levels

| Level | Name | Typical Capabilities |
|-------|------|---------------------|
| 0 | Untrusted | Read-only, no network, all changes require manual review |
| 1 | Limited | Read-write with locks, documentation domains only |
| 2 | Standard | Full file access, approved domains, automated verification |
| 3 | Elevated | Skip Tier 0-1 verification, extended resource limits |
| 4 | Admin | Full access, can modify policies and profiles |

---

### Requirement: Cloud Agent Integration

The system SHALL support cloud-hosted agents (Claude Code Web, Codex Cloud) with restricted network access.

- Cloud agents SHALL connect via HTTP API
- Cloud agents SHALL authenticate with session-derived or task-derived credentials
- The coordination API domain SHALL be compatible with cloud agent network allowlists
- The system SHALL support GitHub-mediated coordination as fallback

#### Scenario: Claude Code Web agent connects
- **WHEN** Claude Code Web session starts with coordination environment configured
- **THEN** agent authenticates via HTTP API using session-derived API key
- **AND** agent identity includes `agent_type: "claude_code_web"` and session metadata

#### Scenario: Codex Cloud agent connects
- **WHEN** Codex Cloud task launches with coordination configuration
- **THEN** agent authenticates via HTTP API using task-specific credentials
- **AND** all operations are logged with Codex task_id for traceability

#### Scenario: Network-restricted fallback to GitHub
- **WHEN** cloud agent cannot reach coordination API
- **THEN** agent MAY use GitHub-mediated coordination
- **AND** uses issue labels for lock signaling (`locked:path/to/file`)
- **AND** uses branch naming conventions for task assignment

#### Scenario: Cloud agent environment configuration
- **WHEN** cloud agent session is configured
- **THEN** environment includes `COORDINATION_API_URL`, `COORDINATION_API_KEY`, `AGENT_TYPE`
- **AND** coordination domain is added to network allowlist

---

### Requirement: Network Access Policies

The system SHALL enforce network egress policies for agents accessing external resources.

- Policies SHALL support domain allowlists and denylists
- Policies SHALL support wildcard patterns (e.g., `*.example.com`)
- Policies SHALL be assignable per agent profile
- All network access attempts SHALL be logged
- Default policy SHALL be deny-all for cloud agents

#### Scenario: Agent requests allowed domain
- **WHEN** agent with network policy requests URL matching allowlist
- **THEN** system permits the request
- **AND** logs access in `network_access_log` with `allowed: true`

#### Scenario: Agent requests blocked domain
- **WHEN** agent requests URL matching denylist or not in allowlist
- **THEN** system blocks the request
- **AND** returns `{success: false, error: "domain_blocked", domain: "example.com"}`
- **AND** logs attempt with `allowed: false, alert: true`

#### Scenario: Default deny for unspecified domains
- **WHEN** agent has no explicit policy for a domain
- **AND** agent profile has `network_default: "deny"`
- **THEN** request is blocked

#### Default Domain Categories

| Category | Domains | Default For |
|----------|---------|-------------|
| Coordination | `coord.yourdomain.com` | All agents |
| Package Managers | `pypi.org`, `npmjs.com`, `rubygems.org` | trust_level >= 1 |
| Documentation | `docs.python.org`, `developer.mozilla.org` | trust_level >= 1 |
| Cloud Providers | `*.amazonaws.com`, `*.azure.com`, `*.googleapis.com` | trust_level >= 2 |
| Source Control | `github.com`, `gitlab.com` | All agents |

---

### Requirement: Destructive Operation Guardrails

The system SHALL prevent autonomous agents from executing destructive operations without explicit approval.

- The system SHALL maintain a registry of destructive operation patterns
- Destructive operations SHALL be blocked by default for cloud agents
- Destructive operations MAY be permitted for elevated trust levels with logging
- All guardrail violations SHALL be logged to audit trail

#### Destructive Operation Categories

| Category | Patterns | Default Behavior |
|----------|----------|------------------|
| Git Force Operations | `git push --force`, `git reset --hard`, `git clean -f` | Block, require approval |
| Branch Deletion | `git branch -D`, `git push origin --delete` | Block for main/master, warn for others |
| Mass File Deletion | `rm -rf`, `find -delete`, unscoped `DELETE FROM` | Block, require approval |
| Credential Modification | Changes to `*.env`, `*credentials*`, `*secrets*` | Block, require manual review |
| Production Deployment | Deploy commands, infrastructure changes | Block, require approval |
| Database Migration | Schema changes, data migrations | Require Tier 3+ verification |

#### Scenario: Cloud agent attempts destructive git operation
- **WHEN** cloud agent submits work containing `git push --force`
- **THEN** system detects destructive pattern before execution
- **AND** returns `{success: false, error: "destructive_operation_blocked", operation: "force_push", approval_required: true}`
- **AND** logs violation to `guardrail_violations`

#### Scenario: Elevated agent executes monitored operation
- **WHEN** agent with trust_level >= 3 executes operation in guardrail registry
- **AND** operation is in profile's `elevated_operations` allowlist
- **THEN** operation proceeds
- **AND** system logs to audit trail with elevated flag
- **AND** sends notification to security channel

#### Scenario: Pre-execution static analysis
- **WHEN** agent submits task completion with code changes
- **THEN** system runs static analysis to detect destructive patterns
- **AND** blocks task completion if destructive patterns found
- **AND** returns specific pattern matches for agent to address

#### Scenario: Credential file modification attempt
- **WHEN** agent attempts to modify file matching `*.env` or `*credentials*`
- **THEN** system blocks modification regardless of trust level
- **AND** adds to approval_queue for human review
- **AND** returns `{success: false, error: "credential_file_protected", requires: "manual_review"}`

---

### Requirement: Agent Orchestration

The system SHALL support multi-agent orchestration patterns for complex workflows.

- The system SHALL integrate with Strands Agents SDK for orchestration
- Orchestrators SHALL be able to spawn and manage worker agents
- The system SHALL support agents-as-tools, swarm, and graph patterns
- Task dependencies SHALL be enforced across orchestrated agents

#### Scenario: Orchestrator spawns worker agent
- **WHEN** orchestrator agent calls `spawn_agent(profile, task)`
- **THEN** system creates new agent session with specified profile
- **AND** assigns task to spawned agent
- **AND** returns `{success: true, agent_id: uuid, task_id: uuid}`

#### Scenario: Swarm coordination
- **WHEN** orchestrator creates swarm with multiple agents
- **THEN** each agent receives coordination context
- **AND** agents can communicate via shared work queue
- **AND** orchestrator receives aggregated results

#### Scenario: Graph-based workflow
- **WHEN** orchestrator defines workflow graph with agent nodes
- **THEN** system enforces execution order via task dependencies
- **AND** conditional edges are evaluated based on task results

---

### Requirement: Audit Trail

The system SHALL maintain comprehensive audit logs for all agent operations.

- All coordination operations SHALL be logged with timestamp, agent_id, operation, and result
- Guardrail violations SHALL be logged with full context
- Network access attempts SHALL be logged
- Audit logs SHALL be immutable (append-only)
- Logs SHALL be retained for configurable period (default 90 days)

#### Scenario: Operation audit logging
- **WHEN** agent performs any coordination operation
- **THEN** system logs `{timestamp, agent_id, agent_type, operation, parameters, result, duration_ms}`

#### Scenario: Guardrail violation logging
- **WHEN** guardrail blocks an operation
- **THEN** system logs `{timestamp, agent_id, operation, pattern_matched, context, blocked: true}`
- **AND** increments agent's violation counter

#### Scenario: Audit log query
- **WHEN** administrator queries audit logs with filters
- **THEN** system returns matching entries without modification
- **AND** supports filtering by agent_id, operation, time_range, result

---

### Requirement: GitHub-Mediated Coordination

The system SHALL support coordination via GitHub for agents with restricted network access.

- File locks SHALL be signaled via issue labels
- Task assignments SHALL use issue assignment and labels
- Branch naming conventions SHALL indicate agent ownership
- The system SHALL sync GitHub state with coordination database

#### Scenario: Lock via GitHub label
- **WHEN** agent cannot reach coordination API
- **AND** agent adds label `locked:src/auth/login.ts` to assigned issue
- **THEN** coordination backend (via webhook) creates corresponding file_lock

#### Scenario: Task assignment via GitHub issue
- **WHEN** GitHub issue is labeled with `agent:claude-web-1` and `status:assigned`
- **THEN** coordination backend creates work_queue entry for agent

#### Scenario: Branch-based ownership
- **WHEN** agent creates branch matching pattern `agent/{agent_id}/{task_id}`
- **THEN** system associates branch with agent session
- **AND** files modified on branch are implicitly locked to that agent

---

### Requirement: Session Continuity

The system SHALL support session continuity through handoff documents that preserve context across agent sessions.

- Handoff documents SHALL include a summary
- Handoff documents MAY include completed work, in-progress items, decisions, next steps, and relevant files
- Handoff documents SHALL be associated with an agent name and session ID
- The system SHALL support retrieving the most recent handoff for a given agent
- Handoff documents SHALL be stored durably in the coordination database

#### Scenario: Agent writes handoff document
- **WHEN** agent calls `write_handoff(summary, completed_work?, in_progress?, decisions?, next_steps?, relevant_files?)`
- **THEN** system returns `{success: true, handoff_id: uuid}`
- **AND** the handoff document is persisted for future sessions

#### Scenario: Agent reads previous handoff
- **WHEN** agent calls `read_handoff(agent_name?, limit?)`
- **THEN** system returns the most recent handoff documents matching the criteria
- **AND** documents are ordered by creation time descending

#### Scenario: No previous handoff exists
- **WHEN** agent calls `read_handoff` and no handoff documents exist for the agent
- **THEN** system returns `{handoffs: []}`

#### Scenario: Handoff write fails due to database error
- **WHEN** agent calls `write_handoff` and the coordination database is unreachable
- **THEN** system returns `{success: false, error: "database_unavailable"}`

#### Scenario: Session start context loading
- **WHEN** a new agent session begins
- **THEN** the system SHALL make the most recent handoff available via `read_handoff`
- **AND** the handoff provides context for resuming prior work

---

### Requirement: Agent Discovery

The system SHALL enable agents to discover other active agents and their capabilities for coordination purposes.

- Agent sessions SHALL track capabilities (array of strings)
- Agent sessions SHALL track real-time status (active, idle, disconnected)
- Agent sessions SHALL track current task description
- The system SHALL support filtering agents by capability and status

#### Scenario: Agent discovers active peers
- **WHEN** agent calls `discover_agents(capability?, status?)`
- **THEN** system returns array of `{agent_id, agent_type, capabilities, status, current_task, last_heartbeat}`
- **AND** only agents matching filter criteria are returned

#### Scenario: Agent registers with capabilities
- **WHEN** agent calls `register_session(capabilities?, current_task?)`
- **THEN** the capabilities and current task are stored in the agent_sessions record
- **AND** the agent becomes discoverable by other agents searching for those capabilities

#### Scenario: No matching agents found
- **WHEN** agent calls `discover_agents` with filters that match no active agents
- **THEN** system returns `{agents: []}`

---

### Requirement: Declarative Team Composition

The system SHALL support declarative team definitions that specify agent roles, capabilities, and coordination rules.

- Team definitions SHALL use a structured YAML format
- Team definitions SHALL specify agent name, role, capabilities, and description
- Team definitions SHALL be loadable and validatable programmatically

#### Scenario: Team configuration loaded
- **WHEN** system reads a `teams.yaml` file
- **THEN** system parses agent definitions with name, role, capabilities, and description
- **AND** validates that all required fields are present

#### Scenario: Invalid team configuration
- **WHEN** team configuration is missing required fields or has invalid values
- **THEN** system returns validation errors with specific field and reason

---

### Requirement: Lifecycle Hooks

The system SHALL support lifecycle hooks for automatic agent registration and cleanup.

- Session start hooks SHALL register the agent and load previous handoffs
- Session end hooks SHALL release all held locks and write a final handoff document
- Hooks SHALL be configurable via Claude Code's hook system

#### Scenario: Agent auto-registers on session start
- **WHEN** a new Claude Code session starts with lifecycle hooks configured
- **THEN** the hook registers the agent session with the coordination system
- **AND** loads the most recent handoff document for context continuity

#### Scenario: Agent auto-cleanup on session end
- **WHEN** a Claude Code session ends (normally or via crash recovery)
- **THEN** the hook releases all file locks held by the agent
- **AND** writes a final handoff document with session summary

#### Scenario: Lifecycle hook script fails
- **WHEN** the hook script encounters an error (network failure, missing dependencies)
- **THEN** the agent session proceeds without coordination registration
- **AND** the error is logged locally for debugging

---

### Requirement: Heartbeat and Dead Agent Detection

The system SHALL detect unresponsive agents and reclaim their resources through heartbeat monitoring.

- Agents SHALL periodically update a heartbeat timestamp
- The system SHALL provide a cleanup function for agents whose heartbeat is stale
- Stale agent cleanup SHALL release held file locks
- Stale agent cleanup SHALL mark agent status as disconnected
- The default stale threshold SHALL be 15 minutes to accommodate long-running operations

#### Scenario: Agent sends heartbeat
- **WHEN** agent calls `heartbeat()`
- **THEN** system updates the agent's `last_heartbeat` timestamp
- **AND** returns `{success: true, session_id: uuid}`

#### Scenario: Dead agent detection and cleanup
- **WHEN** cleanup function runs with configurable stale threshold (default 15 minutes)
- **THEN** agents with `last_heartbeat` older than threshold are marked as disconnected
- **AND** all file locks held by those agents are released
- **AND** system returns the count of cleaned-up agents

#### Scenario: Active agent not affected by cleanup
- **WHEN** cleanup function runs
- **AND** agent's `last_heartbeat` is within the stale threshold
- **THEN** agent's status and locks are not affected

#### Scenario: Heartbeat fails due to database error
- **WHEN** agent calls `heartbeat()` and the coordination database is unreachable
- **THEN** system returns `{success: false, error: "database_unavailable"}`
- **AND** the agent continues operating without updated heartbeat

### Requirement: Port allocation service

The port allocator service SHALL assign conflict-free port blocks to sessions without requiring any database backend. Each block SHALL contain 4 ports at fixed offsets within the block: offset +0 for `db_port`, +1 for `rest_port`, +2 for `realtime_port`, +3 for `api_port`. The configured `range_per_session` determines the spacing between blocks (default: 100), so the first session gets base..base+3, the second gets base+100..base+103, etc.

#### Scenario: Successful port allocation
- **WHEN** an agent calls `allocate_ports` with a `session_id`
- **THEN** the service SHALL return a port assignment containing `db_port`, `rest_port`, `realtime_port`, and `api_port` with no overlap with any active allocation
- **AND** the service SHALL return a `compose_project_name` unique to that session (format: `ac-<first 8 chars of session_id hash>`)
- **AND** the service SHALL return an `env_snippet` string in `export VAR=value` format, one variable per line, containing `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, `AGENT_COORDINATOR_REALTIME_PORT`, `API_PORT`, `COMPOSE_PROJECT_NAME`, and `SUPABASE_URL`

#### Scenario: Duplicate session allocation
- **WHEN** an agent calls `allocate_ports` with a `session_id` that already has an active allocation
- **THEN** the service SHALL return the existing allocation unchanged
- **AND** the lease TTL SHALL be refreshed

#### Scenario: Port range exhaustion
- **WHEN** all available port blocks are allocated and a new allocation is requested
- **THEN** the service SHALL return `{success: false, error: "no_ports_available"}`
- **AND** no existing allocation SHALL be affected

### Requirement: Port allocation lease management

Port allocations SHALL have a configurable TTL and MUST be automatically reclaimed after expiry.

#### Scenario: Lease expires
- **WHEN** a port allocation's TTL elapses without renewal
- **THEN** the port block SHALL be available for new allocations
- **AND** subsequent calls to `allocate_ports` with a new session MAY reuse the expired block's ports

#### Scenario: Explicit release
- **WHEN** an agent calls `release_ports` with a valid `session_id`
- **THEN** the allocation SHALL be removed immediately
- **AND** the ports SHALL be available for reuse

#### Scenario: Release of unknown session
- **WHEN** an agent calls `release_ports` with a `session_id` that has no active allocation
- **THEN** the service SHALL return success (idempotent)

### Requirement: Port allocation configuration

The port allocator SHALL read configuration from environment variables with sensible defaults.

#### Scenario: Default configuration
- **WHEN** no port allocator environment variables are set
- **THEN** the service SHALL use base port 10000, range 100 per session, TTL 120 minutes, and max 20 sessions

#### Scenario: Custom configuration
- **WHEN** `PORT_ALLOC_BASE=20000` and `PORT_ALLOC_RANGE=50` are set
- **THEN** the first allocation SHALL use ports starting at 20000 (db=20000, rest=20001, realtime=20002, api=20003)
- **AND** each subsequent allocation SHALL use ports offset by 50 (second session: db=20050, rest=20051, etc.)

#### Scenario: Invalid configuration values
- **WHEN** `PORT_ALLOC_BASE` is less than 1024 or `PORT_ALLOC_RANGE` is less than 4
- **THEN** the service SHALL raise a configuration error at startup
- **AND** the error message SHALL specify which value is invalid and what the minimum acceptable value is

### Requirement: MCP tool exposure

The port allocator SHALL be accessible via MCP tools for local agents.

#### Scenario: MCP allocate_ports tool
- **WHEN** a local agent invokes the `allocate_ports` MCP tool with `session_id="worktree-1"`
- **THEN** the tool SHALL return a dict with `success: true`, `allocation` (containing `db_port`, `rest_port`, `realtime_port`, `api_port`, `compose_project_name`), and `env_snippet`

#### Scenario: MCP release_ports tool
- **WHEN** a local agent invokes the `release_ports` MCP tool with `session_id="worktree-1"`
- **THEN** the tool SHALL return `{success: true}`

#### Scenario: MCP ports_status tool
- **WHEN** a local agent invokes the `ports_status` MCP tool
- **THEN** the tool SHALL return a list of all active allocations with session IDs, port assignments, and remaining TTL in minutes

#### Scenario: MCP allocate_ports when range exhausted
- **WHEN** a local agent invokes `allocate_ports` and all port blocks are in use
- **THEN** the tool SHALL return `{success: false, error: "no_ports_available"}`

### Requirement: HTTP API exposure

The port allocator SHALL be accessible via HTTP endpoints for cloud agents.

#### Scenario: HTTP allocate endpoint
- **WHEN** a POST request is made to `/ports/allocate` with `{"session_id": "worktree-1"}` and a valid API key
- **THEN** the endpoint SHALL return 200 with port allocation details and env snippet

#### Scenario: HTTP status endpoint
- **WHEN** a GET request is made to `/ports/status`
- **THEN** the endpoint SHALL return a list of all active allocations with session IDs, ports, and remaining TTL

#### Scenario: HTTP release endpoint
- **WHEN** a POST request is made to `/ports/release` with `{"session_id": "worktree-1"}` and a valid API key
- **THEN** the endpoint SHALL return 200 with `{success: true}`

#### Scenario: HTTP allocate without API key
- **WHEN** a POST request is made to `/ports/allocate` without a valid API key
- **THEN** the endpoint SHALL return 401 Unauthorized

#### Scenario: HTTP allocate with missing session_id
- **WHEN** a POST request is made to `/ports/allocate` with an empty or missing `session_id`
- **THEN** the endpoint SHALL return 422 with a validation error

### Requirement: Standalone operation

The port allocator service MUST function without Supabase, database connections, or any other coordination service being configured.

#### Scenario: No database configured
- **WHEN** `SUPABASE_URL` is not set and `DB_BACKEND` is not configured
- **THEN** `allocate_ports` and `release_ports` SHALL still work correctly using in-memory state
- **AND** no database connection SHALL be attempted by the port allocator

#### Scenario: Database configured but port allocator used
- **WHEN** the full agent-coordinator is running with database
- **THEN** the port allocator SHALL still use in-memory state (not database)
- **AND** other services (locks, memory, etc.) SHALL continue using the database as before

### Requirement: Validate-feature port configuration

The validate-feature skill SHALL use environment variables for all port references instead of hardcoded values.

#### Scenario: Docker health check uses env var
- **WHEN** the validate-feature skill checks if the REST API is ready
- **THEN** the health check URL MUST use `${AGENT_COORDINATOR_REST_PORT:-3000}` instead of hardcoded `localhost:3000`

#### Scenario: Docker-compose invocation forwards port vars
- **WHEN** the validate-feature skill starts docker-compose
- **THEN** the invocation MUST explicitly pass `AGENT_COORDINATOR_DB_PORT`, `AGENT_COORDINATOR_REST_PORT`, and `AGENT_COORDINATOR_REALTIME_PORT` environment variables

#### Scenario: Hardcoded port in existing code example
- **WHEN** the validate-feature skill contains inline code examples referencing ports
- **THEN** those examples MUST use the `AGENT_COORDINATOR_REST_PORT` environment variable or `${AGENT_COORDINATOR_REST_PORT:-3000}` pattern

### Requirement: Integration test port configuration

Integration tests SHALL read port configuration from environment variables.

#### Scenario: Custom port via env var
- **WHEN** `AGENT_COORDINATOR_REST_PORT=13000` is set
- **THEN** integration tests MUST connect to `http://localhost:13000` instead of the default `http://localhost:3000`

#### Scenario: Default port when env var not set
- **WHEN** `AGENT_COORDINATOR_REST_PORT` is not set
- **THEN** integration tests SHALL default to `http://localhost:3000`

### Requirement: Skill Integration Usage Patterns

The agent-coordinator documentation SHALL include usage patterns showing how workflow skills integrate with coordinator capabilities across both local CLI and Web/Cloud execution contexts.

#### Scenario: Documentation covers runtime and transport matrix
- **WHEN** a user reads agent-coordinator documentation
- **THEN** there SHALL be a matrix describing:
  - Claude Codex, Codex, and Gemini CLI runtimes using MCP transport
  - Web/Cloud runtimes using HTTP API transport
  - standalone fallback behavior when coordinator is unavailable

#### Scenario: Documentation maps skills to capabilities
- **WHEN** a user reviews skill integration documentation
- **THEN** it SHALL identify which skills consume lock, work queue, handoff, memory, and guardrail capabilities
- **AND** explain capability-gated behavior when only a subset is available

#### Scenario: Documentation covers setup for CLI and Web/Cloud
- **WHEN** a user wants to enable coordination
- **THEN** documentation SHALL reference `/setup-coordinator`
- **AND** include manual configuration guidance for MCP (CLI) and HTTP API (Web/Cloud) paths

### Requirement: Production Container Image

The agent-coordinator MUST provide a production Dockerfile that builds the coordination HTTP API into a container image with multi-stage build, using `uv` for dependency installation and `uvicorn` as the ASGI server.

#### Scenario: Build container image successfully
- **WHEN** `docker build -t coordination-api agent-coordinator/` is run
- **THEN** the image SHALL build successfully with a non-root runtime user
- **AND** the image SHALL be less than 200MB
- **AND** the image SHALL expose port 8081

#### Scenario: Run container with required environment
- **WHEN** the container is started with `POSTGRES_DSN`, `DB_BACKEND=postgres`, and `COORDINATION_API_KEYS` set
- **THEN** the coordination API SHALL be accessible on port 8081
- **AND** the `/health` endpoint SHALL return `{"status": "ok"}`

---

### Requirement: Railway Deployment Configuration

The agent-coordinator MUST include a Railway deployment configuration that specifies the build method, health check endpoint, and required environment variables.

#### Scenario: Deploy two-service project to Railway
- **WHEN** the repository is connected to Railway with two services configured
- **THEN** Service 1 (ParadeDB Postgres) SHALL be accessible on the private network
- **AND** Service 2 (Coordination API) SHALL build from the Dockerfile
- **AND** the health check SHALL poll `GET /health` every 30 seconds
- **AND** the API service SHALL be accessible via Railway-provided HTTPS URL

---

### Requirement: Production Server Settings

The coordination API MUST support production uvicorn configuration via environment variables for worker count, keep-alive timeout, and access logging.

#### Scenario: Configure production workers
- **WHEN** `API_WORKERS=4` is set in the environment
- **THEN** uvicorn SHALL start 4 worker processes
- **AND** the default worker count SHALL be 1

#### Scenario: Configure access logging
- **WHEN** `API_ACCESS_LOG=true` is set in the environment
- **THEN** uvicorn SHALL emit access log entries for each request

---

### Requirement: Health Check with Database Connectivity

The `/health` endpoint MUST include a database connectivity check that reports both API and database status.

#### Scenario: Database is reachable
- **WHEN** a GET request is made to `/health` and the database is responsive
- **THEN** the response SHALL be `{"status": "ok", "db": "connected"}` with HTTP 200

#### Scenario: Database is unreachable
- **WHEN** a GET request is made to `/health` and the database is not responsive within 2 seconds
- **THEN** the response SHALL be `{"status": "degraded", "db": "unreachable"}` with HTTP 503

---

### Requirement: ParadeDB Local Development Environment

The local docker-compose MUST use the ParadeDB Postgres image as a single database service, replacing the previous three-service Supabase stack.

#### Scenario: Start local development database
- **WHEN** `docker compose up -d` is run in the agent-coordinator directory
- **THEN** a single ParadeDB Postgres container SHALL start on port 54322
- **AND** all existing migrations SHALL be applied automatically
- **AND** the `pg_search` and `vector` extensions SHALL be available

#### Scenario: Connect with asyncpg
- **WHEN** `DB_BACKEND=postgres` and `POSTGRES_DSN=postgresql://postgres:postgres@localhost:54322/postgres` are set
- **THEN** the coordination MCP server and HTTP API SHALL connect successfully via asyncpg

---

### Requirement: Cloud Deployment Guide

A deployment guide MUST document Railway two-service setup, ParadeDB Postgres configuration, environment setup, API key provisioning, migration execution, and verification steps.

#### Scenario: Follow deployment guide to production
- **WHEN** a developer follows `docs/cloud-deployment.md` from start to finish
- **THEN** they SHALL have a working Railway deployment with ParadeDB Postgres and coordination API
- **AND** cloud agents SHALL be able to call `/health` and receive a 200 response

#### Scenario: Database migration execution
- **WHEN** the guide's migration section is followed
- **THEN** all migration files SHALL be applied to the Railway Postgres instance
- **AND** at least one automated migration method SHALL be documented (psql script or GitHub Actions)

---

### Requirement: Setup-Coordinator Cloud Support

The setup-coordinator skill MUST include instructions for configuring cloud agent access to the deployed coordination API.

#### Scenario: Configure cloud agent endpoint
- **WHEN** a cloud agent runs the setup-coordinator skill with `--mode web`
- **THEN** it SHALL verify connectivity to the `COORDINATION_API_URL` endpoint
- **AND** it SHALL confirm API key authentication works

---

### Requirement: SSRF Allowlist Documentation

The coordination bridge MUST document how to configure `COORDINATION_ALLOWED_HOSTS` for cloud deployment URLs beyond the default localhost allowlist.

#### Scenario: Cloud URL in SSRF allowlist
- **WHEN** `COORDINATION_ALLOWED_HOSTS` includes the Railway deployment hostname
- **THEN** the coordination bridge SHALL allow HTTP requests to that host
- **AND** requests to unlisted hosts SHALL still be blocked

### Requirement: Task Read API

The coordinator SHALL expose a `get_task(task_id)` tool for reading a task's current state including status, result, and input_data without claiming the task.

- The tool SHALL be available as both an MCP tool and an HTTP endpoint (`GET /api/v1/tasks/{task_id}`).
- The response SHALL include `task_id`, `task_type`, `status`, `input_data`, `result`, `error_message`, `priority`, `created_at`, and `completed_at`.
- Reading a task SHALL NOT change its status or ownership.

#### Scenario: Agent reads completed task result
- **WHEN** an agent calls `get_task(task_id)` for a completed task
- **THEN** the coordinator SHALL return the task with `status="completed"` and the full `result` JSON
- **AND** the task's status SHALL remain unchanged

#### Scenario: Agent reads non-existent task
- **WHEN** an agent calls `get_task(task_id)` with an invalid task_id
- **THEN** the coordinator SHALL return an error indicating the task was not found

#### Scenario: Dependency result read during package execution
- **WHEN** a work package agent needs to read its dependency's output
- **THEN** the agent SHALL call `get_task(dependency_task_id)` to fetch the result
- **AND** parse the `result` JSON to extract relevant outputs

### Requirement: Cancellation Convention

The coordinator SHALL support task cancellation via a convention using existing `complete_work` semantics.

- Cancellation SHALL be represented as `complete_work(success=false)` with `error_code="cancelled_by_orchestrator"` in the result payload.
- A helper function `cancel_task_convention(task_id, reason)` SHALL wrap this pattern.

#### Scenario: Orchestrator cancels dependent package
- **WHEN** a package fails and the orchestrator cancels its dependents
- **THEN** the orchestrator SHALL call `cancel_task_convention(task_id, reason)` for each dependent
- **AND** the cancelled task's result SHALL contain `error_code="cancelled_by_orchestrator"` and the reason

#### Scenario: Cancelled task is queryable
- **WHEN** a task has been cancelled via the convention
- **THEN** `get_task(task_id)` SHALL return `status="failed"` with `error_code="cancelled_by_orchestrator"` in the result

### Requirement: Feature Registry

The coordinator SHALL maintain a feature registry for cross-feature resource claim management and conflict detection.

- Features SHALL register with a unique `feature_id` and a set of resource claims using the lock key namespace.
- The registry SHALL support conflict analysis between registered features.
- The registry SHALL produce parallel feasibility assessments: `FULL`, `PARTIAL`, or `SEQUENTIAL`.

#### Scenario: Register feature with resource claims
- **WHEN** an orchestrator registers a feature with resource claims `["api:GET /v1/users", "db:schema:users", "src/api/users.py"]`
- **THEN** the registry SHALL store the feature and its claims
- **AND** the feature SHALL be visible in cross-feature conflict queries

#### Scenario: Conflict analysis between features
- **WHEN** two registered features share resource claims
- **THEN** the registry SHALL identify the overlapping claims
- **AND** produce a feasibility assessment based on overlap severity

#### Scenario: Feature deregistration after completion
- **WHEN** a feature completes (all packages merged, cleanup done)
- **THEN** the orchestrator SHALL deregister the feature from the registry
- **AND** its resource claims SHALL no longer appear in conflict analysis

### Requirement: Boundary Enforcement Integrity

The system SHALL enforce authorization and profile checks inline on every state-mutating coordination operation.

- Mutation operations SHALL evaluate policy/profile authorization in the same execution path before side effects.
- Denied mutation requests SHALL produce no state changes in coordination tables.
- Guardrail evaluation during mutation flows SHALL use effective trust context resolved from policy/profile lookups.
- Guardrail violations detected in mutation flows SHALL be persisted to `guardrail_violations` and audit trail.
- Policy decisions (native and Cedar) for mutation operations SHALL be logged to audit trail with decision reason and engine metadata.

#### Scenario: Denied lock mutation has no side effects
- **WHEN** an agent without permission attempts lock acquisition
- **THEN** the operation is denied before lock state mutation
- **AND** no new `file_locks` row is created
- **AND** an audit entry records the denial reason

#### Scenario: Denied task mutation has no side effects
- **WHEN** an agent without permission attempts task submission or completion
- **THEN** the operation is denied before queue mutation
- **AND** no new or updated `work_queue` row is committed
- **AND** an audit entry records the denial reason

#### Scenario: Trust-aware guardrail execution
- **WHEN** guardrails run during claim/submit/complete paths
- **THEN** guardrails evaluate with resolved trust context for the requesting agent
- **AND** fallback default trust is used only if profile/policy resolution is unavailable

#### Scenario: Guardrail violation persistence
- **WHEN** guardrails detect a mutation-flow violation
- **THEN** a `guardrail_violations` record is written
- **AND** an immutable audit entry includes matched pattern context and block/allow outcome

#### Scenario: Cedar decision auditability
- **WHEN** mutation authorization is evaluated with `POLICY_ENGINE=cedar`
- **THEN** the allow/deny decision is logged to audit trail
- **AND** the audit record includes Cedar as decision engine metadata

---

### Requirement: Direct PostgreSQL Identifier Safety

The direct PostgreSQL backend SHALL reject unsafe dynamic identifier inputs during query construction.

- Dynamic identifiers (table names, selected columns, order columns) SHALL be constrained to trusted/safe forms.
- Unsafe identifier inputs SHALL be rejected before SQL execution.

#### Scenario: Unsafe identifier rejected before execution
- **WHEN** identifier-like input contains unsafe SQL tokens or delimiters
- **THEN** the backend returns a validation error
- **AND** no SQL statement is executed

#### Scenario: Safe identifier accepted
- **WHEN** identifier input matches the configured safe identifier strategy (allowlist or validated quoting path)
- **THEN** query construction proceeds
- **AND** the resulting statement executes without identifier-validation errors

---

### Requirement: Behavioral Assurance and Formal Verification

The system SHALL maintain an assurance program that verifies safety-critical coordination behavior through automated tests and formal modeling.

- The system SHALL continuously verify lock/work queue invariants via automated tests.
- The system SHALL verify boundary enforcement behavior (denied mutations cause no side effects).
- The system SHALL verify audit completeness for mutation operations.
- The system SHALL verify default-decision equivalence between native and Cedar policy engines.
- The system SHALL include a formal model of lock/task lifecycle invariants.
- Formal model checks SHALL be runnable in CI.

#### Scenario: Lock exclusivity invariant under concurrency
- **WHEN** concurrent lock acquisition attempts target the same file
- **THEN** verification confirms at most one live lock exists for that file

#### Scenario: Task claim uniqueness invariant
- **WHEN** concurrent claim attempts run against a queue with one eligible task
- **THEN** verification confirms only one claimant receives that task

#### Scenario: Completion ownership invariant
- **WHEN** a non-claiming agent attempts to complete a claimed task
- **THEN** verification confirms completion is rejected
- **AND** task ownership is unchanged

#### Scenario: Audit completeness for mutations
- **WHEN** mutation operations execute (success or denial)
- **THEN** verification confirms corresponding audit entries exist with required decision fields

#### Scenario: Native/Cedar equivalence regression check
- **WHEN** differential verification runs baseline profiles and operation/resource matrix
- **THEN** native and Cedar engines produce identical allow/deny outcomes for baseline policy set

#### Scenario: Formal model safety check
- **WHEN** TLC runs on the coordination TLA+ model
- **THEN** lock/task safety invariants hold for bounded state exploration

#### Scenario: Formal invariant regression is surfaced
- **WHEN** a model change violates one of the declared safety invariants
- **THEN** TLC reports the violated invariant
- **AND** CI marks the formal-check step as failed (or warning while non-blocking mode is configured)

### Requirement: Delegated Agent Identity

The system SHALL support binding agent identity to the human user or parent agent that authorized the session, enabling permission inheritance and full audit attribution.

- Agent sessions SHALL accept an optional `delegated_from` field identifying the authorizing principal
- When `delegated_from` is set, Cedar policies SHALL have access to the delegating principal's attributes for authorization decisions
- The audit trail SHALL record both `agent_id` and `delegated_from` for every operation
- MCP tools SHALL accept an optional `on_behalf_of` parameter, validated against session credentials
- HTTP API requests SHALL accept `delegated_from` in the request body, validated against the API key's ownership scope
- If `delegated_from` is not provided, the agent SHALL be treated as self-authorized (backward-compatible default)

#### Scenario: Agent session with delegated identity
- **WHEN** agent registers session with `delegated_from: "user:jane@example.com"`
- **THEN** system stores the delegation binding in `agent_sessions`
- **AND** Cedar entity for the agent includes `delegated_by: "user:jane@example.com"` attribute
- **AND** all subsequent operations by this agent are attributed to both agent and delegating user

#### Scenario: Cedar policy restricts based on delegating user
- **WHEN** Cedar policy contains `when { principal.delegated_by == "user:intern@example.com" && principal.trust_level > 2 }`
- **AND** agent with `delegated_from: "user:intern@example.com"` attempts trust-level-3 operation
- **THEN** system denies the operation because the delegating user's policy restricts elevation

#### Scenario: Agent without delegated identity (backward compatible)
- **WHEN** agent registers session without `delegated_from`
- **THEN** system treats the agent as self-authorized
- **AND** Cedar entity has `delegated_by: ""` (empty string)
- **AND** existing policies that do not reference `delegated_by` continue to function unchanged

#### Scenario: Delegated identity in audit trail
- **WHEN** agent with `delegated_from: "user:jane@example.com"` acquires a file lock
- **THEN** audit log entry contains both `agent_id` and `delegated_from` fields
- **AND** audit queries support filtering by `delegated_from`

---

### Requirement: Human-in-the-Loop Approval Gates

The system SHALL support blocking approval gates that suspend high-risk operations until a human reviewer approves or denies them.

- Guardrail rules SHALL support `severity: approval_required` in addition to `block` and `warn`
- When an operation triggers an `approval_required` guardrail, the operation SHALL be suspended and an approval request inserted into `approval_queue`
- Approval requests SHALL include: operation details, agent identity, risk context, and requesting reason
- Reviewers SHALL be able to approve or deny requests via HTTP API
- Approved operations SHALL resume execution; denied operations SHALL return an error to the agent
- Unanswered requests SHALL auto-deny after a configurable timeout (default: 1 hour)
- All approval decisions SHALL be logged immutably in the audit trail

#### Scenario: Destructive operation triggers approval gate
- **WHEN** agent submits work containing `git push --force` and guardrail rule has `severity: approval_required`
- **THEN** system suspends the operation
- **AND** inserts approval request into `approval_queue` with status `pending`
- **AND** returns `{success: false, status: "approval_pending", request_id: uuid, message: "Human approval required"}`

#### Scenario: Reviewer approves pending operation
- **WHEN** reviewer calls `POST /approvals/{request_id}/decide` with `{decision: "approved", reason: "Verified safe"}`
- **THEN** system updates approval request status to `approved`
- **AND** the agent can re-attempt the operation, which now proceeds
- **AND** audit trail records the approval with reviewer identity and reason

#### Scenario: Reviewer denies pending operation
- **WHEN** reviewer calls `POST /approvals/{request_id}/decide` with `{decision: "denied", reason: "Too risky"}`
- **THEN** system updates approval request status to `denied`
- **AND** agent receives `{success: false, error: "approval_denied", reason: "Too risky"}` on next check
- **AND** audit trail records the denial

#### Scenario: Approval request auto-expires
- **WHEN** approval request remains in `pending` status beyond the configured timeout
- **THEN** system automatically sets status to `expired`
- **AND** agent receives `{success: false, error: "approval_expired"}`
- **AND** audit trail records the expiration

#### Scenario: Agent checks approval status
- **WHEN** agent calls `check_approval(request_id)`
- **THEN** system returns `{request_id, status: "pending"|"approved"|"denied"|"expired", decided_by?, decided_at?, reason?}`

---

### Requirement: Contextual Risk Scoring

The system SHALL compute dynamic risk scores for operations based on contextual factors, enabling graduated authorization responses instead of binary allow/deny decisions.

- Risk scores SHALL be computed on a 0.0 to 1.0 scale
- Risk factors SHALL include: agent trust level, operation severity, resource sensitivity, recent violation count, session age, and time-of-day
- Risk scores SHALL be passed to Cedar as `context.risk_score` for policy-based threshold evaluation
- Risk thresholds SHALL be configurable: low (auto-allow), medium (log + allow), high (require approval)
- Recent violation counts SHALL be tracked per-agent in a configurable sliding window (default: 1 hour)
- The risk scorer SHALL be disabled by default (`RISK_SCORING_ENABLED=false`), returning 0.0 as pass-through

#### Scenario: Low-risk operation auto-allowed
- **WHEN** agent with trust_level 3, zero recent violations, performs a read operation
- **THEN** risk scorer computes score below low threshold (e.g., 0.1)
- **AND** operation proceeds without additional checks

#### Scenario: Medium-risk operation logged
- **WHEN** agent with trust_level 2, two recent violations, performs a write operation on a non-sensitive file
- **THEN** risk scorer computes score in medium range (e.g., 0.4)
- **AND** operation proceeds
- **AND** audit trail records the elevated risk score

#### Scenario: High-risk operation requires approval
- **WHEN** agent with trust_level 2, five recent violations, performs an admin operation
- **THEN** risk scorer computes score above high threshold (e.g., 0.8)
- **AND** system routes to approval gate (if approval gates enabled)
- **OR** blocks the operation (if approval gates disabled)

#### Scenario: Risk scoring disabled (default)
- **WHEN** `RISK_SCORING_ENABLED=false`
- **THEN** risk scorer returns 0.0 for all operations
- **AND** authorization proceeds based on trust levels and guardrails only (existing behavior)

#### Scenario: Cedar policy uses risk score
- **WHEN** Cedar policy contains `when { context.risk_score > 0.7 }` in a forbid rule
- **AND** operation has computed risk score of 0.8
- **THEN** Cedar evaluation denies the operation based on the risk threshold

---

### Requirement: Real-Time Policy Synchronization

The system SHALL support push-based policy cache invalidation to reduce policy propagation latency from TTL-based polling to sub-second updates.

- The system SHALL use PostgreSQL `LISTEN/NOTIFY` via an after-trigger on the `cedar_policies` table to detect INSERT, UPDATE, and DELETE events
- An asyncpg listener SHALL call `CedarPolicyEngine.invalidate_cache()` on receiving a `policy_changed` notification
- If the LISTEN connection is unavailable or drops, the system SHALL fall back to TTL-based polling (existing behavior)
- The `PolicySyncService` SHALL implement a pluggable interface (`start`, `stop`, `on_policy_change`) to allow future replacement with OPAL
- Real-time sync SHALL be opt-in via `POLICY_SYNC_ENABLED` environment variable (default: false)

#### Scenario: Policy updated with LISTEN/NOTIFY enabled
- **WHEN** operator updates a row in `cedar_policies` table
- **AND** `POLICY_SYNC_ENABLED=true`
- **THEN** PostgreSQL trigger sends `NOTIFY policy_changed` with the policy name as payload
- **AND** asyncpg listener in `PolicySyncService` receives the notification
- **AND** `CedarPolicyEngine.invalidate_cache()` is called within 1 second
- **AND** next authorization check loads the updated policy

#### Scenario: Policy updated with LISTEN/NOTIFY disabled
- **WHEN** operator updates a row in `cedar_policies` table
- **AND** `POLICY_SYNC_ENABLED=false`
- **THEN** policy cache expires after TTL (default 300 seconds)
- **AND** next authorization check after TTL expiry loads the updated policy

#### Scenario: LISTEN connection drops
- **WHEN** asyncpg LISTEN connection is lost
- **THEN** `PolicySyncService` attempts reconnection with exponential backoff
- **AND** falls back to TTL-based polling until connection is restored
- **AND** logs connection state changes for operational visibility

#### Scenario: OPAL replacement path
- **WHEN** system scales to multiple coordination API instances
- **THEN** operator can implement `OpalPolicySyncService` with the same interface
- **AND** swap it in via configuration without changing policy engine or Cedar policies

---

### Requirement: Policy Version History

The system SHALL maintain a complete version history of all Cedar policy changes, enabling audit, rollback, and change tracking.

- Every INSERT, UPDATE, and DELETE on `cedar_policies` SHALL be captured in `cedar_policies_history`
- History records SHALL include: policy_id, version number, policy_text, changed_by, changed_at, change_type
- Policy version numbers SHALL auto-increment on each update
- Operators SHALL be able to rollback a policy to a previous version
- Policy mutations SHALL be logged in the audit trail with before/after content

#### Scenario: Policy update creates history entry
- **WHEN** operator updates the `write-operations` policy in `cedar_policies`
- **THEN** a trigger copies the previous version to `cedar_policies_history`
- **AND** the `policy_version` column on `cedar_policies` increments

#### Scenario: Policy rollback to previous version
- **WHEN** operator calls `POST /policies/write-operations/rollback?version=3`
- **THEN** system retrieves version 3 from `cedar_policies_history`
- **AND** updates `cedar_policies` with the historical policy_text
- **AND** creates a new history entry recording the rollback
- **AND** logs the rollback in audit trail

#### Scenario: Policy deletion preserves history
- **WHEN** operator deletes a policy from `cedar_policies`
- **THEN** a trigger copies the final version to `cedar_policies_history` with `change_type: "delete"`
- **AND** full history remains queryable

#### Scenario: List policy versions
- **WHEN** agent or operator calls `list_policy_versions(policy_name, limit?)`
- **THEN** system returns array of `{version, policy_text, changed_by, changed_at, change_type}` ordered by version descending

---

### Requirement: Session-Scoped Permission Grants

The system SHALL support per-session permission grants that expire when the session ends, enabling a zero-standing-permissions model where agents request and justify access rather than inheriting permanent trust levels.

- Agents SHALL be able to request elevated permissions for the current session via `request_permission(operation, justification)`
- Permission grants SHALL be scoped to the requesting agent's session and expire when the session ends
- Grant requests MAY require human approval (routed through approval gates) based on the operation's risk level
- Cedar policies SHALL support `session_grants` as a principal attribute for conditional evaluation
- The system SHALL log all permission grants and their justifications in the audit trail
- Default behavior (no session grants) SHALL match existing trust-level-based authorization

#### Scenario: Agent requests session-scoped write permission
- **WHEN** agent with trust_level 1 calls `request_permission("acquire_lock", "Need to fix critical bug in auth.py")`
- **AND** policy allows self-service grants for `acquire_lock` at trust_level 1
- **THEN** system adds `acquire_lock` to agent's `session_grants`
- **AND** agent can perform `acquire_lock` for the remainder of the session
- **AND** grant is logged with justification in audit trail

#### Scenario: Permission grant requires approval
- **WHEN** agent requests `force_push` permission
- **AND** policy requires approval for `force_push` grants
- **THEN** system routes to approval gate
- **AND** agent must wait for human approval before grant is active

#### Scenario: Session ends and grants expire
- **WHEN** agent session terminates (normal exit or stale heartbeat cleanup)
- **THEN** all session-scoped permission grants are automatically revoked
- **AND** audit trail records grant expiration

#### Scenario: Cedar policy evaluates session grants
- **WHEN** Cedar policy contains `when { principal.session_grants.contains(action) }`
- **AND** agent has been granted the requested operation for this session
- **THEN** Cedar evaluation permits the operation

### Requirement: CI Integration Tests Against Live Database

CI SHALL run integration tests against a live ParadeDB instance on every push to `main` and on pull requests. Integration tests SHALL validate the `DirectPostgresClient` (asyncpg) backend — the production database path.

- The CI pipeline SHALL include a `test-integration` job with a ParadeDB service container
- Migrations SHALL be auto-applied via `/docker-entrypoint-initdb.d` volume mount
- Integration tests SHALL use `DB_BACKEND=postgres` and `POSTGRES_DSN` environment variables
- Integration tests SHALL use transaction rollback for test isolation

#### Scenario: Integration tests run in CI on pull request

- **WHEN** a pull request is opened or pushed to
- **THEN** the `test-integration` CI job starts a ParadeDB service container
- **AND** runs `pytest -m "integration or e2e"` with `POSTGRES_DSN` set
- **AND** the job passes if all tests pass

#### Scenario: Test isolation via transaction rollback

- **WHEN** two DirectPostgresClient integration tests run sequentially
- **AND** the first test inserts data within a transaction
- **THEN** the transaction is rolled back after the first test
- **AND** the second test sees a clean database state

---

### Requirement: DirectPostgresClient Integration Test Coverage

Integration tests SHALL cover lock lifecycle, work queue lifecycle, and memory operations via `DirectPostgresClient` to validate JSONB serialization, UUID coercion, and array handling against real PostgreSQL.

- Lock integration tests SHALL cover acquire, release, conflict detection, TTL expiry, and concurrent acquire
- Work queue integration tests SHALL cover submit, claim, complete, and dependency tracking
- Memory integration tests SHALL cover store, recall, tag filtering, and deduplication

#### Scenario: Lock lifecycle via DirectPostgresClient

- **GIVEN** a running ParadeDB instance with migrations applied
- **WHEN** a lock is acquired, checked, and released via DirectPostgresClient
- **THEN** each operation succeeds with correct state transitions
- **AND** JSONB return values are correctly deserialized

#### Scenario: Work queue lifecycle via DirectPostgresClient

- **GIVEN** a running ParadeDB instance with migrations applied
- **WHEN** a task is submitted, claimed, and completed via DirectPostgresClient
- **THEN** each operation succeeds with correct state transitions

---

### Requirement: E2E HTTP API Test Coverage

E2E tests SHALL exercise the HTTP coordination API against a live database using FastAPI `TestClient`, covering health, locks, guardrails, memory, handoffs, work queue, and audit endpoints.

- E2E tests in CI SHALL use `DirectPostgresClient` via `DB_BACKEND=postgres`
- E2E tests SHALL validate request/response contracts for all major endpoints

#### Scenario: Memory store and recall via HTTP API

- **GIVEN** a running coordination API with live database
- **WHEN** a memory is stored via `POST /memory/store` and then recalled via `POST /memory/query`
- **THEN** the recall returns the stored memory with correct content and tags

#### Scenario: Handoff write and read via HTTP API

- **GIVEN** a running coordination API with live database
- **WHEN** a handoff document is written via `POST /handoffs/write` with list fields
- **THEN** the lists are correctly serialized as JSONB
- **AND** reading the handoff returns all fields intact

---

### Requirement: Database Readiness Verification

A readiness script SHALL verify database connectivity and migration completion before test execution, with a configurable timeout.

- The script SHALL verify PostgreSQL is accepting connections via `pg_isready`
- The script SHALL verify expected tables exist by querying `information_schema` or `pg_catalog`
- The script SHALL timeout after 60 seconds with a clear error message

#### Scenario: Readiness check passes

- **GIVEN** ParadeDB is running with all migrations applied
- **WHEN** the readiness script runs
- **THEN** it exits with code 0 within 10 seconds

#### Scenario: Readiness check fails on timeout

- **GIVEN** ParadeDB is not yet ready
- **WHEN** the readiness script polls for 60 seconds without success
- **THEN** it exits with a non-zero code and prints a diagnostic error message

### Requirement: Feature Registry MCP Tools

The coordination MCP server SHALL expose `register_feature`, `deregister_feature`, `get_feature`, `list_active_features`, and `analyze_feature_conflicts` as MCP tools that delegate to `FeatureRegistryService`.

#### Scenario: Register feature via MCP
- WHEN an agent calls `register_feature` with `feature_id`, `resource_claims`, and `title`
- THEN the tool SHALL delegate to `FeatureRegistryService.register()` and return a dict with `success`, `feature_id`, and `action` fields

#### Scenario: Register feature with missing feature_id
- WHEN an agent calls `register_feature` without `feature_id`
- THEN the tool SHALL return an error indicating the required parameter is missing

### Requirement: Feature Registry HTTP Endpoints

The coordination HTTP API SHALL expose feature registry operations as REST endpoints with auth middleware.

#### Scenario: List active features via HTTP
- WHEN a client sends `GET /features/active` with a valid API key
- THEN the API SHALL return a JSON array of active features ordered by merge priority

#### Scenario: Unauthorized feature access
- WHEN a client sends `GET /features/active` without an API key
- THEN the API SHALL return HTTP 401

### Requirement: Merge Queue MCP Tools

The coordination MCP server SHALL expose `enqueue_merge`, `get_merge_queue`, `get_next_merge`, `run_pre_merge_checks`, `mark_merged`, and `remove_from_merge_queue` as MCP tools that delegate to `MergeQueueService`.

#### Scenario: Enqueue feature for merge
- WHEN an agent calls `enqueue_merge` with `feature_id`
- THEN the tool SHALL delegate to `MergeQueueService.enqueue()` and return the queue entry with `feature_id`, `merge_status`, and `merge_priority`

#### Scenario: Enqueue non-existent feature
- WHEN an agent calls `enqueue_merge` with a `feature_id` that is not registered
- THEN the tool SHALL return `success: false` with a descriptive reason

### Requirement: Merge Queue HTTP Endpoints

The coordination HTTP API SHALL expose merge queue operations as REST endpoints.

#### Scenario: Get merge queue via HTTP
- WHEN a client sends `GET /merge-queue` with a valid API key
- THEN the API SHALL return a JSON array of queued features in priority order

#### Scenario: Run pre-merge checks via HTTP
- WHEN a client sends `POST /merge-queue/check/{feature_id}` with a valid API key
- THEN the API SHALL return a JSON object with `passed`, `checks`, `issues`, and `conflicts` fields

### Requirement: CLI Entry Point

The coordinator SHALL provide a `coordination-cli` command-line entry point with subcommand groups for all coordinator capabilities.

#### Scenario: CLI feature list with JSON output
- WHEN a user runs `coordination-cli --json feature list`
- THEN the CLI SHALL print a JSON array of active features to stdout and exit 0

#### Scenario: CLI help text
- WHEN a user runs `coordination-cli --help`
- THEN the CLI SHALL print usage information including all subcommand groups

#### Scenario: CLI merge-queue enqueue
- WHEN a user runs `coordination-cli merge-queue enqueue --feature-id X`
- THEN the CLI SHALL delegate to `MergeQueueService.enqueue()` and print the result

#### Scenario: CLI with database unavailable
- WHEN a user runs any CLI command and the database is unreachable
- THEN the CLI SHALL print an error message to stderr and exit with non-zero code

### Requirement: CLI Coverage

The CLI SHALL expose subcommands for all existing coordinator capabilities: `lock`, `work`, `handoff`, `memory`, `feature`, `merge-queue`, `health`, `guardrails`, `policy`, `audit`, `ports`, `approval`.

#### Scenario: CLI lock acquire
- WHEN a user runs `coordination-cli lock acquire --file-path X --agent-id Y --agent-type Z`
- THEN the CLI SHALL delegate to `LockService.acquire()` and print the result

#### Scenario: CLI unknown subcommand
- WHEN a user runs `coordination-cli unknown-cmd`
- THEN the CLI SHALL print an error and available subcommands to stderr

### Requirement: Bridge Endpoint Probes

The coordination bridge SHALL probe only canonical endpoint paths, removing stale variants.

#### Scenario: Handoff capability detection
- WHEN `detect_coordination()` probes for `CAN_HANDOFF`
- THEN it SHALL probe `POST /handoffs/write` only (not `/handoff/write` or `/handoffs/latest`)

#### Scenario: All capability probes use correct methods
- WHEN `detect_coordination()` probes any capability
- THEN the probe SHALL use the HTTP method matching the actual endpoint (POST for write operations, GET for read operations)

### Requirement: Bridge Capability Flags

The coordination bridge SHALL support `CAN_FEATURE_REGISTRY` and `CAN_MERGE_QUEUE` capability flags in addition to existing flags.

#### Scenario: Feature registry capability detection
- WHEN `detect_coordination()` runs
- THEN it SHALL set `CAN_FEATURE_REGISTRY` based on probing `GET /features/active`

#### Scenario: Merge queue capability detection
- WHEN `detect_coordination()` runs
- THEN it SHALL set `CAN_MERGE_QUEUE` based on probing `GET /merge-queue`

### Requirement: Event Bus Service

The coordinator SHALL provide a generalized event bus built on PostgreSQL LISTEN/NOTIFY that extends the existing `policy_sync.py` pattern to multiple channels.

- The event bus SHALL listen on the following PostgreSQL NOTIFY channels:
  - `coordinator_approval` — approval request submitted, decided, or expired (trigger on `approval_queue`)
  - `coordinator_task` — task claimed, completed, or failed (trigger on `work_queue`)
  - `coordinator_agent` — agent registered, stale, or disconnected (trigger on `agent_discovery`)
  - `coordinator_status` — phase transitions, escalations, completion signals (emitted by `POST /status/report` and watchdog via direct `pg_notify`)
- The event bus SHALL support registering async callbacks per channel via `on_event(channel, callback)`.
- The event bus SHALL reconnect with exponential backoff (max 5 retries, base 1s) on connection loss, matching the `policy_sync.py` pattern.
- The event bus SHALL use a single dedicated asyncpg connection (not from the pool) for LISTEN.
- Database triggers SHALL emit NOTIFY on INSERT or UPDATE to `approval_queue`, `work_queue`, and `agent_discovery` tables.
- NOTIFY payloads SHALL be JSON objects conforming to the CoordinatorEvent schema.
- If a NOTIFY payload exceeds 7KB (leaving 1KB margin below PostgreSQL's 8KB limit), the `context` field SHALL be truncated and a `"[context truncated]"` marker added.
- The event bus MUST NOT emit NOTIFY events in response to changes made by the coordinator itself (e.g., watchdog-initiated cleanups). Triggers SHALL check `current_setting('app.coordinator_internal')` and skip NOTIFY when set to `'true'`.

#### Scenario: Approval request triggers notification event

WHEN an approval request is inserted into `approval_queue`
THEN a `coordinator_approval` NOTIFY is emitted with payload `{"event_type": "approval.submitted", "entity_id": "<request_id>", "agent_id": "<agent_id>", "urgency": "high", "summary": "Approval needed: <operation>", "context": {"operation": "<operation>", "resource": "<resource>"}}`
AND the event bus dispatches to all registered callbacks for `coordinator_approval`.

#### Scenario: Task completion triggers notification event

WHEN a work queue task status changes to `completed` or `failed`
THEN a `coordinator_task` NOTIFY is emitted with payload `{"event_type": "task.<new_status>", "entity_id": "<task_id>", "agent_id": "<agent_id>", "urgency": "medium"}`
AND the event bus dispatches to all registered callbacks for `coordinator_task`.

#### Scenario: Event bus reconnects on connection loss

WHEN the LISTEN connection detects `ConnectionDoesNotExistError` or receives no data for 60 seconds
THEN the event bus SHALL retry with backoff delays of 1s, 2s, 4s, 8s, 16s
AND if all 5 retries fail, the event bus SHALL log a CRITICAL error, set an internal `failed` flag, and cease listening.

#### Scenario: Event bus exhausts retries

WHEN the event bus has failed all reconnection attempts
THEN the watchdog (if running) SHALL detect the failed flag within one check interval
AND emit a `high` urgency notification via direct `pg_notify` call (bypassing the failed listener)
AND the event bus SHALL NOT attempt further reconnections until manually restarted or the API server restarts.

### Requirement: Notification Service

The coordinator SHALL provide a pluggable notification service that subscribes to the event bus and dispatches notifications through configured channels.

- The notifier SHALL implement a `NotificationChannel` protocol with methods: `send(event) -> bool`, `test() -> bool`, `supports_reply() -> bool`.
- The notifier SHALL maintain a registry of enabled channels, configured via the `NOTIFICATION_CHANNELS` environment variable (comma-separated list, e.g., `gmail,telegram,webhook`).
- The notifier SHALL dispatch events to all enabled channels in parallel via `asyncio.gather()`.
- The notifier SHALL classify events by urgency: `high` (immediate), `medium` (within 1 minute), `low` (batched into digest).
- High-urgency events: approval submitted, phase escalated, agent stale, `needs_human=true` status reports, event bus connection failure.
- Medium-urgency events: task completed, review completed, PR created, loop done.
- Low-urgency events: phase transitions, agent registered, lock acquired.
- The notifier SHALL support an event type filter per channel via `NOTIFICATION_EVENT_FILTER_{CHANNEL}` env var (comma-separated event types, e.g., `approval.submitted,agent.stale`). Events not matching the filter SHALL be silently dropped for that channel.
- If `NOTIFICATION_CHANNELS` is empty or unset, the notifier SHALL be disabled (no-op).
- If a channel's `send()` raises an exception, the notifier SHALL catch the exception, log a WARNING, and continue dispatching to remaining channels. The notifier SHALL return a dict of per-channel success/failure results.
- The notifier SHALL retry failed channel sends with exponential backoff (base 2s, max 60s, up to 3 attempts) before marking the send as failed.
- Low-urgency events SHALL be collected into a digest batch and sent every `NOTIFICATION_DIGEST_INTERVAL_SECONDS` seconds (default: 600, i.e., 10 minutes). The digest SHALL contain: event count, per-type summary, and the 5 most recent event summaries. Max batch size: 100 events (oldest dropped if exceeded).
- The notifier MUST NOT dispatch notifications for events originating from the notifier itself or the watchdog (preventing notification loops). Events with `context.source == "notifier"` or `context.source == "watchdog"` SHALL be skipped.

**Testing Strategy:**

- All channel implementations SHALL have a corresponding `Fake` test double implementing the `NotificationChannel` protocol (e.g., `GmailChannelFake`) that buffers sent events in a list for assertion.
- `NotifierService` unit tests SHALL use fake channels exclusively (no real SMTP/IMAP).
- Integration tests requiring real SMTP/IMAP SHALL be marked `@pytest.mark.integration` and skipped in CI by default.
- Time-dependent tests SHALL inject a `time_fn` parameter (default `time.monotonic`) and use `freezegun` or `time-machine` to advance time deterministically.

#### Scenario: Approval request sends immediate notification

WHEN an `approval.submitted` event arrives at the notifier
AND the event urgency is `high`
THEN the notifier SHALL dispatch to all enabled channels immediately (within 1 second)
AND each channel's `send()` receives a `CoordinatorEvent` conforming to the schema defined in Definitions.

#### Scenario: No channels configured

WHEN `NOTIFICATION_CHANNELS` is empty
THEN the notifier SHALL not subscribe to the event bus
AND no notifications are sent.

#### Scenario: One channel fails during dispatch

WHEN the notifier dispatches an event to 3 channels
AND the second channel's `send()` raises `SMTPConnectionError`
THEN the notifier SHALL log a WARNING for the failed channel
AND the first and third channels SHALL still receive the event
AND the return value SHALL be `{"gmail": False, "telegram": True, "webhook": True}`.

#### Scenario: Low-urgency events batched into digest

WHEN 5 low-urgency events arrive within a 10-minute window
THEN the notifier SHALL NOT send them immediately
AND after 10 minutes (or `NOTIFICATION_DIGEST_INTERVAL_SECONDS`), the notifier SHALL send a single digest email containing all 5 event summaries.

### Requirement: Gmail Notification Channel

The coordinator SHALL provide a Gmail-compatible email channel with SMTP outbound and IMAP IDLE inbound for bidirectional communication.

Outbound (SMTP):

- The Gmail channel SHALL send notifications via SMTP using `aiosmtplib`.
- The Gmail channel SHALL support Gmail App Passwords for authentication, configured via `SMTP_HOST` (default: `smtp.gmail.com`), `SMTP_PORT` (default: `587`), `SMTP_USER`, `SMTP_PASSWORD` environment variables. OAuth2 support is deferred to a future change.
- Email subjects SHALL include the change-id and a notification token in the format `[coordinator] <summary> [#<TOKEN>]`.
- Email bodies SHALL be HTML with: event summary, agent info, context details, and reply instructions.
- Emails SHALL use `In-Reply-To` and `References` headers to thread messages by change-id.
- The Gmail channel SHALL include custom headers: `X-Coordinator-Token`, `X-Coordinator-Event`, `X-Coordinator-Change-Id`.

#### Scenario: Approval notification email

WHEN the Gmail channel receives an `approval.submitted` event
THEN it sends an email with subject `[coordinator] Approval needed: <operation> [#<TOKEN>]`
AND the body includes agent name, operation description, resource, and reply instructions
AND a notification token is generated and stored with 1-hour TTL.

Inbound (IMAP IDLE):

- The Gmail channel SHALL monitor an IMAP mailbox using IMAP IDLE for near-real-time reply detection.
- The Gmail channel SHALL use `aioimaplib` for async IMAP operations.
- IMAP credentials SHALL be configured via `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD` environment variables.
- The Gmail channel SHALL reconnect and re-IDLE on timeout (29 minutes for Gmail) or connection loss.
- Reply parsing SHALL extract the token from: (a) subject line `[#TOKEN]` pattern, or (b) `In-Reply-To` header matching a sent message.
- Reply parsing SHALL extract the token using this precedence: (1) regex match `\[#([A-Za-z0-9]{8})\]` in subject line, (2) `In-Reply-To` header matching a previously sent `Message-ID`. If neither yields a token, the reply SHALL be ignored.
- Reply parsing SHALL split the reply body by whitespace, strip punctuation from the first word, and match case-insensitively against the command set. Multi-line replies SHALL treat the first line as the command; remaining lines are appended as guidance context.
- Reply parsing SHALL recognize these commands (case-insensitive, first word only):
  - `approved`, `approve`, `yes` → calls `ApprovalService.decide_request(request_id, "approved", decided_by=sender_email)`
  - `denied`, `deny`, `no` → calls `ApprovalService.decide_request(request_id, "denied", decided_by=sender_email)`
  - `resolved` → calls `POST /status/report` with `{"event_type": "gate_check", "change_id": "<from_token>", "message": "Human confirmed resolved"}`, which the auto-dev-loop's gate check evaluates on next iteration
  - `skip` → calls `POST /status/report` with `{"event_type": "phase_skip", "change_id": "<from_token>", "message": "Human requested phase skip"}`
  - Any other text → calls `MemoryService.remember(event_type="guidance", content=<reply_text>, tags=["human-feedback", change_id])` for injection into the next convergence round
- The Gmail channel SHALL validate the sender by extracting the email address from the IMAP envelope and matching case-insensitively against `NOTIFICATION_ALLOWED_SENDERS` (comma-separated email allowlist). No domain wildcards.
- Invalid tokens (expired, already used, not found) SHALL result in a reply email explaining the specific error. If expired, the reply SHALL include a list of current pending approvals (if any).

Security Prohibitions:

- The relay MUST NOT execute arbitrary shell commands or code derived from email content.
- The relay MUST NOT allow approval decisions from addresses not in `NOTIFICATION_ALLOWED_SENDERS`.
- The relay MUST NOT reuse or re-validate an invalidated token.
- The relay MUST NOT include secrets, API keys, or internal URLs in outbound notification emails.
- The relay MUST NOT process email attachments — only the plain-text body is parsed.

#### Scenario: Human approves via email reply

WHEN a human replies to an approval notification email with "approved"
AND the sender is in the allowed senders list
AND the token in the subject is valid and unexpired
THEN the Gmail channel SHALL call `ApprovalService.decide_request(request_id, "approved", decided_by=sender_email)`
AND the token SHALL be invalidated (single-use)
AND a confirmation email SHALL be sent: "Approved. Agent resuming."

#### Scenario: Concurrent replies for same approval

WHEN two humans reply to the same approval notification simultaneously
THEN the first reply to reach the database SHALL set `used_at = NOW()` via `UPDATE ... WHERE used_at IS NULL` (atomic)
AND the second reply SHALL receive "Token already used" error
AND no duplicate coordinator action is taken.

#### Scenario: Reply with expired token

WHEN a human replies to a notification email
AND the token has expired (past TTL)
THEN the Gmail channel SHALL send a reply: "Token expired. Current pending approvals: [list]"
AND no coordinator action is taken.

#### Scenario: Reply from unauthorized sender

WHEN an email reply is received from an address not in `NOTIFICATION_ALLOWED_SENDERS`
THEN the reply SHALL be ignored (no response sent)
AND an audit log entry SHALL be created with `operation: "unauthorized_reply"`, `agent_id: "<sender_email>"`.

#### Scenario: Human replies "resolved" to escalation notification

WHEN a human replies "resolved" to an escalation notification
AND the token is valid
THEN the relay SHALL call `POST /status/report` with `event_type: "gate_check"` and `change_id` from the token
AND the coordinator SHALL store this as a status event in the `coordinator_status` NOTIFY channel
AND a confirmation email SHALL be sent: "Gate check triggered. Loop will re-evaluate."

Note: The auto-dev-loop's existing `gate_check_fn` callback (already defined in `auto_dev_loop.py`) polls coordinator state. When it sees a `gate_check` status event for its change-id, it re-evaluates the escalation condition. No new callback parameter is needed — `gate_check_fn` is already part of `run_loop()`'s signature.

#### Scenario: Human replies with free-text guidance

WHEN a human replies with "The API should use REST conventions, not RPC style"
AND the token is valid
THEN the relay SHALL store the text via `MemoryService.remember()` with tags `["human-feedback", "<change_id>"]`
AND a confirmation email SHALL be sent: "Guidance recorded. Will be available in next review round."

### Requirement: Notification Tokens

The coordinator SHALL manage short-lived, single-use tokens for secure reply-based interactions.

- Tokens SHALL be 8-character alphanumeric strings generated via `secrets.token_urlsafe`.
- Tokens SHALL be stored in a `notification_tokens` table with columns: `token`, `event_type`, `entity_id`, `change_id`, `created_at`, `expires_at`, `used_at`.
- Default TTL SHALL be 1 hour, configurable via `NOTIFICATION_TOKEN_TTL_SECONDS` (default: 3600).
- Tokens SHALL be single-use — the `used_at` column is set on first use, subsequent uses are rejected.
- Expired tokens SHALL be cleaned up by the watchdog service periodically.

#### Scenario: Token validation succeeds

WHEN a reply contains token `ABC12345`
AND the token exists in `notification_tokens` with `used_at IS NULL` and `expires_at > NOW()`
THEN validation succeeds
AND `used_at` is set to the current timestamp.

#### Scenario: Token reuse rejected

WHEN a reply contains a token that has already been used (`used_at IS NOT NULL`)
THEN validation fails with "Token already used".

### Requirement: Status Reporting

The coordinator SHALL accept status reports from agents via both Claude Code hooks and HTTP API.

- A new `POST /status/report` endpoint SHALL accept: `agent_id`, `change_id`, `phase`, `message`, `needs_human` (boolean), `event_type` (optional, default: `"phase_transition"`), `metadata` (optional JSON).
- The endpoint SHALL update the agent's heartbeat timestamp as a side effect.
- If `needs_human` is true, the event SHALL be classified as `high` urgency.
- The endpoint SHALL emit a `coordinator_status` NOTIFY event for all status reports.
- Special `event_type` values have semantic meaning for the auto-dev-loop:
  - `gate_check` — signals that a human has confirmed an escalation is resolved. The auto-dev-loop's `gate_check_fn` SHALL query for recent `gate_check` events for its `change_id` and re-evaluate the escalation condition if found.
  - `phase_skip` — signals that a human wants to bypass the current phase. The auto-dev-loop's `gate_check_fn` SHALL query for recent `phase_skip` events and return `True` (resolved) if found, causing the loop to exit ESCALATE and proceed to the next phase.
- A `report_status.py` Claude Code hook script SHALL:
  - Fire on `Stop` and `SubagentStop` events.
  - Read `loop-state.json` if present to extract `current_phase` and `findings_trend`.
  - If `loop-state.json` is missing or contains invalid JSON, report `phase: "UNKNOWN"` and log a warning to stderr.
  - Compare `current_phase` against `.status-cache.json` — only report if phase has changed.
  - Call `POST /status/report` with extracted data.
  - Run the HTTP call with a hard 5-second timeout (`subprocess` or `httpx` with `timeout=5.0`). If the coordinator is unreachable or the call times out, log to stderr and exit 0 (do NOT block Claude Code).
  - Exit 0 in all cases (success, timeout, error) — the hook MUST NOT block the agent.
  - Update `.status-cache.json` with the reported phase on success.
- The auto-dev-loop's `run_loop()` SHALL accept an optional `status_fn` callback with signature `(state: LoopState, event_type: str, message: str, urgent: bool) -> None`.
- If `status_fn` raises an exception or exceeds 5 seconds, the exception SHALL be caught and logged. The loop SHALL NOT crash or change behavior due to `status_fn` failures. The error SHALL be included as `error_details` in the next heartbeat.
- **Two code paths** (both produce equivalent `coordinator_status` NOTIFY events):
  - **Path A (in-band callback)**: `run_loop()` calls `status_fn` at phase transitions. The callback delegates to `report_status` MCP tool (local) or `POST /status/report` (HTTP). Works for all agents (Claude, Codex, Gemini).
  - **Path B (out-of-band hook)**: Claude Code `Stop` hook fires `report_status.py`, which reads `loop-state.json` independently and POSTs to `/status/report`. Claude Code-specific; provides implicit heartbeat.

#### Scenario: Claude Code hook reports phase transition

WHEN a Claude Code `Stop` hook fires
AND `loop-state.json` exists with `current_phase` different from cached phase
THEN `report_status.py` SHALL call `POST /status/report` with the new phase
AND the coordinator emits a `coordinator_status` NOTIFY event.

#### Scenario: Codex agent reports status via HTTP

WHEN a Codex agent calls `POST /status/report` with `{"agent_id": "codex-1", "phase": "IMPL_REVIEW", "needs_human": false}`
THEN the coordinator stores the status and updates the heartbeat
AND emits a `coordinator_status` NOTIFY event with urgency `medium`.

### Requirement: Watchdog Service

The coordinator SHALL run a periodic health monitoring loop as an asyncio background task.

- The watchdog SHALL run within the `coordination_api.py` FastAPI lifespan (not a separate process).
- The watchdog SHALL check every 60 seconds (configurable via `WATCHDOG_INTERVAL_SECONDS`, range 10-3600, default: 60).
- The watchdog SHALL detect and notify on:
  - **Stale agents**: heartbeat older than 15 minutes → `high` urgency notification, then call `cleanup_dead_agents()`.
  - **Aging approvals**: pending approvals older than 15 minutes → `medium` urgency reminder. Reminders SHALL be debounced by storing `last_reminder_at` in a `watchdog_state` in-memory dict keyed by `approval_id`. Re-send only if `last_reminder_at` is older than 30 minutes. On coordinator restart, debounce state resets (acceptable — first check after restart sends reminders for all aging approvals).
  - **Expiring locks**: locks within 10 minutes of TTL expiration → `medium` urgency warning to lock holder.
  - **Expired tokens**: DELETE from `notification_tokens` WHERE `expires_at < NOW()`.
  - **Event bus health**: if event bus `failed` flag is set, emit a `high` urgency notification via direct `pg_notify` (not through the failed listener) and attempt to restart the event bus.
  - **Stale agent with pending approvals**: if a stale agent is cleaned up AND `approval_queue` has pending requests from that agent, those approvals SHALL be expired and a notification sent.
- The watchdog SHALL emit events via direct `pg_notify` call (using the coordinator's database connection, not through the event bus listener) to ensure notifications work even if the event bus is down.
- The watchdog SHALL NOT block if `pg_notify` fails — log error and continue to next check.
- The watchdog SHALL be disabled when `NOTIFICATION_CHANNELS` is empty (no point monitoring if nobody is listening).

#### Scenario: Stale agent detected

WHEN the watchdog finds an agent with `last_heartbeat` older than 15 minutes
AND the agent status is `active`
THEN it emits a `coordinator_agent` event with `event_type: "stale"` and urgency `high`
AND calls `cleanup_dead_agents()` to release the agent's locks.

#### Scenario: Aging approval reminder

WHEN the watchdog finds a pending approval older than 15 minutes
AND no reminder has been sent in the last 30 minutes for this approval
THEN it emits a `coordinator_approval` event with `event_type: "reminder"` and urgency `medium`.

## Database Tables

### Phase 1 (Implemented)
| Table | Purpose | Migration |
|-------|---------|-----------|
| `file_locks` | Active file locks with TTL | `001_core_schema.sql` |
| `work_queue` | Task assignment queue | `001_core_schema.sql` |
| `agent_sessions` | Agent work sessions | `001_core_schema.sql` |

### Phase 2 (Implemented)
| Table | Purpose | Migration |
|-------|---------|-----------|
| `memory_episodic` | Experiences and their outcomes | `004_memory_tables.sql` |
| `memory_working` | Active context for current tasks | `004_memory_tables.sql` |
| `memory_procedural` | Learned skills and patterns | `004_memory_tables.sql` |
| `handoff_documents` | Session continuity between agents | `002_handoff_documents.sql` |
| `agent_discovery` | Agent heartbeat and discovery | `003_agent_discovery.sql` |

### Phase 3 (Implemented)
| Table | Purpose | Migration |
|-------|---------|-----------|
| `operation_guardrails` | Destructive operation patterns and rules | `006_guardrails.sql` |
| `agent_profiles` | Capability definitions with trust levels | `007_profiles.sql` |
| `network_policies` | Domain allowlists/denylists per profile | `008_network_policies.sql` |
| `audit_log` | Immutable log of all coordination operations | `009_audit.sql` |
| `cedar_policies` | Cedar policy-as-code storage (optional) | `010_cedar_policies.sql` |
| `feature_registry` | Active feature tracking and resource claims | `011_feature_registry.sql` |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Lock conflicts | 0 | Count of failed merges due to conflicts |
| Memory retrieval relevance | >70% useful | Agent feedback on suggested memories |
| Task completion rate | >90% | Completed / Claimed tasks |
| Verification pass rate | >80% | First-pass verification success |
| Mean time to verify | <5 min | From push to verification complete |
| Guardrail block rate | >99% | Destructive operations caught before execution |
| Cloud agent coordination success | >95% | Successful API connections from cloud agents |
| Audit log completeness | 100% | All operations logged without gaps |
| Trust level accuracy | <1% false positives | Legitimate operations incorrectly blocked |

---

## Preconfigured Agent Profiles

### claude-code-cli
```yaml
agent_type: claude_code_cli
trust_level: 3
connection: mcp
network_policy: full_access
allowed_operations: [read, write, execute, git_push]
blocked_operations: [git_push_force_main, credential_modify]
resource_limits:
  max_file_modifications: unlimited
  max_execution_time: unlimited
guardrails: [warn_destructive_git]
```

### claude-code-web-reviewer
```yaml
agent_type: claude_code_web
trust_level: 2
connection: http_api
network_policy: documentation_only
allowed_operations: [read, analyze, comment, create_review]
blocked_operations: [write, execute, git_push]
resource_limits:
  max_file_reads: 500
  max_execution_time: 30m
guardrails: [read_only_filesystem]
```

### claude-code-web-implementer
```yaml
agent_type: claude_code_web
trust_level: 3
connection: http_api
network_policy: package_managers_and_docs
required_domains: [coord.yourdomain.com]
allowed_operations: [read, write, execute, git_push_branch]
blocked_operations: [git_push_force, git_push_main, credential_modify]
resource_limits:
  max_file_modifications: 100
  max_execution_time: 2h
guardrails: [no_destructive_git, lock_before_write, test_required]
```

### codex-cloud-worker
```yaml
agent_type: codex_cloud
trust_level: 2
connection: http_api
network_policy: coordination_only
required_domains: [coord.yourdomain.com]
allowed_operations: [read, write, execute]
blocked_operations: [git_push]  # Codex creates PRs, doesn't push
resource_limits:
  max_file_modifications: 50
  max_execution_time: 1h
guardrails: [no_destructive_git, lock_before_write]
```

### strands-orchestrator
```yaml
agent_type: strands_agent
trust_level: 4
connection: agentcore_gateway
network_policy: configurable
allowed_operations: [read, write, execute, spawn_agent, manage_swarm]
blocked_operations: [credential_modify]
resource_limits:
  max_spawned_agents: 10
  max_execution_time: 8h
guardrails: [audit_all_operations]
```
