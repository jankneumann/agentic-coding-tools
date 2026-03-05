## Context

The agent-coordinator has significant Phase 2-3 code in the `verification_gateway/` directory that exists independently of the main `src/` and `supabase/migrations/` structure. Additionally, several specified features (guardrails, profiles, audit, network policies, GitHub coordination) have no implementation at all. This design document addresses how to integrate existing code and build missing features while adhering to established architectural patterns.

## Goals / Non-Goals

- **Goals:**
  - Integrate verification_gateway SQL schemas into the main migration pipeline
  - Implement all missing Phase 2-3 features specified in the agent-coordinator spec
  - Maintain backward compatibility with Phase 1 deployments
  - Follow existing architectural patterns (async services, Supabase RPC, dataclass results)
  - Extend the evaluation framework to measure Phase 3 safety feature effectiveness
  - Update README.md and all documentation to reflect complete system state

- **Non-Goals:**
  - Strands SDK / AgentCore integration (deferred to separate proposal)
  - Rewriting existing verification_gateway Python code (refactoring is separate)
  - Adding new requirements beyond what's already specified
  - Migrating off PostgreSQL (all backends must be PostgreSQL-compatible)

## Decisions

### 1. Schema Integration Strategy

- **Decision:** Create new numbered migrations (004-009) that extract and adapt SQL from `verification_gateway/*.sql` files. Do NOT modify existing migrations 000-003.
- **Alternatives:** (a) Copy SQL files directly into migrations/ — rejected because they need adaptation for compatibility with existing tables. (b) Keep schemas separate — rejected because it prevents standard deployment.
- **Rationale:** Numbered migrations ensure ordering, allow rollback, and work with standard Supabase migration tooling.

#### Migration Dependency DAG

```
000 (bootstrap: roles, auth, realtime)
  └─> 001 (core: file_locks, work_queue, agent_sessions)
       ├─> 002 (handoff_documents)
       ├─> 003 (agent_discovery: extends agent_sessions)
       ├─> 004 (memory: memory_episodic, memory_working, memory_procedural + functions)
       ├─> 005 (verification: changesets, verification_results, verification_policies, approval_queue + views + functions)
       ├─> 006 (guardrails: operation_guardrails, guardrail_violations)
       ├─> 007 (profiles: agent_profiles, agent_profile_assignments)  [referenced by 008, 009]
       ├─> 008 (audit_log: immutable trigger, retention policy)       [depends on 007 for agent context]
       └─> 009 (network: network_policies, network_access_log)        [depends on 007 for per-profile policies]
```

Migrations 004-006 have no inter-dependencies and can be developed in parallel. Migrations 007-009 have a dependency chain (profiles before audit/network). All are additive CREATE TABLE statements — no ALTER on 000-003 tables.

### 2. Database Client Factory Pattern

- **Decision:** Introduce a `DatabaseClient` protocol (Python `Protocol` class) that defines the interface currently implemented by `SupabaseClient` (`rpc`, `query`, `insert`, `update`, `delete`, `close`). A factory function `create_db_client(config)` returns the appropriate implementation based on configuration. The existing `SupabaseClient` (PostgREST HTTP) becomes one implementation; a new `DirectPostgresClient` (asyncpg) becomes another.
- **Alternatives:** (a) Keep `SupabaseClient` as the only implementation — rejected because it couples the system to PostgREST HTTP, preventing use with plain PostgreSQL, Amazon RDS, or other Postgres-compatible databases. (b) Use an ORM like SQLAlchemy — rejected because the system already uses PostgreSQL functions (RPC calls) for atomic operations, and an ORM would add unnecessary abstraction over what are essentially stored procedure calls.
- **Rationale:** All service modules already depend on the `SupabaseClient` interface (5 methods). By extracting this into a protocol and using a factory, we gain database portability with minimal refactoring. Services continue to call `db.rpc("function_name", params)` and `db.query("table", ...)` regardless of backend. The migration SQL is standard PostgreSQL and works with any Postgres-compatible database.

