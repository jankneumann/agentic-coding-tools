# Agent Coordinator System

## Purpose

A multi-agent coordination system that enables local agents (Claude Code CLI, Codex CLI, Aider), cloud agents (Claude Code Web, Codex Cloud), and orchestrated agent swarms (Strands Agents) to collaborate safely on shared codebases.

**Problem Statement**: When multiple AI coding agents work on the same codebase they face conflicts (merge conflicts from concurrent edits), context loss (no memory across sessions), no orchestration (no task tracking), verification gaps (cloud agents can't verify against real environments), and safety risks (autonomous agents executing destructive operations).

## Implementation Status

| Phase | Scope | Status |
|-------|-------|--------|
| **Phase 1 (MVP)** | File locking, work queue, MCP server, Supabase persistence | **Implemented** |
| Phase 2 | HTTP API for cloud agents, episodic memory, GitHub-mediated coordination | Specified |
| Phase 3 | Guardrails engine, verification gateway, agent profiles, approval queues | Specified |
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

The system SHALL provide exclusive file locking to prevent merge conflicts when multiple agents edit files concurrently.

- Locks SHALL be associated with a specific agent ID
- Locks SHALL have a configurable TTL (time-to-live) with auto-expiration
- Lock acquisition SHALL be atomic to prevent race conditions
- The system SHALL support optional reason tracking for locks

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
- **THEN** agent discovers available tools: `acquire_lock`, `release_lock`, `check_locks`, `get_work`, `complete_work`, `submit_work`
- **AND** (Phase 2) `remember`, `recall` tools when memory is implemented

#### Scenario: MCP resource access
- **WHEN** agent queries MCP resources
- **THEN** agent can access `locks://current`, `work://pending` resources

---

### Requirement: HTTP API Interface

The system SHALL provide HTTP API for cloud agents that cannot use MCP protocol.

- Authentication SHALL use API key via `X-API-Key` header
- All coordination capabilities SHALL have equivalent HTTP endpoints

#### Scenario: Cloud agent acquires lock via HTTP
- **WHEN** cloud agent sends `POST /locks/acquire` with valid API key
- **THEN** system processes lock request and returns JSON response

#### Scenario: Invalid API key
- **WHEN** request is made without valid `X-API-Key` header
- **THEN** system returns 401 Unauthorized

---

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

The system SHALL track agent work sessions for coordination and auditing.

- Sessions SHALL be associated with agent_id and agent_type
- Sessions SHALL track start/end times
- Changesets SHALL be associated with sessions

#### Scenario: Session tracking
- **WHEN** agent begins work
- **THEN** system creates or updates agent_sessions record

---

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

## Database Tables

### Phase 1 (Implemented)
| Table | Purpose | Migration |
|-------|---------|-----------|
| `file_locks` | Active file locks with TTL | `001_core_schema.sql` |
| `work_queue` | Task assignment queue | `001_core_schema.sql` |
| `agent_sessions` | Agent work sessions | `001_core_schema.sql` |

### Phase 2+ (Planned)
| Table | Purpose |
|-------|---------|
| `changesets` | Records of agent-generated changes |
| `verification_results` | Outcomes of verification runs |
| `verification_policies` | Configurable routing rules |
| `approval_queue` | Human review tracking |
| `memory_episodic` | Experiences and their outcomes |
| `memory_working` | Active context for current tasks |
| `memory_procedural` | Learned skills and patterns |

### Phase 3+ (Planned)
| Table | Purpose |
|-------|---------|
| `agent_profiles` | Capability definitions with trust levels |
| `agent_profile_assignments` | Maps agent_id to profile_id |
| `network_policies` | Domain allowlists/denylists per profile |
| `network_access_log` | Audit trail of network requests |
| `operation_guardrails` | Destructive operation patterns and rules |
| `guardrail_violations` | Log of blocked/approved destructive attempts |
| `audit_log` | Immutable log of all coordination operations |

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
