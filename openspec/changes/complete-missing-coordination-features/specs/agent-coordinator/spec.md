## MODIFIED Requirements

### Requirement: Database Persistence

The system SHALL use PostgreSQL-compatible databases for persistence, with Supabase as the default backend and support for direct PostgreSQL connections via a factory pattern.

- All coordination state SHALL be stored in PostgreSQL-compatible tables
- Critical operations SHALL use PostgreSQL functions for atomicity
- Row Level Security (RLS) SHALL be used for access control where supported by the backend
- Database schemas SHALL be managed through numbered migration files in the `supabase/migrations/` directory (standard PostgreSQL SQL)
- All table definitions — including verification, memory, guardrails, profiles, audit, and network policy tables — SHALL be part of the main migration pipeline
- Migrations SHALL be additive and backward-compatible with prior phases
- New migrations (004-009) SHALL NOT modify or ALTER tables from migrations 000-003
- The system SHALL define a `DatabaseClient` protocol with methods: `rpc`, `query`, `insert`, `update`, `delete`, `close`
- A factory function SHALL create the configured backend based on the `DB_BACKEND` environment variable
- The default backend SHALL be Supabase (PostgREST HTTP), with direct PostgreSQL (asyncpg) as an alternative
- All service classes SHALL depend on the `DatabaseClient` protocol, not on a specific implementation

#### Scenario: Atomic lock acquisition
- **WHEN** lock acquisition is attempted
- **THEN** system uses `INSERT ... ON CONFLICT DO NOTHING RETURNING` pattern

#### Scenario: Atomic task claiming
- **WHEN** task claiming is attempted
- **THEN** system uses `FOR UPDATE SKIP LOCKED` pattern to prevent race conditions

#### Scenario: Schema deployed via migration pipeline
- **WHEN** a new coordination feature requires database tables
- **THEN** the schema SHALL be defined in a numbered migration file (e.g., `004_memory_tables.sql`)
- **AND** the migration SHALL be deployable via standard Supabase migration tooling or direct `psql` execution
- **AND** the migration SHALL not modify or break existing tables from prior migrations

#### Scenario: Audit log immutability enforced at database level
- **WHEN** any client (including service_role) attempts UPDATE or DELETE on audit_log
- **THEN** the database trigger SHALL raise an exception preventing the modification
- **AND** the audit entry remains unchanged

#### Scenario: Database backend selection via factory
- **WHEN** system starts with `DB_BACKEND=supabase` (default)
- **THEN** factory creates `SupabaseClient` using PostgREST HTTP
- **WHEN** system starts with `DB_BACKEND=postgres`
- **THEN** factory creates `DirectPostgresClient` using asyncpg with connection pooling
- **AND** all service classes operate identically regardless of backend

### Requirement: MCP Server Interface

The system SHALL expose coordination capabilities as native MCP tools for local agents (Claude Code, Codex CLI).

- The server SHALL implement FastMCP protocol
- Connection SHALL be via stdio transport
- All coordination tools SHALL be available as MCP tools
- Memory tools (`remember`, `recall`) SHALL be included for episodic and procedural memory access
- Phase 3 features SHALL expose MCP tools: `check_guardrails`, `get_my_profile`, `query_audit`
- Phase 3 features SHALL expose MCP resources: `memories://recent`, `guardrails://patterns`, `profiles://current`, `audit://recent`

#### Scenario: Local agent connects via MCP
- **WHEN** local agent connects to coordination MCP server
- **THEN** agent discovers available tools: `acquire_lock`, `release_lock`, `check_locks`, `get_work`, `complete_work`, `submit_work`, `write_handoff`, `read_handoff`, `discover_agents`, `register_session`, `heartbeat`, `remember`, `recall`, `check_guardrails`, `get_my_profile`, `query_audit`

#### Scenario: MCP resource access
- **WHEN** agent queries MCP resources
- **THEN** agent can access `locks://current`, `work://pending`, `handoffs://recent`, `memories://recent`, `guardrails://patterns`, `profiles://current`, `audit://recent` resources

#### Scenario: Agent stores memory via MCP
- **WHEN** agent calls `remember(event_type, summary, details?, outcome?, lessons?, tags?)`
- **THEN** system stores episodic memory and returns `{success: true, memory_id: uuid, action: "created"}`
- **AND** if a duplicate memory exists within 1 hour, returns `{success: true, memory_id: uuid, action: "deduplicated"}`

#### Scenario: Agent retrieves memories via MCP
- **WHEN** agent calls `recall(task_description, tags?, event_type?, limit?, min_relevance?)`
- **THEN** system returns relevant memories sorted by relevance score with time-decay weighting

