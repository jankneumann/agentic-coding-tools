## Context

The agent-coordinator has significant Phase 2-3 code in the `verification_gateway/` directory that exists independently of the main `src/` and `supabase/migrations/` structure. Additionally, several specified features (guardrails, profiles, audit, network policies, GitHub coordination) have no implementation at all. This design document addresses how to integrate existing code and build missing features.

## Goals / Non-Goals

- **Goals:**
  - Integrate verification_gateway SQL schemas into the main migration pipeline
  - Implement all missing Phase 2-3 features specified in the agent-coordinator spec
  - Maintain backward compatibility with Phase 1 deployments
  - Follow existing architectural patterns (async services, Supabase RPC, dataclass results)

- **Non-Goals:**
  - Strands SDK / AgentCore integration (deferred to separate proposal)
  - Rewriting existing verification_gateway Python code (refactoring is separate)
  - Adding new requirements beyond what's already specified

## Decisions

### 1. Schema Integration Strategy

- **Decision:** Create new numbered migrations (004-009) that extract and adapt SQL from `verification_gateway/*.sql` files. Do NOT modify existing migrations 000-003.
- **Alternatives:** (a) Copy SQL files directly into migrations/ — rejected because they need adaptation for compatibility with existing tables. (b) Keep schemas separate — rejected because it prevents standard deployment.
- **Rationale:** Numbered migrations ensure ordering, allow rollback, and work with standard Supabase migration tooling.

### 2. Guardrails Architecture

- **Decision:** Implement guardrails as a deterministic pattern-matching engine using regex and AST analysis, not LLM-based reasoning. Patterns are stored in database with a code-level fallback registry.
- **Alternatives:** (a) LLM-based analysis — rejected because guardrails must be deterministic and not bypassable via prompt injection. (b) Code-only patterns — rejected because database storage allows runtime updates without redeployment.
- **Rationale:** The spec explicitly calls for deterministic pattern matching. Database patterns allow operational flexibility while code fallbacks ensure safety even if the database is unavailable.

### 3. Agent Profiles Implementation

- **Decision:** Use Pydantic models for profile validation with preconfigured profiles loaded from the spec's YAML definitions. Profiles are stored in database with code-level defaults.
- **Alternatives:** (a) YAML files only — rejected because cloud agents need database access. (b) Database only — rejected because defaults must work without database setup.
- **Rationale:** Hybrid approach matches the existing pattern of env-based config with database storage.

### 4. Audit Trail Immutability

- **Decision:** Use a PostgreSQL table with INSERT-only policy (no UPDATE/DELETE allowed via RLS). A `BEFORE UPDATE OR DELETE` trigger will RAISE EXCEPTION to enforce immutability at the database level.
- **Alternatives:** (a) Application-level enforcement only — rejected because it can be bypassed. (b) Separate audit database — rejected as over-engineering for current scale.
- **Rationale:** Database-level enforcement is the strongest guarantee of immutability.

### 5. Phase 4 Deferral

- **Decision:** Defer Strands SDK and AgentCore integration to a separate proposal. The evaluation framework (already implemented) serves as Phase 4's measurement capability.
- **Alternatives:** Include everything in one proposal — rejected because Strands/AgentCore introduce external AWS dependencies requiring separate evaluation.
- **Rationale:** Phase 2-3 features are self-contained and can be delivered independently. Phase 4 requires AWS account setup and Strands SDK evaluation.

## Risks / Trade-offs

- **Migration ordering risk**: New migrations must not conflict with data already in Phase 1 tables.
  - Mitigation: Each migration is additive (CREATE TABLE, not ALTER on existing tables). Integration tests verify compatibility.

- **Guardrail bypass risk**: Agents might find ways around pattern matching.
  - Mitigation: Defense in depth — database patterns + code fallback + audit logging. All bypass attempts are logged.

- **Performance risk from audit logging**: Logging every operation could slow coordination.
  - Mitigation: Audit inserts are async and use UNLOGGED table option for high-throughput scenarios. Retention policy (90 days default) prevents unbounded growth.

- **Profile enforcement scope**: Profiles only enforce within the coordination layer, not at the OS level.
  - Mitigation: This is documented. OS-level enforcement is the responsibility of AgentCore (Phase 4).

## Migration Plan

1. Deploy migrations 004-009 to Supabase (additive, no downtime)
2. Deploy new Python modules (guardrails, profiles, audit, network_policies, github_coordination, memory)
3. Update MCP server with new tools (remember, recall)
4. Update documentation
5. Rollback: Drop new tables in reverse migration order. No Phase 1 tables are affected.

## Open Questions

1. Should the verification_gateway Python code be refactored into `src/` or kept as a separate subpackage?
2. What is the retention period for audit logs in production? (Spec says 90 days default)
3. Should guardrail patterns be seeded via migration or loaded at application startup?
