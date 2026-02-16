## Task Dependencies

```
Task 0 (DB Factory) ─── foundational, no dependencies
├── Task 1a (Migrations 004-006) ─── parallel, independent
├── Task 1b (Migrations 007-009) ─── sequential: 007 → 008, 009
├── Task 7 (GitHub Coordination) ─── isolated, no file conflicts
└── Task 8 (Verification Executors) ─── isolated in verification_gateway/

Task 2 (Audit) ─── depends on: Task 0, Task 1b (008_audit_log.sql)
Task 3 (Memory) ─── depends on: Task 0, Task 1a (004_memory_tables.sql)
Task 4 (Profiles) ─── depends on: Task 0, Task 1b (007_agent_profiles.sql)
Task 5 (Guardrails) ─── depends on: Task 0, Task 1a (006), Task 4 (trust levels)
Task 6 (Network) ─── depends on: Task 0, Task 1b (009), Task 4 (per-profile policies)
Task 9 (Evaluation) ─── depends on: Tasks 2-8 (all features)
Task 10 (Audit Hooks) ─── depends on: Task 2, Tasks 3-7 (embedded in feature tasks)
Task 11 (Documentation) ─── depends on: all feature tasks
Task 12 (Cedar) ─── depends on: Tasks 4, 6 (replaces their enforcement)
Task 13 (Validation) ─── depends on: all tasks
```

**Shared file hotspots** (tasks that modify the same files):
- `src/config.py`: Tasks 0, 2, 3, 4, 5, 6, 12
- `tests/conftest.py`: Tasks 2, 3, 4, 5, 6
- `src/coordination_mcp.py`: Tasks 3, 4, 5
- `src/work_queue.py`: Tasks 4, 5, 10

**Note**: Audit integration hooks (Task 10) were embedded directly in each feature task (Tasks 2-8) during implementation rather than as a separate cross-cutting pass.

---

## 0. Database Client Factory Pattern — Foundational change before new modules

- [x] 0.1 Define `DatabaseClient` protocol in `src/db.py` with methods: `rpc`, `query`, `insert`, `update`, `delete`, `close`
- [x] 0.2 Refactor existing `SupabaseClient` to implement `DatabaseClient` protocol (no behavior change)
- [x] 0.3 Add `DatabaseConfig` and `PostgresConfig` dataclasses to `src/config.py`
- [x] 0.4 Implement `create_db_client(config)` factory function in `src/db.py`
- [x] 0.5 Implement `DirectPostgresClient` using asyncpg:
  - `rpc()` → `SELECT * FROM function_name(params)` via asyncpg
  - `query()` → translate PostgREST filter syntax to SQL WHERE clauses
  - `insert()` → `INSERT INTO ... RETURNING *`
  - `update()` → `UPDATE ... SET ... WHERE ... RETURNING *`
  - `delete()` → `DELETE FROM ... WHERE ...`
  - Connection pooling via `asyncpg.create_pool()`
- [x] 0.6 Update `get_db()` to call `create_db_client()` instead of directly instantiating `SupabaseClient`
- [x] 0.7 Update all service class type hints: `db: SupabaseClient | None` → `db: DatabaseClient | None`
- [x] 0.8 Add `asyncpg` to `pyproject.toml` as optional dependency (`[postgres]` extra)
- [x] 0.9 Create `tests/test_db_factory.py`:
  - Test factory returns `SupabaseClient` when `DB_BACKEND=supabase`
  - Test factory returns `DirectPostgresClient` when `DB_BACKEND=postgres`
  - Test `DirectPostgresClient` RPC translation
  - Test `DirectPostgresClient` query filter translation
- [x] 0.10 Verify all existing tests pass unchanged (SupabaseClient is still the default)

## 1. Schema Integration (Phase 2-3 Database) — Must complete before Python modules

- [x] 1.1 Create migration `004_memory_tables.sql`:
  - Tables: `memory_episodic`, `memory_working`, `memory_procedural`
  - Functions: `store_episodic_memory()`, `get_relevant_memories()` (adapt from `verification_gateway/supabase_memory_schema.sql`)
  - RLS: anon read, service_role write (match existing `001_core_schema.sql` pattern)
  - Indexes: GIN on tags arrays, B-tree on agent_id + event_type
