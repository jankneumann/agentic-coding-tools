# Change: Complete Missing Coordination Features (Phases 2-4)

## Why

The agent-coordinator documentation (`docs/agent-coordinator.md`) and spec (`openspec/specs/agent-coordinator/spec.md`) both state that Phases 2-4 are only "Specified" (not implemented). However, a code audit reveals that significant Phase 2-3 work already exists in the `verification_gateway/` directory — including an HTTP API, memory endpoints, verification gateway, and SQL schemas — but this code is not integrated into the main migration pipeline and several key safety/governance features remain unbuilt. The documentation is outdated, and the gap between what exists and what's specified creates confusion and risk.

## Gap Analysis

### Already Implemented (undocumented)

| Feature | Phase | Location |
|---------|-------|----------|
| HTTP API (15+ endpoints, API key auth) | 2 | `verification_gateway/coordination_api.py` |
| Memory API (episodic, working, procedural) | 2 | `verification_gateway/coordination_api.py` |
| Memory DB schema (3 tables, 3 functions) | 2 | `verification_gateway/supabase_memory_schema.sql` |
| Verification gateway (4 tiers, 5 executors) | 3 | `verification_gateway/gateway.py` |
| Verification DB schema (4 tables, 3 views, 2 functions) | 3 | `verification_gateway/supabase_schema.sql` |
| GitHub/Agent webhooks | 3 | `verification_gateway/gateway.py` |
| Inline static analysis (ruff, mypy, tsc) | 3 | `verification_gateway/gateway.py` |
| Evaluation framework | 4 | `agent-coordinator/evaluation/` |
| Session continuity (handoff documents) | 1+ | `src/handoffs.py`, migration `002_handoff_documents.sql` |
| Agent discovery & heartbeat | 1+ | `src/discovery.py`, migration `003_agent_discovery.sql` |
| Declarative team composition | 1+ | `src/teams.py`, `teams.yaml` |

### Genuinely Missing

| Feature | Phase | Spec Requirements |
|---------|-------|-------------------|
| Guardrails engine | 3 | Req: Destructive Operation Guardrails |
| Agent profiles with trust levels | 3 | Req: Agent Profiles |
| Network access policies | 3 | Req: Network Access Policies |
| Audit trail | 3 | Req: Audit Trail |
| GitHub-mediated coordination | 2 | Req: GitHub-Mediated Coordination |
| Strands SDK orchestration | 4 | Req: Agent Orchestration |
| AgentCore integration | 4 | Req: Agent Orchestration |
| Memory MCP tools (remember/recall) | 2 | Req: MCP Server Interface (Phase 2 note) |
| Schema integration into main migrations | 2-3 | Req: Database Persistence |

### Integration Gaps

The `verification_gateway/` directory contains standalone SQL schemas (`supabase_schema.sql`, `supabase_memory_schema.sql`) that are **not** part of the main migration pipeline (`supabase/migrations/`). This means:
- Schemas are defined but not deployable via standard migration workflow
- No migration ordering or dependency management with Phase 1 tables
- Verification and memory features cannot be enabled without manual SQL execution

### Architecture Alignment Gaps (identified during proposal review)

1. **Service layer pattern not specified**: New modules (guardrails, profiles, audit, memory, network_policies) must follow the established pattern in `locks.py` — dataclass results with `from_dict()`, service class with DI constructor, `@property db` lazy init, module-level singleton getter. The original proposal did not mandate this.

2. **Configuration management missing**: No config dataclasses were specified for new features. Each module needs env-based config following the `SupabaseConfig`/`LockConfig` pattern in `src/config.py`.

3. **MCP tools/resources incomplete for Phase 3**: Original proposal only specified `remember`/`recall` MCP tools. Phase 3 features (guardrails, profiles, audit) also need MCP tools and resources for agent access.

4. **Cross-feature integration points undefined**: Guardrails must hook into `complete_work()`, profiles must hook into `acquire_lock()` and HTTP API, audit must hook into all existing services. These integration points were not specified.

5. **Evaluation framework not extended**: The evaluation framework has no ablation flags, metrics, or tasks for Phase 3 safety features. Without them, the spec's success metrics (guardrail block rate >99%, audit completeness 100%) cannot be validated.

6. **Backward compatibility not addressed**: No analysis of how Phase 1 agents behave after Phase 3 deployment.

7. **README.md outdated**: Still says "Phase 1 MVP" and lists only 6 MCP tools. Architecture diagram shows only Phase 1 components. No setup instructions for Phase 2-3 features.

## What Changes

### Database Abstraction (Foundational)
- Introduce `DatabaseClient` protocol in `src/db.py` abstracting the database interface (`rpc`, `query`, `insert`, `update`, `delete`, `close`)
- Implement `create_db_client()` factory function selecting backend based on `DB_BACKEND` env var
- Existing `SupabaseClient` (PostgREST HTTP) becomes one implementation; new `DirectPostgresClient` (asyncpg) enables direct PostgreSQL connections for self-hosted, RDS, Neon, or any Postgres-compatible database
- All service classes updated to depend on the `DatabaseClient` protocol instead of `SupabaseClient`

