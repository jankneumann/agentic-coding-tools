# Agent Coordinator System

## Purpose

A multi-agent coordination system that enables local agents (Claude Code, Codex CLI, Aider) and cloud agents (Claude API, Codex Cloud) to collaborate safely on shared codebases.

**Problem Statement**: When multiple AI coding agents work on the same codebase they face conflicts (merge conflicts from concurrent edits), context loss (no memory across sessions), no orchestration (no task tracking), and verification gaps (cloud agents can't verify against real environments).

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
- **THEN** system returns `{success: true, task_id: null}`

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
- **THEN** agent discovers available tools: `acquire_lock`, `release_lock`, `check_locks`, `remember`, `recall`, `get_work`, `complete_work`, `submit_work`

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

## Database Tables

### Core Tables
| Table | Purpose |
|-------|---------|
| `file_locks` | Active file locks with TTL |
| `changesets` | Records of agent-generated changes |
| `verification_results` | Outcomes of verification runs |
| `verification_policies` | Configurable routing rules |
| `approval_queue` | Human review tracking |
| `agent_sessions` | Agent work sessions |

### Memory Tables
| Table | Purpose |
|-------|---------|
| `memory_episodic` | Experiences and their outcomes |
| `memory_working` | Active context for current tasks |
| `memory_procedural` | Learned skills and patterns |
| `work_queue` | Task assignment queue |

---

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Lock conflicts | 0 | Count of failed merges due to conflicts |
| Memory retrieval relevance | >70% useful | Agent feedback on suggested memories |
| Task completion rate | >90% | Completed / Claimed tasks |
| Verification pass rate | >80% | First-pass verification success |
| Mean time to verify | <5 min | From push to verification complete |