#### Scenario: Agent checks guardrails via MCP
- **WHEN** agent calls `check_guardrails(operation_text, file_paths?)`
- **THEN** system returns `{safe: true}` if no destructive patterns match
- **OR** returns `{safe: false, violations: [{pattern_name, category, matched_text}]}` if patterns match

#### Scenario: Memory recall returns empty results
- **WHEN** agent calls `recall(task_description)` and no relevant memories exist
- **THEN** system returns `{memories: [], relevance_scores: []}` with an empty list
- **AND** the operation does not raise an error

### Requirement: Destructive Operation Guardrails

The system SHALL prevent autonomous agents from executing destructive operations without explicit approval.

- The system SHALL maintain a registry of destructive operation patterns in the `operation_guardrails` database table with a hardcoded fallback registry in code
- Destructive operations SHALL be blocked by default for cloud agents
- Destructive operations MAY be permitted for elevated trust levels with logging
- All guardrail violations SHALL be logged to the audit trail
- Guardrail checks SHALL be integrated into `complete_work()` as a pre-execution hook
- The `GuardrailsService` SHALL follow the established service layer pattern (DI constructor, dataclass results, singleton getter)

#### Scenario: Cloud agent attempts destructive git operation
- **WHEN** cloud agent submits work containing `git push --force`
- **THEN** system detects destructive pattern before execution
- **AND** returns `{success: false, error: "destructive_operation_blocked", operation: "force_push", approval_required: true}`
- **AND** logs violation to `guardrail_violations` and audit trail

#### Scenario: Elevated agent executes monitored operation
- **WHEN** agent with trust_level >= 3 executes operation in guardrail registry
- **AND** operation is in profile's `elevated_operations` allowlist
- **THEN** operation proceeds
- **AND** system logs to audit trail with elevated flag

#### Scenario: Pre-execution check during work completion
- **WHEN** agent calls `complete_work(task_id, success, result)`
- **THEN** system runs guardrail pattern matching against the task result before marking complete
- **AND** blocks completion if destructive patterns are found

#### Scenario: Credential file modification blocked
- **WHEN** any agent (regardless of trust level) attempts to modify files matching `*.env`, `*credentials*`, or `*secrets*`
- **THEN** system blocks the operation
- **AND** logs violation to `guardrail_violations` and audit trail

#### Scenario: Multiple guardrail patterns match
- **WHEN** an operation matches multiple destructive patterns simultaneously
- **THEN** system returns all violations in the response list
- **AND** the operation is blocked if any violation has `blocked: true`

#### Scenario: Database unavailable for pattern loading
- **WHEN** guardrails service cannot reach the database to load patterns
- **THEN** system falls back to hardcoded pattern registry in code
- **AND** all pattern categories remain enforced

### Requirement: Audit Trail

The system SHALL maintain comprehensive audit logs for all agent operations.

- All coordination operations SHALL be logged with timestamp, agent_id, agent_type, operation, parameters, result, and duration_ms
- Guardrail violations SHALL be logged with full context
- Network access attempts SHALL be logged
- Audit logs SHALL be immutable (append-only) enforced by database trigger
- Logs SHALL be retained for configurable period (default 90 days)
- Audit logging SHALL be asynchronous (fire-and-forget) to avoid blocking coordination operations
- The `AuditService` SHALL follow the established service layer pattern (DI constructor, dataclass results, singleton getter)

#### Scenario: Operation audit logging
- **WHEN** agent performs any coordination operation (lock, work queue, handoff, memory, discovery)
- **THEN** system logs `{timestamp, agent_id, agent_type, operation, parameters, result, duration_ms}`
- **AND** the insert does not block the caller (async)

#### Scenario: Guardrail violation logging
- **WHEN** guardrail blocks an operation
- **THEN** system logs `{timestamp, agent_id, operation, pattern_matched, context, blocked: true}`

#### Scenario: Audit log query
- **WHEN** administrator queries audit logs with filters (agent_id, operation, time_range)
- **THEN** system returns matching entries without modification

#### Scenario: Audit log immutability
- **WHEN** any attempt is made to UPDATE or DELETE an audit log entry
- **THEN** the database trigger raises an exception
- **AND** the entry remains unchanged

### Requirement: Agent Profiles

The system SHALL support configurable agent profiles that define capabilities, trust levels, and operational constraints.

- Profiles SHALL specify allowed operations and tools
- Profiles SHALL define trust level (0-4)
- Profiles SHALL configure resource limits (max files, execution time, API calls)
- Profiles SHALL be assignable per agent_id or agent_type
- Default profiles SHALL exist for each agent type, seeded via database migration
- Profile checks SHALL be integrated into MCP tool calls and HTTP API requests
- The `ProfilesService` SHALL follow the established service layer pattern (DI constructor, dataclass results, singleton getter)