Protocol definition:
```python
# src/db.py
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class DatabaseClient(Protocol):
    """Protocol for database backends. All implementations must support
    PostgreSQL-compatible operations."""

    async def rpc(self, function_name: str, params: dict[str, Any]) -> Any:
        """Call a stored PostgreSQL function."""
        ...

    async def query(
        self, table: str, query_params: str | None = None, select: str = "*"
    ) -> list[dict[str, Any]]:
        """Query a table with optional PostgREST-style filters."""
        ...

    async def insert(
        self, table: str, data: dict[str, Any], return_data: bool = True
    ) -> dict[str, Any]:
        """Insert a row."""
        ...

    async def update(
        self, table: str, match: dict[str, Any], data: dict[str, Any],
        return_data: bool = True
    ) -> list[dict[str, Any]]:
        """Update matching rows."""
        ...

    async def delete(self, table: str, match: dict[str, Any]) -> None:
        """Delete matching rows."""
        ...

    async def close(self) -> None:
        """Close the connection."""
        ...


def create_db_client(config: DatabaseConfig | None = None) -> DatabaseClient:
    """Factory: returns SupabaseClient or DirectPostgresClient based on config."""
    config = config or get_config().database
    if config.backend == "supabase":
        return SupabaseClient(config.supabase)
    elif config.backend == "postgres":
        return DirectPostgresClient(config.postgres)
    else:
        raise ValueError(f"Unknown database backend: {config.backend}")
```

Configuration:
```python
# src/config.py
@dataclass
class DatabaseConfig:
    backend: str = "supabase"  # "supabase" or "postgres"
    supabase: SupabaseConfig | None = None
    postgres: PostgresConfig | None = None
    # Env: DB_BACKEND=supabase (default) or DB_BACKEND=postgres

@dataclass
class PostgresConfig:
    dsn: str = ""  # e.g., "postgresql://user:pass@localhost:5432/coordinator"
    pool_min: int = 2
    pool_max: int = 10
    # Env: POSTGRES_DSN, POSTGRES_POOL_MIN, POSTGRES_POOL_MAX
```

Impact on existing code:
- `get_db()` calls `create_db_client()` instead of directly instantiating `SupabaseClient`
- Service classes already accept `db: DatabaseClient | None` — change type to `DatabaseClient | None`
- No changes to service method signatures or business logic
- `DirectPostgresClient` translates `rpc()` calls to `SELECT function_name(params)` via asyncpg
- `DirectPostgresClient` translates `query()` PostgREST filter syntax to SQL WHERE clauses

#### Trade-offs: PostgREST (HTTP) vs Direct PostgreSQL (asyncpg)

| Dimension | PostgREST / Supabase (HTTP) | Direct PostgreSQL (asyncpg) |
|-----------|---------------------------|----------------------------|
| **Latency** | Higher — HTTP overhead per request (~2-10ms roundtrip) | Lower — persistent connections, binary protocol (~0.5-2ms) |
| **Connection management** | Stateless — no pool to manage, scales horizontally | Requires connection pool management (pool_min/max) |
| **Auth model** | Built-in RLS via JWT/API key — PostgREST enforces row-level security | Must enforce RLS in application or use `SET ROLE` per connection |
| **Real-time** | Supabase real-time subscriptions built-in | Requires LISTEN/NOTIFY setup manually |
| **Deployment** | Zero-config with Supabase Cloud | Requires PostgreSQL server provisioning |
| **Portability** | Tied to PostgREST query syntax in `query()` method | Standard SQL — works with any PostgreSQL-compatible DB (RDS, Aurora, CockroachDB, Neon) |
| **Transactions** | No multi-statement transactions (each RPC call is its own) | Full multi-statement transaction support |
| **Observability** | HTTP status codes, standard API monitoring | Requires database-level monitoring (pg_stat, etc.) |
| **Best for** | Cloud deployments, low-ops, Supabase ecosystem | Self-hosted, high-throughput, existing Postgres infrastructure |

The factory pattern lets teams choose based on their infrastructure. Default is `supabase` (current behavior, zero migration effort). Teams with existing PostgreSQL can set `DB_BACKEND=postgres` and provide a DSN.

### 3. Service Layer Pattern (Mandatory for all new modules)

