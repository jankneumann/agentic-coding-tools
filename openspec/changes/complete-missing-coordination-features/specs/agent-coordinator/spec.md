## MODIFIED Requirements

### Requirement: Database Persistence

The system SHALL use Supabase as the coordination backbone with PostgreSQL for persistence.

- All coordination state SHALL be stored in Supabase tables
- Critical operations SHALL use PostgreSQL functions for atomicity
- Row Level Security (RLS) SHALL be used for access control
- Database schemas SHALL be managed through numbered migration files in the `supabase/migrations/` directory
- All table definitions — including verification, memory, guardrails, profiles, audit, and network policy tables — SHALL be part of the main migration pipeline
- Migrations SHALL be additive and backward-compatible with prior phases

#### Scenario: Atomic lock acquisition
- **WHEN** lock acquisition is attempted
- **THEN** system uses `INSERT ... ON CONFLICT DO NOTHING RETURNING` pattern

#### Scenario: Atomic task claiming
- **WHEN** task claiming is attempted
- **THEN** system uses `FOR UPDATE SKIP LOCKED` pattern to prevent race conditions

#### Scenario: Schema deployed via migration pipeline
- **WHEN** a new coordination feature requires database tables
- **THEN** the schema SHALL be defined in a numbered migration file (e.g., `004_memory_tables.sql`)
- **AND** the migration SHALL be deployable via standard Supabase migration tooling
- **AND** the migration SHALL not modify or break existing tables from prior migrations

### Requirement: MCP Server Interface

The system SHALL expose coordination capabilities as native MCP tools for local agents (Claude Code, Codex CLI).

- The server SHALL implement FastMCP protocol
- Connection SHALL be via stdio transport
- All coordination tools SHALL be available as MCP tools
- Memory tools (`remember`, `recall`) SHALL be included for episodic and procedural memory access

#### Scenario: Local agent connects via MCP
- **WHEN** local agent connects to coordination MCP server
- **THEN** agent discovers available tools: `acquire_lock`, `release_lock`, `check_locks`, `get_work`, `complete_work`, `submit_work`, `write_handoff`, `read_handoff`, `discover_agents`, `register_session`, `heartbeat`, `remember`, `recall`

#### Scenario: MCP resource access
- **WHEN** agent queries MCP resources
- **THEN** agent can access `locks://current`, `work://pending`, `handoffs://recent` resources

#### Scenario: Agent stores memory via MCP
- **WHEN** agent calls `remember(event_type, summary, details?, outcome?, lessons?, tags?)`
- **THEN** system stores episodic memory and returns `{success: true, memory_id: uuid}`

#### Scenario: Agent retrieves memories via MCP
- **WHEN** agent calls `recall(task_description, tags?, limit?)`
- **THEN** system returns relevant memories sorted by relevance score