#### Scenario: Agent with restricted profile
- **WHEN** agent with "reviewer" profile attempts file modification via `acquire_lock()`
- **THEN** system checks if "write" is in profile's allowed_operations
- **AND** rejects operation if not permitted with `{success: false, error: "operation_not_permitted"}`

#### Scenario: Resource limit enforcement
- **WHEN** agent exceeds profile's max_file_modifications limit
- **THEN** system blocks further modifications
- **AND** returns `{success: false, error: "resource_limit_exceeded", limit: "max_file_modifications"}`

#### Scenario: Trust level verification
- **WHEN** agent attempts operation requiring trust_level >= 3
- **AND** agent's profile has trust_level < 3
- **THEN** system rejects with `{success: false, error: "insufficient_trust_level"}`

#### Scenario: Default profile assignment
- **WHEN** agent connects without an explicit profile assignment
- **THEN** system assigns a default profile based on agent_type
- **AND** the default profile is loaded from preconfigured profiles seeded in database

### Requirement: Verification Gateway

The system SHALL route agent-generated changes to matching verification tiers based on configurable file glob policies.

- Policies SHALL match files by glob patterns
- Each tier SHALL have a configured executor: inline (Tier 0), GitHub Actions (Tier 1), Local NTM or E2B sandbox (Tier 2), manual review (Tier 4)
- Verification results SHALL be stored in the `verification_results` database table (via main migration pipeline)
- Tier 4 (manual review) SHALL route changesets to the `approval_queue` table
- The verification gateway SHALL integrate with guardrails for pre-dispatch safety checks

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
- **AND** approval/denial is processed via `approve_changeset()` database function

#### Scenario: GitHub webhook processing
- **WHEN** GitHub push event received at `/webhook/github`
- **THEN** system identifies affected files and routes to matching verification tier
- **AND** runs guardrail pre-check before dispatching to executors

### Requirement: Cedar Policy Engine (Optional Enhancement)

The system SHALL support an optional Cedar-based policy engine as an alternative to the native profile and network policy enforcement modules.

- Cedar SHALL be selectable via `POLICY_ENGINE=cedar` environment variable (default: `native`)
- When active, Cedar SHALL replace `ProfilesService` and `NetworkPolicyService` for authorization decisions
- Cedar SHALL NOT replace the regex-based guardrails engine (content inspection is separate from authorization)
- Cedar SHALL NOT replace the audit trail (logging is separate from authorization)
- Cedar policies SHALL be stored in the database and cached with configurable TTL
- Cedar schema SHALL define entity types mapping to the coordination model: `Agent`, `AgentType`, `Action`, `File`, `Domain`, `Task`
- All Cedar authorization decisions SHALL be logged to the audit trail
- The system SHALL validate Cedar policies against the schema before storing
- Default Cedar policies SHALL produce identical authorization decisions to the native engine for all preconfigured profiles
- `cedarpy` SHALL be an optional dependency (only required when `POLICY_ENGINE=cedar`)
- The `CedarPolicyEngine` SHALL follow the established service layer pattern (DI constructor, dataclass results, singleton getter)

#### Scenario: Agent operation authorized via Cedar
- **WHEN** `POLICY_ENGINE=cedar` and agent calls any coordination operation
- **THEN** system evaluates Cedar policies with `is_authorized(principal=Agent, action=Operation, resource=Target, context={trust_level, ...})`
- **AND** permits or denies based on Cedar's default-deny + forbid-overrides-permit semantics
- **AND** logs the decision to audit trail

#### Scenario: Network access checked via Cedar
- **WHEN** `POLICY_ENGINE=cedar` and agent makes network request to a domain
- **THEN** system evaluates `is_authorized(principal=Agent, action=Action::"network_access", resource=Domain::domain)`
- **AND** permits only if an explicit `permit` policy exists for the domain (Cedar is default-deny)

#### Scenario: Cedar policy validation on write
- **WHEN** administrator adds or updates a Cedar policy
- **THEN** system validates policy text against the Cedar schema using `validate_policies()`
- **AND** rejects policies that contain schema errors

#### Scenario: Native engine fallback
- **WHEN** `POLICY_ENGINE=native` (default)
- **THEN** system uses `ProfilesService` and `NetworkPolicyService` for authorization
- **AND** Cedar module is not loaded and `cedarpy` dependency is not required