- **Decision:** All new services SHALL follow the established pattern in `locks.py`, `work_queue.py`, `discovery.py`, and `handoffs.py`:
  - `@dataclass` result/entity types with `from_dict()` factory methods
  - Service class with `__init__(self, db: DatabaseClient | None = None)` for testable DI
  - `@property def db` with lazy initialization via `get_db()`
  - Async methods calling Supabase RPCs with config-based parameter injection
  - Module-level singleton getter function (e.g., `get_guardrails_service()`)
- **Alternatives:** (a) Different patterns per module — rejected because consistency reduces cognitive load and enables shared test fixtures. (b) Dependency injection framework — rejected as over-engineering.
- **Rationale:** Directly mirrors the proven patterns in `locks.py:71-220`. Tests use constructor injection to pass mock `SupabaseClient`, enabling respx-based unit tests without a running database.

Example structure for each new module:
```python
# src/guardrails.py (same pattern as src/locks.py)
@dataclass
class GuardrailViolation:
    pattern_name: str
    operation: str
    blocked: bool
    ...
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GuardrailViolation": ...

class GuardrailsService:
    def __init__(self, db: DatabaseClient | None = None):
        self._db = db
    @property
    def db(self) -> DatabaseClient: ...
    async def check_operation(self, operation: str, context: dict) -> GuardrailResult: ...

_service: GuardrailsService | None = None
def get_guardrails_service() -> GuardrailsService: ...
```

### 4. Configuration Extension

- **Decision:** Add new config dataclasses to `src/config.py` following the existing `SupabaseConfig`/`AgentConfig`/`LockConfig` pattern, plus `DatabaseConfig` for backend selection and `PostgresConfig` for direct connections. Load from environment variables with sensible defaults.
- **Rationale:** Consistent with existing configuration management; no new dependencies needed.

New config dataclasses:
```python
@dataclass
class GuardrailsConfig:
    patterns_cache_ttl_seconds: int = 300   # Refresh DB patterns every 5 min
    enable_code_fallback: bool = True        # Use hardcoded patterns if DB unavailable
    # Env: GUARDRAILS_CACHE_TTL, GUARDRAILS_CODE_FALLBACK

@dataclass
class ProfilesConfig:
    default_trust_level: int = 2             # Standard trust for unregistered agents
    enforce_resource_limits: bool = True
    # Env: PROFILES_DEFAULT_TRUST, PROFILES_ENFORCE_LIMITS

@dataclass
class AuditConfig:
    retention_days: int = 90
    async_logging: bool = True               # Non-blocking audit inserts
    # Env: AUDIT_RETENTION_DAYS, AUDIT_ASYNC

@dataclass
class NetworkPolicyConfig:
    default_policy: str = "deny"             # "deny" or "allow" for unspecified domains
    # Env: NETWORK_DEFAULT_POLICY
```

### 5. Guardrails Architecture

- **Decision:** Implement guardrails as a deterministic pattern-matching engine using regex and AST analysis, not LLM-based reasoning. Patterns are stored in database with a code-level fallback registry.
- **Alternatives:** (a) LLM-based analysis — rejected because guardrails must be deterministic and not bypassable via prompt injection. (b) Code-only patterns — rejected because database storage allows runtime updates without redeployment.
- **Rationale:** The spec explicitly calls for deterministic pattern matching. Database patterns allow operational flexibility while code fallbacks ensure safety even if the database is unavailable.

#### Integration points with existing features:
- **Work Queue**: `complete_work()` runs guardrail check on task result before marking complete. If destructive patterns found, task completion is blocked and violation is logged.
- **File Locking**: `acquire_lock()` checks if file matches credential patterns (`*.env`, `*credentials*`). If so, requires elevated trust level.
- **Verification Gateway**: `execute_verification()` runs guardrail pre-check on changeset before dispatching to executors.

### 6. Agent Profiles Implementation

- **Decision:** Use dataclass models (matching the established service layer pattern) for profile definitions with preconfigured profiles seeded via database migration. Profiles are stored in database with code-level defaults.
- **Alternatives:** (a) YAML files only — rejected because cloud agents need database access. (b) Database only — rejected because defaults must work without database setup.
- **Rationale:** Hybrid approach matches the existing pattern of env-based config with database storage.

