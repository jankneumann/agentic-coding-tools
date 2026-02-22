## ADDED Requirements

### Requirement: Cross-Surface Skill Parity

Coordinator-integrated workflow skills SHALL remain synchronized across all runtime skill trees used by this repository:
- `.claude/skills/` (Claude Codex runtime)
- `.codex/skills/` (Codex runtime)
- `.gemini/skills/` (Gemini runtime)
- `skills/` (top-level shared mirror)

Changes to integrated skills SHALL be applied consistently across these trees, except for explicitly documented runtime-specific differences.

#### Scenario: Integration change is applied to all runtimes
- **WHEN** a coordination hook is added to an integrated skill
- **THEN** the corresponding skill file in each runtime tree SHALL be updated in the same change
- **AND** the change SHALL document any intentional runtime-specific differences

#### Scenario: Runtime parity check detects drift
- **WHEN** parity validation runs
- **AND** one runtime skill file diverges without an approved exception
- **THEN** validation SHALL fail
- **AND** report the divergent files

### Requirement: Coordination Detection

Each integrated skill SHALL detect coordinator access using a transport-aware model that works for both CLI and Web/Cloud agents.

Detection SHALL set:
- `COORDINATOR_AVAILABLE` (`true` or `false`)
- `COORDINATION_TRANSPORT` (`mcp`, `http`, or `none`)
- Capability flags: `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

Detection rules:
- Local CLI agents (Claude Codex, Codex, Gemini CLI) SHALL inspect available MCP tools by function name
- Web/Cloud agents SHALL detect coordinator availability via HTTP API reachability/capability checks
- Coordination features SHALL execute only when their required capability flag is true

#### Scenario: CLI runtime with MCP tools
- **WHEN** an integrated skill starts in a CLI runtime
- **AND** coordination MCP tools are present in the available tool list
- **THEN** the skill SHALL set `COORDINATION_TRANSPORT=mcp`
- **AND** set `COORDINATOR_AVAILABLE=true`
- **AND** set capability flags based on discovered tool availability

#### Scenario: Web/Cloud runtime with HTTP coordinator
- **WHEN** an integrated skill starts in a Web/Cloud runtime
- **AND** coordinator HTTP endpoint is reachable with valid credentials
- **THEN** the skill SHALL set `COORDINATION_TRANSPORT=http`
- **AND** set `COORDINATOR_AVAILABLE=true`
- **AND** set capability flags based on available HTTP endpoints/features

#### Scenario: Partial capability availability
- **WHEN** coordinator transport is available but one or more capabilities are missing
- **THEN** the skill SHALL keep `COORDINATOR_AVAILABLE=true`
- **AND** set missing capability flags to false
- **AND** skip only the unsupported coordination steps

#### Scenario: No coordinator access
- **WHEN** neither MCP nor HTTP coordinator access is available
- **THEN** the skill SHALL set `COORDINATOR_AVAILABLE=false`
- **AND** set `COORDINATION_TRANSPORT=none`
- **AND** execute existing standalone behavior without errors

#### Scenario: Coordinator becomes unreachable mid-execution
- **WHEN** a coordination call fails after detection succeeded
- **THEN** the skill SHALL log the failure as informational
- **AND** continue with standalone fallback behavior for that step
- **AND** NOT abort solely due to coordinator unavailability

### Requirement: File Locking in Implement Feature

The `/implement-feature` skill SHALL use coordinator file locks only when lock capability is available.

#### Scenario: Lock acquisition succeeds
- **WHEN** `/implement-feature` is about to modify a file
- **AND** `CAN_LOCK=true`
- **THEN** the skill SHALL request a lock for that file before modification
- **AND** proceed only after lock acquisition succeeds

#### Scenario: Lock acquisition blocked by another agent
- **WHEN** `/implement-feature` requests a lock held by another agent
- **THEN** the skill SHALL report lock owner and expiry details when provided
- **AND** skip modification of the blocked file
- **AND** continue with unblocked files

#### Scenario: Lock release on completion or failure
- **WHEN** `/implement-feature` completes or exits unexpectedly
- **AND** locks were acquired
- **THEN** the skill SHALL attempt to release all acquired locks
- **AND** report release failures as warnings

#### Scenario: Locking capability unavailable
- **WHEN** `/implement-feature` runs with `CAN_LOCK=false`
- **THEN** the skill SHALL continue using existing non-locking behavior

### Requirement: Work Queue Integration in Implement Feature

The `/implement-feature` skill SHALL integrate with coordinator work queue capabilities when available.

#### Scenario: Submit independent tasks to queue
- **WHEN** `/implement-feature` identifies independent implementation tasks
- **AND** `CAN_QUEUE_WORK=true`
- **THEN** the skill SHALL submit those tasks to the coordinator queue
- **AND** report submitted task identifiers for tracking

#### Scenario: Local claim when tasks are unclaimed
- **WHEN** submitted tasks are not claimed by other agents within timeout
- **AND** `CAN_QUEUE_WORK=true`
- **THEN** the skill SHALL claim and execute tasks locally through coordinator queue APIs
- **AND** mark tasks completed after execution

#### Scenario: Queue capability unavailable
- **WHEN** `/implement-feature` runs with `CAN_QUEUE_WORK=false`
- **THEN** the skill SHALL use existing local `Task()` execution behavior

### Requirement: Session Handoff Hooks

The creative lifecycle skills (`/plan-feature`, `/implement-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/cleanup-feature`) SHALL use handoff hooks when handoff capability is available.

#### Scenario: Read handoff context at skill start
- **WHEN** one of the lifecycle skills starts
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL read recent handoffs
- **AND** incorporate relevant context into execution planning

#### Scenario: Write handoff summary at skill completion
- **WHEN** one of the lifecycle skills completes
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL write a handoff summary with completed work, in-progress items, decisions, and next steps

#### Scenario: Handoff capability unavailable
- **WHEN** lifecycle skills run with `CAN_HANDOFF=false`
- **THEN** they SHALL proceed without handoff operations

### Requirement: Memory Hooks

Memory hooks SHALL be applied selectively to skills where historical context directly improves outcomes.

- Recall at start (`CAN_MEMORY=true`): `/explore-feature`, `/plan-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature`
- Remember on completion (`CAN_MEMORY=true`): `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature`

#### Scenario: Recall relevant memories
- **WHEN** one of the recall-enabled skills starts
- **AND** `CAN_MEMORY=true`
- **THEN** the skill SHALL query relevant memories for the current change/task context
- **AND** use relevant results to refine execution

#### Scenario: Record iteration or validation outcomes
- **WHEN** one of the remember-enabled skills completes
- **AND** `CAN_MEMORY=true`
- **THEN** the skill SHALL store a structured outcome summary and lessons learned

#### Scenario: Memory capability unavailable
- **WHEN** memory hooks are reached with `CAN_MEMORY=false`
- **THEN** the skill SHALL skip memory operations and continue normally

### Requirement: Guardrail Pre-checks

The `/implement-feature` and `/security-review` skills SHALL run guardrail checks when guardrail capability is available.

In phase 1, guardrail violations SHALL be informational and SHALL NOT hard-block execution.

#### Scenario: Guardrail check indicates safe operation
- **WHEN** a guarded operation is evaluated
- **AND** `CAN_GUARDRAILS=true`
- **AND** the guardrail response indicates safe execution
- **THEN** the skill SHALL proceed with the operation

#### Scenario: Guardrail violations detected
- **WHEN** guardrail response reports violations
- **AND** `CAN_GUARDRAILS=true`
- **THEN** the skill SHALL report violation details in findings/output
- **AND** continue execution in informational mode

#### Scenario: Guardrail capability unavailable
- **WHEN** guardrail checks are reached with `CAN_GUARDRAILS=false`
- **THEN** the skill SHALL continue without guardrail checks

### Requirement: Setup Coordinator Skill

The system SHALL provide a `/setup-coordinator` skill in all runtime trees (`.claude`, `.codex`, `.gemini`, and `skills`) to onboard users for coordinator usage across CLI and Web/Cloud contexts.

#### Scenario: CLI setup path
- **WHEN** a user runs `/setup-coordinator` for CLI usage
- **THEN** the skill SHALL verify or configure MCP coordinator settings for that runtime
- **AND** verify connectivity through a coordinator session/health call

#### Scenario: Web/Cloud setup path
- **WHEN** a user runs `/setup-coordinator` for Web/Cloud usage
- **THEN** the skill SHALL guide HTTP API configuration (URL, credentials, allowlist considerations)
- **AND** verify API connectivity

#### Scenario: Existing configuration detected
- **WHEN** `/setup-coordinator` finds existing coordinator configuration
- **THEN** the skill SHALL validate it and report status
- **AND** provide reconfiguration guidance when validation fails

#### Scenario: Setup fails
- **WHEN** setup cannot complete due to connectivity or credential issues
- **THEN** the skill SHALL report the specific failure
- **AND** provide troubleshooting guidance
- **AND** remind users that workflow skills still work in standalone mode

### Requirement: Coordination Bridge Script

The system SHALL provide `scripts/coordination_bridge.py` as a stable HTTP coordination contract for skill helper scripts and Web/Cloud-oriented validation flows.

The bridge SHALL:
- Normalize endpoint/parameter differences behind stable helper functions
- Detect HTTP transport availability and exposed capabilities
- Return no-op success-like responses with `status="skipped"` when unavailable

#### Scenario: Bridge detects HTTP coordinator and capabilities
- **WHEN** a script calls bridge detection helper
- **AND** coordinator API is reachable
- **THEN** the bridge SHALL return availability, transport (`http`), and capability metadata

#### Scenario: Bridge provides graceful no-op fallback
- **WHEN** a script calls a bridge operation and coordinator is unavailable
- **THEN** the bridge SHALL return `status="skipped"` with explanatory metadata
- **AND** SHALL NOT raise unhandled exceptions for expected unavailability

#### Scenario: Bridge absorbs API contract changes
- **WHEN** coordinator HTTP endpoint shapes evolve
- **THEN** updates SHALL be localized to `scripts/coordination_bridge.py`
- **AND** downstream scripts using bridge helpers SHALL not require API-shape rewrites

#### Scenario: Bridge used by validation tooling
- **WHEN** validation or smoke tooling needs coordination assertions
- **THEN** tooling SHALL be able to call bridge helpers instead of hardcoding coordinator HTTP details
