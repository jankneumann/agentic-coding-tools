## ADDED Requirements

### Requirement: Canonical Skill Distribution

Coordinator-integrated skill content SHALL be authored in the canonical `skills/` tree.

Runtime skill trees (`.claude/skills/`, `.codex/skills/`, `.gemini/skills/`) SHALL be treated as synced mirrors for this work and refreshed using the existing `skills/install.sh` workflow in `rsync` mode.

#### Scenario: Canonical edit and sync
- **WHEN** coordinator integration changes are made to a skill
- **THEN** changes SHALL be applied to `skills/<skill-name>/SKILL.md`
- **AND** runtime mirror trees SHALL be updated by running `skills/install.sh --mode rsync --agents claude,codex,gemini`

#### Scenario: Runtime mirror drift is detected
- **WHEN** runtime mirror skills differ from canonical `skills/` after sync
- **THEN** the differences SHALL be treated as parity defects
- **AND** the change SHALL NOT be considered ready until drift is resolved

#### Scenario: Existing sync workflow is preserved
- **WHEN** implementing this change
- **THEN** it SHALL reuse existing `skills/install.sh` behavior
- **AND** SHALL NOT introduce a second competing distribution mechanism

### Requirement: Coordination Detection

Each integrated skill SHALL detect coordinator access using a transport-aware model that works for both CLI and Web/Cloud agents.

Detection SHALL set:
- `COORDINATOR_AVAILABLE` (`true` or `false`)
- `COORDINATION_TRANSPORT` (`mcp`, `http`, or `none`)
- capability flags: `CAN_LOCK`, `CAN_QUEUE_WORK`, `CAN_HANDOFF`, `CAN_MEMORY`, `CAN_GUARDRAILS`

Detection rules:
- Local CLI agents (Claude Codex, Codex, Gemini CLI) inspect available MCP tools by function name
- Web/Cloud agents detect coordinator via HTTP API reachability/capability checks
- Coordination hooks execute only when their capability flag is true

#### Scenario: CLI runtime with MCP tools
- **WHEN** an integrated skill starts in a CLI runtime
- **AND** coordination MCP tools are present
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
- **WHEN** transport is available but some capabilities are not
- **THEN** the skill SHALL keep `COORDINATOR_AVAILABLE=true`
- **AND** set missing capability flags to false
- **AND** skip only unsupported hooks

#### Scenario: No coordinator access
- **WHEN** neither MCP nor HTTP coordinator access is available
- **THEN** the skill SHALL set `COORDINATOR_AVAILABLE=false`
- **AND** set `COORDINATION_TRANSPORT=none`
- **AND** continue standalone behavior without errors

#### Scenario: Coordinator becomes unreachable mid-execution
- **WHEN** a coordination call fails after detection succeeded
- **THEN** the skill SHALL log informationally
- **AND** continue standalone fallback behavior for that step
- **AND** NOT abort solely due to coordinator unavailability

### Requirement: File Locking in Implement Feature

The `/implement-feature` skill SHALL use coordinator file locks only when lock capability is available.

#### Scenario: Lock acquisition succeeds
- **WHEN** `/implement-feature` is about to modify a file
- **AND** `CAN_LOCK=true`
- **THEN** the skill SHALL request a lock before modification
- **AND** proceed only after lock acquisition succeeds

#### Scenario: Lock acquisition blocked by another agent
- **WHEN** `/implement-feature` requests a lock held by another agent
- **THEN** the skill SHALL report owner/expiry details when available
- **AND** skip blocked files while continuing unblocked work

#### Scenario: Lock release on completion or failure
- **WHEN** `/implement-feature` completes or fails after acquiring locks
- **THEN** it SHALL attempt lock release
- **AND** log release failures as warnings

#### Scenario: Locking capability unavailable
- **WHEN** `CAN_LOCK=false`
- **THEN** the skill SHALL continue existing non-locking behavior

### Requirement: Work Queue Integration in Implement Feature

The `/implement-feature` skill SHALL integrate with coordinator work queue capabilities when available.

#### Scenario: Submit independent tasks to queue
- **WHEN** independent implementation tasks are identified
- **AND** `CAN_QUEUE_WORK=true`
- **THEN** the skill SHALL submit them to the coordinator queue
- **AND** report submitted task identifiers

#### Scenario: Local claim when tasks are unclaimed
- **WHEN** submitted tasks remain unclaimed within timeout
- **AND** `CAN_QUEUE_WORK=true`
- **THEN** the skill SHALL claim and execute them locally via queue APIs
- **AND** mark completion

#### Scenario: Queue capability unavailable
- **WHEN** `CAN_QUEUE_WORK=false`
- **THEN** the skill SHALL use existing local `Task()` behavior

### Requirement: Session Handoff Hooks