#### Scenario: Cedar produces identical results to native engine
- **WHEN** default Cedar policies are loaded
- **THEN** Cedar authorization decisions match native engine decisions for all preconfigured agent profiles
- **AND** no behavioral difference exists for agents


### Requirement: HTTP API Interface

The system SHALL provide HTTP API for cloud agents that cannot use MCP protocol.

- Authentication SHALL use API key via `X-API-Key` header
- All coordination capabilities SHALL have equivalent HTTP endpoints
- API key SHALL map to an agent profile for trust level and operation enforcement
- Phase 3 features (guardrails, profiles, audit) SHALL have corresponding HTTP endpoints

#### Scenario: Cloud agent acquires lock via HTTP
- **WHEN** cloud agent sends `POST /locks/acquire` with valid API key
- **THEN** system processes lock request and returns JSON response
- **AND** profile checks are applied based on the API key's associated profile

#### Scenario: Invalid API key
- **WHEN** request is made without valid `X-API-Key` header
- **THEN** system returns 401 Unauthorized

#### Scenario: Cloud agent profile enforcement via HTTP
- **WHEN** cloud agent sends request and API key maps to a restricted profile
- **THEN** system validates operation against profile's allowed_operations and trust_level
- **AND** rejects disallowed operations with 403 Forbidden

### Requirement: Network Access Policies

The system SHALL enforce per-profile network access policies controlling which domains agents may access.

- Policies SHALL support domain allowlists and denylists per agent profile
- Policies SHALL support wildcard patterns (e.g., `*.example.com` matches `api.example.com`)
- Default policy SHALL be deny for cloud agents and allow for local agents
- All network access decisions SHALL be logged to `network_access_log` and the audit trail
- The `NetworkPolicyService` SHALL follow the established service layer pattern (DI constructor, dataclass results, singleton getter)

#### Scenario: Agent accesses allowed domain
- **WHEN** agent requests access to a domain in the profile's allowlist
- **THEN** system returns `{allowed: true, domain, reason: "allowlist_match"}`
- **AND** logs the decision to `network_access_log`

#### Scenario: Agent accesses denied domain
- **WHEN** agent requests access to a domain in the profile's denylist
- **THEN** system returns `{allowed: false, domain, reason: "denylist_match"}`
- **AND** logs the blocked attempt to `network_access_log` and audit trail

#### Scenario: Wildcard domain matching
- **WHEN** agent requests access to `api.example.com` and profile allowlist contains `*.example.com`
- **THEN** system matches the wildcard pattern and returns `{allowed: true}`
- **WHEN** agent requests access to `example.com` and profile allowlist contains only `*.example.com`
- **THEN** system does NOT match (wildcard requires subdomain) and applies default policy

#### Scenario: Default policy for unspecified domains
- **WHEN** cloud agent requests access to a domain not in any allowlist or denylist
- **THEN** system applies default deny and returns `{allowed: false, reason: "default_deny"}`
- **WHEN** local agent requests access to a domain not in any allowlist or denylist
- **THEN** system applies default allow and returns `{allowed: true, reason: "default_allow"}`

### Requirement: GitHub-Mediated Coordination

The system SHALL support coordination via GitHub issue labels, branch naming conventions, and webhooks as a fallback for agents that cannot use MCP or HTTP API directly.

- Issue labels following the pattern `locked:<file_path>` SHALL create corresponding file locks
- Branch names following the pattern `agent/{agent_id}/{task_id}` SHALL associate branches with agent sessions
- Files modified on an agent branch SHALL have implicit file locks
- Push webhooks SHALL sync GitHub state to the coordination database
- Webhook-submitted tasks SHALL be subject to guardrail checks before processing
- The `GitHubCoordinationService` SHALL follow the established service layer pattern (DI constructor, singleton getter)

#### Scenario: Lock via GitHub issue label
- **WHEN** GitHub issue receives a label `locked:src/config.py`
- **THEN** system creates a `file_locks` entry for `src/config.py` with the issue author as the lock holder

#### Scenario: Branch-based agent tracking
- **WHEN** a branch named `agent/claude-1/task-42` is pushed
- **THEN** system associates the branch with agent `claude-1` and task `task-42`
- **AND** files modified on the branch have implicit file locks

#### Scenario: Push webhook triggers verification
- **WHEN** GitHub push event is received at the webhook endpoint
- **THEN** system identifies affected files from the push diff
- **AND** runs guardrail pre-check on the changeset before routing to verification

#### Scenario: Webhook-submitted destructive operation blocked
- **WHEN** a push webhook contains a changeset with destructive patterns (e.g., force-push, credential file modifications)
- **THEN** system blocks verification routing and logs the guardrail violation
- **AND** returns error status to the webhook caller