- [x] 1.2 Create migration `005_verification_tables.sql`:
  - Tables: `changesets`, `verification_results`, `verification_policies`, `approval_queue`
  - Enums: `verification_tier`, `verification_executor`, `verification_status`
  - Views: `changeset_status`, `agent_performance`, `tier_metrics`
  - Functions: `get_pending_approvals()`, `approve_changeset()`
  - Adapt from `verification_gateway/supabase_schema.sql`, resolve any FK conflicts with `001` tables
- [x] 1.3 Create migration `006_guardrails_tables.sql`:
  - Tables: `operation_guardrails` (pattern registry), `guardrail_violations` (blocked attempts log)
  - Seed default destructive patterns via INSERT (git force-push, rm -rf, credential modify, etc.)
  - RLS: anon read, service_role write
- [x] 1.4 Create migration `007_agent_profiles.sql`:
  - Tables: `agent_profiles`, `agent_profile_assignments`
  - Seed preconfigured profiles from spec: `claude-code-cli`, `claude-code-web-reviewer`, `claude-code-web-implementer`, `codex-cloud-worker`, `strands-orchestrator`
  - Functions: `get_agent_profile(p_agent_id, p_agent_type)` with fallback to default by agent_type
- [x] 1.5 Create migration `008_audit_log.sql`:
  - Table: `audit_log` (timestamp, agent_id, agent_type, operation, parameters JSONB, result JSONB, duration_ms)
  - Immutability trigger: `BEFORE UPDATE OR DELETE` → `RAISE EXCEPTION`
  - RLS: INSERT for service_role, SELECT for all, no UPDATE/DELETE
  - Index: B-tree on (timestamp DESC), B-tree on (agent_id, operation)
- [x] 1.6 Create migration `009_network_policies.sql`:
  - Tables: `network_policies` (per-profile domain allowlists/denylists), `network_access_log`
  - FK: `network_policies.profile_id` → `agent_profiles.id`
  - Functions: `is_domain_allowed(p_agent_id, p_domain)`
- [x] 1.7 Add migration compatibility tests:
  - Verify 004-009 apply cleanly on top of 000-003
  - Verify 000-003 tables are unmodified after applying 004-009
  - Test migration ordering (007 before 008/009)

## 2. Audit Trail (Phase 3) — Implement early since other modules log to it

**Depends on**: Task 0 (DatabaseClient protocol), Task 1b (migration 008_audit_log.sql)

- [x] 2.1 Create `src/audit.py` following the `LockService` pattern:
  - `AuditEntry` dataclass with `from_dict()` factory
  - `AuditResult` dataclass (success, entry_id)
  - `AuditService` class with DI constructor, `@property db`, lazy init
  - `get_audit_service()` singleton getter
