## ADDED Requirements

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

## MODIFIED Requirements

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