#### Enforcement points:
- **MCP layer** (`coordination_mcp.py`): Profile checked before each tool call. Operations not in `allowed_operations` are rejected.
- **HTTP API** (`coordination_api.py`): API key maps to profile. Trust level and resource limits checked per request.
- **Supabase RPCs**: Profile-aware functions receive `trust_level` parameter for database-level enforcement where needed.

### 7. Audit Trail Immutability

- **Decision:** Use a PostgreSQL table with INSERT-only policy (no UPDATE/DELETE allowed via RLS). A `BEFORE UPDATE OR DELETE` trigger will RAISE EXCEPTION to enforce immutability at the database level.
- **Alternatives:** (a) Application-level enforcement only — rejected because it can be bypassed. (b) Separate audit database — rejected as over-engineering for current scale.
- **Rationale:** Database-level enforcement is the strongest guarantee of immutability.

Trigger implementation:
```sql
CREATE OR REPLACE FUNCTION raise_immutable_error()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Audit log entries are immutable — UPDATE and DELETE are prohibited';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prevent_audit_modification
BEFORE UPDATE OR DELETE ON audit_log
FOR EACH ROW EXECUTE FUNCTION raise_immutable_error();
```

#### Logging semantics:
- **Sync/async:** Audit inserts are async (fire-and-forget) for operational performance. Compliance queries may lag by up to 30 seconds.
- **Authoritative source:** For operational decisions (e.g., "is this lock released?"), use the authoritative table (`file_locks`), not the audit log. The audit log is for forensics and compliance.
- **Completeness guarantee:** Every coordination operation logs `{timestamp, agent_id, agent_type, operation, parameters, result, duration_ms}`. Gaps are detectable by comparing operation counts against audit entry counts.

### 8. MCP Tools and Resources for Phase 3

- **Decision:** Phase 3 features expose MCP tools and resources following the existing pattern in `coordination_mcp.py`.
- **Rationale:** Agents need programmatic access to safety features, not just enforcement.

| Feature | MCP Tools | MCP Resources |
|---------|-----------|---------------|
| Memory | `remember`, `recall` | `memories://recent` |
| Guardrails | `check_guardrails` | `guardrails://patterns` |
| Profiles | `get_my_profile` | `profiles://current` |
| Audit | `query_audit` | `audit://recent` |

Note: Network policies are enforced transparently — no MCP tools needed. Agents don't explicitly request domain access; the coordination layer checks policies when proxying operations.

### 9. Phase 4 Deferral

- **Decision:** Defer Strands SDK and AgentCore integration to a separate proposal. The evaluation framework (already implemented) serves as Phase 4's measurement capability.
- **Alternatives:** Include everything in one proposal — rejected because Strands/AgentCore introduce external AWS dependencies requiring separate evaluation.
- **Rationale:** Phase 2-3 features are self-contained and can be delivered independently. Phase 4 requires AWS account setup and Strands SDK evaluation.

### 10. Evaluation Framework Extension

- **Decision:** Extend the evaluation framework to measure Phase 3 safety features via new ablation flags, metrics, and task definitions.
- **Rationale:** Without measurement, guardrails/profiles/audit effectiveness cannot be validated. The spec defines success metrics (guardrail block rate >99%, audit completeness 100%, trust level accuracy <1% FP) that require instrumentation.

Changes to evaluation framework:
```python
# evaluation/config.py — extend AblationFlags
@dataclass
class AblationFlags:
    # Phase 1-2 (existing)
    locking: bool = True
    memory: bool = True
    handoffs: bool = True
    parallelization: bool = True
    work_queue: bool = True
    # Phase 3 (new)
    guardrails: bool = True
    profiles: bool = True
    audit: bool = True
    network_policies: bool = True

# evaluation/metrics.py — extend CoordinationMetrics
@dataclass
class SafetyMetrics:
    guardrail_checks: int = 0
    guardrail_blocks: int = 0
    guardrail_block_rate: float = 0.0
    profile_enforcement_checks: int = 0
    profile_violations_blocked: int = 0
    audit_entries_written: int = 0
    audit_write_latency_ms: float = 0.0
    network_requests_blocked: int = 0
```