- [x] 2.2 Implement `async log_operation(agent_id, agent_type, operation, parameters, result, duration_ms)` — async fire-and-forget insert
- [x] 2.3 Implement `async query(agent_id?, operation?, time_range?, limit?)` — filtered audit retrieval
- [x] 2.4 Add `AuditConfig` dataclass to `src/config.py` (retention_days, async_logging env vars)
- [x] 2.5 Extend `tests/conftest.py` with audit response fixtures
- [x] 2.6 Create `tests/test_audit.py` with respx-mocked unit tests:
  - Test log_operation success/failure
  - Test query with filters
  - Test async behavior (fire-and-forget doesn't block caller)

## 3. Memory Service & MCP Tools (Phase 2)

**Depends on**: Task 0 (DatabaseClient protocol), Task 1a (migration 004_memory_tables.sql)

- [x] 3.1 Create `src/memory.py` following the service layer pattern:
  - `EpisodicMemory`, `ProceduralSkill` dataclasses with `from_dict()`
  - `MemoryResult` dataclass (success, memory_id, action: 'created'|'deduplicated')
  - `RecallResult` dataclass (memories: list, relevance scores)
  - `MemoryService` class with DI constructor
  - `get_memory_service()` singleton getter
- [x] 3.2 Implement `async remember(event_type, summary, details?, outcome?, lessons?, tags?)`:
  - Call `store_episodic_memory()` RPC
  - Return `{success, memory_id, action}` where action indicates if deduplicated
- [x] 3.3 Implement `async recall(task_description, tags?, event_type?, limit?, min_relevance?)`:
  - Call `get_relevant_memories()` RPC
  - Return memories sorted by relevance with time-decay scoring
- [x] 3.4 Add `remember` and `recall` tools to `coordination_mcp.py` following existing tool pattern
- [x] 3.5 Add `memories://recent` MCP resource
- [x] 3.6 Extend `tests/conftest.py` with memory response fixtures
- [x] 3.7 Create `tests/test_memory.py` with respx-mocked unit tests:
  - Test remember success, deduplication, error handling
  - Test recall with tag filtering, empty results, relevance ordering
  - Log to audit trail on memory operations

## 4. Agent Profiles (Phase 3)

**Depends on**: Task 0 (DatabaseClient protocol), Task 1b (migration 007_agent_profiles.sql)

- [x] 4.1 Create `src/profiles.py` following the service layer pattern:
  - `AgentProfile` dataclass (trust_level, allowed_operations, blocked_operations, resource_limits, network_policy)
  - `ProfileResult` dataclass (success, profile, reason)
  - `ProfilesService` class with DI constructor
  - `get_profiles_service()` singleton getter
- [x] 4.2 Implement `async get_profile(agent_id, agent_type)`:
  - Query `agent_profiles` + `agent_profile_assignments` tables
  - Fall back to default profile by agent_type if no explicit assignment
  - Cache profiles in-memory with configurable TTL
- [x] 4.3 Implement `async check_operation(agent_id, operation, context?)`:
  - Verify operation is in `allowed_operations` and not in `blocked_operations`
  - Verify trust_level meets minimum for operation
  - Check resource limits (file modification count, execution time)
  - Return `{allowed: bool, reason?: str}`
- [x] 4.4 Add `ProfilesConfig` dataclass to `src/config.py`
- [x] 4.5 Add `get_my_profile` MCP tool and `profiles://current` resource to `coordination_mcp.py`
- [x] 4.6 Integrate profile checks into existing tools:
  - `acquire_lock()`: check "write" permission, credential file protection
  - `get_work()` / `complete_work()`: check agent is allowed to claim/complete tasks
  - `submit_work()`: check agent is allowed to create tasks
- [x] 4.7 Integrate profile checks into HTTP API (`coordination_api.py`): validate API key → profile → operation on each request
- [x] 4.8 Extend `tests/conftest.py` with profile fixtures
- [x] 4.9 Create `tests/test_profiles.py`:
  - Test profile lookup, default fallback, caching
  - Test operation allow/deny for each trust level
  - Test resource limit enforcement
  - Test integration with lock acquisition and work queue

## 5. Guardrails Engine (Phase 3)

**Depends on**: Task 0 (DatabaseClient protocol), Task 1a (migration 006_guardrails_tables.sql), Task 4 (trust levels from profiles)

- [x] 5.1 Create `src/guardrails.py` following the service layer pattern:
  - `GuardrailPattern` dataclass (name, category, regex_pattern, severity, requires_approval)
  - `GuardrailViolation` dataclass (pattern_name, operation, matched_text, blocked, context)
  - `GuardrailResult` dataclass (safe: bool, violations: list)
  - `GuardrailsService` class with DI constructor
  - `get_guardrails_service()` singleton getter
- [x] 5.2 Implement hardcoded fallback pattern registry for:
  - Git force operations: `git push --force`, `git reset --hard`, `git clean -f`
  - Branch deletion: `git branch -D`, `git push origin --delete`
  - Mass file deletion: `rm -rf`, `find -delete`, unscoped `DELETE FROM`
  - Credential files: patterns matching `*.env`, `*credentials*`, `*secrets*`
  - Production deployment: deploy commands, infrastructure changes
  - Database migrations: schema changes, data migrations
- [x] 5.3 Implement `async check_operation(operation_text, file_paths?, agent_profile?)`:
  - Load patterns from database (with cache TTL) + code fallback
  - Run regex matching against operation text and file paths
  - For elevated trust agents (trust_level >= 3), log but don't block (except credential files)
  - Log violations to `guardrail_violations` table and audit trail
- [x] 5.4 Add pre-execution hook to `complete_work()` in work_queue service:
  - Check task result for destructive patterns before marking complete
  - If violation found: block completion, return `{success: false, error: "destructive_operation_blocked"}`
- [x] 5.5 Add `GuardrailsConfig` dataclass to `src/config.py`
- [x] 5.6 Add `check_guardrails` MCP tool and `guardrails://patterns` resource to `coordination_mcp.py`
- [x] 5.7 Extend `tests/conftest.py` with guardrail fixtures
- [x] 5.8 Create `tests/test_guardrails.py`:
  - Test each destructive pattern category (git, deletion, credentials, etc.)
  - Test trust-level-based allow/block behavior
  - Test DB pattern loading + code fallback when DB unavailable
  - Test integration with complete_work() pre-execution hook
  - Test violation logging to audit trail

## 6. Network Access Policies (Phase 3)

**Depends on**: Task 0 (DatabaseClient protocol), Task 1b (migration 009_network_policies.sql), Task 4 (per-profile policies)

- [x] 6.1 Create `src/network_policies.py` following the service layer pattern:
  - `NetworkPolicy` dataclass (profile_id, allowed_domains, denied_domains, default_action)
  - `AccessDecision` dataclass (allowed: bool, domain, reason, logged: bool)
  - `NetworkPolicyService` class with DI constructor
  - `get_network_policy_service()` singleton getter
- [x] 6.2 Implement `async check_domain(agent_id, domain)`:
  - Load per-profile policy (from `network_policies` table)
  - Check against allowlist/denylist with wildcard support (e.g., `*.example.com`)
  - Default deny for cloud agents, default allow for local agents
  - Log decision to `network_access_log` and audit trail
- [x] 6.3 Add `NetworkPolicyConfig` dataclass to `src/config.py`
- [x] 6.4 Integrate with agent profiles (per-profile network policies)
- [x] 6.5 Create `tests/test_network_policies.py`:
  - Test allowlist/denylist matching with wildcards
  - Test default deny/allow based on agent type
  - Test logging to network_access_log

## 7. GitHub-Mediated Coordination (Phase 2)

**Depends on**: Task 0 (DatabaseClient protocol). Isolated — no shared files with other feature tasks.

- [x] 7.1 Create `src/github_coordination.py` following the service layer pattern:
  - `GitHubCoordinationService` class
  - `get_github_coordination_service()` singleton getter
- [x] 7.2 Implement issue label lock signaling:
  - Parse labels like `locked:path/to/file` from GitHub webhooks
  - Create corresponding `file_locks` entry in coordination database
- [x] 7.3 Implement branch naming convention parser:
  - Pattern: `agent/{agent_id}/{task_id}`
  - Associate branch with agent session
  - Implicit file locks for files modified on branch
- [x] 7.4 Add webhook handler that syncs GitHub state to coordination database
- [x] 7.5 Integrate guardrail checks into webhook-submitted tasks
- [x] 7.6 Create `tests/test_github_coordination.py`:
  - Test label parsing and lock creation
  - Test branch naming convention
  - Test webhook state sync

## 8. Verification Executor Completion (Phase 3)

**Depends on**: Task 0 (DatabaseClient protocol), Task 1b (migration 005_verification_tables.sql). Isolated in `verification_gateway/` directory.

- [x] 8.1 Complete GitHub Actions trigger in `gateway.py`:
  - Implement `_trigger_github_actions()` with GitHub API workflow dispatch
  - Handle webhook callback for result collection
- [x] 8.2 Complete NTM dispatch in `gateway.py`:
  - Implement `_dispatch_to_ntm()` with task submission
- [x] 8.3 Complete E2B sandbox execution in `gateway.py`:
  - Implement `_run_in_e2b()` with sandbox creation and code execution
- [x] 8.4 Integrate approval queue routing for Tier 4 (manual review):
  - Route changesets matching `requires_approval` policies to `approval_queue` table
  - Implement approval/denial flow using `approve_changeset()` function
- [x] 8.5 Write integration tests for each executor type

## 9. Evaluation Framework Extension (Phase 3 Measurement)

**Depends on**: Tasks 2-8 (all feature modules must exist for safety metrics)

- [x] 9.1 Extend `AblationFlags` in `evaluation/config.py` with: `guardrails`, `profiles`, `audit`, `network_policies` boolean toggles
- [x] 9.2 Add `SafetyMetrics` dataclass to `evaluation/metrics.py`:
  - `guardrail_checks`, `guardrail_blocks`, `guardrail_block_rate`
  - `profile_enforcement_checks`, `profile_violations_blocked`
  - `audit_entries_written`, `audit_write_latency_ms`
  - `network_requests_blocked`
- [x] 9.3 Extend `CoordinationMetrics` with safety-related `coord_ops` tracking
- [x] 9.4 Create evaluation tasks for Phase 3 features:
  - `tier1/destructive-git-operation.yaml` — guardrails should block
  - `tier1/credential-file-access.yaml` — guardrails should block
  - `tier2/trust-level-enforcement.yaml` — profile check for elevated ops
  - `tier2/resource-limit-enforcement.yaml` — profile limit exceeded
  - `tier3/audit-completeness.yaml` — verify all ops logged across multi-step task
- [x] 9.5 Update `evaluation/reports/generator.py` to include safety metrics in output

## 10. Audit Integration Hooks (Cross-cutting)

**Note**: Audit logging was embedded directly into each feature module during implementation (Tasks 2-8) rather than applied as a separate cross-cutting pass. All hooks are already in place.

- [x] 10.1 Add audit logging to `src/locks.py`: log acquire_lock, release_lock, extend_lock
- [x] 10.2 Add audit logging to `src/work_queue.py`: log claim, complete, submit
- [x] 10.3 Add audit logging to `src/handoffs.py`: log write_handoff, read_handoff
- [x] 10.4 Add audit logging to `src/discovery.py`: log register, discover, heartbeat, cleanup
- [x] 10.5 Add audit logging to `src/memory.py`: log remember, recall
- [x] 10.6 Add audit logging to `src/guardrails.py`: log all violations (already partially in 5.3)
- [x] 10.7 Add audit logging to `src/profiles.py`: log operation denials

## 11. Documentation & Status Updates

- [x] 11.1 Update `docs/agent-coordinator.md`:
  - Change Phase 2 status from "Specified" to "Implemented" (HTTP API, memory, verification gateway)
  - Change Phase 3 status from "Specified" to "Implemented" (guardrails, profiles, audit, network policies)
  - Update database tables section with all Phase 2-3 tables
  - Update MCP tools table with new tools (remember, recall, check_guardrails, get_my_profile, query_audit)
  - Update architecture diagram to show Phase 2-3 components
- [ ] 11.2 Update `openspec/specs/agent-coordinator/spec.md`:
  - Update Implementation Status table
  - Update Database Tables section: move Phase 2+ and Phase 3+ tables to "Implemented"
- [x] 11.3 Update `agent-coordinator/README.md`:
  - Update features section beyond "Phase 1 MVP" to include all implemented features
  - Add Phase 2-3 MCP tools to the tools table
  - Add Phase 2-3 MCP resources to the resources table
  - Update file structure to include new modules (guardrails.py, profiles.py, audit.py, memory.py, network_policies.py, github_coordination.py)
  - Update architecture diagram to show HTTP API, verification gateway, and safety layers
  - Add setup instructions for Phase 2-3 features (new migrations, new env vars)
  - Update "Future Phases" section (Phase 2-3 now implemented, only Phase 4 remains future)
  - Add configuration reference for new environment variables
- [x] 11.4 Update `agent-coordinator/.env.example` with new environment variables

## 12. Cedar Policy Engine (Optional Enhancement — `POLICY_ENGINE=cedar`)

**Depends on**: Tasks 4 and 6 must be complete (Cedar replaces their enforcement logic)

- [x] 12.1 Add `cedarpy` as optional dependency to `pyproject.toml` under `[cedar]` extra
- [x] 12.2 Add `PolicyEngineConfig` dataclass to `src/config.py`:
  - `engine: str = "native"` — `"native"` (profiles.py + network_policies.py) or `"cedar"` (cedarpy)
  - `policy_cache_ttl_seconds: int = 300` — cache TTL for loaded policies
  - `enable_code_fallback: bool = True` — fallback to hardcoded policies if DB unavailable
  - `schema_path: str = ""` — optional path to `.cedarschema` file
  - Env: `POLICY_ENGINE`, `POLICY_CACHE_TTL`, `POLICY_CODE_FALLBACK`
- [x] 12.3 Define Cedar schema (`cedar/schema.cedarschema`):
  - Entity types: `Agent` (attrs: trust_level, max_file_modifications, allowed_operations), `AgentType`, `Action`, `File`, `Domain`, `Task`
  - Action groups: `read_actions` (check_locks, get_work, recall, discover_agents), `write_actions` (acquire_lock, complete_work, submit_work, remember), `admin_actions` (force_push, delete_branch)
- [x] 12.4 Create default Cedar policies (`cedar/default_policies.cedar`):
  - Permit read operations for all agents
  - Permit write operations for trust_level >= 2
  - Forbid admin operations unless trust_level >= 3
  - Forbid all actions for trust_level 0 (suspended agents)
  - Permit network access for `github.com`, `registry.npmjs.org`, `pypi.org`
  - Deny all other network access (implicit Cedar default-deny)
- [x] 12.5 Create migration `010_cedar_policies.sql`:
  - Table: `cedar_policies` (id, name, policy_text, priority, enabled, created_at, updated_at)
  - Table: `cedar_entities` (id, entity_type, entity_id, attributes JSONB, parents JSONB)
  - Seed default policies from `cedar/default_policies.cedar`
  - RLS: service_role read/write, anon read-only for policies
- [x] 12.6 Create `src/policy_engine.py` following the service layer pattern:
  - `PolicyDecision` dataclass (allowed, reason, policy_id) with `from_cedar()` classmethod
  - `CedarPolicyEngine` class with DI constructor, `@property db`, lazy init
  - `get_policy_engine()` singleton getter (returns `CedarPolicyEngine` or `NativePolicyEngine` based on config)
  - `NativePolicyEngine` wrapper that delegates to `ProfilesService` + `NetworkPolicyService` for backward compatibility
- [x] 12.7 Implement `CedarPolicyEngine.check_operation(agent_id, agent_type, operation, resource, context?)`:
  - Load policies from database (cached with TTL) + code fallback
  - Build Cedar entities from agent profiles table
  - Call `cedarpy.is_authorized()` with PARC request
  - Return `PolicyDecision.from_cedar(result)`
  - Log decision to audit trail
- [x] 12.8 Implement `CedarPolicyEngine.check_network_access(agent_id, domain)`:
  - Maps to `is_authorized(principal=Agent, action=Action::"network_access", resource=Domain::domain)`
  - Replaces `NetworkPolicyService.check_domain()` when Cedar is active
- [x] 12.9 Integrate `get_policy_engine()` into enforcement points:
  - `coordination_mcp.py`: replace direct ProfilesService calls with policy engine dispatch
  - `coordination_api.py`: replace direct ProfilesService calls with policy engine dispatch
  - Network check sites: replace NetworkPolicyService calls with policy engine dispatch
- [x] 12.10 Add Cedar policy validation on write:
  - Call `cedarpy.validate_policies(policy_text, schema)` before storing to database
  - Reject policies that fail schema validation
- [x] 12.11 Add `cedar-admin` MCP tools (only when `POLICY_ENGINE=cedar`):
  - `list_policies` — list all active Cedar policies
  - `validate_policy` — validate Cedar policy text against schema
- [x] 12.12 Create `tests/test_policy_engine.py`:
  - Test `CedarPolicyEngine` with sample policies and entities
  - Test trust level enforcement (forbid for trust < 2)
  - Test network domain allow/deny via Cedar
  - Test policy caching and TTL expiry
  - Test fallback to code policies when DB unavailable
  - Test `NativePolicyEngine` delegates correctly to profiles + network services
  - Test config dispatch: `POLICY_ENGINE=native` vs `POLICY_ENGINE=cedar`
- [x] 12.13 Update `.env.example` with `POLICY_ENGINE=native` and Cedar-related env vars

## 13. Integration & Validation

- [x] 13.1 Run full test suite: `pytest` — 278 passed, 0 failures
- [x] 13.2 Run type checking: `mypy --strict src/` — zero errors (17 source files)
- [x] 13.3 Run linting: `ruff check src/ tests/` — zero errors
- [x] 13.4 Verify all existing Phase 1 tests still pass unchanged
- [x] 13.5 Verify backward compatibility: Phase 1 MCP tool calls succeed after Phase 3 deployment
- [x] 13.6 Verify new module code coverage >90%
- [x] 13.7 Verify Cedar engine produces identical decisions to native engine for all default profile scenarios
