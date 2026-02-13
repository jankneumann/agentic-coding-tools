## Context

Our agent-coordinator uses Cedar for policy-as-code authorization, backed by a Supabase `cedar_policies` table with TTL-based caching (300s). Analysis against Permit.io's Four-Perimeter Framework and evaluation of OPAL for policy distribution identified gaps in identity delegation, real-time policy sync, human approval workflows, and contextual authorization. This design bridges those gaps while preserving our single-instance architecture and preparing for future OPAL adoption.

### Stakeholders
- Agent developers (need delegated identity, approval workflows)
- Security reviewers (need audit attribution, risk visibility)
- Platform operators (need real-time policy control, version rollback)

### Constraints
- Must not break existing Phase 1-3 agents (all changes additive)
- Must work in single-instance MCP topology (no OPAL server required)
- Cedar engine remains optional (`POLICY_ENGINE=cedar`); native engine gets equivalent features
- Supabase Realtime requires an active WebSocket connection (not available in all deployment modes)

## Goals / Non-Goals

- Goals:
  - Bind agent identity to the human/parent who authorized it
  - Provide blocking approval gates for high-risk operations
  - Reduce policy propagation latency from 300s to sub-second
  - Enable contextual risk-based authorization decisions
  - Create policy version history with rollback capability
  - Design abstractions that allow OPAL to be swapped in later

- Non-Goals:
  - Full OPAL deployment (deferred until multi-instance scaling)
  - OAuth/OIDC identity provider integration (future work)
  - Real-time dashboard UI for approvals (API-only in this phase)
  - Multi-tenant policy isolation
  - Replacing regex guardrails with semantic analysis

## Decisions

### Decision 1: Supabase Realtime over OPAL for policy sync

**Choice**: Use Supabase Realtime WebSocket subscription on `cedar_policies` table.

**Alternatives considered**:
- **OPAL Server + Cedar-Agent**: Production-proven at scale (Tesla, Walmart), but requires 3 new components (OPAL Server, OPAL Client, Cedar-Agent sidecar). Replaces our zero-latency in-process `cedarpy` with HTTP-based Cedar-Agent. Operational overhead unjustified for single-instance topology.
- **PostgreSQL LISTEN/NOTIFY**: Lightweight, no new dependencies. But requires direct PostgreSQL connection (not available via Supabase PostgREST). Would work with `DirectPostgresClient` but not `SupabaseClient`.
- **Short TTL (e.g., 5s)**: Simple but wasteful — polls every 5 seconds whether or not anything changed. Doesn't scale.

**Rationale**: Supabase Realtime is already in our stack (listed in project.md), adds zero new infrastructure, and provides sub-second push notification. The `PolicySyncService` abstraction ensures we can swap to OPAL when scaling demands it.

### Decision 2: Approval queue in PostgreSQL, not external workflow engine

**Choice**: Store approval requests in `approval_queue` table with simple state machine (pending → approved/denied/expired).

**Alternatives considered**:
- **GitHub Issues as approval queue**: Leverages existing GitHub integration. But adds latency (webhook round-trip), requires GitHub connectivity, and mixes authorization concerns with project management.
- **Temporal/Step Functions**: Production-grade workflow engines. Massive overkill for a state machine with 3 states and 1 transition.
- **Slack/email integration**: Good UX for reviewers. But adds external dependencies and notification plumbing. Can be layered on top of the DB-based queue later.

**Rationale**: PostgreSQL approval queue is simple, transactional, queryable via existing Supabase client, and composable with Realtime for push notifications to reviewers.

### Decision 3: Risk scoring as a Cedar context attribute, not a separate engine

**Choice**: Compute risk score in application layer, pass as `context.risk_score` to Cedar evaluation.

**Alternatives considered**:
- **Separate risk engine with its own policy language**: Maximum flexibility but fragments authorization logic across two systems.
- **Cedar-only risk computation**: Cedar lacks aggregation functions (no "count violations in last hour"). Can't compute risk scores in Cedar alone.
- **Static risk levels per operation**: Simple but misses contextual factors (agent history, time, session age).

**Rationale**: Risk scoring requires data aggregation (violation counts, session metadata) that Cedar can't perform. Computing the score in Python and passing it as Cedar context gives us the best of both: dynamic scoring with declarative policy thresholds.

### Decision 4: Delegated identity via session metadata, not token chains

**Choice**: Store `delegated_from` as a field on `agent_sessions` and pass to Cedar as a principal attribute.

**Alternatives considered**:
- **JWT delegation chains (macaroons-style)**: Cryptographically verifiable delegation. But requires PKI infrastructure, token management, and doesn't integrate with our environment-variable-based identity model.
- **OAuth2 token exchange (RFC 8693)**: Standard for impersonation/delegation. Requires an authorization server we don't have.
- **No delegation (status quo)**: Simplest, but leaves the fundamental gap identified in Permit.io analysis.

**Rationale**: Session-level delegation metadata is the minimal viable approach. It doesn't provide cryptographic verification (a known gap we accept), but it enables Cedar policies to reason about delegation chains and provides audit attribution. Token-based verification can be layered on later without changing the Cedar policy model.

## Risks / Trade-offs

- **Supabase Realtime availability**: If Realtime connection drops, we fall back to TTL-based polling (existing behavior). No degradation, just higher latency.
  → Mitigation: `PolicySyncService` implements reconnection with exponential backoff and logs connection state.

- **Approval queue blocking**: If no reviewer is available, operations hang until auto-deny timeout (1 hour default).
  → Mitigation: Configurable timeout, ability to set `approval_required: false` per guardrail rule for non-critical environments.

- **Risk score gaming**: An agent could avoid triggering violations to maintain a low risk score, then execute a destructive operation.
  → Mitigation: Risk scoring is additive to (not replacing) trust levels and guardrails. High-severity guardrails still block regardless of risk score.

- **Delegated identity spoofing**: Without cryptographic verification, `delegated_from` can be self-declared.
  → Mitigation: Audit trail captures the claim; HTTP API validates `delegated_from` against API key ownership. MCP sessions inherit from environment (trusted by host process). Acknowledged gap for future PKI work.

## Migration Plan

1. **Database migrations** (non-breaking):
   - Add `delegated_from` nullable column to `agent_sessions`
   - Create `approval_queue` table
   - Create `cedar_policies_history` table with trigger
   - Add `policy_version` column to `cedar_policies`

2. **Code deployment** (feature-flagged):
   - `POLICY_SYNC_ENABLED=false` (default) — Realtime sync off until operator enables
   - `APPROVAL_GATES_ENABLED=false` (default) — approval queue inactive
   - `RISK_SCORING_ENABLED=false` (default) — risk scorer returns 0.0 (pass-through)
   - All features can be enabled independently

3. **Rollback**: Drop new columns/tables. No existing data affected. Feature flags ensure instant disable without redeployment.

## Open Questions

- Should approval requests support escalation (auto-route to a different reviewer after N minutes)?
- Should risk score history be persisted for trend analysis, or is in-memory sliding window sufficient?
- When we adopt OPAL, should we run it alongside Supabase Realtime (belt-and-suspenders) or replace it entirely?
