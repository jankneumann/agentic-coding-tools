# agent-coordinator — delta

## MODIFIED Requirements

### Requirement: Session Continuity

The system SHALL support session continuity through handoff documents that preserve context across agent sessions.

- Handoff documents SHALL include a summary
- Handoff documents MAY include completed work, in-progress items, decisions, next steps, and relevant files
- Handoff documents MAY include a `supervisor_record` object conforming to `contracts/schemas/supervisor-record.schema.json`; when absent it SHALL be stored and returned as `null`
- Handoff documents SHALL be associated with an agent name and session ID
- The system SHALL support retrieving the most recent handoff for a given agent
- Handoff documents SHALL be stored durably in the coordination database

#### Scenario: Agent writes handoff document
- **WHEN** agent calls `write_handoff(summary, completed_work?, in_progress?, decisions?, next_steps?, relevant_files?, supervisor_record?)`
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

#### Scenario: Handoff without a supervisor record is unchanged
- **WHEN** agent calls `write_handoff` without `supervisor_record`
- **THEN** the stored row SHALL have `supervisor_record = NULL`
- **AND** `read_handoff` SHALL return `supervisor_record: null` alongside the existing fields
- **AND** every pre-existing handoff test SHALL pass without modification

#### Scenario: Supervisor record round-trips through every surface
- **WHEN** a handoff is written with a schema-valid `supervisor_record` via the service, `POST /handoffs/write`, the MCP `write_handoff` tool, or `http_proxy.proxy_write_handoff`
- **THEN** reading it back through the service, `POST /handoffs/read`, the MCP `read_handoff` tool, `handoffs://recent`, and `coordination_cli handoff read` SHALL return a byte-identical `supervisor_record`
- **AND** all four sections (`active_changes`, `pending_gates`, `standing_decisions`, `back_edge`) SHALL be intact

#### Scenario: Pre-migration rows load with a null record
- **WHEN** `HandoffDocument.from_dict` receives a row dict without a `supervisor_record` key
- **THEN** the resulting document SHALL have `supervisor_record = None`
- **AND** no exception SHALL be raised

## ADDED Requirements

### Requirement: Supervisor Record Storage

The `handoff_documents` table SHALL carry a nullable `supervisor_record JSONB` column added by migration `034_handoff_supervisor_record.sql`. The `write_handoff` stored function SHALL accept a trailing `p_supervisor_record JSONB DEFAULT NULL` parameter, and the migration SHALL drop the previous eight-argument overload so RPC calls stay unambiguous. The `read_handoff` stored function SHALL select the column. The coordinator SHALL NOT validate the inner document beyond requiring it to be a JSON object or null; inner-schema validation is the writer's responsibility.

#### Scenario: Migration is additive and forward-only
- **WHEN** migration 034 runs against a database at 033
- **THEN** existing `handoff_documents` rows SHALL be readable with `supervisor_record IS NULL`
- **AND** `SELECT write_handoff(...)` with eight arguments SHALL resolve to the new function with `p_supervisor_record = NULL`

#### Scenario: RPC name alignment holds
- **WHEN** `test_rpc_migration_alignment` runs
- **THEN** every `.rpc()` name in `handoffs.py` SHALL exist as a `CREATE FUNCTION` in migrations

#### Scenario: Non-object record is rejected at the HTTP boundary
- **WHEN** `POST /handoffs/write` receives `supervisor_record` that is not a JSON object or null
- **THEN** the request SHALL fail with HTTP 422
- **AND** nothing SHALL be written