New evaluation tasks needed (YAML in `evaluation/tasks/`):
- `tier1/destructive-git-operation.yaml` — agent attempts `git push --force`, guardrails should block
- `tier1/credential-file-access.yaml` — agent attempts to modify `.env`, guardrails should block
- `tier2/trust-level-enforcement.yaml` — agent with trust_level=1 attempts elevated operation
- `tier2/resource-limit-enforcement.yaml` — agent exceeds max_file_modifications
- `tier3/audit-completeness.yaml` — multi-step task, verify all operations logged

## Risks / Trade-offs

- **Migration ordering risk**: New migrations must not conflict with data already in Phase 1 tables.
  - Mitigation: Each migration is additive (CREATE TABLE, not ALTER on existing tables). Integration tests verify compatibility.

- **Guardrail bypass risk**: Agents might find ways around pattern matching.
  - Mitigation: Defense in depth — database patterns + code fallback + audit logging. All bypass attempts are logged.

- **Performance risk from audit logging**: Logging every operation could slow coordination.
  - Mitigation: Audit inserts are async with eventual consistency (up to 30s lag). Retention policy (90 days default) prevents unbounded growth.

- **Profile enforcement scope**: Profiles only enforce within the coordination layer, not at the OS level.
  - Mitigation: This is documented. OS-level enforcement is the responsibility of AgentCore (Phase 4).

- **Backward compatibility**: Phase 1 agents connecting after Phase 3 deployment.
  - Mitigation: New features are additive. Phase 1 agents operate normally — guardrails default to permissive for trust_level >= 3 (local CLI agents), audit logs their operations transparently, and profiles assign defaults based on agent_type. No agent changes required.

- **Evaluation framework scope creep**: Adding safety metrics and tasks is additional work.
  - Mitigation: Safety tasks and metrics are minimal (5 tasks, 1 new dataclass). Without them, the spec's success metrics (guardrail block rate >99%, audit completeness 100%) cannot be validated.

## Migration Plan

1. Deploy migrations 004-007 to Supabase (independent, no inter-deps)
2. Deploy migrations 008-009 to Supabase (depend on 007)
3. Deploy new Python modules (memory, guardrails, profiles, audit, network_policies, github_coordination)
4. Update MCP server with new tools (remember, recall, check_guardrails, get_my_profile, query_audit)
5. Update HTTP API with new endpoints for Phase 3 features
6. Extend evaluation framework (ablation flags, metrics, tasks)
7. Update README.md with complete feature list, architecture diagram, and setup instructions
8. Update docs/agent-coordinator.md and spec implementation status
9. Rollback: Drop new tables in reverse migration order (009→004). No Phase 1 tables are affected.

## Testing Strategy

All new modules SHALL follow the testing patterns established in `tests/test_locks.py` and `tests/test_work_queue.py`:

- **Unit tests**: respx-mocked HTTP responses, service class instantiated with mock `SupabaseClient`
- **Fixtures**: Extend `tests/conftest.py` with fixtures for new response payloads (e.g., `guardrail_match_response`, `profile_enforcement_response`)
- **Coverage target**: >90% code coverage for all new modules
- **Type checking**: `mypy --strict src/` with zero errors (per `pyproject.toml` strict mode)
- **Linting**: `ruff check src/ tests/` with zero errors (per `pyproject.toml` rules)
- **RLS/immutability tests**: Separate integration test file verifying audit table UPDATE/DELETE rejection
- **Backward compatibility tests**: Verify Phase 1 tool calls succeed unchanged after Phase 3 deployment

### 11. Cedar Policy Engine (Configurable Enhancement)