Creative lifecycle skills (`/plan-feature`, `/implement-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/cleanup-feature`) SHALL use handoff hooks when `CAN_HANDOFF=true`.

#### Scenario: Read handoff context at skill start
- **WHEN** a lifecycle skill starts
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL read recent handoffs and incorporate relevant context

#### Scenario: Write handoff summary at completion
- **WHEN** a lifecycle skill completes
- **AND** `CAN_HANDOFF=true`
- **THEN** the skill SHALL write a handoff summary with completed work, in-progress items, decisions, and next steps

#### Scenario: Handoff capability unavailable
- **WHEN** `CAN_HANDOFF=false`
- **THEN** the skill SHALL proceed without handoff operations

### Requirement: Memory Hooks

Memory hooks SHALL be applied where historical context is high value.

- Recall at start (`CAN_MEMORY=true`): `/explore-feature`, `/plan-feature`, `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature`
- Remember on completion (`CAN_MEMORY=true`): `/iterate-on-plan`, `/iterate-on-implementation`, `/validate-feature`

#### Scenario: Recall relevant memories
- **WHEN** a recall-enabled skill starts
- **AND** `CAN_MEMORY=true`
- **THEN** the skill SHALL query relevant memories and use applicable results

#### Scenario: Record iteration or validation outcomes
- **WHEN** a remember-enabled skill completes
- **AND** `CAN_MEMORY=true`
- **THEN** the skill SHALL store structured outcomes and lessons learned

#### Scenario: Memory capability unavailable
- **WHEN** `CAN_MEMORY=false`
- **THEN** memory hooks SHALL be skipped without failing the skill

### Requirement: Guardrail Pre-checks

The `/implement-feature` and `/security-review` skills SHALL run guardrail checks when `CAN_GUARDRAILS=true`.

In phase 1, guardrail violations SHALL be informational and SHALL NOT hard-block execution.

#### Scenario: Guardrail check indicates safe operation
- **WHEN** a guarded operation is evaluated
- **AND** `CAN_GUARDRAILS=true`
- **AND** the response indicates safe execution
- **THEN** the skill SHALL proceed

#### Scenario: Guardrail violations detected
- **WHEN** guardrail response reports violations
- **AND** `CAN_GUARDRAILS=true`
- **THEN** the skill SHALL report violation details
- **AND** continue in informational mode

#### Scenario: Guardrail capability unavailable
- **WHEN** `CAN_GUARDRAILS=false`
- **THEN** the skill SHALL continue without guardrail checks

### Requirement: Setup Coordinator Skill

The system SHALL provide canonical `skills/setup-coordinator/SKILL.md`, then sync it to runtime mirrors using the canonical distribution flow.

The skill SHALL support both:
- CLI MCP setup/verification
- Web/Cloud HTTP setup/verification

#### Scenario: CLI setup path
- **WHEN** user runs `/setup-coordinator` for CLI usage
- **THEN** the skill SHALL verify or configure MCP coordinator settings
- **AND** verify connectivity through a coordinator session/health call

#### Scenario: Web/Cloud setup path
- **WHEN** user runs `/setup-coordinator` for Web/Cloud usage
- **THEN** the skill SHALL guide HTTP API configuration (URL, credentials, allowlist considerations)
- **AND** verify API connectivity

#### Scenario: Existing configuration detected
- **WHEN** setup detects existing configuration
- **THEN** it SHALL validate and report status
- **AND** provide reconfiguration guidance on failure

#### Scenario: Setup fails
- **WHEN** setup cannot complete due to connectivity/credential issues
- **THEN** the skill SHALL report specific failure and troubleshooting guidance
- **AND** remind that standalone mode remains available

### Requirement: Coordination Bridge Script

The system SHALL provide `scripts/coordination_bridge.py` as stable HTTP coordination contract for helper scripts and Web/Cloud validation flows.

The bridge SHALL:
- Normalize endpoint/parameter differences behind stable helpers
- Detect HTTP availability and exposed capabilities
- Return no-op responses with `status="skipped"` when unavailable

#### Scenario: Bridge detects HTTP coordinator and capabilities
- **WHEN** a script calls bridge detection helper
- **AND** coordinator API is reachable
- **THEN** bridge returns availability, transport (`http`), and capability metadata

#### Scenario: Bridge provides graceful no-op fallback
- **WHEN** bridge operation is called and coordinator is unavailable
- **THEN** bridge returns `status="skipped"` with context
- **AND** does not raise unhandled exceptions for expected unavailability

#### Scenario: Bridge absorbs API contract changes
- **WHEN** coordinator HTTP endpoint shapes evolve
- **THEN** changes are localized to `scripts/coordination_bridge.py`
- **AND** downstream scripts using bridge helpers remain stable

#### Scenario: Bridge used by validation tooling
- **WHEN** validation tooling needs coordination assertions
- **THEN** tooling can use bridge helpers instead of hardcoded HTTP details