### Phase 2 Completion
- Integrate memory database schema into main migrations (`004_memory_tables.sql`)
- Create `src/memory.py` service following established service layer pattern
- Add `remember` and `recall` MCP tools + `memories://recent` resource to `coordination_mcp.py`
- Implement GitHub-mediated coordination fallback (issue labels, branch naming)
- Integrate verification_gateway coordination_api.py with main project structure

### Phase 3 Completion
- Implement guardrails engine (`src/guardrails.py`) with destructive operation pattern registry and code fallback
- Implement agent profiles (`src/profiles.py`) with trust levels 0-4 and resource limits
- Implement network access policies (`src/network_policies.py`) with domain allowlists/denylists
- Implement audit trail (`src/audit.py`) with immutable append-only logging and async inserts
- Add Phase 3 MCP tools (`check_guardrails`, `get_my_profile`, `query_audit`) and resources
- Integrate verification schema into main migrations (`005_verification_tables.sql`)
- Create guardrails, profiles, audit, and network policy migrations (006-009)
- Complete verification executor implementations (GitHub Actions, NTM, E2B — currently skeleton)
- Integrate profile checks into existing MCP tools and HTTP API
- Integrate guardrail pre-execution hooks into `complete_work()`
- Add audit logging hooks to all existing coordination operations
- Add config dataclasses (`GuardrailsConfig`, `ProfilesConfig`, `AuditConfig`, `NetworkPolicyConfig`) to `src/config.py`

### Evaluation Framework Extension
- Add Phase 3 ablation flags: `guardrails`, `profiles`, `audit`, `network_policies`
- Add `SafetyMetrics` dataclass for guardrail block rate, profile enforcement, audit completeness
- Create 5 new evaluation tasks testing destructive operations, trust enforcement, and audit completeness
- Update report generator to include safety metrics

### Cedar Policy Engine (Configurable Enhancement)
- Introduce Cedar (AWS open-source policy-as-code language) as an optional authorization engine (`POLICY_ENGINE=cedar`)
- When enabled, Cedar replaces custom profile enforcement (`profiles.py`) and network policy code (`network_policies.py`) with a unified policy-as-code engine
- Cedar's PARC model (Principal/Action/Resource/Context) maps directly to Agent/Operation/Resource
- Regex guardrails remain separate — Cedar handles authorization, not content inspection
- Audit trail remains separate — Cedar makes decisions, audit logs them
- `cedarpy` dependency (Rust engine via PyO3, microsecond evaluation) added as optional `[cedar]` extra
- Database table `cedar_policies` stores policy text, loaded and cached with configurable TTL
- Cedar schema defines entity types: `Agent`, `AgentType`, `Action`, `File`, `Domain`, `Task`
- Strategic alignment: Amazon Bedrock AgentCore uses Cedar for agent-to-tool authorization — adopting Cedar now provides a direct migration path for Phase 4 AgentCore integration
- Default is `native` (current profiles.py + network_policies.py code), Cedar is opt-in


### Phase 4 (Deferred — Design Only)
- Strands SDK orchestration and AgentCore integration are deferred to a future proposal
- Current evaluation framework is sufficient for Phase 4's measurement goals
- Design document captures integration architecture for when Strands/AgentCore are adopted

### Documentation Updates
- Update `docs/agent-coordinator.md` implementation status table and architecture diagram
- Update `openspec/specs/agent-coordinator/spec.md` implementation status and database tables sections
- **Update `agent-coordinator/README.md`**: Expand from "Phase 1 MVP" to full system documentation — all MCP tools/resources, updated architecture diagram, Phase 2-3 setup instructions, new environment variables, updated file structure, and revised future phases section

## Impact

- Affected specs: `agent-coordinator`, `evaluation-framework`
- Affected code:
  - `agent-coordinator/src/` (new modules: guardrails.py, profiles.py, audit.py, memory.py, network_policies.py, github_coordination.py, policy_engine.py)
  - `agent-coordinator/src/config.py` (new config dataclasses)
  - `agent-coordinator/src/coordination_mcp.py` (add Phase 2-3 tools and resources)
  - `agent-coordinator/src/locks.py`, `work_queue.py`, `handoffs.py`, `discovery.py` (audit logging hooks, profile checks)
  - `agent-coordinator/supabase/migrations/` (new migrations 004-009)
  - `agent-coordinator/verification_gateway/` (integrate schemas into main pipeline)
  - `agent-coordinator/evaluation/` (ablation flags, metrics, tasks for Phase 3)
  - `agent-coordinator/README.md` (comprehensive update with Phase 2-3 documentation)
  - `agent-coordinator/.env.example` (new environment variables)
  - `docs/agent-coordinator.md` (update status)
  - `openspec/specs/agent-coordinator/spec.md` (update status metadata)
  - `agent-coordinator/cedar/` (Cedar schema and default policies, only when `POLICY_ENGINE=cedar`)
  - `agent-coordinator/pyproject.toml` (`cedarpy` as optional `[cedar]` dependency)
- **BREAKING**: None. All changes are additive. Phase 1 agents operate unchanged after deployment. Cedar is opt-in via `POLICY_ENGINE=cedar` and does not affect the default `native` engine.