- **Decision:** Introduce Cedar (AWS's open-source policy-as-code language) as an optional, configurable authorization engine that can replace the custom profile enforcement and network policy enforcement code. Controlled by `POLICY_ENGINE=cedar` (default: `native`). The regex-based guardrails engine and audit trail remain separate — Cedar handles authorization ("can this agent do this?"), not content inspection ("does this output contain destructive patterns?") or logging.
- **Alternatives:** (a) Use Cedar for everything including guardrails — rejected because Cedar has no regex operator and cannot do content inspection against operation output text. (b) Skip Cedar entirely — rejected because Amazon Bedrock AgentCore uses Cedar for exactly the same purpose (agent-to-tool authorization at gateway level), making Cedar adoption a strategic alignment for Phase 4 AgentCore integration. (c) Build a custom policy DSL — rejected as reinventing what Cedar already provides with formal verification.
- **Rationale:** Cedar's Principal/Action/Resource/Context (PARC) model maps directly to our Agent/Operation/Resource model. Adopting Cedar now means Phase 4 AgentCore policies are already in the right format. The `cedarpy` Python library (Rust engine via PyO3) evaluates policies in microseconds. This mirrors AgentCore's own architecture where "Guardrails manage expression; Policy manages action."

#### Entity model mapping

| Cedar Concept | Agent-Coordinator Mapping | Examples |
|---------------|--------------------------|----------|
| **Principal** | Agent identity | `Agent::"claude-code-agent-1"`, `AgentType::"cloud"` |
| **Action** | Coordination operation | `Action::"acquire_lock"`, `Action::"complete_work"`, `Action::"network_access"` |
| **Resource** | Target of operation | `File::"src/config.py"`, `Domain::"github.com"`, `Task::"task-uuid"` |
| **Context** | Request parameters | `{trust_level: 3, files_modified: 5, department: "eng"}` |

#### What Cedar replaces vs. what it doesn't

| Current Module | Cedar Replaces? | Rationale |
|----------------|----------------|-----------|
| `profiles.py` (agent profiles) | **Yes** | Cedar's PARC model is purpose-built for "can agent X do operation Y on resource Z?" — this is RBAC/ABAC |
| `network_policies.py` (domain access) | **Yes** | Domain allowlists/denylists map directly to Cedar permit/forbid on `Domain::` resources |
| `guardrails.py` (content inspection) | **No** | Guardrails do regex content inspection on output text. Cedar has no regex operator — it does authorization, not content scanning |
| `audit.py` (operation logging) | **No** | Audit is logging, not authorization. Cedar makes decisions; audit records them |

#### Example Cedar policies for agent-coordinator

```cedar
// Profile: restrict reviewers to read-only operations
forbid(
    principal is AgentType::"reviewer",
    action in [Action::"acquire_lock", Action::"complete_work", Action::"submit_work"],
    resource
);

// Trust level: block elevated operations for low-trust agents
forbid(
    principal,
    action == Action::"acquire_lock",
    resource
)
when { principal.trust_level < 2 };

// Resource limits: block after max file modifications exceeded
forbid(
    principal,
    action == Action::"acquire_lock",
    resource
)
when { context.files_modified >= principal.max_file_modifications };

// Network: allow GitHub access for all agents
permit(
    principal,
    action == Action::"network_access",
    resource == Domain::"github.com"
);

// Network: allow npm registry for all agents
permit(
    principal,
    action == Action::"network_access",
    resource == Domain::"registry.npmjs.org"
);

// All other domains denied by Cedar's default-deny semantics

// Elevated: allow force-push only for trust_level >= 3
permit(
    principal,
    action == Action::"force_push",
    resource
)
when { principal.trust_level >= 3 };
```

#### Architecture: hybrid enforcement

```
Agent Request
    │
    ├── [1] Cedar Policy Engine (authorization) ─── POLICY_ENGINE=cedar
    │       "Is this agent allowed to call complete_work() on this resource?"
    │       Replaces: profiles.py + network_policies.py
    │       Engine: cedarpy (Rust via PyO3, microsecond eval)
    │
    ├── [2] Regex Guardrails Engine (content inspection) ─── Always active
    │       "Does the task result contain destructive patterns?"
    │       Remains: guardrails.py (regex + AST analysis)
    │       Database patterns + code fallback
    │
    └── [3] Audit Trail (logging) ─── Always active
            Logs both Cedar decisions and guardrail checks
            Remains: audit.py (async, immutable)
```

#### Implementation approach

```python
# src/policy_engine.py
from cedarpy import is_authorized, AuthzResult, Decision

@dataclass
class PolicyDecision:
    allowed: bool
    reason: str | None = None
    policy_id: str | None = None

    @classmethod
    def from_cedar(cls, result: AuthzResult) -> "PolicyDecision":
        return cls(
            allowed=result.allowed,
            reason=str(result.diagnostics) if not result.allowed else None,
        )

class CedarPolicyEngine:
    """Cedar-based authorization engine. Replaces ProfilesService + NetworkPolicyService
    when POLICY_ENGINE=cedar."""

    def __init__(self, db: DatabaseClient | None = None):
        self._db = db
        self._policies_cache: str | None = None
        self._entities_cache: list | None = None
        self._cache_expiry: float = 0

    @property
    def db(self) -> DatabaseClient:
        if self._db is None:
            self._db = get_db()
        return self._db

    async def check_operation(
        self, agent_id: str, agent_type: str, operation: str,
        resource: str, context: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        policies = await self._load_policies()
        entities = await self._load_entities()
        result = is_authorized(
            request={
                "principal": f'Agent::"{agent_id}"',
                "action": f'Action::"{operation}"',
                "resource": f'{self._resource_type(resource)}::"{resource}"',
                "context": context or {},
            },
            policies=policies,
            entities=entities,
        )
        return PolicyDecision.from_cedar(result)
```

#### Configuration

```python
# src/config.py
@dataclass
class PolicyEngineConfig:
    engine: str = "native"           # "native" or "cedar"
    policy_cache_ttl_seconds: int = 300
    enable_code_fallback: bool = True
    schema_path: str = ""            # Path to .cedarschema file (optional)
    # Env: POLICY_ENGINE, POLICY_CACHE_TTL, POLICY_CODE_FALLBACK
```

#### Python SDK

- **Package**: `cedarpy` on PyPI (v4.8.0+, Rust core via PyO3)
- **API**: `is_authorized(request, policies, entities)` → `AuthzResult` (microsecond eval)
- **Batch**: `is_authorized_batch()` for bulk authorization checks
- **Validation**: `validate_policies(policies, schema)` catches policy errors at write time
- **Dependency**: Added as optional extra `[cedar]` in `pyproject.toml` — only required when `POLICY_ENGINE=cedar`

#### AgentCore alignment

Adopting Cedar provides a direct migration path to Phase 4:
1. Local Cedar policies can later be managed via AgentCore Policy service
2. AgentCore's Principal=Agent, Action=ToolCall, Resource=Target maps 1:1 to our model
3. AgentCore's natural language → Cedar authoring works with our policy schema
4. AgentCore's gateway interception pattern matches our coordination layer enforcement


## Resolved Questions

1. **Should the verification_gateway Python code be refactored into `src/` or kept as a separate subpackage?**
   - **Decision**: Kept as a separate subpackage (`verification_gateway/`). The verification gateway has distinct deployment concerns (webhook endpoints, executor backends) and its own entry point (`gateway.py`). Refactoring into `src/` would conflate coordination services with verification routing. SQL schemas were extracted into the main migration pipeline (004-005) while Python code remained in its directory.

2. **Should guardrail patterns be seeded via migration (SQL INSERT) or loaded at application startup from a patterns file?**
   - **Decision**: Both — migration seeds default patterns via SQL INSERT (migration `006_guardrails_tables.sql`), and a hardcoded fallback registry in `guardrails.py` ensures patterns are enforced even when the database is unavailable. The code fallback is the authoritative baseline; database patterns allow runtime additions without redeployment.

3. **Should `check_guardrails` be an explicit MCP tool agents call proactively, or should guardrail checks be transparently woven into existing tools?**
   - **Decision**: Both — `check_guardrails` is exposed as an explicit MCP tool for proactive agent use, AND guardrail checks are transparently integrated as a pre-execution hook in `complete_work()`. Agents can proactively check before attempting operations, while the system enforces checks as a safety net regardless.

4. **Network policy enforcement location: coordinator-level proxy or agent SDK integration?**
   - **Decision**: Coordinator-level enforcement. The `NetworkPolicyService.check_domain()` is called within the coordination layer, not at the agent level. This ensures enforcement without requiring per-agent changes and provides a single point of audit logging.
