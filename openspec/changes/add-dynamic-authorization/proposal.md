# Change: Add Dynamic Authorization Layer

## Why

Our current authorization model uses static trust levels (0-3), cached for 300 seconds, with no mechanism for delegated identity, human-in-the-loop approval, real-time policy revocation, or contextual risk scoring. Analysis against Permit.io's Four-Perimeter Framework for securing AI agents revealed three high-priority gaps: (1) no binding between agent identity and the human who invoked it, (2) no blocking approval gate for destructive operations, and (3) no cryptographic agent identity verification. Separately, evaluation of OPAL for policy distribution concluded it is premature for our single-instance topology but identified immediate improvements: Supabase Realtime push-based cache invalidation, policy version history, and a preparatory abstraction for future OPAL adoption.

## What Changes

### 1. Delegated Identity (Agent-to-Human Binding)

- Add `delegated_from` field to agent sessions and Cedar entities — tracks which human user (or parent agent) authorized this agent
- Extend Cedar schema with `DelegatingUser` entity type and `delegated_by` relationship
- Cedar policies can constrain operations based on the delegating user's permissions (e.g., an agent spawned by a junior developer inherits restricted trust)
- MCP tools and HTTP API accept optional `on_behalf_of` parameter, validated against session credentials
- Audit trail records both `agent_id` and `delegated_from` for full attribution

### 2. Human-in-the-Loop Approval Gates

- Add `approval_queue` table for operations that require human sign-off before execution
- Guardrails engine gains `severity: approval_required` level (in addition to existing `block` and `warn`)
- When a guardrail triggers `approval_required`, the operation is suspended and an approval request is inserted into the queue
- New MCP tools: `request_approval(operation, context)` and `check_approval(request_id)`
- New HTTP endpoints for human reviewers: `GET /approvals/pending`, `POST /approvals/{id}/decide`
- Approval decisions are logged immutably in audit trail
- Configurable auto-deny timeout (default: 1 hour) for unanswered requests

### 3. Supabase Realtime Policy Sync (OPAL-Preparatory)

- Subscribe to Supabase Realtime channel on `cedar_policies` table for INSERT/UPDATE/DELETE events
- On change event, immediately call `CedarPolicyEngine.invalidate_cache()` — reduces policy propagation from 300s TTL to sub-second
- Add `cedar_policies_history` table that captures every policy version via a PostgreSQL trigger (before-update/delete copies row to history)
- Add `PolicySyncService` abstraction with `start()`, `stop()`, `on_policy_change()` interface — designed so an `OpalPolicySyncService` implementation can replace it when we scale to multiple instances
- Add `policy_version` column to `cedar_policies` (auto-incrementing on update)

### 4. Contextual Risk Scoring

- Add `RiskScorer` that evaluates operation risk based on: trust level, operation type, resource sensitivity, recent violation count, session age, and time-of-day
- Risk score (0.0-1.0) determines authorization path: low risk → auto-allow, medium → log + allow, high → require approval
- Risk thresholds configurable via Cedar policies using new `context.risk_score` attribute
- Recent violation count tracked per-agent in a sliding window (default: 1 hour)

### 5. Policy Versioning and Rollback

- `cedar_policies_history` table stores: `policy_id`, `version`, `policy_text`, `changed_by`, `changed_at`, `change_type` (create/update/delete)
- New MCP tool: `list_policy_versions(policy_name, limit?)` for observability
- New HTTP endpoint: `POST /policies/{name}/rollback?version={n}` to restore a previous policy version
- All policy mutations logged in audit trail with before/after diff

## Impact

- Affected specs: `agent-coordinator`
- Affected code:
  - `agent-coordinator/src/policy_engine.py` (Realtime subscription, risk scoring integration, policy versioning)
  - `agent-coordinator/src/guardrails.py` (approval_required severity, risk score integration)
  - `agent-coordinator/src/profiles.py` (delegated identity resolution)
  - `agent-coordinator/src/audit.py` (delegated_from attribution, approval decision logging)
  - `agent-coordinator/src/config.py` (new `ApprovalConfig`, `PolicySyncConfig`, `RiskScoringConfig` dataclasses)
  - `agent-coordinator/src/coordination_mcp.py` (new tools: `request_approval`, `check_approval`, `list_policy_versions`)
  - `agent-coordinator/src/approval.py` (new — approval queue service)
  - `agent-coordinator/src/risk_scorer.py` (new — contextual risk scoring)
  - `agent-coordinator/src/policy_sync.py` (new — Realtime subscription service)
  - `agent-coordinator/cedar/schema.cedarschema` (DelegatingUser entity, risk_score context)
  - `agent-coordinator/cedar/default_policies.cedar` (approval-gated policies, risk-based conditions)
  - `agent-coordinator/supabase/migrations/` (new migrations for approval_queue, cedar_policies_history, agent_sessions delegated_from)
  - `agent-coordinator/verification_gateway/coordination_api.py` (approval endpoints, on_behalf_of parameter)
- **BREAKING**: None. All changes are additive. Delegated identity defaults to `null` (self-acting). Approval gates only activate for new `approval_required` guardrail rules. Risk scoring defaults to pass-through (threshold 1.0). Realtime sync is opt-in via `POLICY_SYNC_ENABLED=true`.
